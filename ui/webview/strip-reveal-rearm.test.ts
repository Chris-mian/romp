// A REVEAL RE-ARMS THE IDLE PREFETCH, WHATEVER CAUSED THE REPAINT (PR 1671 round four; the user 2026-09-14: hidden tabs
// are not built until shown, and shown ones are). Rounds two and three re-armed the prefetch at renderTabs's callers one by
// one and missed three: a views or lens change arriving on the kernel's tabOrder frame (captureViews, then applyTabOrder's
// bare renderTabs), the phone/desktop media flip (which empties the plan's folded set) and a rename crossing a standing
// #only= filter. The reveal is a STATE change, so renderTabs now detects it where the shown set is computed (visibleIds
// less the plan's folded ids) and schedules the prebuild when any tab went hidden to shown. Executed here: the detector's
// own lines, extracted from render.ts and run over the real predicates (lensVisible, matchesOnly, planStrip) with a counted
// schedulePrebuild; the pure roads (the predicates and the plan alone) are the controls. Synthetic ids and tags only.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import * as TG from "./tab-groups";
import { planStrip, parseTabGroups, setSectionCollapsed, type StripPlan } from "./tab-groups";
import { viewTagUnion, type TagUnion } from "./session-views";
import { lensVisible, type TagLens } from "./tag-lens";
import { matchesOnly } from "./only-filter";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const PHONE_LAYOUT_MEDIA = "(pointer:coarse) and (max-width:1024px)";

// the notes-api demo world: api holds a1 and a2, web holds w1; a3 is untagged
const UNIONS: TagUnion[] = viewTagUnion({ tags: [
  { id: "g1", name: "api", color: "#4EC9B0", members: ["a1", "a2"] },
  { id: "g2", name: "web", color: "#DD42FF", members: ["w1"] },
] });
const IDS = ["w1", "a1", "a2", "a3"];
const flat = (visible: string[]): StripPlan => planStrip(visible, UNIONS, { ...parseTabGroups(null), on: false }, null, false, null);

type Detector = (visibleIds: string[], plan: StripPlan, prev: Set<string> | null, schedule: () => void) => Set<string>;
/** The detector as renderTabs runs it, from the shown set to the memory the next paint reads. Both anchors and the
 *  pure half must exist: at the round-three head none does, so every executed road below reads red there. */
function detector(): Detector {
  const revealed = (TG as Record<string, unknown>).revealedTabs;
  assert.equal(typeof revealed, "function", "tab-groups.ts exports revealedTabs, the pure half of the detector");
  const head = "const shownNow = visibleIds.filter((id) => !plan.folded.has(id));";
  const tail = "lastShownTabIds = new Set(shownNow);";
  const a = RENDER.indexOf(head), b = RENDER.indexOf(tail, a);
  assert.ok(a > 0 && b > a, "renderTabs carries the reveal detector: the shown set, the revealedTabs check, the memory");
  const js = RENDER.slice(a, b + tail.length);
  const fn = new Function("visibleIds", "plan", "lastShownTabIds", "revealedTabs", "schedulePrebuild", js + "\nreturn lastShownTabIds;");
  return (visibleIds, plan, prev, schedule) => fn(visibleIds, plan, prev, revealed, schedule) as Set<string>;
}
/** One paint of the strip for `visible` under `plan`, against the last paint's memory: the arms it fired and the new memory. */
function paint(det: Detector, visible: string[], plan: StripPlan, prev: Set<string> | null): { armed: number; shown: Set<string> } {
  let armed = 0;
  const shown = det(visible, plan, prev, () => { armed++; });
  return { armed, shown };
}

test("executed: the pure half, revealedTabs, names the ids shown now that the last paint did not show; the first paint counts every shown tab", () => {
  const revealed = (TG as Record<string, unknown>).revealedTabs as (p: ReadonlySet<string> | null, s: readonly string[]) => string[];
  assert.equal(typeof revealed, "function", "exported by tab-groups.ts");
  assert.deepEqual(revealed(null, ["a1", "a2"]), ["a1", "a2"], "the first paint: no memory, every shown tab is a reveal (arms once)");
  assert.deepEqual(revealed(new Set(["a1"]), ["a1", "a2"]), ["a2"], "one went hidden to shown");
  assert.deepEqual(revealed(new Set(["a1", "a2"]), ["a1"]), [], "a tab hidden is not a reveal");
  assert.deepEqual(revealed(new Set(["a1", "a2"]), ["a2", "a1"]), [], "a reorder is not a reveal");
  assert.deepEqual(revealed(new Set(), []), [], "nothing shown, nothing revealed");
});

test("executed: a peer's LENS change arriving on the kernel's tabOrder frame reveals two tabs and the repaint re-arms the prefetch once (round three, medium 1)", () => {
  // the chat predicate as render.ts derives it: chatVisible is lensVisible over the chat surface's lens, and stripShows
  // filters the strip's ids by it (tabInView), so a peer's lens change reaches renderTabs as a different visibleIds
  const before: TagLens = { all: false, none: false, tags: ["web"] }, after: TagLens = { all: false, none: false, tags: ["web", "api"] };
  const visibleUnder = (lens: TagLens) => IDS.filter((id) => lensVisible(lens, UNIONS, id));
  assert.deepEqual(visibleUnder(before), ["w1"], "control: the web lens shows w1 alone");
  assert.deepEqual(visibleUnder(after), ["w1", "a1", "a2"], "control: the wider lens shows the api tabs too (a3, untagged, stays out)");
  const det = detector();
  const first = paint(det, visibleUnder(before), flat(visibleUnder(before)), null);
  assert.equal(first.armed, 1, "the first paint arms once (no memory yet; it coalesces with the skeleton frame's own arm)");
  const same = paint(det, visibleUnder(before), flat(visibleUnder(before)), first.shown);
  assert.equal(same.armed, 0, "a repaint that reveals nothing schedules nothing");
  const wider = paint(det, visibleUnder(after), flat(visibleUnder(after)), same.shown);
  assert.equal(wider.armed, 1, "the frame's repaint reveals a1 and a2: one arm (the idle pass asks one skeleton per callback)");
  assert.deepEqual([...wider.shown], ["w1", "a1", "a2"], "the memory is the new shown set");
  const narrower = paint(det, visibleUnder(before), flat(visibleUnder(before)), wider.shown);
  assert.equal(narrower.armed, 0, "the lens narrowing again hides two tabs: not a reveal, no arm");
  // the path: the frame adopts the blob, then applyTabOrder repaints bare, and renderTabs is where the detector runs
  assert.match(RENDER, /captureViews\(m\.views \|\| null\);\s*\n\s*applyTabOrder\(m\.order, m\.tabs,/, "the tabOrder branch: captureViews, then applyTabOrder");
  const ato = RENDER.slice(RENDER.indexOf("\nfunction applyTabOrder("), RENDER.indexOf("\nfunction syncTabKeysWithStrip("));
  assert.match(ato, /\n  renderTabs\(\);\s*\n\s*syncTabKeysWithStrip\(\);\s*\n\}/, "applyTabOrder ends in the bare repaint that carries the reveal");
});

test("executed: the phone/desktop media flip repaints bare, and since the phone folds like the desktop (2026-09-23) it reveals nothing and arms nothing (round three, medium 2)", () => {
  // the listener, extracted and run with stubs: one bare repaint (under rounds two and three it would have needed to re-arm itself)
  const line = RENDER.split("\n").find((l) => l.includes('matchMedia(PHONE_LAYOUT_MEDIA).addEventListener("change"'));
  assert.ok(line, "the media-flip listener exists");
  let repaints = 0;
  const box: { h: (() => void) | null } = { h: null };
  const mql = { addEventListener(t: string, f: () => void) { assert.equal(t, "change"); box.h = f; } };
  new Function("window", "PHONE_LAYOUT_MEDIA", "renderTabs", line)({ matchMedia: () => mql }, PHONE_LAYOUT_MEDIA, () => { repaints++; });
  assert.ok(box.h, "the handler is installed on the media query list");
  box.h!(); assert.equal(repaints, 1, "the flip repaints the strip, bare");
  // the same flip over one store state: the api section folded on the desktop AND on the phone (until 2026-09-23 the phone
  // folded nothing, and this flip revealed the folded tabs; the reveal detector still runs inside that bare repaint)
  const st = setSectionCollapsed({ ...parseTabGroups(null), on: true }, "api", true);
  const visible = ["w1", "a1", "a2", "a3"];
  const desktop = planStrip(visible, UNIONS, st, "w1", false, null), phone = planStrip(visible, UNIONS, st, "w1", true, null);
  assert.deepEqual([...desktop.folded].sort(), ["a1", "a2"], "control: the desktop plan folds the api tabs away");
  assert.deepEqual([...phone.folded].sort(), ["a1", "a2"], "…and the phone plan folds the same ones");
  const det = detector();
  const onDesktop = paint(det, visible, desktop, new Set(["w1", "a3"]));
  assert.equal(onDesktop.armed, 0, "the desktop paint over the same shown set arms nothing");
  const onPhone = paint(det, visible, phone, onDesktop.shown);
  assert.equal(onPhone.armed, 0, "the flip to the phone reveals nothing: no arm");
  assert.deepEqual([...onPhone.shown].sort(), ["a3", "w1"], "the same tabs shown");
  // …while a fold the phone's own picker opens IS a reveal, and the repaint that carries it arms
  const opened = planStrip(visible, UNIONS, setSectionCollapsed(st, "api", false), "w1", true, null);
  assert.equal(paint(det, visible, opened, onPhone.shown).armed, 1, "the picker's heading opens api: a1 and a2 revealed, one arm");
});

test("executed: a rename crossing a standing #only= filter reveals the tab through the renamed frame's bare repaint (round three, low 1)", () => {
  // stripShows's name half: matchesOnly over the session's name under the filter
  const names = new Map([["w1", "web-1"], ["a1", "api-1"], ["a2", "api-2"], ["a3", "notes"]]);
  const visibleUnder = (only: string) => IDS.filter((id) => matchesOnly(names.get(id), only));
  assert.deepEqual(visibleUnder("api"), ["a1", "a2"], "control: the api filter shows the api-named tabs");
  const det = detector();
  const first = paint(det, visibleUnder("api"), flat(visibleUnder("api")), new Set(["a1", "a2"]));
  assert.equal(first.armed, 0, "a repaint under the same filter and names arms nothing");
  names.set("w1", "api-web");   // the renamed frame: the session's name crosses the filter
  assert.deepEqual(visibleUnder("api"), ["w1", "a1", "a2"], "control: the renamed tab now matches");
  const renamed = paint(det, visibleUnder("api"), flat(visibleUnder("api")), first.shown);
  assert.equal(renamed.armed, 1, "the rename's repaint reveals w1: one arm");
  assert.match(RENDER, /if \(s && s\.name !== m\.name\) \{ s\.name = m\.name; renderTabs\(\);/, "the renamed frame repaints bare, and that repaint carries the reveal");
});

test("executed: a section opened here or from a sibling document reveals through the same detector, and a fold does not arm (rounds two and three's roads, one mechanism)", () => {
  const open = { ...parseTabGroups(null), on: true }, folded = setSectionCollapsed(open, "api", true);
  const visible = ["w1", "a1", "a2", "a3"];
  const det = detector();
  const shownOpen = paint(det, visible, planStrip(visible, UNIONS, open, "w1", false, null), null);
  assert.equal(shownOpen.armed, 1, "the first paint arms once");
  const afterFold = paint(det, visible, planStrip(visible, UNIONS, folded, "w1", false, null), shownOpen.shown);
  assert.equal(afterFold.armed, 0, "folding the section hides a1 and a2: no arm");
  assert.deepEqual([...afterFold.shown], ["w1", "a3"], "the memory drops the folded ids");
  const afterOpen = paint(det, visible, planStrip(visible, UNIONS, open, "w1", false, null), afterFold.shown);
  assert.equal(afterOpen.armed, 1, "opening it again reveals them: one arm, whichever document wrote the store");
  // the two deliveries, the column holds and the filter repaint bare now: the detector is theirs too
  assert.match(RENDER, /^window\.addEventListener\(TABGROUPS_EVENT, \(\) => renderTabs\(\)\);$/m);
  assert.match(RENDER, /^window\.addEventListener\("storage", \(e\) => \{ if \(e\.key === TABGROUPS_KEY\) renderTabs\(\); \}\);$/m);
  assert.match(RENDER, /^window\.addEventListener\("storage", \(e\) => \{ if \(e\.key === "romp-chat-cols"\) renderTabs\(\); \}\);$/m);
  assert.match(RENDER, /^const onOnlyHashChange = \(\): void => renderTabs\(\);/m);
});
