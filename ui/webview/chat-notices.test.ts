// The chat page's APPROVAL BOX (#notices; plans/notice-cards.md, "Action kinds and the held-mail card", 2026-09-19): the
// active session's needs-you notices with actions (a held peer message's Approve and Deny), listed above the background box,
// rendered from status.notices on every status change, posting the same noticeAction wire the feed card posts (the action's
// KIND with the stored body, a deny's optional note as the click's input) and re-armed or removed on noticeActionDone. Source
// pins (the chat renderer has no jsdom harness); the behaviour rides tests/test_held_mail_chat_served.py.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const UI = path.resolve(process.cwd(), "..", "ui", "webview");
const RENDER = fs.readFileSync(path.join(UI, "render.ts"), "utf8");
const CSS = fs.readFileSync(path.join(UI, "styles.css"), "utf8");
const fn = (name: string) => { const i = RENDER.indexOf("function " + name + "("); assert.ok(i >= 0, name); return RENDER.slice(i, RENDER.indexOf("\n}\n", i) + 3); };

test("the status carries the rows and the box renders on every status change beside the background box", () => {
  assert.match(RENDER, /interface Status \{ notices\?: ChatNotice\[\] \| null; state: ChipState;/);
  assert.match(RENDER, /interface ChatNotice \{ itemId: string; key: string; rev: number; title: string; body: string; producer: string;\s*\n\s*actions: \{ label: string; kind\?: string; route\?: string; body: Record<string, unknown> \}\[\] \}/);
  // awaitKey is the status key every status-carrying frame compares (the T225 pins): the rows are part of it, so a hold or a
  // decision repaints the box through the same awaitChanged road as the background box
  assert.match(fn("awaitKey"), /\(st\.notices \|\| \[\]\)\.map\(\(n\) => n\.itemId \+ "\/" \+ \(n\.actions \|\| \[\]\)\.length\)\]\);/);
  assert.match(fn("awaitChanged"), /if \(sid === activeId\) renderBgTasks\(\);\s*\n\s*if \(sid === activeId\) renderNotices\(\);/);
  assert.match(RENDER, /renderBgTasks\(\); \/\/ swap in the active session's background-task box \(or hide if none\)\s*\n\s*renderNotices\(\); \/\/ swap in the active session's approval box/, "the tab switch");
  assert.match(RENDER, /    renderBgTasks\(\);\s*\n\s*renderNotices\(\);\s*\n\s*\} else if \(!activeId\) \{/, "the session frame");
});

test("the box: one row per notice, the message text as the body, the kernel's actions as buttons of their kind", () => {
  const r = fn("renderNotices");
  assert.match(r, /const host = document\.getElementById\("notices"\);/);
  assert.match(r, /const rows: ChatNotice\[\] = \(s && s\.status && s\.status\.notices\) \|\| \[\];/);
  assert.match(r, /if \(!s \|\| !activeId \|\| !rows\.length\) \{ host\.style\.display = "none"; return; \}/, "hidden with no row");
  assert.match(r, /row\.className = "ntc-row"; row\.dataset\.item = n\.itemId;/, "the row is keyed by the notice id: the kernel's answer finds it");
  assert.match(r, /body\.textContent = n\.body \|\| ""; body\.title = n\.body \|\| "";/, "the message text, whole on hover");
  assert.match(r, /const kind = act\.kind \|\| \(act\.route === "\/send" \? "send" : ""\);/);
  assert.match(r, /vscodeApi\?\.postMessage\(\{ type: "noticeAction", itemId: n\.itemId, sid, kind, body: act\.body, \.\.\.\(input \? \{ input \} : \{\}\) \}\);/, "the same wire as the feed card: the kind and the stored body, the input only when the click made one");
  assert.match(r, /const deny = act\.kind === "quarantine" && !!act\.body && \(act\.body as any\)\.verdict === "deny";/);
  assert.match(r, /if \(deny\) denyStep\(act\); else go\(act, b\);/, "an approve goes at once; a deny opens the note first");
  assert.match(r, /button\("Deny & send note", "ntc-deny"\)/); assert.match(r, /button\("Deny without note", "ntc-deny"\)/); assert.match(r, /button\("Back", "ntc-back"\)/);
  assert.match(r, /go\(act, withNote, t \? \{ note: t \} : undefined\)/, "the note rides as input, trimmed, or not at all");
  assert.match(r, /for \(const b of Array\.from\(acts\.querySelectorAll\("button"\)\) as HTMLButtonElement\[\]\) b\.disabled = true; clicked\.textContent = label \+ "…";/, "every button of the row latches on a click");
  assert.doesNotMatch(r, /Edit/, "nobody edits held mail");
});

test("the kernel's answer re-arms the row on a refusal, saying why in the row, and drops it on a success", () => {
  const i = RENDER.indexOf('else if (m.type === "noticeActionDone" && typeof m.itemId === "string" && m.itemId) {');
  assert.ok(i >= 0, "the handler sits in the inbound dispatch");
  const h = RENDER.slice(i, RENDER.indexOf('else if (m.type === "err"', i));
  assert.match(h, /document\.querySelector<HTMLElement>\('#notices \.ntc-row\[data-item="' \+ m\.itemId\.replace\(\/\["\\\\\]\/g, "\\\\\$&"\) \+ '"\]'\)/);
  assert.match(h, /if \(m\.ok\) \{ row\.remove\(\);/);
  assert.match(h, /b\.disabled = false; b\.textContent = \(b as any\)\._idle \|\| b\.textContent;/);
  assert.match(h, /e\.textContent = "Refused: " \+ String\(m\.error \|\| "the kernel did not say why"\); e\.style\.display = "";/);
});

test("the box's chrome: the background box's frame with the ask ring's yellow edge, above it, dense-chrome aware", () => {
  assert.match(CSS, /#notices \{ flex: 0 0 auto; min-height: 0; max-height: min\(40vh, 280px\); overflow: auto; box-sizing: border-box; margin: 8px 10px 0;\s*\n\s*border: 1px solid var\(--box-border\); border-left: 3px solid var\(--st-working-bg\); border-radius: 8px; background: var\(--box-bg\);/);
  assert.match(CSS, /\.ntc-body \{[^}]*-webkit-line-clamp: 4;/, "the message text clamped");
  assert.match(CSS, /\.ntc-btn\.ntc-deny \{ color: #e5484d;/); assert.match(CSS, /\.ntc-btn\.ntc-ok \{ color: var\(--accent\);/);
  assert.match(CSS, /body\.dense-chrome #notices \{ margin: 4px 10px 0; \}/);
  assert.ok(CSS.indexOf("#notices {") > CSS.indexOf("#bg-tasks {"), "declared beside the background box's rules");
});
