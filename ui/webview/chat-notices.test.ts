// The chat page's NEEDS YOU BOX (#notices; plans/needs-you.md, phase three; the approval box of plans/notice-cards.md, "Action
// kinds and the held-mail card", 2026-09-19, before it): the active session's Needs you items that are not hard stops, listed
// above the background box under a "Needs you · N" header, rendered from status.notices on every status change. A goal row
// (kind "goal") offers Reply (the composer takes the card), Continue where the card offers it and Clear, on the card's own
// wires; a notice row posts the same noticeAction wire the feed card posts (the action's KIND with the stored body, a deny's
// optional note as the click's input), re-armed or removed on noticeActionDone, or Clear when it has no stored action. The
// gear's Needs you box switch hides the box and leaves the ring. Source pins (the chat renderer has no jsdom harness); the
// behaviour rides tests/test_held_mail_chat_served.py and tests/test_needs_you_box_chat_served.py.
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
  assert.match(RENDER, /interface ChatNotice \{ itemId: string; key: string; rev: number; title: string; body: string; producer: string; attachment\?: NoticeAttachment \| null;\s*\n\s*actions: \{ label: string; kind\?: string; route\?: string; body: Record<string, unknown> \}\[\];\s*\n\s*kind\?: "goal" \| "notice";[^\n]*\n\s*cont\?: boolean;[^\n]*\n\s*fix\?: "credential" \}/, "the row carries the feed card's attachment too (low e), and since phase three its kind, its Continue offer and its fix");
  // awaitKey is the status key every status-carrying frame compares (the T225 pins): the rows are part of it, so a hold or a
  // decision repaints the box through the same awaitChanged road as the background box
  // by id AND face (the second review of PR 1967): a brief landing, a Continue offered, a retitle or the credential fix repaints the box
  assert.match(fn("awaitKey"), /\(st\.notices \|\| \[\]\)\.map\(\(n\) => JSON\.stringify\(\[n\.itemId, n\.kind \|\| "notice", n\.title \|\| "", n\.body \|\| "", !!n\.cont, n\.fix \|\| "", \(n\.actions \|\| \[\]\)\.length\]\)\)\]\);/);
  assert.match(fn("awaitChanged"), /if \(sid === activeId\) renderBgTasks\(\);\s*\n\s*if \(sid === activeId\) renderNotices\(\);/);
  assert.match(RENDER, /renderBgTasks\(\); \/\/ swap in the active session's background-task box \(or hide if none\)\s*\n\s*renderNotices\(\); \/\/ swap in the active session's approval box/, "the tab switch");
  assert.match(RENDER, /    renderBgTasks\(\);\s*\n\s*renderNotices\(\);\s*\n\s*\} else if \(!activeId\) \{/, "the session frame");
});

test("the box: rows keyed by the notice id and reconciled in place, the shared notice face, the kernel's actions as buttons naming their act and index", () => {
  const r = fn("renderNotices");
  assert.match(r, /const host = document\.getElementById\("notices"\);/);
  assert.match(r, /const rows: ChatNotice\[\] = \(s && s\.status && s\.status\.notices\) \|\| \[\];/);
  assert.match(r, /if \(!s \|\| !activeId \|\| !rows\.length \|\| !settings\.needsBox\) \{ host\.replaceChildren\(\); host\.style\.display = "none"; return; \}/, "hidden with no row, and under the gear's switch (phase three)");
  assert.doesNotMatch(r.replace(/if \(!s \|\| !activeId \|\| !rows\.length \|\| !settings\.needsBox\) \{ host\.replaceChildren\(\);[^\n]*/, ""), /host\.replaceChildren\(\)/, "with rows, the box is never rebuilt whole: a press must survive a frame (the review of PR 1890, medium 1)");
  assert.match(r, /let head = host\.querySelector<HTMLElement>\("\.ntc-head"\);\s*\n\s*if \(!head\) \{ head = buildNoticeHead\(\); host\.prepend\(head\); \}/, "the header is built once and kept");
  assert.match(r, /lab\.textContent = "Needs you · " \+ rows\.length;/, "the title with the count");
  assert.match(r, /let prev: HTMLElement = head;/, "the rows follow the header in the frame's order");
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
  // `held` (the second executed review of PR 1935, carried here): a delivery whose dismissal's write refused keeps the row with its
  // buttons spent and says so; a plain success drops the row; a refusal re-arms the buttons and says why
  assert.match(h, /if \(m\.ok && !m\.held\) \{ row\.remove\(\);/);
  assert.match(h, /if \(!m\.ok\) for \(const b of Array\.from\(row\.querySelectorAll\("button"\)\) as HTMLButtonElement\[\]\) \{ b\.disabled = false; b\.textContent = \(b as any\)\._idle \|\| b\.textContent; \}/);
  assert.match(h, /e\.textContent = \(m\.ok \? "Done, but " : "Refused: "\) \+ String\(m\.error \|\| "the kernel did not say why"\); e\.style\.display = "";/);
  const FEEDSRC = fs.readFileSync(path.join(UI, "feed.ts"), "utf8");
  assert.match(FEEDSRC, /const held = !!m\.ok && !!m\.held;/, "the feed card keeps a held card too");
  assert.match(FEEDSRC, /if \(m\.ok && dismisses && !held\) \{/); assert.match(FEEDSRC, /\} else if \(!held\) \{/, "a held card's buttons stay spent");
  assert.match(FEEDSRC, /else if \(held\) feedToast\("The card's action ran, but " \+ String\(m\.error \|\| "the card could not be dismissed"\) \+ "\."\);/);
  assert.match(RENDER, /const BOXES_BELOW = \["notices", "bg-tasks", "footer"\];/); assert.match(RENDER, /for \(const boxId of BOXES_BELOW\) \{/, "the bottom-box rule covers the approval box (low a); the list is shared with the footprint record (the review of PR 1926)");
  const FED = fs.readFileSync(path.join(UI, "federation.ts"), "utf8");
  assert.match(FED, /out\.status = \{ \.\.\.out\.status, notices: out\.status\.notices\.map\(\(n: any\) => \(n && typeof n === "object" && typeof n\.itemId === "string"\) \? \{ \.\.\.n, itemId: prefixNoticeId\(host, n\.itemId\) \} : n\) \};/, "the slice's ids wear the host (medium 2)");
});

test("a refused act re-arms the row the kernel's reply names, with the reason in the row (the second review of PR 1967)", () => {
  const i = RENDER.indexOf('else if (m.type === "err" && typeof m.text === "string" && m.text) {');
  assert.ok(i >= 0);
  const h = RENDER.slice(i, RENDER.indexOf('else if (m.type === "dirCompletions")', i));
  assert.match(h, /const refusedIds = \[typeof m\.itemId === "string" \? m\.itemId : "", \.\.\.\(Array\.isArray\(m\.itemIds\) \? m\.itemIds\.map\(String\) : \[\]\)\]\.filter\(Boolean\);/,
    "the card the reply names, and the batch a clears-log refusal names");
  assert.match(h, /const row = document\.querySelector<HTMLElement>\(noticeRowSelector\(id\)\); if \(!row\) continue;/);
  assert.match(h, /b\.disabled = false; b\.textContent = \(b as any\)\._idle \|\| b\.textContent;/, "the latched buttons let go with their idle labels");
  assert.match(h, /e\.textContent = "Refused: " \+ title; e\.style\.display = "";/, "and the row says why");
  // the kernel's clears-log refusal names the request: op, the first id and the batch
  const KERNEL = fs.readFileSync(path.join(UI, "..", "..", "kernel", "kernel.py"), "utf8");
  assert.match(KERNEL, /def _gesture_store_refusal\(client, gesture, skipped, ids=None, op=""\):/);
  assert.match(KERNEL, /"itemId": _ids\[0\] if _ids else "", "itemIds": _ids\}\)\)/);
  // the op is the request's own type (a pin elsewhere splits the dispatcher's source on the quoted op name, so no arm repeats its literal)
  for (const arm of ['_gesture_store_refusal(client, "clear", _skipped, ids=[str(msg["itemId"])], op=str(msg.get("type") or ""))',
                     '_gesture_store_refusal(client, "clear", _skipped, ids=_ids, op=str(msg.get("type") or ""))',
                     '_gesture_store_refusal(client, "drop", _skipped, ids=[str(msg["nodeId"])], op=str(msg.get("type") or ""))']) assert.ok(KERNEL.includes(arm), arm);
  assert.equal((KERNEL.match(/if LEDGER_KEY not in _skipped/g) || []).length, 2, "askClear and nodeOverride keep the citation on a refusal...");
  assert.ok(KERNEL.includes("if _ids and LEDGER_KEY not in _skipped:"), "...and so does the batch clear");
});

test("phase three: a goal row's Reply, Continue and Clear on the card's own wires; a no-action notice's Clear; the kind and the offer ride the row's face and its type", () => {
  assert.match(RENDER, /kind\?: "goal" \| "notice";/, "the row says its kind"); assert.match(RENDER, /cont\?: boolean;/, "and whether Continue is offered");
  assert.match(fn("noticeActionsSig"), /JSON\.stringify\(\[n\.kind \|\| "notice", !!n\.cont, n\.fix \|\| "", \(n\.actions \|\| \[\]\)\.map/, "the face signature carries the kind, the offer and the fix: a Continue that appears rebuilds the buttons");
  const plain = fn("noticeRowPlain");
  assert.match(plain, /if \(n\.kind === "goal"\) \{[^]*?acts\.appendChild\(noticeButton\("Reply", "ntc-ok", "ntc-reply", 0\)\);\s*\n\s*if \(n\.cont\) acts\.appendChild\(noticeButton\("Continue", "ntc-ok", "ntc-cont", 1\)\);\s*\n\s*acts\.appendChild\(noticeButton\("Clear", "ntc-clear", "ntc-clear", 2\)\);\s*\n\s*return;/, "a goal row: Reply, Continue where offered, Clear");
  assert.match(plain, /if \(!\(n\.actions \|\| \[\]\)\.length\) \{ acts\.appendChild\(noticeButton\("Clear", "ntc-clear", "ntc-clear", 0\)\); return; \}/, "a notice with no stored action offers Clear");
  const i = RENDER.indexOf('const host = document.getElementById("notices");\n  if (!host) return;\n  const rowOf');
  const d = RENDER.slice(i, RENDER.indexOf("})();", i));
  assert.match(d, /"ntc-reply": \(el\) => \{ const p = item\(el\); if \(p && activeId\) setCitation\(activeId, \{ itemId: p\[1\]\.itemId, title: p\[1\]\.title \}\); \},/, "Reply points the composer at the card, as a feed card click that lands in the chat does; the row stays until the reply is judged");
  assert.match(d, /"ntc-cont": \(el\) => \{[^\n]*vscodeApi\?\.postMessage\(\{ type: "askFollowUp", itemId: p\[1\]\.itemId, sid: activeId, cont: true \}\); latch\(p\[0\], el as HTMLButtonElement\); \},/, "Continue is the card's Continue wire, and the row latches");
  assert.match(d, /"ntc-clear": \(el\) => \{[^\n]*vscodeApi\?\.postMessage\(\{ type: "askClear", itemId: p\[1\]\.itemId, sid: activeId \}\); latch\(p\[0\], el as HTMLButtonElement\); \},/, "Clear is the card's Clear wire, and the row latches");
  assert.match(RENDER, /fix\?: "credential" \}/, "the row says when its one action is the credential fix");
  assert.match(plain, /if \(n\.kind === "goal" && n\.fix === "credential"\) \{[^]*?noticeButton\("Fix credential…", "ntc-ok", "ntc-fix", 0\)\);\s*\n\s*return;/, "the credential row: the fix alone, no Reply, no Continue, no Clear (a Clear would hide the fault while the refusals go on)");
  assert.match(d, /"ntc-fix": \(\) => openSettingsOn\("general"\),/, "the fix opens the settings' General tab, where the Billing block sits");
  assert.match(fn("buildNoticeHead"), /head\.className = "ntc-head";[^]*?el\("span", "ntc-dot"\)[^]*?el\("span", "ntc-label"\)/, "the header: the dot and the label");
  assert.match(RENDER, /onExternalSettingsChange\(\(\) => renderNotices\(\)\);/, "a settings save repaints the box: the gear's switch takes effect at once");
  const SETTINGS = fs.readFileSync(path.join(UI, "settings.ts"), "utf8");
  assert.match(SETTINGS, /needsBox: boolean;/); assert.match(SETTINGS, /needsBox: true,/, "on by default");
  const GEAR = fs.readFileSync(path.join(UI, "gear.js"), "utf8");
  assert.match(GEAR, /<input type=checkbox id=rs-needsbox checked>/, "the row under Chat, on by default");
  assert.match(GEAR, /<b>Needs you box<\/b>/); assert.match(GEAR, /s\.needsBox = nb\.checked; save\(s\);/, "the save the chat page hears"); assert.match(GEAR, /if \(nb\) nb\.checked = s\.needsBox !== false;/, "a store from before the key reads as on");
  assert.match(CSS, /\.ntc-head \{[^}]*border-bottom: 1px solid var\(--box-border\);/, "the header bar in the background box's grammar");
  assert.match(CSS, /\.ntc-head \.ntc-dot \{[^}]*background: var\(--st-needs-bg\); \}/, "the dot in the token");
  assert.doesNotMatch(CSS.slice(CSS.indexOf("#notices {"), CSS.indexOf("\n", CSS.indexOf("#notices {") + 200)), /--st-working-bg|border-left: 3px/, "the working gold's thick edge is gone: one thin line in the token, the awaiting box's dress");
});

test("the box's chrome: the background box's frame, its one thin edge in the Needs you token, a header bar with the dot, above the background box, dense-chrome aware", () => {
  assert.match(CSS, /#notices \{ flex: 0 0 auto; min-height: 0; max-height: min\(40vh, 280px\); overflow: auto; box-sizing: border-box; margin: 8px 10px 0;\s*\n\s*border: 1px solid var\(--st-needs-bg\); border-radius: 8px; background: var\(--box-bg\);/);
  assert.match(CSS, /\.ntc-body \{[^}]*-webkit-line-clamp: 4;/, "the message text clamped");
  assert.match(CSS, /\.ntc-btn\.ntc-deny \{ color: #e5484d;/); assert.match(CSS, /\.ntc-btn\.ntc-ok \{ color: var\(--accent\);/);
  assert.match(CSS, /body\.dense-chrome #notices \{ margin: 4px 10px 0; \}/);
  assert.match(CSS, /\.ntc-attach \.fask-nimg \{ display: block; max-width: 100%;/, "the pinned picture in the row");
  assert.ok(CSS.indexOf("#notices {") > CSS.indexOf("#bg-tasks {"), "declared beside the background box's rules");
});
