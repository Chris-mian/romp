// The team-internals LENS (the user 2026-08-25, option (iii) of the provenance audit): the DEFAULT
// board shows cards whose evidence chain roots in the user's own asks; kernel-stamped `internal`
// cards fold behind a footer "N team-internal" word-button. Needs-you ALWAYS breaks through (the
// satellite's rule), an unclassifiable card is never stamped (false-quiet is the chosen-against
// failure), and the lens layers INSIDE viewFiltered's slot family so the session filter, search,
// the hover-freeze churn badges, and the incoming tag lens all compose structurally. Source pins,
// the feed-panel idiom; the kernel walk's truth table lives in tests/test_feed_provenance_split.py.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const W = (f: string) => fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", f), "utf8");
const FEED = W("feed.ts");
const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "bin", "romp-kernel"), "utf8");

test("kernel: the stamp is additive, class-only, and only on a CONFIDENT internal verdict", () => {
  assert.match(KERNEL, /\*\*\(\{"internal": True\} if _prov\.internal\(fsid, nid\) else \{\}\)/,
    "stamped unconditionally of column — the view owns visibility, counts stay honest");
  assert.match(KERNEL, /return self\.klass\(sid, nid\) == "internal"/,
    "None (unclassifiable) is never stamped — the card shows");
  assert.match(FEED, /internal\?: boolean \| null;/, "additive on the type — old payloads render as before");
});

test("kernel: the walk is cache-only and refuses cross-host hops", () => {
  assert.match(KERNEL, /ps = _parse_cached\(path\)\n\s+if ps is None:\n\s+return None/,
    "a cold cache is unclassifiable — never a cold parse on the push path");
  assert.match(KERNEL, /and not o\.get\("peerHost"\)/,
    "another kernel's stores are not ours to read; its rows arrive classified and ride the merge");
});

test("the lens layers inside viewFiltered — breakthrough included — so every counter sees it", () => {
  assert.match(FEED, /const base = viewBase\(list\);\n\s+if \(internalLensOn\(\)\) return base;\n\s+return base\.filter\(\(a\) => !a\.internal \|\| a\.column === "needs_input"\);/,
    "needs-you cards show regardless of class — interrupt only when the human is the bottleneck");
  assert.match(FEED, /function internalLensCount\(list: AskItem\[\]\): number \{\n\s+return viewBase\(list\)\.filter\(\(a\) => a\.internal && a\.column !== "needs_input"\)\.length;/,
    "the count is what the lens GOVERNS under the current session/search scoping");
});

test("the footer button wears the mode-toggle vocabulary and persists via romp:settings", () => {
  assert.match(FEED, /b = el\("button", "fdismiss ffollow feed-modetoggle"\);\n\s+b\.id = "feed-internal-lens";/,
    "the session combobox's exact button vocabulary — no new footer species");
  assert.match(FEED, /setViewPref\("teamInternals", !internalLensOn\(\)\)/,
    "the shared settings write + romp:settings re-render event, like every footer view pref");
  assert.match(FEED, /\.teamInternals === true;/, "default OFF: the split is the new default board");
});

test("render wires the honest count, the accent .on state, and hides a zero-card control", () => {
  assert.match(FEED, /lensBtn\.textContent = lensN \+ " team-internal";/);
  assert.match(FEED, /lensBtn\.classList\.toggle\("on", lensOn\);/,
    ".feed-modetoggle.on — the accent language selected footer toggles already wear");
  assert.match(FEED, /lensBtn\.setAttribute\("aria-pressed", lensOn \? "true" : "false"\);/);
  assert.match(FEED, /lensBtn\.style\.display = \(showCA && \(lensN > 0 \|\| lensOn\)\) \? "" : "none";/,
    "a control that governs zero cards is noise — but an ON lens stays reachable to turn off");
});

test("the button is ensure-once (click-safe across re-renders)", () => {
  assert.match(FEED, /let b = document\.getElementById\("feed-internal-lens"\);\n\s+if \(!b\) \{/,
    "the node persists; render() only rewrites its label — a push can never destroy it mid-press");
});
