// The card-age provenance tooltip (the user 2026-07-27): the header's "Nm ago" stamps the card's
// NEWEST event — a completed card's age is when it was marked done — so hovering it must tell where
// the thread CAME from: started when, each sub-item with the time it landed, and what the visible
// stamp itself marks. EXECUTES ./provenance directly; the feed wiring (titles set beside every
// ageEl/_time write) is source-pinned below.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { provenanceTitle, provenanceGroupTitle, rootStart, type ProvItem, type ProvFmt } from "./provenance";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");

// deterministic formatters: the real relAge/clockHM/logPhrase live in feed.ts (pinned there); this
// module owns only the story's structure
const F: ProvFmt = {
  rel: (s) => Math.round(s / 60) + "m ago",
  clock: (t) => "@" + t,
  phrase: (r) => "[" + r.kind + "]",
};
const NOW = 10_000;

function item(over: Partial<ProvItem> = {}): ProvItem {
  return {
    itemId: "root", t: 9_400, column: "completed",
    tree: [
      { id: "root", text: "ship the notes-api", status: "done", t: 1_000, last: 9_400 },
      { id: "s1", text: "write the parser", status: "done", t: 1_600, last: 5_000, mt: 5_200 },
      { id: "s2", text: "ask about the schema", status: "question", t: 2_200, last: 7_000, mt: 7_000 },
      { id: "s3", text: "docs pass", status: "open", t: 8_800, last: 8_800 },
    ],
    ...over,
  };
}

test("the story: started at the root's mint, each sub at ITS time, the stamp explained last", () => {
  const lines = provenanceTitle(item(), NOW, F).split("\n");
  assert.equal(lines[0], "started 150m ago · @1000", "line 1 = the root's mint time");
  assert.equal(lines[1], "✓ write the parser — 80m ago · @5200", "a resolved sub stamps where it RESOLVED (mt)");
  assert.equal(lines[2], "⏸ ask about the schema — 50m ago · @7000");
  assert.equal(lines[3], "· docs pass — 20m ago · @8800", "an open sub stamps its mint (nothing resolved yet)");
  assert.equal(lines[4], "marked done 10m ago · @9400", "the visible age is named for what it marks");
});

test("the final line matches the column: blocked / last update", () => {
  assert.match(provenanceTitle(item({ column: "needs_input" }), NOW, F), /\nblocked 10m ago · @9400$/);
  assert.match(provenanceTitle(item({ column: "working" }), NOW, F), /\nlast update 10m ago · @9400$/);
});

test("the root's own verdict rows ride between start and subs, in the feed's outcome words", () => {
  const it = item();
  it.tree[0].log = [{ kind: "block", src: "romp", at: 3_000 }, { kind: "unblock", src: "romp", evT: 4_000 }];
  const lines = provenanceTitle(it, NOW, F).split("\n");
  assert.equal(lines[1], "[block] 117m ago · @3000");
  assert.equal(lines[2], "[unblock] 100m ago · @4000", "evT is the time-nav fallback when `at` is absent");
  assert.equal(lines[3], "✓ write the parser — 80m ago · @5200", "subs follow the root's events");
});

test("cleared subs stay out; a huge tree caps at 8 with an honest remainder", () => {
  const it = item();
  it.tree[1].cleared = true;
  assert.ok(!provenanceTitle(it, NOW, F).includes("write the parser"), "a cleared sub is not provenance");
  const big = item({
    tree: [{ id: "root", text: "r", status: "done", t: 1_000, last: 9_000 } as any].concat(
      Array.from({ length: 11 }, (_, i) => ({ id: "n" + i, text: "sub " + i, status: "open", t: 2_000 + i, last: 2_000 + i } as any))),
  });
  const lines = provenanceTitle(big, NOW, F).split("\n");
  assert.equal(lines.length, 1 + 8 + 1 + 1, "start + 8 subs + remainder + stamp line");
  assert.equal(lines[9], "…and 3 more", "no silent truncation");
});

test("rootStart falls back: earliest tree mint without a root row, the card's t on an empty tree", () => {
  assert.equal(rootStart(item()), 1_000);
  assert.equal(rootStart(item({ itemId: "elsewhere" })), 1_000, "no root row → earliest mint");
  assert.equal(rootStart(item({ tree: [] })), 9_400, "provisional cards have no tree at all");
});

test("a group's story is the fold: earliest member start, the member count, the group stamp", () => {
  const lines = provenanceGroupTitle([5_000, 3_000, 7_000], 9_000, NOW, F).split("\n");
  assert.equal(lines[0], "started 117m ago · @3000");
  assert.equal(lines[1], "3 cards from one prompt");
  assert.equal(lines[2], "last update 17m ago · @9000");
});

test("the feed wires the tooltip beside every age write — card, group card, both modal headers", () => {
  assert.match(FEED, /a\._time\.title = provenanceTitle\(it, hostNow, PROV_FMT\);/);
  assert.match(FEED, /a\._time\.title = provenanceGroupTitle\(g\.members\.map\(rootStart\), g\.t, hostNow, PROV_FMT\);/);
  assert.match(FEED, /ageEl\.title = provenanceTitle\(it, hostNow, PROV_FMT\);/);
  assert.match(FEED, /ageEl\.title = provenanceGroupTitle\(grp\.members\.map\(rootStart\), grp\.t, hostNow, PROV_FMT\);/);
  // …with the same vocabulary the card itself renders in
  assert.match(FEED, /const PROV_FMT: ProvFmt = \{ rel: relAge, clock: clockHM, phrase: logPhrase \};/);
});
