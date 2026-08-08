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
  assert.match(RENDER, /if \(v\) v\.stale = true;\s*\n\s*if \(id === activeId\) appendActive\(\);/);
});

// The reconcile's two IN-PLACE tail mutations — merging into an existing queued group (a busy session
// already showing queued messages) and pop+push on a repeat send — leave s.events.length unchanged, so
// syncView's no-op fast path (rendered === len && !stale) concluded "nothing changed" and skipped the
// repaint: the bubble waited for the NEXT kernel push, a visible beat after Enter (the user 2026-08-07).
// Only the length-growing case (first send, bare tail) painted on the keystroke. registerOptimistic now
// marks the view stale before appendActive, so every send takes the stale window re-render immediately.
test("a send paints on ITS OWN keystroke even when the tail mutates in place (no length change)", () => {
  // the stale mark sits between the reconcile and the repaint, so appendActive can't hit the fast path
  assert.match(RENDER, /reconcileOptimistic\(s\);[\s\S]{0,700}const v = views\.get\(id\);\s*\n\s*if \(v\) v\.stale = true;\s*\n\s*if \(id === activeId\) appendActive\(\);/);
  // the fast path it defeats keys on length + staleness — stale must veto the skip
  assert.match(RENDER, /if \(v\.rendered === len && !v\.stale && v\.el\.childNodes\.length > 0\) return v;/);
  // executed replica: the fast-path predicate must not skip once the view is marked stale, even though
  // the in-place merge keeps the length equal to what was last rendered
  const skips = (rendered: number, len: number, stale: boolean, children: number) =>
    rendered === len && !stale && children > 0;
  assert.equal(skips(50, 50, false, 50), true, "length-neutral mutation without the mark: skipped (the bug)");
  assert.equal(skips(50, 50, true, 50), false, "the stale mark forces the repaint on the same keystroke");
});

test("every push entry point re-asserts (or retires) the optimistic tail", () => {
  // update(), chatTail(), and upsert() each call reconcileOptimistic after setting s.events
  const calls = RENDER.match(/reconcileOptimistic\(s\);/g) || [];
  assert.ok(calls.length >= 4, "reconcile wired into send + all three push paths, got " + calls.length);
});

// The optimistic echo rides the QUEUED idiom (the user 2026-07-16): to the reader an unconfirmed send and a
// queued one are the same state, so they wear the same dashed bubble — and the look then only ever moves
// provisional→settled. It first shipped as a 0.6-opacity SOLID bubble, which invented a third look and made a
// queued send flip solid→dashed (backwards, as if it had un-landed).
test("an optimistic echo is a tail-appended, kernel-invisible QUEUED event — never a solid user bubble", () => {
  const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
  assert.match(RENDER, /const OPT_PREFIX = "optimistic:";/);
  assert.match(RENDER, /const mk = \(p: \{ text: string \}\) => \(\{ md: p\.text, optimistic: true, cancelable: false \}\);/);
  // stale ones pop cheaply off the end (always tail-appended)
  assert.match(RENDER, /while \(s\.events\.length && isOptimistic\(s\.events\[s\.events\.length - 1\]\)\) s\.events\.pop\(\);/);
  // the abandoned dim idiom is gone from both the render and the stylesheet
  assert.doesNotMatch(RENDER, /ev\.pending/);
  assert.doesNotMatch(CSS, /\.user-bubble\.pending \{/);
  // it reuses the chat's ONE provisional look rather than adding CSS of its own
  assert.match(CSS, /\.queued-bubble \{[\s\S]*?border: 1px dashed/);
});

test("nothing known-queued → a BARE dashed bubble (no 'N queued' header we can't back)", () => {
  assert.match(RENDER, /s\.events\.push\(\{ kind: "queued", bare: true, texts: keep\.map\(mk\), uuid: OPT_PREFIX \+ keep\[0\]\.ts \}\);/);
  assert.match(RENDER, /if \(!ev\.bare\) \{/, "renderQueued skips the header for a bare group");
});

test("something IS queued → ours merges into that group, counted under its header", () => {
  assert.match(RENDER, /s\.events\[qj\] = \{ \.\.\.q, texts: \[\.\.\.q\.texts, \.\.\.keep\.map\(mk\)\] \};/);
  // and the extension is undone before `landed` runs, so reconcile only ever reads kernel truth
  assert.match(RENDER, /if \(q\.texts\.some\(\(t\) => t\.optimistic\)\) s\.events\[qi\] = \{ \.\.\.q, texts: q\.texts\.filter\(\(t\) => !t\.optimistic\) \};/);
});

test("an unconfirmed echo gets its own tooltip and never an ✕ (nothing confirmed to cancel)", () => {
  assert.match(RENDER, /if \(t\.optimistic\) bubble\.title = "sent just now — romp hasn't confirmed the session has it yet";/);
  // cancelable:false → the ✕ branch (which needs cancelable AND an idx/park handle) can't fire for ours
  assert.match(RENDER, /if \(t\.cancelable && \(t\.idx !== undefined \|\| t\.park !== undefined\)\) \{/);
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
