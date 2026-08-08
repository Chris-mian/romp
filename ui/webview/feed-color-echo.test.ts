// The optimistic colour echo (the user 2026-08-08): picking a tab-menu swatch in the CHAT pane
// repainted the tabs instantly, but the FEED kept the old colour until the kernel's next feed REBUILD
// pushed — a second or two. The echo now travels kernel-free on the same host-matched pair settings
// sync rides: the browser's same-origin iframes hear a localStorage write (`storage` fires
// cross-document), and in VS Code — separate synthetic origins, no storage events — the extension fans
// {colorSync} to its other panels. setSessionColor still goes to the kernel, whose re-broadcast
// reconciles behind the echo. Source pins (no jsdom harness — the repo convention).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const ROOT = path.resolve(process.cwd(), "..");
const RENDER = fs.readFileSync(path.join(ROOT, "ui", "webview", "render.ts"), "utf8");
const FEED = fs.readFileSync(path.join(ROOT, "ui", "webview", "feed.ts"), "utf8");
const EXT = fs.readFileSync(path.join(ROOT, "vscode-extension", "src", "extension.ts"), "utf8");

test("the chat pane writes the echo on the swatch click itself, before any kernel round-trip", () => {
  assert.ok(RENDER.includes('localStorage.setItem("romp:color-echo", JSON.stringify({ sid: id, bg, t: Date.now() }))'),
    "the `t` stamp makes re-picking the same colour still fire the storage event");
  assert.ok(RENDER.includes('if ((window as any).__rompShowStrip) vscodeApi?.postMessage({ type: "colorSync", sid: id, bg });'),
    "the host fan-out leg fires only under VS Code — the browser's storage event already covers its iframes");
  // the authoritative write still goes to the kernel, unchanged
  assert.ok(RENDER.includes('vscodeApi.postMessage({ type: "setSessionColor", id, bg })'));
});

test("the feed applies the echo to every copy it holds and re-renders at once", () => {
  assert.ok(FEED.includes('if (e.key !== "romp:color-echo" || !e.newValue) return;'), "the browser leg");
  assert.ok(FEED.includes('m.type === "colorSync" && typeof m.sid === "string" && typeof m.bg === "string"'), "the VS Code leg");
  assert.ok(FEED.includes("for (const a of asks) if (a.sid === sid) { a.color = color; hit = true; }"), "card borders + titles");
  assert.ok(FEED.includes("for (const s of sessionsMeta) if (s.sid === sid) { s.color = color; hit = true; }"), "the session-filter menu");
  assert.ok(FEED.includes("if (nm) sessionColors.set(nm, bg);"), "held-mail cards look colours up by name");
  assert.ok(FEED.includes("if (hit) render();"), "…then one immediate repaint, no kernel wait");
});

test("the VS Code host fans colorSync to its other panels, exactly like settingsSync", () => {
  assert.ok(EXT.includes('if (m.type === "colorSync") { broadcastColorSync(m, p.webview); return; }'));
  assert.match(EXT, /function broadcastColorSync[\s\S]{0,500}?w\.postMessage\(\{ type: "colorSync", sid: m\.sid, bg: m\.bg \}\)/);
});
