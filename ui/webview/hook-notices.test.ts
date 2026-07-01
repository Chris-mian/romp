// parseHookNotices turns a slash command's hook-execution echoes (e.g. /compact's "PreCompact [hook]
// completed successfully PostCompact [hook] completed successfully") into structured chips instead of a wall
// of gray prose (the user 2026-06-30). These EXECUTE the parse rather than pin its source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { parseHookNotices } from "./hook-notices";

test("parses each hook notice into its event name + path, keeping the leading result word", () => {
  const text = "Compacted PreCompact [~/.claude/hooks/tmux-status.sh] completed successfully " +
               "PostCompact [~/.claude/hooks/tmux-status.sh] completed successfully";
  const r = parseHookNotices(text);
  assert.ok(r, "hook notices present → not null");
  assert.deepEqual(r!.notices.map((n) => n.evt), ["PreCompact", "PostCompact"]);
  assert.equal(r!.notices[0].path, "~/.claude/hooks/tmux-status.sh");
  assert.equal(r!.lead, "Compacted", "the non-notice remainder is kept as the lead label");
});

test("a normal assistant message (no hook notice) returns null → renders as prose, unchanged", () => {
  assert.equal(parseHookNotices("Here's the plan: first I'll read the file, then edit it."), null);
  assert.equal(parseHookNotices(""), null);
});

test("a lone notice with no leading prose yields an empty lead", () => {
  const r = parseHookNotices("SessionStart [~/.claude/hooks/x.sh] completed successfully");
  assert.ok(r);
  assert.deepEqual(r!.notices.map((n) => n.evt), ["SessionStart"]);
  assert.equal(r!.lead, "");
});

test("does not misfire on prose that merely mentions completion", () => {
  // no bracketed path → not a hook notice
  assert.equal(parseHookNotices("The build completed successfully after two retries."), null);
});
