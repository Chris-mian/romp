// The feed footer's SESSION FILTER (the user 2026-08-08): a menu right of the Group toggle listing
// every session the chat tab strip shows, in ITS order, each in canonical form — identity-colour dot +
// name with any "host:" prefix folded quiet (.host-prefix). Picking one shows only that session's
// cards; the DEFAULT is nothing selected, everything shows. The kernel attaches the tab list to the
// feed payload (name+colour resolved exactly as tab_meta); federation prefixes and concatenates it.
// The federation legs are pure and tested functionally; feed.ts has no jsdom harness → source pins
// (the repo convention).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { prefixInbound, mergeHostFeeds } from "./federation";

const ROOT = path.resolve(process.cwd(), "..");
const FEED = fs.readFileSync(path.join(ROOT, "ui", "webview", "feed.ts"), "utf8");
const KERNEL = fs.readFileSync(path.join(ROOT, "kernel", "kernel.py"), "utf8");

const U = "11111111-2222-3333-4444-555555555555";
const V = "99999999-8888-7777-6666-555555555555";

test("the kernel's feed payload carries the chat tab strip's sessions, tab_meta-shaped", () => {
  assert.ok(KERNEL.includes('"sessions": [{"sid": s["sid"], "name": s.get("name", ""), "color": _name_color(s["sid"])}'));
  assert.ok(KERNEL.includes("for s in _chat_tab_sessions(now, tmux)]"), "the SAME list the tabs render, in ITS order");
});

test("federation prefixes each sessions[] entry's sid AND name, and the merge concatenates local-first", () => {
  const out = prefixInbound("TESTHOST", { type: "feed", sessions: [{ sid: U, name: "api", color: null }] });
  assert.equal(out.sessions[0].sid, "TESTHOST:" + U);
  assert.equal(out.sessions[0].name, "TESTHOST:api");
  const merged = mergeHostFeeds({
    "": { type: "feed", sessions: [{ sid: U, name: "web" }] },
    TESTHOST: { type: "feed", sessions: [{ sid: "TESTHOST:" + V, name: "TESTHOST:api" }] },
  }, ["", "TESTHOST"]);
  assert.deepEqual(merged.sessions.map((s: any) => s.name), ["web", "TESTHOST:api"]);
});

test("the filter defaults to NOTHING selected and only ever narrows the RENDER, never the data", () => {
  assert.ok(FEED.includes("let feedOnlySid: string | null = null;"));
  assert.ok(FEED.includes('sessionStorage.getItem("romp:feedOnly")'),
    "survives this tab's reloads only — a fresh window always starts unfiltered");
  assert.ok(FEED.includes("const shown = feedOnlySid ? asks.filter((a) => a.sid === feedOnlySid) : asks;"));
  assert.ok(FEED.includes("for (const a of shown) {"), "the group-fold loop reads the filtered view");
  assert.ok(FEED.includes("for (const a of shown) { if (grouped.has(a.itemId)) continue;"), "…and the singles loop");
  // a filter aimed at a session the tab strip no longer shows clears itself — the deciding EVENT is
  // the session leaving the tab list, never a timer
  assert.ok(FEED.includes("if (feedOnlySid && !sessionsMeta.some((s) => s.sid === feedOnlySid)) setFeedOnly(null);"));
});

test("the menu sits right of Group, lists sessions in tab order, canonical form, click-safe", () => {
  assert.match(FEED, /ensureGroupToggle\(\)\.style\.display = showCA \? "" : "none";[^\n]*\n\s*ensureSessionFilter\(\)\.style\.display = showCA \? "" : "none";/);
  // tab order: ranked by the kernel's session-order list — the same rank grouped mode sorts by
  assert.ok(FEED.includes("const rows = sessionsMeta.slice().sort((a, b) => (rank.get(a.sid) ?? 1e9) - (rank.get(b.sid) ?? 1e9));"));
  // the menu lives on document.body — outside render()'s reconcile, so a push can't rebuild it mid-press
  assert.ok(FEED.includes("document.body.appendChild(menu);"));
});

test("menu rows write a session the way the tabs do — coloured bold name + the shared status dot", () => {
  // the identity treatment every other surface gives a session (the user 2026-08-08, round two: a
  // colour SWATCH read as a status dot — on this board a dot beside a name means working/awaiting)
  assert.ok(FEED.includes("nm.replaceChildren(...hostNameNodes(s.name, s.sid));"), "host prefix folded quiet");
  assert.ok(FEED.includes("if (s.color) nm.style.color = s.color.bg;"), "name IN the identity colour");
  assert.ok(FEED.includes("for (const s of rows) row(feedOnlySid === s.sid, s.sid, sessMenuName(s), s.name);"));
  assert.ok(FEED.includes("if (dotName) setWorkDot(label, dotFor(dotName));"),
    "the SAME working/awaiting dot the tabs and headers wear — never a colour swatch");
  assert.ok(!FEED.includes("sessDot"), "the swatch helper is gone");
  const CSS = fs.readFileSync(path.join(ROOT, "ui", "webview", "feed.css"), "utf8");
  assert.match(CSS, /\.fsm-name \{ font-weight: 600; \}/, "bold, like the tab titles and session headers");
  assert.ok(!CSS.includes(".fsm-dot"), "no swatch styles either");
  // with a filter on, the button quotes the picked session verbatim, dot included — a narrowed board
  // must never look like the whole one
  assert.ok(FEED.includes('b.replaceChildren(nm, document.createTextNode(" ▴"));'));
  assert.ok(FEED.includes("setWorkDot(nm, dotFor(cur.name));"));
});
