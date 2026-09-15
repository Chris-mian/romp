// THE EXTENSION'S OUTLINE PANEL DECLARES THE PROVISIONAL-ROW CAPABILITY (plans/outline-pane-provisional-row.md, 2026-09-15): the
// host builds its own connect URL for every panel (no query terms beyond app, wid and token), so without the term its Outline
// panel would be a permanently unflagged pane that disables the cold-tab gate for the whole kernel while open. The term rides the
// URL for the Outline app only, as the kernel's own shim adds it for the served Outline frame.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const EXT = fs.readFileSync(path.resolve(process.cwd(), "src", "extension.ts"), "utf8");

test("the panel's connect URL carries provrows=1 for the Outline app only", () => {
  assert.match(EXT, /\/ws\?app=\$\{this\.app\}&wid=\$\{encodeURIComponent\(vscode\.env\.sessionId\)\}&token=\$\{encodeURIComponent\(serveToken\(\)\)\}\$\{this\.app === "fleet" \? "&provrows=1" : ""\}/,
    "the Outline's dial declares the capability (the kernel reads it gated on the app); the other panels' dials are unchanged");
});
