// Native Claude Code TEAMMATE message rendering (the user 2026-07-05): one agent messages another over
// Claude Code's own agent-to-agent channel (not romp's postal bus). It used to render as a blue "you typed
// this" bubble full of coordination JSON. renderTeammate gives it its OWN collapsed card — like the postal
// card in AFFORDANCE (collapse→expand) but deliberately UNLIKE it in look: no per-peer color, no romp swirl,
// no from/to arrow, no colored session chip — so it's tellable apart from a romp-postal message at a glance.
// No jsdom for the chat renderer (the repo convention) → pin the wiring at source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
// renderTeammate's function body, isolated so the "must NOT look like postal" asserts can't be satisfied by
// an unrelated part of the file.
const BODY = (RENDER.match(/function renderTeammate\([\s\S]*?\n}\n/) || [""])[0];

test("a kind:'teammate' event carries per-sender blocks and is dispatched to renderTeammate", () => {
  assert.match(RENDER, /kind: "teammate"; blocks: \{ id: string; summary\?: string; body: string \}\[\]/);
  assert.match(RENDER, /if \(ev\.kind === "teammate"\) return renderTeammate\(ev\);/);
  assert.ok(BODY, "renderTeammate is defined");
});

test("it is its own neutral card — a 'teammate' tag + plain agent names + the collapse affordance", () => {
  assert.match(BODY, /el\("div", "turn turn-teammate"\)/);
  assert.match(BODY, /el\("div", "teammate-card"\)/);
  assert.match(BODY, /"teammate-tag"/);
  assert.match(BODY, /el\("span", "teammate-names"\)/);
  // collapse→expand, same affordance as the postal card
  assert.match(BODY, /classList\.add\("teammate-expandable"\)/);
  assert.match(BODY, /body\.classList\.toggle\("expanded"\)/);
});

test("it is DIFFERENTIABLE from a romp postal card — no color, no swirl, no session chip", () => {
  assert.doesNotMatch(BODY, /makeSessionChip/, "no clickable colored session chip (that's the postal card's language)");
  assert.doesNotMatch(BODY, /setPeerDot/, "no peer working-dot");
  assert.doesNotMatch(BODY, /--peer-bg|--peer-fg/, "no per-peer color chrome");
  assert.doesNotMatch(BODY, /romp-swirl-glyph|romp-logo/, "no romp swirl — this is NOT from romp's postal service");
  assert.doesNotMatch(BODY, /postal-service/, "does not reuse the postal card classes");
});

test("the teammate card CSS is a neutral (dashed, colorless) frame that shares only the expand toggle", () => {
  assert.match(CSS, /\.teammate-card \{[^}]*dashed/, "a dashed monochrome frame, not a colored postal bar");
  assert.doesNotMatch(CSS, /\.teammate-card[^}]*--peer-bg/, "no per-peer color var on the teammate card");
  assert.match(CSS, /\.teammate-expandable\.expanded \.teammate-full \{ display: block; \}/);
});
