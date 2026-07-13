// Strikethrough must require DOUBLE tildes (the user 2026-06-26): marked's built-in GFM `del` fires on a
// SINGLE tilde, so prose with two "approximately" tildes ("~21 Wh … ~1.5 days") rendered as one big struck-
// through run. render.ts overrides the `del` tokenizer to require ~~ (matching GitHub). This test mirrors
// that config and checks behavior, then source-pins render.ts so the two can't drift.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { marked } from "marked";
import * as fs from "node:fs";
import * as path from "node:path";

marked.setOptions({ gfm: true, breaks: false });
marked.use({
  tokenizer: {
    del(src: string) {
      const m = /^~~(?=\S)([\s\S]*?\S)~~/.exec(src);
      if (!m) return undefined;
      return { type: "del", raw: m[0], text: m[1], tokens: (this as { lexer: { inlineTokens(s: string): unknown[] } }).lexer.inlineTokens(m[1]) };
    },
  },
} as Parameters<typeof marked.use>[0]);

test("a single ~ (approximately) does NOT strike through", () => {
  const html = marked.parse("near the ~21 Wh/day budget and it gives ~1.5 days of buffer") as string;
  assert.doesNotMatch(html, /<del>/, "lone tildes stay literal — no strikethrough");
  assert.match(html, /~21/);
  assert.match(html, /~1\.5/);
});

test("double ~~ still strikes through", () => {
  const html = marked.parse("this is ~~struck~~ out") as string;
  assert.match(html, /<del>struck<\/del>/);
});

test("render.ts ships the same del-requires-double-tilde override", () => {
  const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
  assert.match(RENDER, /del\(src: string\)/);
  assert.match(RENDER, /\/\^~~\(\?=\\S\)\(\[\\s\\S\]\*\?\\S\)~~\//, "the ~~-only del regex");
});
