// Artifact strips (the user 2026-07-08, removed upstream 2026-08-14, restored here 2026-08-19): a
// completed goal that PRODUCED files — a written document, a plot, a PDF report — shows "N artifacts"
// at the bottom of its summary, and the card modal renders them as click-to-expand previews. The
// CHAT-side preview core lives in preview-core.test.ts; this file owns the FEED surface plus the two
// paths that decide whether a card has artifacts at all: the kernel's subtree hoist and the judge's
// keep-what-you-recorded write. Source pins over feed.ts / both css sheets / the kernel / the judge.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const UI = path.resolve(process.cwd(), "..", "ui", "webview");
const FEED = fs.readFileSync(path.join(UI, "feed.ts"), "utf8");
const FEED_CSS = fs.readFileSync(path.join(UI, "feed.css"), "utf8");
const CHAT_CSS = fs.readFileSync(path.join(UI, "styles.css"), "utf8");
const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "bin", "romp-kernel"), "utf8");
const JUDGE = fs.readFileSync(path.resolve(process.cwd(), "..", "bin", "romp-judge"), "utf8");

test("feed card: 'N artifacts' rides the bottom of the summary section and opens the modal", () => {
  assert.match(FEED, /artifacts\?: string\[\] \| null;/, "AskItem carries the kernel's existence-filtered list");
  assert.match(FEED, /const artline = el\("div", "fask-artline nav"\); artline\.style\.display = "none";/);
  assert.match(FEED, /if \(choice === "summary" && arts\.length\) \{/, "shows only with the summary section open");
  assert.match(FEED, /arts\.length === 1 \? "1 artifact" : arts\.length \+ " artifacts"/);
  assert.match(FEED, /artline\.onclick = \(ev: Event\) => \{ ev\.stopPropagation\(\); fullscreenAskId = it\.itemId; renderModal\(\); \};/);
  assert.match(FEED_CSS, /\.fask-artline \{ font-size: 0\.86em;/, "same size as the summary body it sits in");
});

test("feed modal: artifacts strip below the tree — previews on the web, open-the-file chips in VS Code", () => {
  assert.match(FEED, /applyModalArtifacts\(body, it\);/, "wired in the single-ask modal branch");
  assert.match(FEED, /const sig = arts\.join\("\\n"\);\n  if \(strip && \(strip as any\)\._sig === sig\) return;/, "sig-guarded so a kernel repush doesn't re-fetch every thumb");
  assert.match(FEED, /chip\.onclick = \(ev: Event\) => \{ ev\.stopPropagation\(\); vscodeApi\?\.postMessage\(\{ type: "openFile", path: p, id: it\.sid \}\); \};/, "no-preview fallback still opens the file");
  assert.match(FEED_CSS, /\.fmodal-arts \{ margin-top: 12px;/);
});

test("kernel: a card's artifacts are HOISTED from its whole subtree, then existence-filtered", () => {
  // the user 2026-08-19: a merged umbrella is distilled as a whole, so the ARTIFACTS line lands on
  // the child goal that produced the files while the CARD renders the umbrella — reading only the
  // card's own node stranded every path one level down.
  assert.match(KERNEL, /def _subtree_artifacts\(nodes, children, root\):/);
  assert.match(KERNEL, /for p in \(\(nodes\.get\(nid\) or \{\}\)\.get\("artifacts"\) or \[\]\):\n\s+if p not in acc:/,
               "pre-order union, card's own paths first, no path listed twice");
  assert.match(KERNEL, /if nid in seen:/, "a malformed parent cycle can't spin the feed build");
  assert.match(KERNEL, /"artifacts": _feed_artifacts\(_subtree_artifacts\(nodes, children, nid\), fsid\)/,
               "build_feed ships the hoisted list, not just the card node's own");
  assert.match(KERNEL, /def _feed_artifacts\(paths, sid\):/);
  assert.match(KERNEL, /if os\.path\.isabs\(ap\) and os\.path\.isfile\(ap\) and ap not in out:/,
               "the filesystem is the authority on what a card may show");
  assert.match(KERNEL, /if p == "\/file":/, "the preview bytes endpoint exists");
  assert.match(KERNEL, /def do_HEAD\(self\):/, "HEAD probe for chips that can't self-verify like an <img>");
});

test("judge: written documents count as artifacts, and a re-distill never erases recorded paths", () => {
  // the ARTIFACTS instruction excluded nearly everything a coding agent produces, which is why the
  // surface was rare enough to be cut upstream — a markdown deliverable is an output file, not source.
  assert.match(JUDGE, /written document \(a spec, a summary, a report, a runbook, a set of notes, a plan\)/,
               "documents are named alongside plots and PDFs");
  assert.match(JUDGE, /a written document meant to be read is an output "\n\s+"file, never source code/);
  assert.match(JUDGE, /Still excluded: source code, tests and configs touched along the way/,
               "the bans that keep edited code out of the strip stay");
  // a later distill reads a longer <work> where the file's creation has scrolled away; transcription
  // then finds nothing and `arts or None` used to wipe what an earlier pass had recorded.
  assert.match(JUDGE, /if arts:\n\s+nodes\[top\]\["artifacts"\] = arts\n\s+elif not nodes\[top\]\.get\("artifacts"\):/,
               "keep-what-you-recorded; the existence filter retires moved files instead");
});

test("the lightbox + thumb styles exist in BOTH sheets (each page loads only its own css)", () => {
  for (const css of [FEED_CSS, CHAT_CSS]) {
    assert.match(css, /#romp-lightbox \{ position: fixed; inset: 0; z-index: 1300;/);
    assert.match(css, /\.path-thumb \{ display: inline-flex;/);
    assert.match(css, /\.path-thumb-img \{ display: block; max-width: 220px; max-height: 140px;/);
  }
  assert.match(CHAT_CSS, /\.path-thumbs \{ display: flex; flex-wrap: wrap;/, "the chat strip container");
});
