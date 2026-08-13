// EXECUTES the card's spin ladder (./spin-caption). The rule used to live inline in feed.ts and be pinned
// by source regex, which is exactly how it went wrong: the "keep the decision brief visible" fix gated the
// recheck/rejudging swirl on `!briefText`, the regex pins were updated to match, and every test stayed
// green while a live card (a blocked goal being re-judged) rendered as a bare summary sitting in the
// Working column with nothing saying it was in motion or still blocked (the user 2026-07-21).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { spinFor } from "./spin-caption";
import { distillInputs, distillText, distillPending } from "./distiller-line";

// --- THE REGRESSION: a re-judging card always spins ----------------------------------------------
// A blocked goal you replied to on the thread. The kernel moves it to Working while the reply is in
// flight (build_feed: "The 'Re-judging…' swirl rides along in Working"). Since 2026-07-22 the decision
// brief is withheld for exactly that window (./distiller-line), which makes this swirl the ONLY thing on
// the card saying it is in motion and still blocked underneath. The `↩ re-judging` chip is recheck-only,
// so gating the swirl on anything would leave the card mute.
test("a rejudging card WITH a decision brief still spins (the brief never suppresses the swirl)", () => {
  const s = spinFor({ rejudging: true, column: "working" }, false, false);
  assert.equal(s.caption, "Analyzing…", "a re-judging card must say it is being re-judged");
  assert.match(s.tip, /replied on this thread/);
  assert.equal(s.awaitingBg, false, "only the AWAITING case wears the box");
});

test("a recheck card WITH a decision brief still spins", () => {
  const s = spinFor({ recheck: true, column: "working" }, false, false);
  assert.equal(s.caption, "Analyzing…");
  assert.match(s.tip, /followed up/);
});

// Without a brief it behaved correctly all along — pin both halves so the fix can't be half-reverted.
test("recheck/rejudging spin the same whether or not a brief exists", () => {
  for (const it of [{ recheck: true }, { rejudging: true }]) {
    // distillPending true = "resolved, distiller hasn't produced its line yet" (no brief on screen);
    // false = the brief has landed. The caption is identical either way.
    assert.equal(spinFor(it, true, false).caption, spinFor(it, false, false).caption,
      "a present brief must not change the spin caption");
  }
});

// --- the rest of the ladder, in precedence order ---------------------------------------------------
test("AWAITING outranks everything and wears the box", () => {
  const s = spinFor({ awaiting: { why: "" }, recheck: true, judging: true, column: "working" }, true, false);
  assert.equal(s.caption, "Awaiting background agents");
  assert.equal(s.awaitingBg, true, "the awaiting case gets the rounded box (.await-paused)");
  assert.match(s.tip, /Not on you|not on you/);
});

test("AWAITING uses the kernel's why verbatim (capitalized) when it reads 'waiting on …'", () => {
  const s = spinFor({ awaiting: { why: "waiting on 3 subagents" } }, false, false);
  assert.equal(s.caption, "Waiting on 3 subagents");
  assert.match(s.tip, /^waiting on 3 subagents\. Not on you/);
});

test("a peer wait (waitingOn chip) and a bg-TASK wait (pill) both defer — no generic awaiting box", () => {
  // the "Awaiting <peer>" chip / the "Awaiting task" pill already carry these; the box would double up
  assert.equal(spinFor({ awaiting: { why: "x" }, waitingOn: "peer" }, false, false).caption, null);
  assert.equal(spinFor({ awaiting: { why: "x", tasks: ["t1"] } }, false, false).caption, null);
});

test("a PROVISIONAL working card tells the truth about its phase", () => {
  assert.equal(spinFor({ provisional: true, column: "working" }, false, false).caption, "Working…",
    "an OPEN turn is just working — the judge has nothing to classify yet");
  assert.equal(spinFor({ provisional: true, column: "working", judging: true }, false, false).caption,
    "Analyzing…", "once the turn settles the planner's pass is due");
});

test("a provisional AWAITING placeholder never reads a false 'Working…'", () => {
  // provisional + awaiting (a bg-task wait with no goal to floor) → the awaiting branch owns it
  const s = spinFor({ provisional: true, column: "working", awaiting: { why: "" } }, false, false);
  assert.equal(s.caption, "Awaiting background agents");
});

test("the SETTLE GAP (turn done, verdict pending) spins on a working card", () => {
  assert.equal(spinFor({ judging: true, column: "working" }, false, false).caption, "Analyzing…");
  assert.equal(spinFor({ judging: true, column: "needs_input" }, false, false).caption, null,
    "judging only speaks for a card sitting in Working");
});

test("the SETTLE GAP tip carries the nudge hold the retired judging-stall chip used to tell", () => {
  // The user 2026-07-31: a goal held only because romp's own review is mid-flight is romp WORKING the
  // card, so the yellow Stalled chip no longer minted for it (jd.stall_why_stands screens WHY_JUDGING).
  // The story moved here, one hover deep — the tip must keep saying the hold exists and is not a stall,
  // or dropping the chip becomes dropping the information.
  const tip = spinFor({ judging: true, column: "working" }, false, false).tip;
  assert.match(tip, /[Nn]udges hold off/, "the hold is named");
  assert.match(tip, /not stuck/, "…and read as romp working, not a wedge");
});

test("DISTILLING names which line is being written", () => {
  assert.equal(spinFor({}, true, true).tip, "Writing the key takeaway…");
  assert.equal(spinFor({}, true, false).tip, "Writing the decision brief…");
  assert.equal(spinFor({}, true, true).caption, "Distilling…");
});

test("an ordinary working card with its turn open shows no spin at all", () => {
  assert.deepEqual(spinFor({ column: "working" }, false, false), { caption: null, tip: "", awaitingBg: false });
});

test("recheck/rejudging outrank the settle gap and the distiller", () => {
  assert.match(spinFor({ rejudging: true, judging: true, column: "working" }, true, false).tip,
    /replied on this thread/);
  assert.match(spinFor({ recheck: true, judging: true, column: "working" }, true, false).tip,
    /followed up/);
});

// --- NEVER MUTE: withholding the line must not leave a silent card ---------------------------------
// The 2026-07-22 change rests on one claim: a card only reaches the Working column while settled if
// recheck or rejudging put it there, and both raise a caption. Execute the pair together — the exact
// composition feed.ts runs — so the claim cannot rot into a blank card.
test("a settled card displaced to Working loses its line but never its caption", () => {
  for (const displaced of [{ recheck: true }, { rejudging: true }]) {
    for (const state of ["blocked", "completed"] as const) {
      const { completed, blocked } = distillInputs(state, "working");
      assert.equal(distillText(completed, blocked, "a takeaway", "a decision brief"), "",
        `${state} + ${JSON.stringify(displaced)}: the stale line is withheld`);
      const s = spinFor({ ...displaced, column: "working" }, distillPending(completed, blocked, null, null), completed);
      assert.equal(s.caption, "Analyzing…",
        `${state} + ${JSON.stringify(displaced)}: ...and the card still says it is in motion`);
    }
  }
});

// --- wiring: feed.ts must actually call the module (the rule is useless unbound) --------------------
const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");

test("feed.ts routes the card's swirl through spinFor and keeps no inline copy of the ladder", () => {
  assert.match(FEED, /import \{ spinFor \} from "\.\/spin-caption";/);
  assert.match(FEED, /const spin = spinFor\(it, distillPending\(/);
  assert.match(FEED, /const spinCaption = spin\.caption, spinTip = spin\.tip, awaitingBg = spin\.awaitingBg;/);
  // the inline ladder is gone — no second, drifting copy of the rule
  assert.doesNotMatch(FEED, /spinCaption = "Analyzing…";/);
  assert.doesNotMatch(FEED, /it\.rejudging && !briefText/);
  assert.doesNotMatch(FEED, /it\.recheck && !briefText/);
  // …and it still drives the same DOM
  assert.match(FEED, /a\._awaitSpin\.style\.display = spinCaption \? "" : "none";/);
  assert.match(FEED, /a\._awaitSpin\.classList\.toggle\("await-paused", awaitingBg\);/);
  assert.match(FEED, /a\._awaitWhy\.textContent = spinCaption; a\._awaitSpin\.title = spinTip \|\| spinCaption;/);
});

// --- the working narration (the user 2026-08-13): the previously-mute ordinary working card ---------
test("an ordinary working card with its turn open narrates: tool count + running time", () => {
  const s = spinFor({ column: "working", working: { since: 1000, toolUses: 23 } },
                    false, false, 1000 + 8 * 60);
  assert.equal(s.caption, "Working — 23 tool uses · 8m");
  const one = spinFor({ column: "working", working: { since: 1000, toolUses: 1 } },
                      false, false, 1030);
  assert.equal(one.caption, "Working — 1 tool use · 0m", "singular reads as English");
  const long = spinFor({ column: "working", working: { since: 1000, toolUses: 400 } },
                       false, false, 1000 + 95 * 60);
  assert.equal(long.caption, "Working — 400 tool uses · 1h 35m", "hours split out past sixty minutes");
});

test("zero tool uses says nothing — the timer alone narrates until the first call", () => {
  // "0 tool uses" was noise (the user 2026-08-13): the count earns its place at one
  const z = spinFor({ column: "working", working: { since: 1000, toolUses: 0 } },
                    false, false, 1000 + 3 * 60);
  assert.equal(z.caption, "Working — 3m");
  const bare = spinFor({ column: "working", working: { since: null, toolUses: 0 } }, false, false);
  assert.equal(bare.caption, "Working…", "no count, no clock → the plain swirl still says in-motion");
});

test("the narration is the FLOOR — every richer story still wins", () => {
  const w = { since: 1000, toolUses: 5 };
  assert.equal(spinFor({ column: "working", working: w, judging: true }, false, false, 2000).caption,
               "Analyzing…", "the settle gap outranks narration");
  assert.equal(spinFor({ column: "working", working: w, recheck: true }, false, false, 2000).caption,
               "Analyzing…", "re-check outranks narration");
  assert.equal(spinFor({ column: "working", working: w, awaiting: { why: null } }, false, false, 2000).caption,
               "Awaiting background agents", "awaiting outranks narration");
  assert.equal(spinFor({ column: "working", working: w }, true, false, 2000).caption,
               "Distilling…", "a pending distill outranks narration");
});

test("no narration off the working column or without the payload", () => {
  assert.equal(spinFor({ column: "needs_input", working: { since: 1, toolUses: 2 } }, false, false, 100).caption,
               null);
  assert.equal(spinFor({ column: "working" }, false, false, 100).caption, null,
               "a cache-cold card paints plain until the payload snaps in");
});
