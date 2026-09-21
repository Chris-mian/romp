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
    freeze is collected; the re-freeze restores the state. Fired when the cache's eviction or
    drop counters moved (a session's decoded tree released).

A request that arrives during a reconcile waits that one collection; the idle boundary is the
best moment for it, not a guarantee none arrives. The state and the trade are visible on `/perf`:
the reconcile and reclaim counts and the last reconcile's pause, beside `gc.get_freeze_count()`.

Default on; `ROMP_GC_FREEZE=off` (or `0`/`false`) turns it off for a measurement.
"""
import gc as _gc_mod
import os
import time

DEFAULT_LOAD_TREES = 8            # record-cache inserts since the last freeze that count as a material load
_OFF = ("off", "0", "false", "no")


def enabled_from_env(env=None):
    """The freeze is on unless ROMP_GC_FREEZE names an off value (the measurement switch)."""
    v = (env if env is not None else os.environ).get("ROMP_GC_FREEZE")
    return not (v is not None and v.strip().lower() in _OFF)


class GcFreeze:
    """The freeze controller. `gc` and `clock` are injected so a test drives a fake collector or
    a real one; the kernel passes the real `gc`. Never takes a lock: the caller runs it on the
    pusher thread at the idle boundary."""

    def __init__(self, enabled=True, load_trees=DEFAULT_LOAD_TREES, gc=_gc_mod, clock=time.perf_counter):
        self.enabled = bool(enabled)
        self.load_trees = int(load_trees)
        self._gc = gc
        self._clock = clock
        self.frozen = False
        self._ins_mark = 0           # cache inserts at the last freeze
        self._rel_mark = 0           # cache evictions + drops at the last freeze
        self.freezes = 0             # initial freeze plus load fold-ins
        self.reclaims = 0            # release-triggered unfreeze/collect/re-freeze passes
        self.last_ms = 0.0           # the last reconcile's collection pause
        self.total_ms = 0.0          # every reconcile's collection pause, summed
        self.last_kind = None        # "initial" | "load" | "release", for /perf

    def due(self, inserts, releases):
        """Whether a reconcile is owed: the first freeze once anything is loaded, a material load
        since the last freeze, or any release since it. `inserts` and `releases` are the record
        cache's monotone counters (inserts; evictions + drops)."""
        if not self.enabled:
            return False
        if not self.frozen:
            return inserts > 0                       # nothing frozen yet: freeze once something is loaded
        return (inserts - self._ins_mark) >= self.load_trees or releases != self._rel_mark

    def reconcile(self, inserts, releases):
        """Run the owed operation. A release since the last freeze needs the unfreeze reclaim
        (up to the full pause); otherwise a cheap load fold-in. Returns the kind run, or None."""
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
        """The /perf gc block's freeze sub-block: the state and the reconcile trade, so a
        reconcile collection is told apart from an organic one. `frozenCount` is added by the
        caller from gc.get_freeze_count()."""
        return {"enabled": self.enabled, "frozen": self.frozen, "loadTrees": self.load_trees,
                "freezes": self.freezes, "reclaims": self.reclaims,
                "lastReconcileMs": round(self.last_ms, 1), "lastReconcileKind": self.last_kind,
                "totalReconcileMs": round(self.total_ms, 1)}
