// Pins the /clear fork-follow rule (customTitleOf + liveTranscriptOf in
// chat.ts): after /clear, Claude forks to a NEW transcript uuid with the SAME
// customTitle; a tab's live transcript is the newest sibling carrying its
// name. Must stay identical to the daemon's grouping rule
// (romp-summarize-backfill custom_title()/sessions()).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { customTitleOf, liveTranscriptOf, Session } from "./chat";

let mt = 1_700_000_000_000;
function writeTr(dir: string, base: string, title: string | null, extra = ""): string {
  const file = path.join(dir, `${base}.jsonl`);
  const lines = [];
  if (title) lines.push(JSON.stringify({ type: "custom-title", customTitle: title, sessionId: base }));
  lines.push(JSON.stringify({ type: "user", uuid: "u1", parentUuid: null, message: { role: "user", content: "hi" + extra } }));
  fs.writeFileSync(file, lines.join("\n") + "\n");
  mt += 5000; // strictly increasing mtimes, in write order
  fs.utimesSync(file, mt / 1000, mt / 1000);
  return file;
}

function sess(file: string, name: string): Session {
  return { id: path.basename(file, ".jsonl"), file, name, color: null, lastSig: "", lastSince: null, lastState: "", lastWorking: false };
}

test("customTitleOf reads the custom-title head line; null without one", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "romp-fork-"));
  const titled = writeTr(dir, "aaaa", "web_app");
  const untitled = writeTr(dir, "bbbb", null);
  assert.equal(customTitleOf(titled), "web_app");
  assert.equal(customTitleOf(untitled), null);
  assert.equal(customTitleOf(path.join(dir, "missing.jsonl")), null);
});

test("customTitleOf cache invalidates when the file changes", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "romp-fork-"));
  const f = writeTr(dir, "cccc", null);
  assert.equal(customTitleOf(f), null);
  fs.writeFileSync(f, JSON.stringify({ type: "custom-title", customTitle: "late_name" }) + "\n");
  mt += 5000;
  fs.utimesSync(f, mt / 1000, mt / 1000);
  assert.equal(customTitleOf(f), "late_name");
});

test("liveTranscriptOf follows the newest same-title fork only", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "romp-fork-"));
  const anchor = writeTr(dir, "anchor00", "web_app");
  const otherSession = writeTr(dir, "other000", "feed_design");   // newer, wrong title
  const fork1 = writeTr(dir, "fork0001", "web_app");              // /clear fork
  const fork2 = writeTr(dir, "fork0002", "web_app");              // a second /clear
  const s = sess(anchor, "web_app");
  assert.equal(liveTranscriptOf(s), fork2, "newest matching sibling wins");
  assert.notEqual(liveTranscriptOf(s), otherSession);
  // already on the newest fork: stays put
  assert.equal(liveTranscriptOf(sess(fork2, "web_app")), fork2);
  // an OLDER same-title sibling never wins (no re-point backwards)
  assert.equal(liveTranscriptOf(sess(fork2, "web_app")), fork2);
  void fork1;
});

test("liveTranscriptOf stays pinned when nothing matches", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "romp-fork-"));
  const anchor = writeTr(dir, "anchor11", "web_app");
  writeTr(dir, "noise111", null);                                 // newer but untitled
  assert.equal(liveTranscriptOf(sess(anchor, "web_app")), anchor);
  // fallback-named tab (uuid prefix, no romp identity): never re-points
  const bare = writeTr(dir, "bare2222", null);
  writeTr(dir, "titled33", "someone_else");
  assert.equal(liveTranscriptOf(sess(bare, "bare2222".slice(0, 8))), bare);
});

test("liveTranscriptOf survives a vanished current file (any titled sibling wins)", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "romp-fork-"));
  const anchor = writeTr(dir, "anchor22", "web_app");
  const fork = writeTr(dir, "fork2222", "web_app");
  fs.unlinkSync(anchor);
  assert.equal(liveTranscriptOf(sess(anchor, "web_app")), fork);
});
