// Per-tab hot keys (the user 2026-09-10): a key combination that switches to a session, set from the tab's
// menu and shown minified on the tab; and the commands that cycle the focus between chat columns. The pure
// rules (tab-keys.ts) are executed; the shell's registration and dispatch (palette-main.ts), the dialog's
// solo recording mode (shortcuts-modal.ts), and the pane's menu row, set bookkeeping and repaint (render.ts; the
// keycap on the tab is tab-widgets.ts's) are pinned at source — the repo's convention where there is no DOM.
// Synthetic sids and names only.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { hotkeyCommandId, sidOfHotkeyCommand, loadTabKeys, rememberTabKey, forgetTabKey, tabChord, TABKEYS_KEY,
         unboundTabKeys, goneTabKeys, renamedTabKeys } from "./tab-keys";

const read = (f: string) => fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", f), "utf8");
const RENDER = read("render.ts");
const MAIN = read("palette-main.ts");
const MODAL = read("shortcuts-modal.ts");
const CSS = read("styles.css");
const SID = "11111111-2222-4333-8444-000000000501";

function store(init: Record<string, string> = {}) {
  const m = new Map(Object.entries(init));
  return { getItem: (k: string) => (m.has(k) ? m.get(k)! : null), setItem: (k: string, v: string) => { m.set(k, v); }, dump: () => Object.fromEntries(m) };
}

test("a tab's hot key is a command: session.hotkey.<sid>, and the id round-trips", () => {
  assert.equal(hotkeyCommandId(SID), "session.hotkey." + SID);
  assert.equal(sidOfHotkeyCommand("session.hotkey." + SID), SID);
  assert.equal(sidOfHotkeyCommand("session.jump"), null);
});

test("the set of sessions with a hot key persists with their names; a nameless one wears its short id", () => {
  const s = store();
  assert.deepEqual(loadTabKeys(s), {});
  rememberTabKey(s, SID, " web ");
  assert.deepEqual(loadTabKeys(s), { [SID]: "web" });
  rememberTabKey(s, "11111111-2222-4333-8444-000000000502", "");
  assert.equal(loadTabKeys(s)["11111111-2222-4333-8444-000000000502"], "11111111");
  forgetTabKey(s, SID);
  assert.deepEqual(Object.keys(loadTabKeys(s)), ["11111111-2222-4333-8444-000000000502"]);
  assert.equal(TABKEYS_KEY, "romp:tabkeys");
  // a corrupt or foreign value reads as empty, never throws
  assert.deepEqual(loadTabKeys(store({ [TABKEYS_KEY]: "nonsense" })), {});
  assert.deepEqual(loadTabKeys(store({ [TABKEYS_KEY]: JSON.stringify({ a: 1, b: "ok" }) })), { b: "ok" });
});

test("the chord a tab answers to comes from the shared bindings store, resolved per platform; none → empty", () => {
  const overrides = { ["session.hotkey." + SID]: "Mod+1" };
  assert.equal(tabChord(SID, overrides, true), "Meta+1");
  assert.equal(tabChord(SID, overrides, false), "Ctrl+1");
  assert.equal(tabChord(SID, {}, true), "");
  assert.equal(tabChord(SID, { ["session.hotkey." + SID]: "" }, true), "", "a deliberate unbind is none");
});

// ── keeping the set honest (review 2026-09-10: it only ever grew) ──────────────────────────────────────
const SID2 = "11111111-2222-4333-8444-000000000502";

test("a session with no chord bound leaves the set: a cancelled first recording, a Backspace, a menu's Remove (a \"\" write)", () => {
  const set = { [SID]: "web", [SID2]: "api" };
  assert.deepEqual(unboundTabKeys(set, { ["session.hotkey." + SID]: "Alt+Shift+K" }, false), [SID2], "no override at all: unbound");
  assert.deepEqual(unboundTabKeys(set, { ["session.hotkey." + SID]: "Alt+Shift+K", ["session.hotkey." + SID2]: "" }, false), [SID2], "a deliberate unbind: unbound");
  assert.deepEqual(unboundTabKeys(set, { ["session.hotkey." + SID]: "Mod+1", ["session.hotkey." + SID2]: "F6" }, true), [], "both bound: nothing to drop");
  assert.deepEqual(unboundTabKeys({}, {}, false), []);
});

test("a session whose tab left the strip leaves the set — but an EMPTY strip drops nothing (a kernel not yet heard from)", () => {
  const set = { [SID]: "web", [SID2]: "api" };
  assert.deepEqual(goneTabKeys(set, [SID, "other", SID2]), []);
  assert.deepEqual(goneTabKeys(set, [SID2]), [SID]);
  assert.deepEqual(goneTabKeys(set, []), [], "no strip yet is not a strip with nothing on it");
});

test("a renamed session is re-titled in the set; a nameless or unchanged one is left alone", () => {
  const set = { [SID]: "web", [SID2]: "api" };
  const names: Record<string, string | undefined> = { [SID]: "web-v2", [SID2]: "api" };
  assert.deepEqual(renamedTabKeys(set, (sid) => names[sid]), [[SID, "web-v2"]]);
  assert.deepEqual(renamedTabKeys(set, () => undefined), [], "a session the pane has not loaded keeps its stored title");
  assert.deepEqual(renamedTabKeys(set, () => "  "), [], "blank is not a name");
});

test("render.ts: the pane keeps the set honest at the strip — departed tabs drop out, renamed ones re-title — and the shell follows", () => {
  assert.match(RENDER, /import \{ hotkeyCommandId, loadTabKeys, rememberTabKey, forgetTabKey, goneTabKeys, renamedTabKeys \} from "\.\/tab-keys";/);
  assert.match(RENDER, /for \(const id of kernelOrder\) kernelListed\.add\(id\);[\s\S]*?\n\s*renderTabs\(\);\n\s*syncTabKeysWithStrip\(\);\n\}/, "after every tab-order push (the T357 restore between, the strip painted, then the set follows it)");
  assert.match(RENDER, /function syncTabKeysWithStrip\(\): void \{\n\s*if \(!inRompShell\(\)\) return;[\s\S]*?for \(const sid of goneTabKeys\(set, order\)\) \{ forgetTabKey\(localStorage, sid\); saveOverride\(hotkeyCommandId\(sid\), null\); \}\n\s*for \(const \[sid, name\] of renamedTabKeys\(set, \(sid\) => sessions\.get\(sid\)\?\.name\)\) rememberTabKey\(localStorage, sid, name\);/);
  assert.match(RENDER, /s\.name = m\.name; renderTabs\(\); syncTabKeysWithStrip\(\);/, "and on a rename");
  // the shell: every bindings write it hears prunes the unbound (its own KEYS_EVENT, a pane's storage event), never
  // while the dialog is up; a change to the set re-syncs the registry, unregistering departed sessions
  assert.match(MAIN, /function pruneUnboundHotkeys\(\): void \{\n\s*if \(keys\.isOpen\(\)\) return;\n\s*for \(const sid of unboundTabKeys\(loadTabKeys\(localStorage\), loadOverrides\(\), mac\)\) unregisterTabHotkey\(sid\);/);
  assert.match(MAIN, /function unregisterTabHotkey\(sid: string\): void \{\n\s*forgetTabKey\(localStorage, sid\);\n\s*unregisterCommand\(hotkeyCommandId\(sid\)\);\n\s*hotkeySids\.delete\(sid\);\n\s*saveOverride\(hotkeyCommandId\(sid\), null\);/);
  assert.match(MAIN, /window\.addEventListener\("storage", \(e\) => \{ if \(e\.key === TABKEYS_KEY\) syncTabHotkeys\(\); \}\);\n\s*window\.addEventListener\("storage", \(e\) => \{ if \(e\.key === KEYS_EVENT\) pruneUnboundHotkeys\(\); \}\);[^\n]*\n\s*window\.addEventListener\(KEYS_EVENT, pruneUnboundHotkeys\);\n\s*pruneUnboundHotkeys\(\);/);
  assert.match(MAIN, /for \(const sid of Array\.from\(hotkeySids\)\) if \(!\(sid in set\)\) \{ unregisterCommand\(hotkeyCommandId\(sid\)\); hotkeySids\.delete\(sid\); invalidate\(\); \}/);
});

test("render.ts: the keycap is the T379 widget's, its chord is in the strip's repaint signature, and the strip repaints on a store change", () => {
  const loop = RENDER.slice(RENDER.indexOf("appendTabAfterWidgets(tab, s);"), RENDER.indexOf('const close = el("span", "tab-close");'));
  assert.ok(loop.length > 0 && loop.length < 2000, "the after-the-name block, between the widgets and the close ×: " + loop.length);
  assert.doesNotMatch(loop, /tab-key/, "the pane paints no badge of its own between the widgets and the close ×: the keycap is tab-widgets.ts's (tabHotkey, the same romp:tabkeys set and session.hotkey.<sid> override)");
  assert.match(RENDER, /st\.ctx, st\.ctxColor, st\.ctxTone, !!s\.sub, down, note, tabHotkey\(id\)\]/, "an input the strip paints is in its signature (the chord via the widget's reader)");
  assert.doesNotMatch(RENDER, /keyOverrides|tabChord\(/, "no second reader of the bindings store in the pane: the widget reads it");
  assert.match(RENDER, /window\.addEventListener\("storage", \(e\) => \{ if \(e\.key === KEYS_EVENT\) renderTabs\(\); \}\);\n\s*window\.addEventListener\(KEYS_EVENT, \(\) => renderTabs\(\)\);/);
});

test("render.ts + styles.css: the bell command's word on the new state is a quiet NOTE toast, never a warning (review 2026-09-14: the warn border is the error colour, so a routine confirmation read as a failure)", () => {
  // the helper beside ephemeralWarnToast: the same dismissible toast (the ✕, Esc, the fade, the reload-skip mark), dressed .note
  assert.match(RENDER, /^function ephemeralNoteToast\(msg: string\): void \{ const t = warnToast\(msg\); t\.classList\.add\("note"\); t\.dataset\.ephemeral = "1"; \}/m);
  assert.match(RENDER, /setSessionFlag\(activeId, "notify", on\);\s*ephemeralNoteToast\(\(on \? "Notifications enabled for " : "Notifications disabled for "\) \+ \(s\.name \|\| activeId\.slice\(0, 8\)\)\);/,
    "the bell's confirmation, its wording kept");
  assert.equal((RENDER.match(/ephemeralNoteToast\(/g) || []).length, 2, "the definition and the bell: a refusal stays a warning");
  // the dress: the standard hairline every quiet notice wears (the seek note, the jump chip), no error or warning tint
  const at = CSS.indexOf(".warn-toast.note {");
  assert.ok(at > CSS.indexOf(".warn-toast {"), "declared after the base rule it overrides");
  const rule = CSS.slice(at, CSS.indexOf("}", at));
  assert.match(rule, /border-color: var\(--menu-border\);/);
  assert.doesNotMatch(rule, /errorForeground|--warn\b|#f48771/);
});

test("render.ts: the tab menu's one row asks the shell to record a hot key; a bound one reads Update and the recorder removes too", () => {
  const i = RENDER.indexOf('label: cur ? "Update hot key…" : "Hot key…"');
  assert.ok(i > 0);
  const block = RENDER.slice(RENDER.lastIndexOf("if (inRompShell()", i), RENDER.indexOf("// The colour swatches close the section with Rename", i));
  assert.match(block, /typeof \(window\.parent as any\)\.__rompHotkeyConfigure === "function"/, "shell-hosted only: the shell owns the recorder");
  assert.match(block, /window\.parent\.postMessage\(\{ romp: "hotkeyConfigure", sid: id, name: sessions\.get\(id\)\?\.name \|\| "" \}, "\*"\)/);
  // one row (the user 2026-09-11): no separate Remove row — the recorder it opens re-records or removes (Backspace, or
  // its Remove button, shortcuts-modal.ts: the same unbind in the bindings store)
  assert.doesNotMatch(block, /Remove hot key/);
  assert.match(block, /sub: cur \? "now " \+ miniChord\(cur\) \+ " — press a new combination, or remove it" : "press a key combination that switches to this tab",/);
  assert.match(block, /ctxIcon\("key", false\)/);
  assert.ok(i > RENDER.indexOf('l.textContent = "Rename"') && i < RENDER.indexOf('const row = el("div", "ctx-colors")'), "with Rename, before the colour swatches: how this tab shows and holds on the strip (the partition has no split row, 2026-09-11)");
  assert.match(RENDER, /kind === "key"\n\s*\? '<rect x="1.5" y="4" width="13" height="8" rx="1.5"\/><line x1="4.5" y1="9.5" x2="11.5" y2="9.5"\/>'/);
});

test("palette-main.ts: per-tab commands are registered from the store at boot and on a pane's ask, fire through the column arbitration, and the split cycles", () => {
  assert.match(MAIN, /import \{ hotkeyCommandId, loadTabKeys, rememberTabKey, forgetTabKey, tabChord, unboundTabKeys, TABKEYS_KEY \} from "\.\/tab-keys";/);
  assert.match(MAIN, /function registerTabHotkey\(sid: string, name: string\): void \{\n\s*registerCommand\(\{ id: hotkeyCommandId\(sid\), title: "Switch to " \+ \(name \|\| sid\.slice\(0, 8\)\), run: \(\) => jumpToSession\(sid\) \}\);\n\s*hotkeySids\.add\(sid\);\n\s*invalidate\(\);/);
  assert.match(MAIN, /function syncTabHotkeys\(\): void \{[^\n]*\n\s*const set = loadTabKeys\(localStorage\);\n\s*for \(const \[sid, name\] of Object\.entries\(set\)\) registerTabHotkey\(sid, name\);[\s\S]*?\n\s*syncTabHotkeys\(\);/, "at boot, before any pane loads");
  assert.match(MAIN, /const f = \(w\.__rompChatTarget && w\.__rompChatTarget\(sid\)\) \|\| pane\("f-chat"\);/, "the column already showing it, else the one last worked in");
  assert.match(MAIN, /postMessage\(\{ type: "jumpSession", id: sid \}, "\*"\)/);
  // the pane's ask (the message) and the probe global run ONE function: the session joins the set, its command exists,
  // the dialog opens on that row; when it closes the focus goes back to the asking pane's composer, and a session
  // left with no chord leaves the set
  assert.match(MAIN, /function configureHotkey\(sid: string, name: string, from: Window \| null\): void \{\n\s*rememberTabKey\(localStorage, sid, name\);\n\s*registerTabHotkey\(sid, name\);\n\s*keys\.openFor\(hotkeyCommandId\(sid\), \(\) => \{\n\s*if \(tabChord\(sid, loadOverrides\(\), mac\)\) rememberTabKey\(localStorage, sid, name\); else unregisterTabHotkey\(sid\);\n\s*pruneUnboundHotkeys\(\);\n\s*const back = from \|\| chatPane\(\)\?\.contentWindow \|\| null;\n\s*try \{ back!\.focus\(\); back!\.postMessage\(\{ type: "focusComposer" \}, "\*"\); \}/);
  assert.match(MAIN, /if \(!m \|\| m\.romp !== "hotkeyConfigure" \|\| typeof m\.sid !== "string" \|\| !m\.sid\) return;\n\s*configureHotkey\(m\.sid, typeof m\.name === "string" \? m\.name : "", \(e\.source as Window \| null\) \|\| null\);/);
  assert.match(MAIN, /w\.__rompHotkeyConfigure = \(sid: string, name: string\) => configureHotkey\(sid, name, null\);/, "the pane's menu gates on this");
  assert.match(MAIN, /registerCommand\(\{ id: "chat\.nextSplit", title: "Focus the next chat column", run: \(\) => cycleSplit\(1\) \}\);/);
  assert.match(MAIN, /registerCommand\(\{ id: "chat\.prevSplit", title: "Focus the previous chat column", run: \(\) => cycleSplit\(-1\) \}\);/);
  assert.match(MAIN, /const f = pane\(ids\[\(i \+ dir \+ ids\.length\) % ids\.length\]\);/, "wraps");
  assert.match(MAIN, /if \(ids\.length < 2\) return;\n\s*try \{ if \(w\.__rompPaneToggle\) w\.__rompPaneToggle\("chat", true\); \}/, "a hidden chat pane shows itself when the cycle has somewhere to go");
  assert.match(MAIN, /function invalidate\(\): void \{ byChord = null; \}/, "hoisted: the boot registrations run before the dispatcher's declaration");
});

test("shortcuts-modal.ts: openFor is a solo recording — one row, recording at once, a commit or a cancel closes it and runs the caller's onClose", () => {
  assert.match(MODAL, /openFor\(id: string, onClose\?: \(\) => void\): void;/);
  assert.match(MODAL, /function openFor\(id: string, onClose\?: \(\) => void\): void \{[\s\S]*?soloId = id;\n\s*soloDone = onClose \|\| null;[\s\S]*?recId = id;/);
  assert.match(MODAL, /if \(solo && c\.id !== solo\.id\) continue;/, "only that command's row");
  assert.match(MODAL, /heading\.textContent = solo \? "Hot key for \\u201c" \+ solo\.title\.replace\(\/\^Switch to \/, ""\) \+ "\\u201d" : "Keyboard shortcuts";/);
  assert.match(MODAL, /input\.hidden = !!solo;[^\n]*\n\s*fixed\.hidden = !!solo;/, "the built-in section is out of the way too: the dialog is that row alone");
  // both exits go through leaveSolo: hide first, THEN the caller's onClose (so the focus it hands back is not stolen by a shown card)
  assert.match(MODAL, /function leaveSolo\(\): void \{\n\s*const done = soloDone;\n\s*soloId = null; soloDone = null;\n\s*if \(back\) back\.hidden = true;\n\s*for \(const fn of closers\) fn\(\);\n\s*if \(done\) done\(\);\n\s*\}/);
  assert.match(MODAL, /function commit\(id: string, chord: string\): void \{\n\s*saveOverride\(id, chord\);[\s\S]*?if \(soloId\) \{ leaveSolo\(\); return; \}/);
  assert.match(MODAL, /function cancelRecord\(\): void \{[\s\S]*?if \(soloId\) \{ leaveSolo\(\); return; \}/);
  assert.match(MODAL, /panel\.tabIndex = -1;/, "the card takes focus so the captured keydown reaches the recorder with the filter box hidden");
  assert.match(MODAL, /return \{ open, openFor, close, isOpen, feed, onClose \};/);
  // the chord lands wherever the focus was: the shell's dispatcher hands a pane's keydown to the recorder while the dialog is open
  assert.match(MODAL, /function feed\(e: KeyboardEvent\): boolean \{\n\s*if \(!isOpen\(\) \|\| !recId \|\| e\.key === "Escape"\) return false;[\s\S]*?onRecordKey\(e\);\n\s*return true;/);
  assert.match(MAIN, /if \(keys\.isOpen\(\)\) \{ keys\.feed\(e\); return; \}/);
  // a refused key is SAID on the row, not swallowed (the user 2026-09-10 pressed ` then 1 and saw nothing happen)
  assert.match(MODAL, /if \(!bindable\(ch\)\) \{\n\s*refused = ch\.includes\("\+"\)\n\s*\? displayChord\(ch, mac\) \+ " is a key the panes own — pick another"\n\s*: "“" \+ displayChord\(ch, mac\) \+ "” alone would fire while you type — hold "/);
  assert.match(MODAL, /\} else if \(refused\) \{\n\s*hint\.className = "rkeys-conflict";\n\s*hint\.textContent = refused;/);
});

test("the full dialog's exit prunes too: an unbind made there fires while the dialog is up, and the close is what runs the prune", () => {
  assert.match(MODAL, /onClose\(fn: \(\) => void\): void;/, "the API");
  assert.match(MODAL, /function close\(\): boolean \{\n\s*if \(!back \|\| back\.hidden\) return false;\n\s*if \(recId\) \{ cancelRecord\(\); return true; \}[^\n]*\n\s*back\.hidden = true;\n\s*for \(const fn of closers\) fn\(\);/, "the regular exit runs the listeners (never the one-Escape-level cancel, which stays open)");
  assert.match(MODAL, /function leaveSolo\(\): void \{\n\s*const done = soloDone;\n\s*soloId = null; soloDone = null;\n\s*if \(back\) back\.hidden = true;\n\s*for \(const fn of closers\) fn\(\);\n\s*if \(done\) done\(\);/, "the solo exit too, before its own onClose");
  assert.match(MAIN, /keys\.onClose\(pruneUnboundHotkeys\);/, "the shell prunes the set on every close");
});
