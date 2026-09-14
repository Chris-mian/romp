// The merged feed frame's clock anchor travels with the frame. federation.ts re-emits the merged feed on a
// view-order write (`storage` / VIEW_ORDER_EVENT → reorder → emitMergedFeed; view-order-wiring.test.ts pins
// the wiring), on every remote host's frame and on a detach — and a pane that runs its ages on the kernel's
// clock (fleet.ts, feed-age.ts liveNow) sets that clock from the frame it is handed. Anchored on the EMIT, a
// re-emit after a quiet hour would take every age back by that hour (a tab drag in another pane, or an
// attached kernel's 60 s repost, moving "1m ago" back to "<1m ago"). The anchor is the (now, nowAt) PAIR of
// the local frame's wire arrival, so a re-emit anchors exactly as the arrival did. The real manager, a stub
// window (emissions) and a stub clock; synthetic hosts and ids only.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { mergeHostFeeds, FederationManager } from "./federation";
import { liveNow } from "./feed-age";

const FED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "federation.ts"), "utf8");
const card = (i: number, extra: Record<string, unknown> = {}) => ({ itemId: "TESTSID:g" + i, sid: "TESTSID", text: "card " + i, t: 1000 + i, ...extra });

function withFeedManager(fn: (fm: FederationManager, emitted: any[], clock: { ms: number }) => void): void {
  const emitted: any[] = [];
  const clock = { ms: 5_000_000 };
  const g: any = globalThis;
  const hadWindow = "window" in g, prevWindow = g.window;
  const hadLS = "localStorage" in g, prevLS = g.localStorage;
  const realNow = Date.now;
  g.window = { dispatchEvent: (ev: any) => { if (ev && ev.data) emitted.push(ev.data); } };
  g.localStorage = { getItem: () => null, setItem: () => {} };
  Date.now = () => clock.ms;
  try {
    fn(new FederationManager(), emitted, clock);
  } finally {
    Date.now = realNow;
    if (hadWindow) g.window = prevWindow; else delete g.window;
    if (hadLS) g.localStorage = prevLS; else delete g.localStorage;
  }
}
const pair = (m: any) => [m.now, m.nowAt];

test("the merged frame's clock anchor is the local frame's (now, nowAt) wire arrival: a re-emit after a quiet hour carries the same pair", () => {
  withFeedManager((fm, emitted, clock) => {
    const T = 1_000_000;
    fm.inbound("", { type: "feed", asks: [card(0)], now: T, buildId: 1 });
    assert.equal(emitted.length, 1);
    assert.deepEqual(pair(emitted[0]), [T, 5_000_000], "stamped with the moment the frame arrived");
    clock.ms += 3_600_000;                       // a quiet hour on the wire
    (fm as any).emitMergedFeed();                // what a view-order write runs (reorder), with no new frame
    assert.equal(emitted.length, 2);
    assert.deepEqual(pair(emitted[1]), [T, 5_000_000], "the re-emit anchors exactly as the arrival did");
    assert.equal(liveNow(emitted[1].now, emitted[1].nowAt, clock.ms), T + 3600, "so the pane's live clock keeps the hour");
    assert.equal(liveNow(emitted[1].now, clock.ms, clock.ms), T, "anchored on the emit it would lose it — the bug");
    assert.deepEqual(emitted[1].asks.map((a: any) => a.itemId), ["TESTSID:g0"], "the same board, unchanged");
  });
});

test("a remote host's frame never moves the local anchor; the next local frame re-anchors on its own arrival", () => {
  withFeedManager((fm, emitted, clock) => {
    const T = 1_000_000;
    fm.inbound("", { type: "feed", asks: [card(0)], now: T, buildId: 1 });
    clock.ms += 3_600_000;
    fm.inbound("TESTHOST", { type: "feed", asks: [], now: T + 7200, buildId: 9 });   // an attached kernel's 60 s repost, its clock 2 h ahead
    assert.equal(emitted.length, 2);
    assert.deepEqual(pair(emitted[1]), [T, 5_000_000], "the local pair, untouched by the remote's clock or arrival");
    assert.equal(liveNow(emitted[1].now, emitted[1].nowAt, clock.ms), T + 3600);
    clock.ms += 60_000;
    fm.inbound("", { type: "feed", now: T + 3660, buildId: 2, asks: [card(0, { text: "changed" })] });
    assert.equal(emitted.length, 3);
    assert.deepEqual(pair(emitted[2]), [T + 3660, clock.ms], "new local information: the frame's clock, and when it arrived");
    assert.equal(emitted[2].asks[0].text, "changed");
    clock.ms += 30_000;
    fm.inbound("TESTHOST", { type: "feed", asks: [], now: T + 7300, buildId: 10 });
    assert.deepEqual(pair(emitted[3]), [T + 3660, clock.ms - 30_000], "…and the remote's next repost leaves it there");
  });
});

test("with no local frame yet the pair comes from the newest REMOTE arrival — both halves from one host; no arrivals known → no nowAt", () => {
  withFeedManager((fm, emitted, clock) => {
    fm.inbound("HOSTA", { type: "feed", asks: [], now: 500 });
    clock.ms += 10_000;
    fm.inbound("HOSTB", { type: "feed", asks: [], now: 900 });
    assert.deepEqual(pair(emitted[emitted.length - 1]), [900, 5_010_000], "HOSTB arrived last: its clock with its arrival");
  });
  const perHost = { HOSTA: { type: "feed", now: 500 }, HOSTB: { type: "feed", now: 900 } };
  const older = mergeHostFeeds(perHost, ["", "HOSTA", "HOSTB"], [], [], { HOSTA: 9, HOSTB: 5 });
  assert.deepEqual(pair(older), [500, 9], "the newest ARRIVAL wins, not the largest clock");
  const local = mergeHostFeeds({ "": { type: "feed", now: 7 }, HOSTA: { type: "feed", now: 500 } }, ["", "HOSTA"], [], [], { "": 3, HOSTA: 9 });
  assert.deepEqual(pair(local), [7, 3], "a local frame is the anchor whenever it exists, however old its arrival");
  const bare = mergeHostFeeds({ "": { type: "feed", now: 7 } }, [""]);
  assert.equal(bare.now, 7);
  assert.equal("nowAt" in bare, false, "a caller with no wire (no arrivals) sets none: the pane anchors on its own arrival");
  const none = mergeHostFeeds({ HOSTA: { type: "feed", asks: [] } }, ["", "HOSTA"], [], [], { HOSTA: 9 });
  assert.equal("now" in none, false, "a frame with no clock (an older kernel) anchors nothing");
});

test("federation stamps the arrival beside the frame on the wire path, drops it with the host, and the merge is handed it", () => {
  assert.match(FED, /private perHostFeedAt: Record<string, number> = \{\};/);
  assert.match(FED, /this\.perHostFeed\[host\] = m;\n\s*this\.perHostFeedAt\[host\] = Date\.now\(\);/, "a frame's arrival");
  assert.match(FED, /delete this\.perHostFeed\[host\];\n\s*delete this\.perHostFeedAt\[host\];/, "a detach forgets both");
  assert.match(FED, /mergeHostFeeds\(this\.perHostFeed, this\.hostSeq, this\.view\(\), dead, this\.perHostFeedAt, this\.hostsRead\)/, "every emit carries the arrivals");   // the sixth argument: whether the host list has been read (T404 round nine)
  assert.equal((FED.match(/perHostFeedAt\[host\] = Date\.now\(\)/g) || []).length, 1, "stamped where the frame comes off the wire and nowhere else — never on an emit");
});
