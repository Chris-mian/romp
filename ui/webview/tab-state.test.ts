// tab-state.ts: the tab strip's ONE state → class rule, shared by the tab and a folded section
// header's member-derived summary pip (tab groups, 2026-09-04). The header once classed every "blocked"
// member red while the tab rendered a transient, auto-retrying API error amber — a folded group showed
// "waiting on you" over a tab that needed nothing (a false interrupt). Executed on the pure module; the
// render.ts call sites are pinned in tab-groups.test.ts. Synthetic statuses only.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { tabStateClass, RING_ORDER, RING_TEST, tabRingId, sectionPip, SECTION_PIP_TITLE, SECTION_PIP_TITLE_MANY, sectionPipMembers, sectionPipTitle } from "./tab-state";

test("executed: tabStateClass — the strip's rule, on-you blocks red, transient API errors amber", () => {
  assert.equal(tabStateClass({ state: "working" }), "tab-working");
  assert.equal(tabStateClass({ state: "blocked" }), "tab-retrying", "a transient API error auto-retries: amber, not red");
  assert.equal(tabStateClass({ state: "blocked", apiTooLong: true }), "tab-blocked");
  assert.equal(tabStateClass({ state: "blocked", apiSpendLimit: true }), "tab-blocked");
  assert.equal(tabStateClass({ state: "blocked", apiModelLimit: true }), "tab-blocked");
  assert.equal(tabStateClass({ state: "blocked", apiAuthErr: true }), "tab-blocked");
  assert.equal(tabStateClass({ state: "blocked", apiRefusal: true }), "tab-blocked");
  assert.equal(tabStateClass({ state: "needsInput" }), "tab-awaiting");
  assert.equal(tabStateClass({ state: "awaiting" }), "tab-awaiting", "the legacy name an older remote kernel sends");
  assert.equal(tabStateClass({ state: "retrying" }), "tab-retrying");
  assert.equal(tabStateClass({ state: "compacting" }), "tab-compacting");
  assert.equal(tabStateClass({ state: "clearing" }), "tab-compacting");
  assert.equal(tabStateClass({ state: "closed" }), "tab-closed");
  assert.equal(tabStateClass({ state: "ready" }), "", "no tab treatment → no class");
  assert.equal(tabStateClass(undefined), "");
});

test("executed: sectionPip — a folded header's pip is red ONLY for a member the tab itself renders red", () => {
  // the finding: a transient auto-retrying API error (state blocked, no on-you flag) turned the
  // header pip red — "blocked or waiting on you" — over an amber tab
  assert.equal(sectionPip([{ state: "ready" }, { state: "blocked" }]), "retrying", "the tab is amber, so is the pip");
  assert.equal(sectionPip([{ state: "ready" }, { state: "blocked", apiTooLong: true }]), "blocked", "on you → red");
  assert.equal(sectionPip([{ state: "working" }, { state: "needsInput" }]), "blocked", "waiting on you outranks working");
  assert.equal(sectionPip([{ state: "working" }, { state: "blocked" }]), "working", "progress outranks a stall that is not on you");
  assert.equal(sectionPip([{ state: "ready" }, { state: "working" }]), "working");
  assert.equal(sectionPip([{ state: "ready" }, undefined, { state: "closed" }]), null, "nothing happening → no pip");
  assert.equal(sectionPip([]), null);
  assert.match(SECTION_PIP_TITLE.blocked, /waiting on you/);
  assert.match(SECTION_PIP_TITLE.retrying, /retrying on its own/);
  assert.match(SECTION_PIP_TITLE.working, /working/);
});

test("executed: the pip's tooltip names the sessions whose own tab wears its color (the user 2026-09-06)", () => {
  const members = [
    { name: "web", status: { state: "working" } },
    { name: "api", status: { state: "needsInput" } },
    { name: "tests", status: { state: "blocked", apiAuthErr: true } },
    { name: "old1", status: { state: "blocked" } },
    undefined,
  ];
  assert.deepEqual(sectionPipMembers("blocked", members), ["api", "tests"], "waiting on you + an on-you API stop; not the auto-retrying one");
  assert.deepEqual(sectionPipMembers("working", members), ["web"]);
  assert.deepEqual(sectionPipMembers("retrying", members), ["old1"]);
  assert.equal(sectionPipTitle("blocked", ["api"]), "a session in this group is blocked or waiting on you: api", "one name: the singular phrase");
  assert.equal(sectionPipTitle("working", []), SECTION_PIP_TITLE.working, "no names → the phrase alone");
  assert.deepEqual(sectionPipMembers("working", [{ name: "  ", status: { state: "working" } }]), ["(unnamed)"]);
});

test("executed: the pip's tooltip counts several sessions — never a singular phrase before a list of names", () => {
  // "a session in this group is blocked or waiting on you: api, tests" read as one session, then two
  assert.equal(sectionPipTitle("blocked", ["api", "tests"]), "2 sessions in this group are blocked or waiting on you: api, tests");
  assert.equal(sectionPipTitle("working", ["web", "api", "tests"]), "3 sessions in this group are working: web, api, tests");
  assert.equal(sectionPipTitle("retrying", ["old1", "old2"]), "2 sessions in this group hit an API error and are retrying on their own: old1, old2");
  for (const kind of ["blocked", "working", "retrying"] as const) {
    assert.equal(sectionPipTitle(kind, ["solo"]), `${SECTION_PIP_TITLE[kind]}: solo`, "one name keeps the singular table");
    assert.equal(sectionPipTitle(kind, ["a", "b"]), `${SECTION_PIP_TITLE_MANY[kind](2)}: a, b`, "two names take the counted table");
    assert.doesNotMatch(SECTION_PIP_TITLE_MANY[kind](2), /\ba session\b| is /, "the counted phrase is plural throughout");
  }
});

// ── THE RINGS (the rings-as-widgets change, 2026-09-14; the ask ring itself from the review of 2026-09-13): a session
// with something waiting on you should grab attention without a click, even while it goes on working in the background.
// The three rings are widgets with a switch each; this is the pure twin of the registry's composition (tab-widgets.ts
// composeTabRing, pinned equal to tabRingId over every status and switch set in tab-widgets.test.ts).
const off = (...ids: string[]) => (id: string) => !ids.includes(id);
test("executed: tabRingId — the yellow ring for the feed's needs-you verdict in every live state, red over yellow over amber, one ring at a time", () => {
  assert.deepEqual(RING_ORDER, ["ring-needs-you", "ring-waiting-on-you", "ring-retrying"], "the precedence: red, yellow, amber");
  // the common case the state rule never sees: a session that asked something and went idle
  assert.equal(tabRingId({ state: "ready", needsYou: true }), "ring-waiting-on-you");
  assert.equal(tabRingId({ state: "idle", needsYou: true }), "ring-waiting-on-you");
  // …and the case the ask is for: it asked and went ON WORKING (or waits on background work) — the ring shows anyway
  assert.equal(tabRingId({ state: "working", needsYou: true }), "ring-waiting-on-you", "working does not hide an ask");
  assert.equal(tabRingId({ state: "awaitingBg", needsYou: true }), "ring-waiting-on-you", "nor does awaiting background work");
  assert.equal(tabRingId({ state: "compacting", needsYou: true }), "ring-waiting-on-you", "nor a context operation in flight");
  // the amber retrying ring gives way to the ask (the ask is on you; the retry is not): the order, not the CSS
  assert.equal(tabRingId({ state: "retrying", needsYou: true }), "ring-waiting-on-you");
  assert.equal(tabRingId({ state: "blocked", needsYou: true }), "ring-waiting-on-you", "a transient API error is the amber ring: the ask outranks it");
  // the red rings already say "needs you now" and outrank it; a dead tab is past tense
  assert.equal(tabRingId({ state: "needsInput", needsYou: true }), "ring-needs-you", "a live prompt: the red ring, not two rings");
  assert.equal(tabRingId({ state: "awaiting", needsYou: true }), "ring-needs-you", "the legacy name of the same live prompt");
  assert.equal(tabRingId({ state: "blocked", apiTooLong: true, needsYou: true }), "ring-needs-you", "an API stop only you can clear: the red ring");
  assert.equal(tabRingId({ state: "blocked", apiRefusal: true, needsYou: true }), "ring-needs-you", "a refusal: red");
  assert.equal(tabRingId({ state: "closed", needsYou: true }), null, "a closed session wears nothing");
  // the red and the amber without a card: the rings the strip had before
  assert.equal(tabRingId({ state: "needsInput" }), "ring-needs-you");
  assert.equal(tabRingId({ state: "blocked", apiSpendLimit: true }), "ring-needs-you");
  assert.equal(tabRingId({ state: "retrying" }), "ring-retrying");
  assert.equal(tabRingId({ state: "blocked" }), "ring-retrying", "a transient API error auto-retries: amber");
  // only TRUE is a verdict: false (no card) and null (no feed build yet) are the same nothing, as is an older kernel's absent field
  assert.equal(tabRingId({ state: "working", needsYou: false }), null);
  assert.equal(tabRingId({ state: "ready", needsYou: null }), null);
  assert.equal(tabRingId({ state: "ready" }), null, "an older remote kernel sends no field");
  assert.equal(tabRingId({ state: "working" }), null);
  assert.equal(tabRingId(undefined), null);
  assert.equal(tabRingId(null), null);
  // the state class is untouched by the field: the ring composes with it on the tab
  assert.equal(tabStateClass({ state: "working", needsYou: true }), "tab-working");
  // the yellow's own test no longer stands down under the red states: the composition's order does
  assert.equal(RING_TEST["ring-waiting-on-you"]({ state: "needsInput", needsYou: true }), true);
  assert.equal(RING_TEST["ring-waiting-on-you"]({ state: "closed", needsYou: true }), false);
  assert.equal(RING_TEST["ring-needs-you"]({ state: "blocked" }), false, "a transient API error is not the red ring's");
  assert.equal(RING_TEST["ring-retrying"]({ state: "blocked", apiAuthErr: true }), false, "…and an on-you stop is not the amber's");
});

test("executed: tabRingId under the switches — a ring switched off hands the tab to the next ring that applies, or to nothing", () => {
  assert.equal(tabRingId({ state: "needsInput", needsYou: true }, off("ring-needs-you")), "ring-waiting-on-you", "red off: a live prompt with a card is yellow, which is true of that tab");
  assert.equal(tabRingId({ state: "needsInput" }, off("ring-needs-you")), null, "red off, no card: a plain tab");
  assert.equal(tabRingId({ state: "working", needsYou: true }, off("ring-waiting-on-you")), null, "yellow off: a working card is nothing");
  assert.equal(tabRingId({ state: "retrying", needsYou: true }, off("ring-waiting-on-you")), "ring-retrying", "yellow off: the amber shows through");
  assert.equal(tabRingId({ state: "retrying" }, off("ring-retrying")), null, "amber off: a retry is nothing");
  assert.equal(tabRingId({ state: "blocked", apiTooLong: true, needsYou: true }, off("ring-needs-you", "ring-waiting-on-you")), null, "an on-you stop is never amber");
  assert.equal(tabRingId({ state: "needsInput", needsYou: true }, off("ring-needs-you", "ring-waiting-on-you", "ring-retrying")), null, "every ring off: a plain strip");
});

test("executed: sectionPip — a hidden member's ask is yellow, between red and gold, so a fold never hides it; under the switches the pip follows the members' tabs", () => {
  assert.equal(sectionPip([{ state: "ready" }, { state: "ready", needsYou: true }]), "ask", "an idle session that asked");
  assert.equal(sectionPip([{ state: "working" }, { state: "working", needsYou: true }]), "ask", "the ask outranks working: it is on you, progress is not");
  assert.equal(sectionPip([{ state: "blocked" }, { state: "ready", needsYou: true }]), "ask", "…and the amber retry");
  assert.equal(sectionPip([{ state: "needsInput" }, { state: "ready", needsYou: true }]), "blocked", "red outranks it: a live prompt");
  assert.equal(sectionPip([{ state: "blocked", apiAuthErr: true }, { state: "working", needsYou: true }]), "blocked", "…or an on-you API stop");
  assert.equal(sectionPip([{ state: "needsInput", needsYou: true }]), "blocked", "one session, both facts: the red ring is the tab's, so the pip's");
  assert.equal(sectionPip([{ state: "closed", needsYou: true }, { state: "ready" }]), null, "a closed member's stale verdict is nothing");
  assert.equal(sectionPip([{ state: "ready", needsYou: false }, { state: "ready", needsYou: null }]), null);
  // the switches: the pip wears a colour only when a member's own tab would
  assert.equal(sectionPip([{ state: "needsInput", needsYou: true }, { state: "ready" }], off("ring-needs-you")), "ask", "the red ring switched off: a hidden member with a prompt and a card shows the fold's pip yellow");
  assert.equal(sectionPip([{ state: "needsInput" }], off("ring-needs-you")), null, "…and with no card, nothing: a fold never shows a colour no unfolded tab would wear");
  assert.equal(sectionPip([{ state: "retrying" }], off("ring-retrying")), null, "the only lit ring switched off: null");
  assert.equal(sectionPip([{ state: "working", needsYou: true }], off("ring-waiting-on-you")), "working", "yellow off: the working dot is the state's, not a ring's, and stays");
  assert.equal(sectionPip([{ state: "working" }], off("ring-needs-you", "ring-waiting-on-you", "ring-retrying")), "working");
  assert.match(SECTION_PIP_TITLE.ask, /something waiting on you/);
  assert.equal(SECTION_PIP_TITLE_MANY.ask(2), "2 sessions in this group have something waiting on you");
  assert.doesNotMatch(SECTION_PIP_TITLE_MANY.ask(2), /\ba session\b| is | has /, "the counted phrase is plural throughout");
  assert.equal(sectionPipTitle("ask", ["api"]), "a session in this group has something waiting on you: api");
  assert.equal(sectionPipTitle("ask", ["api", "web"]), "2 sessions in this group have something waiting on you: api, web");
});

test("executed: the pip's tooltip names the members by the ring their tab wears under the switches — a working session with an ask is named under both kinds", () => {
  const members = [
    { name: "web", status: { state: "working", needsYou: true } },
    { name: "api", status: { state: "ready", needsYou: true } },
    { name: "tests", status: { state: "needsInput", needsYou: true } },
    { name: "docs", status: { state: "working" } },
  ];
  assert.deepEqual(sectionPipMembers("ask", members), ["web", "api"], "the two whose tab wears the yellow ring; not the red one");
  assert.deepEqual(sectionPipMembers("working", members), ["web", "docs"], "the working dot is still theirs");
  assert.deepEqual(sectionPipMembers("blocked", members), ["tests"]);
  assert.deepEqual(sectionPipMembers("ask", members, off("ring-needs-you")), ["web", "api", "tests"], "the red ring switched off: the prompt's tab wears the yellow, so the yellow pip names it");
  assert.deepEqual(sectionPipMembers("blocked", members, off("ring-needs-you")), [], "…and no tab wears the red");
  assert.deepEqual(sectionPipMembers("working", members, off("ring-waiting-on-you")), ["web", "docs"], "working is the state's whatever the switches");
});
