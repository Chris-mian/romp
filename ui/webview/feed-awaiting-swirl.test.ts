// Spinning-swirl + caption on "in motion, not on you" cards (the user 2026-06-29): a small romp swirl spins in
// the card body — the SAME spot the distiller takeaway/decision-brief lands for completed/blocked cards — with a
// couple words saying what's happening. THREE cases, all in the Working column: AWAITING (it.awaiting, not a
// peer wait → the kernel why), PROVISIONAL (a dashed live-prompt placeholder → "Working…"), RE-CHECK (a
// soft-block you answered with a TARGETED follow-up, moved to Working → "Re-judging…"), and REJUDGING (a
// soft-block + a PLAIN reply that STAYS in Needs-You, with a turn in flight → "Re-judging…"). Source pin (no jsdom).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("the swirl element is built in the body, right after the distiller line, and registered", () => {
  assert.match(FEED, /const awaitSpin = el\("div", "fask-awaiting"\); awaitSpin\.style\.display = "none";/);
  assert.match(FEED, /const awaitGlyph = el\("span", "fask-awaiting-swirl"\)/);
  // distill now rides inside the takeaway section (takeSec), with the background section above it (2026-07-02)
  assert.match(FEED, /main\.append\(row1, row2, row3, secs, awaitSpin, checklist, delegations\)/);
  assert.match(FEED, /a\._awaitSpin = awaitSpin; a\._awaitWhy = awaitWhy;/);
});

test("the swirl + caption covers awaiting, provisional, and re-check — shown when there's a caption, else hidden", () => {
  // a single computed caption drives the swirl: awaiting → the why; a working provisional placeholder →
  // "Working…"; a targeted-follow-up re-check → "Re-judging…"; a plain-reply rejudging (moved to Working while in flight) →
  // "Re-judging…". The blocked placeholder (needs-input) is NOT covered — it's on you, not in motion.
  // AWAITING: a bg-TASK wait skips the box entirely (the user 2026-07-13) — the compact "Waiting on task"
  // pill carries it (task list one click away, like Sub-goals); a subagent/overlay why keeps the boxed
  // "Awaiting background agents" label (2026-07-04).
  assert.match(FEED, /const awTasks = \(\(aw && aw\.tasks\) \|\| \[\]\)\.filter\(Boolean\);/);
  assert.match(FEED, /if \(aw && !it\.waitingOn && !awTasks\.length\) \{\s*\n\s*awaitingBg = true;/);
  assert.match(FEED, /spinCaption = \/\^waiting on\/i\.test\(why\) \? why\.charAt\(0\)\.toUpperCase\(\) \+ why\.slice\(1\)\s*\n\s*: "Awaiting background agents";/);
  // the provisional chip is PHASE-truthful (the user 2026-07-12): open turn → "Working…" (the judge has
  // nothing to classify yet); turn settled (kernel `judging`) → "Analyzing…" (the planner pass is due/live)
  assert.match(FEED, /\} else if \(it\.provisional && it\.column === "working"\) \{[\s\S]*?spinCaption = it\.judging \? "Analyzing…" : "Working…";/);
  assert.match(FEED, /\} else if \(it\.recheck\) \{\s*\n\s*spinCaption = "Analyzing…";/);
  assert.match(FEED, /\} else if \(it\.rejudging\) \{\s*\n\s*spinCaption = "Analyzing…";/);
  // a resolved card awaiting its distiller line → "Distilling…" (the user 2026-06-29) — the executable rule is
  // distillPending (distiller-line.test.ts); here we just pin that the card branch uses it + sets the caption
  assert.match(FEED, /\} else if \(distillPending\(it\.column === "completed", it\.column === "needs_input", it\.summary, it\.blockSummary, !!it\.blocked\)\) \{[\s\S]*?spinCaption = "Distilling…";/);
  assert.match(FEED, /import \{ distillText, applyDistillLine, distillPending \} from "\.\/distiller-line";/);
  assert.match(FEED, /a\._awaitSpin\.style\.display = spinCaption \? "" : "none";/);
  assert.match(FEED, /a\._awaitWhy\.textContent = spinCaption; a\._awaitSpin\.title = spinTip \|\| spinCaption;/);
});

test("a bg-task wait wears the compact 'Waiting on task' pill that expands the task list (the user 2026-07-13)", () => {
  // the pill joins the mutually-exclusive card sections (bg / summary / subgoals / tasks), swirl inside
  assert.match(FEED, /const taskBtn = el\("button", "fask-secbtn fask-taskbtn"\)/);
  assert.match(FEED, /"bg" \| "summary" \| "subgoals" \| "tasks" \| "none"/);
  assert.match(FEED, /taskList\.length === 1 \? "Waiting on task" : "Waiting on " \+ taskList\.length \+ " tasks"/);
  assert.match(FEED, /taskBtn\.onclick = pick\("tasks"\);/);
  // expanded rows render in the checklist spot, same view as Sub-goals, the swirl as each row's mark
  assert.match(FEED, /if \(choice === "tasks"\) \{[\s\S]*?el\("div", "fcheck ftask"\)[\s\S]*?ftask-swirl/);
  assert.match(CSS, /\.fask-taskbtn \{ display: inline-flex/);
  assert.match(CSS, /\.ftask-swirl\.fask-awaiting-swirl/);
});

test("each case carries a concise tooltip on the swirl (hover → the key idea, not an essay)", () => {
  assert.match(FEED, /let spinCaption: string \| null = null, spinTip = "", awaitingBg = false;/);
  // tooltips are short and plain-spoken (the user 2026-06-29): the key idea, no LLM-essay phrasing, no em dashes
  assert.match(FEED, /"A new prompt, still running\. Sorted into a goal once this stretch of work finishes\.";/);
  assert.match(FEED, /"This stretch of work finished; the judge is sorting it into a goal\."/);
  assert.match(FEED, /spinTip = "You followed up\. Reopened to Working; the judge will resolve it or re-block it\.";/);
  assert.match(FEED, /spinTip = "You replied on this thread\. Moved to Working while the reply runs; it comes back if the judge re-confirms the block\.";/);
  // no em dashes anywhere in the swirl tooltips (JLD + the user's house style ban them)
  assert.doesNotMatch(FEED, /spinTip = "[^"]*—/);
  assert.match(FEED, /a\._awaitSpin\.title = spinTip \|\| spinCaption;/);
});

test("the swirl's Analyzing caption REPLACES the '↩ re-judging' chip (no double-labeling)", () => {
  assert.match(FEED, /if \(spinCaption === "Analyzing…"\) a\._followedup\.style\.display = "none";/);
});

test("the awaiting case gets a rounded box, its swirl SPINS, and its caption wraps to two lines (the user 2026-07-04)", () => {
  // the awaiting-background-agents case wears the box (its distinct read); the class marks it so
  assert.match(FEED, /a\._awaitSpin\.classList\.toggle\("await-paused", awaitingBg\);/);
  // rounded outline box
  assert.match(CSS, /\.fask-awaiting\.await-paused \{[\s\S]*?border: 1px solid var\(--box-border\); border-radius: 8px;/);
  // the swirl now SPINS here too (the user 2026-07-04) — no per-box animation:none override remains
  assert.doesNotMatch(CSS, /\.fask-awaiting\.await-paused \.fask-awaiting-swirl \{ animation: none/);
  // the caption WRAPS to up to two lines instead of truncating with an ellipsis, so the full message reads
  assert.match(CSS, /\.fask-awaiting-why \{[\s\S]*?-webkit-line-clamp: 2;/);
  assert.doesNotMatch(CSS, /\.fask-awaiting-why \{[^}]*text-overflow: ellipsis; white-space: nowrap;/);
  // the box top-aligns so a two-line caption sits cleanly beside the glyph
  assert.match(CSS, /\.fask-awaiting\.await-paused \{[\s\S]*?align-items: flex-start;/);
});

test("the swirl uses the shared glyph, spins SLOWER (calmer) + reverse like the loader, and respects reduced-motion", () => {
  assert.match(CSS, /\.fask-awaiting-swirl \{[\s\S]*?url\(\.\.\/media\/romp-swirl-glyph\.svg\)/);
  assert.match(CSS, /animation: fask-swirl-spin 2\.4s linear infinite;/);   // slowed from 1.4s (the user 2026-06-29)
  assert.match(CSS, /@keyframes fask-swirl-spin \{ to \{ transform: rotate\(-360deg\); \} \}/);   // reverse, like rl-spin
  assert.match(CSS, /@media \(prefers-reduced-motion: reduce\) \{ \.fask-awaiting-swirl \{ animation: none; \} \}/);
});
