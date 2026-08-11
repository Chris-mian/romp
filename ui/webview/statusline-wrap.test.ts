// A narrow pane must WRAP the statusline controls (dir, branch, mode/model/effort/fast badges, ctx
// battery) onto extra rows, not clip them (the user 2026-08-10, whose controls vanished one by one as
// the pane shrank: the no-wrap flex row shrank the dir/branch to nothing and pushed the rest past the
// right edge). The footer is flex: 0 0 auto, so extra rows grow it instead of overflowing.
// And the wrapped rows stay CLUSTERED ON THE RIGHT (the user 2026-08-10, on a phone): the right-side
// controls live in ONE .sl-right container that carries the auto margin and right-justifies its own
// wrapped rows — flat statusline children would restart each extra row at the left edge.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");

test("the statusline wraps instead of clipping when the pane narrows", () => {
  assert.match(CSS, /\.statusline \{[^}]*flex-wrap: wrap/);
});

test("the meta-badge cluster wraps between badges, keeping each badge whole", () => {
  const rule = CSS.match(/\.spinner-meta \{[^}]*\}/)?.[0] || "";
  assert.match(rule, /flex-wrap: wrap/);
  // badges must not break INSIDE their own label — the container wraps, the badge doesn't
  assert.match(rule, /white-space: nowrap/);
  // its own wrapped badge rows hug the right edge too
  assert.match(rule, /justify-content: flex-end/);
});

test("the right-side controls are one container whose wrapped rows hug the right edge", () => {
  const rule = CSS.match(/\.sl-right \{[^}]*\}/)?.[0] || "";
  assert.match(rule, /margin-left: auto/);        // the container, not .status-dir, anchors the cluster
  assert.match(rule, /flex-wrap: wrap/);
  assert.match(rule, /justify-content: flex-end/);
  const dir = CSS.match(/\.status-dir \{[^}]*\}/)?.[0] || "";
  assert.doesNotMatch(dir, /margin-left: auto/);  // the old flat-anchor must not come back
});

test("render.ts groups dir, branch, badges and ctx battery into .sl-right", () => {
  assert.match(RENDER, /el\("span", "sl-right"\)/);
  assert.match(RENDER, /right\.appendChild\(dir\)/);
  assert.match(RENDER, /right\.appendChild\(meta\)/);
  assert.match(RENDER, /right\.appendChild\(bar\)/);
  assert.match(RENDER, /sl\.appendChild\(right\)/);
});
