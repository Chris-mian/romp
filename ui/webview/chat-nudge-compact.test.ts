// A romp-injected NUDGE bubble is disclosed progressively (the user 2026-07-17: default compact, click
// to expand — the standing UI principle, see CLAUDE.md Design): the bubble defaults to a one-line GIST
// with a caret, and clicking it swaps in the full markdown text. The open state is KEYED (nudge:<uuid>)
// so an expanded nudge survives the chat's re-renders, exactly like tool folds. A nudge whose whole text
// IS the gist gets no caret and no click affordance (never a dead-end fake expander). Source pins.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("a romp bubble renders a one-line gist by default, full text behind a keyed click", () => {
  const fn = RENDER.slice(RENDER.indexOf('} else if (romp && ev.md) {'), RENDER.indexOf('} else if (ev.md) {'));
  // gist = first line, truncated at a word boundary like the romp system notice's
  assert.match(fn, /const gist = firstLine\.length > 90 \? firstLine\.slice\(0, 88\)\.replace\(\/\\s\+\\S\*\$\/, ""\) \+ "…" : firstLine;/);
  // the romp markers are stripped before the gist is cut (they'd read as literal comment text)
  assert.match(fn, /ev\.md\.replace\(\/<!--\[\\s\\S\]\*\?-->\/g, ""\)\.trim\(\);/);
  // collapsible ONLY when there is more than the gist; the caret marks it
  assert.match(fn, /const more = collapseWs\(raw\) !== collapseWs\(gist\);/);
  assert.match(fn, /if \(more\) \{ const c = el\("span", "nudge-caret"\); c\.textContent = "▸"; gistEl\.appendChild\(c\); \}/);
  // keyed open-state → an expanded nudge survives re-renders (the openFolds idiom)
  assert.match(fn, /const nkey = ev\.uuid \? "nudge:" \+ ev\.uuid : undefined;/);
  assert.match(fn, /applyFold\(bubble, "expanded", nkey\);/);
  // the toggle rides the stable document.body delegate (click-safe across re-renders, CLAUDE.md) —
  // never a per-render bubble listener
  assert.match(fn, /bubble\.dataset\.act = "nudgetoggle";/);
  assert.match(RENDER, /nudgetoggle: \(el\) => \{/);
  assert.match(RENDER, /rememberFold\(el, "expanded", el\.dataset\.nkey \|\| undefined\);/);
});

test("the CSS swap: gist shown collapsed, full text shown expanded — never both", () => {
  assert.match(CSS, /\.romp-bubble \.nudge-full \{ display: none; \}/);
  assert.match(CSS, /\.romp-bubble\.expanded \.nudge-full \{ display: block; \}/);
  assert.match(CSS, /\.romp-bubble\.expanded \.nudge-gist \{ display: none; \}/);
  assert.match(CSS, /\.romp-bubble\.nudge-collapsible \{ cursor: pointer; \}/);
});

test("the progressive-disclosure principle is recorded in CLAUDE.md's Design section", () => {
  const doc = fs.readFileSync(path.resolve(process.cwd(), "..", "CLAUDE.md"), "utf8");
  assert.match(doc, /### Progressive disclosure is the UI's organizing principle/);
});
