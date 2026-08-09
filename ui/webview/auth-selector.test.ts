// Per-session BILLING (the user 2026-08-08, reshaped 2026-08-09): pick, per session, whether it bills
// the Claude login or the API key the manager's environment carries — and SEE the fact everywhere even
// when there is nothing to pick.
//   * the new-session picker's Billing row is ALWAYS there for an SDK session: segmented buttons when
//     the selected host's own sessionList reply (authAvail) says both choices are real, and the same
//     spot writes the single choice out as plain text when only one is (a fact, not a control);
//   * the statusline auth badge is the SWITCHING control, so it keeps the stricter gate: it exists
//     only when the machine offers both (st.authBoth), posting setAuth and wearing switching-dots
//     while the applying reconnect is pending;
//   * the chat tab's hover carries the fact as a Billing row whenever the backend reports it
//     (st.auth rides ungated now), naming WHICH login account (st.authAcct) beside 'Login'.
// The key is labelled plainly 'API key' — NO key material anywhere: not the key, not even a last-4
// tail (the user 2026-08-08, evening: a tail is still key material; hosts are told apart by name).
// No jsdom harness → source pins (the repo convention).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const ROOT = path.resolve(process.cwd(), "..");
const RENDER = fs.readFileSync(path.join(ROOT, "ui", "webview", "render.ts"), "utf8");
const INTENT = fs.readFileSync(path.join(ROOT, "vscode-extension", "src", "pipe-intent.ts"), "utf8");

test("the picker's Billing row shows for SDK whenever availability is known", () => {
  // one known choice is enough to SHOW the row (the user 2026-08-09) — the both-test only decides
  // buttons vs written-out text; the backend toggle still re-decides the row (tmux CLIs live in the
  // tmux server's env, which the kernel doesn't control)
  assert.match(RENDER, /const show = !pickMode && !!\(a && \(a\.login \|\| a\.key\)\) && \(beSel\?\.dataset\.be \|\| loadSettings\(\)\.backend\) === "sdk";/);
  assert.match(RENDER, /const both = !!\(a!\.login && a!\.key\);/);
  assert.match(RENDER, /auWrap\.style\.display = "none";\s*\/\/ hidden until a sessionList reply carries authAvail/);
  assert.match(RENDER, /beWrap\.addEventListener\("click", \(\) => syncPickerAuth\(\)\);/);
  // a host switch clears the availability — the choices on screen belong to the OLD host
  assert.match(RENDER, /pickerAuthAvail = null;\s*\n\s*syncPickerAuth\(\);/);
  // …and the reply that re-arms it is dropped-if-stale by the same host check the list itself uses
  assert.match(RENDER, /pickerAuthAvail = \(m\.authAvail && typeof m\.authAvail === "object"\) \? m\.authAvail : null;/);
});

test("one real choice renders WRITTEN OUT in the buttons' place, naming the login account", () => {
  // the buttons hide, the fixed span shows the single applying choice as plain text (the user
  // 2026-08-09: informative, never a one-option selector) — Login named by its account when known
  assert.match(RENDER, /wrap\.querySelectorAll\("\.picker-be-opt"\)\.forEach\(\(x\) => \(\(x as HTMLElement\)\.style\.display = both \? "" : "none"\)\);/);
  assert.match(RENDER, /fixed\.style\.display = both \? "none" : "";/);
  assert.match(RENDER, /fixed\.textContent = both \? "" : \(a!\.key \? "API key" : \(a!\.acct \? `Login \(\$\{a!\.acct\}\)` : "Login"\)\);/);
  assert.match(RENDER, /const auFixed = el\("span", "picker-auth-fixed"\);/);
  // in button mode, the Login button's hover names WHICH account
  assert.match(RENDER, /if \(loginBtn && a!\.acct\) loginBtn\.title = `Bill this session to the machine's Claude login \(\$\{a!\.acct\}\)\.`;/);
});

test("the pick rides createSession, omitted when the row is hidden or written-out", () => {
  assert.match(RENDER, /function pickerAuthChoice\(\): string/);
  assert.match(RENDER, /host: hostSel, \.\.\.\(auth \? \{ auth \} : \{\}\) \}\);/);
  assert.match(RENDER, /interface CreateReq \{ name: string; backend: string; dir: string; host: string; auth\?: string \}/);
  // text mode sends nothing — the kernel default IS the single choice, and a stale .sel from a
  // previously-selected both-offering host must not ride along
  assert.match(RENDER, /if \(!sel \|\| sel\.style\.display === "none"\) return "";/);
  // fresh open forgets last time's pick + availability; the local reply re-arms it
  assert.match(RENDER, /auWrapEl\.querySelectorAll\("\.picker-be-opt"\)\.forEach\(\(x\) => x\.classList\.remove\("sel"\)\);/);
  // the default selection comes from the host's own answer, once, not on every re-sync
  assert.match(RENDER, /const def = a!\.default === "key" \? "key" : "login";/);
});

test("the statusline auth badge — the switching CONTROL — still gates on both", () => {
  assert.match(RENDER, /type MetaKind = "mode" \| "model" \| "effort" \| "fast" \| "auth";/);
  // st.auth is always reported now; the CONTROL keys on st.authBoth so a one-auth machine
  // shows no dead selector (the display rows carry the fact instead)
  assert.match(RENDER, /\(st\.auth && st\.authBoth\) \? "auth" : ""/);
  assert.match(RENDER, /if \(st\.auth && st\.authBoth\) meta\.appendChild\(metaButton\("auth", prettyAuth\(st\)\)\);/);
  // the badge label is the plain choice, never key material
  assert.match(RENDER, /return \(st\.auth \|\| ""\)\.toLowerCase\(\) === "key" \? "API key" : "Login";/);
  // the pick posts setAuth, and the applying reconnect drives the switching-dots
  assert.match(RENDER, /kind === "auth" \? "setAuth"/);
  assert.match(RENDER, /\(kind === "auth" && !!st\.authPending\)/);
  assert.match(RENDER, /kind === "model" \|\| kind === "effort" \|\| kind === "auth"\);/);
  assert.match(RENDER, /auth\?: string; authPending\?: boolean; authBoth\?: boolean; authAcct\?: string;/);
});

test("no key material reaches the webview — no tail plumbing survives anywhere", () => {
  // the user 2026-08-08 (evening): even a last-4 tail is more key than any label needs. The kernel
  // stopped shipping authTail/apiTail/tail, and the client has no code left that could render one.
  assert.doesNotMatch(RENDER, /authTail/);
  assert.doesNotMatch(RENDER, /apiTail/);
  assert.doesNotMatch(RENDER, /a!\.tail/);
});

test("the chat tab hover says Billing whenever the backend reports it, naming the login", () => {
  // ungated on machine shape (the user 2026-08-09: one-auth machines included; only a tmux session,
  // whose CLI env romp does not control, reports nothing) — and 'Login (account)' when known
  assert.match(RENDER, /if \(s\.status\.auth\) rows\.push\(\["Billing", s\.status\.auth === "key" \? "API key"\s*\n\s*: \(s\.status\.authAcct \? `Login \(\$\{s\.status\.authAcct\}\)` : "Login"\)\]\);/);
});

test("setAuth is an intent op — held through a kernel-restart window, never dropped", () => {
  assert.match(INTENT, /"setModel", "setEffort", "setMode", "setFast", "setAuth",/);
});
