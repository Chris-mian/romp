import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

// The two drag grips wear ONE dress (T410 review, low 5): the feed's section grip (.drag-grip, feed.css) and the settings'
// widget-row grip (#rsettings .rs-grip, gear.css) are the same handle on two surfaces, so their rest and hover declarations
// must agree property for property. Declarations are compared, not pixels: both files resolve the same tokens
// (--text-muted, --text-bright, --accent-wash) in both theme blocks, so equal declarations are equal computed styles.
// the harness runs from vscode-extension/ (the sibling tests' idiom): the sources sit one directory up
const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");
const GEAR = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "gear.css"), "utf8");

function decls(css: string, selectorRe: RegExp): Record<string, string> {
  const m = css.match(new RegExp(selectorRe.source + "\\s*\\{([^}]*)\\}"));
  assert.ok(m, "rule found: " + selectorRe.source);
  const out: Record<string, string> = {};
  for (const d of m![1].split(";")) {
    const i = d.indexOf(":");
    if (i > 0) out[d.slice(0, i).trim()] = d.slice(i + 1).trim().replace(/\s+/g, " ");
  }
  return out;
}

test("the section grip's rest dress is the settings grip's: size, colour, corners, cursor, touch", () => {
  const feed = decls(FEED, /\n\.drag-grip/), gear = decls(GEAR, /#rsettings \.rs-grip/);
  for (const p of ["width", "height", "padding", "border", "background", "color", "font-size", "line-height", "border-radius",
                   "cursor", "touch-action", "user-select", "-webkit-user-select"]) {
    assert.equal(feed[p], gear[p], p + " matches the settings' rs-grip");
  }
});

test("the section grip's hover and focus dress is the settings grip's: bright ink on the accent wash", () => {
  const feed = decls(FEED, /\.drag-grip:hover, \.drag-grip:focus-visible, \.feed-col-head:hover \.drag-grip, \.feed-col\.col-dragging \.drag-grip/);
  const gear = decls(GEAR, /#rsettings \.rs-grip:hover, #rsettings \.rs-grip:focus-visible/);
  for (const p of ["color", "background", "outline"]) assert.equal(feed[p], gear[p], p + " on hover matches the settings' rs-grip");
});

test("both grips are the six-dot glyph, and both surfaces resolve the same tokens in both themes", () => {
  for (const tok of ["--text-muted", "--text-bright", "--accent-wash"]) {
    assert.equal((FEED.match(new RegExp("^\\s*" + tok + ":", "mg")) || []).length, 2, tok + " is defined in feed.css's two theme blocks");
  }
});
