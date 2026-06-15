// Cross-surface hover wiring (the user 2026-06-12). The chat↔feed↔timeline
// highlight join had asymmetric gaps. These pin the fixes at the SOURCE level —
// the wiring lives in DOM event handlers with no jsdom harness here, so (as the
// timeline-view tests do) we assert the handlers exist and are attached to the
// right element. Behavioural coverage of the nonce contract is in
// kernel/hover-push.test.ts.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const read = (...p: string[]) => fs.readFileSync(path.resolve(process.cwd(), ...p), "utf8");
const RENDER = read("src", "webview", "render.ts");
const FEED = read("src", "webview", "feed.ts");
const SERVER = read("src", "kernel", "server.ts");

// The user 2026-06-15: hovering the message TEXT must NOT light the timeline — only the rail DOT (the
// "timeline" gutter) does. The hover target is the DOT (turn fallback only when a turn has no dot).
test("chat hover is wired on the rail dot, not the whole turn", () => {
  assert.match(RENDER, /wireTurnHover\(turn, railDot/, "call site still passes turn + dot");
  assert.match(RENDER, /function wireTurnHover\(turn: HTMLElement, dot: HTMLElement \| null/);
  assert.match(RENDER, /const hoverTarget = dot \|\| turn/, "the hover target is the dot, falling back to turn");
  assert.match(RENDER, /hoverTarget\.addEventListener\("mouseenter"/, "hover (mouseenter) is on the dot");
  assert.match(RENDER, /hoverTarget\.addEventListener\("mouseleave"/);
});

test("the rail dot keeps the click (open the feed card), separate from turn hover", () => {
  // the click must be on the DOT, not the turn — clicking anywhere in a long work
  // turn shouldn't open the card.
  assert.match(RENDER, /dot\.addEventListener\("click"[\s\S]*?type: "dotOpen"/);
});

// #9a (chat side) — hovering a chat turn reciprocally glows the turn's whole span
// in the chat too (light the work period when you hover the message, and vice
// versa), matching the feed→chat glow so either end of the join looks identical.
test("onDotHover reciprocally glows the chat turn span and clears it on leave", () => {
  assert.match(SERVER, /chatGlow\(\[String\(ev\.id\)\]\)/, "set: glow this turn's span in the chat");
  assert.match(SERVER, /if \(!ev\) \{ pushHover\(null\);[\s\S]*?chatGlow\(null\);/, "clear: drop the glow");
});

// #9b — the feed MODAL title, hovered, lights the originating message in the chat
// (and its timeline glyph). Assignable props (not addEventListener) so a re-render
// overwrites instead of stacking handlers; clears for modals with no chat anchor.
test("the feed modal title hover lights the originating chat message", () => {
  assert.match(FEED, /ttlEl\.onmouseenter = titleHoverId \? \(\) => hoverEmit\(titleHoverId\) : null/);
  assert.match(FEED, /ttlEl\.onmouseleave = titleHoverId \? \(\) => hoverEmit\(null\) : null/);
  assert.match(FEED, /titleHoverId = it\.turnId/);
  assert.match(FEED, /titleHoverId = grp\.turnId/);
});

// #10 — both hover paths push directly to the timeline (not only the modal one),
// so a chat-message hover lights the timeline instantly too.
test("both hover paths route through the direct pushHover", () => {
  assert.match(SERVER, /function pushHover\(ids: string\[\] \| string \| null\)/);
  assert.match(SERVER, /timelinePost\(\{ type: "hover", ids:[^,]+, nonce \}\)/);
  assert.match(SERVER, /function hoverFan[\s\S]*?pushHover\(ids\)/, "feed→ path pushes");
  assert.match(SERVER, /pushHover\(String\(atomId\)\)/, "chat→ path pushes");
});

// #11 — a timeline (or any) jump lands the target at the TOP of the viewport so
// you read DOWN into it, not centered with its start scrolled off.
test("landOn top-aligns the target (block:'start'), never centers", () => {
  const landOn = RENDER.slice(RENDER.indexOf("function landOn("));
  const body = landOn.slice(0, landOn.indexOf("\n}\n"));
  assert.match(body, /scrollIntoView\(\{ block: "start"/, "lands at the top");
  assert.doesNotMatch(body, /block: "center"/, "must not center the landing");
});

// Ask preview — the live picker card reproduces the focused option's side-by-side
// TUI box (the user 2026-06-13). Rendered as a monospace <pre> via textContent
// (NEVER innerHTML: the pane text is untrusted terminal output).
test("the live ask card renders ask.preview as a monospace pre via textContent", () => {
  assert.match(RENDER, /if \(ask\?\.preview\) appendPreview\(host, ask\.preview\)/);
  const fn = RENDER.slice(RENDER.indexOf("function appendPreview("));
  const body = fn.slice(0, fn.indexOf("\n}\n"));
  assert.match(body, /el\("pre", "ask-preview"\)/);
  assert.match(body, /pre\.textContent = preview/);
  assert.doesNotMatch(body, /innerHTML/, "untrusted pane text must never go through innerHTML");
});
