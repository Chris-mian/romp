// Links in the chat must follow on click (the user 2026-06-25). On the web dashboard the old handler only
// ever postMessage'd the host an openLink — but the kernel has no openLink handler, so a link click did
// nothing on the web dashboard. Now the click handler splits by host: a web origin (http/https) opens the
// link in the viewer's own browser via window.open; a VS Code webview (vscode-webview: origin) still routes
// to the host extension's openExternal. The chat renderer has no jsdom harness, so pin it at the source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");

// isolate the global anchor-click handler
const HANDLER = (RENDER.match(/closest\?\.\("a\[href\]"\)[\s\S]*?\}, true\);/) || [""])[0];

test("the chat has a global a[href] click handler", () => {
  assert.ok(HANDLER, "found the anchor-click handler");
  assert.match(HANDLER, /e\.preventDefault\(\)/);
});

test("web dashboard (http/https origin) opens the link in the viewer's browser", () => {
  assert.match(HANDLER, /location\.protocol === "http:" \|\| location\.protocol === "https:"/);
  assert.match(HANDLER, /window\.open\(href, "_blank", "noopener,noreferrer"\)/);
});

test("VS Code webview still routes the link to the host (openExternal)", () => {
  assert.match(HANDLER, /vscodeApi\.postMessage\(\{ type: "openLink", href \}\)/);
});

test("the web path is checked before the vscode path (web origin wins)", () => {
  const web = HANDLER.indexOf("window.open(href");
  const code = HANDLER.indexOf('type: "openLink"');
  assert.ok(web > -1 && code > -1 && web < code, "window.open branch precedes the openLink branch");
});
