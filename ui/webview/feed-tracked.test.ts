// Tracked delegation on the feed (the user 2026-08-24): a report-back handoff reads as ONE card
// homed under the DELEGATOR. The kernel ships two additive keys — delegTracked (the primary card's
// recipient identities) and satellite (the recipient-side copy) — and the feed renders them with
// machinery it already has: the primary names its recipients on the origin slot with the board's
// own live dot; the satellite drops off the DEFAULT board only, with the session filter as the
// one-click path back (nothing runs in secret, the 2026-08-11 rule). Source pins, the feed-panel
// idiom; the kernel-side truth table lives in tests/test_tracked_delegation.py.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8") + fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "card-sections.ts"), "utf8");   // the badges moved to card-sections.ts (round two of the box content PR: one builder for the card and the Needs you row)

test("the default board hides satellites; the session filter is the one-click path back", () => {
  // inside viewFiltered, so the hover-freeze churn badges count exactly what the board shows
  assert.match(SRC, /list\.filter\(\(a\) => a\.sid === feedOnlySid\) : list\.filter\(\(a\) => !a\.satellite\)/,
    "hidden ONLY on the unfiltered board — picking the worker's session still shows its copy");
});

test("the primary names its recipients with the board's own live dot, STACKING after any ↪ from", () => {
  const BLK = SRC.slice(SRC.indexOf("if (hasTracked) {"),
                        SRC.indexOf("if (it.recheck && spinCaption"));   // the tracked half of the one provenance anchor (stateBadges), up to the next badge
  // an else-if hid a MIDDLEMAN's tracked handoff behind its own ↪ from badge (review 2026-08-24):
  // origin and delegTracked are different facts about one card, so they stack on the slot
  assert.match(SRC, /if \(hasOrigin\) \{[\s\S]*?if \(hasHandoff\) \{[\s\S]*?if \(hasTracked\) \{/, "stacks after the ↪ from badge and the handoff badge, in ONE anchor, in that order (stateBadges)");
  assert.match(BLK, /pre\.textContent = \(had \? " · " : ""\) \+ "↪ delegated to ";/, "the separator after an origin or a handoff");

  assert.match(BLK, /peer\.replaceChildren\(\.\.\.hostPartsNodes\(d\.host, d\.name\)\);/,
    "identity rendering matches every other session name (quiet host: prefix included)");
  assert.match(SRC, /workDot: \(peer, name\) => setWorkDot\(peer, dotFor\(name\)\),/, "the feed hands the builder its live dot"); assert.match(BLK, /env\.workDot\?\.\(peer, d\.name\);/,
    "the recipient's LIVE state rides the card — the dot language the board already speaks");
  assert.match(BLK, /peer\.dataset\.act = "sec-open-session"; peer\.dataset\.sid = d\.sid;/, "each recipient span opens ITS session — ↪ from keeps its own click (delegated)"); assert.match(BLK, /if \(!had\) \{ og\.title = "a tracked handoff: the work runs with " \+ ds\.map\(\(d\) => d\.name\)\.join\(", "\) \+ " and reports back to this card"; \}/, "with no sender the anchor names the work; the clicks stay the recipients'");
});

test("both keys are additive on the type — an untracked payload renders exactly as before", () => {
  assert.match(SRC, /satellite\?: boolean \| null;/);
  assert.match(SRC, /delegTracked\?: \{ name: string; host\?: string; sid: string; color\?: \{ bg: string; fg: string \} \| null \}\[\] \| null;/);
});
