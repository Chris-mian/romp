// The composer 📎 attach button. On DESKTOP it asks the host to run a native open
// dialog (type:"pickFile") and the picked path comes back as droppedPath. On a
// TOUCH device that dialog would pop on the desktop running the kernel, not the
// phone — useless — so 📎 instead opens the phone's own photo picker (a hidden
// <input type=file accept=image/*>) and ships the chosen image's bytes to the
// host via shipFileToHost → dropFile, which saves them under the state dir and
// posts the saved path back for insertion (the user 2026-06-17).
// The chat renderer has no jsdom harness, so — like the other webview tests —
// pin the wiring at the source level.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "src", "webview", "render.ts"), "utf8");

test("📎 on touch opens an image file picker, not the desktop-only host dialog", () => {
  // a hidden file input scoped to images
  assert.match(RENDER, /createElement\("input"\)/);
  assert.match(RENDER, /filePicker\.type = "file"/);
  assert.match(RENDER, /filePicker\.accept = "image\/\*"/);
  // touch is gated on pointer:coarse (a phone), NOT viewport width — desktop panes are narrow too
  assert.match(RENDER, /matchMedia\("\(pointer:coarse\)"\)\.matches/);
  // the click handler (real gesture, required by iOS to open a file input) opens the picker on touch
  assert.match(RENDER, /attach\?\.addEventListener\("click", \(e\) => \{ if \(isTouch\(\)\) \{ e\.preventDefault\(\); filePicker\.click\(\); \} \}\)/);
});

test("📎 routes the chosen image through the existing dropFile pipeline (no new path)", () => {
  // chosen files go to shipFileToHost, which already posts {type:"dropFile"} and
  // gets {type:"droppedPath"} back — we reuse it rather than add a second uploader
  assert.match(RENDER, /filePicker\.files \|\| \[\]\)\.forEach\(\(f\) => shipFileToHost\(f\)\)/);
  assert.match(RENDER, /vscodeApi\)\s*vscodeApi\.postMessage\(\{ type: "dropFile"/);
});

test("📎 on desktop still uses the native host dialog (pickFile), unchanged", () => {
  // mousedown bails on touch so the picker (click handler) owns the phone; desktop posts pickFile
  assert.match(RENDER, /addEventListener\("mousedown", \(e\) => \{\s*if \(isTouch\(\)\) return;/);
  assert.match(RENDER, /vscodeApi\?\.postMessage\(\{ type: "pickFile" \}\)/);
});
