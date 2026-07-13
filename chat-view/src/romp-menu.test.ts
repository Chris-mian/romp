// The romp status-bar dropdown's decision core: usage summary formatting, the
// menu's fixed sections, the settings submenu reflecting the kernel's current
// values, and the setting→kernel-op mapping (the kernel _dispatch_ws contract).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { buildMenu, usageSummary, usageResetLine } from "./romp-menu";

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

test("the Settings item opens the shared gear modal (not a native submenu)", () => {
  const settings = buildMenu(null, 0).find((i) => i.action === "settings");
  assert.ok(settings, "menu must offer Settings");
  assert.match(settings!.description || "", /modal/);
});
