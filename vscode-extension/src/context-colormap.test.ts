// The GLOBAL colormap colors the context-window % bars (the user 2026-06-26). The kernel ships ctxColor
// ([r,g,b]) per session; the client surfaces just apply it (mirrors the usage bar) and fall back to the old
// green/amber/red traffic-light only when an older kernel ships no color. Surfaces: the chat statusline +
// tab-tooltip battery (render.ts setCtxBar), and the timeline lane battery (romp-timeline-view.js ctxInfo).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const TL = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");

test("the chat battery applies the server ctxColor, falling back to the traffic-light", () => {
  assert.match(RENDER, /ctxColor\?: number\[\];/);   // on the Status interface
  assert.match(RENDER, /function setCtxBar\(bar: HTMLElement, ctxStr: string \| undefined, compacting = false, ctxColor\?: number\[\]\)/);
  assert.match(RENDER, /\(ctxColor && ctxColor\.length === 3\) \? `rgb\(\$\{ctxColor\.join\(","\)\}\)`/);
  assert.match(RENDER, /pct >= 85 \? "#c0392b" : pct >= 60 \? "#e0b020" : "#54B204"/);  // fallback intact
});

test("every setCtxBar caller threads s.status.ctxColor (statusline, tick, tab tooltip)", () => {
  const calls = RENDER.match(/setCtxBar\(bar, s\.status\.ctx, s\.status\.state === "compacting", s\.status\.ctxColor\)/g) || [];
  assert.equal(calls.length, 3, "all three callers pass the color through");
});

test("the timeline lane battery applies the server ctxColor with the same fallback", () => {
  assert.match(TL, /\(s\.ctxColor && s\.ctxColor\.length === 3\) \? 'rgb\(' \+ s\.ctxColor\.join\(','\) \+ '\)'/);
  assert.match(TL, /p >= 85 \? '#c0392b' : \(p >= 60 \? '#e0b020' : '#54B204'\)/);   // fallback intact
});
