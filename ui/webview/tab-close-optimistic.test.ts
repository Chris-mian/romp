// Closing a chat tab is OPTIMISTIC and STAYS that way (the user 2026-07-24): the tab goes the instant you
// confirm, the shutdown runs behind it, and only a close that genuinely didn't take says anything.
//
// The bug: dismissSession already dropped the tab on click, but nothing recorded the close locally. The
// kernel goes on listing the session for a push or two (closeTab flips a hidden flag, then a full rebuild),
// and applyTabOrder adopts the kernel's list VERBATIM — so the id came straight back. With its session
// already dropped client-side there was nothing to render but a tabs-first placeholder: the closed tab faded
// back in wearing the spinning romp swirl and sat there, reading as a shutdown you had to wait out.
//
// The executed model below is the whole close/ack/backstop cycle; the source pins hold the wiring in render.ts.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");

const CLOSE_ACK_MS = 15_000;

// A stand-in for the client's tab state around a close: the kernel's last pushed list, the ids we know a
// session for, and the just-closed set. Mirrors render.ts — closeTabLocally records + drops, ackClosingTabs
// settles against each kernel push, and the strip skips anything still in `closing`.
function model(now = 0) {
  const kernelList: string[] = [];
  const known = new Set<string>();
  const closing = new Map<string, number>();
  const warned: string[] = [];
  let clock = now;
  return {
    warned,
    tick(ms: number) { clock += ms; },
    session(id: string) { known.add(id); if (!kernelList.includes(id)) kernelList.push(id); },
    // the ✕: post closeTab, record it, drop the session locally (dismissSession)
    close(id: string) { closing.set(id, clock); known.delete(id); },
    // a kernel tabOrder push — `list` is what the kernel currently believes is open
    push(list: string[]) {
      for (const [id, ts] of Array.from(closing)) {
        if (!list.includes(id)) { closing.delete(id); continue; }        // kernel agreed → confirmed
        if (clock - ts < CLOSE_ACK_MS) continue;                          // still in flight
        closing.delete(id);
        warned.push(id);                                                  // the close plainly didn't take
      }
      kernelList.length = 0;
      for (const id of list) kernelList.push(id);
    },
    // what the strip actually draws: the kernel's ids minus the ones we just closed. An id with no session
    // behind it is the PLACEHOLDER case — the swirl — so it's called out separately.
    tabs() { return kernelList.filter((id) => !closing.has(id)); },
    placeholders() { return kernelList.filter((id) => !closing.has(id) && !known.has(id)); },
  };
}

test("the closed tab does NOT come back as a swirling placeholder on the next push", () => {
  const m = model();
  m.session("web"); m.session("api"); m.session("tests");
  m.close("api");
  assert.deepEqual(m.tabs(), ["web", "tests"], "gone the instant it's confirmed");
  // the kernel hasn't caught up yet — this push still lists api. Before the fix this re-added it, and with
  // no session behind it the strip drew the loading placeholder.
  m.push(["web", "api", "tests"]);
  assert.deepEqual(m.placeholders(), [], "no romp-swirl placeholder for a tab we just closed");
  assert.deepEqual(m.tabs(), ["web", "tests"], "still gone while the shutdown runs behind us");
  // the kernel finally drops it → the close is acked and nothing is suppressed any more
  m.push(["web", "tests"]);
  assert.deepEqual(m.tabs(), ["web", "tests"]);
  assert.deepEqual(m.warned, [], "an ordinary close says nothing at all");
});

test("a close that never takes surfaces an error and lets the tab back", () => {
  const m = model();
  m.session("web"); m.session("api");
  m.close("api");
  m.tick(CLOSE_ACK_MS - 1);
  m.push(["web", "api"]);
  assert.deepEqual(m.warned, [], "still within the ack window — a slow kernel isn't a failure");
  assert.deepEqual(m.tabs(), ["web"]);
  m.tick(2);
  m.push(["web", "api"]);
  assert.deepEqual(m.warned, ["api"], "past the backstop the close plainly didn't take — say so");
  assert.deepEqual(m.tabs(), ["web", "api"], "…and the tab returns rather than hiding a live session");
});

test("the ack is the kernel DROPPING the id, not the elapsed time", () => {
  const m = model();
  m.session("web"); m.session("api");
  m.close("api");
  m.push(["web"]);                       // acked immediately, well inside the window
  m.tick(CLOSE_ACK_MS * 10);             // …so no amount of later time can raise a false alarm
  m.push(["web"]);
  assert.deepEqual(m.warned, []);
  // and a session the kernel re-opens for real (revive) is drawn again — the suppression was cleared on ack
  m.session("api");
  m.push(["web", "api"]);
  assert.deepEqual(m.tabs(), ["web", "api"]);
});

test("a session dying on its OWN is not recorded as a close of ours", () => {
  // dismissSession is shared by both paths; only the ✕ goes through closeTabLocally. If a death were
  // recorded as a close, the backstop could later warn about a session nobody asked to close.
  const m = model();
  m.session("web"); m.session("api");
  m.push(["web", "api"]);
  // the kernel's `closed` event: drop it, record nothing
  m.session("web");
  m.push(["web"]);
  m.tick(CLOSE_ACK_MS * 2);
  m.push(["web"]);
  assert.deepEqual(m.warned, []);
});

// ---- the wiring in render.ts -------------------------------------------------------------------------

test("closeTabLocally drops the tab, THEN records the close — in that order", () => {
  // (2026-07-30: a PROVISIONAL tab short-circuits above this — there is no session to close, so the ✕
  // means "never mind" and cancels the spawn instead. A real tab's path is unchanged.)
  //
  // The order is the whole mechanism (the user 2026-08-02, closed tabs lingering as the spinning swirl):
  // this shipped as set-then-dismiss while dismissSession opened with closingTabs.delete(id), so the
  // record was erased the instant it was written — the executed model above passed while the composed
  // wiring was a no-op. Hence these pins hold the ORDER, and the next test holds dismissSession's hands.
  assert.match(RENDER, /return;\s*\n\s*\}\s*\n\s*dismissSession\(id\);\s*\n\s*closingTabs\.set\(id, Date\.now\(\)\);/,
    "the provisional short-circuit returns above; a real tab still dismisses THEN records");
  // declared beside tabMeta, NOT down by dismissSession: renderTabs reads it and can run before the module
  // finishes evaluating, which would make a `const` down there a temporal-dead-zone throw.
  assert.match(RENDER, /const tabMeta = new Map[\s\S]{0,900}?const closingTabs = new Map<string, number>\(\);/);
  assert.match(RENDER, /const CLOSE_ACK_MS = 15_000;/);
});

test("the strip skips a just-closed tab on BOTH passes (order AND the tabMeta placeholder pass)", () => {
  // the tabMeta pass is the one that drew the swirl: an id the kernel still lists with no session behind it
  assert.match(RENDER, /for \(const id of order\) \{ if \(!seen\.has\(id\) && !closingTabs\.has\(id\)\)/);
  assert.match(RENDER, /for \(const id of tabMeta\.keys\(\)\) \{ if \(!seen\.has\(id\) && !closingTabs\.has\(id\)\)/);
});

test("every close path is optimistic — the in-page ✕, a dead read-only tab, and the kernel's confirmClose", () => {
  assert.match(RENDER, /closeTab", id \}\);\s*\n\s*closeTabLocally\(id\);/, "the in-page ✕ confirm");
  // the dead-tab ✕: still optimistic, with the closeTab post skipped for a failed provisional id the
  // kernel never knew (2026-08-08 — the failed tab now lingers holding its text)
  assert.match(RENDER, /if \(el\.dataset\.dead === "1"\) \{\s*\n\s*if \(!isProvisionalId\(id\)\) vscodeApi\.postMessage\(\{ type: "closeTab", id \}\);\s*\n\s*closeTabLocally\(id\);\s*\n\s*return;/);
  // the kernel-driven confirmClose modal used to post and then just sit there waiting for the push
  assert.match(RENDER, /m\.type === "confirmClose"[\s\S]*?closeTabLocally\(m\.id\);/);
});

test("ackClosingTabs settles against the kernel's list on every tabOrder push", () => {
  assert.match(RENDER, /ackClosingTabs\(kernelOrder\);/);
  assert.match(RENDER, /function ackClosingTabs\(kernelOrder: readonly string\[\]\): void/);
  assert.match(RENDER, /if \(!live\.has\(id\)\) \{ closingTabs\.delete\(id\); continue; \}/, "gone from the kernel = confirmed");
  assert.match(RENDER, /if \(now - ts < CLOSE_ACK_MS\) continue;/, "inside the window a slow kernel is not a failure");
  assert.match(RENDER, /warnToast\(`Couldn't close/);
});

test("dismissSession never touches the suppression — retiring belongs to ack, backstop, and reopen", () => {
  // dismissSession is the shared drop path: the ✕ runs through it microseconds after recording the close,
  // and under federation the kernel's `closed` event can predate stale merged frames that still list the
  // id. A closingTabs.delete in its body is what disarmed the whole optimistic close (see above).
  const body = RENDER.match(/function dismissSession\(id: string\): void \{[\s\S]*?\n\}/);
  assert.ok(body, "dismissSession not found");
  assert.doesNotMatch(body![0], /closingTabs\./, "dismissSession must not read or write closingTabs");
  // …and the one legitimate early retire: an explicit reveal (reopen from the picker inside the ack
  // window) must show the tab at once instead of waiting out the suppression
  assert.match(RENDER, /m\.type === "focus"\) \{\s*\n\s*revealSelfPane\(\);.*\n\s*closingTabs\.delete\(m\.id\);/);
});
