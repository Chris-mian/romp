// The ONE context-pressure threshold pair (2026-08-27): warn 70, danger 88 — replacing the 60/85
// ctx-gauge triple and the 70/90 usage-bar pair that disagreed about when the same fullness turns
// alarming. kernel/colormap.py owns the canonical pair (pinned by test_kernel_context_colormap);
// this pins the client mirror and the timeline's inlined copy (plain JS in a foreign host — it
// cannot import, so equality is enforced by grep, the STOPS-parity precedent).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { CTX_WARN, CTX_DANGER, ctxFallbackColor, usageFallbackColor, pickTone, readableRgb } from "./ctx-color";

const ui = (...p: string[]) => fs.readFileSync(path.resolve(process.cwd(), "..", "ui", ...p), "utf8");

// executable in BOTH themes: a fake body toggles the class the picker probes
function withBody(classes: string[], fn: () => void): void {
  (globalThis as any).document = { body: { classList: { contains: (c: string) => classes.includes(c) } } };
  try { fn(); } finally { delete (globalThis as any).document; }
}

test("CLASSIC keeps main's palettes verbatim (the owner's call, PR #763): 60/85 ctx, 70/90 usage", () => {
  withBody([], () => {
    assert.equal(ctxFallbackColor(59), "#54B204");
    assert.equal(ctxFallbackColor(60), "#e0b020");
    assert.equal(ctxFallbackColor(84), "#e0b020");
    assert.equal(ctxFallbackColor(85), "#c0392b");
    assert.equal(usageFallbackColor(69), "#54B204");
    assert.equal(usageFallbackColor(70), "#e0b020");
    assert.equal(usageFallbackColor(89), "#e0b020");
    assert.equal(usageFallbackColor(90), "#c0392b");
    // and the picker hands back the classic color, ignoring a shipped tone
    assert.deepEqual(pickTone([1, 2, 3], [9, 9, 9]), [1, 2, 3]);
  });
});

test("the yatharth themes use the unified 70/88 pair + the tone palette, and pick shipped tones", () => {
  assert.equal(CTX_WARN, 70);
  assert.equal(CTX_DANGER, 88);
  withBody(["chat-theme-yatharth"], () => {
    assert.equal(ctxFallbackColor(0), "#5196B8");
    assert.equal(ctxFallbackColor(CTX_WARN), "#d7a23a");
    assert.equal(ctxFallbackColor(CTX_DANGER), "#c0392b");
    assert.equal(usageFallbackColor(CTX_DANGER - 1), "#d7a23a");
    assert.deepEqual(pickTone([1, 2, 3], [9, 9, 9]), [9, 9, 9]);
    assert.deepEqual(pickTone([1, 2, 3], undefined), [1, 2, 3], "older kernel: no tone -> classic color");
  });
});

test("light re-encodes kernel RGB down in lightness, order preserved; dark passes through", () => {
  withBody(["chat-theme-yatharth", "theme-light"], () => {
    const faint = readableRgb([184, 129, 81]);   // haiku's dark tone
    const vivid = readableRgb([247, 169, 100]);  // fable's
    const lum = (c: number[]) => 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
    assert.ok(lum(faint) < 0.5 * 255 && lum(vivid) < 0.55 * 255, "darkened for the ivory ground");
    assert.ok(lum(vivid) > lum(faint), "the vividness ORDER survives");
  });
  withBody(["chat-theme-yatharth"], () => {
    assert.deepEqual(readableRgb([184, 129, 81]), [184, 129, 81], "dark passes through untouched");
  });
});

test("the timeline's inlined copies match (it runs inside Obsidian and cannot import)", () => {
  const TL = ui("romp-timeline-view.js");
  assert.equal((TL.match(/>= 88 \? '#c0392b' : \(p(?:ct)? >= 70 \? '#d7a23a' : '#5196B8'\)/g) || []).length, 2,
    "both timeline yatharth fallbacks carry the unified pair");
  assert.equal((TL.match(/>= 85 \? '#c0392b' : \(p >= 60 \? '#e0b020' : '#54B204'\)/g) || []).length, 1,
    "the ctx classic fallback is main's 60/85 verbatim");
  assert.equal((TL.match(/>= 90 \? '#c0392b' : \(pct >= 70 \? '#e0b020' : '#54B204'\)/g) || []).length, 1,
    "the usage classic fallback is main's 70/90 verbatim");
  assert.match(TL, /function pickTone\(legacy, tone\)/, "the dual-palette pick is inlined");
  assert.match(TL, /function readableRgb\(rgb\)/, "…and the light re-encode");
});

test("kernel and client state the same pair (grep parity — the kernel is python)", () => {
  const CM = fs.readFileSync(path.resolve(process.cwd(), "..", "kernel", "colormap.py"), "utf8");
  assert.match(CM, /CTX_WARN, CTX_DANGER = 70, 88/);
});
