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
const FEED = fs.readFileSync(path.join(UI, "feed.ts"), "utf8");
const NOTICE_FACE = fs.readFileSync(path.join(UI, "notice-face.ts"), "utf8");
const fn = (name: string) => { const i = RENDER.indexOf("function " + name + "("); assert.ok(i >= 0, name); return RENDER.slice(i, RENDER.indexOf("\n}\n", i) + 3); };

test("the status carries the rows and the box renders on every status change beside the background box", () => {
  assert.match(RENDER, /interface Status \{ state: ChipState; sinceEpoch: number \| null; modelFallback\?: ModelFallback \| null; notices\?: ChatNotice\[\] \| null;/, "the slice on the status, after main's model-fallback field");
  assert.match(RENDER, /interface ChatNotice \{ itemId: string; key: string; rev: number; title: string; body: string; producer: string; attachment\?: NoticeAttachment \| null;\s*\n\s*actions: \{ label: string; kind\?: string; route\?: string; body: Record<string, unknown> \}\[\] \}/, "the row carries the feed card's attachment too (low e)");
  // awaitKey is the status key every status-carrying frame compares (the T225 pins): the rows are part of it, so a hold or a
  // decision repaints the box through the same awaitChanged road as the background box
  assert.match(fn("awaitKey"), /\(st\.notices \|\| \[\]\)\.map\(\(n\) => n\.itemId \+ "\/" \+ \(n\.actions \|\| \[\]\)\.length\)\]\);/);
  assert.match(fn("awaitChanged"), /if \(sid === activeId\) renderBgTasks\(\);\s*\n\s*if \(sid === activeId\) renderNotices\(\);/);
  assert.match(RENDER, /renderBgTasks\(\); \/\/ swap in the active session's background-task box \(or hide if none\)\s*\n\s*renderNotices\(\); \/\/ swap in the active session's approval box/, "the tab switch");
  assert.match(RENDER, /    renderBgTasks\(\);\s*\n\s*renderNotices\(\);\s*\n\s*\} else if \(!activeId\) \{/, "the session frame");
});

test("the box: rows keyed by the notice id and reconciled in place, the shared notice face, the kernel's actions as buttons naming their act and index", () => {
  const r = fn("renderNotices");
  assert.match(r, /const host = document\.getElementById\("notices"\);/);
  assert.match(r, /const rows: ChatNotice\[\] = \(s && s\.status && s\.status\.notices\) \|\| \[\];/);
  assert.match(r, /if \(!s \|\| !activeId \|\| !rows\.length\) \{ host\.replaceChildren\(\); host\.style\.display = "none"; return; \}/, "hidden with no row");
  assert.doesNotMatch(r.replace(/if \(!s \|\| !activeId \|\| !rows\.length\) \{ host\.replaceChildren\(\);[^\n]*/, ""), /host\.replaceChildren\(\)/, "with rows, the box is never rebuilt whole: a press must survive a frame (the review of PR 1890, medium 1)");
  assert.match(r, /for \(const r of Array\.from\(host\.querySelectorAll<HTMLElement>\("\.ntc-row"\)\)\) if \(!want\.has\(r\.dataset\.item \|\| ""\)\) r\.remove\(\);/, "a row that left leaves");
  assert.match(r, /if \(!row\) \{ row = buildNoticeRow\(n, s\.id\);/); assert.match(r, /updateNoticeRow\(row, n, s\.id\);/, "an existing row is updated in place");
  const u = fn("updateNoticeRow");
  assert.match(u, /if \(body && row\._body !== \(n\.body \|\| ""\)\) \{ body\.replaceChildren\(\.\.\.noticeBodyNodes\(n\.body \|\| ""\)\);/, "the body through the shared face (low e)");
  assert.match(u, /att\.replaceChildren\(\.\.\.noticeAttachmentNodes\(n\.attachment, sid\)\);/, "the attachment through the shared face");
  assert.match(u, /const sig = noticeActionsSig\(n\);\s*\n\s*if \(row\._sig !== sig\) \{/, "the buttons and the refusal line are rebuilt only when the row's own actions change");
  const b = fn("buildNoticeRow");
  assert.match(b, /row\.className = "ntc-row"; row\.dataset\.item = n\.itemId;/, "the row is keyed by the notice id: the kernel's answer finds it");
  const plain = fn("noticeRowPlain");
  assert.match(plain, /const deny = act\.kind === "quarantine" && !!act\.body && \(act\.body as any\)\.verdict === "deny";/);
  assert.match(plain, /noticeButton\(act\.label, deny \? "ntc-deny" : "ntc-ok", deny \? "ntc-deny-step" : "ntc-go", i\)/, "an approve goes at once; a deny opens the note first");
  const step = fn("noticeRowDenyStep");
  assert.match(step, /noticeButton\("Deny & send note", "ntc-deny", "ntc-deny-note", idx\), noticeButton\("Deny without note", "ntc-deny", "ntc-deny-bare", idx\), noticeButton\("Back", "ntc-back", "ntc-back", idx\)/);
  assert.doesNotMatch(r + u + b + plain + step, /Edit/, "nobody edits held mail");
  assert.match(RENDER, /import \{ noticeBodyNodes, noticeAttachmentNodes, type NoticeAttachment \} from "\.\/notice-face";/);
  assert.match(FEED, /import \{ noticeBodyNodes, noticeAttachmentNodes \} from "\.\/notice-face";/, "the feed card reads the same module");
  assert.doesNotMatch(FEED, /function noticeBodyNodes/, "one definition, in notice-face.ts");
  assert.match(NOTICE_FACE, /export function noticeBodyNodes\(md: string\): Node\[\]/); assert.match(NOTICE_FACE, /export function noticeAttachmentNodes\(att: NoticeAttachment \| null \| undefined, sid: string\): HTMLElement\[\]/);
});

test("the clicks ride one delegate on the stable container; every button of the row latches on a decision; the kind and the note ride the wire", () => {
  const i = RENDER.indexOf('const host = document.getElementById("notices");\n  if (!host) return;\n  const rowOf');
  assert.ok(i >= 0, "the delegate installs on #notices once");
  const d = RENDER.slice(i, RENDER.indexOf("})();", i));
  assert.match(d, /delegate\(host, \{/);
  for (const act of ["ntc-go", "ntc-deny-step", "ntc-deny-note", "ntc-deny-bare", "ntc-back"]) assert.ok(d.includes('"' + act + '":'), act);
  assert.match(d, /return \(\(s && s\.status && s\.status\.notices\) \|\| \[\]\)\.find\(\(n\) => n\.itemId === row\.dataset\.item\) \|\| null;/, "the notice is read from the active frame at click time, never a stale closure");
  assert.match(d, /const kind = act\.kind \|\| \(act\.route === "\/send" \? "send" : ""\);/);
  assert.match(d, /vscodeApi\?\.postMessage\(\{ type: "noticeAction", itemId: n\.itemId, sid: activeId, kind, body: act\.body, \.\.\.\(input \? \{ input \} : \{\}\) \}\);/, "the same wire as the feed card");
  assert.match(d, /for \(const b of Array\.from\(row\.querySelectorAll\("button"\)\) as HTMLButtonElement\[\]\) b\.disabled = true;/, "every button of the row latches");
  assert.match(d, /go\(p\[0\], p\[1\], p\[2\], el as HTMLButtonElement, t \? \{ note: t \} : undefined\)/, "the note rides as input, trimmed, or not at all");
});

test("the kernel's answer re-arms the row on a refusal, saying why in the row, and drops it on a success; the box is a box below; the slice's ids wear the host", () => {
  const i = RENDER.indexOf('else if (m.type === "noticeActionDone" && typeof m.itemId === "string" && m.itemId) {');
  assert.ok(i >= 0, "the handler sits in the inbound dispatch");
  const h = RENDER.slice(i, RENDER.indexOf('else if (m.type === "err"', i));
  assert.match(h, /document\.querySelector<HTMLElement>\(noticeRowSelector\(m\.itemId\)\)/, "the row by the answer's id (a remote host's is prefixed on the way in, like the row's)");
  assert.match(h, /if \(m\.ok\) \{ row\.remove\(\);/);
  assert.match(h, /b\.disabled = false; b\.textContent = \(b as any\)\._idle \|\| b\.textContent;/);
  assert.match(h, /e\.textContent = "Refused: " \+ String\(m\.error \|\| "the kernel did not say why"\); e\.style\.display = "";/);
  assert.match(RENDER, /for \(const boxId of \["notices", "bg-tasks", "footer"\]\) \{/, "the bottom-box rule covers the approval box (low a)");
  const FED = fs.readFileSync(path.join(UI, "federation.ts"), "utf8");
  assert.match(FED, /out\.status = \{ \.\.\.out\.status, notices: out\.status\.notices\.map\(\(n: any\) => \(n && typeof n === "object" && typeof n\.itemId === "string"\) \? \{ \.\.\.n, itemId: prefixNoticeId\(host, n\.itemId\) \} : n\) \};/, "the slice's ids wear the host (medium 2)");
});

test("the box's chrome: the background box's frame with the working gold's edge, above it, dense-chrome aware", () => {
  assert.match(CSS, /#notices \{ flex: 0 0 auto; min-height: 0; max-height: min\(40vh, 280px\); overflow: auto; box-sizing: border-box; margin: 8px 10px 0;\s*\n\s*border: 1px solid var\(--box-border\); border-left: 3px solid var\(--st-working-bg\); border-radius: 8px; background: var\(--box-bg\);/);
  assert.match(CSS, /\.ntc-body \{[^}]*-webkit-line-clamp: 4;/, "the message text clamped");
  assert.match(CSS, /\.ntc-btn\.ntc-deny \{ color: #e5484d;/); assert.match(CSS, /\.ntc-btn\.ntc-ok \{ color: var\(--accent\);/);
  assert.match(CSS, /body\.dense-chrome #notices \{ margin: 4px 10px 0; \}/);
  assert.match(CSS, /\.ntc-attach \.fask-nimg \{ display: block; max-width: 100%;/, "the pinned picture in the row");
  assert.ok(CSS.indexOf("#notices {") > CSS.indexOf("#bg-tasks {"), "declared beside the background box's rules");
});
