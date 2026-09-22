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
  - a RELEASE reclaim (up to the full pause): `gc.unfreeze(); gc.collect(); gc.freeze()`. The unfreeze
    brings the frozen set back into the walk so a released reference CYCLE is collected. Measured
    (plans/gc-full-collection-pause.md): ZERO an hour under warm re-reads that release nothing cyclic,
    and one per genuine cyclic release (a session end), never the 2.8 s pause on a schedule.

The reclaim is keyed ONLY on the release of a CYCLIC owner, never on a record-cache pop. This is the
2026-09-21 review's correction: a record-cache pop releases decoded json that is ACYCLIC and dies by
reference counting, frozen or not, so an unfreeze reclaim there collects nothing (executed: pops and
cache clears under a freeze all died by refcount, the unfreeze walk reclaimed zero); the parsed
session trees measured acyclic too. Keying the reclaim on pops would pay the full 2.8 s pause at every
idle boundary a kernel re-reads an appended transcript, the very pause we set out to remove. So the
release note (`note_release`) is raised only where a cyclic runtime owner is dropped: the backend's
session at session end (a session and its backend hold each other), and any other cyclic per-session
owner a caller wires. A BOUNDED BACKSTOP covers what no note reaches: after `backstop_foldins` load
fold-ins since the last reclaim, a reclaim runs anyway, so a frozen cycle released on an unnoted path
lives at most that many fold-ins, never the process lifetime. The record cache's `released` counter
stays a /perf statistic; it is not a trigger.

A request that arrives during a reconcile waits that one collection; the idle boundary is the best
moment for it, not a guarantee none arrives. Default on; `ROMP_GC_FREEZE=off` (or `0`/`false`) off.
"""
import gc as _gc_mod
import os
import time

DEFAULT_LOAD_TREES = 8            # record-cache inserts since the last freeze that count as a material load
MIN_LOAD_TREES = 1               # floored here: a threshold of 0 or below would make due() fire every idle cycle
DEFAULT_BACKSTOP_FOLDINS = 1000  # a reclaim after this many load fold-ins since the last reclaim, bounding an unnoted cyclic
#                                  release; at the measured ~97 fold-ins an hour it fires about once in ten hours, near-zero
#                                  beside the ~70 organic full collections an hour it replaces
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


# The shared release note: a CYCLIC owner's release point calls note_release(), and the controller reads
# noted_releases() at the idle boundary. Module level on the ONE gcf the kernel loads (the stores call it through a
# reference the kernel injects, never their own load), so the count is shared across the process.
_NOTED_RELEASES = [0]


def note_release():
    _NOTED_RELEASES[0] += 1


def noted_releases():
    return _NOTED_RELEASES[0]


class GcFreeze:
    """The freeze controller. `gc` and `clock` are injected so a test drives a fake collector or a real one; the
    kernel passes the real `gc`. Never takes a lock: the caller runs it on the pusher thread at the idle boundary."""

    def __init__(self, enabled=True, load_trees=DEFAULT_LOAD_TREES, backstop_foldins=DEFAULT_BACKSTOP_FOLDINS,
                 gc=_gc_mod, clock=time.perf_counter):
        self.enabled = bool(enabled)
        self.load_trees = max(MIN_LOAD_TREES, int(load_trees))
        self.backstop_foldins = max(1, int(backstop_foldins))
        self._gc = gc
        self._clock = clock
        self.frozen = False
        self._ins_mark = 0           # cache inserts at the last freeze
        self._note_mark = 0          # noted cyclic releases at the last reclaim
        self._foldins = 0            # load fold-ins since the last reclaim (the backstop counts these)
        self.freezes = 0             # initial freeze plus load fold-ins
        self.reclaims = 0            # unfreeze/collect/re-freeze passes (a cyclic note, or the backstop)
        self.last_ms = 0.0           # the last reconcile's collection pause
        self.total_ms = 0.0          # every reconcile's collection pause, summed
        self.last_kind = None        # "initial" | "load" | "release" | "backstop", for /perf

    def _kinds(self, notes):
        notes_moved = self.frozen and notes != self._note_mark
        backstop = self.frozen and self._foldins >= self.backstop_foldins
        return notes_moved, backstop

    def due(self, inserts, notes):
        """Whether a reconcile is owed: the first freeze once anything is loaded, a material load since the last
        freeze, a cyclic release noted since the last reclaim, or the backstop. `inserts` is the record cache's
        insert counter; `notes` is noted_releases()."""
        if not self.enabled:
            return False
        if not self.frozen:
            return inserts > 0
        notes_moved, backstop = self._kinds(notes)
        return notes_moved or backstop or (inserts - self._ins_mark) >= self.load_trees

    def reconcile(self, inserts, notes):
        """Run the owed operation. A cyclic release or the backstop needs the unfreeze reclaim (up to the full
        pause); otherwise a cheap load fold-in. Returns the kind run, or None."""
        if not self.enabled:
            return None
        notes_moved, backstop = self._kinds(notes)
        need_reclaim = notes_moved or backstop
        kind = "release" if notes_moved else ("backstop" if backstop else ("load" if self.frozen else "initial"))
        t0 = self._clock()
        if need_reclaim:
            self._gc.unfreeze()                      # lift the frozen set back into the walk so a released cycle collects
        self._gc.collect()                           # a fold-in walks only the unfrozen; a reclaim walks everything
        self.last_ms = (self._clock() - t0) * 1000.0
        self.total_ms += self.last_ms
        self._gc.freeze()                            # (re)freeze: the survivors leave the collector's walk again
        was_frozen = self.frozen
        self.frozen = True
        self._ins_mark = inserts
        self.last_kind = kind
        if need_reclaim:
            self.reclaims += 1
            self._foldins = 0
            self._note_mark = notes
        else:
            self.freezes += 1
            if was_frozen:
                self._foldins += 1                   # a load fold-in; the initial freeze is not one
            else:
                self._note_mark = notes              # the initial freeze syncs the note mark too: a release noted BEFORE the
                #                                      first freeze is already taken by the initial collect, so it must not
                #                                      drive a wasted full reclaim at the next tick (2026-09-22 review)
        return kind

    def perf(self):
        """The /perf gc block's freeze sub-block: the state and the reconcile trade, so a reconcile collection is
        told apart from an organic one. `active` is whether a freeze is held now (named to not collide with the
        integer `gc.frozen`); `frozenCount` (gc.get_freeze_count) is added by the caller."""
        return {"enabled": self.enabled, "active": self.frozen, "loadTrees": self.load_trees,
                "backstopFoldins": self.backstop_foldins, "freezes": self.freezes, "reclaims": self.reclaims,
                "lastReconcileMs": round(self.last_ms, 1), "lastReconcileKind": self.last_kind,
                "totalReconcileMs": round(self.total_ms, 1)}


def pusher_tick(controller, idle, first, stats_fn, on_error):
    """The pusher's idle-boundary call, extracted so it is pinned in-process. Reconcile only on an IDLE, non-FIRST
    cycle. `stats_fn` returns the record cache stats (its `inserts` keys the LOAD fold-in); the RELEASE reclaim is
    keyed on the shared noted_releases() (a cyclic owner's release) and the controller's own backstop, never on a
    cache pop. A raising `stats_fn` or reconcile is handed to `on_error` and never propagates: the pusher must not
    die on the freeze. Returns the reconcile kind run, or None."""
    if not (idle and not first) or not controller.enabled:
        return None
    try:
        inserts = int((stats_fn() or {}).get("inserts") or 0)
        notes = noted_releases()
        if controller.due(inserts, notes):
            return controller.reconcile(inserts, notes)
    except Exception as e:
        on_error(e)
    return None
