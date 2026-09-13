// tab-state.ts: the tab strip's ONE state → class rule, shared by the tab and a folded section
// header's member-derived summary pip (tab groups, 2026-09-04). The header once classed every "blocked"
// member red while the tab rendered a transient, auto-retrying API error amber — a folded group showed
// "waiting on you" over a tab that needed nothing (a false interrupt). Executed on the pure module; the
// render.ts call sites are pinned in tab-groups.test.ts. Synthetic statuses only.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { tabStateClass, tabAskClass, tabClasses, sectionPip, SECTION_PIP_TITLE, SECTION_PIP_TITLE_MANY, sectionPipMembers, sectionPipTitle } from "./tab-state";

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

// ── the ASK RING (the user 2026-09-13): a session with something waiting on you should grab attention without a
// click, even while it goes on working in the background — a second class beside the state class, never a state.
test("executed: tabAskClass — the feed's needs-you verdict rings the tab in every live state the red ring does not own", () => {
  // the common case the state rule never sees: a session that asked something and went idle
  assert.equal(tabAskClass({ state: "ready", needsYou: true }), "tab-ask");
  assert.equal(tabAskClass({ state: "idle", needsYou: true }), "tab-ask");
  // …and the case the ask is for: it asked and went ON WORKING (or waits on background work) — the ring shows anyway
  assert.equal(tabAskClass({ state: "working", needsYou: true }), "tab-ask", "working does not hide an ask");
  assert.equal(tabAskClass({ state: "awaitingBg", needsYou: true }), "tab-ask", "nor does awaiting background work");
  assert.equal(tabAskClass({ state: "compacting", needsYou: true }), "tab-ask", "nor a context operation in flight");
  // the amber retrying ring gives way to the ask (the ask is on you; the retry is not) — styles.css orders the outlines
  assert.equal(tabAskClass({ state: "retrying", needsYou: true }), "tab-ask");
  assert.equal(tabAskClass({ state: "blocked", needsYou: true }), "tab-ask", "a transient API error is the amber ring: the ask outranks it");
  // the red rings already say "needs you now" and outrank it; a dead tab is past tense
  assert.equal(tabAskClass({ state: "needsInput", needsYou: true }), "", "a live prompt: the red ring, not two rings");
  assert.equal(tabAskClass({ state: "awaiting", needsYou: true }), "", "the legacy name of the same live prompt");
  assert.equal(tabAskClass({ state: "blocked", apiTooLong: true, needsYou: true }), "", "an API stop only you can clear: the red ring");
  assert.equal(tabAskClass({ state: "blocked", apiRefusal: true, needsYou: true }), "", "a refusal: red");
  assert.equal(tabAskClass({ state: "closed", needsYou: true }), "", "a closed session wears nothing new");
  // only TRUE is a verdict: false (no card) and null (no feed build yet) are the same nothing, as is an older kernel's absent field
  assert.equal(tabAskClass({ state: "working", needsYou: false }), "");
  assert.equal(tabAskClass({ state: "ready", needsYou: null }), "");
  assert.equal(tabAskClass({ state: "ready" }), "", "an older remote kernel sends no field");
  assert.equal(tabAskClass(undefined), "");
  assert.equal(tabAskClass(null), "");
  // the state class is untouched by the field: the two compose on the tab
  assert.equal(tabStateClass({ state: "working", needsYou: true }), "tab-working");
  assert.deepEqual(tabClasses({ state: "working", needsYou: true }), ["tab-working", "tab-ask"], "gold dot AND yellow ring");
  assert.deepEqual(tabClasses({ state: "ready", needsYou: true }), ["tab-ask"]);
  assert.deepEqual(tabClasses({ state: "needsInput", needsYou: true }), ["tab-awaiting"], "red alone");
  assert.deepEqual(tabClasses({ state: "ready" }), []);
});

test("executed: sectionPip — a hidden member's ask is yellow, between red and gold, so a fold never hides it", () => {
  assert.equal(sectionPip([{ state: "ready" }, { state: "ready", needsYou: true }]), "ask", "an idle session that asked");
  assert.equal(sectionPip([{ state: "working" }, { state: "working", needsYou: true }]), "ask", "the ask outranks working: it is on you, progress is not");
  assert.equal(sectionPip([{ state: "blocked" }, { state: "ready", needsYou: true }]), "ask", "…and the amber retry");
  assert.equal(sectionPip([{ state: "needsInput" }, { state: "ready", needsYou: true }]), "blocked", "red outranks it: a live prompt");
  assert.equal(sectionPip([{ state: "blocked", apiAuthErr: true }, { state: "working", needsYou: true }]), "blocked", "…or an on-you API stop");
  assert.equal(sectionPip([{ state: "needsInput", needsYou: true }]), "blocked", "one session, both facts: the red ring is the tab's, so the pip's");
  assert.equal(sectionPip([{ state: "closed", needsYou: true }, { state: "ready" }]), null, "a closed member's stale verdict is nothing");
  assert.equal(sectionPip([{ state: "ready", needsYou: false }, { state: "ready", needsYou: null }]), null);
  assert.match(SECTION_PIP_TITLE.ask, /something waiting on you/);
  assert.equal(SECTION_PIP_TITLE_MANY.ask(2), "2 sessions in this group have something waiting on you");
  assert.doesNotMatch(SECTION_PIP_TITLE_MANY.ask(2), /\ba session\b| is | has /, "the counted phrase is plural throughout");
  assert.equal(sectionPipTitle("ask", ["api"]), "a session in this group has something waiting on you: api");
  assert.equal(sectionPipTitle("ask", ["api", "web"]), "2 sessions in this group have something waiting on you: api, web");
});

test("executed: the pip's tooltip names the members by EVERY class their tab wears — a working session with an ask is named under both kinds", () => {
  const members = [
    { name: "web", status: { state: "working", needsYou: true } },
    { name: "api", status: { state: "ready", needsYou: true } },
    { name: "tests", status: { state: "needsInput", needsYou: true } },
    { name: "docs", status: { state: "working" } },
  ];
  assert.deepEqual(sectionPipMembers("ask", members), ["web", "api"], "the two whose tab wears the yellow ring; not the red one");
  assert.deepEqual(sectionPipMembers("working", members), ["web", "docs"], "the working dot is still theirs");
  assert.deepEqual(sectionPipMembers("blocked", members), ["tests"]);
});
