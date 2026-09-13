// TODAY's rail markers read how long ago in the user's words (T406, the user 2026-09-13; the vocabulary itself is
// time-marker.test.ts). Source pins on the parts a refactor could quietly break: one writer for the render and the
// minute tick, the previous row stored at render so the tick compares against the same reference, ONE page-level
// timer re-armed past each clock-minute boundary (never a timer per marker), the hidden-tab and hidden-window
// catch-ups, the sticky stamp reading the same label and hiding incoming stamps under its own (two-line) band, and
// the slot styling: the whole 56px gutter, "ago" on its own line, the transcript untouched (the marker is absolute).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("one writer paints a marker for the render and for the tick, against the previous row the render stored", () => {
  assert.match(RENDER, /m\.dataset\.prev = prevEpoch == null \? "" : String\(prevEpoch\);/, "the chain's reference rides the marker");
  assert.match(RENDER, /function timeMarker\(epoch: number, prevEpoch: number \| null\): HTMLElement \{[\s\S]*?paintMarker\(m, epoch, prevEpoch, Date\.now\(\)\);\n  return m;\n\}/);
  assert.match(RENDER, /function paintMarker\(m: HTMLElement, epoch: number, prevEpoch: number \| null, now: number\): void \{\n  const \{ text, day, hm \} = markerLabel\(epoch, prevEpoch, now\);\n  m\.dataset\.hm = hm;\n  const rel = relativeLabel\(epoch, now\);/);
  // shown where the label CHANGES from the previous timed row's (the same-minute rule at the label's grain); the tooltip is the exact HH:MM, only on a shown stamp
  assert.match(RENDER, /const shown = rel !== \(prevEpoch == null \? "" : relativeLabel\(prevEpoch, now\)\);/);
  assert.match(RENDER, /m\.classList\.add\("rel"\);\n\s*m\.textContent = shown \? relativeLines\(rel\) : "";\n\s*if \(shown\) m\.title = hm; else m\.removeAttribute\("title"\);/);
  // any other day: exactly the old rail, class and tooltip off (a today marker handed back after midnight loses both)
  assert.match(RENDER, /m\.classList\.remove\("rel"\); m\.removeAttribute\("title"\);\n\s*m\.textContent = text \? \(day \? hm : text\) : "";/);
  // the tick repaints today's markers only, from the stored moment and reference, then the sticky's usual repaint
  assert.match(RENDER, /for \(const m of Array\.from\(root\.querySelectorAll<HTMLElement>\("\.time-marker\.rel"\)\)\)\n\s*paintMarker\(m, Number\(m\.dataset\.epoch\), m\.dataset\.prev \? Number\(m\.dataset\.prev\) : null, now\);\n\s*scheduleRailSticky\(\);/);
});

test("one page-level minute timer, re-armed past each clock-minute boundary; hidden tabs and windows catch up when shown", () => {
  const arms = RENDER.match(/setTimeout\(railMinuteTick, 60000 - \(Date\.now\(\) % 60000\) \+ 50\);/g) || [];
  assert.equal(arms.length, 2, "armed once at load and re-armed once per fire, nowhere else");
  assert.match(RENDER, /function railMinuteTick\(\): void \{\n  if \(!document\.hidden && activeId\) refreshRelativeMarkers\(views\.get\(activeId\)\?\.el\);\n  setTimeout\(railMinuteTick/);
  assert.doesNotMatch(RENDER, /setInterval\([^)]*railMinuteTick|setInterval\([^)]*refreshRelativeMarkers/, "no interval: a boundary-aligned timeout, so labels turn with the clock");
  assert.doesNotMatch(RENDER, /setTimeout\([^;]*paintMarker/, "never a timer per marker");
  assert.match(RENDER, /document\.addEventListener\("visibilitychange", \(\) => \{ if \(!document\.hidden && activeId\) refreshRelativeMarkers\(views\.get\(activeId\)\?\.el\); \}\);/);
  assert.match(RENDER, /vv\.el\.style\.display = vid === activeId \? "" : "none";\n  if \(!reshow\) refreshRelativeMarkers\(v\.el\);/, "a switch refreshes the tab it shows");
});

test("the sticky stamp reads today's label too, and hides incoming stamps under its own band", () => {
  assert.match(RENDER, /const rel = relativeLabel\(Number\(marker!\.dataset\.epoch\), Date\.now\(\)\);/);
  assert.match(RENDER, /stamp\.classList\.toggle\("rel", !!rel\);\n\s*stamp\.textContent = rel \? relativeLines\(rel\) : hm;/);
  assert.match(RENDER, /const stampH = stamp\.getBoundingClientRect\(\)\.height \|\| g\.height;/, "measured after the text and display are set");
  assert.match(RENDER, /m\.style\.visibility = top < slotLine \+ stampH \? "hidden" : "";/);
  // the notch tooltip keeps the clock time (markerLabel's text), whatever the rail shows
  assert.match(RENDER, /const when = epoch != null \? markerLabel\(epoch, null, Date\.now\(\)\)\.text : "";/);
});

test("the slot is the whole gutter, its right edge unmoved; a plural-hours label wraps before 'ago'; the marker stays out of flow", () => {
  const thread = CSS.match(/\.thread \{[^}]*padding: 0 24px 0 (\d+)px;/);
  assert.ok(thread, "the thread's gutter");
  const slot = CSS.match(/\.time-marker \{\n  position: absolute; top: 13px; left: -(\d+)px; width: (\d+)px;/);
  assert.ok(slot, "the marker's slot");
  assert.equal(slot[2], thread[1], "the slot spans the gutter (56px): '59 min ago' is 55.9px and '1 hour ago' 51.9px at the default font");
  assert.equal(Number(slot[2]) - Number(slot[1]), 3, "the right edge stays 3px short of the dot, where it always was");
  assert.match(CSS, /\.time-marker \{[^}]*white-space: nowrap;/, "the clock time never wraps");
  assert.match(CSS, /\.time-marker\.rel \{ white-space: pre-line; \}/, "a plural-hours label breaks at the newline relativeLines puts before 'ago'");
});
