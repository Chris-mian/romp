// T402 (the user 2026-09-12): the chat's "Loading earlier messages" pill stayed on a reader at the tail and could not be dismissed.
// The rule: the pill shows only while an older-history request the reader made is outstanding; never for the page's own
// re-render or its walk to the tail; it hides when the request lands, fails, or its socket dies; a click ends the wait. Pins over
// render.ts and the sheet; the served lab (tests/test_loading_pill_browser.py) drives the three roads.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
const fn = (name: string) => RENDER.slice(RENDER.indexOf("function " + name + "("), RENDER.indexOf("\n}\n", RENDER.indexOf("function " + name + "(")));

test("the pill is for the reader's outstanding older-history ask only: not the virtualiser's own re-render, not the walk to the tail", () => {
  const virt = fn("virtualizeToViewport");
  assert.doesNotMatch(virt, /showLoadingPill\(\)|hideLoadingPill\(\)/, "a re-window renders resident content and asks for nothing (T402)");
  assert.match(virt, /revirtBusy = true;\s*\n\s*\/\/ no pill here \(T402/);
  const newer = fn("requestNewer");
  assert.doesNotMatch(newer, /showLoadingPill\(\)/, "the walk toward the tail is the page's own ask");
  for (const f of ["requestOlder", "fetchOlderForAnchor", "requestAround"]) assert.match(fn(f), /showLoadingPill\(\);/, f + ": the reader's ask into unloaded history shows it");
  for (const f of ["chatHead", "chatWindow", "chatMore"]) assert.match(fn(f), /loadingOlder\.delete\(msg\.id\);\s*\n\s*hideLoadingPill\(\);/, f + ": the reply ends the wait");
});

test("a click ends the wait, drops a landing waiting on it, and frees the next ask; a reopened socket ends every wait", () => {
  const show = fn("showLoadingPill");
  assert.match(show, /loadingPillEl\.textContent = "Loading earlier messages… click to stop waiting";/, "the pill says it can be clicked away");
  assert.match(show, /loadingPillEl\.addEventListener\("click", \(\) => cancelOlderWait\("click"\)\);/);
  const cancel = fn("cancelOlderWait");
  assert.match(cancel, /const sids = why === "wsup" \? \[\.\.\.loadingOlder\] : \(activeId \? \[activeId\] : \[\]\);/, "the click ends the active session's wait; the reopen every session's");
  assert.match(cancel, /loadingOlder\.delete\(sid\); pendingOlderAnchor\.delete\(sid\); pendingOlderKeepY\.delete\(sid\); pendingWindowNav\.delete\(sid\);/, "the in-flight marks go, so the next scroll or click may ask again");
  assert.match(cancel, /landTrail\.push\("cancelled"\);/, "a landing waiting on the ask files its row as cancelled");
  assert.match(cancel, /pendingAnchor = null; pendingAnchorIntent = null; pendingAnchorT = null; pendingAnchorKind = null; anchorPendingOlder = false;/, "…and is dropped: the reply inserts its history and moves nothing");
  assert.match(cancel, /if \(loadingOlder\.size === 0\) hideLoadingPill\(\);/);
  assert.match(RENDER, /window\.addEventListener\("romp:wsup", \(\) => cancelOlderWait\("wsup"\)\);/, "every ask in flight died with the old socket");
  assert.match(CSS, /\.tx-loading-pill \{[^}]*pointer-events: auto; cursor: pointer;/, "the pill takes the click (its anchor stays pointer-events none)");
  assert.match(CSS, /\.tx-loading-pill:hover \{ border-color: var\(--accent\); \}/);
});
