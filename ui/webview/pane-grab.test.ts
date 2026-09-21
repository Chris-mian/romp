// THE PANE GRAB DETECTOR's pure decision, executed (plans/pane-docking.md section 3, the empty space inside a
// pane): a press counts as a grab only on the page's own empty background (the container itself, never a card,
// a row, a control or an SVG mark under the pointer), by app; the chat has no empty background here (its
// transcript is selection territory); the press must be the primary button with no modifier (Option is the
// shell's own path). Fake targets stand in for elements: matches() and closest() are all the decision reads.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import { emptyPress, forwardable, EMPTY_BY_APP, CONTROL_SEL, GRAB_HOVER_CLASS, KIT_CLASS, install } from "./pane-grab";
import * as PG from "./pane-grab";
// read by name off the module so a build at a base without the export still builds and each test reds on its behaviour (the base run measures it)
const EMPTY_ATTR = (PG as unknown as Record<string, string>).EMPTY_ATTR;
const EMPTY_ATTR_SEL = (PG as unknown as Record<string, string>).EMPTY_ATTR_SEL;

/** A fake element: `self` is what it matches (its own selectors), `inside` what some ancestor (or itself) matches. */
const fake = (self: string[], inside: string[] = []) => ({
  matches: (sel: string) => sel.split(",").map((s) => s.trim()).some((s) => self.includes(s)),
  closest: (sel: string) => (sel.split(",").map((s) => s.trim()).some((s) => self.includes(s) || inside.includes(s)) ? {} : null),
});

test("the feed: its list, columns and card lists are empty background; a card, a chip or a button inside is not", () => {
  assert.equal(emptyPress("feed", fake(["#feed-list"])), true);
  assert.equal(emptyPress("feed", fake([".feed-col-list"])), true, "below the cards");
  assert.equal(emptyPress("feed", fake(["body"])), true);
  assert.equal(emptyPress("feed", fake([".fitem"])), false, "a card (a feed item) is content");
  assert.equal(emptyPress("feed", fake(["span"], [".fitem"])), false, "text inside a card");
  assert.equal(emptyPress("feed", fake(["div"], [".ftask-group"])), false, "a card group's own box");
  assert.equal(emptyPress("feed", fake(["button"])), false);
  assert.equal(emptyPress("feed", fake([".feed-col-list"], ["[role]"])), false, "a list inside a role'd region yields");
  assert.equal(emptyPress("feed", fake(["div"])), false, "an unnamed div is not the background");
});

test("the sessions band: the SVG root and its wrap are empty; every SVG child (a lane, a bar, a mark, a label) is not", () => {
  assert.equal(emptyPress("timeline", fake(["svg"])), true);
  assert.equal(emptyPress("timeline", fake([".romp-tl-wrap"])), true);
  assert.equal(emptyPress("timeline", fake(["#host"])), true);
  assert.equal(emptyPress("timeline", fake(["rect"], ["svg *"])), false, "a bar");
  assert.equal(emptyPress("timeline", fake(["text"], ["svg *"])), false, "a lane label");
  assert.equal(emptyPress("timeline", fake(["button"])), false, "the band's controls");
});

test("the outline and the files pane: the list below the rows and the empty state; a row yields", () => {
  assert.equal(emptyPress("fleet", fake(["#fleet-list"])), true);
  assert.equal(emptyPress("fleet", fake(["#fleet-foot"])), true);
  assert.equal(emptyPress("fleet", fake(["div"], ["[data-sid]"])), false, "a session row");
  assert.equal(emptyPress("fleet", fake(["input"])), false, "the search field");
  assert.equal(emptyPress("files", fake(["#files-empty"])), true);
  assert.equal(emptyPress("files", fake(["body"])), true);
  assert.equal(emptyPress("files", fake([".fileview-body"])), false, "a file's content is selection territory");
});

test("the chat has no empty background here; unknown apps and a null target never grab", () => {
  assert.equal(EMPTY_BY_APP.chat, undefined, "the chat's grab surface stays the strip's empty run");
  assert.equal(emptyPress("chat", fake(["#content"])), false);
  assert.equal(emptyPress("settings", fake(["body"])), false);
  assert.equal(emptyPress("feed", null), false);
  assert.equal(emptyPress("feed", { matches: () => { throw new Error("bad selector"); }, closest: () => null }), false, "a throwing target is no grab");
});

test("forwardable: the primary button with no modifier; Option is the shell's own path", () => {
  const base = { button: 0, altKey: false, ctrlKey: false, metaKey: false, shiftKey: false };
  assert.equal(forwardable(base), true);
  assert.equal(forwardable({ ...base, button: 2 }), false);
  assert.equal(forwardable({ ...base, altKey: true }), false);
  assert.equal(forwardable({ ...base, shiftKey: true }), false, "a shift press is a selection gesture");
  assert.equal(forwardable({ ...base, metaKey: true }), false);
});

test("the names the shell and the pages share", () => {
  assert.equal(KIT_CLASS, "pane-docking");
  assert.equal(GRAB_HOVER_CLASS, "pd-grab-hover");
  assert.ok(CONTROL_SEL.includes("svg *") && CONTROL_SEL.includes(".fitem") && CONTROL_SEL.includes("[data-sid]"));
});

// A registry pane's page declares its own empty background (plans/panes-as-data.md section 4): an element carrying
// data-pane-empty is a grab surface for ANY app, read before the shipped per-app lists; a control inside it still yields;
// and the detector installs for an app it never heard of, so a state-root pane's page gets the hand and the forward.
test("data-pane-empty: a page-declared surface grabs for an unknown app; a control inside yields; the chat stays list-less", () => {
  assert.equal(emptyPress("notes", fake(["[data-pane-empty]", "div"])), true, "the declared element itself, any app");
  assert.equal(EMPTY_ATTR, "data-pane-empty"); assert.equal(EMPTY_ATTR_SEL, "[data-pane-empty]");
  assert.equal(emptyPress("notes", fake(["div"])), false, "an undeclared element in an unknown app: no grab");
  assert.equal(emptyPress("notes", { matches: (sel: string) => sel === "[data-pane-empty]", closest: (sel: string) => (sel === CONTROL_SEL ? {} : null) }), false, "a control inside the declared surface yields");
  assert.equal(emptyPress("feed", fake(["[data-pane-empty]"])), true, "a shipped pane may declare too");
  assert.equal(EMPTY_BY_APP.chat, undefined, "the chat's list stays absent: its grab surface is the strip's empty run");
});

test("install wires a page for any app: a registry pane's document gets the style, the wired flag and the read-only hook", () => {
  const listeners: string[] = [];
  const body = { classList: { contains: () => false, toggle() {}, remove() {} } };
  const appended: Array<{ id: string; textContent: string }> = [];
  const head = { appendChild(n: { id: string; textContent: string }) { appended.push(n); } };
  const doc = { body, head, documentElement: head, getElementById: () => null, createElement: () => ({ id: "", textContent: "" }), addEventListener: (k: string) => { listeners.push(k); } };
  const win = { document: doc, parent: {} } as unknown as Window;
  install(win, "notes");
  const w = win as unknown as { __rompPaneGrabWired?: boolean; __rompPaneGrab?: { app: string; empty: (el: unknown) => boolean } };
  assert.equal(w.__rompPaneGrabWired, true, "wired for an app outside the shipped lists");
  assert.equal(w.__rompPaneGrab && w.__rompPaneGrab.app, "notes");
  assert.deepEqual(listeners.sort(), ["pointerdown", "pointerleave", "pointermove"]);
  assert.equal(w.__rompPaneGrab!.empty(fake(["[data-pane-empty]"]) as unknown as Element), true, "the hook answers by the declared surface");
  assert.equal(appended.length, 1, "the hand's style is appended to the page (the 1920 read: the fake recorded nothing, so a dropped ensureStyle passed)");
  assert.equal(appended[0].id, "pd-grab-css"); assert.match(appended[0].textContent, /cursor:grab/);
});
