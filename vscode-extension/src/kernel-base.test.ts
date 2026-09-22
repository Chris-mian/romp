// A romp webview's direct kernel fetches (the pickers' /models, the gear's /palette + /version, the
// strip's /usage) run on the CLIENT. Connected to a remote machine, `http://127.0.0.1:<kernel port>`
// is the client's own loopback — no kernel there — so the base the webview is handed must come from
// `env.asExternalUri`, which opens the port forward and returns the local uri to it (a no-op on a local
// window). A declared portMapping alone did not carry the fetch over Remote-SSH (the kernel's /perf
// counters: zero GET /models across an hour of use, 2026-09-22). Executed against the pure resolver, and
// source pins holding every webview's HTML build to it.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { externalKernelBase, loopbackKernelBase, originOf } from "./kernel-base";

const SRC = fs.readFileSync(path.join(process.cwd(), "src", "extension.ts"), "utf8");
const uriOf = (s: string) => ({ toString: () => s });

test("a local window: asExternalUri is a no-op, and the base is the loopback origin unchanged", async () => {
  const seen: string[] = [];
  const base = await externalKernelBase(async (u) => { seen.push(u.toString()); return u; }, uriOf, "127.0.0.1", 29855);
  assert.equal(base, "http://127.0.0.1:29855");
  assert.deepEqual(seen, ["http://127.0.0.1:29855/"], "the kernel root is what gets resolved (asExternalUri wants a full http uri)");
});

test("a remote window: the forwarded local uri's ORIGIN is the base — no path, no trailing slash, the tunnel's port", async () => {
  const base = await externalKernelBase(async () => uriOf("http://localhost:53021/"), uriOf, "127.0.0.1", 29855);
  assert.equal(base, "http://localhost:53021");
  const cs = await externalKernelBase(async () => uriOf("https://abc-29855.example.test/some/prefix?x=1"), uriOf, "127.0.0.1", 29855);
  assert.equal(cs, "https://abc-29855.example.test", "a cloud host's https forward keeps scheme + host, drops path and query");
});

test("a resolver that throws or answers a non-http scheme falls back to the loopback base rather than failing the pane", async () => {
  const thrown = await externalKernelBase(async () => { throw new Error("no tunnel"); }, uriOf, "127.0.0.1", 29855);
  assert.equal(thrown, loopbackKernelBase("127.0.0.1", 29855));
  const odd = await externalKernelBase(async () => uriOf("vscode-remote://ssh/foo"), uriOf, "127.0.0.1", 29855);
  assert.equal(odd, "http://127.0.0.1:29855");
  assert.equal(originOf("not a url", "fb"), "fb");
});

test("every webview's HTML is built through setWebviewHtml, which resolves the base before it builds", () => {
  const direct = SRC.match(/\.webview\.html = build/g) || [];
  assert.equal(direct.length, 0, "no `webview.html = build…(webview)` left: a synchronous build cannot know the resolved base");
  const viaHelper = SRC.match(/setWebviewHtml\(/g) || [];
  // chat + feed + outline panels: first paint and the pipe's reconnect repaint (2 each = 6); the shared
  // view wiring: first paint + reconnect (2); refreshWebviewHtml: four surfaces (4); the definition (1)
  assert.ok(viaHelper.length >= 13, `expected the helper at every paint site, found ${viaHelper.length}`);
  assert.match(SRC, /function setWebviewHtml\(webview: vscode\.Webview, build: \(w: vscode\.Webview, kernelBase: string\) => string\)/);
  assert.match(SRC, /resolveKernelBase\(\)\.then\(\(kernelBase\) => \{ webview\.html = build\(webview, kernelBase\); \}/,
    "the resolved base is handed to the builder");
});

test("the builders take the resolved base; only resolveKernelBase names the loopback, through the injectable resolver", () => {
  // the outline pane's bundle makes no direct kernel fetch today, so its builder takes the base under the
  // unused-parameter spelling; the signature is still the shared one setWebviewHtml calls
  for (const b of ["buildHtml", "buildFeedHtml", "buildTimelineHtml", "buildFleetHtml"])
    assert.match(SRC, new RegExp(`function ${b}\\(webview: vscode\\.Webview, _?kernelBase: string\\): string \\{`), `${b} takes kernelBase`);
  assert.match(SRC, /function resolveKernelBase\(\): Promise<string> \{/);
  assert.match(SRC, /externalKernelBase\(\(u\) => vscode\.env\.asExternalUri\(u as vscode\.Uri\), \(s\) => vscode\.Uri\.parse\(s\), HOST, kernelPort\(\)\)/,
    "the extension hands VS Code's own asExternalUri and Uri.parse to the pure resolver");
  const literal = SRC.match(/`http:\/\/\$\{HOST\}:\$\{kernelPort\(\)\}`/g) || [];
  assert.equal(literal.length, 0, "no builder composes the loopback base itself any more");
  // the CSP still names the base the bundle will fetch (gear.test.ts and timeline-kernel-url.test.ts pin the token)
  for (const b of ["buildHtml", "buildFeedHtml", "buildTimelineHtml"]) {
    const at = SRC.indexOf(`function ${b}(`); const end = SRC.indexOf("\nfunction ", at + 1);
    assert.ok(SRC.slice(at, end).includes("connect-src ${kernelBase}"), `${b}'s CSP allows the resolved base`);
  }
});
