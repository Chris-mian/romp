// A clicked path opens in the editor the way it opens on the web dashboard (the user 2026-09-21: "romp:
// couldn't open ~/specs/…/postmortem.md"). The webview posts the path AS WRITTEN in the transcript; the
// kernel's own handler expands `~` and resolves a relative path against the session's cwd
// (kernel.py _resolve_open_path), while the extension's opener handed the raw string to vscode.Uri.file —
// so a `~/` link (clickable since T351 stage 2, 2026-09-12) and any relative link failed in VS Code with
// the unexpanded path in the warning. open-path.ts is the kernel's rule, pure, executed here; the wiring
// into the openFile handler is a source pin. Synthetic paths only.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { resolveOpenPath, needsSessionDir } from "./open-path";

const SRC = fs.readFileSync(path.join(process.cwd(), "src", "extension.ts"), "utf8");
const HOME = "/home/TESTUSER";

test("~ expands against the REMOTE home; an absolute path passes through", () => {
  assert.equal(resolveOpenPath("~/specs/TESTSLUG/postmortem.md", HOME), "/home/TESTUSER/specs/TESTSLUG/postmortem.md");
  assert.equal(resolveOpenPath("~", HOME), "/home/TESTUSER");
  assert.equal(resolveOpenPath("/tmp/TESTHOST/notes.md", HOME), "/tmp/TESTHOST/notes.md");
  assert.equal(resolveOpenPath("/tmp/TESTHOST/a/../notes.md", HOME), "/tmp/TESTHOST/notes.md", "normalised, as path.resolve does");
  assert.equal(resolveOpenPath("~user/x.md", HOME), "~user/x.md", "another user's home is not expanded (the kernel's rule for `~user`)");
});

test("a file:// caption link opens its own path, percent-decoded", () => {
  assert.equal(resolveOpenPath("file:///tmp/TESTHOST/a%20b.md", HOME), "/tmp/TESTHOST/a b.md");
  assert.equal(resolveOpenPath("file://localhost/tmp/TESTHOST/c.md", HOME), "/tmp/TESTHOST/c.md", "an empty or localhost authority is this machine");
});

test("a relative path resolves against the SESSION's cwd when known, and is left for the caller to look up when not", () => {
  assert.equal(resolveOpenPath("design/foo.md", HOME, "/tmp/TESTHOST/repo"), "/tmp/TESTHOST/repo/design/foo.md");
  assert.equal(resolveOpenPath("./foo.md", HOME, "/tmp/TESTHOST/repo"), "/tmp/TESTHOST/repo/foo.md");
  assert.equal(resolveOpenPath("../foo.md", HOME, "/tmp/TESTHOST/repo/sub"), "/tmp/TESTHOST/repo/foo.md");
  assert.equal(resolveOpenPath("design/foo.md", HOME), "design/foo.md", "no cwd: unchanged, never resolved against the extension host's own cwd");
  assert.equal(resolveOpenPath("design/foo.md", HOME, ""), "design/foo.md", "an empty dir is no dir");
  assert.equal(needsSessionDir("design/foo.md"), true);
  assert.equal(needsSessionDir("/tmp/TESTHOST/x.md"), false);
  assert.equal(needsSessionDir(resolveOpenPath("~/x.md", HOME)), false, "expanded first, so a ~ path needs no session lookup");
});

test("the openFile handler resolves before it opens, looks the session's dir up only for a relative path, and names both paths on failure", () => {
  assert.match(SRC, /import \{ resolveOpenPath, needsSessionDir \} from "\.\/open-path";/);
  assert.match(SRC, /if \(m\.type === "openFile" && m\.path\) \{ void openFileResolved\(String\(m\.path\), m\.line, typeof m\.id === "string" \? m\.id : undefined\); return; \}/);
  assert.match(SRC, /let file = resolveOpenPath\(raw, os\.homedir\(\)\);/, "the remote home: the extension host runs on the machine the files are on");
  assert.match(SRC, /if \(needsSessionDir\(file\) && sid\) \{\n\s*const s = \(await fetchSessions\(\)\)\.find\(\(x\) => x\.id === sid\);\n\s*file = resolveOpenPath\(file, os\.homedir\(\), s \? s\.dir : null\);/, "one /sessions read, only when a relative path needs it");
  assert.match(SRC, /openFileInEditor\(file, line, raw\);/);
  assert.match(SRC, /vscode\.window\.showWarningMessage\(`romp: couldn't open \$\{file\}\$\{raw && raw !== file \? ` \(from \$\{raw\}\)` : ""\}`\);/, "the warning names what was tried, and what was written when that differs");
});
