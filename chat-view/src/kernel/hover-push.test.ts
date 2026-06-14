// Hover-push nonce contract (the user 2026-06-12): the modal→timeline highlight
// lagged the chat because the timeline hover round-tripped through
// timeline-hover.json → fs.watch → a FULL tl.build() rebuild, while the chat glow
// was a direct ws push. The fix adds a direct push to the kernel's own /timeline
// clients that SUPPLEMENTS the file write (the file stays the cross-front-end
// channel for VS Code trackchanges + the Obsidian vault). For the push and a
// trailing data-poll not to fight, both must carry the SAME monotonic nonce — so
// hoverTimeline now assigns the nonce at CALL time and RETURNS it, and the
// debounced write commits that exact value. These pin that contract.
import * as fs from "fs";
import * as os from "os";
import * as path from "path";

// state-dir helpers read XDG_STATE_HOME at call time; set it before any write.
const TEST_STATE = fs.mkdtempSync(path.join(os.tmpdir(), "romp-hover-test-"));
process.env.XDG_STATE_HOME = TEST_STATE;

import { test } from "node:test";
import * as assert from "node:assert/strict";
import { hoverTimeline, ROMP_STATE, ROMP_TIMELINE_HOVER } from "./state";

fs.mkdirSync(ROMP_STATE(), { recursive: true });
const settle = () => new Promise((r) => setTimeout(r, 80)); // > the 40ms write debounce

test("hoverTimeline returns a strictly-monotonic nonce per call", () => {
  const a = hoverTimeline(["x"]);
  const b = hoverTimeline(["y"]);
  const c = hoverTimeline(null);
  assert.ok(b > a && c > b, `expected increasing nonces, got ${a},${b},${c}`);
});

test("the file commits the exact nonce returned to the pusher (push ties, never clobbers)", async () => {
  const n = hoverTimeline(["only"]);
  await settle();
  const f = JSON.parse(fs.readFileSync(ROMP_TIMELINE_HOVER(), "utf8"));
  assert.equal(f.nonce, n, "file nonce must equal the nonce handed to the direct push");
  assert.deepEqual(f.ids, ["only"]);
  assert.equal(f.id, "only");
});

test("calls coalesced within the debounce commit the latest ids under the latest nonce", async () => {
  const first = hoverTimeline(["a"]);
  const last = hoverTimeline(["b"]); // supersedes within the 40ms window
  await settle();
  const f = JSON.parse(fs.readFileSync(ROMP_TIMELINE_HOVER(), "utf8"));
  assert.ok(last > first);
  assert.equal(f.nonce, last);
  assert.deepEqual(f.ids, ["b"]);
});

test("a clear (null) commits null ids under its own higher nonce", async () => {
  hoverTimeline(["lit"]);
  const clearN = hoverTimeline(null);
  await settle();
  const f = JSON.parse(fs.readFileSync(ROMP_TIMELINE_HOVER(), "utf8"));
  assert.equal(f.nonce, clearN);
  assert.equal(f.ids, null);
  assert.equal(f.id, null);
});
