#!/usr/bin/env python3
"""romp-wordmark — render the "Romp" logotype (the README hero).

The wordmark sets "Romp" in the Anta typeface and drops the romp swirl in as
the lowercase "o". The swirl geometry is the SAME mark make_icon.py draws — we
import `variant_swirl_glyph()` so there is one source of truth for the spiral —
then forge a STRONG variant of it (faint halos + soft glows stripped, the three
arms thickened, nodes punched up, center left open) so it stays bold and legible
at letter size rather than dissolving into the word.

The three letters R/m/p each wear one of the swirl's three arm colors
(make_icon.COLORS, in order: blue/green/teal) so the word carries the mark's
palette instead of being flat white.

Layout is done in HTML/CSS and rasterized with headless Chrome, because getting
real font metrics (x-height, side bearings) and sub-pixel placement right is
exactly what a browser does for free. The swirl's vertical placement was tuned
empirically: its content centroid sits low under `vertical-align:middle`, so we
nudge it up by DY_EM until the measured swirl centroid lands on the lowercase
o-slot center (baseline + x-height/2). See the comment on DY_EM.

Deps: Google Chrome / Chromium (set $CHROME to override the binary), and
optionally Pillow (used only to auto-trim the banner to its content).

Run:  python make_wordmark.py
Outputs two PNGs:
  - romp-wordmark.png (here) — the dark-banner README hero.
  - ../../chat-view/media/romp-wordmark.png — a TRANSPARENT-background copy for
    the dashboard's inbox-zero empty state (served at /media; the pane is dark so
    it floats on the pane's own background instead of carrying a banner of its own).
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
OUT = HERE / "romp-wordmark.png"          # dark-banner README hero
# transparent copy served by the kernel at /media for the inbox-zero empty state
MEDIA_OUT = HERE.parent.parent / "chat-view" / "media" / "romp-wordmark.png"

# --- design constants -------------------------------------------------------
FONT_PX = 300
SWIRL_EM = 0.65            # the swirl, sized to read as a true lowercase "o"
# vertical-align:middle puts the swirl box center on the o-slot center. The mesh
# "o" raster is framed (102..922 crop) so its vortex/geometric center sits at the
# box center, so DY_EM=0 lands the vortex on the o center. (The old -0.20 was for a
# swirl whose content centroid sat low; it shoved this mesh "o" far too high.)
DY_EM = 0.0
TEXT = "#e8eef5"          # off-white fallback — matches the swirl's core/ring color
# each letter wears one of the swirl's three arm colors (make_icon.COLORS order:
# blue, green, teal) so the word carries the mark's palette: R=blue, m=green, p=teal.
R_COL, M_COL, P_COL = make_icon.COLORS
# Horizontal placement: the swirl box (SWIRL_EM wide) gets negative side margins so it
# occupies EXACTLY the lowercase-o slot — its center lands on the o-glyph center and its
# advance equals Anta's 'o' advance, so m/p sit where a real "o" would put them.
# margin = -(SWIRL_EM - advance('o'))/2; Anta advance('o') = 0.583em (from its hmtx).
O_ADVANCE_EM = 0.583
SW_MARGIN_X = -(SWIRL_EM - O_ADVANCE_EM) / 2   # = -0.0335em for SWIRL_EM=0.65
# Letters are thinned to the swirl's LINE weight so the strokes match (the user's
# pick): erode each glyph edge with a background-colored text-stroke. The swirl line
# reads ~0.0555em at this size; Anta's stem is ~0.1030em, so erode the difference.
SWIRL_LINE_EM = 0.0555
ANTA_STEM_EM = 0.1030
THIN_PX = round((ANTA_STEM_EM - SWIRL_LINE_EM) * FONT_PX, 1)   # = 14.2px at FONT_PX=300
BG_FLAT = "#0e1116"
CROP = "102 102 820 820"  # tight box around the glyph, centered on (512,512);
                          # roomy enough that the top node isn't clipped
CANVAS_W, CANVAS_H = 1400, 460


def strong_swirl() -> str:
    """make_icon's swirl glyph, restyled bold/crisp for use at letter size."""
    s = make_icon.variant_swirl_glyph()
    subs = [
        (r'<path[^>]*?opacity="0\.5"[^>]*?/>', '', re.S),           # drop faint halo trails
        (r'<circle[^>]*?fill="url\(#glow-[^)]*\)"[^>]*?/>', '', re.S),  # drop soft dot glows
    ]
    for pat, repl, flags in subs:
        s = re.sub(pat, repl, s, flags=flags)
    s = s.replace('stroke-width="40"', 'stroke-width="70"')         # thicken the 3 arms
    s = s.replace('r="35"', 'r="46"').replace('stroke-width="6"', 'stroke-width="10"')  # punch up nodes
    # the center is left fully open: make_icon draws no center dot or glow at all
    # (the user 2026-06-23), so the thickened arms just dissolve toward the middle.
    s = re.sub(r'width="\d+"\s+height="\d+"', '', s, count=1)       # CSS drives the size
    s = s.replace('viewBox="0 0 1024 1024"', f'viewBox="{CROP}"')
    # fail loudly if make_icon's output format drifts out from under the transform
    for leftover in ('stroke-width="40"', 'opacity="0.5"', 'url(#glow-'):
        assert leftover not in s, f"swirl format changed; update make_wordmark transform ({leftover})"
    assert 'cx="512.0" cy="512.0" r="11"' not in s, "make_icon re-added a center dot; update transform"
    return s


def build_html(transparent: bool = False) -> str:
    font_b64 = base64.b64encode(FONT.read_bytes()).decode()
    # The "o" is the FINALIZED swirl at the MATCHED weight (W=70 mesh, 102..922 crop),
    # rasterized to a transparent master (swirl-o-wordmark.png). Letters are eroded to
    # the same line weight via a bg-colored text-stroke (needs the flat BG_FLAT bg).
    o_b64 = base64.b64encode((HERE / "swirl-o-wordmark.png").read_bytes()).decode()
    thin = f"-webkit-text-stroke:{THIN_PX}px {BG_FLAT};"
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
  @font-face {{ font-family:'Anta'; src:url(data:font/ttf;base64,{font_b64}) format('truetype'); }}
  html,body {{ margin:0; padding:0; }}
  body {{ width:{CANVAS_W}px; height:{CANVAS_H}px; display:flex;
    align-items:center; justify-content:center;
    background: {BG_FLAT};
    overflow:hidden; }}
  .mark {{ font-family:'Anta',sans-serif; font-size:{FONT_PX}px; line-height:1;
    color:{TEXT}; white-space:nowrap; letter-spacing:0.01em; }}
  .mark .sw {{ height:{SWIRL_EM}em; width:{SWIRL_EM}em; display:inline-block;
    vertical-align:middle; position:relative; top:{DY_EM}em; margin:0 {SW_MARGIN_X:.4f}em;
    -webkit-text-stroke:0; }}
  .mark .sw img {{ width:100%; height:100%; display:block; }}
</style></head><body>
  <div class="mark"><span style="color:{R_COL};{thin}">R</span><span class="sw"><img src="data:image/png;base64,{o_b64}"></span><span style="color:{M_COL};{thin}">m</span><span style="color:{P_COL};{thin}">p</span></div>
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


def autotrim(path: Path, transparent: bool = False) -> None:
    """Crop the banner down to its content + even padding (no-op if no Pillow).

    For the dark banner we threshold on luminance (content vs dark bg); for the
    transparent copy we threshold on the alpha channel instead, so the crop keeps
    the mark's own light pixels and trims only the empty (alpha 0) surround.
    """
    try:
        from PIL import Image
    except ImportError:
        print("  (Pillow not installed — skipping auto-trim)")
        return
    if transparent:
        im = Image.open(path).convert("RGBA")
        mask = im.getchannel("A").point(lambda v: 255 if v > 16 else 0)  # opaque vs empty
    else:
        im = Image.open(path).convert("RGB")
        mask = im.convert("L").point(lambda v: 255 if v > 70 else 0)     # content vs dark bg
    bbox = mask.getbbox()
    if not bbox:
        return
    pad = int(0.18 * (bbox[3] - bbox[1]))
    x0, y0, x1, y1 = bbox
    im.crop((max(0, x0 - pad), max(0, y0 - pad),
             min(im.width, x1 + pad), min(im.height, y1 + pad))).save(path)


def render(chrome: str, out: Path, transparent: bool = False) -> None:
    """Rasterize the wordmark to `out` with headless Chrome, then auto-trim it."""
    cmd = [chrome, "--headless", "--disable-gpu", "--hide-scrollbars",
           "--force-device-scale-factor=2", f"--window-size={CANVAS_W},{CANVAS_H}"]
    if transparent:
        cmd.append("--default-background-color=00000000")  # keep page alpha in the screenshot
    with tempfile.TemporaryDirectory() as td:
        html = Path(td) / "wordmark.html"
        html.write_text(build_html(transparent))
        subprocess.run(cmd + [f"--screenshot={out}", html.as_uri()],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    autotrim(out, transparent)
    print("wrote", out.relative_to(HERE.parent.parent))


def main() -> None:
    chrome = find_chrome()
    render(chrome, OUT)                                    # README hero (flat #0e1116)
    MEDIA_OUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(OUT, MEDIA_OUT)                        # dashboard uses the same wordmark
    print("copied", MEDIA_OUT.relative_to(HERE.parent.parent))


if __name__ == "__main__":
    main()
