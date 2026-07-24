// Per-paragraph brief ages (the user 2026-07-24). A MULTI-item decision brief writes one paragraph
// per owed item in order (judge BLOCK_BRIEF_SYS 2026-07-21), and the kernel ships briefParts —
// [{id, since}] in that same order, each `since` the ask's own block-event time — so the card stamps
// every paragraph with a live "Nm ago" of ITS OWN ask. The incident this serves: a card re-displayed
// a brief whose go-ahead the user had given two hours earlier; a per-paragraph age makes exactly that
// staleness visible at a glance. Source-pinned like the sibling stall-section test: feed.ts builds
// the card imperatively, so the wiring is asserted over the source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");
const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "kernel", "kernel.py"), "utf8");
const JUDGE = fs.readFileSync(path.resolve(process.cwd(), "..", "kernel", "judge.py"), "utf8");

test("the AskItem declares briefParts in the kernel's shape", () => {
  assert.match(FEED, /briefParts\?: \{ id\?: string; since: number \}\[\] \| null;/);
});

test("the kernel ships briefParts beside the decision brief", () => {
  assert.ok(KERNEL.includes('"briefParts": nodes[nid].get("briefParts") or None'),
    "build_feed's ask payload carries the per-paragraph stamps");
});

test("the judge stores one {id, since} per owed item, in order, multi-item only", () => {
  assert.ok(JUDGE.includes('nodes[top]["briefParts"] = ([{"id": d["id"], "since": _block_since(d)} for d in blkd]'),
    "written from the SAME blkd list the owed paragraphs were ordered by");
  assert.ok(JUDGE.includes("if (not proc_only and len(blkd) > 1) else None)"),
    "single-item briefs store nothing — the card header's age is that stamp (the user's rule)");
});

test("the renderer gates on blocked + multi-item + an exact paragraph-count match", () => {
  assert.ok(FEED.includes("if (distillShown && dBlocked && !dCompleted && bp && bp.length > 1)"),
    "blocked briefs only, never a completed takeaway; single ask keeps the header age");
  assert.ok(FEED.includes("if (paras.length === bp.length)"),
    "the model may merge paragraphs — a missing stamp beats a wrong one");
  assert.match(FEED, /split\(\/\\n\\s\*\\n\/\)/, "paragraphs split on blank lines, the brief's own separator");
});

test("each paragraph wears its own live age chip", () => {
  assert.ok(FEED.includes('el("span", "fask-para-age")'));
  assert.ok(FEED.includes("relAge(nowS - (bp[i].since || nowS))"),
    "the ask's OWN block-event age, via the shared relAge vocabulary");
});

test("the chip inherits the brief's font size — dimness is the only differentiation", () => {
  const rule = CSS.match(/\.fask-para-age \{[^}]*\}/);
  assert.ok(rule, "the chip has a css rule");
  assert.ok(!/font-size/.test(rule![0]),
    "no new font-size on this surface (the consistent-fonts rule); var(--dim) does the work");
  assert.match(rule![0], /var\(--dim\)/);
});
