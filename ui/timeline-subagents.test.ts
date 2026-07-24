// Live Task-subagent count on the WORKING badge (the user 2026-06-30): the SDK backend tracks the subagents
// running right now via the SubagentStart/SubagentStop hooks — the transparency the tmux backend never had —
// and the timeline surfaces the count on the WORKING badge, exactly the way COMPACTING carries its %. No DOM
// harness for the SVG draw path, so pin the wiring at the source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "romp-timeline-view.js"), "utf8");

test("the WORKING badge appends the live Task-subagent count when there are any", () => {
  // reads the count off the session's live `subagents` array (threaded by the kernel from the SDK snapshot)
  assert.match(SRC, /s\.subagents && s\.subagents\.length/);
  // singular/plural, appended to the Working label like Compacting's " 40%". "subagent", not "agent":
  // the session itself is the agent, and these are the Task-spawned children under it (the user 2026-07-24).
  assert.match(SRC, /'Working · ' \+ n \+ \(n === 1 \? ' subagent' : ' subagents'\)/);
  // blank suffix when none → the badge stays a plain "Working"
  assert.match(SRC, /n \? 'Working · '[\s\S]*?: 'Working'/);
});
