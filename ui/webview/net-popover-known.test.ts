// The network popover lists PREVIOUSLY ATTACHED hosts as persistent rows, and every status/control
// explains itself on hover (the user 2026-07-22: "I shouldn't have to do anything from the command
// line ... all of the information can be learned from hovering over tooltips within the application").
//
// There are TWO copies of this popover — the web shell's (_LANDING_REMOTES_JS, inline in kernel.py)
// and the VS Code strip's (strip.ts). They must stay in step, so both are pinned here.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const ROOT = path.resolve(process.cwd(), "..");
const KERNEL = fs.readFileSync(path.join(ROOT, "kernel", "kernel.py"), "utf8");
const STRIP = fs.readFileSync(path.join(ROOT, "ui", "webview", "strip.ts"), "utf8");

test("web popover renders remembered hosts with re-attach + forget", () => {
  assert.match(KERNEL, /function render\(ts,known\)/, "render takes the known list");
  assert.match(KERNEL, /if\(!back\.hidden\)render\(ts,\(d&&d\.known\)\|\|\[\]\);/, "refresh passes it through");
  assert.match(KERNEL, /Previously attached/);
  assert.match(KERNEL, /data-ra=/, "a Re-attach control keyed by host");
  assert.match(KERNEL, /data-fg=/, "a Forget control keyed by host");
  assert.match(KERNEL, /\/tunnels\/forget/, "Forget hits the kernel route");
  // the empty state must not swallow the remembered rows
  assert.match(KERNEL, /if\(!ts\.length&&!known\.length\)/);
});

test("VS Code strip renders remembered hosts with re-attach + forget", () => {
  assert.match(STRIP, /function renderList\(ts: any\[\], known: any\[\] = \[\]\)/);
  assert.match(STRIP, /renderList\(ts, \(d && d\.known\) \|\| \[\]\)/);
  assert.match(STRIP, /Previously attached/);
  assert.match(STRIP, /"Re-attach"/);
  assert.match(STRIP, /"Forget"/);
  assert.match(STRIP, /\/tunnels\/forget/);
  assert.match(STRIP, /if \(!ts\.length && !known\.length\)/);
});

test("both copies explain every status on hover, with the same wording", () => {
  // one TIP map per copy, covering every status the LBL map can show
  for (const [name, src] of [["kernel", KERNEL], ["strip", STRIP]] as const) {
    for (const status of ["up", "authorizing", "connecting", "no-kernel", "down", "error"]) {
      assert.ok(new RegExp(`['"]?${status}['"]?\\s*:`).test(src), `${name}: TIP covers ${status}`);
    }
    // the wording that makes each status actionable
    assert.ok(src.includes("ssh tunnel is open"), `${name}: 'up' says what connected means`);
    assert.ok(src.includes("no romp kernel is answering"), `${name}: 'no-kernel' says what to do`);
    assert.ok(src.includes("keeps retrying"), `${name}: 'down' says romp retries`);
  }
});

test("both copies explain the destructive/confusing controls on hover", () => {
  for (const [name, src] of [["kernel", KERNEL], ["strip", STRIP]] as const) {
    // Push: the two things that actually surprise people — uncommitted work isn't sent, and it refuses
    assert.ok(src.includes("Uncommitted local edits are NOT sent"), `${name}: Push warns about uncommitted work`);
    // Detach: says the host is REMEMBERED, so it doesn't read as destructive
    assert.ok(src.includes("previously-attached host"), `${name}: Detach says the host is remembered`);
    // Forget: says it doesn't touch the host itself
    assert.ok(src.includes("does not touch the host itself"), `${name}: Forget scopes itself`);
    // Re-attach: says the trust level comes back
    assert.ok(src.includes("restoring its remembered trust level"), `${name}: Re-attach mentions trust restore`);
  }
});
