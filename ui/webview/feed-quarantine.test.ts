// Quarantine card in the feed (per-host trust model): mail from a DIRECTED federated peer is HELD, and
// surfaces as a needs_input card (blocked.state "quarantine") with a read-only body textarea + Approve /
// Edit / Deny. Approve/Deny post a quarantineDecision op carrying the (possibly edited) textarea value;
// Edit just unlocks the textarea. Source-pin (no jsdom for the feed renderer), like the other feed-*.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");

test("the quarantine buttons + body textarea are created and registered", () => {
  assert.match(FEED, /const qApprove = el\("button", "fdismiss fq fq-ok"\)[\s\S]*?qApprove\.textContent = "Approve"/);
  assert.match(FEED, /const qEdit = el\("button", "fdismiss fq"\)[\s\S]*?qEdit\.textContent = "Edit"/);
  assert.match(FEED, /const qDeny = el\("button", "fdismiss fq fq-no"\)[\s\S]*?qDeny\.textContent = "Deny"/);
  assert.match(FEED, /const qbody = el\("textarea", "fask-qbody"\)[\s\S]*?qbody\.readOnly = true/);
  assert.match(FEED, /a\._qApprove = qApprove; a\._qEdit = qEdit; a\._qDeny = qDeny; a\._qBody = qbody;/);
});

test("the blocked type carries the quarantine fields", () => {
  assert.match(FEED, /mid\?: string; frm\?: string; to\?: string; origin\?: string; body\?: string \};\s*\/\/ quarantine/);
});

test("Approve/Deny post a quarantineDecision with the textarea value; Edit unlocks the textarea", () => {
  assert.match(FEED, /const isQuar = it\.blocked\?\.state === "quarantine"/);
  // the block chip is suppressed for a quarantine card (like largeResume)
  assert.match(FEED, /it\.blocked\.state !== "quarantine"/);
  // the verdict carries the (possibly edited) textarea value
  assert.match(FEED, /vscodeApi\?\.postMessage\(\{ type: "quarantineDecision", mid, action, text: qBody\.value \}\)/);
  // Edit only unlocks the body — it does not deliver
  assert.match(FEED, /a\._qEdit\.onclick = [\s\S]*?qBody\.readOnly = false; qBody\.focus\(\)/);
  assert.match(FEED, /a\._qApprove\.onclick = [\s\S]*?decide\("approve", "Delivering…"\)/);
  assert.match(FEED, /a\._qDeny\.onclick = [\s\S]*?decide\("deny", "Denying…"\)/);
  // the body is refreshed from the payload only when the user isn't mid-edit (focus guard)
  assert.match(FEED, /if \(document\.activeElement !== qBody\) qBody\.value = it\.blocked\.body \|\| ""/);
});
