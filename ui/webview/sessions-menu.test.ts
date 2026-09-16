import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

// The Sessions pane's row menu (the user 2026-09-16): Rename and Delete on the tab strip's own roads, through the shared
// builder. These pins hold the wiring's shape; the served lab (tests/test_sessions_menu_served.py) drives it.
const PANE = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "fleet.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("a right-click on a session's head, or the menu key on the focused head, opens the shared menu; the goal rows keep their clicks", () => {
  assert.match(PANE, /import \{ openContextMenu, openConfirmBox \} from "\.\/ctx-menu";/);
  assert.match(PANE, /list\.addEventListener\("contextmenu", \(e\) => \{\s*\n\s*const head = \(e\.target as Element\)\.closest\?\.\("\.fl-head"\) as HTMLElement \| null;\s*\n\s*if \(!head \|\| !head\.dataset\.sid\) return;/);
  assert.match(PANE, /if \(e\.key === "ContextMenu" \|\| \(e\.key === "F10" && e\.shiftKey\)\) \{/, "the row's menu key and Shift+F10");
  assert.match(PANE, /showSessionMenu\(r\.left \+ 12, r\.bottom, head\.dataset\.sid, true\);/, "a keyboard opening anchors to the row and focuses the first item; the menu is keyed by sid, never the node");
  assert.match(PANE, /showSessionMenu\(e\.clientX, e\.clientY, head\.dataset\.sid, false\);/);
  assert.match(PANE, /function headOf\(sid: string\): HTMLElement \| null \{\s*\n\s*return document\.querySelector\('#fleet-list \.fl-head\[data-sid="' \+ CSS\.escape\(sid\) \+ '"\]'\) as HTMLElement \| null;/,
    "every pick resolves the row's head by sid at pick time (round two, high: a push between the open and the pick rebuilt the list and the pick worked on a detached row, latching the render hold)");
  assert.equal((PANE.match(/head\.tabIndex = 0; head\.setAttribute\("role", "button"\);/g) || []).length, 2, "both head shapes (a tree's, a provisional-only) are focusable");
});

test("Rename edits in place with the strip's rules and posts the strip's message; render waits while the input is open", () => {
  const fn = PANE.slice(PANE.indexOf("function startRowRename("), PANE.indexOf("function confirmEndSession("));
  assert.match(fn, /const head = headOf\(sid\);/, "the row as it stands now");
  assert.match(fn, /if \(!head \|\| !nm \|\| renameHold\) return;/, "a row that is gone: nothing to edit, nothing held");
  assert.match(fn, /const p = hostPrefix\(full, sid\);[^\n]*\n\s*const base = p \? p\.rest : full;/, "a federated row's name is edited bare (round two, medium: the host prefix was seeded and posted)");
  assert.match(fn, /const fixed = p \? document\.createElement\("span"\) : null;[^\n]*\n\s*if \(fixed\) \{ fixed\.className = "host-prefix"; fixed\.textContent = p!\.host; \}/,
    "the host prefix stays beside the input as the row renders it (round three, low: the input replaced the whole name span and the prefix vanished while editing)");
  assert.match(fn, /nm\.replaceWith\(input\);\s*\n\s*if \(fixed\) input\.before\(fixed\);\s*\n\s*if \(!input\.isConnected\) return;[^\n]*\n\s*renameHold = true;/, "the render hold is set only for an input in the document");
  assert.match(fn, /if \(input\.isConnected\) input\.replaceWith\(nm\);\s*\n\s*fixed\?\.remove\(\);\s*\n\s*if \(hadFocus && row\.isConnected\) row\.focus\(\{ preventScroll: true \}\);/,
    "the edit's end removes the fixed prefix with the input; a keyboard end hands the focus back to the row");
  assert.match(fn, /input\.className = "fl-rename";/);
  assert.match(fn, /if \(e\.key === "Enter"\) \{ e\.preventDefault\(\); finish\(true\); \}\s*\n\s*else if \(e\.key === "Escape"\) \{ e\.preventDefault\(\); finish\(false\); \}/);
  assert.match(fn, /input\.addEventListener\("blur", \(\) => finish\(true\)\);/);
  assert.match(fn, /if \(commit && v && v !== base\) vscodeApi\?\.postMessage\(\{ type: "renameSession", id: sid, name: v \}\);/, "the tab menu's exact wire message, only for a changed non-empty name");
  assert.doesNotMatch(fn, /nm\.textContent = v|textContent = input\.value/, "nothing renamed locally ahead of the kernel");
  assert.match(PANE, /if \(renameHold\) \{ renameDirty = true; return; \}/, "a push mid-edit waits");
  assert.match(fn, /renameHold = false;\s*\n\s*if \(renameDirty\) \{ renameDirty = false; render\(\); \}/, "…and paints when the edit ends");
});

test("Delete is the strip's close-button road: the End confirm with the open goals named, then endSession and closeTab in that order; Cancel does nothing", () => {
  const fn = PANE.slice(PANE.indexOf("function confirmEndSession("), PANE.indexOf("// Fleet-list clicks are DELEGATED"));
  assert.match(fn, /const titles = openTopTitles\(\(sessionRow\(sid\)\?\.ledger\?\.tree \|\| \[\]\) as any\);/, "the live ledger at click time, as the strip reads it (round two, low d)");
  assert.match(PANE, /import \{ openTopTitles, endConfirmDetail, RENAME_SUBLINE, END_SESSION_STANDING \} from "\.\/clear-confirm";/, "the strip's own detail builder and its two sentences");
  assert.match(fn, /openConfirmBox\("End \\u201c" \+ name \+ "\\u201d\?",/, "the strip's title, through the shared confirm box");
  assert.match(fn, /endConfirmDetail\(titles, END_SESSION_STANDING\)/, "the strip's standing sentence, one copy (clear-confirm.ts)");
  assert.match(fn, /\[\{ label: "End session", value: "end", danger: true \}, \{ label: "Cancel", value: "" \}\]/);
  assert.match(fn, /if \(v !== "end"\) return;[^\n]*\n\s*vscodeApi\?\.postMessage\(\{ type: "endSession", id: sid \}\);[^\n]*\n\s*vscodeApi\?\.postMessage\(\{ type: "closeTab", id: sid \}\);/);
  assert.doesNotMatch(fn, /sec\.remove\(\)|head\.remove\(\)|render\(\)/, "the row leaves on the kernel's push, never locally ahead of it");
});

test("the menu's rows: Rename first, Delete second and marked danger; the danger dress is a token rule in the reference sheet", () => {
  const fn = PANE.slice(PANE.indexOf("function showSessionMenu("), PANE.indexOf("function startRowRename("));
  assert.match(fn, /\{ label: "Rename", sub: RENAME_SUBLINE, pick: \(\) => startRowRename\(sid\) \},\s*\n\s*\{ label: "Delete", sub: "ends the session; its history stays on disk", danger: true, pick: \(\) => confirmEndSession\(sid\) \},/,
    "both picks carry the sid alone");
  assert.match(fn, /onClose: \(\) => \{ const h = headOf\(sid\); if \(h\) h\.focus\(\{ preventScroll: true \}\); \}/, "focus returns to the row's head when the menu closes (round two, low a)");
  assert.match(PANE, /document\.addEventListener\("focusin", \(e\) => \{[^\n]*\n\s*focusedHead = \(e\.target as Element\)\.closest\?\.\("\.fl-head"\) as HTMLElement \| null;/,
    "the focused head is remembered as the node, never its sid alone");
  assert.match(PANE, /import \{ openTopTitles, endConfirmDetail, RENAME_SUBLINE, END_SESSION_STANDING \} from "\.\/clear-confirm";/);
  assert.match(CSS, /\.ctx-item-danger \.ctx-item-label \{ color: var\(--vscode-errorForeground, #f48771\); \}/, "a var() with the confirm button's fallback, never a bare hex");
});

test("a rebuild restores the focus only when it removed the head that held it and the pane has the focus; a push never pulls the focus into the pane", () => {
  // round three, high: the round-two restore (focusedHeadSid set, activeElement fallen to body) fired on EVERY push once a head had been focused, so a
  // head left for a goal row and then the chat composer took the window's focus back on the next push and each space pressed the head (openSession)
  const start = PANE.indexOf("function render() {");
  const render = PANE.slice(start, PANE.indexOf("\nfunction ", start + 1));   // render() up to the next top-level function
  assert.match(render, /const held = focusedHead;[^\n]*\n\s*const heldActive = !!held && held\.isConnected && held\.contains\(document\.activeElement\);[^\n]*\n\s*rebuilding = true;\s*\n\s*list\.replaceChildren\(\);\s*\n\s*rebuilding = false;/,
    "the focused node and whether it holds the focus are read before the rebuild, which is bracketed so its focusout is not read as the user leaving");
  assert.match(render, /if \(held && !held\.isConnected\) \{\s*\n\s*const next = heldActive && document\.hasFocus\(\) && held\.dataset\.sid \? headOf\(held\.dataset\.sid\) : null;\s*\n\s*focusedHead = next;\s*\n\s*next\?\.focus\(\{ preventScroll: true \}\);\s*\n\s*\}/,
    "restore only when THIS render removed the node, it held the focus, and the document has the focus; the removed node is dropped either way");
  assert.doesNotMatch(render, /document\.activeElement === document\.body/, "no proxy for the event: the body holding the focus says nothing about how it got there");
  assert.match(PANE, /list\.addEventListener\("focusout", \(e\) => \{[^\n]*\n\s*if \(rebuilding\) return;[^\n]*\n\s*const to = e\.relatedTarget as Node \| null;\s*\n\s*if \(!to \|\| !list\.contains\(to\)\) focusedHead = null;/,
    "focus leaving the list clears the remembered head, except the focusout the rebuild's own removal fires");
  assert.match(PANE, /let focusedHead: HTMLElement \| null = null;/);
  assert.match(PANE, /let rebuilding = false;/);
  assert.equal((PANE.match(/focusedHeadSid/g) || []).length, 0, "the sid-keyed record is gone");
});
