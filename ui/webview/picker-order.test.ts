// The new-session picker's layout (the user 2026-08-12): CREATE controls first — the name box, then
// directory, backend, billing, host, and the New session button — and the resume list LAST, under a
// heading that names it as the alternative. Typing in the name box re-filters the list, whose height
// changes with every keystroke; with the list mid-dialog, every control below it jumped exactly while
// being reached for — and creating is the common case, reviving the occasional one. Source pins (the
// renderer has no jsdom harness — the repo convention).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("the create controls precede the list, and the list sits last under its heading", () => {
  const seq = [
    "box.appendChild(search);", "box.appendChild(errLine);", "box.appendChild(dirWrap);",
    "box.appendChild(beWrap);", "box.appendChild(auWrap);", "box.appendChild(hostWrap);",
    "box.appendChild(actions);", "box.appendChild(altHead);", "box.appendChild(list);",
  ];
  let at = -1;
  for (const s of seq) {
    const i = RENDER.indexOf(s);
    assert.ok(i > at, `${s} must appear, after its predecessor`);
    at = i;
  }
});

test("the heading presents the list as the alternative to creating, and hides in pick-mode", () => {
  assert.match(RENDER, /altHead\.textContent = "Or reopen an existing session \(last 30 days\)"/);
  // pick-mode: the list IS the dialog (choosing an existing session), so the heading hides with the
  // create rows rather than labeling the only thing on screen an "alternative"
  assert.match(RENDER, /altHeadEl\.style\.display = pick \? "none" : ""/);
  assert.match(CSS, /\.picker-alt-head \{ flex: 0 0 auto; color: var\(--dim\)/);
  assert.match(CSS, /\.picker-alt-head \{[^}]*border-top: 1px solid var\(--box-border\)/,
    "the heading's rule draws the seam above the resume section");
});

test("the heading's '(last 30 days)' states the kernel's REAL reach — the two must move together", () => {
  // the kernel's PICKER_WINDOW is how far back the list actually goes (30 days, the user 2026-07-24);
  // the label quotes it (the user 2026-08-12), so a widened window must rewrite both or fail here
  const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "kernel", "kernel.py"), "utf8");
  assert.match(KERNEL, /PICKER_WINDOW = 30 \* 86400/);
  assert.match(RENDER, /\(last 30 days\)/);
});

test("the in-dialog button says Create session — New session is the door, not the act", () => {
  // you already pressed New session to open this dialog (the user 2026-08-12); the palette command
  // that OPENS the picker keeps the New session name (palette.test.ts pins that one)
  assert.match(RENDER, /newSess\.textContent = "✛ Create session"/);
  assert.doesNotMatch(RENDER, /textContent = "✛ New session"/);
});

test("the dir row lost its border-top — the name box's own border-bottom draws that seam now", () => {
  const dir = CSS.match(/\.picker-dir \{[^}]*\}/)![0];
  assert.doesNotMatch(dir, /border-top/, "search-bottom + dir-top would stack a doubled hairline");
});
