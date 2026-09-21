// The failed compaction's card carries no retry action (2026-09-21). A compaction that fails on Codex's side ends the
// backend's compaction bracket loudly, as a launch error, and the chat renders every launch error on the API-error card:
// a "retrying soon" meta and two Retry buttons, whose press sent the literal word "retry" into the thread as a turn,
// cleared the card, and compacted nothing. The bracket's end notices (systemError, notLoaded, the app-server's death) now
// carry `noRetry`; build_session lifts it onto the status as `apiNoRetry` (the apiRefusal precedent: the card reads its
// flags from the live session status, never the event); renderApiError then draws no meta and no actions. Scoped to the
// bracket's ends: a failed turn's card keeps its button. The chat renderer has no jsdom harness, so the wiring is pinned
// at the source; the kernel's half is executed in tests/test_codex_compact_route.py. Synthetic values only.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const ROOT = path.resolve(process.cwd(), "..");
const read = (...p: string[]) => fs.readFileSync(path.join(ROOT, ...p), "utf8");
const RENDER = read("ui", "webview", "render.ts");
const KERNEL = read("kernel", "kernel.py");
const BACKEND = read("kernel", "codex_backend.py");
const CONTRACT = read("kernel", "session_backend.py");

test("Status carries apiNoRetry, and renderApiError reads it off the live status: the same card with no countdown meta and no actions, before the retry machinery", () => {
  assert.match(RENDER, /interface Status \{[^\n]*apiNoRetry\?: boolean;/);
  const i = RENDER.indexOf("function renderApiError(");
  assert.ok(i > 0);
  const card = RENDER.slice(i, RENDER.indexOf("\n}\n", i));
  const early = card.indexOf("if (st?.apiNoRetry) {");
  assert.ok(early > 0, "read from the live session status, the apiRefusal precedent");
  assert.match(card.slice(early), /^if \(st\?\.apiNoRetry\) \{\n\s+return notice\(\{ src: "API", glyph: "api", sev: "err", gist, body, open: true, key: "apierr:" \+ \(ev\.uuid \|\| \(activeId \|\| ""\)\), cls: "turn-apierror" \}\);\n\s+\}/,
    "no meta and no acts: the retrying-soon countdown, Retry now and Stop-all are never built for it; the same fold key, so the user's fold on the card holds");
  assert.ok(early < card.indexOf("const acts: HTMLElement[] = [];"), "returned before the actions exist");
  assert.ok(early < card.indexOf('acts.push(noticeAct("Retry now"'), "…and before the Retry the press would have sent as a turn");
  assert.match(card, /return notice\(\{ src: "API", glyph: "api", sev: "err", gist, meta: countdown, acts, body,\n\s+open: true, key: "apierr:" \+ \(ev\.uuid \|\| \(activeId \|\| ""\)\), cls: "turn-apierror" \}\);/,
    "every other launch error and API error keeps the card as it was");
});

test("the kernel lifts the launch error's noRetry onto the status; only the bracket's end notices carry it", () => {
  assert.match(KERNEL, /_launch_no_retry = bool\(_lerr\.get\("noRetry"\)\)/);
  assert.match(KERNEL, /"apiNoRetry": _launch_no_retry,/);
  assert.match(CONTRACT, /`noRetry`/, "the contract names the optional key");
  const ends = BACKEND.match(/"limit": False, "noRetry": True\}/g) || [];
  assert.equal(ends.length, 2, "two writers cover the bracket's three loud ends: the status handler (systemError and notLoaded) and the pump's client-death arm; no other launch-error writer carries it");
  assert.match(BACKEND, /"text": "codex %s rejected: %s" % \(e\.operation, e\),\n\s+"at": time\.time\(\), "limit": False\}/, "a failed turn's notice keeps its Retry");
});
