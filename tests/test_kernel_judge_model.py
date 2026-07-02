"""Judge model chooser (the user 2026-07-02): the triage judges default to Sonnet 5 now (bumped from Sonnet
4.6), and the model is selectable from the gear's Judges section. The pick is SERVER-SIDE (the judge runs
kernel-side): the dropdown posts setJudgeModel → _set_judge_model writes STATE/judge-model, and the judge reads
it via jd._triage_model() on its next pass (no restart). Index tier stays on Haiku, not exposed.
"""
import inspect
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()   # isolate STATE so the test never touches the real judge-model
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
os.environ.setdefault("ROMP_SERVE_TOKEN", "testtok")
jd = SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()
km = SourceFileLoader("romp_kernel", os.path.join(BIN, "romp-kernel")).load_module()


class JudgeModel(unittest.TestCase):
    def setUp(self):
        # start each test from a clean override (no STATE/judge-model file)
        try:
            (jd.STATE / "judge-model").unlink()
        except OSError:
            pass
        jd._judge_model_cache["mt"] = None

    def test_triage_default_is_sonnet_5(self):
        self.assertEqual(jd.TRIAGE_MODEL, "claude-sonnet-5", "the triage judges default to Sonnet 5 now")
        self.assertEqual(jd._triage_model(), "claude-sonnet-5", "no override → the default")

    def test_index_tier_stays_on_haiku(self):
        self.assertEqual(jd.INDEX_MODEL, "claude-haiku-4-5-20251001", "captioner+archiver stay on Haiku (cost lever)")

    def test_judge_models_menu_leads_with_the_default_and_lists_known_ids(self):
        ids = [m[0] for m in jd.JUDGE_MODELS]
        self.assertEqual(ids[0], jd.TRIAGE_MODEL, "the default is the first menu option")
        self.assertIn("claude-sonnet-5", ids)
        self.assertIn("claude-opus-4-8", ids)
        self.assertIn("claude-haiku-4-5-20251001", ids)

    def test_triage_model_honors_a_valid_override(self):
        (jd.STATE / "judge-model").write_text("claude-opus-4-8")
        jd._judge_model_cache["mt"] = None   # force a re-read (same-second write in the harness)
        self.assertEqual(jd._triage_model(), "claude-opus-4-8")

    def test_triage_model_ignores_an_unknown_override(self):
        (jd.STATE / "judge-model").write_text("gpt-nonsense")
        jd._judge_model_cache["mt"] = None
        self.assertEqual(jd._triage_model(), jd.TRIAGE_MODEL, "an unknown id falls back to the default")

    def test_every_triage_judge_reads_the_live_model_not_the_constant(self):
        # the judgment judges must call _triage_model() so a settings change reaches them; only the offline
        # CLASSIFY_ARMS A/B baseline may reference the raw constant.
        src = inspect.getsource(jd)
        # no live _judge_run passes the bare TRIAGE_MODEL constant (the _triage_model() call is used instead)
        self.assertNotIn("_judge_run(TRIAGE_MODEL,", src, "triage judges must use _triage_model(), not the constant")
        self.assertIn("_judge_run(_triage_model(), GROUP_SYS", src)
        self.assertIn("_judge_run(_triage_model(), CLOSER_SYS", src)
        self.assertIn("_judge_run(_triage_model(), COURIER_SYS", src)
        self.assertIn("model or _triage_model(), PLAN_SYS", src)

    def test_kernel_set_judge_model_persists_valid_only(self):
        km._set_judge_model("claude-opus-4-8")
        self.assertEqual((jd.STATE / "judge-model").read_text().strip(), "claude-opus-4-8")
        km._set_judge_model("bogus")   # ignored
        self.assertEqual((jd.STATE / "judge-model").read_text().strip(), "claude-opus-4-8")

    def test_version_reports_current_model_and_the_menu(self):
        # setUp already cleared any override, so the judge is on its default
        v = km._version_info()
        self.assertEqual(v["judgeModel"], "claude-sonnet-5")
        self.assertEqual([m[0] for m in v["judgeModels"]], [m[0] for m in jd.JUDGE_MODELS])

    def test_ws_handler_and_gear_dropdown_exist(self):
        ksrc = inspect.getsource(km)
        self.assertIn('msg.get("type") == "setJudgeModel" and msg.get("model")', ksrc)
        self.assertIn('_set_judge_model(str(msg["model"]))', ksrc)
        html = km._gear_html()
        self.assertIn("id=rs-judgemodel", html, "the gear has the Judge model dropdown")
        self.assertIn('<option value="claude-sonnet-5"', html, "options come from JUDGE_MODELS")


if __name__ == "__main__":
    unittest.main()
