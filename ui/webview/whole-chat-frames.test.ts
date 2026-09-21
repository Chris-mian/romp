// Whole chat frames (2026-09-15), pinned at the source like the other webview tests (the gear has no
// jsdom harness). The night stage one b landed, every session with a saved assembly document began to
// render from the document's cut for a protocol-2 page, the region above the cut left to the page's
// history wire; a page that cannot fill that region shows the last two turns and nothing scrolls. The
// switch is the reversible lever: a per-install kernel-side checkbox in the gear's Chat tab, beside
// Thinking summaries, read live by the kernel's floor decision at every push (no restart), gesture-stamped
// like every kernel-side setting the gear posts, filled from /version, named in the stale-gesture toast,
// and deliberately NOT in federation's KERNEL_SETTING set (the floor is this kernel's build decision).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const ROOT = path.resolve(process.cwd(), "..");
const read = (...p: string[]) => fs.readFileSync(path.join(ROOT, ...p), "utf8");
const GEAR = read("ui", "webview", "gear.js");
const FED = read("ui", "webview", "federation.ts");
const KERNEL = read("bin", "romp-kernel");

test("the gear has an Always load whole chats checkbox in its own Chat history section of the Chat tab, gesture-stamped, filled from /version", () => {
  assert.ok(GEAR.includes("id=rs-wholechat"), "the checkbox exists in the gear markup");
  const at = GEAR.indexOf("id=rs-wholechat");
  assert.ok(GEAR.indexOf("id=rs-thinksum") < at, "…after Thinking summaries");
  const sec = GEAR.lastIndexOf("<div class='rs-sec'>", at);
  assert.ok(GEAR.slice(sec, at).includes(">Chat history</div>"), "…under its own Chat history section header, not Thinking's (the 1704 read, low 4)");
  assert.ok(GEAR.indexOf("data-pane=chat") > 0 && GEAR.indexOf("data-pane=feed") > 0, "both panes exist (indexOf's -1 would pass the order check)");
  assert.ok(GEAR.indexOf("data-pane=chat") < at && at < GEAR.indexOf("data-pane=feed"), "…in the Chat tab");
  const row = GEAR.slice(at, GEAR.indexOf("</label>", at) + 8);
  assert.match(row, /<b>Always load whole chats<\/b>/, "the user's words, not the wire's (low 5)");
  assert.ok(/Load every chat from its first message, instead of the most recent part with the rest loading as you scroll; slower on long chats\./.test(row),
    "the sub-copy in the user's words");
  assert.equal((row.match(/<span/g) || []).length, (row.match(/<\/span>/g) || []).length, "every span the row opens it closes (low 3)");
  assert.ok(GEAR.includes("post({ type: 'setWholeChatFrames', enabled: wcf.checked, gt: gclock.stamp('whole-chat-frames') })"),
    "the click posts the kernel's designed message with the gesture stamp minted in the literal");
  assert.ok(GEAR.includes("wcf.checked = !!v.wholeChatFrames"),
    "the box always shows the kernel's persisted answer, never a page default");
  assert.match(GEAR, /STALE_LABELS = \{[\s\S]*?'whole-chat-frames': 'Always load whole chats'/,
    "a stood-down gesture toasts under the row's own name");
  assert.match(GEAR, /STALE_TYPE = \{[\s\S]*?'whole-chat-frames': 'setWholeChatFrames'/,
    "the toast's Apply anyway may re-issue this one setting");
});

test("Whole chat frames is per-install: not a KERNEL_SETTING, so it never propagates", () => {
  const setSrc = FED.match(/const KERNEL_SETTING = new Set\(\[([\s\S]*?)\]\)/);
  assert.ok(setSrc, "federation.ts's KERNEL_SETTING set located");
  assert.ok(!setSrc![1].includes("setWholeChatFrames"), "the set must not carry it: this kernel keeps its own floor");
  assert.ok(!FED.includes("setWholeChatFrames"), "…and no other federation path names it either");
  assert.ok(!KERNEL.includes('"wholeChatFrames", "whole-chat-frames", _set_whole_chat_frames'),
    "…nor the mesh-adopted settings table on the kernel side");
});

test("the kernel reads the switch live in its floor decision and serves it on /version", () => {
  const at = KERNEL.indexOf("def _chat_floor0_of(chat_clients, now=None):");
  assert.ok(at > 0, "the floor decision exists");
  const body = KERNEL.slice(at, at + 3200);
  assert.ok(body.includes("if _whole_chat_frames_on():"), "the switch is read at every decision, before the client protocols");
  assert.ok(KERNEL.includes('"wholeChatFrames": _whole_chat_frames_on(),'), "/version carries it for the gear's fill");
  assert.ok(KERNEL.includes('msg.get("type") == "setWholeChatFrames"'), "the WS op exists");
  assert.ok(KERNEL.includes("def _seed_whole_chat_frames():") && KERNEL.includes('os.environ.get("ROMP_CHAT_FLOOR0") != "1"'),
    "the boot-time seed exists as a function main() calls once the module is loaded (the 1704 read, low 1)");
});
