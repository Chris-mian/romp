#!/usr/bin/env python3
"""romp-icon — generate the romp app icon.

The icon renders the romp *timeline* visual language as a small mark: three
session-colored lines (the first three palette colors — blue/green/teal)
swirling/orbiting a center, each ending in a "prompt dot" (the colored circle
with a light border that the timeline draws at the start of every turn).

Colors are the first three of bin/romp's default _palette (reordered to put
teal third, ahead of purple, 2026-06):
  --bg       #0e1116   dark canvas
  palette-1  #1EA1EB   blue
  palette-2  #54B204   green
  palette-3  #4EA8A9   teal
  --dotBorder #e8eef5  light ring on every dot
  lines      rounded caps/joins, with a wider faint same-color "glow" understroke

Run:  uv run --with cairosvg python make_icon.py
Outputs an SVG master + PNGs per variant into this directory.
"""
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent

# --- palette: the first THREE default session colors, in bin/romp _palette order
# (the user reordered the default palette to blue, green, TEAL — teal replaced
# purple in the top three, 2026-06; purple is now last). Exact hexes from
# bin/romp's _palette so the mark matches session identity everywhere. ----------
BG        = "#0e1116"
BG_CENTER = "#171c24"
BLUE      = "#1EA1EB"   # _palette[0]
GREEN     = "#54B204"   # _palette[1]
TEAL      = "#4EA8A9"   # _palette[2]  (was purple #9088F0, now demoted to last)
DOTBORDER = "#e8eef5"
COLORS    = [BLUE, GREEN, TEAL]

SIZE   = 1024          # master canvas (square)
C      = SIZE / 2      # center
CORNER = 0.2237 * SIZE # iOS-ish rounded-square corner radius


def rad(d): return d * math.pi / 180.0


def pt(cx, cy, r, ang_deg):
    a = rad(ang_deg)
    return (cx + r * math.cos(a), cy + r * math.sin(a))


def path_d(points):
    """Polyline through points; rounded linejoin in CSS smooths it."""
    d = "M %.2f %.2f" % points[0]
    for x, y in points[1:]:
        d += " L %.2f %.2f" % (x, y)
    return d


def hex_no_hash(h): return h.lstrip("#")


# --- shared SVG fragments ---------------------------------------------------
# Comet fade: each arm's alpha ramps smoothly from 0 at its inner tip to full by
# FADE_T of the way out, then holds. Because the arm's radius grows monotonically
# along its length (r = r0 + (r1-r0)*t**FADE_EXPO), keying the fade to RADIUS is
# the same as keying it to position ALONG the arm — but it's a single radial
# gradient, so the fade stays perfectly smooth at any zoom (no segmentation).
# FADE_EXPO MUST match the exponent used to lay out the arm points (variant_swirl).
FADE_T = 0.42
FADE_EXPO = 0.92
FADE_NSTOPS = 16


def defs_for_colors(stroke_r0, stroke_r1):
    """One comet-trail stroke-fade gradient + one dot-glow gradient per color.

    The stroke gradient dissolves each line ALONG its length into the dark center
    and burns full at its dot (the 'comet trail' read), via a smoothstep opacity
    ramp sampled into gradient stops keyed to radius (see the FADE_* note above).
    """
    g = []
    for col in COLORS:
        cid = hex_no_hash(col)
        stops = [(0.0, 0.0), (stroke_r0 / stroke_r1, 0.0)]   # transparent inner tip
        for j in range(1, FADE_NSTOPS + 1):
            t = FADE_T * j / FADE_NSTOPS
            r = stroke_r0 + (stroke_r1 - stroke_r0) * (t ** FADE_EXPO)
            s = t / FADE_T
            stops.append((r / stroke_r1, s * s * (3 - 2 * s)))   # smoothstep -> full
        stops.append((1.0, 1.0))
        trail = "".join(
            f'\n      <stop offset="{o:.4f}" stop-color="{col}" stop-opacity="{op:.4f}"/>'
            for o, op in stops)
        g.append(f'''
    <radialGradient id="trail-{cid}" gradientUnits="userSpaceOnUse"
        cx="{C}" cy="{C}" r="{stroke_r1:.1f}">{trail}
    </radialGradient>
    <radialGradient id="glow-{cid}">
      <stop offset="0" stop-color="{col}" stop-opacity="0.55"/>
      <stop offset="0.45" stop-color="{col}" stop-opacity="0.18"/>
      <stop offset="1" stop-color="{col}" stop-opacity="0"/>
    </radialGradient>''')
    return "".join(g)


def background():
    return f'''
  <defs>
    <radialGradient id="bgwash" cx="0.5" cy="0.42" r="0.75">
      <stop offset="0" stop-color="{BG_CENTER}"/>
      <stop offset="1" stop-color="{BG}"/>
    </radialGradient>
  </defs>
  <rect x="0" y="0" width="{SIZE}" height="{SIZE}" rx="{CORNER:.1f}" ry="{CORNER:.1f}"
        fill="url(#bgwash)"/>
  <rect x="1.5" y="1.5" width="{SIZE-3}" height="{SIZE-3}" rx="{CORNER-1.5:.1f}" ry="{CORNER-1.5:.1f}"
        fill="none" stroke="#ffffff" stroke-opacity="0.06" stroke-width="2"/>'''


def dot(x, y, col, r=35, glow_r=92, ring=6):
    cid = hex_no_hash(col)
    return f'''
  <circle cx="{x:.2f}" cy="{y:.2f}" r="{glow_r}" fill="url(#glow-{cid})"/>
  <circle cx="{x:.2f}" cy="{y:.2f}" r="{r}" fill="{col}"/>
  <circle cx="{x:.2f}" cy="{y:.2f}" r="{r}" fill="none"
          stroke="{DOTBORDER}" stroke-opacity="0.92" stroke-width="{ring}"/>'''


def center_node():
    # No center mark: the sharp white dot AND the soft white center glow were both
    # removed (the user 2026-06-23), so the arms dissolve into a fully open center.
    return ""


def center_glow_def():
    col = DOTBORDER
    cid = hex_no_hash(col)
    return f'''
    <radialGradient id="glow-{cid}">
      <stop offset="0" stop-color="{col}" stop-opacity="0.22"/>
      <stop offset="1" stop-color="{col}" stop-opacity="0"/>
    </radialGradient>'''


def line(d, col, w_main, w_glow):
    cid = hex_no_hash(col)
    return f'''
  <path d="{d}" fill="none" stroke="url(#trail-{cid})" stroke-width="{w_glow}"
        stroke-linecap="round" stroke-linejoin="round" opacity="0.5"/>
  <path d="{d}" fill="none" stroke="url(#trail-{cid})" stroke-width="{w_main}"
        stroke-linecap="round" stroke-linejoin="round"/>'''


# --- variant: swirl (logarithmic-ish spiral arms) ---------------------------
# with_bg=False → the arms+dots on a TRANSPARENT canvas (no rounded-square
# background): the favicon / VS Code activity-bar GLYPH, which sits on the host's
# own surface. With background → the full app-icon tile.
def variant_swirl(with_bg=True):
    r0, r1 = 70, 352          # r0 pulled inward so the arms dissolve nearer the center
    sweep = 252
    rot0 = -100
    N = 90
    arms = []
    dots = []
    for i, col in enumerate(COLORS):
        base = rot0 + i * 120
        pts = []
        last = None
        for k in range(N + 1):
            t = k / N
            r = r0 + (r1 - r0) * (t ** 0.92)
            ang = base + sweep * t
            x, y = pt(C, C, r, ang)
            pts.append((x, y))
            last = (x, y)
        arms.append(line(path_d(pts), col, 40, 96))
        dots.append(dot(last[0], last[1], col))
    body = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}" '
            f'viewBox="0 0 {SIZE} {SIZE}">'
            + (background() if with_bg else "")
            + f'<defs>{defs_for_colors(r0, r1)}</defs>'
            + "".join(arms) + "".join(dots)
            + "</svg>")
    return body


def variant_swirl_glyph():
    return variant_swirl(with_bg=False)


# --- variant: orbit (three elliptical orbital arcs, atom-like) --------------
def variant_orbit():
    A, B = 360, 138        # ellipse semi-axes
    start, end = 18, 322   # degrees of the arc actually drawn (gap for the dot)
    N = 120
    arms = []
    dots = []
    # constant-opacity strokes for orbits (like the timeline's alpha-stacking),
    # so crossings near the center read as an interwoven knot.
    defs = []
    for col in COLORS:
        defs.append(defs_for_colors(60, 360))  # reuse trail grads (unused) + glow
    glowdefs = "".join(
        f'''<radialGradient id="glow-{hex_no_hash(col)}">
              <stop offset="0" stop-color="{col}" stop-opacity="0.5"/>
              <stop offset="0.45" stop-color="{col}" stop-opacity="0.16"/>
              <stop offset="1" stop-color="{col}" stop-opacity="0"/>
            </radialGradient>''' for col in COLORS)
    for i, col in enumerate(COLORS):
        orot = i * 60
        pts = []
        for k in range(N + 1):
            t = k / N
            ang = start + (end - start) * t
            # point on axis-aligned ellipse then rotate by orot
            ex = A * math.cos(rad(ang))
            ey = B * math.sin(rad(ang))
            ca, sa = math.cos(rad(orot)), math.sin(rad(orot))
            x = C + ex * ca - ey * sa
            y = C + ex * sa + ey * ca
            pts.append((x, y))
        d = path_d(pts)
        head = pts[-1]
        cid = hex_no_hash(col)
        arms.append(
            f'<path d="{d}" fill="none" stroke="{col}" stroke-opacity="0.28" '
            f'stroke-width="42" stroke-linecap="round"/>'
            f'<path d="{d}" fill="none" stroke="{col}" stroke-opacity="0.92" '
            f'stroke-width="17" stroke-linecap="round"/>')
        dots.append(dot(head[0], head[1], col))
    body = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}" '
            f'viewBox="0 0 {SIZE} {SIZE}">'
            + background()
            + f'<defs>{glowdefs}{center_glow_def()}</defs>'
            + "".join(arms) + center_node() + "".join(dots)
            + "</svg>")
    return body


# --- variant: braid (tighter intertwining vortex) ---------------------------
def variant_braid():
    r0, r1 = 70, 350
    sweep = 410          # >360 so arms wrap and cross -> woven look
    rot0 = -90
    N = 140
    arms = []
    dots = []
    for i, col in enumerate(COLORS):
        base = rot0 + i * 120
        pts = []
        last = None
        for k in range(N + 1):
            t = k / N
            r = r0 + (r1 - r0) * (t ** 1.05)
            # gentle radial wobble so arms weave over/under each other
            r += 26 * math.sin(rad(sweep * t * 1.0))
            ang = base + sweep * t
            x, y = pt(C, C, r, ang)
            pts.append((x, y))
            last = (x, y)
        arms.append(line(path_d(pts), col, 16, 40))
        dots.append(dot(last[0], last[1], col))
    body = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{SIZE}" height="{SIZE}" '
            f'viewBox="0 0 {SIZE} {SIZE}">'
            + background()
            + f'<defs>{defs_for_colors(r0, r1)}{center_glow_def()}</defs>'
            + "".join(arms) + center_node() + "".join(dots)
            + "</svg>")
    return body


VARIANTS = {
    "swirl": variant_swirl,
    "orbit": variant_orbit,
    "braid": variant_braid,
}


# --- monochrome MASK variant (for VS Code's tinted editor-title button) ------
# Flat, single-color line-art swirl on a transparent bg, drawn small (32u canvas)
# so it stays legible when VS Code masks/tints it down to ~16px. No gradients,
# no glow, no background — just the pinwheel + tip dots in one color.
def mask_body(color, with_center=False):
    S = 32.0
    c = S / 2
    r0, r1 = 6.6, 10.7
    sweep = 104       # short hooks in the outer ring -> 3 clean comma blades at ~16px
    rot0 = -100
    N = 40
    sw = 2.7          # stroke width
    dot_r = 2.8
    parts = []
    for i in range(3):
        base = rot0 + i * 120
        pts = []
        for k in range(N + 1):
            t = k / N
            r = r0 + (r1 - r0) * (t ** 0.92)
            ang = base + sweep * t
            pts.append(pt(c, c, r, ang))
        d = "M %.3f %.3f " % pts[0] + " ".join("L %.3f %.3f" % (x, y) for x, y in pts[1:])
        parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{sw}" '
                     f'stroke-linecap="round" stroke-linejoin="round"/>')
        hx, hy = pts[-1]
        parts.append(f'<circle cx="{hx:.3f}" cy="{hy:.3f}" r="{dot_r}" fill="{color}"/>')
    if with_center:
        parts.append(f'<circle cx="{c}" cy="{c}" r="1.7" fill="{color}"/>')
    return "".join(parts)


def variant_mask(color="currentColor", with_center=True):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" '
            'viewBox="0 0 32 32">' + mask_body(color, with_center) + "</svg>")


def mask_preview(color="#e8eef5", with_center=True):
    """White-on-dark card so the mask is visible in a PNG preview."""
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" '
            'viewBox="0 0 32 32"><rect width="32" height="32" rx="7" fill="#0e1116"/>'
            + mask_body(color, with_center) + "</svg>")


def main():
    # 1) always emit the SVG masters (no native deps)
    for name, fn in VARIANTS.items():
        svg = fn()
        svg_path = HERE / f"romp-icon-{name}.svg"
        svg_path.write_text(svg)
        print("wrote", svg_path.name)
    # transparent-background swirl glyph (favicon + VS Code activity-bar icon)
    (HERE / "romp-icon-swirl-glyph.svg").write_text(variant_swirl_glyph())
    print("wrote romp-icon-swirl-glyph.svg")

    # 2) try to rasterize via cairosvg if the native cairo lib is present
    try:
        import cairosvg
    except Exception as e:               # ImportError OR OSError (missing libcairo)
        print("cairosvg unavailable (%s); SVGs written, rasterize separately" % e)
        return
    for name in VARIANTS:
        svg = (HERE / f"romp-icon-{name}.svg").read_text()
        for px in (1024, 256):
            out = HERE / f"romp-icon-{name}-{px}.png"
            cairosvg.svg2png(bytestring=svg.encode(), write_to=str(out),
                             output_width=px, output_height=px)
            print("  ->", out.name)

    # monochrome mask deliverable (currentColor so VS Code can tint it) + previews
    (HERE / "romp-icon-mask.svg").write_text(variant_mask("currentColor", with_center=False))
    print("wrote romp-icon-mask.svg")
    prev = mask_preview("#e8eef5", with_center=False)
    for px in (16, 24, 32, 96, 256):
        out = HERE / f"romp-icon-mask-preview-{px}.png"
        cairosvg.svg2png(bytestring=prev.encode(), write_to=str(out),
                         output_width=px, output_height=px)
        print("  ->", out.name)


if __name__ == "__main__":
    main()
