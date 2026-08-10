// Hover discoverability (the user 2026-08-10): every button that runs a command advertises the
// command's CURRENT binding in its tooltip — the live overrides store, never a hardcoded chord — so
// the shortcuts are discoverable by hovering the control that does the same thing.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { DEFAULT_CHORDS, registerCommand, commandList } from "./commands";
import { displayChord, keyHint, titleWithKey } from "./keybindings";

const p = (...f: string[]) => path.resolve(process.cwd(), "..", ...f);

// keyHint detects the platform from `navigator` (which node ≥21 exposes), so expectations are built
// through the same displayChord it uses — the tests assert the plumbing, not the runner's platform.
const MAC = typeof navigator !== "undefined" && /Mac|iP(hone|ad|od)/.test((navigator as any).platform || "");
const disp = (chord: string) => displayChord(chord, MAC);

// node has no localStorage; install a stub so the overrides store is exercisable, and restore after.
function withOverrides(overrides: Record<string, string>, fn: () => void): void {
  const g: any = globalThis;
  const had = "localStorage" in g, prev = g.localStorage;
  g.localStorage = { getItem: (k: string) => (k === "romp:keys" ? JSON.stringify(overrides) : null),
                     setItem: () => {} };
  try { fn(); } finally { if (had) g.localStorage = prev; else delete g.localStorage; }
}

test("registerCommand fills the default chord from the ONE table", () => {
  registerCommand({ id: "session.new", title: "New session", run: () => {} });
  const c = commandList().find((x) => x.id === "session.new")!;
  assert.equal(c.chord, DEFAULT_CHORDS["session.new"], "call sites declare no chord; the table is the source");
  assert.equal(c.chord, "Mod+Shift+O");
});

test("titleWithKey appends the current binding; the bare title when unbound", () => {
  // no localStorage in node → no overrides → the default chord shows
  assert.equal(titleWithKey("Open a session", "session.new"), `Open a session (${disp("Mod+Shift+O")})`);
  assert.equal(titleWithKey("Open the log", "log.open"), "Open the log", "log.open ships unbound → no hint");
  assert.equal(titleWithKey("Open a session", "no.such.command"), "Open a session");
});

test("a REBIND changes what the next hover says; an explicit unbind removes the hint", () => {
  withOverrides({ "session.new": "Ctrl+K" }, () => {
    assert.equal(titleWithKey("Open a session", "session.new"), `Open a session (${disp("Ctrl+K")})`);
  });
  withOverrides({ "session.new": "" }, () => {
    assert.equal(titleWithKey("Open a session", "session.new"), "Open a session",
      "deliberately unbound → the tooltip stops advertising the default");
  });
  // …and a command with NO default becomes discoverable the moment the user binds it
  withOverrides({ "log.open": "Alt+ArrowDown" }, () => {
    assert.equal(keyHint("log.open"), disp("Alt+ArrowDown"), "named keys wear their keycap form");
  });
});

test("the shell sweeps [data-keycmd] tooltips and re-syncs on every rebind", () => {
  const MAIN = fs.readFileSync(p("ui", "webview", "palette-main.ts"), "utf8");
  assert.match(MAIN, /querySelectorAll\("\[data-keycmd\]"\)/);
  assert.match(MAIN, /el\.title = titleWithKey\(base, el\.dataset\.keycmd \|\| ""\)/);
  assert.match(MAIN, /window\.addEventListener\(KEYS_EVENT, syncKeyTitles\);/);
  assert.match(MAIN, /window\.addEventListener\("storage", syncKeyTitles\);/, "a rebind in another tab counts too");
  assert.match(MAIN, /w\.__rompKeyHint = keyHint;/, "the landing page's inline scripts (pane toggles) read this");
});

test("the chat strip's + button carries the binding", () => {
  const RENDER = fs.readFileSync(p("ui", "webview", "render.ts"), "utf8");
  assert.match(RENDER, /add\.title = titleWithKey\("Open a session", "session\.new"\);/);
});
