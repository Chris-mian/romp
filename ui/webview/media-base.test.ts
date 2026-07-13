// Media assets must resolve on BOTH hosts: the kernel serves /media on the web
// origin, but a VS Code webview's synthetic origin has no /media route — an
// absolute src there 404s, and the loader's broken-image icon SPINS on the
// rl-o animation (the user 2026-07-13). The rule these tests pin: JS-created
// asset URLs go through the media-base helpers (window.__rompMediaBase,
// injected by the extension host); CSS url()s are RELATIVE to the emitted
// dist stylesheet (../media/...), never absolute.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { mediaSrc } from "./media";

const ROOT = path.resolve(process.cwd(), "..");
const read = (...p: string[]) => fs.readFileSync(path.join(ROOT, ...p), "utf8");

test("mediaSrc defaults to the kernel's /media route", () => {
  delete (globalThis as any).window;
  assert.equal(mediaSrc("romp-swirl-o.svg"), "/media/romp-swirl-o.svg");
});

test("mediaSrc honors the host-injected __rompMediaBase (the VS Code webview)", () => {
  (globalThis as any).window = { __rompMediaBase: "https://file.vscode-resource.test/ext/media" };
  try {
    assert.equal(mediaSrc("romp-swirl-o.svg"), "https://file.vscode-resource.test/ext/media/romp-swirl-o.svg");
  } finally {
    delete (globalThis as any).window;
  }
});

test("render.ts creates no absolute /media srcs — every asset goes through mediaSrc", () => {
  const src = read("ui", "webview", "render.ts");
  assert.ok(!/["'`]\/media\//.test(src), "render.ts must route media URLs through mediaSrc()");
});

test("the timeline view routes every asset through its mediaUrl helper", () => {
  const src = read("ui", "romp-timeline-view.js");
  assert.ok(src.includes("__rompMediaBase"), "the view must honor the host-injected base");
  // The single allowed absolute literal is the helper's web default.
  const hits = src.match(/'\/media/g) || [];
  assert.equal(hits.length, 1, `expected only mediaUrl's default, found ${hits.length} absolute /media literals`);
});

test("stylesheet media url()s are relative to the emitted dist css, never absolute", () => {
  for (const f of ["styles.css", "feed.css", "fleet-pane.css", "timeline-pane.css"]) {
    const src = read("ui", "webview", f);
    assert.ok(!src.includes("url(/media/"), `${f}: absolute url(/media/...) breaks in the VS Code webview`);
  }
});

test("the extension host injects __rompMediaBase into all four webview surfaces", () => {
  const src = read("vscode-extension", "src", "extension.ts");
  const injections = src.match(/mediaBaseTag\(webview, n\)/g) || [];
  assert.equal(injections.length, 4, "chat, feed, timeline, and fleet builders must all inject the base");
  assert.ok(src.includes("window.__rompMediaBase="), "the injected tag must set window.__rompMediaBase");
});
