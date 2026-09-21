// Theme-aware color picking for the kernel's DUAL palette (PR #763 review item 1): the kernel
// ships BOTH the classic colors (modelColor/effortColor/ctxColor + usage seg.color — the recency
// colormap, byte-identical to what main always shipped) and the yatharth tones (modelTone/
// effortTone/ctxTone/seg.tone — single-hue ramps: orange by capability, violet by effort, teal
// context). The theme lives client-side, so the CLIENT picks: classic keeps its colors untouched
// (the owner's call), the yatharth themes take the tones. The probe is the one class every
// non-classic theme wears (body.chat-theme-yatharth, set by theme.ts / the shell's inline reader);
// a document with no class — including the Obsidian timeline host — is classic by construction.
export const CTX_WARN = 70;
export const CTX_DANGER = 88;
const CALM = "#5196B8";     // tone_rgb("context", 0) — the calm end of the teal tone
const WARN = "#d7a23a";     // --warn
const DANGER = "#c0392b";   // --err

export function nonClassic(): boolean {
  try { return document.body.classList.contains("chat-theme-yatharth"); } catch { return false; }
}
export function isLightTheme(): boolean {
  try { return document.body.classList.contains("theme-light"); } catch { return false; }
}

/** The theme pick: the tone on a yatharth theme when the kernel shipped one, else the classic
 * color (also the older-kernel fallback — no tones in the payload degrades to classic colors). */
export function pickTone(legacy?: number[] | null, tone?: number[] | null): number[] | undefined {
  return nonClassic() && tone && tone.length === 3 ? tone : (legacy ?? undefined);
}

/** Kernel-shipped RGB is dark-tuned (~L 0.52-0.72 — unreadable at ~2.2:1 on the ivory page); on
 * the light theme re-encode lightness down and saturation up, preserving hue and the vividness
 * ORDER (review item 4). Dark and classic pass through untouched. */
export function readableRgb(rgb: number[]): number[] {
  if (!isLightTheme() || rgb.length !== 3) return rgb;
  const [h, s, l] = rgbToHsl(rgb[0], rgb[1], rgb[2]);
  return hslToRgb(h, Math.min(1, s + 0.08), Math.min(0.46, Math.max(0.26, l * 0.62)));
}

/** The stale-kernel fallback (no server color in the payload). Classic keeps main's exact
 * traffic light (60/85, the historical palette); the yatharth themes use the unified pair. */
export function ctxFallbackColor(pct: number): string {
  if (!nonClassic()) return pct >= 85 ? "#c0392b" : pct >= 60 ? "#e0b020" : "#54B204";
  return pct >= CTX_DANGER ? DANGER : pct >= CTX_WARN ? WARN : CALM;
}

/** The usage bars' fallback: classic keeps main's 70/90 palette; yatharth the unified pair. */
export function usageFallbackColor(pct: number): string {
  if (!nonClassic()) return pct >= 90 ? "#c0392b" : pct >= 70 ? "#e0b020" : "#54B204";
  return pct >= CTX_DANGER ? DANGER : pct >= CTX_WARN ? WARN : CALM;
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
