// A page reload gives the comment thread back (the user 2026-09-23: the reader's place and view survive a reload,
// their unsent words do not). The decisions are pure and execute here; render.ts has import-time DOM side effects,
// so its wiring — the writer on the reload core's synchronous hook and on the pagehide belt, the load-time take,
// the marks pass's one-shot reopen, the suppressed focus — is pinned to source, the way reload-restore.test.ts
// pins the scroll record's.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { RELOAD_COMMENT_KEY, reloadCommentRecord, takeReloadComment } from "./reload-comment";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const SID = "11111111-2222-4333-8444-000000000901";
const OTHER = "11111111-2222-4333-8444-000000000902";
const TID = "tid-notes-api-1";

test("the record names the tab, the mode, the thread and the box's position", () => {
  assert.deepEqual(reloadCommentRecord(SID, "thread", TID, { x: 420, y: 96 }),
                   { id: SID, mode: "thread", tid: TID, pos: { x: 420, y: 96 } });
  assert.equal(RELOAD_COMMENT_KEY, "romp:reloadComment");
});

test("a CREATE popup records nothing: its content is unsent text the reader does not want kept", () => {
  assert.equal(reloadCommentRecord(SID, "create", "11111111-2222-4333-8444-0000000009aa", { x: 10, y: 10 }), null);
  assert.equal(reloadCommentRecord(SID, "", TID, { x: 10, y: 10 }), null, "no popup on screen → nothing to keep");
});

test("nothing to keep without a tab or a thread", () => {
  assert.equal(reloadCommentRecord(null, "thread", TID, { x: 1, y: 2 }), null);
  assert.equal(reloadCommentRecord("", "thread", TID, { x: 1, y: 2 }), null);
  assert.equal(reloadCommentRecord(SID, "thread", "", { x: 1, y: 2 }), null);
  assert.equal(reloadCommentRecord(SID, "thread", null, { x: 1, y: 2 }), null);
});

test("an unmeasurable position is dropped, not carried: the box reopens at its default geometry", () => {
  assert.deepEqual(reloadCommentRecord(SID, "thread", TID, null)!.pos, null);
  assert.deepEqual(reloadCommentRecord(SID, "thread", TID, { x: NaN, y: 4 })!.pos, null);
  assert.deepEqual(reloadCommentRecord(SID, "thread", TID, { x: 4, y: Infinity })!.pos, null);
  assert.deepEqual(reloadCommentRecord(SID, "thread", TID, { x: 0, y: 0 })!.pos, { x: 0, y: 0 }, "the top-left corner is a real place");
});

test("the record applies to the tab it was saved for; another tab gets nothing", () => {
  const rec = reloadCommentRecord(SID, "thread", TID, { x: 420, y: 96 })!;
  assert.deepEqual(takeReloadComment(rec, SID), rec);
  assert.equal(takeReloadComment(rec, OTHER), null, "a different tab reopens nothing");
  assert.equal(takeReloadComment(rec, null), null);
  assert.equal(takeReloadComment(null, SID), null, "one reload, one restore: the spent record reopens nothing");
});

test("a malformed record gets nothing", () => {
  assert.equal(takeReloadComment("junk", SID), null);
  assert.equal(takeReloadComment({ id: SID }, SID), null, "no mode, no thread → no restore");
  assert.equal(takeReloadComment({ id: SID, mode: "thread" }, SID), null, "no thread id → no restore");
  assert.equal(takeReloadComment({ id: SID, mode: "create", tid: TID }, SID), null, "a create-mode record never reopens");
  assert.equal(takeReloadComment({ id: SID, mode: "thread", tid: 7 }, SID), null);
  assert.deepEqual(takeReloadComment({ id: SID, mode: "thread", tid: TID, pos: { x: "4", y: 2 } }, SID),
                   { id: SID, mode: "thread", tid: TID, pos: null }, "a junk position falls to the default geometry");
});

test("render.ts writes the record on the reload core's hook and on the pagehide belt", () => {
  assert.match(RENDER, /import \{ RELOAD_COMMENT_KEY, reloadCommentRecord, takeReloadComment, type ReloadComment \} from "\.\/reload-comment";/);
  // the core's hook writes all three records; the comment record rides pagehide with the scroll record, because
  // the thread you had open is the same kind of thing as the place you were reading
  assert.match(RENDER, /^function persistForReload\(\): void \{ persistScrollForReload\(\); persistNoticesForReload\(\); persistCommentForReload\(\); \}/m);
  assert.match(RENDER, /\(window as any\)\.__rompPersistForReload = persistForReload;/);
  assert.match(RENDER, /window\.addEventListener\("pagehide", persistCommentForReload\);/);
  const m = RENDER.match(/^function persistCommentForReload\(\): void \{([\s\S]*?)\n\}/m);
  assert.ok(m, "persistCommentForReload");
  const body = m![1];
  assert.match(body, /const pop = document\.getElementById\("cmt-pop"\);/);
  assert.match(body, /reloadCommentRecord\(activeId, pop\?\.dataset\.mode, openCommentKey\?\.tid,\s*\n?\s*pop \? \{ x: pop\.offsetLeft, y: pop\.offsetTop \} : null\)/,
               "the LIVE box's position, so it comes back where they left it");
  assert.match(body, /sessionStorage\.setItem\(RELOAD_COMMENT_KEY, JSON\.stringify\(rec\)\)/,
               "per tab: the persisted webview state is localStorage on the served page, shared by every dashboard tab");
  assert.match(body, /else sessionStorage\.removeItem\(RELOAD_COMMENT_KEY\)/,
               "nothing open clears a record a refused reload left behind, rather than reopening it later");
});

test("render.ts takes the record out of sessionStorage at load (one reload, one restore)", () => {
  assert.match(RENDER, /let pendingReloadComment: ReloadComment \| null = \(\(\) => \{[\s\S]*?const raw = sessionStorage\.getItem\(RELOAD_COMMENT_KEY\);\s*\n\s*if \(raw\) sessionStorage\.removeItem\(RELOAD_COMMENT_KEY\);/);
});

test("the marks pass reopens it once, through openCommentPopover, and only for a live open thread", () => {
  const m = RENDER.match(/^function reopenCommentForReload\(sid: string\): void \{([\s\S]*?)\n\}/m);
  assert.ok(m, "reopenCommentForReload");
  const body = m![1];
  assert.match(body, /const rec = takeReloadComment\(pendingReloadComment, activeId\);/);
  assert.match(body, /if \(!rec \|\| rec\.id !== sid\) return;/);
  // the deciding EVENT is this tab's own comments frame plus its landed transcript: before either, this pass knows
  // nothing about the thread, so it decides nothing and stays armed (no timer, no poll — the next marks pass is an event)
  assert.match(body, /if \(!commentThreads\.has\(sid\)\) return;/);
  assert.match(body, /if \(!v \|\| !v\.shown\) return;/);
  assert.match(body, /pendingReloadComment = null;/);
  assert.match(body, /if \(document\.getElementById\("cmt-pop"\)\) return;/, "whatever the reader opened themselves wins");
  assert.match(body, /if \(!th \|\| th\.status !== "open"\) return;/, "resolved away, promoted or deleted: nothing reopens, no trace");
  assert.match(body, /if \(!v\.el\.querySelector\(`mark\.cmt-hl\[data-tid="\$\{cssEscape\(rec\.tid\)\}"\]`\)\) return;/,
               "the marks must be rendered — a windowed-out passage reopens nothing");
  assert.match(body, /if \(rec\.pos\) commentPopPos = \{ x: rec\.pos\.x, y: rec\.pos\.y \};/);
  assert.match(body, /restoringCommentPop = true;[^\n]*\n\s*try \{ openCommentPopover\(sid, rec\.tid\); \} finally \{ restoringCommentPop = false; \}/,
               "the ordinary opener, with the focus steal suppressed");
  // hung off the marks pass, which runs after every transcript sync AND after every comments frame
  const marks = RENDER.match(/^function applyCommentMarks\(sid: string\): void \{([\s\S]*?)\n\}/m);
  assert.ok(marks, "applyCommentMarks");
  assert.equal((marks![1].match(/reopenCommentForReload\(sid\);/g) || []).length, 2,
               "both exits of the marks pass decide: the no-threads early return and the end");
  // …and the LAND, after its scroll writes: that pass's marks ran before v.shown was set, so a comments frame that
  // arrived ahead of the first chat frame would otherwise wait for a pass an idle session never sends
  const land = RENDER.match(/^function landActive\(content: HTMLElement \| null, v: View\): void \{([\s\S]*?)\n\}/m);
  assert.ok(land, "landActive");
  assert.match(land![1], /v\.shown = true;[\s\S]*\n\s*if \(activeId\) reopenCommentForReload\(activeId\);\s*$/,
               "the last thing the land does, never before the scroll writes");
  assert.equal((RENDER.match(/reopenCommentForReload\(/g) || []).length, 4, "defined once, spent from exactly three events");
});

test("reopening never steals the composer: the restore suppresses the popover's focus", () => {
  assert.match(RENDER, /^let restoringCommentPop = false;/m);
  const pop = RENDER.split("function renderCommentPopover(")[1].split("\nfunction ")[0];
  assert.match(pop, /if \(!restoringCommentPop && \(create \|\| hadFocus \|\| !th \|\| !th\.msgs\.length\)\)/,
               "a reader who starts typing in the composer right after a reload is not hijacked");
});
