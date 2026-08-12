"""The recency colormaps live in TWO copies — bin/romp_colormap.py (kernel-coloured feed) and the webview's
render.ts COLORMAPS (ledger). They MUST stay identical, else the feed and ledger disagree. cividis was
mis-sampled (over-saturated middle, ~33/255 off matplotlib) until 2026-06-17. These guard both."""
import os, re, importlib.util, unittest
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
spec = importlib.util.spec_from_file_location("romp_colormap", os.path.join(ROOT, "bin", "romp_colormap.py"))
cm = importlib.util.module_from_spec(spec); spec.loader.exec_module(cm)


def _webview_colormaps():
    src = open(os.path.join(ROOT, "ui", "webview", "render.ts")).read()
    block = re.search(r"const COLORMAPS[^{]*\{(.*?)\n\};", src, re.S).group(1)
    out = {}
    for name, arr in re.findall(r"(\w+):\s*(\[\[.*?\]\]),", block):
        nums = [int(x) for x in re.findall(r"-?\d+", arr)]
        out[name] = [tuple(nums[i:i + 3]) for i in range(0, len(nums), 3)]
    return out


class Colormaps(unittest.TestCase):
    def test_kernel_and_webview_colormaps_are_identical(self):
        web = _webview_colormaps()
        self.assertEqual(set(web), set(cm.COLORMAPS), "the two colormap copies have different maps")
        for name, stops in cm.COLORMAPS.items():
            self.assertEqual(web[name], [tuple(s) for s in stops], f"'{name}' drifted between kernel and webview")

    def test_cividis_is_real_cividis(self):
        c = cm.COLORMAPS["cividis"]
        self.assertEqual(c[0], (0, 34, 78))            # dark blue end
        self.assertEqual(c[-1], (254, 232, 56))         # bright yellow end
        self.assertEqual(c[3], (108, 110, 114))         # MUTED gray middle (was an over-saturated (87,85,109))

    def test_all_maps_match_matplotlib_when_available(self):
        try:
            import numpy as np, matplotlib
        except Exception:
            self.skipTest("matplotlib not installed")
        for name, stops in cm.COLORMAPS.items():
            if name in ("hawaii", "aurora"):
                continue                                # hawaii=crameri, aurora=romp-generated — neither in matplotlib
            real = [tuple(round(c * 255) for c in matplotlib.colormaps[name](x)[:3])
                    for x in np.linspace(0, 1, len(stops))]
            err = max(max(abs(a - b) for a, b in zip(s, r)) for s, r in zip(stops, real))
            self.assertLessEqual(err, 8, f"'{name}' is {err}/255 off matplotlib")


if __name__ == "__main__":
    unittest.main()
