// Cycling the sessions of a chat column by key (the user 2026-09-23): the browser's "Go to the next / previous
// session" commands and their default chords, beside the VS Code view's rompChat.nextTab / prevTab, which had the
// keys already. The chord rules run against the real keybindings model; the shell's registration (palette-main.ts),
// the pane's message arm (render.ts) and the pane-focus script's bail (kernel.py) are pinned at source — the repo's
// convention where there is no DOM — and the VS Code bindings are read from the extension's own manifest.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { DEFAULT_CHORDS } from "./commands";
import { builtInOwner, chordOf, conflictOf, dispatchable, displayChord, resolveChord } from "./keybindings";

const read = (...p: string[]) => fs.readFileSync(path.resolve(process.cwd(), "..", ...p), "utf8");
const MAIN = read("ui", "webview", "palette-main.ts");
const RENDER = read("ui", "webview", "render.ts");
const KERNEL = read("kernel", "kernel.py");
const MANIFEST = JSON.parse(read("vscode-extension", "package.json"));
const PAIR = [["chat.nextTab", "ArrowRight"], ["chat.prevTab", "ArrowLeft"]] as const;

test("the defaults are literal Ctrl+Alt+arrows: one chord on every platform, and the one a browser's keydown spells", () => {
  assert.equal(DEFAULT_CHORDS["chat.nextTab"], "Ctrl+Alt+ArrowRight");
  assert.equal(DEFAULT_CHORDS["chat.prevTab"], "Ctrl+Alt+ArrowLeft");
  for (const [id, key] of PAIR) {
    const d = DEFAULT_CHORDS[id];
    assert.equal(resolveChord(d, true), resolveChord(d, false), "no Mod: a Mac gets Control+Option, not the Cmd+Option the browser owns");
    assert.equal(chordOf({ key, ctrlKey: true, altKey: true, shiftKey: false, metaKey: false }), resolveChord(d, false));
  }
  assert.equal(displayChord(DEFAULT_CHORDS["chat.nextTab"], true), "⌃⌥→");
  assert.equal(displayChord(DEFAULT_CHORDS["chat.nextTab"], false), "Ctrl+Alt+→");
});

test("the chords are free: no built-in behaviour owns them and no other default holds them", () => {
  const cmds = Object.entries(DEFAULT_CHORDS).map(([id, chord]) => ({ id, chord }));
  for (const mac of [true, false]) {
    for (const [id] of PAIR) {
      assert.equal(builtInOwner(DEFAULT_CHORDS[id], mac), null, "the shell's Alt+Arrow pane focus is not Ctrl+Alt+Arrow");
      assert.equal(conflictOf(DEFAULT_CHORDS[id], id, cmds, {}, mac), null);
    }
  }
});

test("the chord fires from the composer, where the strip's bare arrows do not", () => {
  assert.equal(dispatchable({ ctrlKey: true, altKey: true, metaKey: false }, true), true, "a Ctrl/Alt chord dispatches whatever holds the focus");
  assert.equal(dispatchable({ ctrlKey: false, altKey: false, metaKey: false }, true), false, "a bare arrow while typing is typing");
  // the shell's Alt+Arrow capture bails on any further modifier, so a Ctrl+Alt+Arrow keydown reaches the dispatcher
  assert.match(KERNEL, /if\(!e\.altKey\|\|e\.shiftKey\|\|e\.ctrlKey\|\|e\.metaKey\)return;\s+\/\/ Alt\(Option\)\+Arrow ONLY \(no other modifiers\)/);
});

test("palette-main.ts registers the pair, posting the pane the messages the VS Code view posts; the pane steps with cycleTab", () => {
  assert.match(MAIN, /registerCommand\(\{ id: "chat\.nextTab", title: "Go to the next session", run: \(\) => chatPost\(\{ type: "nextTab" \}\) \}\);/);
  assert.match(MAIN, /registerCommand\(\{ id: "chat\.prevTab", title: "Go to the previous session", run: \(\) => chatPost\(\{ type: "prevTab" \}\) \}\);/);
  assert.match(RENDER, /else if \(m\.type === "nextTab"\) cycleTab\(1\);\s*\n\s*else if \(m\.type === "prevTab"\) cycleTab\(-1\);/,
               "one arm for the shell's post and the VS Code host's");
  // "Switch to <name>" is the per-tab hot key's title: the dialog's solo heading strips that prefix and the served split
  // test lists the hot-key rows by it, so the pair must not wear it (CI caught the first spelling, 2026-09-23)
  for (const m of MAIN.matchAll(/id: "chat\.(?:next|prev)Tab", title: "([^"]+)"/g)) assert.doesNotMatch(m[1], /^Switch to /, m[1]);
});

test("VS Code binds the same pair to Ctrl+Alt+arrows (Cmd+Alt on a Mac) while the romp panel is active, and posts the same messages", () => {
  const kb = MANIFEST.contributes.keybindings as Array<{ command: string; key?: string; mac?: string; when: string }>;
  const next = kb.find((k) => k.command === "rompChat.nextTab" && k.key);
  const prev = kb.find((k) => k.command === "rompChat.prevTab" && k.key);
  assert.equal(next?.key, "ctrl+alt+right");
  assert.equal(prev?.key, "ctrl+alt+left");
  assert.equal(next?.mac, "cmd+alt+right");
  assert.equal(prev?.mac, "cmd+alt+left");
  for (const k of kb.filter((x) => x.command === "rompChat.nextTab" || x.command === "rompChat.prevTab")) {
    assert.equal(k.when, "activeWebviewPanelId == 'rompChat'");
  }
  const EXT = read("vscode-extension", "src", "extension.ts");
  assert.match(EXT, /registerCommand\("rompChat\.nextTab", \(\) => panel\?\.webview\.postMessage\(\{ type: "nextTab" \}\)\)/);
  assert.match(EXT, /registerCommand\("rompChat\.prevTab", \(\) => panel\?\.webview\.postMessage\(\{ type: "prevTab" \}\)\)/);
});
