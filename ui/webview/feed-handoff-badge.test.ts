// Sender-side handoff provenance on the feed (the user 2026-08-24): a TOP-LEVEL "↪ delegated to
// <peer>" tracking node wore its provenance as the card TITLE, arrow and all. The kernel now titles
// the card with the WORK and ships the delegation as `handoffTo` — rendered on the origin slot as
// the exact mirror of the recipient's "↪ from <peer>" badge: identity color, quiet host: prefix for
// a federated recipient, click opens the recipient session, STACKING after an ↪ from badge (origin
// and handoffTo are different facts about one card). Source pins, the feed-panel idiom; the
// kernel-side truth table lives in tests/test_handoff_card_title.py.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8") + fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "card-sections.ts"), "utf8");   // the badge lives in the shared builder since round two of the box content PR (stateBadges); feed.ts draws it through the module
const BLK = SRC.slice(SRC.indexOf("const hasOrigin = !!(it.origin && it.origin.peer), hasHandoff"),
                      SRC.indexOf("if (it.recheck && spinCaption"));   // the one provenance anchor (stateBadges), up to the next badge

test("the badge is additive on the type — a payload without it renders exactly as before", () => {
  assert.match(SRC, /handoffTo\?: \{ peer: string; peerSid: string; peerHost\?: string; color\?: \{ bg: string; fg: string \} \| null \} \| null;/);
});

test("the title is the kernel-shipped text verbatim — the de-arrowing lives kernel-side", () => {
  // setLinkedText writes it.text as-is and only wraps its PR references in anchors (pr-links.ts);
  // the visible text is still the kernel's, character for character
  assert.match(SRC, /setLinkedText\(a\._title, it\.text, prRepoOf\(it\.sid\)\);/,
    "no client-side munging: one place (kernel _handoff_card_fields) owns the derivation");
});

test("the badge mirrors ↪ from: identity rendering, recipient click, stacking after origin", () => {
  assert.ok(BLK.length > 0, "the handoffTo render block exists");
  // stacks after an ↪ from badge rather than replacing it — same rule the tracked slot pinned
  assert.match(BLK, /if \(hasOrigin\) \{[\s\S]*?had = true;[\s\S]*?if \(hasHandoff\) \{/, "stacks after the origin badge in ONE anchor: the two are different facts about one card, in that order");
  assert.match(BLK, /const og = el\("a", "fask-origin" \+ \(hasOrigin && it\.origin!\.live === false \? " fask-origin-absorbed" : ""\)\);/, "the absorbed class dims the whole badge, as the card always drew it (the verifier's round two)");
  assert.match(BLK, /pre\.textContent = \(had \? " · " : ""\) \+ "↪ delegated to ";/, "the separator after an origin");
  // identity rendering matches every other session name (quiet host: prefix included)
  assert.match(BLK, /peer\.replaceChildren\(\.\.\.hostPartsNodes\(h\.peerHost, h\.peer\)\);/);
  assert.match(BLK, /if \(h\.color && h\.color\.bg\) peer\.style\.color = h\.color\.bg;/);
  // the click opens the RECIPIENT session — symmetric with the origin badge's click
  assert.match(BLK, /if \(!had\) \{ og\.title = "delegated to " \+ h\.peer \+ "; their result checks this card off · click opens the session"; og\.dataset\.act = "sec-open-session"; og\.dataset\.sid = h\.peerSid; \}/, "with no sender the anchor itself opens the recipient"); assert.match(BLK, /peer\.dataset\.act = "sec-open-session"; peer\.dataset\.sid = h\.peerSid;/, "and the recipient's name always does");   // delegated through data-act (round three of the box content PR: rebuilt nodes carry no handler of their own; sectionActs routes the act)
});
