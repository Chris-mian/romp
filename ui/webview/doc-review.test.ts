// Doc review wiring (the user 2026-08-14). No jsdom for the renderer here (the repo convention), so the
// reader's contract is pinned at source: what a clicked .md path opens, that the batch is DRAFTED and not
// sent, that every control is delegated (click-safe across re-renders), and that a stale file is called
// out loudly instead of shipping quietly-wrong line numbers.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "kernel", "kernel.py"), "utf8");

test("clicking a text document opens the reader instead of the OS editor", () => {
  assert.match(RENDER, /const DOC_REVIEW_EXT = \/\\\.\(\?:md\|markdown\|txt\)\$\/i;/);
  assert.match(RENDER, /const isDoc = DOC_REVIEW_EXT\.test\(open\);/);
  assert.match(RENDER, /if \(isDoc\) return openDocReview\(raw, open\);/);
  // ...and the old behavior stays reachable from the reader's own header
  assert.match(RENDER, /openIn\.textContent = "Open in editor ↗";/);
  assert.match(RENDER, /dropen: \(\) => \{[^}]*type: "openFile", path: docReview\.path/s);
});

test("the reader fetches the SOURCE from /doc, through kernelUrl so VS Code works too", () => {
  assert.match(RENDER, /kernelUrl\("\/doc\?path=" \+ encodeURIComponent\(path\)/);
  assert.match(RENDER, /&sid=" \+ encodeURIComponent\(bareId\(sid\)\)/);
});

test("the wait shows the romp loader, not a blank pane", () => {
  assert.match(RENDER, /function docLoader\(\)/);
  assert.match(RENDER, /el\("div", "rl-in"\)/);
  assert.match(RENDER, /el\("div", "rl-dots"\)/);
  assert.match(RENDER, /body\.appendChild\(docLoader\(\)\)/);
});

test("a remote session says so out loud rather than opening an empty reader", () => {
  assert.match(RENDER, /if \(hostOf\(sid\)\) \{/);
  assert.match(RENDER, /Doc review isn’t available for sessions on another machine yet/);
});

test("a failed load renders the kernel's reason in place — never a silent blank", () => {
  assert.match(RENDER, /docReviewErr = e\.message \|\| "could not read this file"/);
  assert.match(RENDER, /const err = el\("div", "dr-err"\)/);
  assert.match(CSS, /\.dr-err \{/);
});

test("Submit DRAFTS the batch into the composer — nothing is sent without the user", () => {
  const fn = RENDER.slice(RENDER.indexOf("function submitDocReview("));
  const body = fn.slice(0, fn.indexOf("\n}\n"));
  assert.match(body, /buildReviewMessage\(label, list\)/);
  assert.match(body, /docCommentsIntoComposer\(sid, text\)/);
  assert.doesNotMatch(body, /sendMessage/, "Submit must not send — it drafts");
  // the batch clears only once the text has landed
  assert.ok(body.indexOf("docCommentsIntoComposer") < body.indexOf("setDocList([])"));
});

test("the composer insert APPENDS, so it never clobbers a half-typed draft", () => {
  const fn = RENDER.slice(RENDER.indexOf("function docCommentsIntoComposer("));
  const body = fn.slice(0, fn.indexOf("\n}\n"));
  assert.match(body, /ta\.value = ta\.value \+ sep \+ text;/);
  assert.match(body, /drafts\.set\(sid, ta\.value\)/);
  assert.match(body, /persistDrafts\(\)/);
});

test("a file that changed under the reader is called out loudly before sending", () => {
  const fn = RENDER.slice(RENDER.indexOf("function submitDocReview("));
  const body = fn.slice(0, fn.indexOf("\n}\n"));
  assert.match(body, /docReviewStale = d\.mtime !== docReview\?\.mtime/);
  assert.match(body, /warnToast\("The file changed while you were reading it/);
  // a failed re-read must not fabricate staleness we never observed
  assert.match(body, /\.catch\(\(\) => \{ docReviewStale = false; \}\)/);
});

test("every reader control is DELEGATED — the reader rebuilds on each saved comment", () => {
  for (const act of ["drclose", "drsubmit", "dropen", "drsave", "drcancel", "drmark", "drdel"]) {
    assert.match(RENDER, new RegExp("\\n    " + act + ": "), act + " must be a delegated action handler");
    assert.match(RENDER, new RegExp('dataset\\.act = "' + act + '"'), act + " must be attached by data-act");
  }
  // ...and the reader's own builder attaches no click listener of its own: it rebuilds wholesale, so a
  // per-render handler would be destroyed mid-press (the click-safety rule).
  const build = RENDER.slice(RENDER.indexOf("function renderDocReview("));
  assert.doesNotMatch(build.slice(0, build.indexOf("\nfunction docLoader(")),
    /addEventListener\("click"/, "the reader's builder must not attach click listeners");
});

test("comments ride the draft lifecycle: persisted, restored, keyed per session AND file", () => {
  assert.match(RENDER, /docComments: Object\.fromEntries\(docComments\)/);
  assert.match(RENDER, /const savedDocs = \(\(vscodeApi\?\.getState\?\.\(\) \|\| \{\}\) as any\)\.docComments;/);
  assert.match(RENDER, /docComments\.get\(docKey\(docReview\.sid, docReview\.path\)\)/);
});

test("commented spans reuse the chat's re-anchoring, and mark up like its highlights", () => {
  assert.match(RENDER, /findAnchorRange\(nodes\.map\(\(t\) => t\.data\)\.join\(""\), c\.quote\)/);
  assert.match(RENDER, /sliceRanges\(nodes\.map\(\(t\) => t\.data\.length\), r\.start, r\.end\)/);
  assert.match(CSS, /mark\.dr-hl \{/);
  assert.match(CSS, /var\(--cmt-hl\)/);
});

test("the comment's text is one click under its marker (progressive disclosure)", () => {
  assert.match(RENDER, /docOpenComment = docOpenComment === id \? null : id;/);
  assert.match(RENDER, /pop\.className = "dr-note";/);
  assert.match(CSS, /\.dr-note \{/);
});

test("commenting uses the chat's own selection menu chrome — one menu vocabulary", () => {
  assert.match(RENDER, /const m = el\("div", "ctx-menu"\);/);
  assert.match(RENDER, /item\("Comment", \(\) => beginDocComment\(text\)\);/);
});

test("the panel dims the pane behind it rather than replacing it", () => {
  assert.match(CSS, /#doc-review \{[^}]*background: rgba\(0, 0, 0, 0\.55\)/s);
});

test("Esc closes the reader, and the comment box eats its own Esc first", () => {
  assert.match(RENDER, /if \(e\.key === "Escape" && docReview && !docPendingQuote\) \{[^}]*closeDocReview\(\)/s);
  assert.match(RENDER, /if \(e\.key === "Escape"\) \{ e\.preventDefault\(\); e\.stopPropagation\(\); docPendingQuote = null;/);
});

test("the kernel serves text documents only, capped, and 413s rather than truncating", () => {
  assert.match(KERNEL, /_DOC_EXT = \{"\.md", "\.markdown", "\.txt"\}/);
  assert.match(KERNEL, /_DOC_MAX_BYTES = 2_000_000/);
  assert.match(KERNEL, /if p == "\/doc":/);
  assert.match(KERNEL, /os\.path\.splitext\(fp\)\[1\]\.lower\(\) not in _DOC_EXT/);
  assert.match(KERNEL, /return self\._send\(413, "too large to review"/);
  // same path resolution as click-to-open and /file — a relative path lands in the session's repo
  assert.match(KERNEL, /fp = _resolve_open_path\(\(q\.get\("path"\) or \[""\]\)\[0\], \(q\.get\("sid"\) or \[None\]\)\[0\]\)\n *if os\.path\.splitext/);
});
