// Expand/collapse state must SURVIVE the incremental re-render a send/turn triggers (the user 2026-06-19):
// a short transcript rebuilds from index 0, a long one re-renders the trailing TAIL_RECHECK turns, so a
// DOM-only `.open`/`.expanded` silently snaps shut whatever the user had opened (the reported bug: expand
// the system-context card, type, hit ⏎ → it collapses). We persist open-state in a module Set keyed by a
// stable id and reapply on rebuild. No jsdom harness for the renderer, so pin the wiring at the source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");

test("there is a persisted-fold registry with apply/remember helpers", () => {
  assert.match(RENDER, /const openFolds = new Set<string>\(\);/);
  assert.match(RENDER, /function applyFold\(target: HTMLElement, cls: string, key\?: string\)/);
  assert.match(RENDER, /function rememberFold\(target: HTMLElement, cls: string, key\?: string\)/);
  // apply reinstates on (re)build; remember toggles + records the new state
  assert.match(RENDER, /if \(key && openFolds\.has\(key\)\) target\.classList\.add\(cls\)/);
  assert.match(RENDER, /if \(open\) openFolds\.add\(key\); else openFolds\.delete\(key\)/);
});

test("the system-context card persists per session (keyed by renderingSid)", () => {
  assert.match(RENDER, /renderingSid = id;/, "syncView records which session it's building");
  assert.match(RENDER, /const key = renderingSid \? "sysctx:" \+ renderingSid : undefined;/);
  assert.match(RENDER, /applyFold\(card, "open", key\)/);
  assert.match(RENDER, /rememberFold\(card, "open", key\)/);
});

test("foldable/inlineFold/ioClamp take a stable key and route through the persisted helpers", () => {
  assert.match(RENDER, /function foldable\(label: string, content: HTMLElement, key\?: string\)/);
  assert.match(RENDER, /function inlineFold\(head: HTMLElement, turn: HTMLElement, label: string, content: HTMLElement, key\?: string\)/);
  assert.match(RENDER, /function ioClamp\(input: string, output: string, isError: boolean, key\?: string\)/);
});

test("the other collapsibles pass stable keys (reminders, tool folds, thinking)", () => {
  assert.match(RENDER, /"rem:" \+ ev\.uuid/, "system reminders key on the user turn uuid");
  assert.match(RENDER, /const fkey = ev\.uuid \? "tool:" \+ ev\.uuid : undefined;/, "tool folds key on the tool uuid");
  assert.match(RENDER, /"think:" \+ ev\.uuid/, "thinking clamp keys on the thinking uuid");
  // the agent prompt vs report get distinct sub-keys so they don't toggle each other
  assert.match(RENDER, /fkey \+ ":prompt"/);
  assert.match(RENDER, /fkey \+ ":report"/);
});
