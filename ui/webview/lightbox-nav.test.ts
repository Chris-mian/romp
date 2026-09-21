// Lightbox arrow navigation (the user 2026-08-29: arrows step to the previous/next picture in the
// chat, like a messaging app). The index is provider-built from the session's EVENTS — the DOM
// misses virtualization-windowed turns — and every entry threads the (path, sid, pin) triple so a
// step renders THAT message's pinned bytes: the history-rewrite guard extends to navigation.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const PREVIEW = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "preview.ts"), "utf8");

test("the index walks EVENTS oldest→newest and threads pins per target", () => {
  const at = RENDER.indexOf("function chatImagesFor(");
  assert.ok(at > 0);
  const body = RENDER.slice(at, RENDER.indexOf("\n}", at));
  assert.match(body, /for \(const ev of s\.events/, "events, not the DOM — virtualization windows images out");
  assert.match(body, /out\.push\(\{ path: target, sid, pin: pins\[target\] \}\);/,
    "the SAME triple the embed's click passes — a step shows that message's pinned bytes");
  assert.match(body, /previewKind\(target\) !== "img"/, "the lightbox's own image gate decides image-ness");
  assert.match(body, /seen\.has\(target\)/, "one entry per (event, target)");
  assert.match(RENDER, /setLightboxNav\(chatImagesFor\);/, "registered once; providerless surfaces keep inert arrows");
});

test("arrows clamp at the ends, ride the capture listener, and never scroll the chat", () => {
  const at = PREVIEW.indexOf("const onKey = (ev: KeyboardEvent) => {");
  const body = PREVIEW.slice(at, PREVIEW.indexOf("};", at));
  assert.match(body, /ev\.key === "ArrowLeft" \|\| ev\.key === "ArrowRight"/);
  assert.match(body, /ev\.stopPropagation\(\); ev\.preventDefault\(\);/);
  assert.match(body, /ev\.key === "ArrowLeft" \? -1 : 1/, "← older, → newer — the transcript's own order");
  const stepAt = PREVIEW.indexOf("step = (delta: number) => {");
  const step = PREVIEW.slice(stepAt, PREVIEW.indexOf("};", stepAt));
  assert.match(step, /if \(at < 0 \|\| nav\.length < 2\) return;/, "a single image means arrows do nothing");
  assert.match(step, /if \(n < 0 \|\| n >= nav\.length\) return;/, "the ends END — no wrap, the messaging-app feel");
});

test("a step swaps the whole embed identity and resets the zoom (T162 contracts intact)", () => {
  const stepAt = PREVIEW.indexOf("step = (delta: number) => {");
  const step = PREVIEW.slice(stepAt, PREVIEW.indexOf("};", stepAt));
  assert.match(step, /e\.pin \? "&pin=" \+ encodeURIComponent\(e\.pin\) : ""/, "the new entry's PIN rides the src");
  assert.match(step, /pzc\.retarget\(next\);/, "zoom resets to the fit view for the new image");
  assert.match(step, /dl\.href = fileUrl\(e\.path, e\.sid\)/, "…and the download anchor follows");
  // the retarget re-identities the view for a FRESH element; the stage's listeners are wired once
  assert.match(PREVIEW, /return \{ retarget: \(next: HTMLImageElement\) => \{ img = next; view = pz\.identity\(\); ptrs\.clear\(\); start = null; apply\(\); \} \};/);
});

test("the position cue wears the house sub scale and only shows for a real sequence", () => {
  assert.match(PREVIEW, /if \(nav\.length > 1 && at >= 0\) \{/);
  const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
  assert.match(CSS, /\.romp-lightbox-cue \{ flex: 0 0 auto; font-size: 0\.82em; color: var\(--dim\); font-variant-numeric: tabular-nums; \}/);
});
