// Per-session BILLING selector (the user 2026-08-08): pick, per session, whether it bills the Claude
// login or the API key the manager's environment carries. Two surfaces, both existence-gated on the
// machine actually offering BOTH choices (one choice is no choice — the control disappears):
//   * the new-session picker's Billing row, armed by the selected host's own sessionList reply
//     (authAvail) and shown only while the backend toggle says SDK;
//   * the statusline auth badge, present only when the kernel emits st.auth (it gates on _auth_both),
//     posting setAuth and wearing switching-dots while the applying reconnect is pending.
// The key is labelled plainly 'API key' — NO key material anywhere: not the key, not even a last-4
// tail (the user 2026-08-08, evening: a tail is still key material; hosts are told apart by name).
// The chat tab's hover tooltip carries the same fact as a Billing row (same day).
// No jsdom harness → source pins (the repo convention).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const ROOT = path.resolve(process.cwd(), "..");
const RENDER = fs.readFileSync(path.join(ROOT, "ui", "webview", "render.ts"), "utf8");
const INTENT = fs.readFileSync(path.join(ROOT, "vscode-extension", "src", "pipe-intent.ts"), "utf8");

test("the picker's Billing row exists only when the host offers both, and only for SDK", () => {
  // hidden until the selected host's OWN sessionList reply proves both choices exist; the backend
  // toggle re-decides it (tmux CLIs live in the tmux server's env, which the kernel doesn't control)
  assert.match(RENDER, /const show = !pickMode && !!\(a && a\.login && a\.key\) && \(beSel\?\.dataset\.be \|\| loadSettings\(\)\.backend\) === "sdk";/);
  assert.match(RENDER, /auWrap\.style\.display = "none";\s*\/\/ hidden until a sessionList reply proves both choices exist/);
  assert.match(RENDER, /beWrap\.addEventListener\("click", \(\) => syncPickerAuth\(\)\);/);
  // a host switch clears the availability — the choices on screen belong to the OLD host
  assert.match(RENDER, /pickerAuthAvail = null;\s*\n\s*syncPickerAuth\(\);/);
  // …and the reply that re-arms it is dropped-if-stale by the same host check the list itself uses
  assert.match(RENDER, /pickerAuthAvail = \(m\.authAvail && typeof m\.authAvail === "object"\) \? m\.authAvail : null;/);
});

test("the pick rides createSession, omitted when the row is hidden", () => {
  // the pick is omitted entirely when the row is hidden — the kernel's own default stands
  assert.match(RENDER, /function pickerAuthChoice\(\): string/);
  assert.match(RENDER, /host: hostSel, \.\.\.\(auth \? \{ auth \} : \{\}\) \}\);/);
  assert.match(RENDER, /interface CreateReq \{ name: string; backend: string; dir: string; host: string; auth\?: string \}/);
  // fresh open forgets last time's pick + availability; the local reply re-arms it
  assert.match(RENDER, /auWrapEl\.querySelectorAll\("\.picker-be-opt"\)\.forEach\(\(x\) => x\.classList\.remove\("sel"\)\);/);
  // the default selection comes from the host's own answer, once, not on every re-sync
  assert.match(RENDER, /const def = a!\.default === "key" \? "key" : "login";/);
});

test("the statusline auth badge is a MetaKind gated on the kernel emitting st.auth", () => {
  assert.match(RENDER, /type MetaKind = "mode" \| "model" \| "effort" \| "fast" \| "auth";/);
  assert.match(RENDER, /st\.auth \? "auth" : ""/);
  assert.match(RENDER, /meta\.appendChild\(metaButton\("auth", prettyAuth\(st\)\)\)/);
  // the badge label is the plain choice, never key material
  assert.match(RENDER, /return \(st\.auth \|\| ""\)\.toLowerCase\(\) === "key" \? "API key" : "Login";/);
  // the pick posts setAuth, and the applying reconnect drives the switching-dots
  assert.match(RENDER, /kind === "auth" \? "setAuth"/);
  assert.match(RENDER, /\(kind === "auth" && !!st\.authPending\)/);
  assert.match(RENDER, /kind === "model" \|\| kind === "effort" \|\| kind === "auth"\);/);
  assert.match(RENDER, /auth\?: string; authPending\?: boolean;/);
});

test("no key material reaches the webview — no tail plumbing survives anywhere", () => {
  // the user 2026-08-08 (evening): even a last-4 tail is more key than any label needs. The kernel
  // stopped shipping authTail/apiTail/tail, and the client has no code left that could render one.
  assert.doesNotMatch(RENDER, /authTail/);
  assert.doesNotMatch(RENDER, /apiTail/);
  assert.doesNotMatch(RENDER, /a!\.tail/);
});

test("the chat tab hover carries a Billing row with the same disappearing rule", () => {
  // whether this tab bills the API key or the login, on the tab tooltip (the user 2026-08-08);
  // st.auth is both-gated by the kernel, so a one-auth machine shows no row at all
  assert.match(RENDER, /if \(s\.status\.auth\) rows\.push\(\["Billing", s\.status\.auth === "key" \? "API key" : "Login"\]\);/);
});

test("setAuth is an intent op — held through a kernel-restart window, never dropped", () => {
  assert.match(INTENT, /"setModel", "setEffort", "setMode", "setFast", "setAuth",/);
});
