// Executable rule for dragging a tab INTO and OUT OF a tag group (the user 2026-09-23): what a drop does
// to the dragged session's TAGS, given the strip's unions and the zone the provisional tab is sitting in.
// The place a tab is dropped states where the user wants it to appear: a group IS a tag, so a drop in its
// row ADDS that tag and leaves the others alone; the ungrouped row is not a group but the sessions with
// NO tags, so a drop there CLEARS every tag. The asymmetry is the rule, not an oversight. The decision
// executes in node (drag-join.ts is pure); the geometry that produces the zone, and the writes it drives,
// are the browser test's (tests/test_tab_drag_reorder_browser.py).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { resolveTabDrop, writesTag, leaveWords, type DropZone } from "./drag-join";
import { viewTagUnion, type SessionViews } from "./session-views";
import { applyTagEdit } from "./views-writes";

// the notes-api demo world, synthetic throughout: placeholder sids, invented session names
const WEB = "11111111-2222-3333-4444-555555555555";
const API = "22222222-3333-4444-5555-666666666666";
const TESTS = "33333333-4444-5555-6666-777777777777";
const VIEWS: SessionViews = {
  active: "all",
  tags: [{ id: "tag-infra", name: "infra", color: "#4EC9B0", members: [WEB] },
         { id: "tag-qa", name: "qa", color: "#c98cff", members: [WEB, TESTS] }],
};
const U = () => viewTagUnion(VIEWS);
const inGroup = (name: string): DropZone => ({ section: name, trail: false });
const TRAIL: DropZone = { section: null, trail: true };
const HEAD: DropZone = { section: null, trail: false };
/** the blob the ops of one drop leave behind — the writes render.ts posts, applied in order */
const applyDrop = (v: SessionViews, d: ReturnType<typeof resolveTabDrop>, sid: string): SessionViews => {
  let nv = v;
  for (const r of d.tags) if (r.tid) nv = applyTagEdit(nv, { op: d.kind === "join" ? "addMember" : "removeMember", tid: r.tid, sids: [sid] });
  return nv;
};
const holds = (v: SessionViews, sid: string) => viewTagUnion(v).filter((u) => u.members.includes(sid)).map((u) => u.name);

test("a drop in a group's row the session is NOT in joins it: one addMember by the tag's stored id", () => {
  const d = resolveTabDrop(U(), inGroup("infra"), API);
  assert.deepEqual(d, { kind: "join", tags: [{ tag: "infra", tid: "tag-infra", hosts: [] }], why: "" });
  assert.equal(writesTag(d), true);
  assert.deepEqual(applyDrop(VIEWS, d, API).tags?.find((t) => t.id === "tag-infra")?.members, [WEB, API],
    "…and the shared applier puts the member exactly where the kernel's merge will");
});

test("a session ALREADY carrying the tag writes nothing — a drag inside one group is the plain reorder", () => {
  const d = resolveTabDrop(U(), inGroup("infra"), WEB);
  assert.deepEqual(d, { kind: "reorder", tags: [], why: "already" });
  assert.equal(writesTag(d), false, "…so the cue lights nothing and the drop posts nothing");
});

test("a session under several tags gains the new one and KEEPS the rest: it renders under both", () => {
  const d = resolveTabDrop(U(), inGroup("infra"), TESTS);
  assert.equal(d.kind, "join");
  assert.deepEqual(holds(applyDrop(VIEWS, d, TESTS), TESTS), ["infra", "qa"],
    "a group is a tag, so 'appear in infra' is satisfied by adding infra — qa is not the gesture's business");
});

test("a drop on the UNGROUPED row clears EVERY tag: that row is the sessions with none", () => {
  const d = resolveTabDrop(U(), TRAIL, WEB);   // web is in infra and qa
  assert.equal(d.kind, "leave");
  assert.deepEqual(d.tags, [{ tag: "infra", tid: "tag-infra", hosts: [] }, { tag: "qa", tid: "tag-qa", hosts: [] }],
    "one removal route per tag it carries — the ungrouped row is not a group, so nothing partial satisfies it");
  assert.deepEqual(holds(applyDrop(VIEWS, d, WEB), WEB), [], "untagged afterwards, so the strip draws it once, in that row");
});

test("…and a one-tag session's clear is the same rule with one route", () => {
  const d = resolveTabDrop(U(), TRAIL, TESTS);
  assert.deepEqual(d.tags.map((t) => t.tag), ["qa"]);
  assert.deepEqual(holds(applyDrop(VIEWS, d, TESTS), TESTS), []);
});

test("trail to trail is a plain reorder: an untagged session has nothing to clear", () => {
  assert.deepEqual(resolveTabDrop(U(), TRAIL, API), { kind: "reorder", tags: [], why: "untagged" });
});

test("the head of the strip is not the ungrouped row: a drop ahead of the first header clears nothing", () => {
  assert.deepEqual(resolveTabDrop(U(), HEAD, WEB), { kind: "reorder", tags: [], why: "head" },
    "a drop aimed a little left of the first group's chip finds no header either — and must not strip a tag");
});

test("REVERSIBILITY is one tag, not all: dragging back into a group restores THAT tag and only it", () => {
  // the cost of the asymmetry, stated as a test so nobody reads the gesture as a symmetric undo (the user
  // 2026-09-23 accepted it; the pre-release cue naming every tag is the safety, and there is no undo stack)
  const cleared = applyDrop(VIEWS, resolveTabDrop(U(), TRAIL, WEB), WEB);
  assert.deepEqual(holds(cleared, WEB), []);
  const back = resolveTabDrop(viewTagUnion(cleared), inGroup("qa"), WEB);
  assert.equal(back.kind, "join");
  assert.deepEqual(holds(applyDrop(cleared, back, WEB), WEB), ["qa"], "exactly the group dragged into — infra does not come back");
});

test("a section no union holds, and a create still in flight, write nothing", () => {
  assert.equal(resolveTabDrop(U(), inGroup("archived"), API).why, "unknown");
  const pending: SessionViews = { tags: [{ id: "pending-1", name: "draft", members: [] }] };
  assert.deepEqual(resolveTabDrop(viewTagUnion(pending), inGroup("draft"), API), { kind: "reorder", tags: [], why: "pending" },
    "the placeholder id is the one the ack replaces — the kernel would refuse an op addressed by it");
  // …and a clear stands down on a tag whose only holder is such a create: nothing addressable to remove
  const flight: SessionViews = { tags: [{ id: "pending-2", name: "draft", members: [API] }] };
  assert.deepEqual(resolveTabDrop(viewTagUnion(flight), TRAIL, API), { kind: "reorder", tags: [], why: "unknown" });
});

test("a tag whose only home is another kernel rides the editTag wire, by host", () => {
  const remote: SessionViews = { tags: [], remoteTags: [{ id: "TESTHOST:tag-ops", name: "ops", members: [API], host: "TESTHOST" }] };
  assert.deepEqual(resolveTabDrop(viewTagUnion(remote), inGroup("ops"), WEB),
    { kind: "join", tags: [{ tag: "ops", tid: null, hosts: ["TESTHOST"] }], why: "" });
  // a REMOVAL goes to every store holding the (name, member) pair — the Tags flyout's rule
  const both: SessionViews = { tags: [{ id: "tag-ops", name: "ops", members: [API] }],
                               remoteTags: [{ id: "TESTHOST:tag-ops", name: "ops", members: [API], host: "TESTHOST" },
                                            { id: "OTHERHOST:tag-ops", name: "ops", members: [], host: "OTHERHOST" }] };
  assert.deepEqual(resolveTabDrop(viewTagUnion(both), TRAIL, API),
    { kind: "leave", tags: [{ tag: "ops", tid: "tag-ops", hosts: ["TESTHOST"] }], why: "" },
    "the host that does NOT hold the pair is left alone");
});

test("a clear addresses the local tag that actually HOLDS the member, not simply the first of the name", () => {
  const twins: SessionViews = { tags: [{ id: "tag-a", name: "infra", members: [API] },
                                       { id: "tag-b", name: "infra", members: [WEB] }] };
  assert.deepEqual(resolveTabDrop(viewTagUnion(twins), TRAIL, WEB).tags, [{ tag: "infra", tid: "tag-b", hosts: [] }],
    "two local tags may share a name; the op must land on the one whose membership is going");
});

test("the cue names every tag a release would clear — the whole safety on a gesture with no undo", () => {
  assert.deepEqual(leaveWords(resolveTabDrop(U(), TRAIL, WEB)), { leaving: ["infra", "qa"], more: 0 });
  assert.deepEqual(leaveWords(resolveTabDrop(U(), TRAIL, TESTS)), { leaving: ["qa"], more: 0 });
  assert.deepEqual(leaveWords(resolveTabDrop(U(), TRAIL, API)), { leaving: [], more: 0 }, "an untagged tab: that drop is a plain reorder");
  assert.deepEqual(leaveWords(resolveTabDrop(U(), inGroup("infra"), API)), { leaving: [], more: 0 },
    "a join's cue is the ring on the target header; this line has nothing to say");
});

test("…and the cue's chip run is BOUNDED: a session under dozens of tags shows a few and a count", () => {
  const many: SessionViews = { tags: Array.from({ length: 30 }, (_, i) => ({ id: "t" + i, name: "tag" + i, members: [WEB] })) };
  const w = leaveWords(resolveTabDrop(viewTagUnion(many), TRAIL, WEB));
  assert.deepEqual(w.leaving, ["tag0", "tag1", "tag2"], "the many-tags rule holds for a drag cue too");
  assert.equal(w.more, 27);
});

test("render.ts wires the rule into the strip's drag: one decision, the cue and the drop off the same zone", () => {
  const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
  assert.match(RENDER, /import \{ resolveTabDrop, writesTag, leaveWords, type TabDrop, type LeaveWords \} from "\.\/drag-join";/);
  // the zone comes from the PROVISIONAL TAB's place in the strip (dropZoneOf), so the cue and the drop
  // cannot disagree — and sectionHeadOf, the group drag's own reader, is the same walk
  assert.match(RENDER, /resolveTabDrop\(unions, \{ section: zone\.head\?\.dataset\.group \?\? null, trail: zone\.trail \}, id\)/);
  assert.match(RENDER, /function sectionHeadOf\(node: HTMLElement\): HTMLElement \| null \{\s*\n\s*return dropZoneOf\(node\)\.head;/);
  // the dragover paints the cue, the drop posts the tags through the Tags flyout's own writer
  assert.match(RENDER, /paintDragCue\(tabs, dragged, d, head, dragUnions\);/);
  assert.match(RENDER, /if \(postTabDropTag\(d, draggedId\)\) tabDragCommitted = true;/);
  assert.match(RENDER, /const edit: TagEditOp = \{ op: add \? "addMember" : "removeMember", tid: route\.tid, sids: \[id\] \};/,
    "the targeted op the tab menu's Tags flyout posts — never a writer of the drag's own");
  assert.match(RENDER, /if \(ops\.length\) for \(const op of ops\) postTagEdit\(nv, op\);/,
    "a clear's N removals ride ONE optimistic blob, so the strip never shows a half-cleared session");
  // and the cue belongs to the gesture: cleared when the pointer leaves the strip and at dragend
  assert.equal((RENDER.match(/clearDragCue\(\)/g) || []).length, 3, "the definition, the dragleave and the dragend");
});

test("the docs state both halves and the asymmetry between them, in the user's terms", () => {
  const read = (...p: string[]) => fs.readFileSync(path.resolve(process.cwd(), "..", ...p), "utf8");
  const prose = (s: string) => new RegExp(s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "\\s+"));
  const GUIDE = read("docs", "guide.md"), REF = read("docs", "reference.md");
  assert.match(GUIDE, prose("Drag a tab onto a tag group to put that session in it: the tab takes the group's tag "
    + "and lands where you dropped it, keeping its other tags, so a session with several tags shows under each one."));
  assert.match(GUIDE, prose("Drag a tab onto the ungrouped row instead and it loses every tag it had — that row is "
    + "the sessions with no tags — so the label under the tab names them all before you let go. Dragging one back "
    + "into a group restores that tag, not the rest. Dragging a group's header still reorders the groups."));
  assert.match(REF, prose("Drop a tab on the ungrouped row and it loses **every** tag instead: that row is not a "
    + "group but the sessions carrying no tags, so nothing short of clearing them would put it there."));
  assert.match(REF, prose("which of the two gestures you get depends on what you picked up, never on where you dropped it"));
});
