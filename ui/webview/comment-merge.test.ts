// The comment thread's RELAY exit (the user 2026-08-23 as 'merge'; rethought end-to-end by T145,
// the user 2026-08-28): send the discussion back into the parent session. The kernel executes the
// flow (tests/test_comment_merge.py + the injected-voice sweep); these are the UI's source pins.
// The T145 contract: the verb is Relay (Merge implied the thread closes — it doesn't); the arrival
// wears the machine-dressed attribution, never a plain user bubble; the WHOLE exchange goes; the
// thread stays talkable and carries a persistent sent-back marker at the relay's place in time.
// Wire ids (commentMerge / merging / merged) stay — persisted rows; display-only rename, the
// Accept-edits precedent.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const TYPES = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "comments.ts"), "utf8");
const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "bin", "romp-kernel"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("the Relay button rides the actions row, delegated, acknowledging before the round-trip", () => {
  assert.match(RENDER, /mg\.textContent = "Relay";/);
  assert.match(RENDER, /mg\.dataset\.act = "cmtmerge";/);   // the wire op keeps its name
  assert.match(RENDER, /cmtmerge: \(elx\) => \{/);
  assert.match(RENDER, /elx\.textContent = "Relaying…";/);
  assert.match(RENDER, /vscodeApi\?\.postMessage\(\{ type: "commentMerge", id: cur\.sid, tid: cur\.th\.tid \}\);/);
  assert.ok(!RENDER.includes('mg.textContent = "Merge"'), "the old verb is gone from the button");
});

test("relayed is a first-class status, and the thread STAYS TALKABLE", () => {
  assert.match(TYPES, /"merging" \| "merged"/);
  assert.match(RENDER, /: th!\.status === "merging" \? "Relaying back to the session…"/);
  assert.match(RENDER, /: th!\.status === "merged" \? nm \+ " \(relayed to the session\)"/);
  assert.match(RENDER, /t\.status === "open" \|\| t\.status === "resolved" \|\| t\.status === "merged"/);
  assert.match(RENDER, /th\.status === "resolved" \|\| th\.status === "merged" \? " resolved" : ""/);
  // the composer invites the next message instead of declaring the thread done
  assert.match(RENDER, /Reply to continue — the discussion so far was relayed to the session…/);
  // …and the kernel reopens a relayed thread on reply. A RESOLVED thread no longer does (the user
  // 2026-09-01: a thread they closed never reopens) — only the relayed status stays talkable (T223).
  assert.match(KERNEL, /_comment_update_if\(parent_sid, tid, \("open", "merged"\),\n\s*status="open"/);
  assert.match(KERNEL, /if prior == "merged":/);
});

test("the persistent sent-back marker sits at the relay's place in time and survives reopens", () => {
  assert.match(TYPES, /relayedT\?: number;/);
  assert.match(KERNEL, /"relayedT": th\.get\("relayedT"\) or 0,/, "the stamp rides the comments frame — store-backed, reopen-proof");
  assert.match(RENDER, /function cmtRelayedNote\(t: number\): HTMLElement/);
  assert.match(RENDER, /if \(!relayNoted && dayOpen != null && dayOpen > \(th\.relayedT \|\| 0\)\)/,
    "placed BY TIME: above it went back; below is the tail the next relay sends");
  assert.match(RENDER, /if \(!relayNoted\) list\.appendChild\(cmtRelayedNote\(th\.relayedT \|\| 0\)\);/, "relay at the tail still shows");
  assert.match(CSS, /\.cmt-relayed-note \{ text-align: center; font-size: 0\.82em; color: var\(--dim\); opacity: 0\.85; padding: 5px 0 3px; \}/);
});

test("kernel: whole exchange by default, machine-dressed arrival, tail-only re-relays", () => {
  assert.match(KERNEL, /"commentMerge"\)/);
  assert.match(KERNEL, /elif t == "commentMerge" and msg\.get\("tid"\):/);
  assert.match(KERNEL, /_comment_update_if\(parent_sid, tid, \("open", "resolved"\), status="merging"\)/);
  assert.match(KERNEL, /MERGE_BODY_CAP = 48000/, "the whole exchange goes (T145) — the cap is a pathological backstop, not a summary");
  // the arrival renders machine-attributed (the T130 class), never as the user's own typed bubble
  assert.match(KERNEL, /<!-- romp-injected --><!-- romp-tag: relay -->/);
  assert.ok(!KERNEL.includes('romp-system --><!-- romp-tag: relay'), "not romp-system: that routes to the status notice card, and a relay is conversation (lab-caught)");
  // a later relay sends only what the session hasn't seen — evidence-time floor, never wall clock
  assert.match(KERNEL, /floor = th\.get\("relayedT"\) or 0/);
  assert.match(KERNEL, /msgs = \[m for m in msgs if \(m\.get\("t"\) or 0\) > floor\]/);
  assert.match(KERNEL, /relayedT=max\(\(m\.get\("t"\) or 0\) for m in msgs\)/);
  assert.match(KERNEL, /nothing new to send back yet\./);
});
