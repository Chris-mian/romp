// TABS-FIRST (the user 2026-06-26): the chat tab strip used to skip a tab until its session arrived, so
// tabs popped in one-by-one on a cold load. The kernel's tabOrder push now carries name+color per tab, and
// renderTabs paints the WHOLE strip up front — an id whose session hasn't landed yet draws as a
// non-interactive placeholder that fills in when build_session arrives. Source pins (no jsdom for the strip).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("a tabMeta map holds the kernel's name+color per tab", () => {
  assert.match(RENDER, /const tabMeta = new Map<string, \{ name: string; color: Color \| null \}>\(\);/);
});

test("applyTabOrder REBUILDS tabMeta from the authoritative payload (closed tabs don't linger)", () => {
  assert.match(RENDER, /function applyTabOrder\(o: any, tabs\?: any\)/);
  assert.match(RENDER, /if \(Array\.isArray\(tabs\)\) \{\s*tabMeta\.clear\(\);/);
  assert.match(RENDER, /else if \(m\.type === "tabOrder"\) applyTabOrder\(m\.order, m\.tabs\);/);
});

test("renderTabs renders the union of arrived sessions and tabMeta, placeholders for the rest", () => {
  assert.match(RENDER, /for \(const id of tabMeta\.keys\(\)\)/);
  assert.match(RENDER, /if \(!s\) \{ bar\.appendChild\(makePlaceholderTab\(id\)\); continue; \}/);
});

test("makePlaceholderTab draws name + identity color, non-interactive (no data-act)", () => {
  assert.match(RENDER, /function makePlaceholderTab\(id: string\): HTMLElement/);
  assert.match(RENDER, /tab\.classList\.add\("colored"\)/);
  // a placeholder must NOT declare a select/close action — it's inert until the session lands
  const fn = RENDER.slice(RENDER.indexOf("function makePlaceholderTab"), RENDER.indexOf("function renderTabs"));
  assert.doesNotMatch(fn, /dataset\.act/);
});

test("the placeholder has a loading pulse and is non-interactive in CSS", () => {
  assert.match(CSS, /\.tab\.tab-placeholder \{ cursor: default; animation: tab-ph-pulse/);
  assert.match(CSS, /@keyframes tab-ph-pulse/);
});
