"""romp_colormap — the ONE recency colormap shared by every romp view.

Single source of truth: romp-feed, the kernel, and the render bundle (and any future
view / tmux segment) import age_rgb from here, so changing the look is ONE edit, not N.

age_rgb(age_seconds) -> (r,g,b): recency on a LOG scale — most recent maps to the
colormap's BRIGHT/light end, oldest to its DARK end.

To change the colormap, replace STOPS (dark -> light order). Current: crameri
"hawaii" (dark-magenta -> orange -> olive -> green -> teal -> pale-cyan), downsampled.
For an exact LUT: `pip install cmcrameri` then
    from cmcrameri import cm; import numpy as np
    [tuple(round(c*255) for c in row[:3]) for row in cm.hawaii(np.linspace(0,1,9))]
"""
import math

STOPS = [(140, 2, 115), (146, 46, 85), (151, 78, 62), (155, 111, 40), (156, 150, 28),
         (137, 189, 74), (107, 212, 142), (103, 233, 213), (179, 242, 253)]
FADE_LO, FADE_HI = 120.0, 345600.0           # 2 min (brightest) .. 96 h (darkest)

def ramp(v, stops=STOPS):
    """v in [0,1] -> interpolated RGB across stops (v=0 -> stops[0] dark, v=1 -> last, bright)."""
    v = max(0.0, min(1.0, v))
    x = v * (len(stops) - 1); i = int(x); fr = x - i
    if i >= len(stops) - 1:
        return stops[-1]
    a, b = stops[i], stops[i + 1]
    return tuple(round(a[j] + (b[j] - a[j]) * fr) for j in range(3))

def age_rgb(age):
    """AGE in seconds -> RGB. Recent -> bright (v=1), old -> dark (v=0), on a log age scale."""
    a = max(FADE_LO, min(FADE_HI, float(age)))
    f = (math.log(a) - math.log(FADE_LO)) / (math.log(FADE_HI) - math.log(FADE_LO))
    return ramp(1.0 - f)
