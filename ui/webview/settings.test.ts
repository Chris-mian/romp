import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

// Minimal localStorage shim BEFORE importing the module (load/save read it at call time).
const store: Record<string, string> = {};
(globalThis as any).localStorage = {
  getItem: (k: string) => (k in store ? store[k] : null),
  setItem: (k: string, v: string) => { store[k] = v; },
  removeItem: (k: string) => { delete store[k]; },
};
import { loadSettings, saveSettings, installSettingsSync, DEFAULT_SETTINGS, paneSet, OPTIONAL_PANES } from "./settings";

test("loadSettings returns defaults when nothing is stored", () => {
  delete store["romp:settings"];
  assert.deepEqual(loadSettings(), DEFAULT_SETTINGS);
});

test("the Sub-goals card pref defaults ON; the old Explanations pref is gone (the user 2026-06-18)", () => {
  assert.equal(DEFAULT_SETTINGS.subgoals, true);
  assert.equal((DEFAULT_SETTINGS as any).explanations, undefined);
});

test("both judge-set toggles default OFF (the user 2026-06-29): the timeline's judging band stays hidden", () => {
  assert.equal(DEFAULT_SETTINGS.showIndexJudges, false);
  assert.equal(DEFAULT_SETTINGS.showTriageJudges, false);
});

test("Default backend defaults to sdk (the user 2026-07-13); Claude Code and Codex coexist", () => {
  assert.equal(DEFAULT_SETTINGS.backend, "sdk");
});

test("a saved default of the retired terminal backend reads as sdk, never an undefined value (T331)", () => {
  localStorage.setItem("romp:settings", JSON.stringify({ ...DEFAULT_SETTINGS, backend: "tmux" }));
  assert.equal(loadSettings().backend, "sdk");
  localStorage.setItem("romp:settings", JSON.stringify({ ...DEFAULT_SETTINGS, backend: "nonsense" }));
  assert.equal(loadSettings().backend, "sdk", "any value no longer offered reads as the default");
  localStorage.setItem("romp:settings", JSON.stringify({ ...DEFAULT_SETTINGS, backend: "codex" }));
  assert.equal(loadSettings().backend, "codex", "an offered pick stands");
  saveSettings({ backend: "sdk" });
});

test("Compact transcript defaults ON (the user 2026-07-14): fresh installs read the tidy transcript", () => {
  assert.equal(DEFAULT_SETTINGS.compact, true);
});

// The tab strip's one-group-per-row layout (T264) is the default and a per-device pick: an explicit false
// lets the groups follow one another across the strip and wrap as they need (render.ts renderTabs).
test("needsBox defaults ON: the chat's Needs you box shows (plans/needs-you.md, phase three); an explicit false round-trips, and a store from before the key reads as on", () => {
  assert.equal(DEFAULT_SETTINGS.needsBox, true);
  store["romp:settings"] = JSON.stringify({ needsBox: false });
  assert.equal(loadSettings().needsBox, false, "the opt-out round-trips");
  store["romp:settings"] = JSON.stringify({});
  assert.equal(loadSettings().needsBox, true, "a store from before the key reads as on");
  delete store["romp:settings"];
});

test("stripGroupRows defaults ON: every tag group on its own row; an explicit false round-trips, and a store from before the key reads as on", () => {
  assert.equal(DEFAULT_SETTINGS.stripGroupRows, true);
  store["romp:settings"] = JSON.stringify({ stripGroupRows: false });
  assert.equal(loadSettings().stripGroupRows, false, "the opt-out round-trips");
  store["romp:settings"] = JSON.stringify({});
  assert.equal(loadSettings().stripGroupRows, true, "a store from before the key reads as on");
  delete store["romp:settings"];
});

// The state badge became the DEFAULT 2026-09-23 (the user 2026-09-21's follow-up). The MECHANISM of the flip is the
// default itself (DEFAULT_SETTINGS.tabStateBadge = true, supplied by the spread when the key is absent); the read
// `!== false` is only the GUARD around it, keeping a chosen false off and coercing a non-boolean stored value to a real
// boolean. The EXISTING key is kept, not a fresh one: no writer ever merged the old default into stored profiles (the
// gear's load() defaults exclude the key, no webview saveSettings caller, broadcastSettings/installSettingsSync write
// the stored object as-is), so a stored false is always a chosen off, and a fresh key would only discard it.
test("tabStateBadge defaults ON (the badge is the default): absent reads on, a chosen false stays off through a save and a settings-sync write, a literal true stays on", () => {
  assert.equal(DEFAULT_SETTINGS.tabStateBadge, true);
  delete store["romp:settings"];
  assert.equal(loadSettings().tabStateBadge, true, "absent (never chosen): the badge is on");
  store["romp:settings"] = JSON.stringify({ tabStateBadge: false });
  assert.equal(loadSettings().tabStateBadge, false, "a literal false is a CHOSEN off and stays off");
  store["romp:settings"] = JSON.stringify({ tabStateBadge: true });
  assert.equal(loadSettings().tabStateBadge, true, "a literal true stays on");
  // the read's DISTINCT effect (its only one the default spread does not already cover): a NON-boolean stored value,
  // from a corrupt or foreign write, coerces to a real boolean ON, never leaks as the raw value. Delete the read line
  // and this reads back 0/""/null (a falsy badge that no code path intends); the default spread cannot catch it, since
  // the key is present. This is the guard, distinct from the default.
  for (const bad of [0, null, "", "yes", 1]) {
    store["romp:settings"] = JSON.stringify({ tabStateBadge: bad });
    assert.equal(loadSettings().tabStateBadge, true, "a non-boolean stored tabStateBadge (" + JSON.stringify(bad) + ") reads ON as a real boolean");
  }
  // a chosen off survives a whole-object save (saveSettings merges every default, yet keeps the chosen false, not the new on)
  delete store["romp:settings"];
  saveSettings({ tabStateBadge: false });
  assert.equal(loadSettings().tabStateBadge, false, "the chosen off survives a save");
  assert.equal(JSON.parse(store["romp:settings"]).tabStateBadge, false, "…stored as the literal false, never flipped to the new default");
  // a settings-sync write, driven through installSettingsSync's OWN message handler (not a store poke): the handler
  // applies the peer pane's object verbatim, so a chosen off carried in it stays off here
  delete store["romp:settings"];
  const handlers: Record<string, (e: any) => void> = {};
  const prevWindow = (globalThis as any).window, prevEvent = (globalThis as any).Event;
  (globalThis as any).window = { addEventListener: (t: string, fn: (e: any) => void) => { handlers[t] = fn; }, dispatchEvent: () => {} };
  (globalThis as any).Event = class { type: string; constructor(t: string) { this.type = t; } };
  try {
    installSettingsSync();
    handlers.message({ data: { type: "settingsSync", settings: { tabStateBadge: false, compact: true, colormap: "aurora" } } });
    assert.equal(JSON.parse(store["romp:settings"]).tabStateBadge, false, "the sync handler wrote the peer object verbatim");
    assert.equal(loadSettings().tabStateBadge, false, "the chosen off survives a settings-sync write applied by installSettingsSync");
  } finally {
    if (prevWindow === undefined) delete (globalThis as any).window; else (globalThis as any).window = prevWindow;
    if (prevEvent === undefined) delete (globalThis as any).Event; else (globalThis as any).Event = prevEvent;
  }
  delete store["romp:settings"];
});

// The settings change signal must cover every way a change can happen: another
// same-origin tab (storage event), THIS document (the gear now lives in the same
// page — same-document writes never fire storage), and another VS Code webview
// (separate origin + localStorage → the host relays {settingsSync}, applied by
// installSettingsSync). The dead compact toggle (the user 2026-07-14) was the
// same-document gap.
test("settings changes propagate same-document and cross-webview, not just cross-tab", () => {
  const fs = require("node:fs") as typeof import("node:fs");
  const path = require("node:path") as typeof import("node:path");
  const ROOT = path.resolve(process.cwd(), "..");
  const src = fs.readFileSync(path.join(ROOT, "ui", "webview", "settings.ts"), "utf8");
  assert.ok(src.includes('addEventListener("storage"'), "cross-tab: the storage event");
  assert.ok(src.includes('addEventListener("romp:settings"'), "same-document: the gear's save() signal");
  assert.ok(src.includes('"settingsSync"'), "cross-webview: the host-relayed sync applies here");
  const gear = fs.readFileSync(path.join(ROOT, "ui", "webview", "gear.js"), "utf8");
  const save = gear.slice(gear.indexOf("function save(s)"), gear.indexOf("cc.addEventListener"));
  assert.ok(save.includes("dispatchEvent(new Event('romp:settings'))"), "save() always raises the same-doc signal");
  assert.ok(save.includes("settingsSync"), "save() always posts the cross-webview sync");
  const ext = fs.readFileSync(path.join(ROOT, "vscode-extension", "src", "extension.ts"), "utf8");
  assert.ok(ext.includes("function broadcastSettings"), "the host fans a gear save out to the other panes");
  const intercepts = ext.match(/m\.type === "settingsSync"/g) || [];
  assert.equal(intercepts.length, 2, "chat AND feed handlers intercept settingsSync (the two gear hosts)");
});

test("the backend pref roundtrips through storage (the gear writes it; createSession reads it fresh)", () => {
  delete store["romp:settings"];
  saveSettings({ backend: "sdk" });
  assert.equal(loadSettings().backend, "sdk");
});

test("saveSettings persists a patch and merges over defaults", () => {
  delete store["romp:settings"];
  const next = saveSettings({ compact: true });
  assert.equal(next.compact, true);
  assert.equal(loadSettings().compact, true, "the change is read back from storage");
});

test("loadSettings tolerates corrupt JSON → defaults", () => {
  store["romp:settings"] = "{not json";
  assert.deepEqual(loadSettings(), DEFAULT_SETTINGS);
});

test("an unknown key in storage is ignored, known keys still merge", () => {
  store["romp:settings"] = JSON.stringify({ compact: true, future: 42 });
  const s = loadSettings();
  assert.equal(s.compact, true);
  assert.equal((s as any).future, 42, "merge is shallow — extra keys pass through harmlessly");
});

// Compact tabs and agents (the user 2026-09-08: on a phone, the tab strip and the background-work panel
// left about three lines of transcript in view): OFF by default, so the strip and the panel render exactly
// as before the setting existed until the gear opts in. Distinct from `compact`, the transcript's own
// tidy-up (tool runs collapsed, thinking hidden). The class it drives is dense-chrome.test.ts's subject.
test("Compact tabs and agents defaults OFF (the user 2026-09-08); the opt-in round-trips, and a store from before the key reads as off", () => {
  assert.equal(DEFAULT_SETTINGS.denseChrome, false);
  delete store["romp:settings"];
  assert.equal(loadSettings().denseChrome, false, "a fresh install reads off");
  saveSettings({ denseChrome: true });
  assert.equal(loadSettings().denseChrome, true, "the opt-in survives a reload (localStorage)");
  store["romp:settings"] = JSON.stringify({ compact: true });
  assert.equal(loadSettings().denseChrome, false, "a store written before the key reads as off");
  delete store["romp:settings"];
});

// The file-links preference is GONE (T404, the user 2026-09-13): where a chat file link opens follows whether the Files pane
// is open (file-route.ts fileLinkRoute takes no setting). A store that still carries the old key reads without it and the next
// save leaves it behind, the T317-era filesControl key's way.
test("fileLinkPane: no such setting; a stored value is dropped, never read", () => {
  assert.equal((DEFAULT_SETTINGS as unknown as Record<string, unknown>).fileLinkPane, undefined);
  store["romp:settings"] = JSON.stringify({ fileLinkPane: "pane" });
  assert.equal((loadSettings() as unknown as Record<string, unknown>).fileLinkPane, undefined, "an old store's value is not read");
  saveSettings({ compact: false });
  assert.equal(JSON.parse(store["romp:settings"]).fileLinkPane, undefined, "…and the next save leaves it behind");
  assert.equal(loadSettings().compact, false);
});

// The optional dashboard panes (the user 2026-09-10): Sessions (key timeline), Outline (key fleet) and Feed
// can be hidden from the dashboard in the gear, per browser. All shown by default, so a dashboard that never
// opens the section is unchanged; only an explicit stored false hides a pane (a missing key, a store from
// before the setting, or a corrupt value reads as shown), and every key is present after a load so the
// shell's controller (_LANDING_COLLAPSE_JS) never has to guess. The chat is required and not listed.
test("the optional panes default to shown, a hide round-trips, and only an explicit false hides (the user 2026-09-10)", () => {
  assert.deepEqual(DEFAULT_SETTINGS.panes, { timeline: true, fleet: true, feed: true });
  assert.deepEqual([...OPTIONAL_PANES], ["timeline", "fleet", "feed"], "the chat is required and is not an optional pane");
  delete store["romp:settings"];
  assert.deepEqual(loadSettings().panes, { timeline: true, fleet: true, feed: true }, "a fresh install shows every pane");
  saveSettings({ panes: { timeline: true, fleet: true, feed: false } });
  assert.deepEqual(loadSettings().panes, { timeline: true, fleet: true, feed: false }, "hiding the feed survives a reload");
  store["romp:settings"] = JSON.stringify({ compact: true });
  assert.deepEqual(loadSettings().panes, { timeline: true, fleet: true, feed: true }, "a store from before the key shows every pane");
  store["romp:settings"] = JSON.stringify({ panes: { feed: false } });
  assert.deepEqual(loadSettings().panes, { timeline: true, fleet: true, feed: false }, "a partial set fills the missing panes in as shown");
  store["romp:settings"] = JSON.stringify({ panes: "purple" });
  assert.deepEqual(loadSettings().panes, { timeline: true, fleet: true, feed: true }, "a corrupt value costs nothing but the preference");
  assert.deepEqual(paneSet({ timeline: 0, fleet: "no", feed: null }), { timeline: true, fleet: true, feed: true }, "falsy but not false is not a hide");
  assert.deepEqual(paneSet(undefined), { timeline: true, fleet: true, feed: true });
  delete store["romp:settings"];
});

// A pane defined at the kernel (plans/panes-as-data.md, `romp pane`) has a row in the gear's Panes section under its own id:
// the set keeps any boolean member beside the shipped three, so that row's choice survives a save, and a member that is
// not a boolean is not a choice (the shell reads a missing member as the pane's own default: on, or off when experimental).
test("a registry pane's choice rides the pane set beside the shipped three (plans/panes-as-data.md)", () => {
  assert.deepEqual(paneSet({ timeline: true, fleet: false, feed: true, notes: false, lab: true }),
    { timeline: true, fleet: false, feed: true, notes: false, lab: true });
  assert.deepEqual(paneSet({ notes: "yes", docs: 0, lab: null }), { timeline: true, fleet: true, feed: true }, "a member that is not a boolean is not a choice");
  delete store["romp:settings"];
  saveSettings({ panes: { timeline: true, fleet: true, feed: true, notes: false } });
  assert.deepEqual(loadSettings().panes, { timeline: true, fleet: true, feed: true, notes: false }, "the hidden registry pane survives a reload");
  delete store["romp:settings"];
});

// The Files CONTROL's own setting (T317, the user 2026-09-10): whether the dashboard bar's Files toggle and the
// phone's Files tab show at all. OFF by default (T317b, the user the same day: the control is asked for, not
// shipped); only the literal true shows them, so a corrupt entry may cost the preference, never surprise the user
// with a control. The shell reads the store key itself (kernel.py _LANDING_COLLAPSE_JS filesCtl), so the key and
// the true-only rule are the contract.
test("the Files control is hidden by default; showing it round-trips, and only the literal true under the fresh key shows it", () => {
  assert.equal(DEFAULT_SETTINGS.showFilesControl, false);
  delete store["romp:settings"];
  assert.equal(loadSettings().showFilesControl, false, "a fresh install hides the control");
  saveSettings({ showFilesControl: true });
  assert.equal(loadSettings().showFilesControl, true, "showing it survives a reload (localStorage)");
  assert.equal(JSON.parse(store["romp:settings"]).showFilesControl, true, "the key the shell reads, the literal true");
  saveSettings({ showFilesControl: false });
  assert.equal(loadSettings().showFilesControl, false, "turning it off again round-trips too");
  assert.equal(JSON.parse(store["romp:settings"]).showFilesControl, false, "on-then-off leaves the literal false");
  store["romp:settings"] = JSON.stringify({ compact: true });
  assert.equal(loadSettings().showFilesControl, false, "a store written before the key hides the control");
  store["romp:settings"] = JSON.stringify({ showFilesControl: "yes" });
  assert.equal(loadSettings().showFilesControl, false, "a foreign stored value hides it: only true shows");
  // the T317-era key: that gear merged its default filesControl: true into the object and saved the whole object on
  // ANY change, so a profile that touched any setting in that window carries filesControl: true without touching the
  // Files box. It is never read, and the next save drops it.
  store["romp:settings"] = JSON.stringify({ compact: true, filesControl: true });
  assert.equal(loadSettings().showFilesControl, false, "the old key's true is a merged-in default, not an opt-in: hidden");
  assert.equal("filesControl" in loadSettings(), false, "the old key is dropped from the loaded object");
  saveSettings({ compact: false });
  assert.deepEqual(Object.keys(JSON.parse(store["romp:settings"])).filter((k) => /filesControl/i.test(k)), ["showFilesControl"], "the next save leaves the old key behind and writes the fresh one");
  delete store["romp:settings"];
});

// The Artifacts control's key was retired by panes-as-data phase three (the pane is an experimental record; the gear's generic
// Panes row is its control): a browser that stored it sees it dropped at load and gone on the next save, like the repo's other
// retired keys (fileLinkPane, filesControl), never rewritten forever.
test("a stored showArtifactsControl is dropped at load and gone after a save", () => {
  delete store["romp:settings"];
  store["romp:settings"] = JSON.stringify({ compact: true, showArtifactsControl: true });
  const s = loadSettings() as unknown as Record<string, unknown>;
  assert.equal("showArtifactsControl" in s, false, "dropped at load");
  saveSettings({ compact: false });
  assert.equal("showArtifactsControl" in JSON.parse(store["romp:settings"]), false, "gone on the next save");
  delete store["romp:settings"];
});

test("saveSettings has no production caller (a whole-object save would stamp the current default into a store that never chose)", () => {
  // scan the webview AND the extension-host TS (either could call it); the kernel is Python and cannot call a TS symbol,
  // so grep it too to say so. No PRODUCTION module calls saveSettings; the gear posts settingsSync, render.ts only imports it.
  const roots = [path.resolve(process.cwd(), "..", "ui", "webview"), path.resolve(process.cwd(), "..", "vscode-extension", "src")];
  const callers = [];
  for (const dir of roots) {
    for (const f of fs.readdirSync(dir, { recursive: true })) {
      const rel = String(f);
      if (!rel.endsWith(".ts") || rel.endsWith(".test.ts") || rel.endsWith("settings.ts")) continue;
      const p = path.join(dir, rel);
      try { if (/\bsaveSettings\s*\(/.test(fs.readFileSync(p, "utf8"))) callers.push(path.join(path.basename(dir), rel)); } catch { /* a dir entry */ }
    }
  }
  assert.deepEqual(callers, [], "no webview or extension-host module CALLS saveSettings (the gear posts settingsSync; render.ts only imports it): a caller must not be added without the fresh-key rule, since a save stamps DEFAULT_SETTINGS.tabStateBadge (true today) into a never-chose store and would defeat a future flip to off");
  const kernel = fs.readFileSync(path.resolve(process.cwd(), "..", "kernel", "kernel.py"), "utf8");
  assert.doesNotMatch(kernel, /\bsaveSettings\s*\(/, "the kernel is Python: it does not call the webview's saveSettings either");
});
