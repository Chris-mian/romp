import { test } from "node:test";
import * as assert from "node:assert/strict";

// Minimal localStorage shim BEFORE importing the module (load/save read it at call time).
const store: Record<string, string> = {};
(globalThis as any).localStorage = {
  getItem: (k: string) => (k in store ? store[k] : null),
  setItem: (k: string, v: string) => { store[k] = v; },
  removeItem: (k: string) => { delete store[k]; },
};
import { loadSettings, saveSettings, DEFAULT_SETTINGS } from "./settings";

test("loadSettings returns defaults when nothing is stored", () => {
  delete store["romp:settings"];
  assert.deepEqual(loadSettings(), DEFAULT_SETTINGS);
});

test("the Sub-goals card pref defaults ON; the old Explanations pref is gone (the user 2026-06-18)", () => {
  assert.equal(DEFAULT_SETTINGS.subgoals, true);
  assert.equal((DEFAULT_SETTINGS as any).explanations, undefined);
});

test("Debug mode defaults OFF (the user 2026-06-17): refresh button + judging band stay hidden", () => {
  assert.equal(DEFAULT_SETTINGS.debug, false);
});

test("Default backend defaults to tmux (the user 2026-06-22): the + button preserves today's behavior; both backends coexist", () => {
  assert.equal(DEFAULT_SETTINGS.backend, "tmux");
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
