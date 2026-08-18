#!/usr/bin/env python3
"""Give-up cards re-arm on RECOVERY EVENTS (the user 2026-08-18): most give-ups come from call-level
failures (a 529 overload storm, an auth blip) that never engage the usage-limit retry-pause — so the one
wired recovery edge never fired and the "distill failed" chip outlived the outage until a manual Try
again. Under test here:
  - the judge-call health latch: a "call" failure latches degraded; the first SERVED reply after it is
    the degraded→serving edge, consumable exactly once (consume_judge_recovery);
  - rearm_failed_summaries(auto=True), the edge's consumer: one automatic retry per give-up era
    (nd["autoRearmed"]), while discrete events (startup, retry-pause clear, Try again) open a fresh era;
  - a give-up that KEPT an older real summary (a re-completion never blanks prior text) re-arms by
    clearing its event stamp, since the "" flip cannot apply;
  - "stall-failed" joins the scan/re-arm family (the staller's give-ups were invisible to both).
SYNTHETIC fixtures only (placeholder UUIDs, invented text)."""
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
jd = SourceFileLoader("romp_judge_rearm", os.path.join(BIN, "romp-judge")).load_module()

SID = "11111111-2222-3333-4444-555555555555"
NID = SID + ":g1"
T0 = 1781100000


def _warn(kind):
    return [{"kind": kind, "t": T0, "msg": "synthetic msg", "detail": "synthetic detail"}]


def _seed(**nd_extra):
    store = jd.load_goals(SID)
    nd = {"text": "ship the api", "parentId": None, "mt": T0}
    nd.update(nd_extra)
    store["nodes"][NID] = jd.GuardedNode(nd)
    jd.save_goals(SID, store)


def _node():
    return jd.load_goals(SID)["nodes"][NID]


def _drain_edge():
    while jd.consume_judge_recovery():
        pass


class JudgeCallHealthEdge(unittest.TestCase):
    def setUp(self):
        jd.STATE.mkdir(parents=True, exist_ok=True)
        _drain_edge()
        with jd._health_lock:
            jd._CALL_HEALTH["degraded"] = False

    def test_first_served_reply_after_a_call_failure_is_one_edge(self):
        jd._log_judge_error("captioner", None, "call", note="error envelope: 'Overloaded'")
        self.assertFalse(jd.consume_judge_recovery(), "a failure alone is not a recovery")
        jd._mark_call_served()
        self.assertTrue(jd.consume_judge_recovery(), "first served reply after a failure = the edge")
        self.assertFalse(jd.consume_judge_recovery(), "the edge is consumed exactly once")

    def test_serving_while_healthy_is_not_an_edge(self):
        jd._mark_call_served()
        self.assertFalse(jd.consume_judge_recovery(), "no prior failure → nothing recovered")

    def test_non_call_errors_do_not_latch_degraded(self):
        # a parse reject / cite-miss is the MODEL's verdict on one prompt, not API sickness — the next
        # served call must not read as a recovery and re-arm every give-up card in the deployment
        jd._log_judge_error("planner", None, "parse", note="reply rejected")
        jd._log_judge_error("distiller", None, "cite-miss", note="no SOURCE line")
        jd._mark_call_served()
        self.assertFalse(jd.consume_judge_recovery(), "only call-level failures arm the edge")


class RearmRecoveryEvents(unittest.TestCase):
    def tearDown(self):
        for d in (jd.GOALDIR, jd._overrides_dir()):
            for f in d.glob("*"):
                f.unlink()

    def test_auto_rearm_retries_a_give_up_era_exactly_once(self):
        _seed(summary="", distillFails=0, warns=_warn("summary-failed"))
        self.assertEqual(jd.rearm_failed_summaries(T0 + 100, auto=True), 1)
        nd = _node()
        self.assertIsNone(nd.get("summary"), '"" (gave up) → None (owed): the next pass retries')
        self.assertTrue(nd.get("autoRearmed"), "the era's one automatic retry is marked spent")
        # the retry re-gives-up (sentinel + warn re-stamped; the mark survives the give-up write)
        st = jd.load_goals(SID)
        st["nodes"][NID]["summary"] = ""
        jd.save_goals(SID, st)
        self.assertEqual(jd.rearm_failed_summaries(T0 + 200, auto=True), 0,
                         "a healthy neighbor's every edge must not burn DISTILL_FAIL_CAP calls on a "
                         "card whose own call is broken — one automatic retry per era")

    def test_a_discrete_event_rearms_and_opens_a_fresh_era(self):
        _seed(summary="", warns=_warn("summary-failed"), autoRearmed=True)
        self.assertEqual(jd.rearm_failed_summaries(T0 + 300), 1,
                         "startup / retry-pause clear re-arm regardless of the era mark")
        nd = _node()
        self.assertIsNone(nd.get("summary"))
        self.assertNotIn("autoRearmed", nd, "a discrete event opens a fresh era for the health edge")

    def test_rearm_reenters_a_giveup_that_kept_an_older_summary(self):
        # a re-completion's give-up never blanks prior text — so there is no "" to flip; the stamp
        # clears instead and the gate re-enters with the prior summary intact
        _seed(summary="Old takeaway.", distilledMt=T0, warns=_warn("summary-failed"))
        self.assertEqual(jd.rearm_failed_summaries(T0 + 100), 1)
        nd = _node()
        self.assertEqual(nd.get("summary"), "Old takeaway.", "the prior text is never clobbered")
        self.assertIsNone(nd.get("distilledMt"), "the cleared stamp is what re-enters the distiller")

    def test_an_already_owed_line_is_not_recounted(self):
        _seed(summary=None, warns=_warn("summary-failed"))
        self.assertEqual(jd.rearm_failed_summaries(T0 + 100), 0,
                         "None is already owed — nothing to flip, nothing to count")

    def test_stall_failed_joins_the_scan_and_the_rearm(self):
        _seed(stallSummary="", warns=_warn("stall-failed"))
        scan = jd.judge_failure_scan()
        self.assertEqual(scan["count"], 1, "a given-up stall note counts toward the banner")
        self.assertEqual(jd.rearm_failed_summaries(T0 + 100), 1)
        self.assertIsNone(_node().get("stallSummary"), "the stall note re-arms like the other lines")


class KernelRearmWiring(unittest.TestCase):
    """Source pins on the kernel's two recovery-event call sites (the RedistillOpWiring precedent —
    the wiring is a few lines inside 400-line functions no unit test can enter cheaply)."""

    @classmethod
    def setUpClass(cls):
        cls.km = SourceFileLoader("romp_kernel_rearm", os.path.join(BIN, "romp-kernel")).load_module()

    def test_startup_rearms_before_the_server_loop(self):
        import inspect
        src = inspect.getsource(self.km.main)
        self.assertIn("rearm_failed_summaries", src, "a restart is a discrete recovery event — wired in main()")
        self.assertLess(src.index("rearm_failed_summaries"), src.index("serve_forever"),
                        "the boot sweep re-arms before the kernel starts serving")

    def test_producer_consumes_the_health_edge_after_the_tier_join(self):
        import inspect
        src = inspect.getsource(self.km._producer)
        i_join = src.index("t.join()")
        i_edge = src.index("consume_judge_recovery")
        self.assertGreater(i_edge, i_join,
                           "the edge is consumed AFTER the join — the single-writer window, so the "
                           "re-arm's store writes can't race the judge worker threads")
        seg = src[i_edge:]
        self.assertIn("rearm_failed_summaries", seg[:400], "the consumed edge drives the auto re-arm")
        self.assertIn("auto=True", seg[:400], "the health edge is the era-bounded auto path")


if __name__ == "__main__":
    unittest.main()
