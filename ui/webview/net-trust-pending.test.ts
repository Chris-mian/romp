// A trust change (and the web popover's Match) confirms on a LATER poll, and both popovers rebuild
// their rows every poll — so a snapshot fetched before the change used to repaint the OLD level after
// it, which read as "didn't hold" and invited a second click (the user 2026-07-27). Both copies now
// hold a per-host pending map that survives re-renders: rows show the CHOSEN level, disabled with an
// accent applying cue, until a snapshot agrees (the confirming event, never a timer); a refused write
// deletes the entry so the next render honestly reverts. Pinned in BOTH copies (web _LANDING_REMOTES_JS
// in kernel.py, VS Code strip.ts) — they must stay in step.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const ROOT = path.resolve(process.cwd(), "..");
const KERNEL = fs.readFileSync(path.join(ROOT, "kernel", "kernel.py"), "utf8");
const STRIP = fs.readFileSync(path.join(ROOT, "ui", "webview", "strip.ts"), "utf8");
const STRIPCSS = fs.readFileSync(path.join(ROOT, "ui", "webview", "strip.css"), "utf8");

test("web popover: pending trust survives re-renders until a snapshot confirms", () => {
  assert.match(KERNEL, /var _pendTrust=\{\},_pendMirror=\{\};/, "per-host pending maps outlive render()");
  // cleared by AGREEMENT with the snapshot, not by the POST returning or any timer
  assert.match(KERNEL, /function pendLvl\(map,host,current\)\{var p=map\[host\];if\(p&&current===p\)\{delete map\[host\];p=null;\}return p;\}/);
  // recorded ON the click (ack now), before the round trip
  assert.match(KERNEL, /_pendTrust\[h\]=s\.value;s\.disabled=true;s\.classList\.add\('rnet-applying'\);/);
  // a refused write deletes the pending entry (honest revert) AND still alerts (fail loudly)
  assert.match(KERNEL, /delete _pendTrust\[h\];alert\('trust change on '/);
  // all three row kinds (attached, previously-attached, via-relay) render the pending level
  assert.match(KERNEL, /var tpd=pendLvl\(_pendTrust,t\.host,t\.trust\|\|'directed'\)/);
  assert.match(KERNEL, /var kpd=pendLvl\(_pendTrust,k\.host,k\.trust\|\|'directed'\)/);
  assert.match(KERNEL, /var vpd=pendLvl\(_pendTrust,v\.host,v\.trust\|\|'directed'\)/);
  // the cue is visible, not just a disabled control
  assert.match(KERNEL, /rnet-pend/, "an 'applying' note renders next to a pending select");
  assert.match(KERNEL, /\.rnet-trust\.rnet-applying\{border-color:var\(--accent\)/, "accent = in-progress chrome");
});

test("web popover: Match waits for the peer's tier gossip, visibly", () => {
  // pending Match keyed to the DESIRED level, confirmed by tiers gossip (theirs === pending)
  assert.match(KERNEL, /var mpd=pendLvl\(_pendMirror,t\.host,theirs\)/);
  assert.match(KERNEL, /data-lvl=/, "the button carries the level it is matching to");
  assert.match(KERNEL, /_pendMirror\[h\]=b\.getAttribute\('data-lvl'\)/);
  assert.match(KERNEL, /rnet-mirror disabled title=/, "the in-flight state renders disabled");
  assert.match(KERNEL, /Matching/, "…labeled Matching");
  assert.match(KERNEL, /waiting for its bus to confirm/, "the pending tooltip says what it waits on");
  // while pending, the row must not scream mismatch at the user who just fixed it
  assert.match(KERNEL, /rnet-back'\+\(mm&&!mpd\?' rnet-mismatch':''\)/);
});

test("VS Code strip: same pending-trust treatment", () => {
  assert.match(STRIP, /const pendingTrust = new Map<string, string>\(\);/);
  assert.match(STRIP, /if \(pend && \(t\.trust \|\| "directed"\) === pend\) \{ pendingTrust\.delete\(t\.host\); pend = undefined; \}/,
    "cleared by agreement with the snapshot, never a timer");
  assert.match(STRIP, /pendingTrust\.set\(t\.host, trust\.value\);/, "recorded on the click");
  assert.match(STRIP, /if \(!\(d && d\.ok\)\) pendingTrust\.delete\(t\.host\)/, "refused write reverts honestly");
  assert.match(STRIP, /sn-applying/, "the select wears the applying cue");
  assert.match(STRIP, /pn\.textContent = "applying…"/, "a visible note, not just a disabled control");
  assert.match(STRIPCSS, /\.sn-trust\.sn-applying \{ border-color: var\(--accent, #9cd2ff\)/);
});
