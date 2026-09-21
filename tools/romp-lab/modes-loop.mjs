// The scripted PERMISSION-MODE sweep (T139, the user 2026-08-28: a session in confirmed
// bypassPermissions got a permission ask and sat blocked eleven hours — 'maybe it's not working
// properly; do a sweep to make sure that all of them are working as we would expect'). Drives the
// REAL dashboard through every mode with the same action matrix (a Bash command + a file Write)
// and asserts the CONTRACT per mode:
//   * asks appear when the mode says so, never when it says not (bypass is sampled CONTINUOUSLY —
//     one 'permission' blip fails the phase);
//   * the switcher's DISPLAYED mode always matches what was picked (the badge is read back after
//     every set — the T124 truth family);
//   * a MID-SESSION switch is provably live on the very next action (default → accept: the same
//     Write that asked before the switch must not ask after).
// The per-mode ask EXPECTATIONS are the contract table below — plan is exercised via its Plan-ready
// approval shape. Synthetic content only; cheapest model; exits non-zero naming the first divergence.
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const require2 = createRequire(path.join(ROOT, "vscode-extension", "package.json"));
const { chromium } = require2("playwright");

const PORT = process.env.PORT, TOKEN = process.env.TOKEN, LAB = process.env.LAB_DIR, PROJ = process.env.PROJECT_DIR;
const MODEL = process.env.LAB_MODEL || "Haiku";
const shots = path.join(LAB, "shots");
let phaseN = 0;
const fails = [];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const b = await chromium.launch();
const page = await b.newPage({ viewport: { width: 1280, height: 850 } });
page.on("pageerror", (e) => console.log("PAGEERR", String(e)));
const shot = async (name) => page.screenshot({ path: path.join(shots, `md${String(++phaseN).padStart(2, "0")}-${name}.png`) });
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"} modes:${name}${detail ? " — " + detail : ""}`);
  if (!ok) fails.push(name);
};

// ── shared drivers (the highlight loop's idioms) ──────────────────────────
const newSession = async (name) => {
  // the pane loader intercepts pointer events while up (a reconnect re-shows it) — wait it out
  await page.waitForFunction(() => {
    const sp = document.getElementById("pane-spin");
    return !sp || sp.classList.contains("gone");   // it hides via .gone (opacity+pointer-events), never display
  }, { timeout: 30000 });
  await page.click(".tab.tab-add", { timeout: 8000 });
  await page.waitForSelector("#picker-search", { timeout: 8000 });
  await page.fill("#picker-search", name);
  await page.fill("#picker-dir", PROJ);
  await page.click("#picker-new-btn");
  await page.waitForSelector("#statusline .chip, #statusline .compacting-line", { timeout: 60000 });
  // the meta badges land after the connect settles — picking before they exist is a silent no-op
  // (the first sweep's every-mode failure); the highlight loop always waited for the model badge
  await page.waitForSelector('#statusline .meta-btn[data-kind="model"]', { timeout: 60000 });
  await page.waitForSelector('#statusline .meta-btn[data-kind="mode"]', { timeout: 60000 });
};
const pickMeta = async (kind, wantText) => page.evaluate(async ({ kind, wantText }) => {
  document.body.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));   // fold any open menu (a second pick toggled shut)
  await new Promise((r) => setTimeout(r, 120));
  const btn = document.querySelector(`#statusline .meta-btn[data-kind="${kind}"]`);
  if (!btn) return "no-badge";
  btn.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 250));
  const item = Array.from(document.querySelectorAll(".meta-menu .meta-item"))
    .find((i) => i.textContent.toLowerCase().includes(wantText.toLowerCase()));
  if (!item) return "no-item:" + Array.from(document.querySelectorAll(".meta-menu .meta-item")).map((i) => i.textContent.trim().slice(0, 20)).join("|");
  item.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  return "ok";
}, { kind, wantText });
const modeBadge = () => page.evaluate(() => {
  const btn = document.querySelector('#statusline .meta-btn[data-kind="mode"]');
  return btn ? btn.textContent.trim() : "";
});
const askVisible = () => page.evaluate(() => {
  const la = document.getElementById("live-ask");
  // the LIVE picker's option rows are .ask-live-opt (the transcript's answered cards use .ask-opt —
  // the round-4 lesson: the wrong class made every ask invisible to the driver)
  return !!la && la.style.display !== "none" && !!la.querySelector(".ask-live-opt, .ask-opt");
});
const askHeader = () => page.evaluate(() => {
  const la = document.getElementById("live-ask");
  return la ? la.textContent.slice(0, 200) : "";
});
const answerAsk = async (labelMatch) => page.evaluate((m) => {
  const la = document.getElementById("live-ask");
  if (!la) return "no-ask";
  const opts = Array.from(la.querySelectorAll(".ask-live-opt, .ask-opt"));
  const hit = m ? opts.find((o) => o.textContent.toLowerCase().includes(m.toLowerCase())) : opts[0];
  if (!hit) return "no-opt:" + opts.map((o) => o.textContent.trim().slice(0, 30)).join("|");
  hit.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  return "ok";
}, labelMatch);
const send = async (text) => {
  await page.fill("#composer-input", text);
  await page.keyboard.press("Enter");
};
// run one action turn, collecting every ask that appears (answering Allow each time) until the
// turn settles; samples the state continuously so a bypass blip cannot hide between polls
const runActions = async (label, { allowWith = "" } = {}) => {
  const asks = [];
  const t0 = Date.now();
  let settledQuiet = 0, seenBusy = false;
  while (Date.now() - t0 < 240000) {
    if (await askVisible()) {
      seenBusy = true;
      const head = await askHeader();
      asks.push(head.replace(/\s+/g, " ").slice(0, 120));
      await shot(`${label}-ask${asks.length}`);
      const a = await answerAsk(allowWith);
      if (a !== "ok") { check(`${label}-answerable`, false, a); break; }
      await sleep(600);
      continue;
    }
    const busyNow = await page.evaluate(() => {
      const sl = document.querySelector("#statusline");
      return sl ? /working|permission|blocked|retrying|compacting/i.test(sl.textContent) : false;
    });
    if (busyNow) seenBusy = true;
    // quiet only counts once the turn has demonstrably STARTED — the Working chip lags the send by
    // up to a push (~3s), and the first sweep read that pre-push silence as "settled" (0 asks)
    if (!busyNow && (seenBusy || Date.now() - t0 > 15000)) { if (++settledQuiet >= 4) break; }
    else if (busyNow) settledQuiet = 0;
    await sleep(400);
  }
  return asks;
};

import fs from "node:fs";
const actionsFor = (label) => "Do exactly these two things, then stop: "
  + `1) run this bash command: echo probe-${label}-ok. `
  + `2) use the Write tool to create a file named probe-${label}.txt containing the single word: probe. `
  + "No other tools, no questions.";
const probeWritten = (label) => fs.existsSync(path.join(PROJ, `probe-${label}.txt`));

await page.goto(`http://127.0.0.1:${PORT}/chat?token=${TOKEN}`);
await page.waitForSelector("#composer-input", { timeout: 20000 });

// ── the CONTRACT TABLE the sweep asserts (probed on CLI 2.1.221, T139) ──
// default consults for BOTH actions (no shadowing rules in the lab); accept-edits auto-allows the
// Write and consults for Bash; AUTO is MODEL-DEPENDENT — on the lab's Haiku the live switch
// REFUSES ('auto mode unavailable for this model') and the truth contract is THE REVERT: the
// badge must fall back to the pre-pick mode, never assert the refused one; BYPASS cannot apply
// live (launch-flag-gated) — it applies via the RECONNECT, then nothing ever asks.
const TABLE = [
  { menu: "normal", match: /normal/i, min: 1, max: 4, label: "default" },
  // probed round 5: sandbox-safe Bash (echo) auto-approves WITHOUT a consult in default and
  // acceptEdits alike — default's one ask was the Write; under acceptEdits the Write auto-accepts
  // too, so this benign matrix consults for NOTHING. A consult would still be answerable (0-1).
  { menu: "accept", match: /accept/i, min: 0, max: 1, label: "acceptEdits" },
  { menu: "auto", revertExpected: true, label: "auto" },
  { menu: "bypass", match: /bypass/i, min: 0, max: 0, label: "bypass" },
];
const badgeSettles = async (re, ms = 12000) => {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    const b2 = await modeBadge();
    if (re.test(b2)) return b2;
    await sleep(400);
  }
  return await modeBadge();
};

for (const row of TABLE) {
  await newSession(`mode-${row.label}`);
  console.log(`— ${row.label} —`);
  console.log("model:", await pickMeta("model", MODEL));
  const preBadge = await modeBadge();
  const set = await pickMeta("mode", row.menu);
  check(`${row.label}-set`, set === "ok", set);
  if (row.revertExpected) {
    // the refused-live class (auto on the lab's model): the badge must NOT keep asserting the
    // refused pick — it reverts to the pre-pick mode (the T124 truth family, live on the stack)
    const back = await badgeSettles(new RegExp(preBadge.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace("▾", ""), "i"));
    check(`${row.label}-refusal-reverts`, !/auto/i.test(back),
      `badge settled at ${JSON.stringify(back)} (pre-pick ${JSON.stringify(preBadge)})`);
    continue;   // the ask matrix is seed-mode-dependent after a revert — nothing more to assert here
  }
  const badge = await badgeSettles(row.match);
  check(`${row.label}-switcher-truth`, row.match.test(badge),
    `badge reads ${JSON.stringify(badge)} after picking ${row.menu}`);
  await send(actionsFor(row.label));
  let asks = await runActions(row.label);
  if (asks.length === 0 && !probeWritten(row.label)) {
    // the lab model occasionally settles without touching a tool (a compliance blip, not
    // machinery — round 6's bypass session answered toollessly where round 5's ran both actions).
    // ONE bounded retry, logged — never silent (the no-silent-caps rule).
    console.log(`retry: ${row.label} settled toolless — re-sending the actions once`);
    await send(actionsFor(row.label) + " You did not do them yet — do them now.");
    asks = asks.concat(await runActions(row.label + "-retry"));
  }
  check(`${row.label}-ask-count`, asks.length >= row.min && asks.length <= row.max,
    `${asks.length} ask(s): ${asks.join(" || ") || "none"}`);
  if (row.label === "bypass")
    check("bypass-never-blocks", asks.length === 0,
      asks.length ? "an ask under bypass — the specimen class" : "");
  check(`${row.label}-actions-ran`, probeWritten(row.label),
    `probe-${row.label}.txt ${probeWritten(row.label) ? "written" : "missing"} (the filesystem is the ground truth)`);
  await shot(`${row.label}-settled`);

  if (row.label === "default") {
    // MID-SESSION SWITCH truth: default → accept; the very next Write must not ask
    const sw = await pickMeta("mode", "accept");
    check("switch-live-set", sw === "ok", sw);
    await sleep(700);
    check("switch-live-badge", /accept/i.test(await modeBadge()), await modeBadge());
    await send("Use the Write tool to overwrite probe.txt with the word: again. Nothing else.");
    const asks2 = await runActions("default-after-switch");
    check("switch-live-on-next-action", !asks2.some((a) => /write|probe.txt/i.test(a)),
      asks2.length ? asks2.join(" || ") : "no asks (the Write auto-accepted)");
  }
}

// ── PLAN mode: the approval shape, not the action matrix ──────────────────
await newSession("mode-plan");
console.log("— plan —");
console.log("model:", await pickMeta("model", MODEL));
const setPlan = await pickMeta("mode", "plan");
check("plan-set", setPlan === "ok", setPlan);
await sleep(700);
check("plan-switcher-truth", /plan/i.test(await modeBadge()), await modeBadge());
await send("Plan how you would create a file named probe.txt containing the word probe. "
  + "When your plan is ready, use the ExitPlanMode tool to present it for approval.");
const planAsks = await runActions("plan", { allowWith: "keep planning" });
check("plan-approval-shape", planAsks.some((a) => /plan/i.test(a)),
  planAsks.join(" || ") || "no Plan-ready approval appeared");

await shot("sweep-done");
await b.close();
if (fails.length) { console.log("MODES SWEEP FAILURES:", fails.join(", ")); process.exit(1); }
console.log("modes sweep: all green");
