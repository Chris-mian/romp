// The pending guard for the per-session view flags (flag-pending.ts): a frame built before a click cannot flip the copy
// back; the echo clears the expectation, three disagreeing frames yield, a refusal drops it. Executed on the pure module;
// the render.ts sites are pinned at the source (no DOM harness runs the frame handlers). Synthetic sids only.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { notePendingFlag, dropPendingFlag, applyFrameFlags, PENDING_FLAG_MAX_AGE, SESSION_FLAGS, type PendingFlags } from "./flag-pending";

const SID = "11111111-2222-4333-8444-000000000601";
const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");

test("no expectation: the frame's flags land, absent ones are left alone, and what changed is reported", () => {
  const pending: PendingFlags = new Map();
  const s: { notify?: boolean; hideFromFeed?: boolean; postalServiceOff?: boolean } = { notify: false, hideFromFeed: true };
  assert.deepEqual(applyFrameFlags(s, { notify: true, postalServiceOff: false, status: {} }, pending, SID), ["notify", "postalServiceOff"]);
  assert.deepEqual(s, { notify: true, hideFromFeed: true, postalServiceOff: false });
  assert.deepEqual(applyFrameFlags(s, { notify: true }, pending, SID), [], "the same value again changes nothing");
  assert.deepEqual(applyFrameFlags(s, { notify: "yes" }, pending, SID), [], "a non-boolean is not a flag");
});

test("a click's expectation holds off a frame built before it, and the echo clears it", () => {
  const pending: PendingFlags = new Map();
  const s = { notify: false };
  notePendingFlag(pending, SID, "notify", true); s.notify = true;   // what setSessionFlag does: the copy first, the note beside it
  assert.deepEqual(applyFrameFlags(s, { notify: false }, pending, SID), [], "the stale frame (built before the click) does not flip the bell back");
  assert.equal(s.notify, true);
  assert.equal(pending.get(SID)!.get("notify")!.age, 1);
  assert.deepEqual(applyFrameFlags(s, { notify: true }, pending, SID), [], "the echo agrees: nothing changes on the copy…");
  assert.equal(pending.size, 0, "…and the expectation is spent");
  assert.deepEqual(applyFrameFlags(s, { notify: false }, pending, SID), ["notify"], "after the echo a later frame is the kernel's word again");
});

test("three disagreeing frames yield to the kernel's view: the expectation had no ack and the store of record wins", () => {
  const pending: PendingFlags = new Map();
  const s = { hideFromFeed: false };
  notePendingFlag(pending, SID, "hideFromFeed", true); s.hideFromFeed = true;
  for (let i = 0; i < PENDING_FLAG_MAX_AGE; i++) {
    assert.deepEqual(applyFrameFlags(s, { hideFromFeed: false }, pending, SID), [], "held off, frame " + (i + 1));
  }
  assert.deepEqual(applyFrameFlags(s, { hideFromFeed: false }, pending, SID), ["hideFromFeed"], "the fourth disagreeing frame lands");
  assert.equal(s.hideFromFeed, false);
  assert.equal(pending.size, 0);
});

test("expectations are per flag and per session; a refusal drops one, a departure drops the session's", () => {
  const pending: PendingFlags = new Map();
  const OTHER = "11111111-2222-4333-8444-000000000602";
  notePendingFlag(pending, SID, "notify", true); notePendingFlag(pending, SID, "postalServiceOff", true); notePendingFlag(pending, OTHER, "notify", false);
  const s = { notify: true, postalServiceOff: true, hideFromFeed: false };
  assert.deepEqual(applyFrameFlags(s, { notify: false, postalServiceOff: false, hideFromFeed: true }, pending, SID), ["hideFromFeed"], "only the flag with no expectation follows the frame");
  dropPendingFlag(pending, SID, "notify");
  assert.deepEqual(applyFrameFlags(s, { notify: false }, pending, SID), ["notify"], "refused: the kernel's value lands at once");
  assert.ok(pending.get(SID)!.has("postalServiceOff") && pending.get(OTHER)!.has("notify"), "the others stand");
  dropPendingFlag(pending, SID);
  assert.equal(pending.has(SID), false); assert.equal(pending.has(OTHER), true);
  assert.deepEqual([...SESSION_FLAGS], ["notify", "hideFromFeed", "postalServiceOff"]);
});

test("render.ts: the click notes its expectation, both frame roads apply the flags under the guard, the refusal drops it", () => {
  assert.match(RENDER, /import \{ notePendingFlag, dropPendingFlag, applyFrameFlags, type PendingFlags, type SessionFlag \} from "\.\/flag-pending";/);
  assert.match(RENDER, /const pendingFlags: PendingFlags = new Map\(\);[^\n]*\nfunction setSessionFlag/, "the store, declared beside its writer");
  assert.match(RENDER, /function setSessionFlag\(id: string, flag: "hideFromFeed" \| "postalServiceOff" \| "notify", value: boolean\) \{\n\s*const s = sessions\.get\(id\);\n\s*if \(s\) s\[flag\] = value;[^\n]*\n\s*notePendingFlag\(pendingFlags, id, flag, value\);/, "the click");
  assert.match(RENDER, /if \(tm\) applyMetaToSession\(s, tm, pendingTabMeta\.get\(msg\.id\)\);\n\s*applyFrameFlags\(s, msg, pendingFlags, msg\.id\);/, "the full session frame, once the copy is built from it and the pushed meta re-applied");
  assert.match(RENDER, /if \(msg\.status\) s\.status = msg\.status;\n[^\n]*\n[^\n]*\n\s*applyFrameFlags\(s, msg, pendingFlags, msg\.id\);/, "the chatTail (both wires carry the flags)");
  assert.doesNotMatch(RENDER, /for \(const f of \["notify", "hideFromFeed", "postalServiceOff"\] as const\)/, "no unguarded copy of the tail's flags remains");
  assert.match(RENDER, /if \(m\.gesture === "flag" && typeof m\.sid === "string" && typeof m\.flag === "string" && m\.sid && m\.flag\) \{[\s\S]*?dropPendingFlag\(pendingFlags, m\.sid, m\.flag as SessionFlag\);/, "the refusal ends the expectation on THIS event");
});
