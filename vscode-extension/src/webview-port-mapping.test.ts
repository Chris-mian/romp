// Every romp webview declares a port mapping for the kernel's port, so a bundle's direct kernel
// fetch (the model pickers' /models, the gear's /palette and /version, the strip's /usage) reaches the
// kernel when VS Code is connected to a REMOTE machine. A webview's script runs on the client: its
// fetch of http://127.0.0.1:<kernel port> goes to the client's own loopback, where no kernel listens,
// unless VS Code redirects it — and VS Code redirects a localhost/127.0.0.1 request only for a port the
// webview's options map (WebviewPortMappingManager.getRedirect: no matching `portMapping` entry → no
// redirect, no tunnel). With none declared, every such fetch failed silently under Remote-SSH: the
// pickers opened with no rows while the browser, served by the kernel itself, listed every family (the
// user 2026-09-22; the kernel's own /perf counters showed zero GET /models across an hour of use). The
// API docs recommend declaring the mapping even when both ports are the same — that is exactly the
// remote case. Source pins (no VS Code host in the test runner): each webview's options carry it.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.join(process.cwd(), "src", "extension.ts"), "utf8");

test("kernelPortMapping maps the kernel port to itself: the webview asks for the port the kernel listens on, and VS Code tunnels it to the remote", () => {
  assert.match(SRC, /function kernelPortMapping\(\): vscode\.WebviewPortMapping\[\] \{/, "the one helper every webview's options read");
  assert.match(SRC, /return \[\{ webviewPort: kernelPort\(\), extensionHostPort: kernelPort\(\) \}\];/,
    "webviewPort and extensionHostPort are both the kernel's port — the redirect is for the REMOTE hop, not a port change");
});

test("every webview's options declare the kernel port mapping — the three panels at creation and every options reassignment", () => {
  // creation: the fourth argument's options object (chat, feed, outline), pinned beside localResourceRoots
  const creations = SRC.match(/createWebviewPanel\([\s\S]*?localResourceRoots: \[[^\n]*\],\n\s*portMapping: kernelPortMapping\(\),/g) || [];
  assert.equal(creations.length, 3, "chat, feed and outline panels are created with the mapping");
  // reassignment: `webview.options = {...}` replaces the whole options object, so a mapping set at creation
  // is lost unless the reassignment carries it too (wirePanel / wireFeedPanel / wireFleetPanel, and the
  // shared WebviewView wiring for the timeline + outline views)
  const reassignments = SRC.match(/\.webview\.options = \{\n\s*enableScripts: true,\n\s*localResourceRoots: \[[^\n]*\],\n\s*portMapping: kernelPortMapping\(\),\n\s*\};/g) || [];
  assert.equal(reassignments.length, 4, "wirePanel, wireFeedPanel, wireFleetPanel and the view wiring all re-declare it");
  // and no options object anywhere in the file is left without it
  const withRoots = SRC.match(/localResourceRoots: \[/g) || [];
  const withMapping = SRC.match(/portMapping: kernelPortMapping\(\)/g) || [];
  assert.equal(withMapping.length, withRoots.length, "every options object that names localResourceRoots also names the mapping");
});
