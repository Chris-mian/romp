#!/usr/bin/env python3
"""romp-wordmark — render the "Romp" logotype (the README hero).

The wordmark sets "Romp" in the Anta typeface and drops the romp swirl in as
the lowercase "o". The swirl geometry is the SAME mark make_icon.py draws — we
import `variant_swirl_glyph()` so there is one source of truth for the spiral —
then forge a STRONG variant of it (faint halos + soft glows stripped, the three
arms thickened, nodes + center core punched up) so it stays bold and legible at
letter size rather than dissolving into the word.

Layout is done in HTML/CSS and rasterized with headless Chrome, because getting
real font metrics (x-height, side bearings) and sub-pixel placement right is
exactly what a browser does for free. The swirl's vertical placement was tuned
empirically: its content centroid sits low under `vertical-align:middle`, so we
nudge it up by DY_EM until the measured swirl centroid lands on the lowercase
o-slot center (baseline + x-height/2). See the comment on DY_EM.

Deps: Google Chrome / Chromium (set $CHROME to override the binary), and
optionally Pillow (used only to auto-trim the banner to its content).

Run:  python make_wordmark.py
Outputs romp-wordmark.png into this directory.
"""
import base64
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import make_icon  # sibling module — canonical swirl geometry + palette

HERE = Path(__file__).resolve().parent
FONT = HERE / "Anta-Regular.ttf"          # vendored (OFL, see OFL-Anta.txt)
OUT = HERE / "romp-wordmark.png"

# --- design constants -------------------------------------------------------
FONT_PX = 300
SWIRL_EM = 0.65            # the swirl, sized to read as a true lowercase "o"
# vertical-align:middle aligns the element's box center to the o-slot center,
# but the swirl's *content* centroid sits ~0.14em below its box center, so the
# mark lands low. Empirically -0.20em puts the measured swirl centroid exactly
# on the o-slot center (verified offset 0px); re-tune if SWIRL_EM/CROP change.
DY_EM = -0.20
TEXT = "#e8eef5"          # off-white — matches the swirl's own core/ring color
CROP = "102 102 820 820"  # tight box around the glyph, centered on (512,512);
                          # roomy enough that the top node isn't clipped
CANVAS_W, CANVAS_H = 1400, 460


def strong_swirl() -> str:
    """make_icon's swirl glyph, restyled bold/crisp for use at letter size."""
    s = make_icon.variant_swirl_glyph()
    subs = [
        (r'<path[^>]*?opacity="0\.42"[^>]*?/>', '', re.S),          # drop faint halo trails
        (r'<circle[^>]*?fill="url\(#glow-[^)]*\)"[^>]*?/>', '', re.S),  # drop soft glows
    ]
    for pat, repl, flags in subs:
        s = re.sub(pat, repl, s, flags=flags)
    s = s.replace('stroke-width="40"', 'stroke-width="70"')         # thicken the 3 arms
    s = s.replace('r="35"', 'r="46"').replace('stroke-width="6"', 'stroke-width="10"')  # punch up nodes
    core_before = '<circle cx="512.0" cy="512.0" r="11" fill="#e8eef5" fill-opacity="0.45"/>'
    s = s.replace(core_before, '<circle cx="512.0" cy="512.0" r="30" fill="#e8eef5"/>')  # bright solid core
    s = re.sub(r'width="\d+"\s+height="\d+"', '', s, count=1)       # CSS drives the size
    s = s.replace('viewBox="0 0 1024 1024"', f'viewBox="{CROP}"')
    # fail loudly if make_icon's output format drifts out from under the transform
    for leftover in ('stroke-width="40"', 'opacity="0.42"', 'url(#glow-'):
        assert leftover not in s, f"swirl format changed; update make_wordmark transform ({leftover})"
    assert 'r="30" fill="#e8eef5"' in s, "swirl center-dot string changed; update transform"
    return s


def build_html() -> str:
    font_b64 = base64.b64encode(FONT.read_bytes()).decode()
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
  @font-face {{ font-family:'Anta'; src:url(data:font/ttf;base64,{font_b64}) format('truetype'); }}
  html,body {{ margin:0; padding:0; }}
  body {{ width:{CANVAS_W}px; height:{CANVAS_H}px; display:flex;
    align-items:center; justify-content:center;
    background: radial-gradient(120% 120% at 50% 40%, #1b212b 0%, #0e1116 100%);
    overflow:hidden; }}
  .mark {{ font-family:'Anta',sans-serif; font-size:{FONT_PX}px; line-height:1;
    color:{TEXT}; white-space:nowrap; letter-spacing:0.01em; }}
  .mark .sw {{ height:{SWIRL_EM}em; width:{SWIRL_EM}em; display:inline-block;
    vertical-align:middle; position:relative; top:{DY_EM}em; margin:0 -0.05em; }}
</style></head><body>
  <div class="mark"><span>R</span><span class="sw">{strong_swirl()}</span><span>mp</span></div>
</body></html>"""


def find_chrome() -> str:
    env = os.environ.get("CHROME")
    if env and Path(env).exists():
        return env
    cands = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        shutil.which("google-chrome"), shutil.which("chromium"),
        shutil.which("chromium-browser"), shutil.which("chrome"),
    ]
    for c in cands:
        if c and Path(c).exists():
            return c
    sys.exit("Chrome/Chromium not found — install it or set $CHROME to the binary path")


def autotrim(path: Path) -> None:
    """Crop the dark banner down to its content + even padding (no-op if no Pillow)."""
    try:
        from PIL import Image
    except ImportError:
        print("  (Pillow not installed — skipping auto-trim)")
        return
    im = Image.open(path).convert("RGB")
    mask = im.convert("L").point(lambda v: 255 if v > 70 else 0)  # content vs dark bg
    bbox = mask.getbbox()
    if not bbox:
        return
    pad = int(0.18 * (bbox[3] - bbox[1]))
    x0, y0, x1, y1 = bbox
    im.crop((max(0, x0 - pad), max(0, y0 - pad),
             min(im.width, x1 + pad), min(im.height, y1 + pad))).save(path)


def main() -> None:
    chrome = find_chrome()
    with tempfile.TemporaryDirectory() as td:
        html = Path(td) / "wordmark.html"
        html.write_text(build_html())
        subprocess.run(
            [chrome, "--headless", "--disable-gpu", "--hide-scrollbars",
             "--force-device-scale-factor=2", f"--window-size={CANVAS_W},{CANVAS_H}",
             f"--screenshot={OUT}", html.as_uri()],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    autotrim(OUT)
    print("wrote", OUT.relative_to(HERE.parent.parent))


if __name__ == "__main__":
    main()
