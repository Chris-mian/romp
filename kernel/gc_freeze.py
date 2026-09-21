#!/usr/bin/env python3
"""Road B for issue #1735: keep the loaded decoded heap out of the cycle collector's walk.

A generation-two (full) collection visits every tracked container in the interpreter; the
request-serving kernel holds millions of them in decoded transcript trees, so a warm full
collection pauses every thread (the pusher included) for seconds. `gc.freeze()` moves the
currently tracked objects into a permanent generation the collector never walks again, so a
later full collection walks only what was allocated since. Measured (plans/gc-full-collection-pause.md):
a warm full collection over 5.6 million loaded objects fell from 2.83 s to 0.1 ms once they were
frozen, and the freeze itself is a pointer move.

The freeze must be RECONCILED, because a whole-heap freeze also keeps frozen garbage alive:
an acyclic object frozen and then dropped by its owner still dies at once by reference counting,
but a frozen reference CYCLE that loses its external owner survives every collection until an
unfreeze lifts it back into the collector's reach. So this controller runs two operations, both
keyed on events and executed at the pusher's IDLE boundary (never a timer), where the pause is
paid with no browser waiting:

  - a LOAD fold-in (cheap): `gc.collect(); gc.freeze()`. The collect walks only the unfrozen
    objects loaded since the last freeze, so it costs milliseconds; the freeze folds their
    survivors into the frozen set. Fired when the record cache's insert counter has grown by a
    material number of trees since the last freeze.
  - a RELEASE reclaim (up to the full 2.8 s, rare): `gc.unfreeze(); gc.collect(); gc.freeze()`.
    The unfreeze brings the frozen set back into the walk so a cycle released since the last
    freeze is collected; the re-freeze restores the state. Fired when the RELEASE count moved: a
    record cache pop (an eviction, a re-read replacement, an OSError pop, a quiescent drop) or a
    `note_release()` from another store (the atom LRU, a goal store, a judge's per-session teardown).

A request that arrives during a reconcile waits that one collection; the idle boundary is the
best moment for it, not a guarantee none arrives. The state and the trade are visible on `/perf`:
the reconcile and reclaim counts and the last reconcile's pause, beside `gc.get_freeze_count()`.

Default on; `ROMP_GC_FREEZE=off` (or `0`/`false`) turns it off for a measurement.
"""
import gc as _gc_mod
import os
import time

DEFAULT_LOAD_TREES = 8            # record-cache inserts since the last freeze that count as a material load
MIN_LOAD_TREES = 1               # floored here: a threshold of 0 or below would make due() fire every idle cycle
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


# A shared release note for stores OTHER than the record cache (the atom LRU, a goal store, a judge's
# per-session teardown): the release point calls note_release(), and the controller reads noted_releases()
# beside the record cache's own `released` counter, so a release reclaim runs after any of them. Module level
# on the ONE gcf the kernel loads (the stores call it through an injected reference, never their own load), so
# the count is shared across the process.
_NOTED_RELEASES = [0]


def note_release():
    _NOTED_RELEASES[0] += 1


def noted_releases():
    return _NOTED_RELEASES[0]


class GcFreeze:
    """The freeze controller. `gc` and `clock` are injected so a test drives a fake collector or a real one; the
    kernel passes the real `gc`. Never takes a lock: the caller runs it on the pusher thread at the idle boundary."""

    def __init__(self, enabled=True, load_trees=DEFAULT_LOAD_TREES, gc=_gc_mod, clock=time.perf_counter):
        self.enabled = bool(enabled)
        self.load_trees = max(MIN_LOAD_TREES, int(load_trees))
        self._gc = gc
        self._clock = clock
        self.frozen = False
        self._ins_mark = 0           # cache inserts at the last freeze
        self._rel_mark = 0           # the release count (cache pops + noted releases) at the last freeze
        self.freezes = 0             # initial freeze plus load fold-ins
        self.reclaims = 0            # release-triggered unfreeze/collect/re-freeze passes
        self.last_ms = 0.0           # the last reconcile's collection pause
        self.total_ms = 0.0          # every reconcile's collection pause, summed
        self.last_kind = None        # "initial" | "load" | "release", for /perf

    def due(self, inserts, releases):
        """Whether a reconcile is owed: the first freeze once anything is loaded, a material load since the last
        freeze, or any release since it. `inserts` is the record cache's monotone insert counter; `releases` is
        the combined release count (the cache's `released` counter plus noted_releases())."""
        if not self.enabled:
            return False
        if not self.frozen:
            return inserts > 0                       # nothing frozen yet: freeze once something is loaded
        return (inserts - self._ins_mark) >= self.load_trees or releases != self._rel_mark

    def reconcile(self, inserts, releases):
        """Run the owed operation. A release since the last freeze needs the unfreeze reclaim (up to the full
        pause); otherwise a cheap load fold-in. Returns the kind run, or None."""
        if not self.enabled:
            return None
        need_reclaim = self.frozen and releases != self._rel_mark
        kind = "release" if need_reclaim else ("load" if self.frozen else "initial")
        t0 = self._clock()
        if need_reclaim:
            self._gc.unfreeze()                      # lift the frozen set back into the walk so released cycles collect
        self._gc.collect()                           # a fold-in walks only the unfrozen; a reclaim walks everything
        self.last_ms = (self._clock() - t0) * 1000.0
        self.total_ms += self.last_ms
        self._gc.freeze()                            # (re)freeze: the survivors leave the collector's walk again
        self.frozen = True
        self._ins_mark = inserts
        self._rel_mark = releases
        self.last_kind = kind
        if need_reclaim:
            self.reclaims += 1
        else:
            self.freezes += 1
        return kind

    def perf(self):
        """The /perf gc block's freeze sub-block: the state and the reconcile trade, so a reconcile collection is
        told apart from an organic one. `frozenCount` (gc.get_freeze_count) is added by the caller; `active` is
        whether the controller holds a freeze now (named to not collide with the integer `gc.frozen`)."""
        return {"enabled": self.enabled, "active": self.frozen, "loadTrees": self.load_trees,
                "freezes": self.freezes, "reclaims": self.reclaims,
                "lastReconcileMs": round(self.last_ms, 1), "lastReconcileKind": self.last_kind,
                "totalReconcileMs": round(self.total_ms, 1)}


def pusher_tick(controller, idle, first, stats_fn, on_error):
    """The pusher's idle-boundary call, extracted so it is pinned in-process (the #1735 verifier's medium: the
    kernel's call site alone had no teeth). Reconcile only on an IDLE, non-FIRST cycle. `stats_fn` returns the
    record cache stats; the release count is its `released` plus the shared noted_releases(). A raising `stats_fn`
    or reconcile is handed to `on_error` and never propagates: the pusher must not die on the freeze. Returns the
    reconcile kind run, or None."""
    if not (idle and not first) or not controller.enabled:
        return None
    try:
        st = stats_fn()
        inserts = int(st.get("inserts") or 0)
        releases = int(st.get("released") or 0) + noted_releases()
        if controller.due(inserts, releases):
            return controller.reconcile(inserts, releases)
    except Exception as e:
        on_error(e)
    return None
