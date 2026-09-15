// The Billing flyout on a one-auth box: the choices this box can bill are listed, and those only (the user
// 2026-09-14: list what is set up, grey nothing; from 2026-09-08 to then both were always listed, the missing
// side greyed with its reason), a box with nothing to bill shows one inert line naming why, and a pick that
// fell to the other side says so in the sub-line. render.ts has no jsdom harness, so these are source pins, the
// same idiom as auth-selector.test.ts; the kernel/backend halves are pinned in tests/test_session_auth.py.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const ROOT = path.resolve(process.cwd(), "..");
const RENDER = fs.readFileSync(path.join(ROOT, "ui", "webview", "render.ts"), "utf8");
const STYLES = fs.readFileSync(path.join(ROOT, "ui", "webview", "styles.css"), "utf8");
const KERNEL = fs.readFileSync(path.join(ROOT, "kernel", "kernel.py"), "utf8");

test("the Billing submenu renders on availability, not only when both sides exist", () => {
  assert.match(RENDER, /if \(st && st\.auth && \(st\.authAvail \|\| st\.authBoth\)\) \{/);
  assert.match(RENDER, /const avail: AuthAvail = st\.authAvail \|\| \{ login: true, key: true \};/);
});

test("the options this box can bill are listed, and those only; nothing to bill is one inert line naming why", () => {
  // each choice still carries the reason it cannot apply here: the list filters on it (and the sub-line and the log speak it)
  assert.match(RENDER, /value: "login", why: avail\.login \? "" : \(avail\.loginWhy \|\| "no Claude login signed in on this machine"\)/);
  assert.match(RENDER, /value: "key", why: avail\.key \? "" : \(avail\.keyWhy \|\| "no apiKeyHelper configured"\)/);
  assert.match(RENDER, /const all = billingChoices\(st, avail\);\s*\n\s*const choices = all\.filter\(\(c\) => !c\.why\);/);
  assert.match(RENDER, /el\("div", "ctx-item" \+ \(cur \? " current" : ""\)\)/);   // T346: cur = authChoiceCurrent (by WHICH login); no disabled class since 2026-09-14
  assert.match(RENDER, /const none = el\("div", "ctx-item ctx-item-none"\);\s*\n\s*none\.textContent = all\.map\(\(c\) => c\.why\)\.filter\(Boolean\)\.join\("; "\);/);
  const a = RENDER.indexOf("    const openBillingFly = (): HTMLElement | null => {");
  const BILL = RENDER.slice(a, RENDER.indexOf('    wireFlyout(menu, item, ".ctx-sub-billing"', a));
  assert.doesNotMatch(BILL, /aria-disabled|" disabled"|opt\.title = c\.why/, "no greyed row in the flyout");
  assert.match(STYLES, /\.ctx-sub \.ctx-item\.ctx-item-none \{ cursor: default; \}/);
  assert.match(STYLES, /\.ctx-sub \.ctx-item\.ctx-item-none:hover \{ background: transparent; color: inherit; \}/);
});

test("a pick that fell to the other side is said in the sub-line, from the kernel's word on the fall", () => {
  assert.match(RENDER, /st\.authPickUnavailable === st\.auth\s*\n(?:\s*\/\/[^\n]*\n)*\s*\? `⚠ \$\{wordOf\(st\.auth\)\} unavailable`/);
  // the fall itself is the kernel's authPickFell (the launch's own decision), read by BOTH surfaces; an older
  // kernel without the field is inferred the way the sub-line always did (the other side exists)
  assert.match(RENDER, /authPickUnavailable\?: string; authPickFell\?: string;/);
  assert.match(RENDER, /function authFellTo\(st: Status\): string \{\s*\n\s*if \(st\.authPickFell !== undefined\) return st\.authPickFell \|\| "";/);
  assert.match(RENDER, /\+ \(authFellTo\(st\) \? `, billing \$\{wordOf\(authFellTo\(st\)\)\}` : ""\)/);
  assert.match(RENDER, /\+ \(authFellTo\(s\.status\) \? ` — this session bills \$\{authFellTo\(s\.status\) === "key" \? "the API key" : "the login"\}`/);
  assert.match(RENDER, /: " — nothing to fall to, so the launch went out as picked"\)/);
});

test("the kernel's status carries authAvail with reasons, and authBoth only for older clients", () => {
  assert.match(KERNEL, /"authAvail": _auth_avail_status\(\),/);
  assert.match(KERNEL, /def _auth_avail_status\(\):/);
  assert.match(KERNEL, /out\["loginWhy"\] = jd\._cred\.WHY_MANAGED_HELPER if managed else jd\._cred\.WHY_NO_LOGIN/);
  assert.match(KERNEL, /out\["keyWhy"\] = jd\._cred\.WHY_NO_HELPER/);
  // the default falls to the side that exists, in BOTH directions
  assert.match(KERNEL, /elif default == "login" and not login_ok and key:\s*\n\s*default = "key"/);
});
