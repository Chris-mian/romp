// Pasting a local file's PATH into the composer attaches the FILE (the user 2026-08-11): the
// path text used to ride the prompt verbatim, which on a remote session names a file that exists
// only on this machine — the agent couldn't open it, while dragging the same file worked (drops
// ship bytes). Now a paste whose WHOLE text is one path to a kind /file can serve is verified
// against the PAGE's own kernel — the machine the paste came from — and converted into the same
// visible attachment chip a drop produces: the zero-copy path for a locally-owned session,
// shipped bytes (the existing dropFile route) for a remote one. A miss (404: not a local file, or
// a path from some other machine) puts the EXACT text back at the cursor, so nothing changes for
// ordinary text. pastedFilePath is a pure module (unit-tested below); the renderer has no jsdom
// harness, so the wiring is pinned at the source level like the other composer tests.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { pastedFilePath } from "./paste-path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const PASTE = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "paste-path.ts"), "utf8");

test("pastedFilePath accepts the whole-paste single-path shapes people actually paste", () => {
  // the plain absolute path, and ~ (the kernel's _resolve_open_path expands it server-side)
  assert.deepEqual(pastedFilePath("/tmp/shot.png"), { path: "/tmp/shot.png" });
  assert.deepEqual(pastedFilePath("~/Desktop/Screenshot 2026-08-11 at 8.12.01 PM.png"),
    { path: "~/Desktop/Screenshot 2026-08-11 at 8.12.01 PM.png" });
  // Finder/shell quote wrappers come off
  assert.deepEqual(pastedFilePath("'/tmp/a b.png'"), { path: "/tmp/a b.png" });
  assert.deepEqual(pastedFilePath('"/tmp/a b.png"'), { path: "/tmp/a b.png" });
  // terminal drag escaping (\ , \( …) is unescaped
  assert.deepEqual(pastedFilePath("/tmp/Screenshot\\ at\\ 8.12.01\\ PM.png"),
    { path: "/tmp/Screenshot at 8.12.01 PM.png" });
  // file:// URI form is decoded (empty or localhost authority)
  assert.deepEqual(pastedFilePath("file:///tmp/x%20y.png"), { path: "/tmp/x y.png" });
  assert.deepEqual(pastedFilePath("file://localhost/tmp/x.pdf"), { path: "/tmp/x.pdf" });
  // pdf is in the /file allowlist too
  assert.deepEqual(pastedFilePath("/tmp/report.pdf"), { path: "/tmp/report.pdf" });
  // surrounding whitespace (a copied line) is fine
  assert.deepEqual(pastedFilePath("  /tmp/shot.png\n"), { path: "/tmp/shot.png" });
});

test("pastedFilePath rejects everything that is prose, partial, or unservable", () => {
  // prose that mentions a path, before or after — the paste must BE the path
  assert.equal(pastedFilePath("see /tmp/shot.png please"), null);
  assert.equal(pastedFilePath("/tmp/shot.png is broken"), null);
  // multi-line pastes are never one path
  assert.equal(pastedFilePath("/tmp/a.png\n/tmp/b.png"), null);
  // relative paths and bare words are prose (no cwd to resolve against — /file requires absolute)
  assert.equal(pastedFilePath("shots/x.png"), null);
  assert.equal(pastedFilePath("hello"), null);
  // kinds /file won't serve stay text: code files, data, extensionless dirs
  assert.equal(pastedFilePath("/tmp/notes.txt"), null);
  assert.equal(pastedFilePath("/tmp/data.csv"), null);
  assert.equal(pastedFilePath("/tmp/somedir"), null);
  assert.equal(pastedFilePath(""), null);
});

test("the allowlist is previewKind's, imported — never a third copy to drift", () => {
  assert.match(PASTE, /import \{ previewKind \} from "\.\/preview";/);
  assert.match(PASTE, /if \(!previewKind\(s\)\) return null;/);
});

test("a path-shaped paste is verified on the PAGE's own kernel and converted, web only", () => {
  // recognition + the web gate (the VS Code webview can't reach /file; its drops carry File.path)
  assert.match(RENDER, /const pasted = pastedFilePath\(raw\);/);
  assert.match(RENDER, /if \(!pasted \|\| !canPreview\(\)\) return;/);
  // verified via fileUrl with NO sid — the page's own kernel, never routed to some other machine's
  // disk; HEAD for a local session (existence only), GET when the bytes must ship
  assert.match(RENDER, /fetch\(fileUrl\(pasted\.path\), \{ method: remote \? "GET" : "HEAD" \}\)/);
});

test("a local session keeps the zero-copy path; a remote one ships the bytes it verified", () => {
  assert.match(RENDER, /if \(!remote\) \{ addComposerFile\(sid, pasted\.path\); return; \}/);
  // the bytes ride the EXISTING dropFile pipeline (pending chip, 50 MB cap, droppedPath ack) —
  // with the sid captured when the user pasted, so a tab switch mid-verify can't reroute them
  assert.match(RENDER,
    /shipFileToHost\(new File\(\[blob\], pasted\.path\.split\("\/"\)\.pop\(\) \|\| "pasted", \{ type: blob\.type \}\), sid\);/);
});

test("a miss puts the EXACT pasted text back — plain text behaves exactly like today", () => {
  assert.match(RENDER, /ta\.setRangeText\(raw, selS, selE, "end"\);\s*\n\s*ta\.dispatchEvent\(new Event\("input", \{ bubbles: true \}\)\);/);
  // a tab switch mid-verify lands the text in THAT session's draft instead of the wrong box
  assert.match(RENDER, /drafts\.set\(sid, \(drafts\.get\(sid\) \|\| ""\) \+ raw\);/);
  // network failure degrades the same way (text, not silence)
  assert.match(RENDER, /\}\)\.catch\(putBack\);/);
});

test("an oversize pasted path is refused LOUDLY, and the text still lands", () => {
  assert.match(RENDER, /if \(r\.status === 413\) \{/);
  assert.match(RENDER, /is too large to attach from a "\s*\n\s*\+ "pasted path — it was pasted as text instead\./);
});
