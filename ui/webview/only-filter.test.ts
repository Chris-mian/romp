// Demo/recording VIEW filter (the user 2026-07-14): `#only=<tag>` on the dashboard URL scopes every pane
// (chat tabs, feed, fleet, timeline) to sessions whose name starts with <tag>, so you get a clean frame for
// screencasts without a separate instance. Runtime-tests the pure helper; source-pins the four wire-ups.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { onlyTag, matchesOnly } from "./only-filter";

const read = (p: string) => fs.readFileSync(path.resolve(process.cwd(), "..", p), "utf8");
const RENDER = read("ui/webview/render.ts");
const FEED = read("ui/webview/feed.ts");
const FLEET = read("ui/webview/fleet.ts");
const TL = read("ui/romp-timeline-view.js");
const ONLY = read("ui/webview/only-filter.ts");

test("matchesOnly: no tag passes everything; otherwise case-insensitive PREFIX", () => {
  assert.equal(matchesOnly("anything", null), true);
  assert.equal(matchesOnly("anything", ""), true);        // '' is falsy → no filter
  assert.equal(matchesOnly("demo-data", "demo"), true);
  assert.equal(matchesOnly("Demo-Data", "demo"), true);   // case-insensitive
  assert.equal(matchesOnly("bug", "demo"), false);
  assert.equal(matchesOnly("", "demo"), false);
  assert.equal(matchesOnly("predemo", "demo"), false);    // prefix, not substring
});

test("onlyTag reads #only= / ?only= from the shell URL (window.top), lowercased", () => {
  const g = global as any;
  const prev = g.window;
  const mk = (hash: string, search = "") => { const w: any = { location: { hash, search } }; w.top = w; g.window = w; };
  try {
    mk("#only=demo"); assert.equal(onlyTag(), "demo");
    mk("#only=Demo-Foo"); assert.equal(onlyTag(), "demo-foo");
    mk("", "?only=xyz"); assert.equal(onlyTag(), "xyz");
    mk("#other=1"); assert.equal(onlyTag(), null);         // unrelated hash → no filter
    mk("#only="); assert.equal(onlyTag(), null);           // empty tag → no filter
    mk(""); assert.equal(onlyTag(), null);
  } finally { g.window = prev; }
});

test("the helper: case-insensitive prefix + reads the shell URL via window.top", () => {
  assert.match(ONLY, /export function onlyTag\(\)/);
  assert.match(ONLY, /window\.top \|\| window/);
  assert.match(ONLY, /\.toLowerCase\(\)\.startsWith\(tag\)/);
});

test("chat tabs filter by the #only tag", () => {
  assert.match(RENDER, /import \{ onlyTag, matchesOnly \} from "\.\/only-filter";/);
  assert.match(RENDER, /const visibleIds = only \? ids\.filter\(\(id\) => matchesOnly\(nameOf\(id\), only\)\) : ids;/);
  assert.match(RENDER, /for \(const id of visibleIds\)/);
});

test("feed cards filter by the #only tag; clear bookkeeping still uses the FULL payload", () => {
  assert.match(FEED, /import \{ onlyTag, matchesOnly \} from "\.\/only-filter";/);
  assert.match(FEED, /const visible = only \? incomingAsks\.filter\(\(a\) => matchesOnly\(a\.name, only\)\) : incomingAsks;/);
  assert.match(FEED, /asks = pendingCleared\.size \? visible\.filter/);
});

test("fleet sessions filter by the #only tag", () => {
  assert.match(FLEET, /import \{ onlyTag, matchesOnly \} from "\.\/only-filter";/);
  assert.match(FLEET, /if \(only && !matchesOnly\(s\.name, only\)\) continue;/);
});

test("the new-session picker seeds the name box with the tag prefix in a filtered view", () => {
  // launching from `#only=demo` prefills `demo-` so a new session stays in view (the user 2026-07-15);
  // only when creating is possible (create mode or pickAllowNew), and the cursor lands after the prefix
  assert.match(RENDER, /const only = \(!pick \|\| pickAllowNew\) \? onlyTag\(\) : null;/);
  assert.match(RENDER, /const seed = only \? only \+ "-" : "";/);
  assert.match(RENDER, /s\.value = seed;/);
  assert.match(RENDER, /if \(seed\) s\.setSelectionRange\(seed\.length, seed\.length\);/);
  assert.match(RENDER, /filterPicker\(seed\);/);
});

test("timeline lanes filter by the #only tag (self-contained helper in the standalone file)", () => {
  assert.match(TL, /function _rompOnlyTag\(\)/);
  assert.match(TL, /function _rompMatchesOnly\(name, tag\)/);
  assert.match(TL, /sessions: data\.sessions\.filter\(\(s\) => _rompMatchesOnly\(s\.name, _only\)\)/);
});
