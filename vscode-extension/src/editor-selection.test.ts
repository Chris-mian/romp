// Editor highlight-to-reply (the user 2026-07-13): selecting text in a real file seeds the chat
// composer's quote chip — the extension host listens on onDidChangeTextEditorSelection and posts
// editorSelection {text, src} into the chat webview (render.ts seeds the chip; composer-citation.test.ts
// pins that side). Host-side pins, matching the webview's selection rules: never clear on a collapse,
// never summon the panel, only real files.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.join(process.cwd(), "src", "extension.ts"), "utf8");

test("a non-empty selection in a file-scheme editor posts editorSelection {text, src} to the chat webview", () => {
  assert.match(SRC, /vscode\.window\.onDidChangeTextEditorSelection\(\(e\) => \{/);
  assert.match(SRC, /toWebview\(\{ type: "editorSelection", text: text\.slice\(0, 4000\), src \}\);/);
  // src = workspace-relative file:startLine[-endLine]; the column-0 end excludes that line (citeInComposer's rule)
  assert.match(SRC, /const rel = vscode\.workspace\.asRelativePath\(e\.textEditor\.document\.uri, false\);/);
  assert.match(SRC, /const src = rel \+ ":" \+ \(sel\.start\.line \+ 1\) \+ \(endLine > sel\.start\.line \+ 1 \? "-" \+ endLine : ""\);/);
});

test("a collapse never clears, a selection never summons the panel, and non-file schemes are ignored", () => {
  assert.match(SRC, /if \(!panel \|\| e\.textEditor\.document\.uri\.scheme !== "file"\) return;/);
  assert.match(SRC, /if \(!sel \|\| sel\.isEmpty\) return;\s*\/\/ never clear on collapse/);
});
