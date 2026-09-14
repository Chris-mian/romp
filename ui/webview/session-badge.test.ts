// The statusline's session badge (the user 2026-09-09): the session's name on its identity colour, text in
// black, before the state chip — per pane, so a split column badges ITS session. The spec is a pure rule
// (session-badge.ts), executed here; the statusline wiring in render.ts and the chip's styling are pinned at
// source (no jsdom for the renderer — the repo convention). Synthetic names and colours only.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { badgeSpec } from "./session-badge";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("a named session gets its name on its identity colour; no colour yet → the neutral fill (bg null)", () => {
  assert.deepEqual(badgeSpec({ name: "web", color: { bg: "#7fb3d5", fg: "#000000" } as any }), { text: "web", bg: "#7fb3d5" });
  assert.deepEqual(badgeSpec({ name: "api", color: null }), { text: "api", bg: null });
  assert.deepEqual(badgeSpec({ name: " tests " }), { text: "tests", bg: null }, "trimmed");
});

test("no name, no badge — the opening line covers a tab whose payload has not arrived", () => {
  assert.equal(badgeSpec({ name: "", color: { bg: "#7fb3d5" } }), null);
  assert.equal(badgeSpec({}), null);
  assert.equal(badgeSpec(null), null);
  assert.equal(badgeSpec(undefined), null);
});

// Since T409 the badge is the status line's NAME widget (status-widgets.ts, off by default): the line composes its left
// slot before the state chip, and the widget's render draws the chip from the same badgeSpec.
const SW = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "status-widgets.ts"), "utf8");
test("render.ts: updateStatusline composes the left slot (the name widget) first, before the state chip, on every state", () => {
  assert.match(SW, /import \{ badgeSpec \} from "\.\/session-badge";/);
  assert.doesNotMatch(RENDER, /badgeSpec/, "the renderer no longer builds the badge itself");
  const fn = RENDER.slice(RENDER.indexOf("function updateStatusline() {"), RENDER.indexOf("\n}\n", RENDER.indexOf("function updateStatusline() {")));
  const leftAt = fn.indexOf('composeStatusWidgets(sl, "left", rec, settings.statusWidgets);');
  assert.ok(leftAt > 0, "the left slot is composed from the active session's record");
  assert.ok(leftAt > fn.indexOf("sl.replaceChildren();"), "after the line is emptied");
  assert.ok(leftAt > fn.indexOf('ro.textContent = "read-only · a subagent\'s transcript";'), "a subagent viewer, which is no session, gets none");
  assert.ok(leftAt < fn.indexOf('if (s.status.state === "working") {'), "…and before the first state chip");
  assert.match(SW, /const b = el\("span", "chip chip-session"\);\n\s*b\.textContent = bs\.text;/);
  assert.match(SW, /if \(bs\.bg\) b\.style\.background = bs\.bg;/, "the identity colour is the fill");
});

test("styles.css: the badge is a chip with black text on the session's colour, clipped to a short name", () => {
  assert.match(CSS, /\.chip-session \{ color: #000; background: var\(--box-border\); max-width: 14em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; \}/);
});

// The badge is an OPT-IN (the maintainers via the user, 2026-09-10; the user again on T409): the name widget defaults off.
// showSessionBadge stays in the store as the widget's MIRROR (settings.ts never reads it since the one-shot migration and
// writes it back on every save); the gear injects no default for it and has no row of its own for it any more: the
// Status line section's Session name row is the control.
test("settings carry showSessionBadge as the name widget's mirror, defaulting OFF, and the gear injects no default and keeps no row", () => {
  const SETTINGS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "settings.ts"), "utf8");
  const GEAR = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "gear.js"), "utf8");
  assert.match(SETTINGS, /showSessionBadge: boolean;/);
  assert.match(SETTINGS, /DEFAULT_SETTINGS[^;]*showSessionBadge: false/);
  assert.match(SETTINGS, /Object\.assign\(s, legacyOfStatusPrefs\(s\.statusWidgets\)\);/, "the mirror is written from the widgets on load");
  assert.doesNotMatch(GEAR, /showSessionBadge: (true|false)/, "no injected default (the fresh-key rule); a store from before the widgets reads the widget defaults (the one-shot migration)");
  assert.doesNotMatch(GEAR, /id=rs-badge|Show session badge|sbg = document/, "the checkbox row is gone");
  assert.match(GEAR, /data-section=statusline>Status line</, "the Status line section is the control");
  assert.match(GEAR, /s\.showBranch = m\.showBranch; s\.showSessionBadge = m\.showSessionBadge; save\(s\);/, "a section save writes both mirrors");
  assert.match(SW, /id: "name", label: "Session name", defaultOn: false, slot: "left",/);
});

test("render.ts: the line reads the widgets' prefs, never the legacy key, and a gear flip repaints it at once", () => {
  assert.doesNotMatch(RENDER, /settings\.showSessionBadge|showSessionBadge ===/);
  assert.match(RENDER, /onExternalSettingsChange\(\(s\) => \{ settings = s; applyChatScheme\(s\); renderTabs\(\); updateStatusline\(\); rerenderAll\(\);/);
});
