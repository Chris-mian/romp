// Cmd/Ctrl+F inside a romp panel does nothing unless the panel asks VS Code for its find widget at creation
// (WebviewPanelOptions.enableFindWidget): a webview gets no editor find, and the chat bundle has no find of
// its own — the browser's native find covers the web dashboard, nothing covered the editor (the user
// 2026-09-21). Every panel the extension creates opts in; a webview VIEW (the timeline) has no such option
// in the API, so it is not counted here. Source pins (extension.ts pulls in `vscode` and cannot be imported).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const SRC = fs.readFileSync(path.join(process.cwd(), "src", "extension.ts"), "utf8");

test("every webview PANEL is created with VS Code's find widget enabled", () => {
  const panels = SRC.match(/createWebviewPanel\(/g) || [];
  assert.equal(panels.length, 3, "chat, feed, outline");
  // each creation's options object (the fourth argument) names the option, right beside enableScripts
  const re = /createWebviewPanel\(\s*"(\w+)",[\s\S]*?\{\s*enableScripts: true,\s*enableFindWidget: true,[^\n]*\n\s*retainContextWhenHidden: true,/g;   // the option may carry its comment
  const ids: string[] = [];
  let m: RegExpExecArray | null;
  while ((m = re.exec(SRC))) ids.push(m[1]);
  assert.deepEqual(ids, ["rompChat", "rompFeed", "rompFleet"], "each panel's options carry enableFindWidget: true, in the same place");
});
