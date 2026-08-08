// The yellow "warning" chip + warn-detail overlay (the user 2026-07-02): a judge that hits an anomaly
// on a goal (e.g. the distiller's SOURCE citation didn't come back — judge _node_warn) stamps it on the
// node; the kernel ships it as card `warns`; the card shows a yellow pill whose click opens an overlay
// telling, per warn, what happened and why it's unexpected — so pipeline misbehavior is followable from
// the card instead of buried in judge-errors.jsonl. Source pin.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("the warning chip is a button built once, riding the wrapping chip row", () => {
  assert.match(FEED, /const warnChip = el\("button", "fask-warnchip"\)/,
    "a BUTTON (focusable), not a span — it has a click action");
  assert.match(FEED, /warnChip\.textContent = "warning"/, "plain text label, no emoji/glyph");
  assert.match(FEED, /row2\.append\(idwrap, origin, fupBadge, dcBadge, nfBadge, intingBadge, intBadge, warnChip, waitOnBadge\)/);
  assert.match(FEED, /a\._warnChip = warnChip;/);
});

test("the click reads the card's CURRENT warns and opens the detail overlay (click-safe)", () => {
  // the handler is wired ONCE in build and reads _warnsData off the card element at click time, so the
  // incremental re-render (updateAskCard mutates in place) can never orphan the action mid-press.
  assert.match(FEED, /const ws = \(card as any\)\._warnsData as AskItem\["warns"\];/);
  assert.match(FEED, /if \(ws && ws\.length\) feedWarnModal\(/);
  assert.match(FEED, /warnChip\.onclick = \(ev\) => \{\s*\n\s*ev\.stopPropagation\(\);/,
    "stopPropagation so the chip click never also opens the card modal");
});

test("updateAskCard toggles the chip on it.warns and refreshes the data it reads", () => {
  assert.match(FEED, /a\._warnsData = it\.warns \|\| null;/);
  assert.match(FEED, /a\._warnChip\.style\.display = "";/);
  assert.match(FEED, /a\._warnChip\.textContent = it\.warns\.length > 1 \? `warning ×\$\{it\.warns\.length\}` : "warning";/,
    "multiple live warns show a count");
  assert.match(FEED, /it\.warns\[it\.warns\.length - 1\]\.msg \+ " — click for what happened and why"/,
    "hover says the latest msg + that detail is a click away");
});

test("the overlay lists each warn's kind/age and full detail", () => {
  assert.match(FEED, /function feedWarnModal\(cardTitle: string/);
  assert.match(FEED, /meta\.textContent = w\.kind \+ " · " \+ relAge\(/);
  assert.match(FEED, /body\.textContent = w\.detail \|\| w\.msg;/, "detail is the payload; msg is the floor");
  assert.match(FEED, /const onKey = \(e: KeyboardEvent\) => \{ if \(e\.key === "Escape"\) close\(\); \};/,
    "Esc closes, like feedConfirm");
});

test("the chip is a yellow pill and the overlay detail preserves its paragraphs", () => {
  assert.match(CSS, /\.fask-warnchip \{[^}]*color: #ffd166/);
  assert.match(CSS, /\.fask-warnchip \{[^}]*cursor: pointer/);
  assert.match(CSS, /\.fwarn-detail \{[^}]*white-space: pre-wrap/,
    "the what-happened/why-unexpected sections keep their blank-line structure");
});
