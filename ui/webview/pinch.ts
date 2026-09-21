// Pure pinch-zoom math for the image lightbox (T162, the user 2026-08-28 on Android: a picture
// popped up from the chat should support pinch and zoom). No gesture library — pointer-pair
// arithmetic only, kept pure so the geometry is executable-testable headless; the DOM wiring
// (pointer capture, touch-action, the close-gesture guard) lives with openLightbox in preview.ts.
//
// Coordinate frame: q-space — pointer positions relative to the image's UNTRANSFORMED layout
// top-left (the caller subtracts the rest rect). The view renders as
// `translate(tx,ty) scale(s)` with transform-origin 0 0, so a content point c appears at
// q = c*s + t, and the invariant a pinch must keep is THE CONTENT POINT UNDER THE GESTURE
// MIDPOINT STAYS UNDER IT while s changes.

export interface PinchView { s: number; tx: number; ty: number; }
export const PINCH_MIN = 1;
export const PINCH_MAX = 8;
export const PINCH_SNAP = 1.05;        // a pinch ending this close to 1× settles home
export const DOUBLE_TAP_SCALE = 2.5;   // the platform-convention double-tap zoom step

export const identity = (): PinchView => ({ s: 1, tx: 0, ty: 0 });

export function dist(a: { x: number; y: number }, b: { x: number; y: number }): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}
export function midpoint(a: { x: number; y: number }, b: { x: number; y: number }): { x: number; y: number } {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}

/** Scale by `factor` around viewport point q=(mx,my): solve t' so (m - t')/s' == (m - t)/s. */
export function zoomAt(v: PinchView, mx: number, my: number, factor: number): PinchView {
  const s = Math.min(PINCH_MAX, Math.max(PINCH_MIN, v.s * factor));
  const k = s / v.s;
  return { s, tx: mx - (mx - v.tx) * k, ty: my - (my - v.ty) * k };
}

export function pan(v: PinchView, dx: number, dy: number): PinchView {
  return { s: v.s, tx: v.tx + dx, ty: v.ty + dy };
}

/** Keep the scaled content covering the viewport: when the scaled size exceeds the box, the edges
 *  may never pull inside it (no void beyond the image); when it fits, center that axis. (w,h) is
 *  the content's rest size, (vw,vh) the box it rests in, both in q-space. */
export function clampPan(v: PinchView, w: number, h: number, vw: number, vh: number): PinchView {
  const sw = w * v.s, sh = h * v.s;
  const clampAxis = (t: number, scaled: number, box: number): number =>
    scaled <= box ? (box - scaled) / 2 : Math.min(0, Math.max(box - scaled, t));
  return { s: v.s, tx: clampAxis(v.tx, sw, vw), ty: clampAxis(v.ty, sh, vh) };
}

/** A gesture ending near 1× settles exactly home — event-keyed (the gesture's own end), no timer. */
export function settle(v: PinchView): PinchView {
  return v.s < PINCH_SNAP ? identity() : v;
}

/** Double-tap toggles: zoomed (any s>1) → home; home → DOUBLE_TAP_SCALE around the tap point. */
export function doubleTapToggle(v: PinchView, mx: number, my: number): PinchView {
  return v.s > 1 ? identity() : zoomAt(identity(), mx, my, DOUBLE_TAP_SCALE);
}
