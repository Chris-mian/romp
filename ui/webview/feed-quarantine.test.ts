// Quarantine card in the feed (per-host trust model): mail from a DIRECTED federated peer is HELD, and
// surfaces as a needs_input card (blocked.state "quarantine") whose body shows the message IN FULL
// (read-only prose — the human is deciding on it), with Approve / Edit / Deny. Approve/Deny post a
// quarantineDecision op that carries the card's sid, so the federation manager routes the verdict to
// the kernel that actually HOLDS the file (a remote hold's Approve used to land on the local kernel
// and silently no-op — the user 2026-07-26). Edit opens a modal editor on document.body, outside the
// re-rendered feed root, so a kernel push mid-edit can't eat the text. Source-pin (no jsdom for the
// feed renderer), like the other feed-*.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");

test("the quarantine buttons + full-message body are created and registered", () => {
  assert.match(FEED, /const qApprove = el\("button", "fdismiss fq fq-ok"\)[\s\S]*?qApprove\.textContent = "Approve"/);
  assert.match(FEED, /const qEdit = el\("button", "fdismiss fq"\)[\s\S]*?qEdit\.textContent = "Edit"/);
  assert.match(FEED, /const qDeny = el\("button", "fdismiss fq fq-no"\)[\s\S]*?qDeny\.textContent = "Deny"/);
  // the body is a read-only prose div (the whole message), NOT a clipped inline textarea
  assert.match(FEED, /const qbody = el\("div", "fask-qbody"\)/);
  assert.doesNotMatch(FEED, /el\("textarea", "fask-qbody"\)/);
  assert.match(FEED, /a\._qApprove = qApprove; a\._qEdit = qEdit; a\._qDeny = qDeny; a\._qBody = qbody;/);
});

test("the blocked type carries the quarantine fields", () => {
  assert.match(FEED, /mid\?: string; frm\?: string; to\?: string; origin\?: string; body\?: string \};\s*\/\/ quarantine/);
});

test("the decision carries the card's sid so a remote hold's verdict reaches the holding kernel", () => {
  assert.match(FEED, /const isQuar = it\.blocked\?\.state === "quarantine"/);
  // the block chip is suppressed for a quarantine card — its own buttons carry the decision
  assert.match(FEED, /it\.blocked\.state !== "quarantine"/);
  // sid rides the op — federation's routeOutbound keys on it (same shape as the askClear fix, 2026-07-02)
  assert.match(FEED, /vscodeApi\?\.postMessage\(\{ type: "quarantineDecision", mid, action, text, sid: it\.sid \}\)/);
  assert.match(FEED, /a\._qApprove\.onclick = [\s\S]*?decide\("approve", "Delivering…", it\.blocked!\.body \|\| ""\)/);
  assert.match(FEED, /a\._qDeny\.onclick = [\s\S]*?decide\("deny", "Denying…", it\.blocked!\.body \|\| ""\)/);
});

test("Edit opens the modal editor; the dialog lives outside the feed render root", () => {
  assert.match(FEED, /a\._qEdit\.onclick = [\s\S]*?showQuarantineEditDialog\(/);
  // the dialog: overlay on document.body (survives feed re-renders), textarea prefilled with the body,
  // Approve delivers the edited text, Deny drops, Cancel keeps the message held
  assert.match(FEED, /function showQuarantineEditDialog\(/);
  const dlg = FEED.slice(FEED.indexOf("function showQuarantineEditDialog"));
  assert.match(dlg, /document\.body\.appendChild\(overlay\)/);
  assert.match(dlg, /el\("textarea", "qdlg-text"\)/);
  assert.match(dlg, /ta\.value = body/);
  assert.match(dlg, /decide\("approve", "Delivering…", ta\.value\)/);
  assert.match(dlg, /decide\("deny", "Denying…", ta\.value\)/);
  assert.match(dlg, /cancel\.onclick = \(\) => overlay\.remove\(\)/);
});
