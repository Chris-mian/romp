#!/usr/bin/env python3
"""Road B for issue #1735: keep the loaded decoded heap out of the cycle collector's walk.

A generation-two (full) collection visits every tracked container in the interpreter; the
request-serving kernel holds millions of them in decoded transcript trees, so a warm full
collection pauses every thread (the pusher included) for seconds. `gc.freeze()` moves the
currently tracked objects into a permanent generation the collector never walks again, so a
later full collection walks only what was allocated since. Measured (plans/gc-full-collection-pause.md):
a warm full collection over 5.6 million loaded objects fell from 2.83 s to 0.1 ms once they were
frozen, and the freeze itself is a pointer move.

Two operations, both at the pusher's IDLE boundary (never a timer), where a pause is paid with no
browser waiting:

  - a LOAD fold-in (cheap): `gc.collect(); gc.freeze()`. The collect walks only the unfrozen objects
    loaded since the last freeze, so it costs milliseconds; the freeze folds their survivors in.
    Keyed on the record cache's insert counter growing by a material number of trees.
  - a RELEASE reclaim (up to the full pause), STAGED: `gc.collect()` with the freeze IN PLACE first (cheap,
    it takes a released cycle allocated since the last freeze), then the owed refs are re-read and only a
    survivor drives `gc.unfreeze(); gc.collect()` (the frozen-heap walk); a `gc.freeze()` re-holds either
    way. A release the cheap walk took whole counts as a LOAD pass, so the backstop's bound does not stretch.

WHEN to reclaim is MEASURED, not guessed. Three review rounds each guessed cyclicity from a state flag
(a session's `client`, its thread) and each found a new path the guess missed (a teardown exception
after the client was cleared leaves a cyclic session with client None). So instead of deciding at the
pop, every session-end pop REGISTERS a `weakref.ref(session)` (with its worker thread) via `note_ended`,
and the idle tick judges each by observation: a dead ref died by reference counting (acyclic, no
reclaim); a live ref whose worker thread still runs is not garbage yet (kept for the next tick, a kill
mid-turn); a live ref whose thread has finished is a cycle the collector must take (reclaim once for all
such, then drop them). Exact on every path, no per-path reasoning. A BOUNDED BACKSTOP (after
`backstop_foldins` load fold-ins) covers any ended owner nobody registered. The record cache's
`released` counter is a /perf statistic, never a trigger: its entries are acyclic.

The thread test rests on CPython's own threading: a running session and its worker Thread reference each
other (the Thread holds the session as its `_target`), and `Thread.run` deletes `_target` in a `finally`
when it returns, so once the thread has finished it no longer holds the session. A live ref whose thread
has finished is therefore held by a DIFFERENT surviving cycle (a traceback frame, a stray reference), the
reclaim's target. An UNSTARTED thread reads as finished (`is_alive()` False) and still holds the session
(the Thread keeps `_target`, since `run`'s finally never fires for it), so the ref is alive on a cycle;
judging it a reclaim is correct precisely because ONLY the collector can take that cycle (refcounting never
will), which is what a reclaim does. A ref a live ROOT keeps (a never-joined helper thread's `_target`, a
strong reference, not a cycle) reads the same, alive with a finished worker, and is TREATED as a surviving
cycle: the reclaim frees nothing, so it costs exactly ONE full-heap pause, is counted a `survivor` on /perf,
and is dropped (never re-registered), never a pass per tick.

A request that arrives during a reconcile waits that one collection; the idle boundary is the best
moment for it, not a guarantee none arrives. Default on; `ROMP_GC_FREEZE=off` (or `0`/`false`) off.
"""
import gc as _gc_mod
import os
import threading
import time
import weakref

DEFAULT_LOAD_TREES = 8            # record-cache inserts since the last freeze that count as a material load
MIN_LOAD_TREES = 1               # floored here: a threshold of 0 or below would fold in every idle cycle
DEFAULT_BACKSTOP_FOLDINS = 1000  # a reclaim after this many load fold-ins since the last reclaim, bounding a cyclic release
#                                  no ended ref caught; at the measured ~97 fold-ins an hour it fires about once in ten hours
_OFF = ("off", "0", "false")


def enabled_from_env(env=None):
    """The freeze is on unless ROMP_GC_FREEZE names an off value (the measurement switch)."""
    v = (env if env is not None else os.environ).get("ROMP_GC_FREEZE")
    return not (v is not None and v.strip().lower() in _OFF)


def load_trees_from_env(env=None):
    """(load_trees, bad_raw): the ROMP_GC_FREEZE_LOAD_TREES knob, parsed with a fallback to the default on a
    value that is not a positive integer, floored at MIN_LOAD_TREES. `bad_raw` is the offending string when the
    default was substituted (the caller says it once and counts it), else None. Parsed here, never at the kernel's
    import with a bare int(): a bad value must not kill the kernel before it serves (#1735 verifier, the high)."""
    raw = (env if env is not None else os.environ).get("ROMP_GC_FREEZE_LOAD_TREES")
    if raw is None or raw.strip() == "":
        return DEFAULT_LOAD_TREES, None
    try:
        n = int(raw.strip())
    except (TypeError, ValueError):
        return DEFAULT_LOAD_TREES, raw
    return max(MIN_LOAD_TREES, n), None


class GcFreeze:
    """The freeze controller. `gc` and `clock` are injected so a test drives a fake collector or a real one; the
    kernel passes the real `gc`. The `tick`/`_run` path runs on the pusher thread; `note_ended` runs on every
    thread that ends a session (the HTTP handler, housekeeping, a worker), so a small lock guards the ended list."""

    def __init__(self, enabled=True, load_trees=DEFAULT_LOAD_TREES, backstop_foldins=DEFAULT_BACKSTOP_FOLDINS,
                 gc=_gc_mod, clock=time.perf_counter):
        self.enabled = bool(enabled)
        self.load_trees = max(MIN_LOAD_TREES, int(load_trees))
        self.backstop_foldins = max(1, int(backstop_foldins))
        self._gc = gc
        self._clock = clock
        self.frozen = False
        self._ins_mark = 0           # cache inserts at the last freeze
        self._foldins = 0            # load fold-ins since the last reclaim (the backstop counts these)
        self._ended = []             # (weakref(session), weakref(thread)|None) registered at each session-end pop
        self._ended_lock = threading.Lock()   # note_ended runs on other threads than the tick; guard the list
        self.freezes = 0             # initial freeze plus load fold-ins
        self.reclaims = 0            # unfreeze/collect/re-freeze passes (a cyclic ended ref, or the backstop)
        self.survivors = 0           # owed refs still alive after a reclaim's collect: kept by a LIVE ROOT, not a cycle (a wasted pause), counted once and dropped
        self.last_release_sids = []  # first 8 chars of each sid a reclaim was owed for, set under the ended lock, cleared per judgement
        self.last_ms = 0.0           # the last reconcile's collection pause
        self.total_ms = 0.0          # every reconcile's collection pause, summed
        self.last_kind = None        # "initial" | "load" | "release" | "backstop", for /perf

    def note_ended(self, session, thread=None):
        """Register an ended session for the idle tick to judge (a weakref, never a strong ref, so it can die by
        reference counting). `thread` is the session's worker thread; the tick reads whether it still runs. Called
        from whatever thread ended the session, so it takes the ended lock."""
        if not self.enabled:
            return
        try:
            pair = (weakref.ref(session), weakref.ref(thread) if thread is not None else None)
        except TypeError:
            return                   # an object that cannot be weak-referenced: the backstop still covers it
        with self._ended_lock:
            self._ended.append(pair)

    def resolve_ended(self):
        """Judge the registered ended sessions by OBSERVATION and return the list of refs a reclaim is OWED for (empty
        when none, so it reads as a boolean too). A dead ref died by reference counting (acyclic, dropped, no reclaim);
        a live ref whose thread still runs is not garbage yet (kept); a live ref whose thread has finished is a cycle the
        collector must take (owed, and dropped: one reclaim then gone, never re-registered, so a live ROOT that keeps it
        costs exactly one wasted pause). Never reclaims for a dead ref: that is the whole point of measuring instead of
        guessing. Judges IN PLACE under the ended lock, so a registration landing on another thread mid-judgement is never
        dropped. The owed sids' first 8 characters are set on `last_release_sids` under the lock, cleared each judgement, so
        a release names the sessions it was owed for (the 2026-09-22 PR 1999 review, attribution)."""
        keep, owed = [], []
        with self._ended_lock:
            ended = self._ended
            self._ended = keep                       # new registrations land in `keep` while we judge the old list
            for sref, tref in ended:
                if sref() is None:                   # died by refcount: acyclic, gone, nothing to reclaim
                    continue
                t = tref() if tref is not None else None
                if t is not None and t.is_alive():
                    keep.append((sref, tref))        # the worker thread still runs: not garbage yet, judge again next tick
                else:
                    owed.append((sref, tref))        # alive with its thread finished: a surviving cycle the reclaim must take
            self.last_release_sids = [(getattr(sref(), "sid", "") or "")[:8] for sref, _ in owed if sref() is not None]
        return owed                                  # `keep` is already self._ended (set under the lock); no racy rebind here

    def tick(self, inserts):
        """One idle-boundary pass: judge the ended sessions, then run the owed operation. Returns the kind run, or
        None. The reclaim is owed by an observed cyclic ended session or the backstop; the fold-in by a material
        load; the first freeze once anything is loaded."""
        if not self.enabled:
            return None
        owed = self.resolve_ended()
        if not self.frozen:
            return self._run("initial", inserts, []) if inserts > 0 else None
        if owed:
            return self._run("release", inserts, owed)
        if self._foldins >= self.backstop_foldins:
            return self._run("backstop", inserts, [])
        if (inserts - self._ins_mark) >= self.load_trees:
            return self._run("load", inserts, [])
        return None

    def _run(self, kind, inserts, owed):
        """Run the owed collector operation and return the kind actually run. A RELEASE is STAGED (the 2026-09-22 PR 1999
        review): a plain collect with the freeze IN PLACE first (cheap, it takes a cycle allocated since the last freeze),
        then the owed refs are re-read; only when one survived does it unfreeze and walk the frozen heap (the up-to-full
        pause). A release the cheap walk took whole counts as a LOAD pass, so the backstop's bound does not stretch. A
        BACKSTOP is blind (no owed refs) and unfreezes straight away. After the collect, before the re-freeze, an owed ref
        still alive is kept by a LIVE ROOT, not a cycle: a wasted pause, counted as a survivor and dropped (never
        re-registered)."""
        t0 = self._clock()
        reclaimed = False
        if kind == "release":
            self._gc.collect()                       # cheap: the freeze stays in place, so this walks only the unfrozen
            if any(sref() is not None for sref, _ in owed):
                self._gc.unfreeze()                  # a survivor: the released cycle is in the frozen set, lift it and walk
                self._gc.collect()
                reclaimed = True
            # else the cheap collect took the released cycle whole: no full pause, counted as a load pass below
        elif kind == "backstop":
            self._gc.unfreeze()                      # blind periodic reclaim: nothing owed to re-read, walk everything
            self._gc.collect()
            reclaimed = True
        else:
            self._gc.collect()                       # initial / load fold-in: walk only the unfrozen
        self.last_ms = (self._clock() - t0) * 1000.0
        self.total_ms += self.last_ms
        self._gc.freeze()                            # (re)freeze: the survivors leave the collector's walk again
        was_frozen = self.frozen
        self.frozen = True
        self._ins_mark = inserts
        self.survivors += sum(1 for sref, _ in owed if sref() is not None)   # a live root kept it through the reclaim: wasted, counted, dropped
        if reclaimed:
            self.last_kind = kind
            self.reclaims += 1
            self._foldins = 0
        else:
            self.last_kind = "initial" if not was_frozen else "load"   # a cheap-collect release folds in like a load
            self.freezes += 1
            if was_frozen:
                self._foldins += 1                   # a load fold-in; the initial freeze is not one
        return self.last_kind

    def perf(self):
        """The /perf gc block's freeze sub-block: the state and the reconcile trade, so a reconcile collection is
        told apart from an organic one. `active` is whether a freeze is held now (named to not collide with the
        integer `gc.frozen`); `frozenCount` (gc.get_freeze_count) is added by the caller."""
        return {"enabled": self.enabled, "active": self.frozen, "loadTrees": self.load_trees,
                "backstopFoldins": self.backstop_foldins, "freezes": self.freezes, "reclaims": self.reclaims,
                "survivors": self.survivors, "lastReleaseSids": list(self.last_release_sids),
                "endedPending": len(self._ended), "lastReconcileMs": round(self.last_ms, 1),
                "lastReconcileKind": self.last_kind, "totalReconcileMs": round(self.total_ms, 1)}


def pusher_tick(controller, idle, first, stats_fn, on_error):
    """The pusher's idle-boundary call, extracted so it is pinned in-process. Reconcile only on an IDLE, non-FIRST
    cycle. `stats_fn` returns the record cache stats (its `inserts` keys the LOAD fold-in). A raising `stats_fn` or
    tick is handed to `on_error` and never propagates: the pusher must not die on the freeze. Returns the reconcile
    kind run, or None."""
    if not (idle and not first) or not controller.enabled:
        return None
    try:
        inserts = int((stats_fn() or {}).get("inserts") or 0)
        return controller.tick(inserts)
    except Exception as e:
        on_error(e)
    return None
