// The new-session directory field (the user 2026-07-28): what the status line says about a typed path,
// how the keyboard walks the folder list, and how the "that folder isn't there" dialog reads. EXECUTES
// ./dir-complete; the picker plumbing (the request/reply pacing, the create fork, the host routing) is
// source-pinned against render.ts below.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { dirStatusLine, nextDirActive, createDirPrompt, type DirStatus } from "./dir-complete";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8")
  + fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "federation.ts"), "utf8");
const STYLES = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

const st = (over: Partial<DirStatus>): DirStatus => ({
  value: "~/GitRepos/api", path: "~/GitRepos/api", exists: true, isDir: true, isFile: false,
  canCreate: false, nearest: "~/GitRepos", missing: 0, isDefault: false, ...over,
});

test("an existing folder reads as a plain confirmation", () => {
  const said = dirStatusLine(st({}));
  assert.equal(said.text, "✓ ~/GitRepos/api");
  assert.equal(said.cls, "", "nothing is wrong, so nothing is coloured");
});

test("the untouched default says it is the default", () => {
  assert.match(dirStatusLine(st({ isDefault: true })).text, /\(the default\)$/);
});

test("a missing folder warns and names where it would go", () => {
  const said = dirStatusLine(st({ exists: false, isDir: false, canCreate: true, missing: 2 }));
  assert.equal(said.cls, "warn");
  assert.match(said.text, /no such folder yet/);
  // it NAMES the folder it would make, and how much of the chain (the user 2026-07-29)
  assert.match(said.text, /Starting will create ~\/GitRepos\/api and the 1 folder above it$/);
  const one = dirStatusLine(st({ exists: false, isDir: false, canCreate: true, missing: 1 }));
  assert.match(one.text, /Starting will create ~\/GitRepos\/api$/, "one folder needs no arithmetic");
  const three = dirStatusLine(st({ exists: false, isDir: false, canCreate: true, missing: 3 }));
  assert.match(three.text, /and the 2 folders above it$/, "plural when it is more than one");
});

test("a file where a folder was typed is an error, not an offer", () => {
  const said = dirStatusLine(st({ isDir: false, isFile: true, canCreate: false }));
  assert.equal(said.cls, "bad");
  assert.match(said.text, /not a folder: /);
});

test("an unreachable path says so rather than offering to create it", () => {
  const said = dirStatusLine(st({ exists: false, isDir: false, canCreate: false, nearest: "" }));
  assert.equal(said.cls, "bad");
  assert.match(said.text, /invalid path: /);
});

test("no answer yet says nothing at all", () => {
  assert.deepEqual(dirStatusLine(null), { text: "", cls: "" });
});

test("walking the list passes through 'nothing chosen' at both ends", () => {
  assert.equal(nextDirActive(-1, 1, 3), 0);
  assert.equal(nextDirActive(0, 1, 3), 1);
  assert.equal(nextDirActive(2, 1, 3), -1, "off the bottom hands the field back to typing");
  assert.equal(nextDirActive(-1, -1, 3), 2, "up from nothing takes the last row");
  assert.equal(nextDirActive(0, -1, 3), -1);
  assert.equal(nextDirActive(-1, 1, 0), -1, "an empty list has nothing to choose");
});

test("the create dialog names the path and how much it would make", () => {
  assert.match(createDirPrompt("api", st({ path: "~/w/a/b", missing: 2, nearest: "~/w" }), ""),
    /~\/w\/a\/b doesn't exist \(2 new folders under ~\/w\)/);
  // one folder needs no arithmetic in the sentence
  assert.match(createDirPrompt("api", st({ path: "~/w/a", missing: 1, nearest: "~/w" }), ""),
    /~\/w\/a doesn't exist\. Create it/);
  assert.match(createDirPrompt("api", null, "/typed/path"), /^\/typed\/path doesn't exist/);
});

test("the field asks the kernel that would OWN the session, so a remote host completes its own disk", () => {
  assert.match(RENDER, /dirAskedHost = pickerHost\(\);/);
  assert.match(RENDER, /vscodeApi\.postMessage\(\{ type: "dirComplete", value, reqId: \+\+dirReq, host: dirAskedHost \}\)/);
  assert.match(RENDER, /#picker \.picker-host \.picker-be-opt\.sel/, "the host comes off the picker's own selection");
});

test("pacing is the round trip, not a timer: one request in flight, the newest value queued behind it", () => {
  assert.match(RENDER, /if \(dirInFlight\) \{ dirQueued = value; return; \}/);
  assert.match(RENDER, /dirInFlight = false;\s*\n\s*const stale = m\.reqId !== dirReq \|\| \(typeof m\.host === "string" \? m\.host : ""\) !== pickerHost\(\);/);
  assert.match(RENDER, /if \(dirQueued !== null\) \{ const v = dirQueued; dirQueued = null; askDirComplete\(v\); \}/);
  assert.match(RENDER, /if \(stale\) return;/, "a reply for an older keystroke never renders");
  assert.doesNotMatch(RENDER.slice(RENDER.indexOf("function askDirComplete"), RENDER.indexOf("function dirMenuOpen")),
    /setTimeout/, "no debounce");
});

test("a chosen completion walks INTO the folder; it never starts the session", () => {
  assert.match(RENDER, /input\.value = it\.path \+ "\/";/);
  assert.match(RENDER, /if \(e\.key === "Enter" && dirActive >= 0\) \{[\s\S]*?acceptDir\(dirActive\);/);
  assert.match(RENDER, /if \(dirKey\(e\)\) return;/, "the completer gets the keys before the session list does");
});

test("a missing directory raises the create-or-edit choice, and Create re-sends the SAME create", () => {
  assert.match(RENDER, /else if \(m\.type === "createDirMissing" && m\.name\) onCreateDirMissing\(m\)/);
  assert.match(RENDER, /hideOpeningModal\(\);\s*\/\/ the cue would otherwise spin/);
  assert.match(RENDER, /\{ label: "Create it and start", value: "create" \}, \{ label: "Edit the path", value: "edit" \}/);
  assert.match(RENDER, /if \(v === "create"\) \{ startCreate\(req, true\); return; \}/);
  assert.match(RENDER, /\.\.\.\(mkdir \? \{ mkdir: true \} : \{\}\)/, "mkdir rides the same message");
});

test("Edit reopens the picker with what was typed, cursor in the path", () => {
  const edit = RENDER.slice(RENDER.indexOf('if (v === "edit")'), RENDER.indexOf("function openPicker"));
  assert.match(edit, /search\.value = req\.name/);
  assert.match(edit, /dir\.value = req\.dir; dir\.focus\(\); dir\.select\(\); askDirComplete\(dir\.value\)/);
});

test("switching host re-asks: the folders on screen belong to the host that was selected", () => {
  assert.match(RENDER, /\/\/ the completions on screen belong to the host that just stopped being selected\s*\n\s*closeDirMenu\(\);/);
});

// ── round 2 (the user 2026-07-29) ────────────────────────────────────────────────────────────────
// Three complaints, all about the field acting before it was asked to: the folder list dropped over
// the dialog the moment the picker opened; the prefilled path was never vetted against the SERVER the
// session would run on, so a path that cannot exist there only failed after pressing New; and this
// machine's default was prefilled into a remote's field, where it is meaningless.

test("opening the picker asks about the path but does NOT drop a folder list over the dialog", () => {
  assert.match(RENDER, /if \(!dirItems\.length \|\| document\.activeElement !== input\) \{ menu\.style\.display = "none"; return; \}/);
  assert.match(RENDER, /if \(di && !pick\) askDirComplete\(di\.value\);/, "the status is still fetched on open");
});

test("the field itself goes red for a path that cannot work, amber for one that isn't there yet", () => {
  assert.match(RENDER, /box\.classList\.toggle\("bad", said\.cls === "bad"\)/);
  assert.match(RENDER, /box\.classList\.toggle\("warn", said\.cls === "warn"\)/);
  assert.match(STYLES, /\.picker-dir-input\.bad \{ border-color: #e5484d;/);
  assert.match(STYLES, /\.picker-dir-input\.warn \{ border-color: #e0a030; \}/);
});

test("a path that cannot work refuses the create at the field, not after a round trip", () => {
  assert.match(RENDER, /if \(dirStatus && dirStatus\.value === typed && !dirStatus\.isDir && !dirStatus\.canCreate && typed\)/,
    "only when the kernel's answer is about what is typed RIGHT NOW");
  assert.match(RENDER, /That path is a file, not a folder/);
  assert.match(RENDER, /can't be reached on the selected host/);
  // a missing-but-creatable path is NOT refused: that is the create-it-or-edit-it offer
  assert.doesNotMatch(RENDER, /dirStatus\.canCreate \&\& typed\) \{\s*\n\s*pickerError\("That folder doesn't exist/);
});

test("each host remembers the directory you last started a session in there", () => {
  assert.match(RENDER, /const DIR_BY_HOST_KEY = "romp:dirByHost"/);
  assert.match(RENDER, /rememberDir\(req\.host, req\.dir\);/, "recorded when the create is sent");
  assert.match(RENDER, /all\[host \|\| ""\] = d;/, "local is a host key too, so it keeps its own last path");
});

test("a remote's prefill is what you used THERE, never this machine's default", () => {
  // the gear default is one path on this machine; prefilling it into a Linux box's field is a path
  // that cannot exist there. Blank asks that kernel for its own default instead.
  assert.match(RENDER, /return host \? "" : \(kernelDefaultDir \|\| loadSettings\(\)\.defaultDir \|\| ""\);/);
  assert.match(RENDER, /if \(di\) di\.value = dirPrefill\(""\);/, "the open prefill goes through it");
  assert.match(RENDER, /if \(dirIn\) \{ dirIn\.value = dirPrefill\(h\); askDirComplete\(dirIn\.value\); \}/,
    "switching host swaps the path AND re-vets it against that host");
});

test("a new question drops the old verdict, so no answer ever describes another host's disk", () => {
  // the user 2026-07-29: switching host left the field insisting the path was fine. The verdict is about
  // one machine and one path, so it stops standing the moment a different question goes out — and a host
  // whose kernel is too old to answer leaves the line saying "checking", never a borrowed verdict.
  assert.match(RENDER, /dirStatus = null;\s*\n\s*dirItems = \[\];\s*\n\s*renderDirMenu\(false\);/);
  assert.match(RENDER, /checking on \$\{dirAskedHost\}…/);
  assert.match(RENDER, /if \(out\.type === "dirCompletions"\) out\.host = host;/,
    "federation stamps a remote answer with the machine that gave it");
});
