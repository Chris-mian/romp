// A composer send clears the box instantly, but the message only reappears in the chat once the kernel
// round-trips it back as its own provisional. Sending to a busy/slow thread, that provisional could briefly
// VANISH in the server-side echo→landed gap — so a just-sent message looked lost for a beat (the user
// 2026-07-15: "showing up as a provisional message ... and it disappeared"). Fix: a CLIENT-side optimistic
// bubble injected at the tail the moment you hit Enter, re-asserted on every push until the kernel's payload
// demonstrably carries the message, then retired. render.ts has import-time DOM side effects → source pins +
// an executed replica of the reconcile decision (user-img-dedup.test.ts precedent).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(
  path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");

test("the plain send registers an optimistic bubble; follow-up/quote sends keep their own kernel echo", () => {
  // only the PLAIN sendMessage branch registers — a citation follow-up/quote has its own kernel-side echo
  assert.match(RENDER, /else \{ vscodeApi\.postMessage\(\{ type: "sendMessage", id: activeId, text \}\); registerOptimistic\(activeId, text\); \}/);
  // registerOptimistic shows it NOW (before any push) via reconcile + appendActive
  assert.match(RENDER, /function registerOptimistic\(id: string, text: string\): void/);
  assert.match(RENDER, /reconcileOptimistic\(s\);\s*\n\s*if \(id === activeId\) appendActive\(\);/);
});

test("every push entry point re-asserts (or retires) the optimistic tail", () => {
  // update(), chatTail(), and upsert() each call reconcileOptimistic after setting s.events
  const calls = RENDER.match(/reconcileOptimistic\(s\);/g) || [];
  assert.ok(calls.length >= 4, "reconcile wired into send + all three push paths, got " + calls.length);
});

test("an optimistic bubble is a tail-appended, kernel-invisible user event", () => {
  assert.match(RENDER, /const OPT_PREFIX = "optimistic:";/);
  assert.match(RENDER, /s\.events\.push\(\{ kind: "user", md: p\.text, human: true, uuid: OPT_PREFIX \+ p\.ts \}\)/);
  // stale ones pop cheaply off the end (always tail-appended)
  assert.match(RENDER, /while \(s\.events\.length && isOptimistic\(s\.events\[s\.events\.length - 1\]\)\) s\.events\.pop\(\);/);
});

// The optimistic bubble first shipped dimmed (.pending, opacity 0.6), which invented a THIRD provisional look
// next to the dashed .queued-bubble and made every send flicker dim→solid as the kernel's copy superseded it
// (the user 2026-07-16). It now renders EXACTLY like the landed message it's replaced by.
test("a just-sent bubble carries NO distinguishing flag or styling — it looks like what replaces it", () => {
  const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
  assert.match(RENDER, /const bubble = el\("div", \(romp \? "romp-bubble" : injected \? "user-note" : "user-bubble"\) \+ " md"\);/);
  assert.doesNotMatch(RENDER, /ev\.pending/, "no pending flag is read when rendering");
  assert.doesNotMatch(RENDER, /pending: true/, "and none is written onto the optimistic event");
  assert.doesNotMatch(CSS, /\.user-bubble\.pending \{/, "the dim rule is gone");
  // the ONE provisional idiom the chat has stays exactly as it was: dashed = queued behind a busy turn
  assert.match(CSS, /\.queued-bubble \{[\s\S]*?border: 1px dashed/);
});

// executed replica of reconcileOptimistic's keep/retire decision: a send survives until the kernel's payload
// carries its text (a landed user atom OR a queued bubble), or until the TTL backstop expires.
test("reconcile keeps an in-flight send until the kernel surfaces it, then drops it", () => {
  type Ev = { kind: string; md?: string; texts?: { md: string }[] };
  const OPT_TTL_MS = 20_000, OPT_TAIL_SCAN = 30;
  const reconcile = (events: Ev[], list: { text: string; ts: number }[], now: number) => {
    const tail = events.slice(-OPT_TAIL_SCAN);
    const landed = (t: string) => tail.some((e) =>
      (e.kind === "user" && typeof e.md === "string" && e.md.includes(t)) ||
      (e.kind === "queued" && Array.isArray(e.texts) && e.texts.some((x) => typeof x.md === "string" && x.md.includes(t))));
    return list.filter((p) => now - p.ts < OPT_TTL_MS && !landed(p.text));
  };
  const T0 = 1_000_000;
  const sent = [{ text: "ship the docs", ts: T0 }];

  // gap: the kernel push carries NEITHER a user atom nor a queued bubble for it → keep asserting
  assert.equal(reconcile([{ kind: "assistant", md: "working on the prior turn" }], sent, T0 + 500).length, 1);
  // kernel echoed it as a landed user atom → drop (its real bubble now owns the spot)
  assert.equal(reconcile([{ kind: "user", md: "ship the docs" }], sent, T0 + 500).length, 0);
  // busy session: kernel shows it as a QUEUED bubble → also counts as surfaced → drop
  assert.equal(reconcile([{ kind: "queued", texts: [{ md: "ship the docs" }] }], sent, T0 + 500).length, 0);
  // TTL backstop: nothing ever surfaced, but past the window we stop asserting a possibly-dropped send
  assert.equal(reconcile([{ kind: "assistant", md: "…" }], sent, T0 + OPT_TTL_MS + 1).length, 0);
});
