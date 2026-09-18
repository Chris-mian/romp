// The feed as one board definition (plans/card-boards.md, phase one). Two proofs: the DEFINITION equals the literals feed.ts
// and kernel.py carry today (executed over board-def.ts, and held to the sources by regex, so a value that moves on one side
// reads red on the other), and feed.ts reads the definition at the plan's section-4 sites and nowhere else. Then the schema
// check runs over the constant, and over copies with one member changed on purpose, each refused by name.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { FEED_BOARD, FEED_KINDS, FEED_LOCAL_KEY, CHIPS, SORT_FIELDS, KIND_IDS, RESERVED_BOARD_IDS,
         kindOf, columnOf, columnTable, feedColumns, boardCheck, defaultBoard } from "./board-def";
import { FEED_COLUMNS } from "./feed-view-state";

const read = (...p: string[]) => fs.readFileSync(path.resolve(process.cwd(), "..", ...p), "utf8");
const FEED = read("ui", "webview", "feed.ts");
const KERNEL = read("kernel", "kernel.py");
const BOARD_SRC = read("ui", "webview", "board-def.ts");

// today's three header triples, exactly as ensureCols spelt them before the extraction (feed-col-head-case.test.ts pinned
// the literal table; it now pins the definition through columnTable)
const TRIPLES = [["asks", "Working", "working"], ["needsInput", "Blocked", "blocked"], ["completed", "Completed", "completed"]];

test("the feed definition equals today's literals: the columns, their titles and chips, in the build order", () => {
  assert.deepEqual(columnTable(FEED_BOARD).map((t) => [...t]), TRIPLES);
  assert.deepEqual([...feedColumns(FEED_BOARD)], ["asks", "needsInput", "completed"]);
  assert.deepEqual([...feedColumns(FEED_BOARD)], [...FEED_COLUMNS], "the view state's column list is the same order");
  // the stacked and side-by-side CSS defaults feed.ts keeps as literals (pinned by feed-col-fold.test.ts): the board's
  // order and its reverse
  const row = JSON.parse((FEED.match(/const ROW_DEFAULT = (\[[^\]]*\]);/) || [])[1] || "null");
  const stack = JSON.parse((FEED.match(/const STACK_DEFAULT = (\[[^\]]*\]);/) || [])[1] || "null");
  assert.deepEqual(row, [...feedColumns(FEED_BOARD)], "ROW_DEFAULT is the board's order");
  assert.deepEqual(stack, [...feedColumns(FEED_BOARD)].reverse(), "STACK_DEFAULT is the board's order reversed");
  assert.equal(FEED_BOARD.defaultCategory, "working");
});

test("the category mapping: the kernel's raw column values to the renderer's local keys, an unknown value to the default", () => {
  assert.equal(columnOf(FEED_BOARD, "needs_input"), "needsInput");
  assert.equal(columnOf(FEED_BOARD, "completed"), "completed");
  assert.equal(columnOf(FEED_BOARD, "working"), "asks");
  assert.equal(columnOf(FEED_BOARD, "awaiting"), "asks", "a value the kernel never sends files under the default, as the old mapping did");
  assert.deepEqual(FEED_LOCAL_KEY, { working: "asks", needs_input: "needsInput", completed: "completed" });
  assert.deepEqual(FEED_BOARD.categories.map((c) => c.id), ["working", "needs_input", "completed"], "the ids are the kernel's raw values");
});

test("the sort, the grouping and the notification set equal the sources' literals", () => {
  // feed.ts: oldest at the top unless newestFirst (feed-sort.test.ts pins the line); grouped default on
  assert.deepEqual(FEED_BOARD.sort, { key: "t", dir: "asc" });
  assert.match(FEED, /buckets\[k\]\.sort\(\(x, y\) => newestFirst \? y\.t - x\.t : x\.t - y\.t\)/, "asc is x.t - y.t when newestFirst is off");
  assert.equal(FEED_BOARD.groupBy, "session");
  assert.match(FEED, /grouped: s\.grouped !== false/, "grouped mode defaults on");
  // kernel.py: the columns whose entry announces, and the one the badge counts
  const notify = (KERNEL.match(/^_NOTIFY_COLUMNS = \(([^)]*)\)/m) || [])[1] || "";
  assert.deepEqual([...FEED_BOARD.notify], notify.split(",").map((s) => s.trim().replace(/^"|"$/g, "")).filter(Boolean));
  assert.equal(FEED_BOARD.needsYou, "needs_input");
  assert.match(KERNEL, /a\.get\("column"\) == "needs_input"\)/, "_needs_you_count counts needs_input");
  assert.deepEqual([...FEED_BOARD.kinds], [...KIND_IDS]);
  assert.deepEqual([...FEED_BOARD.rules], []); assert.deepEqual([...FEED_BOARD.order], []); assert.deepEqual([...FEED_BOARD.subSorts], []);
});

test("feed.ts reads the definition at the section-4 sites and nowhere else", () => {
  assert.match(FEED, /import \{ FEED_BOARD, columnOf, columnTable, feedColumns, type FeedCategory \} from "\.\/board-def";/);
  assert.match(FEED, /column: FeedCategory;/, "the record's column is typed to the feed board's category ids");
  assert.match(FEED, /return columnOf\(FEED_BOARD, it\.column\);/, "askColumn is the definition's table");
  assert.equal((FEED.match(/for \(const \[key, label, chip\] of columnTable\(FEED_BOARD\)\)/g) || []).length, 2, "ensureCols and the focused section's twin");
  assert.equal((FEED.match(/of feedColumns\(FEED_BOARD\)\)/g) || []).length, 4, "the four column loops (the stack, the focused layout, the order flip, the freeze badges)");
  assert.match(FEED, /const FLY_COLS: readonly \("asks" \| "needsInput" \| "completed"\)\[\] = feedColumns\(FEED_BOARD\);/);
  assert.doesNotMatch(FEED, /\[\["asks", "Working", "working"\]/, "the literal header table is gone from the renderer");
  assert.doesNotMatch(FEED, /for \(const key of \["asks", "needsInput", "completed"\]\)/, "no column loop spells the keys by hand");
  // what stays a literal in feed.ts on purpose (pinned there; asserted equal above): the two CSS default orders, the sort
  // line and the grouped gate. Their consumption is phase five's (sub-sorts) and phase four's (a board with no grouping).
  assert.match(FEED, /const ROW_DEFAULT = \["asks", "needsInput", "completed"\];/);
});

test("the kinds describe the card builder: every labelled button is a literal in feed.ts, every via names a function there", () => {
  const seen = new Set<string>();
  for (const kind of Object.values(FEED_KINDS)) {
    for (const d of [...kind.sections, ...kind.actions, ...kind.menu]) {
      assert.match(FEED, new RegExp("function " + d.via + "\\("), d.id + " points at feed.ts " + d.via);
      if (d.label !== null && !seen.has(d.label)) {
        seen.add(d.label);
        const lit = d.label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        assert.match(FEED, new RegExp('(?:textContent = |label = |label: )"' + lit + '"'), d.id + "'s label is the literal the card wears");
      }
    }
  }
  assert.deepEqual(FEED_KINDS.goal.sections.map((s) => s.id), ["bg", "summary", "subgoals", "stall", "tasks"], "the five one-at-a-time sections, applySections' choices");
  assert.match(FEED, /"bg" \| "summary" \| "subgoals" \| "tasks" \| "stall"/, "the same five ids in the renderer's choice type");
});

test("kindOf discriminates by the flavour, as the renderer does", () => {
  assert.equal(kindOf({ notice: { producer: "cli" } }), "notice");
  assert.equal(kindOf({ blocked: { state: "quarantine" } }), "quarantine");
  assert.equal(kindOf({ blocked: { state: "parkedHandoff" } }), "parked");
  assert.equal(kindOf({ provisional: true }), "placeholder");
  assert.equal(kindOf({ blocked: { state: "apiError" } }), "goal", "an API error is a goal card with a chip, never a kind");
  assert.equal(kindOf({}), "goal");
});

test("the schema check passes the feed's constant and refuses a copy with one member changed, naming it", () => {
  assert.equal(boardCheck(FEED_BOARD, { allowReserved: true }), null);
  assert.match(boardCheck(FEED_BOARD) || "", /code-defined board/, "the door refuses the reserved id");
  assert.deepEqual([...RESERVED_BOARD_IDS], ["feed"]);
  const copy = () => JSON.parse(JSON.stringify(FEED_BOARD));
  const refused = (mut: (b: any) => void, want: RegExp) => { const b = copy(); mut(b); const err = boardCheck(b, { allowReserved: true }); assert.match(err || "(accepted)", want); };
  refused((b) => { b.categories[1].chip = "red"; }, /chip must be one of working, blocked, completed, neutral/);
  refused((b) => { b.categories.push(...Array.from({ length: 6 }, (_, i) => ({ id: "c" + i, title: "C", chip: "neutral" }))); }, /1 to 8/);
  refused((b) => { b.categories[0].id = "Working"; }, /category id must match/);
  refused((b) => { b.categories[2].id = "working"; }, /repeats/);
  refused((b) => { b.defaultCategory = "done"; }, /defaultCategory must name/);
  refused((b) => { b.rules = [{ when: { needsYou: true }, category: "done" }]; }, /rule's category must name/);
  refused((b) => { b.rules = [{ when: { owner: "x" }, category: "working" }]; }, /predicate has an unknown member "owner"/);
  refused((b) => { b.rules = [{ when: {}, category: "working" }]; }, /at least one member/);
  refused((b) => { b.sort = { key: "age", dir: "asc" }; }, /sort\.key must be one of t, session, owner, title/);
  refused((b) => { b.subSorts = Array.from({ length: 7 }, () => ({ key: "t", dir: "asc" })); }, /0 to 6/);
  refused((b) => { b.groupBy = "owner"; }, /groupBy must be/);
  refused((b) => { b.order = ["newestPinned"]; }, /order rules must be from ownerRank/);
  refused((b) => { b.notify = ["done"]; }, /notify names a category the board does not have/);
  refused((b) => { b.needsYou = "done"; }, /needsYou must be one of/);
  refused((b) => { b.kinds = ["card"]; }, /kinds must be from/);
  refused((b) => { b.colour = "blue"; }, /unknown member "colour"/);
  refused((b) => { b.title = ""; }, /title must be 1 to 40/);
  refused((b) => { b.id = "Feed"; }, /id must match/);
  assert.match(boardCheck("feed") || "", /must be a JSON object/);
  assert.deepEqual([...CHIPS], ["working", "blocked", "completed", "neutral"]);
  assert.deepEqual([...SORT_FIELDS], ["t", "session", "owner", "title"]);
});

test("a first-use board takes the plan's defaults and passes the check", () => {
  const b = defaultBoard("notes", "new");
  assert.equal(boardCheck(b), null);
  assert.deepEqual(b, { id: "notes", title: "Notes", categories: [{ id: "new", title: "New", chip: "neutral" }], defaultCategory: "new",
    rules: [], sort: { key: "t", dir: "desc" }, subSorts: [], groupBy: null, order: [], notify: [], needsYou: null, kinds: ["notice"] });
  assert.equal(defaultBoard("scratch").categories[0].id, "notes", "no category named: one called notes");
  assert.match(BOARD_SRC, /^export function boardCheck\(/m, "one validator, the client half");
});
