// Postal cards ALWAYS lead with a one-line summary and expand to the full message on click (the user
// 2026-06-16). Before, incoming mail showed the Haiku caption (full body only as a hover tooltip) while
// outgoing mail showed the whole body — inconsistent. Now both render a summary (the caption, or the
// first line for sent mail with no caption) that opens inline on click. The chat renderer has no jsdom
// harness, so — like render-postal-time.test.ts — pin it at the source level.
//
// 2026-07-25 (the user, from a real sent card): three more guarantees pinned here —
//   1. the expand is KEYED (openFolds), because the unkeyed toggle was silently re-collapsed by the
//      next kernel push ("it expands for like a second and then something collapses it");
//   2. expanded shows the full message ALONE — the summary line was repeating the same words right
//      above the body;
//   3. the collapsed fallback is clamped by CSS to two full lines, not pre-truncated at 100 chars,
//      which parked the "…" mid-line and wasted the rest of the second line.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("a postal summary is the caption, or the first non-empty line of the body when there's none", () => {
  assert.match(RENDER, /function postalServiceSummary/);
  assert.match(RENDER, /const cap = ev\.summary && ev\.summary\.trim\(\)/);
  assert.match(RENDER, /\.split\("\\n"\)\.map\(\(s\) => s\.trim\(\)\)\.find\(Boolean\)/);
  // no hard pre-truncation — the CSS two-line clamp cuts at the box edge instead
  assert.doesNotMatch(RENDER, /slice\(0, 99\)/, "the 100-char pre-truncation must be gone");
  assert.match(CSS, /\.postal-service-summary-text \{[^}]*-webkit-line-clamp: 2/);
});

test("both directions render the summary + a click-to-expand full body (no hover tooltip)", () => {
  // expandable when the full body differs from the summary — same path for incoming and outgoing
  assert.match(RENDER, /const expandable = .*collapseWs\(fullText\) !== collapseWs\(summaryText\)/);
  assert.match(RENDER, /body\.classList\.add\("postal-service-expandable"\)/);
  assert.doesNotMatch(RENDER, /body\.title = ev\.body/, "the old hover-tooltip full body must be gone");
  assert.doesNotMatch(RENDER, /caption \|\| ev\.body/, "no longer 'caption else whole body'");
});

test("the expand is KEYED so a kernel push can't silently re-collapse it (the user 2026-07-25)", () => {
  assert.match(RENDER, /const pkey = "postal:" \+ \(ev\.mid \|\| ev\.uuid \|\| ""\)/);
  assert.match(RENDER, /applyFold\(body, "expanded", pkey\)/);
  assert.match(RENDER, /rememberFold\(body, "expanded", pkey\)/);
  // no bare unkeyed toggle left inside the postal renderer (unkeyed = lost on the next re-render)
  const start = RENDER.indexOf("function renderPostalService");
  const end = RENDER.indexOf("function renderTeammate");
  assert.doesNotMatch(RENDER.slice(start, end), /classList\.toggle\("expanded"\)/,
    "the postal card must not hand-roll its expand state");
});

test("the postal expand box is styled (full body hidden until expanded; summary is clickable)", () => {
  assert.match(CSS, /\.postal-service-full \{[^}]*display: none/);
  assert.match(CSS, /\.postal-service-expandable\.expanded \.postal-service-full \{[^}]*display: block/);
  assert.match(CSS, /\.postal-service-expandable \.postal-service-summary \{[^}]*cursor: pointer/);
});

test("expanded shows the full message ALONE — the summary text yields to its caret (the user 2026-07-25)", () => {
  assert.match(CSS, /\.postal-service-expandable\.expanded \.postal-service-summary-text \{[^}]*display: none/);
});
