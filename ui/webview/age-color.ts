// The recency colour ramp — ONE shared implementation for every "(Xm ago)" tint outside render.ts
// (extracted 2026-07-27 from fleet.ts, which had copied it verbatim from render.ts; the feed's
// age-provenance popover made a third copy imminent, so the copy became a module). render.ts still
// carries its own twin, entangled with its live `settings` object — KEEP THE TWO IN SYNC, and both
// in sync with bin/romp_colormap.py (the kernel computes trgb tints from the same stops).
export const COLORMAPS: Record<string, Array<[number, number, number]>> = {
  aurora: [[84, 178, 4], [0, 180, 115], [35, 175, 156], [66, 169, 176], [25, 168, 201], [14, 164, 227], [74, 155, 241], [113, 145, 244], [144, 136, 240]],   // romp green→teal→blue→purple at CONSTANT lightness — the default
  hawaii: [[140, 2, 115], [146, 46, 85], [151, 78, 62], [155, 111, 40], [156, 150, 28], [137, 189, 74], [107, 212, 142], [103, 233, 213], [179, 242, 253]],
  viridis: [[68, 1, 84], [72, 40, 120], [62, 74, 137], [49, 104, 142], [38, 130, 142], [31, 158, 137], [53, 183, 121], [110, 206, 88], [181, 222, 43], [253, 231, 37]],
  magma: [[0, 0, 4], [28, 16, 68], [79, 18, 123], [129, 37, 129], [181, 54, 122], [229, 80, 100], [251, 135, 97], [254, 194, 135], [252, 253, 191]],
  inferno: [[0, 0, 4], [40, 11, 84], [101, 21, 110], [159, 42, 99], [212, 72, 66], [245, 125, 21], [250, 193, 39], [252, 255, 164]],
  plasma: [[13, 8, 135], [75, 3, 161], [125, 3, 168], [168, 34, 150], [203, 70, 121], [229, 107, 93], [248, 148, 65], [253, 195, 40], [240, 249, 33]],
  cividis: [[0, 34, 78], [33, 59, 110], [76, 85, 108], [108, 110, 114], [142, 137, 120], [177, 165, 112], [217, 197, 92], [254, 232, 56]],
};
function selectedStops(): Array<[number, number, number]> {
  let name = "aurora";
  try { name = String(JSON.parse(localStorage.getItem("romp:settings") || "{}").colormap || "aurora"); } catch { /* default */ }
  return COLORMAPS[name.toLowerCase()] || COLORMAPS.aurora;
}
function ramp(v: number): [number, number, number] {
  const STOPS = selectedStops();
  v = Math.max(0, Math.min(1, v));
  const x = v * (STOPS.length - 1), i = Math.floor(x), fr = x - i;
  if (i >= STOPS.length - 1) return STOPS[STOPS.length - 1];
  const a = STOPS[i], b = STOPS[i + 1];
  return [Math.round(a[0] + (b[0] - a[0]) * fr), Math.round(a[1] + (b[1] - a[1]) * fr), Math.round(a[2] + (b[2] - a[2]) * fr)];
}
function recencyV(ageSecs: number): number {
  const LO = 120, HI = 345600;
  const a = Math.max(LO, Math.min(HI, ageSecs));
  return 1.0 - (Math.log(a) - Math.log(LO)) / (Math.log(HI) - Math.log(LO));
}
function rgbToHsl(r: number, g: number, b: number): [number, number, number] {
  r /= 255; g /= 255; b /= 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
  let h = 0; const l = (mx + mn) / 2;
  const s = d === 0 ? 0 : l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
  if (d !== 0) {
    if (mx === r) h = (g - b) / d + (g < b ? 6 : 0);
    else if (mx === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h /= 6;
  }
  return [h, s, l];
}
function hslToRgb(h: number, s: number, l: number): [number, number, number] {
  if (s === 0) { const v = Math.round(l * 255); return [v, v, v]; }
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s, p = 2 * l - q;
  const hk = (t: number) => {
    if (t < 0) t += 1; if (t > 1) t -= 1;
    if (t < 1 / 6) return p + (q - p) * 6 * t;
    if (t < 1 / 2) return q;
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
    return p;
  };
  return [Math.round(hk(h + 1 / 3) * 255), Math.round(hk(h) * 255), Math.round(hk(h - 1 / 3) * 255)];
}
export function ageColorReadable(ageSecs: number): string {
  const v = recencyV(ageSecs);
  const c = ramp(v);
  const [h, s] = rgbToHsl(c[0], c[1], c[2]);
  const L = 0.50 + 0.22 * v;
  const S = Math.max(0.4, s) * (0.65 + 0.35 * v);
  const o = hslToRgb(h, Math.min(1, S), L);
  return `rgb(${o[0]}, ${o[1]}, ${o[2]})`;
}
