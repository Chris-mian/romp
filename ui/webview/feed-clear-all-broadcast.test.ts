// The board-wide Clear all reaches every attached kernel (T286, the user 2026-09-09): the feed footer's Clear all
// carries no session id and used to fall through to the local kernel alone, so a merged board's Clear all left every
// remote card standing. The router broadcasts it, local first; each kernel clears its own feed's cards and appends its
// own ledger rows; Undo follows the last clear to every kernel it reached. The session header's Clear all
// (askClearMany, routed by its session id) is unchanged. A kernel whose socket is down at the click misses it (the
// message is deliberately not a queued kernel setting) and its cards stay.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { routeOutbound, FederationManager } from "./federation";

const FED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "federation.ts"), "utf8");
const SID = "11111111-2222-3333-4444-555555555555";

function withManager(fn: (fm: FederationManager, localSent: any[], remoteSent: [string, any][]) => void): void {
  const localSent: any[] = [], remoteSent: [string, any][] = [];
  const g: any = globalThis;
  const hadWindow = "window" in g, prevWindow = g.window;
  const hadLS = "localStorage" in g, prevLS = g.localStorage;
  g.window = { dispatchEvent: () => {}, __rompLocalSend: (m: any) => localSent.push(m) };
  g.localStorage = { getItem: () => null, setItem: () => {} };
  try {
    const fm = new FederationManager();
    (fm as any).sendRemote = (h: string, m: any) => remoteSent.push([h, m]);
    (fm as any).hostSeq = ["", "box2", "box3"];       // a board with two attached kernels' cards on it
    fn(fm, localSent, remoteSent);
  } finally {
    if (hadWindow) g.window = prevWindow; else delete g.window;
    if (hadLS) g.localStorage = prevLS; else delete g.localStorage;
  }
}

test("the router broadcasts the board-wide Clear all to every attached kernel, local first, the message untouched", () => {
  const r = routeOutbound({ type: "clearAll" }, new Set(["box2", "box3"]));
  assert.deepEqual(r.map((x) => x.host), ["", "box2", "box3"]);
  assert.ok(r.every((x) => x.msg.type === "clearAll" && Object.keys(x.msg).length === 1));
  assert.deepEqual(routeOutbound({ type: "clearAll" }).map((x) => x.host), [""], "a single-kernel board: the local kernel alone, as before");
});

test("a Clear all on a merged board reaches both kernels and Undo restores both sides", () => {
  withManager((fm, localSent, remoteSent) => {
    fm.outbound({ type: "clearAll" });
    assert.deepEqual(localSent.map((m) => m.type), ["clearAll"], "the local kernel does its part first");
    assert.deepEqual(remoteSent.map(([h, m]) => [h, m.type]), [["box2", "clearAll"], ["box3", "clearAll"]]);
    fm.outbound({ type: "undoClear" });
    assert.deepEqual(localSent.map((m) => m.type), ["clearAll", "undoClear"]);
    assert.deepEqual(remoteSent.map(([h, m]) => [h, m.type]),
      [["box2", "clearAll"], ["box3", "clearAll"], ["box2", "undoClear"], ["box3", "undoClear"]], "each kernel undoes its own batch");
    fm.outbound({ type: "undoClear" });
    assert.equal(remoteSent.length, 4, "a second Undo has no clear to follow to a remote kernel: local alone");
    assert.deepEqual(localSent.map((m) => m.type), ["clearAll", "undoClear", "undoClear"]);
  });
});

test("a remote kernel's refusal of an undo puts that kernel back as the next undo's target, so the retry reaches it; a landed undo still hands a second Undo to the local kernel alone (round ten of PR 1967)", () => {
  withManager((fm, localSent, remoteSent) => {
    fm.outbound({ type: "clearAll" });
    fm.outbound({ type: "undoClear" });                                  // reaches every kernel the Clear all reached; the target resets to local
    (fm as any).inboundNow("box2", { type: "err", op: "undoClear", sid: SID, title: "That undo did not land", text: "the clears log refused", itemIds: [], batches: [], owedBatch: [], batchesTotal: 0 });
    fm.outbound({ type: "undoClear" });                                  // the retry the dialog invites
    assert.deepEqual(remoteSent.slice(4).map(([h, m]) => [h, m.type]), [["box2", "undoClear"]], "to the kernel that refused, alone (before: the local kernel, which had refused nothing)");
    assert.deepEqual(localSent.map((m) => m.type), ["clearAll", "undoClear"], "the local kernel is not asked twice");
    fm.outbound({ type: "undoClear" });                                  // after the retry, the target is local again
    assert.equal(remoteSent.length, 5); assert.deepEqual(localSent.map((m) => m.type), ["clearAll", "undoClear", "undoClear"]);
  });
});

test("two remote kernels refusing the same fanned-out undo both get the retry; a refusal arriving after a later clear leaves that clear's routing alone (the tenth executed review of PR 1967)", () => {
  withManager((fm, localSent, remoteSent) => {
    fm.outbound({ type: "clearAll" });
    fm.outbound({ type: "undoClear" });
    const acct = (h: string) => (fm as any).inboundNow(h, { type: "err", op: "undoClear", sid: SID, title: "That undo did not land", text: "the clears log refused", itemIds: [], batches: [], owedBatch: [], batchesTotal: 0 });
    acct("box2"); acct("box3");
    fm.outbound({ type: "undoClear" });
    assert.deepEqual(remoteSent.slice(4).map(([h, m]) => [h, m.type]), [["box2", "undoClear"], ["box3", "undoClear"]], "every kernel that refused (before: the last refuser alone)");
    assert.deepEqual(localSent.map((m) => m.type), ["clearAll", "undoClear"]);
    // a clear routed after the undo: a late account does not take the routing back to the remote kernel
    fm.outbound({ type: "askClear", itemId: SID + ":g1", sid: SID });        // a local card: routed locally
    acct("box2");                                                             // the remote kernel's account of the earlier undo lands late
    fm.outbound({ type: "undoClear" });
    assert.equal(remoteSent.length, 6, "no remote kernel is asked");
    assert.deepEqual(localSent.map((m) => m.type), ["clearAll", "undoClear", "askClear", "undoClear"], "the undo follows the later clear to the local kernel (before: it went to the remote kernel and the local one never saw an undo)");
  });
});

test("the send hands the panes the kernels the undo went to (undoRouted): every attached kernel after a Clear all, the local kernel alone on the press after (round twelve of PR 1967)", () => {
  withManager((fm) => {
    const routed: any[] = [];
    (globalThis as any).window.dispatchEvent = (ev: any) => { if (ev && ev.data && ev.data.type === "undoRouted") routed.push(ev.data.hosts); };
    fm.outbound({ type: "clearAll" });
    fm.outbound({ type: "undoClear" });
    fm.outbound({ type: "undoClear" });
    assert.deepEqual(routed, [["", "box2", "box3"], [""]], "the routing federation used, handed to the panes at each send");
    fm.outbound({ type: "askClear", itemId: "box2:" + SID + ":g1", sid: "box2:" + SID });
    fm.outbound({ type: "undoClear" });
    assert.deepEqual(routed[2], ["box2"], "a remote card's clear: its kernel alone");
  });
});

test("a kernel's account of an undo retargets the retry whether it refused or reordered (ok true), and the local kernel's own account counts among the refusers (the second contributor's review of PR 1967)", () => {
  withManager((fm, localSent, remoteSent) => {
    fm.outbound({ type: "clearAll" });
    fm.outbound({ type: "undoClear" });
    (fm as any).inboundNow("box2", { type: "err", op: "undoClear", ok: true, sid: SID, title: "Undo brought back earlier cards first", text: "the last clear stands", itemIds: [], batches: [], owedBatch: [], batchesTotal: 0 });
    (fm as any).inboundNow("", { type: "err", op: "undoClear", sid: SID, title: "That undo did not land", text: "the clears log refused", itemIds: [], batches: [], owedBatch: [], batchesTotal: 0 });
    fm.outbound({ type: "undoClear" });
    assert.deepEqual(remoteSent.slice(4).map(([h, m]) => [h, m.type]), [["box2", "undoClear"]], "the reorder's information frame retargets too: the standing clear is there");
    assert.deepEqual(localSent.map((m) => m.type), ["clearAll", "undoClear", "undoClear"], "and the local kernel, which refused, gets the retry as well (before: skipped)");
  });
});

test("one Undo send is ONE undoRouted frame to the panes, naming every kernel it went to, and one undoClear per kernel (the round-twelve verifier's low on PR 1967: a live two-kernel board counted two frames for one click; the manager sends one)", () => {
  withManager((fm, localSent, remoteSent) => {
    const routed: any[] = [];
    (globalThis as any).window.dispatchEvent = (e: any) => { routed.push(e && e.data); };
    fm.outbound({ type: "clearAll" });
    fm.outbound({ type: "undoClear" });
    assert.deepEqual(routed.filter((m) => m && m.type === "undoRouted").map((m) => m.hosts), [["", "box2", "box3"]], "one frame, every kernel the undo went to");
    assert.equal(localSent.filter((m) => m.type === "undoClear").length, 1, "one send to the local kernel");
    assert.deepEqual(remoteSent.filter(([, m]) => m.type === "undoClear").map(([h]) => h), ["box2", "box3"], "one send per remote kernel");
  });
});

test("the session header's Clear all still goes to that session's kernel alone, and Undo follows it there alone", () => {
  withManager((fm, localSent, remoteSent) => {
    fm.outbound({ type: "askClearMany", sid: "box2:" + SID, itemIds: ["box2:" + SID + ":g1", "box2:" + SID + ":g2"] });
    assert.equal(localSent.length, 0);
    assert.deepEqual(remoteSent.map(([h, m]) => [h, m.type, m.sid]), [["box2", "askClearMany", SID]], "routed by id, bare");
    fm.outbound({ type: "undoClear" });
    assert.equal(localSent.length, 0, "the local kernel took no clear: nothing to undo there");
    assert.deepEqual(remoteSent.map(([h, m]) => [h, m.type]), [["box2", "askClearMany"], ["box2", "undoClear"]]);
    fm.outbound({ type: "askClear", sid: SID, itemId: SID + ":g5" });   // the feed's shape: routed by the session id
    fm.outbound({ type: "undoClear" });
    assert.deepEqual(localSent.map((m) => m.type), ["askClear", "undoClear"], "a local clear's Undo stays local");
    assert.equal(remoteSent.length, 2);
  });
});

test("Clear all is not a queued kernel setting: a kernel that is down at the click misses it and its cards stay", () => {
  assert.doesNotMatch(FED.slice(FED.indexOf("const KERNEL_SETTING"), FED.indexOf("]);", FED.indexOf("const KERNEL_SETTING"))), /clearAll/);
  assert.match(FED, /if \(msg\.type === "clearAll"\) return \[LOCAL, \.\.\.\(knownHosts \|\| \[\]\)\]\.map\(\(h\) => \(\{ host: h, msg \}\)\);/);
  assert.match(FED, /this\.diag\("senddrop", \{ host, msgType: \(msg && msg\.type\) \|\| "" \}\);\s*\n\s*this\.dropWarn\(host, msg\);/, "a non-setting on a down socket is dropped and warned, never queued");
});
