// A mid-turn safeguards model swap must be visible in the chat, never silent (the user 2026-08-03:
// fable's safeguards flagged a message, the CLI silently retried on opus, and nothing in the chat said
// so). The kernel emits {kind:"modelFallback"} from the transcript's system/model_refusal_fallback
// record; render.ts wears it as the retried note's slim rail line in the warning voice, with the CLI's
// full explanation one click away. render.ts has import-time DOM side effects → source pins
// (rewind-delete.test.ts precedent).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(
  path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(
  path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("the modelFallback kind is dispatched to its renderer", () => {
  assert.match(RENDER, /if \(ev\.kind === "modelFallback"\) return renderModelFallback\(ev\);/);
  // and the union carries the payload the kernel sends (raw ids + the CLI's explanation)
  assert.match(RENDER, /kind: "modelFallback"; from\?: string; to\?: string; md\?: string/);
});

test("the head line names both models via prettyModel, in the warning voice", () => {
  const fn = RENDER.slice(RENDER.indexOf("function renderModelFallback"));
  const body = fn.slice(0, fn.indexOf("\n}"));
  assert.match(body, /prettyModel\(ev\.from\)/);
  assert.match(body, /prettyModel\(ev\.to\)/);
  assert.match(body, /safeguards flagged this message/);
  assert.match(body, /"retried-text modelswap-text"/, "warning-voice class on the head text");
  // never a red/blocked dress: a swap is a warning about provenance, not a failure of the turn
  assert.doesNotMatch(body, /apierror|gaveup/);
});

test("the full CLI notice is one click away and the fold survives re-renders", () => {
  const fn = RENDER.slice(RENDER.indexOf("function renderModelFallback"));
  const body = fn.slice(0, fn.indexOf("\n}"));
  assert.match(body, /body\.textContent = ev\.md;/, "verbatim notice — never paraphrased chrome");
  assert.match(body, /applyFold\(body, "expanded", key\)/);
  assert.match(body, /rememberFold\(body, "expanded", key\)/);
  assert.match(body, /"mswap:" \+ ev\.uuid/, "fold keyed by the record's uuid");
});

test("the body is hidden until expanded, styled in the note family", () => {
  assert.match(CSS, /\.modelswap-body \{ display: none;/);
  assert.match(CSS, /\.modelswap-body\.expanded \{ display: block; \}/);
  assert.match(CSS, /\.modelswap-text \{ color: var\(--warn/);
});
