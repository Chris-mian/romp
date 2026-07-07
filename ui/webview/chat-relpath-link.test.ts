// Click-to-open BARE file paths in the chat (the user 2026-07-06: "click `design/judge-simplification-plan.md`
// and open it"). The linkifier already handled file:// URIs; now it also linkifies absolute/anchored paths and
// relative paths that carry a file extension — while leaving prose like "and/or", "TCP/IP", "24/7" alone. A
// relative link posts the ACTIVE session id so the kernel resolves it against that session's cwd (the repo the
// agent runs in), not the kernel's launch cwd. render.ts has no jsdom harness → source pins + an executed
// replica of the precision predicate.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");

test("the linkifier matches file:// URIs AND bare paths, and gates bare tokens through looksLikeFilePath", () => {
  // one finder covers both the file: scheme and the bare-path alternative
  assert.ok(RENDER.includes("const CLICKABLE_PATH_RE = /file:"), "regex still handles file:// URIs");
  assert.ok(RENDER.includes("[~.\\w\\-]"), "regex has the bare-path alternative");
  assert.match(RENDER, /if \(!isUri && !looksLikeFilePath\(tok\)\) continue;/);
  assert.match(RENDER, /frag\.appendChild\(isUri \? fileUriLink\(tok\) : fileLink\(tok, tok, true\)\);/);
});

test("a relative path click carries the active session id so the kernel resolves against its cwd", () => {
  assert.match(RENDER, /function fileLink\(raw: string, open: string, relative = false\)/);
  assert.match(RENDER, /\{ type: "openFile", path: open, id: activeId \}/);   // relative → send the session id
  assert.match(RENDER, /\{ type: "openFile", path: open \}/);                 // absolute/file:// → no id needed
});

test("the cheap pre-filter now keys on a slash (not the file: scheme), so bare paths are considered", () => {
  assert.match(RENDER, /if \(!text\.includes\("\/"\)\) continue;/);
});

// executed: mirror looksLikeFilePath EXACTLY to guard its precision (accept real paths, reject prose)
test("looksLikeFilePath accepts real paths and rejects prose fractions/idioms", () => {
  const looksLikeFilePath = (tok: string): boolean => {
    if (tok.includes(":") || tok.includes("//") || !tok.includes("/")) return false;
    if (/^(?:~\/|\.{1,2}\/|\/)/.test(tok)) return true;
    return /\.[A-Za-z0-9]{1,8}$/.test(tok.slice(tok.lastIndexOf("/") + 1));
  };
  // accept — the user's exact case + common repo paths
  for (const p of ["design/judge-simplification-plan.md", "ui/webview/render.ts",
                   "/Users/x/a.md", "~/notes.md", "./foo.txt", "../a/b.py"]) {
    assert.equal(looksLikeFilePath(p), true, p);
  }
  // reject — prose that merely contains a slash, and un-autolinked URLs
  for (const p of ["and/or", "TCP/IP", "24/7", "read/write", "he/she",
                   "https://example.com/page.html", "bin/romp-kernel"]) {
    assert.equal(looksLikeFilePath(p), false, p);
  }
});

// executed: the finder regex actually pulls the path out of a sentence
test("CLICKABLE_PATH_RE finds the path token inside a sentence", () => {
  const re = /file:\/\/\/?[^\s<>"'`)]+|[~.\w\-]*\/[~.\w\-/]*[\w\-]/gi;
  const m = "see design/judge-simplification-plan.md for details".match(re);
  assert.deepEqual(m, ["design/judge-simplification-plan.md"]);
});
