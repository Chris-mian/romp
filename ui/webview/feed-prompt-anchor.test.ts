// Prompt-intent jumps resolve BY ID via promptAnchorUuid — the user's MINTING message (a user turn) — not
// the old anchorUuid (a work/reply turn the chat's kind-guard refuses) + nearest-time heuristic. Kernel emits
// it per node (92e23ff); the feed wires it into the card title, the modal node text (goMsg — see
// feed-modal-zones.test.ts), and the group modal title; the WORK zones (mark/time) keep anchorUuid. This is
// the proper fix for the title-click honest-fail regression. Source-assertion (no jsdom for the feed renderer).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");

test("AskTreeNode carries promptAnchorUuid (the user's minting-turn uuid) alongside anchorUuid (work)", () => {
  assert.match(FEED, /promptAnchorUuid\?: string \| null;/);
});

test("the card title resolves prompt-intent by promptAnchorUuid; the work/origin title keeps anchorUuid", () => {
  // cardAnchorUuid stays the WORK uuid; a separate titleUuid picks the prompt uuid only for the "prompt"
  // title. (The why-line that used to reuse cardAnchorUuid is gone — the card auto-line is plain text now.)
  assert.match(FEED, /const cardAnchorUuid = rootNode\?\.anchorUuid \?\? null;/);
  assert.match(FEED, /let titleUuid = titleAnchor === "prompt" \? \(rootNode\?\.promptAnchorUuid \?\? null\) : cardAnchorUuid;/);
  assert.match(FEED, /anchor: titleAnchor, anchorUuid: titleUuid/);
});

test("the group modal title resolves by the first member's promptAnchorUuid", () => {
  assert.match(FEED, /const gm0Prompt = gm0\.tree\?\.find\(\(n\) => n\.id === gm0\.itemId\)\?\.promptAnchorUuid \?\? null;/);
  assert.match(FEED, /itemId: gm0\.itemId, sid: grp\.sid, t: grp\.t, anchor: "prompt", anchorUuid: gm0Prompt/);
});
