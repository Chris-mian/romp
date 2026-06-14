// The event-based replacement for the feed's old 15s permission debounce:
// whether a `permission` state is a genuine user-facing block depends on the
// session's permission MODE, never on elapsed time.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { isGenuinePermissionBlock } from "./feed";

test("permission block is decided by mode, not by a timer", () => {
  // Modes that prompt for real (and an unreported "") → a permission IS a block,
  // surfaced immediately — this is what fixes the /model confirm answered in <15s.
  for (const m of ["default", "plan", ""]) {
    assert.equal(isGenuinePermissionBlock(m), true, `${m || "(empty)"} should surface as a block`);
  }
  // Auto-resolving modes: a permission notification is the classifier's transient
  // mid-decision blip (allowed moments later), not a block to flag.
  for (const m of ["acceptEdits", "auto", "dontAsk", "bypassPermissions"]) {
    assert.equal(isGenuinePermissionBlock(m), false, `${m} should be treated as auto-resolved`);
  }
  // Fail safe: an unknown/future mode surfaces rather than hides a possible block.
  assert.equal(isGenuinePermissionBlock("some-future-mode"), true);
});
