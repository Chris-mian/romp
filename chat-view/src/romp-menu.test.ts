// The romp status-bar dropdown's decision core: usage summary formatting, the
// menu's fixed sections, the settings submenu reflecting the kernel's current
// values, and the setting→kernel-op mapping (the kernel _dispatch_ws contract).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { buildMenu, settingsMenu, settingOp, usageSummary, usageResetLine } from "./romp-menu";

const USAGE = {
  fiveHour: { pct: 91, resetsAt: 10_000 + 2 * 3600 + 5 * 60 },
  sevenDay: { pct: 44, resetsAt: 10_000 + 90_000 },
  fable: { pct: 75, resetsAt: 10_000 + 90_000 },
};

test("usageSummary names each window with its percent", () => {
  assert.equal(usageSummary(USAGE), "session 91% · week 44% · Fable 5 75%");
  assert.equal(usageSummary({ sevenDay: { pct: 12 } }), "week 12%");
  assert.equal(usageSummary(null), "");
  assert.equal(usageSummary({}), "");
});

test("usageResetLine reports the TIGHTEST window's reset countdown", () => {
  assert.equal(usageResetLine(USAGE, 10_000), "session resets in 2h05m");
  assert.equal(usageResetLine({ fiveHour: { pct: 10, resetsAt: 10_300 } }, 10_000), "session resets in 5m");
  assert.equal(usageResetLine(null, 10_000), "");
});

test("buildMenu leads with usage when known, then surfaces, actions, settings", () => {
  const items = buildMenu(USAGE, 10_000);
  assert.ok(items[0].label.startsWith("Usage: session 91%"));
  const actions = items.map((i) => i.action);
  for (const a of ["openChat", "openFeed", "openTimeline", "openFleet", "cite", "worktree", "diff", "settings"])
    assert.ok(actions.includes(a), `missing ${a}`);
});

test("buildMenu omits the usage row when nothing is known", () => {
  assert.equal(buildMenu(null, 10_000)[0].action, "openChat");
});

test("settingsMenu shows the kernel's CURRENT values from /version", () => {
  const items = settingsMenu({
    autoNudge: true, judgeModel: "sonnet", judgeEffort: "", indexModel: "haiku",
    indexEffort: "low", defaultDir: "~/GitRepos/romp",
  });
  const byAction = Object.fromEntries(items.map((i) => [i.action, i.label]));
  assert.equal(byAction["setting:autoNudge"], "Auto Nudge: on");
  assert.equal(byAction["setting:judgeModel"], "Judge model: sonnet");
  assert.equal(byAction["setting:judgeEffort"], "Judge effort: default");
  assert.equal(byAction["setting:indexEffort"], "Index effort: low");
  assert.equal(byAction["setting:defaultDir"], "Default directory: ~/GitRepos/romp");
  assert.ok(byAction["setting:browser"], "the full gear must stay reachable in the browser");
});

test("settingOp maps each setting to the kernel's exact op + param name", () => {
  assert.deepEqual(settingOp("setting:autoNudge", true), { type: "setAutoNudge", enabled: true });
  assert.deepEqual(settingOp("setting:judgeModel", "opus"), { type: "setJudgeModel", model: "opus" });
  assert.deepEqual(settingOp("setting:indexModel", "haiku"), { type: "setIndexModel", model: "haiku" });
  assert.deepEqual(settingOp("setting:judgeEffort", ""), { type: "setJudgeEffort", effort: "" });
  assert.deepEqual(settingOp("setting:indexEffort", "max"), { type: "setIndexEffort", effort: "max" });
  assert.deepEqual(settingOp("setting:defaultDir", "~/x"), { type: "setDefaultDir", dir: "~/x" });
  assert.equal(settingOp("setting:browser", ""), null);
});
