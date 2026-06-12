// Unit tests for the postal message-format contract (postal-spec.ts):
// join-marker extraction, send-tool detection, the timeline index, and
// hydratePostal's all-or-nothing swap.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { extractMsgIds, isSendTool, loadPostalIndex, hydratePostal, TIMELINE_REL } from "./postal-spec";
import type { ChatEvent } from "./transcript";

const COLORS = {
  byId: (id: string) => (id === "sid-feed" ? { bg: "#112233", fg: "#ffffff" } : null),
  byName: (name: string) => (name === "feed_design" ? { bg: "#112233", fg: "#ffffff" } : null),
};

let mtimeBump = 1_600_000_000_000; // loadPostalIndex caches on mtimeMs — give every fixture a distinct one

function writeTimeline(lines: any[]): string {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "romp-postal-test-"));
  const file = path.join(stateDir, ...TIMELINE_REL);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, lines.map((l) => JSON.stringify(l)).join("\n") + "\n");
  mtimeBump += 1000;
  fs.utimesSync(file, mtimeBump / 1000, mtimeBump / 1000);
  return stateDir;
}

const SENT = {
  t: 1781050000, ev: "sent", id: "m1", from: "feed_design", from_id: "sid-feed",
  to_id: "sid-me", body: "ASK: bump the alpha", park: false,
};

test("extractMsgIds finds every join marker", () => {
  const text = "prose <!-- romp-msg-id: aaa.111 --> more <!--romp-msg-id:bbb.222-->";
  assert.deepEqual(extractMsgIds(text), ["aaa.111", "bbb.222"]);
  assert.deepEqual(extractMsgIds(""), []);
  assert.deepEqual(extractMsgIds("no markers here"), []);
});

test("isSendTool matches plain and MCP-namespaced names only", () => {
  assert.equal(isSendTool("send_message"), true);
  assert.equal(isSendTool("mcp__romp-postal__send_message"), true);
  assert.equal(isSendTool("resend_message"), false);
  assert.equal(isSendTool("send_message_v2"), false);
  assert.equal(isSendTool(""), false);
});

test("loadPostalIndex: only ev=sent lines, junk tolerated, last write wins", () => {
  const stateDir = writeTimeline([
    SENT,
    { t: 1, ev: "exec", id: "m1" },                       // non-sent: ignored
    "not json at all" as any,
    { t: 1781050100, ev: "sent", id: "m1", from: "feed_design", from_id: "sid-feed", to_id: "sid-me", body: "ASK: bump it MORE", park: true },
  ]);
  const map = loadPostalIndex(stateDir);
  assert.equal(map.size, 1);
  const rec = map.get("m1")!;
  assert.equal(rec.body, "ASK: bump it MORE");
  assert.equal(rec.park, true);
});

test("hydratePostal: incoming drain text becomes a postal-in card", () => {
  const stateDir = writeTimeline([SENT]);
  const events: ChatEvent[] = [
    { kind: "user", md: "Stop hook feedback: \u{1F4EC} … <!-- romp-msg-id: m1 -->" },
  ];
  const out = hydratePostal(events, stateDir, COLORS);
  assert.equal(out.length, 1);
  const card = out[0] as Extract<ChatEvent, { kind: "postal" }>;
  assert.equal(card.kind, "postal");
  assert.equal(card.direction, "in");
  assert.equal(card.peer, "feed_design");
  assert.equal(card.body, "ASK: bump the alpha");
  assert.deepEqual(card.color, { bg: "#112233", fg: "#ffffff" });
});

test("hydratePostal: all-or-nothing — one unresolved id leaves the event raw", () => {
  const stateDir = writeTimeline([SENT]);
  const raw: ChatEvent = {
    kind: "user",
    md: "two messages <!-- romp-msg-id: m1 --> <!-- romp-msg-id: missing -->",
  };
  const out = hydratePostal([raw], stateDir, COLORS);
  assert.deepEqual(out, [raw], "partial resolution must pass the event through unchanged");
});

test("hydratePostal: a Bash `romp --mail send` becomes a postal-out card", () => {
  const stateDir = writeTimeline([]);
  const mk = (command: string, output: string, isError = false): ChatEvent =>
    ({ kind: "tool", name: "Bash", desc: "", input: command, output, isError } as any);
  const dq = mk('romp --mail send feed_design "FYI: shipped it — see \\"notes\\""', "[romp mail] delivered to 'feed_design'");
  const sq = mk("romp --mail send feed_design 'one quoted line'", "[romp mail] 'feed_design' is offline — parked as a handoff; it'll be delivered on revival (ignored if it never returns).");
  const failed = mk('romp --mail send feed_design "hello"', "[romp mail] no session named 'feed_design'", true);
  const ambiguous = mk('romp --mail send feed_design "hi" && echo done', "[romp mail] delivered to 'feed_design'");
  const plain = mk("ls -la", "total 0");
  const out = hydratePostal([dq, sq, failed, ambiguous, plain], stateDir, COLORS);
  const a = out[0] as Extract<ChatEvent, { kind: "postal" }>;
  assert.equal(a.kind, "postal");
  assert.equal(a.direction, "out");
  assert.equal(a.peer, "feed_design");
  assert.equal(a.body, 'FYI: shipped it — see "notes"');
  assert.equal(a.status, "delivered");
  assert.deepEqual(a.color, { bg: "#112233", fg: "#ffffff" });
  const b = out[1] as Extract<ChatEvent, { kind: "postal" }>;
  assert.equal(b.body, "one quoted line");
  assert.equal(b.status, "parked");
  assert.equal(out[2].kind, "tool", "a failed send stays a visible Bash row");
  assert.equal(out[3].kind, "tool", "trailing && makes the body ambiguous — passes through");
  assert.equal(out[4].kind, "tool");
});

test("hydratePostal: send_message tool call becomes a postal-out card", () => {
  const stateDir = writeTimeline([]);
  const send: ChatEvent = {
    kind: "tool", name: "mcp__romp-postal__send_message", desc: "",
    input: JSON.stringify({ to: "feed_design", body: "FYI: shipped it" }),
    output: "delivered", isError: false,
  };
  const parked: ChatEvent = { ...send, output: "parked for dead session" } as any;
  const broken: ChatEvent = { ...send, input: "not json" } as any;
  const out = hydratePostal([send, parked, broken], stateDir, COLORS);
  const a = out[0] as Extract<ChatEvent, { kind: "postal" }>;
  assert.equal(a.kind, "postal");
  assert.equal(a.direction, "out");
  assert.equal(a.peer, "feed_design");
  assert.equal(a.status, "delivered");
  const b = out[1] as Extract<ChatEvent, { kind: "postal" }>;
  assert.equal(b.status, "parked");
  assert.equal(out[2].kind, "tool", "unparseable input passes through as the raw tool card");
});
