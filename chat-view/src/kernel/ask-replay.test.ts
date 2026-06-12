// Pending-prompt replay on client connect (pendingAskReplays, chat.ts): askLive
// pushes are change-gated on the kernel-side askSig, so a client connecting
// AFTER a prompt appeared would never see it — a reload hid a blocked session's
// permission prompt in both front ends (2026-06-12). These tests pin the replay
// set: hook-confirmed awaiting sessions and already-signed hookless pickers
// replay; quiet sessions don't; a pane already back at the composer replays
// nothing even when a stale askSig lingers.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { pendingAskReplays, chatAnchorFor, Session } from "./chat";
import type { SessionState } from "./backend";
import type { ParsedAsk } from "../askparse";

function sess(over: Partial<Session>): Session {
  return {
    id: "id-" + (over.name ?? "x"), file: "/dev/null", name: "x", color: null,
    lastSig: "", lastSince: null, lastState: "", lastWorking: false,
    ...over,
  } as Session;
}

function states(m: Record<string, string>): Map<string, SessionState> {
  return new Map(Object.entries(m).map(([name, state]) =>
    [name, { state, since: "0" } as SessionState]));
}

const PICKER = { kind: "single", sig: "p1", options: [{ n: 1, label: "Yes" }] } as unknown as ParsedAsk;

function asker(panes: Record<string, { ask: ParsedAsk | null; sig: string } | null>) {
  const seen: string[] = [];
  return {
    seen,
    liveAsk(name: string) { seen.push(name); return panes[name] ?? null; },
  };
}

test("awaiting session with a parsed picker replays it", () => {
  const a = asker({ pkg: { ask: PICKER, sig: "p1" } });
  const out = pendingAskReplays([sess({ name: "pkg", id: "S1" })], states({ pkg: "permission" }), a);
  assert.deepEqual(out, [{ id: "S1", ask: PICKER }]);
});

test("awaiting session on a free-text screen replays ask:null (text input)", () => {
  const a = asker({ pkg: { ask: null, sig: "TEXT" } });
  const out = pendingAskReplays([sess({ name: "pkg", id: "S1" })], states({ pkg: "permission" }), a);
  assert.deepEqual(out, [{ id: "S1", ask: null }]);
});

test("quiet sessions are skipped without even capturing their panes", () => {
  const a = asker({});
  const out = pendingAskReplays(
    [sess({ name: "idle1" }), sess({ name: "busy", lastWorking: true })],
    states({ idle1: "idle", busy: "working" }), a);
  assert.deepEqual(out, []);
  assert.deepEqual(a.seen, []);             // no pane capture for sessions that can't have a prompt
});

test("hookless picker (askSig set, chip ready) replays", () => {
  const a = asker({ quiet: { ask: PICKER, sig: "p1" } });
  const out = pendingAskReplays([sess({ name: "quiet", id: "S2", askSig: "p1" })], states({ quiet: "waiting" }), a);
  assert.deepEqual(out, [{ id: "S2", ask: PICKER }]);
});

test("stale askSig with the composer back replays nothing", () => {
  // liveAsk returns null once the pane is a composer screen again — the pane is
  // the truth, so a lingering sig must not resurrect an answered prompt.
  const a = asker({ healed: null });
  const out = pendingAskReplays([sess({ name: "healed", askSig: "old" })], states({ healed: "waiting" }), a);
  assert.deepEqual(out, []);
});

// ---- chatAnchorFor: the uuid anchor a kernel locate carries (2026-06-12) ----
// The 60c811c rework made feed work-row locates time-only; every click landed
// "near" (typically a tool block). These pin the anchor selection per intent.

test("work-intent locate anchors on the readable reply", () => {
  assert.equal(chatAnchorFor({ uuid: "p1", replyUuid: "r1" }), "r1");
});

test("work-intent falls back to the prompt line when the slice has no reply (interrupted turn)", () => {
  assert.equal(chatAnchorFor({ uuid: "p1", replyUuid: null }), "p1");
});

test("prompt-intent locate anchors on the turn's own line", () => {
  assert.equal(chatAnchorFor({ uuid: "p1", replyUuid: "r1" }, "user"), "p1");
});

test("unresolvable event yields no anchor (anchorT fallback handles it)", () => {
  assert.equal(chatAnchorFor(null), undefined);
  assert.equal(chatAnchorFor({ uuid: null, replyUuid: null }), undefined);
});

test("empty states map (probe unreliable): only askSig-bearing sessions replay", () => {
  const a = asker({ pkg: { ask: PICKER, sig: "p1" }, other: { ask: PICKER, sig: "p2" } });
  const out = pendingAskReplays(
    [sess({ name: "pkg", id: "S1", askSig: "p1" }), sess({ name: "other", id: "S3" })],
    null, a);
  assert.deepEqual(out, [{ id: "S1", ask: PICKER }]);
});
