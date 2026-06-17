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

# dark -> light. The default name; views fall back to this for an unknown name.
DEFAULT = "hawaii"
COLORMAPS = {
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
    "cividis": [(0, 32, 76), (0, 42, 102), (45, 63, 112), (87, 85, 109), (124, 109, 107),
                (165, 135, 99), (208, 164, 80), (255, 234, 70)],
}
# original module-level name kept so any old `from romp_colormap import STOPS` still works.
STOPS = COLORMAPS["hawaii"]
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
