// A Codex session never receives a slash command as prose (2026-09-19): the kernel refuses it before any backend sees it
// and answers with a warn that names the session (sid) and, for a composer press, the copy (qid). The chat's half: the
// optimistic bubble the press drew ends on that warn (no echo will ever land for it), the words go back into an EMPTY
// composer, and a warn naming a session is never read as a create's verdict, whatever is in flight. The battery compacts on a
// Codex session too since the native compaction (the kernel runs Codex's own): no mark, no declined click, on either surface.
// Pure functions executed; the chat renderer has no jsdom harness, so its wiring is pinned at the source. Synthetic values only.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { refusedRestoreText, newPending } from "./send-pending";

const ROOT = path.resolve(process.cwd(), "..");
const read = (...p: string[]) => fs.readFileSync(path.join(ROOT, ...p), "utf8");
const RENDER = read("ui", "webview", "render.ts");
const TL = read("ui", "romp-timeline-view.js");
const KERNEL = read("kernel", "kernel.py");

test("the words a refused send puts back: the dropped entry's text into an empty box, never over a draft, nothing when no entry was dropped", () => {
  assert.equal(refusedRestoreText(newPending("/clear"), ""), "/clear");
  assert.equal(refusedRestoreText(newPending("/clear"), "a draft"), null, "a draft in progress is never overwritten");
  assert.equal(refusedRestoreText(newPending("/clear"), "   "), "/clear", "whitespace is an empty box");
  assert.equal(refusedRestoreText(undefined, ""), null, "an entry a push already retired restores nothing");
});

test("the warn branch keys on the session first: a sid-bearing warn toasts (and retires the press's bubble only when the frame names it); the provisional arm is the else of that branch", () => {
  const i = RENDER.indexOf('else if (m.type === "warn" && typeof m.text === "string" && m.text) {');
  assert.ok(i > 0, "the chat page handles the frame");
  const arm = RENDER.slice(i, RENDER.indexOf('else if (m.type === "spendCeiling"', i));
  assert.match(arm, /^else if \(m\.type === "warn" && typeof m\.text === "string" && m\.text\) \{\s*\n(?:\s*\/\/[^\n]*\n)*\s*if \(typeof m\.sid === "string" && m\.sid\) \{/,
    "the sid alone opens the session-scoped path: a battery click's or a POST route's refusal carries no qid and must never fall to the create arm");
  assert.match(arm, /if \(typeof m\.qid === "string" && m\.qid\) \{[\s\S]{0,900}dropPending\(list, "", undefined, m\.qid\)/, "the entry is dropped by id alone (the text argument is inert)");
  assert.match(arm, /if \(list\.length\) pendingSent\.set\(m\.sid, list\); else pendingSent\.delete\(m\.sid\);/);
  assert.match(arm, /const s = sessions\.get\(m\.sid\); if \(s\) reconcileOptimistic\(s\);/);
  assert.match(arm, /refusedRestoreText\(dropped, ta\.value\)/);
  assert.match(arm, /ta\.dispatchEvent\(new Event\("input", \{ bubbles: true \}\)\)/, "the cancelResult restore's idiom: the draft listener re-persists it");
  assert.match(arm, /warnToast\(back !== null \? m\.text \+ " It's back in the box\." : m\.text\);/);
  assert.match(arm, /\}\s*\n(?:\s*\/\/[^\n]*\n)*\s*else if \(provisionalId\) failProvisional\(m\.text\); else warnToast\(m\.text\);/,
    "a create's verdict is read only from a warn that names no session");
  const sidAt = arm.indexOf('if (typeof m.sid === "string" && m.sid) {');
  const provAt = arm.indexOf("failProvisional(m.text)");
  assert.ok(sidAt > 0 && provAt > sidAt, "the session branch is tested before the create arm");
  assert.equal(arm.split("failProvisional(").length - 1, 1, "one create arm, after the session branch");
  assert.match(RENDER, /import \{[^}]*\brefusedRestoreText\b[^}]*\} from "\.\/send-pending";/);
  // the chat battery's click pulse ends on the refusal (2026-09-21): the click added ctx-clicked and only a compacting
  // status removed it, so a refused compaction pulsed until the next status change or a tab switch
  assert.match(arm, /if \(m\.sid === activeId\) endCtxBarClick\(document\.getElementById\("ctx-bar"\)\);/,
    "the sid-bearing warn ends the active session's battery pulse (the remover is executed in status-controls.test.ts)");
  assert.match(RENDER, /import \{[^}]*\bendCtxBarClick\b[^}]*\} from "\.\/status-controls";/);
});

test("a compaction refused after a battery click reaches the timeline lane that took it (2026-09-21): the kernel's settingRefused frame ends the lane's click stamp and, marked filed, posts no second bell row", () => {
  // the kernel's half: beside the chat broadcast, the timeline app hears the same refusal on the frame that page renders
  // (its boot drops a warn), marked filed because the kernel's own ring row (_sync_notice) is the bell's record
  const say = KERNEL.slice(KERNEL.indexOf("def _say_compact_refusal("), KERNEL.indexOf("\ndef _codex_compact_command("));
  assert.match(say, /_send_to_app\("chat", dict\(frame, id=str\(sid\)\)\)\n(?:\s*#[^\n]*\n)*\s+_send_to_app\("timeline", \{"type": "settingRefused", "gesture": "command", "sid": str\(sid\), "flag": "",\n\s+"text": why, "filed": True\}\)/,
    "beside the chat broadcast, in the same no-socket branch");
  // the page's half, executed: the same method the boot hands the frame to (setting-refused.test.ts drives it the same way)
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { TimelinePanel } = require(path.join(ROOT, "ui", "romp-timeline-view.js"));
  const posted: any[] = [];
  (globalThis as any).window = { parent: { postMessage: (m: any) => posted.push(m) } };
  try {
    const v: any = Object.create(TimelinePanel.prototype);
    v._compactClicked = { s1: 1, s2: 2 }; v._metaPending = {}; v._pendingFlags = {}; v._dismissed = new Set(); v._dismissedRows = new Map();
    v.data = { sessions: [{ id: "s1" }, { id: "s2" }] }; v._laneMenu = null; v.draws = 0; v.draw = function () { this.draws++; };
    v.settingRefused({ type: "settingRefused", gesture: "command", sid: "s1", flag: "", text: "this session has ended", filed: true });
    assert.deepEqual(v._compactClicked, { s2: 2 }, "the lane's optimistic compacting cue ends on this event, not at its 6 s expiry");
    assert.deepEqual(posted, [], "the kernel filed the bell row itself: the page posts none, so the shell shows one row per refusal");
    assert.equal(v.draws, 1);
    v.settingRefused({ type: "settingRefused", gesture: "command", sid: "s2", flag: "", text: "x" });
    assert.deepEqual(v._compactClicked, {});
    assert.deepEqual(posted, [{ romp: "notify", kind: "refused", text: "x", sid: "s2" }], "the HTTP road's own frame keeps its row: nothing else files one for it");
  } finally { delete (globalThis as any).window; }
});

test("the battery compacts on a Codex session too (native compaction, 2026-09-19): no Codex mark on the chat's bar, the click posts, the timeline's press stamps and posts", () => {
  assert.doesNotMatch(RENDER, /CODEX_NO_COMPACT|markCtxBarFor|inertWhy/, "the inert mark left with the refusal it explained");
  assert.match(RENDER, /^function ctxBar\(\): HTMLElement \{ const bar = buildCtxBar\(compactActiveSession\); bar\.id = "ctx-bar"; return bar; \}/m);
  const c = RENDER.indexOf("function compactActiveSession(bar: HTMLElement): void {");
  assert.ok(c > 0);
  const body = RENDER.slice(c, RENDER.indexOf("\n}\n", c));
  assert.doesNotMatch(body, /backend === "codex"/, "no backend test between the state gate and the post");
  assert.match(body, /vscodeApi\.postMessage\(\{ type: "compactSession", id: activeId \}\);/);
  assert.match(TL, /hit\.style\.cursor = 'pointer';/);
  assert.doesNotMatch(TL, /runs in Codex, which has no \/compact/);
  const press = TL.slice(TL.indexOf("hit.addEventListener('pointerdown'"), TL.indexOf("svg.appendChild(hit);"));
  assert.doesNotMatch(press, /codex/, "the press stamps and posts for every live lane");
  assert.match(press, /this\._compactSession\(s\.name\); this\.draw\(\);/);
});

test("the kernel-served shell's bell explains the refused kind's new tenants: a slash command a session has no such command for, and a clear or compact a Codex session could not run", () => {
  assert.match(KERNEL, /refused:"[^"]*Or a slash command sent to a session that has no such command \(a Codex session has no \/fast\): nothing was sent, and the entry names it\. Or a \/clear or \/compact a Codex session could not run/);
});
