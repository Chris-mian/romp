// When a collapsed tool group ("▸ 3 Edits, 2 Reads") is EXPANDED, its children indent onto their own
// rail, 24px right of the main session rail — leaving two disjoint vertical lines. Bracket them back
// together with a top + bottom horizontal connector in the SAME rail colour so the line reads as one
// continuous path that detours through the children (the user 2026-06-22). Source-level pin (no jsdom).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("the LAST expanded child is tagged so the bottom rail-elbow can hang off it", () => {
  assert.match(RENDER, /if \(i === end\) child\.classList\.add\("tg-last"\)/);
});

test("two horizontal connectors bracket the children onto the main rail, in the rail colour", () => {
  // TOP arm: off the expanded summary line's bottom, reaching from the main rail (x≈10.5) to the child rail
  assert.match(CSS, /\.turn-toolgroup\.expanded::after \{[^}]*left: 10\.5px;[^}]*bottom: 0;[^}]*width: 26px;[^}]*height: 2px/);
  // BOTTOM arm: off the last child (indented 24px → left:-13.5px lands it back on the main rail at x≈10.5)
  assert.match(CSS, /\.tg-child\.tg-last::after \{[^}]*left: -13\.5px;[^}]*bottom: 0;[^}]*width: 26px;[^}]*height: 2px/);
  // both arms are the SAME colour + opacity as the main vertical rail (.turn::before)
  assert.match(CSS, /\.turn::before \{[^}]*background: var\(--active-accent, var\(--rail\)\);[^}]*opacity: 0\.7/);
  assert.match(CSS, /\.turn-toolgroup\.expanded::after \{[^}]*background: var\(--active-accent, var\(--rail\)\);[^}]*opacity: 0\.7/);
  assert.match(CSS, /\.tg-child\.tg-last::after \{[^}]*background: var\(--active-accent, var\(--rail\)\);[^}]*opacity: 0\.7/);
  // and stay out of the way of clicks
  assert.match(CSS, /\.turn-toolgroup\.expanded::after \{[^}]*pointer-events: none/);
  assert.match(CSS, /\.tg-child\.tg-last::after \{[^}]*pointer-events: none/);
});
