// The new-session picker as a FULL-SCREEN modal (the user 2026-07-05). The picker is rendered inside the
// /chat iframe, so its position:fixed;inset:0 only covered the chat PANE — on a short pane the session list
// couldn't scroll. Fix mirrors the settings bridge: render.ts tells the shell to lift #f-chat over the whole
// window (body.picker-open) while the picker is open, and the box uses the full viewport height so the list
// scrolls. Source-level pins (no jsdom for the renderer); the shell/CSS lift is pinned in tests/test_kernel.py.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("render posts {romp:'picker',on} to the shell to lift the chat iframe full-window", () => {
  // the bridge helper: only when embedded (a parent shell exists), a no-op standalone
  assert.match(RENDER, /function signalPickerOverlay\(on: boolean\)/);
  assert.match(RENDER, /window\.parent && window\.parent !== window/);
  assert.match(RENDER, /window\.parent\.postMessage\(\{ romp: "picker", on \}, "\*"\)/);
});

test("openPicker signals on, closePicker signals off", () => {
  // openPicker lifts the iframe right when it shows the overlay
  assert.match(RENDER, /overlay\.style\.display = "flex";\s*\n\s*signalPickerOverlay\(true\);/);
  // closePicker releases the lift as it hides the overlay
  assert.match(RENDER, /o\.style\.display = "none";\s*\n\s*signalPickerOverlay\(false\);/);
});

test("the picker box uses the full viewport height so the list scrolls", () => {
  // full-window now, so vh measures the whole viewport; cap to viewport minus the overlay padding so the
  // actions row is always on screen and .picker-list scrolls the rest
  assert.match(CSS, /\.picker-box \{[\s\S]*?max-height: calc\(100vh - 88px\);/);
  assert.match(CSS, /\.picker-list \{ overflow-y: auto; \}/);
});
