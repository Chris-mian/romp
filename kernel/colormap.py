"""romp_colormap — the recency colormaps shared by every romp view.

Single source of truth: romp-feed, the kernel, and the render bundle (and any future
view / tmux segment) import age_rgb from here, so the look is ONE edit, not N.

age_rgb(age_seconds, name) -> (r,g,b): recency on a LOG scale — most recent maps to the
colormap's BRIGHT/light end, oldest to its DARK end. `name` picks the colormap (the user
2026-06-16 wanted a chooser); default "hawaii" keeps the original look.

Each colormap is STOPS in dark -> light order (recent -> the LAST/bright stop). hawaii is
crameri "hawaii"; the rest are matplotlib's perceptually-uniform maps, downsampled. For an
exact LUT of any: `pip install matplotlib` (or cmcrameri for hawaii) then
    import matplotlib.cm as m, numpy as np
    [tuple(round(c*255) for c in m.get_cmap("viridis")(x)[:3]) for x in np.linspace(0,1,9)]
"""
import math

# dark -> light. The default name; views fall back to this for an unknown name. romp's own 'aurora' is the
# default (the user 2026-06-27) and is listed FIRST so it leads the picker.
DEFAULT = "aurora"
COLORMAPS = {
    # romp's brand hues — green → teal → blue → purple — swept at CONSTANT (perceptual) lightness (the user
    # 2026-06-27, reversed). Generated in OKLCH: the four anchors (#54B204 #4EA8A9 #1EA1EB #9088F0) all sit at
    # L≈0.678, so the ramp holds that L throughout while only the hue turns — value reads by HUE, not
    # brightness (an iso-luminant map). Per-anchor chroma is interpolated, so the ends ARE the true romp shades.
    "aurora": [(84, 178, 4), (0, 180, 115), (35, 175, 156), (66, 169, 176), (25, 168, 201),
               (14, 164, 227), (74, 155, 241), (113, 145, 244), (144, 136, 240)],
    "hawaii": [(140, 2, 115), (146, 46, 85), (151, 78, 62), (155, 111, 40), (156, 150, 28),
               (137, 189, 74), (107, 212, 142), (103, 233, 213), (179, 242, 253)],
    "viridis": [(68, 1, 84), (72, 40, 120), (62, 74, 137), (49, 104, 142), (38, 130, 142),
                (31, 158, 137), (53, 183, 121), (110, 206, 88), (181, 222, 43), (253, 231, 37)],
    "magma": [(0, 0, 4), (28, 16, 68), (79, 18, 123), (129, 37, 129), (181, 54, 122),
              (229, 80, 100), (251, 135, 97), (254, 194, 135), (252, 253, 191)],
    "inferno": [(0, 0, 4), (40, 11, 84), (101, 21, 110), (159, 42, 99), (212, 72, 66),
                (245, 125, 21), (250, 193, 39), (252, 255, 164)],
    "plasma": [(13, 8, 135), (75, 3, 161), (125, 3, 168), (168, 34, 150), (203, 70, 121),
               (229, 107, 93), (248, 148, 65), (253, 195, 40), (240, 249, 33)],
    "cividis": [(0, 34, 78), (33, 59, 110), (76, 85, 108), (108, 110, 114), (142, 137, 120),
                (177, 165, 112), (217, 197, 92), (254, 232, 56)],
}
# original module-level name kept so any old `from romp_colormap import STOPS` still works.
STOPS = COLORMAPS[DEFAULT]
FADE_LO, FADE_HI = 120.0, 345600.0           # 2 min (brightest) .. 96 h (darkest)


def stops_for(name):
    return COLORMAPS.get((name or "").lower(), COLORMAPS[DEFAULT])


def ramp(v, stops=STOPS):
    """v in [0,1] -> interpolated RGB across stops (v=0 -> stops[0] dark, v=1 -> last, bright)."""
    v = max(0.0, min(1.0, v))
    x = v * (len(stops) - 1); i = int(x); fr = x - i
    if i >= len(stops) - 1:
        return stops[-1]
    a, b = stops[i], stops[i + 1]
    return tuple(round(a[j] + (b[j] - a[j]) * fr) for j in range(3))


def age_rgb(age, name=DEFAULT):
    """AGE in seconds -> RGB on colormap `name`. Recent -> bright (v=1), old -> dark (v=0), log scale."""
    a = max(FADE_LO, min(FADE_HI, float(age)))
    f = (math.log(a) - math.log(FADE_LO)) / (math.log(FADE_HI) - math.log(FADE_LO))
    return ramp(1.0 - f, stops_for(name))


# ── semantic single-tone ramps (the user 2026-08-27) ──────────────────────────────────────────
# Model capability, reasoning effort, and context pressure used to sample the SAME user-selectable
# recency colormap over its full extent — so fable == ultracode == a 100%-full context (one
# identical purple) and haiku == low == 0% (one identical green): three meanings, one color. Each
# quantity now owns ONE hue, with saturation+lightness encoding magnitude ("more" reads as more
# vivid), so the FAMILY is recognizable at a glance and the level within it needs no legend:
#   model   = orange (hue 28)  — haiku #B88151 … fable #F7A964
#   effort  = violet (hue 258) — low #9A84CD … ultracode #B394F9 (higher L floor: violets read dark)
#   context = teal   (hue 200) — calm below the warn line; amber/red are SEMANTIC overrides above
# Every sampled value clears 5:1 on the dark #1e1e1e page (tuned 2026-08-27); light-theme clients
# re-encode lightness client-side (the kernel cannot know a page's theme — one kernel serves
# browser, VS Code and Obsidian hosts at once). The recency colormap (gear picker) keeps governing
# feed recency + the compacting sweep only.
TONE_HUES = {"model": 28.0, "effort": 258.0, "context": 200.0}
_TONE_L = {"model": (0.52, 0.16), "effort": (0.66, 0.12), "context": (0.52, 0.16)}


def _hsl_to_rgb(h, s, l):
    h = (h % 360.0) / 360.0
    if s <= 0:
        v = round(l * 255)
        return (v, v, v)
    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q

    def ch(t):
        t = t % 1.0
        if t < 1 / 6: return p + (q - p) * 6 * t
        if t < 1 / 2: return q
        if t < 2 / 3: return p + (q - p) * (2 / 3 - t) * 6
        return p

    return tuple(round(ch(x) * 255) for x in (h + 1 / 3, h, h - 1 / 3))


def tone_rgb(family, v):
    """v in [0,1] -> RGB in `family`'s hue; higher v = more saturated and lighter (dark-UI canonical)."""
    v = max(0.0, min(1.0, float(v)))
    l0, l1 = _TONE_L[family]
    return _hsl_to_rgb(TONE_HUES[family], 0.42 + 0.48 * v, l0 + l1 * v)


# Context-pressure thresholds — ONE pair for every gauge. Before 2026-08-27 the ctx gauges said
# 60/85 (three copies) while the usage bars said 70/90 (two more, bypassing the colormap): the same
# fullness wore different alarms on different surfaces. Above the lines the color is a STATUS, not
# a position on an aesthetic ramp — the shared warn amber, then the shared alarm red.
CTX_WARN, CTX_DANGER = 70, 88
WARN_RGB = (215, 162, 58)     # --warn
DANGER_RGB = (192, 57, 43)    # --err


def context_rgb(pct):
    """Context/usage fullness percent -> RGB: the calm teal tone until CTX_WARN, then amber, then red."""
    p = max(0.0, min(100.0, float(pct or 0)))
    if p >= CTX_DANGER:
        return DANGER_RGB
    if p >= CTX_WARN:
        return WARN_RGB
    return tone_rgb("context", p / 100.0)
