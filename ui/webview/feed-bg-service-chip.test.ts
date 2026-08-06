// The neutral background-process chip on the grouped-mode session header (the user 2026-07-24): a
// process the session KEEPS running (a dev server the judge classified as nobody-waits — kernel
// _bg_split / the payload's bgServices) is session furniture, not a waiting state. It must never wear
// awaiting/urgency framing; it rides the session header as a dim chip whose click expands the process
// list (keyed on sid, so the expansion survives re-renders).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.css"), "utf8");

test("the payload's bgServices map lands in a module store keyed by session name", () => {
  assert.match(FEED, /let bgServicesMap: Record<string, string\[\]> = \{\};/);
  assert.match(FEED, /bgServicesMap = m\.bgServices && typeof m\.bgServices === "object" \? m\.bgServices : \{\};/);
});

test("the chip is built on the session header, chip-vocabulary, hidden until services exist", () => {
  assert.match(FEED, /const svc = el\("button", "fask-secbtn feed-sess-svcbtn"\); svc\.style\.display = "none";/);
  assert.match(FEED, /const svcList = el\("div", "feed-sess-svclist"\); svcList\.style\.display = "none";/);
  assert.match(FEED, /svc\.style\.display = procs\.length \? "" : "none";/);
  // dead sessions show no chip — their processes died with the CLI
  assert.match(FEED, /const procs = e\.live \? bgServicesMap\[e\.name\] \|\| \[\] : \[\];/);
});

test("the chip label counts plainly and says nothing about waiting", () => {
  assert.match(FEED, /procs\.length === 1 \? "background process" : procs\.length \+ " background processes"/);
  // no waiting/urgency words anywhere in the chip's strings
  assert.doesNotMatch(FEED, /feed-sess-svcbtn[\s\S]{0,600}[Ww]aiting/);
});

test("click expands the process list, keyed on sid so it survives re-renders", () => {
  assert.match(FEED, /const openBgSvc = new Set<string>\(\);/);
  assert.match(FEED, /if \(openBgSvc\.has\(e\.sid\)\) openBgSvc\.delete\(e\.sid\); else openBgSvc\.add\(e\.sid\);/);
  assert.match(FEED, /const open = procs\.length > 0 && openBgSvc\.has\(e\.sid\);/);
  assert.match(FEED, /svc\.classList\.toggle\("on", open\);/);   // selected-toggle accent, the accent's one job here
  assert.match(FEED, /svcList\.style\.display = open \? "" : "none";/);
});

test("the CSS keeps it neutral: dim chip, section-body sized list, no status colors", () => {
  // un-bolds from the header's 600 so it reads as a label, not a second title
  assert.match(CSS, /\.feed-sess-svcbtn \{ font-weight: 400; \}/);
  // full-width line under the header (the header wraps), 0.86em like the other section bodies
  assert.match(CSS, /\.feed-sess-svclist \{ flex-basis: 100%;[^}]*font-size: 0\.86em; color: var\(--dim\); \}/);
  assert.match(CSS, /\.feed-sess-head \{ display: flex; flex-wrap: wrap;/);
  // never the working/blocked status colors
  assert.doesNotMatch(CSS, /\.feed-sess-svc(btn|list|row)[^}]*st-working/);
  assert.doesNotMatch(CSS, /\.feed-sess-svc(btn|list|row)[^}]*#f66/);
});

test("the expanded list WRAPS inside the column instead of running on (the user 2026-08-06)", () => {
  // A process description is a sentence. Truncating it dead-ends the one surface that exists to show it,
  // and `white-space: nowrap` on the row did worse than truncate: the list is a FLEX item, whose default
  // min-width:auto is its min-content size, so it could not shrink to the column — the line ran out past
  // the column's edge and under the neighbouring one.
  assert.match(CSS, /\.feed-sess-svclist \{[^}]*min-width: 0;/);
  assert.doesNotMatch(CSS, /\.feed-sess-svcrow \{[^}]*white-space: nowrap/);
  assert.doesNotMatch(CSS, /\.feed-sess-svcrow \{[^}]*text-overflow: ellipsis/);
  assert.match(CSS, /\.feed-sess-svcrow \{[^}]*overflow-wrap: anywhere/);   // a long path/url breaks too
});
