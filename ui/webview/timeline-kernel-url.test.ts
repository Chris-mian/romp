// The timeline pane's lane model picker reads the kernel's /models like every other picker — but in
// the VS Code webview that fetch has to leave the webview's synthetic origin and carry the serve token:
// the browser is served BY the kernel (a bare "/models" is same-origin and rides the romp_token cookie),
// while a webview's "/models" resolves against vscode-webview://… (no such route), carries no cookie, and
// is not even allowed by a CSP with no connect-src. The chat and feed bundles solved this on 2026-07-13
// (media.ts kernelUrl + the host-injected window.__rompKernelBase/__rompKernelToken); the timeline view's
// loader was written against the web page alone, so its menu opened EMPTY in VS Code while the browser's
// listed every family (the user 2026-09-22). These pins hold the view and the timeline builder to the same
// contract the chat, feed and gear already keep (gear.test.ts pins the feed builder's).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { createRequire } from "node:module";

const requireCjs = createRequire(__filename);
const ROOT = path.resolve(process.cwd(), "..");
const VIEW_PATH = path.join(ROOT, "ui", "romp-timeline-view.js");
const VIEW = fs.readFileSync(VIEW_PATH, "utf8");
const EXT = fs.readFileSync(path.join(ROOT, "vscode-extension", "src", "extension.ts"), "utf8");

test("the lane picker's /models read goes through the view's kernelUrl helper, never a bare relative URL", () => {
  assert.ok(!/fetch\(\s*'\/models'/.test(VIEW), "a bare fetch('/models') resolves against the webview's own origin in VS Code");
  assert.match(VIEW, /fetch\(kernelUrl\('\/models'\)/, "the loader must route through kernelUrl()");
  assert.match(VIEW, /function kernelUrl\(path\)/, "the view needs its own helper: it is a CJS file inlined into the bundle AND injected raw into the web page, so it cannot import media.ts");
  assert.ok(VIEW.includes("__rompKernelBase"), "the helper must honor the host-injected kernel base");
  assert.ok(VIEW.includes("__rompKernelToken"), "the helper must carry the host-injected serve token — the kernel gates every request, loopback included");
});

test("executed: kernelUrl defaults to the web page's same-origin path, and prefixes the base + ?token= under a VS Code host", async () => {
  const realFetch = (globalThis as any).fetch;
  const realWindow = (globalThis as any).window;
  const { loadModelChoices } = requireCjs(VIEW_PATH);
  const urls: string[] = [];
  (globalThis as any).fetch = async (u: string) => { urls.push(String(u)); return { ok: true, status: 200, json: async () => ({ models: [], efforts: [] }) }; };
  try {
    delete (globalThis as any).window;                       // the web page: no host globals
    await loadModelChoices();
    assert.deepEqual(urls, ["/models"], "the browser keeps the same-origin path (its cookie rides)");
    urls.length = 0;
    (globalThis as any).window = { __rompKernelBase: "http://127.0.0.1:29855", __rompKernelToken: "t0k/en" };
    await loadModelChoices();
    assert.deepEqual(urls, ["http://127.0.0.1:29855/models?token=t0k%2Fen"], "the webview leaves its origin with the token, URL-encoded");
  } finally {
    (globalThis as any).fetch = realFetch;
    if (realWindow === undefined) delete (globalThis as any).window; else (globalThis as any).window = realWindow;
  }
});

test("the VS Code timeline builder injects the kernel base + serve token and lets its CSP reach the kernel", () => {
  const at = EXT.indexOf("function buildTimelineHtml(");
  const end = EXT.indexOf("\nfunction ", at + 1);
  assert.ok(at > 0 && end > at, "buildTimelineHtml moved — re-anchor");
  const fn = EXT.slice(at, end);
  assert.ok(fn.includes("window.__rompKernelBase="), "the timeline builder must inject the kernel base (chat and feed do)");
  assert.ok(fn.includes("window.__rompKernelToken="), "the timeline builder must inject the serve token");
  assert.ok(fn.includes("connect-src ${kernelBase}"), "the timeline webview CSP must allow the kernel origin, or the fetch is blocked before it leaves");
  // the globals must be set BEFORE the bundle runs its page-load loadModelChoices()
  assert.ok(fn.indexOf("window.__rompKernelBase=") < fn.indexOf('src="${js}"'), "inject the globals ahead of the bundle script");
});
