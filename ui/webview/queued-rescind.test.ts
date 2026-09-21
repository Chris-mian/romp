// The rescind's inverse rules (T373), EXECUTED: a queued message's outgoing body back into the composer's text, quote
// citations and attachment paths, round-tripping quoteReplyBody and the send's trailing paths line. Synthetic text only.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { quoteReplyBody } from "./staged-messages";
import { splitQuoteReplyBody, splitTrailingPaths, rescindedComposerState } from "./queued-rescind";

test("quote sections come back as citations and the text follows; a body without them is text alone", () => {
  const cites = [{ quote: "the handler reads the note by id", src: null }, { quote: "line one\nline two", src: "api/notes.py:12-14" }];
  const body = quoteReplyBody(cites, "why does the second read happen?");
  assert.deepEqual(splitQuoteReplyBody(body), { cites: [{ quote: "the handler reads the note by id" }, { quote: "line one\nline two", src: "api/notes.py:12-14" }], text: "why does the second read happen?" });
  assert.deepEqual(splitQuoteReplyBody("plain words\n\n> a quote the user typed"), { cites: [], text: "plain words\n\n> a quote the user typed" }, "a quote the user typed is not a citation section");
  assert.deepEqual(splitQuoteReplyBody(quoteReplyBody([{ quote: "context only" }], "")), { cites: [{ quote: "context only" }], text: "" }, "a citation with nothing typed");
});

test("the trailing paths line comes off as files by the record alone: no record, no guess", () => {
  assert.deepEqual(splitTrailingPaths("look at these\nplots/a.png \"docs/with space.md\"", ["plots/a.png", "docs/with space.md"]), { text: "look at these", files: ["plots/a.png", "docs/with space.md"] });
  assert.deepEqual(splitTrailingPaths("look at these\nplots/a.png docs/report.pdf", ["plots/a.png", "docs/report.pdf"]), { text: "look at these", files: ["plots/a.png", "docs/report.pdf"] }, "an image and a document alike (the fold's medium: the record is every attachment, not the images)");
  assert.deepEqual(splitTrailingPaths("look at these\nplots/a.png", ["plots/b.png"]), { text: "look at these\nplots/a.png", files: [] }, "a record that does not match leaves the text whole");
  assert.deepEqual(splitTrailingPaths("see https://example.test/a and /var/log/x.log"), { text: "see https://example.test/a and /var/log/x.log", files: [] }, "a user's own URL or path line is never an attachment without a record (the fold's low)");
  assert.deepEqual(splitTrailingPaths("plots/a.png"), { text: "plots/a.png", files: [] }, "even a bare path alone stays words without a record");
});

test("a pasted excerpt whose first line is the send's own lead reads as a citation and re-composes but for one blank line (accepted, documented)", () => {
  const pasted = "Replying to this part of the conversation:\n> the pasted quote\n\nmy words";
  const back = splitQuoteReplyBody(pasted);
  assert.deepEqual(back, { cites: [{ quote: "the pasted quote" }], text: "my words" });
  assert.equal(quoteReplyBody(back.cites, back.text), pasted, "the round trip is byte-exact here; only an excerpt with extra blank lines between lead and text differs by them");
});

test("the whole state: text, citations and files, round-tripped from what the send composed", () => {
  const body = quoteReplyBody([{ quote: "the retry curve" }], "plot it again") + "\nplots/retry.png";
  assert.deepEqual(rescindedComposerState(body, ["plots/retry.png"]), { text: "plot it again", cites: [{ quote: "the retry curve" }], files: ["plots/retry.png"] });
  assert.deepEqual(rescindedComposerState("just words"), { text: "just words", cites: [], files: [] });
});

// ── the wiring (source pins, the repo's convention for the DOM half) ─────────────────────────────────────────────────
import * as fs from "node:fs";
import * as path from "node:path";
const ROOT = path.resolve(process.cwd(), "..");
const RENDER = fs.readFileSync(path.join(ROOT, "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.join(ROOT, "ui", "webview", "styles.css"), "utf8");
const KERNEL = fs.readFileSync(path.join(ROOT, "kernel", "kernel.py"), "utf8");
const SDKBE = fs.readFileSync(path.join(ROOT, "kernel", "sdk_backend.py"), "utf8");
const BUBBLE = RENDER.slice(RENDER.indexOf("function renderQueued("), RENDER.indexOf("\nfunction restoreToComposer("));
const RESCIND = RENDER.slice(RENDER.indexOf("function rescindQueued(el: HTMLElement, toComposer: boolean): void {"), RENDER.indexOf("\n}\n", RENDER.indexOf("function rescindQueued(")));

test("the queued message's one control is the ✎, which rescinds it to the composer; the ✕ stays on commands and romp's own words (T373)", () => {
  assert.match(BUBBLE, /if \(t\.cancelable && \(isCmd \|\| t\.romp\) && \(t\.idx !== undefined \|\| t\.park !== undefined \|\| t\.optimistic\)\) \{\s*\n\s*const x = el\("button", "queued-x"\);/, "the cross: a command's or romp's");
  assert.match(BUBBLE, /if \(t\.cancelable && !t\.romp && !isCmd && \(t\.idx !== undefined \|\| t\.park !== undefined \|\| t\.optimistic\)\) \{\s*\n\s*bubble\.classList\.add\("editable"\);\s*\n\s*const ed = el\("button", "queued-edit"\);/, "the pencil: a message's");
  assert.match(BUBBLE, /ed\.title = "edit this queued message — it leaves the queue and comes back into the message box";/);
  assert.match(BUBBLE, /\(ed as any\)\._qimgs = t\.imgPaths;/, "the attachments the bubble shows ride the control");
  assert.match(BUBBLE, /\(ed as any\)\._qgoal = t\.goalId \? \{ itemId: t\.goalId, title: t\.goal \|\| "" \} : null;/, "a follow-up's goal rides it for its chip");
  assert.match(RENDER, /qedit: \(el\) => rescindQueued\(el, true\),/);
  assert.match(RENDER, /qx: \(el\) => rescindQueued\(el, false\),/);
  assert.match(RESCIND, /const msg: Record<string, unknown> = \{ type: "cancelQueued", id: sidQ, md: qmd \};/, "the rescind IS the cancel: the same kernel route clears every other client's bubble");
  assert.match(RESCIND, /if \(goal && goal\.itemId\) \{ setCitation\(sidQ, \{ itemId: goal\.itemId, title: goal\.title \}\); armedCites\.push\("g:" \+ goal\.itemId\); \}/, "a follow-up comes back on its goal");
  assert.match(RESCIND, /else if \(back\.cites\.length\) \{ composerCitations\.set\(sidQ,/, "quote citations come back as chips");
  assert.match(RESCIND, /if \(!provisional\) pendingCancelRestores\.set\(activeId \+ " " \+ qmd, \{ before, after: ta \? ta\.value : "", cites: citesBefore, files: filesBefore, armedCites, armedFiles \}\);/, "a refused cancel can undo the restore, as before");
  assert.match(CSS, /\.queued-edit \{\s*\n\s*position: absolute; top: 3px; right: 4px;/, "the pencil sits in the cross's corner");
  assert.match(CSS, /\.queued-bubble\.editable \{ padding-right: 28px; \}/, "room for the one control");
});

test("no in-place editor remains, on the page, in the styles, in the kernel or in the backend (T373)", () => {
  for (const word of ["queuedEditors", "openQueuedEditor", "renderQueuedEditor", "saveQueuedEditor", "holdQueued", "editQueued", "editResult", "queued-editnote", "queued-held-label", "applyQueuedEditLocally", "pendingEditRestores"])
    assert.ok(!RENDER.includes(word), "render.ts still says " + word);
  for (const word of [".queued-editor", ".queued-editbox", ".queued-editbtn", ".queued-held-label", ".queued-editnote", ".queued-bubble.editing"])
    assert.ok(!CSS.includes(word), "styles.css still has " + word);
  for (const word of ['t == "holdQueued"', 't == "editQueued"', "_park_holds", "_parked_held", "_hold_parked", "_hold_backend_queued", "_release_client_holds", "_edit_parked", "_edit_backend_queued", '"editQueued", "holdQueued"'])
    assert.ok(!KERNEL.includes(word), "kernel.py still has " + word);
  for (const word of ["_pending_hold", "def hold_queued", "def release_queued", "def release_holds_by", "def replace_queued", "def edit_queued", "_feed_index_locked"])
    assert.ok(!SDKBE.includes(word), "sdk_backend.py still has " + word);
  assert.match(KERNEL, /m\["goalId"\] = _gid\.group\(1\)/, "the queued follow-up carries its goal id for the rescind's chip");
  assert.match(KERNEL, /op = ops\[0\]\s*\n\s*if op\[0\] == "send":\s*\n\s*run = \[\]/, "the parked walk takes the head op again");
  assert.match(SDKBE, /fi = 0 if \(self\._pending and not blocked\) else -1/, "the feeder feeds the head again");
});
