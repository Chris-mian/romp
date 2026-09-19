// The held message from a DIRECTED federated peer is a NOTICE CARD since 2026-09-19 (plans/notice-cards.md, "Action kinds
// and the held-mail card"): the kernel posts it under the RECIPIENT session with the message id as its key, producer
// postal, and two stored actions of the quarantine KIND (Approve delivers, Deny drops, both through the bus's act road; no
// Edit: nobody edits mail). The pane keeps no hand-built family for it any more: these pins hold the removal (no
// qApprove/qDeny, no quarantine body, no decision dialog, no blocked flavour, no render-counter exemption in the gate)
// and the shapes that replaced it (the kind on the noticeAction wire, the deny-note prompt, Clear as every card's). The
// behaviour rides feed-render-incremental.test.ts (the harness boots feed.ts). Source-pin, like the other feed-*.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const GATE = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed-card-gate.ts"), "utf8");
const BOARD = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "board-def.ts"), "utf8");

test("the hand-built quarantine family left the pane: no Approve/Deny buttons of its own, no held body, no decision dialog, no blocked flavour", () => {
  for (const gone of [/qApprove/, /qDeny/, /\bqbody\b/, /_qBody/, /showQuarantineDialog/, /function quarWho/, /isQuar\b/, /quarantineDecision/, /quarantineRefused/,
                      /blocked\.state === "quarantine"/, /blocked\.state !== "quarantine"/, /mid\?: string; frm\?: string; to\?: string; origin\?: string/])
    assert.doesNotMatch(FEED, gone, "left 2026-09-19: " + gone);
  assert.match(FEED, /actions\.append\(revive\);/, "row two's action corner keeps Revive alone");
  assert.match(FEED, /main\.append\(row1, row2, row3, secs, nbody, nattach, nactions, awaitSpin, checklist, delegations\)/);
  assert.match(FEED, /const showBlk = !!it\.blocked && !isApiErr && !isJudgeAuth;/, "no exclusion for a flavour that no longer exists");
  assert.match(FEED, /function clearable\(it: AskItem\): boolean \{\s*\n\s*return !it\.provisional;/, "Clear dismisses a held message's card as any card (the held file stays)");
});

test("a notice action posts its KIND on the wire, with the stored body; an older frame's route reads as send; only a held-mail Deny takes a click-time input", () => {
  assert.match(FEED, /actions: \{ label: string; kind\?: string; route\?: string; body: Record<string, unknown> \}\[\];/, "the record: kind, with route for an older frame");
  assert.match(FEED, /const kind = act\.kind \|\| \(act\.route === "\/send" \? "send" : ""\);/);
  assert.match(FEED, /vscodeApi\?\.postMessage\(\{ type: "noticeAction", itemId: it\.itemId, sid: it\.sid, kind, body: act\.body, \.\.\.\(input \? \{ input \} : \{\}\) \}\);/,
    "kind and body, the input member only when the click made one; the sid rides for federation");
  assert.match(FEED, /if \(kind === "quarantine" && act\.body && \(act\.body as any\)\.verdict === "deny"\) showDenyNoteDialog\(\(note\) => go\(note \? \{ note \} : undefined\)\);\s*\n\s*else go\(\);/);
  assert.doesNotMatch(FEED, /type: "noticeAction"[^\n]*route:/, "no route on the wire");
});

test("the deny-note prompt: on document.body, two choices and no Cancel, the backdrop closes without deciding", () => {
  const dlg = FEED.slice(FEED.indexOf("function showDenyNoteDialog("), FEED.indexOf("function showPickerDialog"));
  assert.ok(dlg.length > 0 && dlg.length < 3000, "one small function");
  assert.match(dlg, /document\.body\.appendChild\(overlay\)/);
  assert.match(dlg, /el\("textarea", "qdlg-text qdlg-feedback"\)/);
  assert.match(dlg, /withNote\.textContent = "Deny & send note"/); assert.match(dlg, /bare\.textContent = "Deny without note"/);
  assert.match(dlg, /onDeny\(note \|\| undefined\)/); assert.match(dlg, /bare\.onclick = \(\) => \{ overlay\.remove\(\); onDeny\(undefined\); \};/);
  assert.doesNotMatch(dlg, /"Cancel"/, "no Cancel button (the user 2026-07-26: approve or deny, nothing else)");
  assert.match(dlg, /if \(e\.target === overlay\) overlay\.remove\(\)/, "the backdrop is the only no-decision exit");
  assert.doesNotMatch(dlg, /qdlg-view/, "no read-only body view: the message text is the card's body and the modal's");
});

test("the card gate lost the quarantine term and the per-render counter; the board's kind table lost the quarantine kind", () => {
  assert.doesNotMatch(GATE, /quarantine/); assert.doesNotMatch(GATE, /\bseq\b/); assert.doesNotMatch(GATE, /blocked\?:/, "the slice reads no blocked flavour");
  assert.doesNotMatch(FEED, /renderSeq/, "no render counter left behind");
  assert.match(BOARD, /export type KindId = "goal" \| "placeholder" \| "parked" \| "notice";/);
  assert.match(BOARD, /export const KIND_IDS: readonly KindId\[\] = \["goal", "placeholder", "parked", "notice"\];/);
  assert.doesNotMatch(BOARD, /quarantine: \{/, "no quarantine descriptor");
  assert.doesNotMatch(BOARD, /st === "quarantine"/, "kindOf has no quarantine branch");
});

// kept from the retired quarantine-route pins: the per-frame colour index outlives the held gist that first needed it
test("the colour index is built from the merged payload, keyed the way a peer addresses a session", () => {
  assert.match(FEED, /const sessionColors = new Map<string, string>\(\)/);
  assert.match(FEED, /sessionColors\.set\(a\.name, a\.color\.bg\)/);
  assert.match(FEED, /sessionColors\.set\(a\.sid\.slice\(0, c\) \+ ":" \+ a\.name, a\.color\.bg\)/,
    "a remote session is also indexed under its host, which is how the sender is addressed");
});
