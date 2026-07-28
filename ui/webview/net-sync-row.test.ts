// The remote-kernel row says HOW a build differs and offers the action that can actually succeed
// (the user 2026-07-27): "behind N" offers Push, "ahead N" offers Pull (fetched over THIS machine's
// ssh — the remote has no route back, its own push died with "No route to host"), a checked-in host
// offers neither (no ssh path from here; the tooltip says to sync from its own dashboard), and an
// auto-sync in flight ('pulling' included) suppresses the manual buttons. Pinned in BOTH copies —
// web _LANDING_REMOTES_JS (kernel.py) and the VS Code strip — which must stay in step.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const ROOT = path.resolve(process.cwd(), "..");
const KERNEL = fs.readFileSync(path.join(ROOT, "kernel", "kernel.py"), "utf8");
const STRIP = fs.readFileSync(path.join(ROOT, "ui", "webview", "strip.ts"), "utf8");

test("web popover: Pull rides the attach tunnel, gated to a provable fast-forward", () => {
  assert.match(KERNEL, /data-p=/, "a Pull control keyed by host");
  assert.match(KERNEL, /\/tunnels\/pull/, "wired to the kernel's pull route");
  assert.match(KERNEL, /t\.fastPull&&!apx&&!t\.checkinPeer/, "offered only when ff-provable, idle, ssh-reachable");
  // a strictly-ahead remote replaces Push with Pull — a push there would only be refused
  assert.match(KERNEL, /!t\.checkinPeer&&!t\.fastPull\)\?'<button class=rnet-upd data-u=/);
  // the checked-in case explains itself instead of dead-ending
  assert.match(KERNEL, /No ssh path from this machine \(it checked in over its own tunnel\)/);
  // an auto-pull in flight counts as busy everywhere a push does
  assert.match(KERNEL, /t\.autoPush\.phase==='pulling'/);
});

test("VS Code strip: same row treatment", () => {
  assert.match(STRIP, /ab > 0 \? ` · ahead \$\{ab\} commit/, "ahead/behind wording matches the web copy");
  assert.match(STRIP, /bb > 0 \? ` · behind \$\{bb\} commit/);
  assert.match(STRIP, /" · diverged"/);
  assert.match(STRIP, /act\("\/tunnels\/pull", t\.host, pl, "Pulling…"\)/, "Pull posts the kernel route");
  assert.match(STRIP, /t\.status === "up" && t\.fastPull && !apx && !t\.checkinPeer/);
  assert.match(STRIP, /!t\.checkinPeer && !t\.fastPull/, "Push yields to Pull on a strictly-ahead remote");
  assert.match(STRIP, /No ssh path from this machine \(it checked in over its own tunnel\)/);
  assert.match(STRIP, /t\.autoPush\.phase === "pulling"/);
});
