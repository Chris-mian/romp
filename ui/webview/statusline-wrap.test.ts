// A narrow pane must WRAP the statusline controls (dir, branch, mode/model/effort/fast badges, ctx
// battery) onto extra rows, not clip them (the user 2026-08-10, whose controls vanished one by one as
// the pane shrank: the no-wrap flex row shrank the dir/branch to nothing and pushed the rest past the
// right edge). The footer is flex: 0 0 auto, so extra rows grow it instead of overflowing.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("the statusline wraps instead of clipping when the pane narrows", () => {
  assert.match(CSS, /\.statusline \{[^}]*flex-wrap: wrap/);
});

test("the meta-badge cluster wraps between badges, keeping each badge whole", () => {
  const rule = CSS.match(/\.spinner-meta \{[^}]*\}/)?.[0] || "";
  assert.match(rule, /flex-wrap: wrap/);
  // badges must not break INSIDE their own label — the container wraps, the badge doesn't
  assert.match(rule, /white-space: nowrap/);
});
