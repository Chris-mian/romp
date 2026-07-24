// API-retry visibility in the chat (the user 2026-07-08): a session stalled on an api_retry backoff (the CLI
// retrying a rate-limited / overloaded request) used to be visible ONLY as the amber tab border, with nothing
// in the chat ("the border says retrying but the chat shows no sign"). Now a transient {kind:"retrying"}
// element — the loader dots + an AMBER "API retrying…" line with the live attempt count — renders in the flow
// (a sibling of compacting/reconnecting), and once output resumes a persistent {kind:"retried"} "Recovered
// after N retries" note is left where it recovered. Source pins.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("the transient retrying + persistent retried events each have their own ChatEvent kind + dispatch", () => {
  assert.match(RENDER, /kind: "retrying"; retries\?: number; info\?: /);
  assert.match(RENDER, /kind: "retried"; retries: number; ts\?: string; uuid\?: string/);
  assert.match(RENDER, /ev\.kind === "retrying"\) return renderRetrying\(ev\)/);
  assert.match(RENDER, /ev\.kind === "retried"\) return renderRetried\(ev\)/);
});

test("renderRetrying is an animated element (loader dots) with the live attempt count", () => {
  const body = RENDER.slice(RENDER.indexOf("function renderRetrying("), RENDER.indexOf("function renderRetried("));
  assert.match(body, /el\("div", "turn turn-retrying"\)/);
  assert.match(body, /line\.appendChild\(metaDots\(\)\)/);                         // the loader dots (mid-operation)
  // singular "API retrying" until attempt 2+, then the live count "API retrying — attempt N"
  assert.match(body, /n > 1 \? `API retrying — attempt \$\{n\}` : "API retrying"/);
});

test("renderRetrying surfaces the api_retry payload's own detail (the user 2026-07-10)", () => {
  const body = RENDER.slice(RENDER.indexOf("function renderRetrying("), RENDER.indexOf("// The next-attempt countdown's text"));
  assert.ok(body, "the renderRetrying slice is anchored");
  assert.match(body, /info\.attempt \|\| ev\.retries/, "payload attempt number outranks the local count");
  assert.match(body, /` of \$\{info\.max\}`/, "the retry budget shows when the payload names it");
  // the error behind the backoff on its own muted line, full message in the tooltip
  assert.match(body, /el\("div", "retrying-err"\)/);
  assert.match(body, /`HTTP \$\{info\.status\}`/);
  assert.match(body, /err\.title = msg/);
});

test("the next-try countdown TICKS every second — it is not frozen at render time (the user 2026-07-24)", () => {
  // the bug: the countdown re-derived only on re-render, so it sat at "next try in ~3s" for the whole
  // backoff. A number that never moves reads as broken. The epoch now rides a data attr and a 1s tick
  // rewrites the span, exactly like the API-error card's countdown.
  const body = RENDER.slice(RENDER.indexOf("function renderRetrying("), RENDER.indexOf("// The next-attempt countdown's text"));
  assert.match(body, /el\("span", "retrying-countdown"\)/);
  assert.match(body, /cd\.dataset\.retryAt = String\(info\.retryAt\)/, "the authoritative epoch rides the element");
  assert.match(RENDER, /function retryingTick\(\): void \{/);
  assert.match(RENDER, /querySelectorAll\("\.retrying-countdown"\)/);
  assert.match(RENDER, /cd\.textContent = retryingCountdownText\(at\)/);
  // ONE 1s timer drives both countdowns — no second scheduler
  assert.match(RENDER, /setInterval\(\(\) => \{ apiRetryTick\(\); retryingTick\(\); \}, 1000\)/);
  assert.doesNotMatch(RENDER, /next try in ~\$\{waitS\}s/, "the frozen render-time countdown is gone");
});

test("a past-due countdown reads 'retrying now', never a stuck 0s or a negative", () => {
  const fn = RENDER.slice(RENDER.indexOf("function retryingCountdownText("), RENDER.indexOf("function retryingTick("));
  assert.match(fn, /s > 0 \? `— next try in \$\{s\}s…` : "— retrying now…"/);
});

test("the card carries a Stop control that interrupts the stalled turn (the user 2026-07-24)", () => {
  // the CLI owns the backoff and the SDK exposes no handle on it, so the honest stop is the same interrupt
  // Ctrl+C sends — it cuts the turn AND leaves the thread retry-suppressed so romp's loop won't relapse.
  const body = RENDER.slice(RENDER.indexOf("function renderRetrying("), RENDER.indexOf("// The next-attempt countdown's text"));
  assert.match(body, /el\("button", "retrying-stop"\)/);
  assert.match(body, /stop\.dataset\.act = "stopRetrying"/, "delegated by data-act, not a per-render listener");
  assert.match(body, /stop\.textContent = "Stop retrying"/);
  // the handler lives on the STABLE body root (the transcript tail rebuilds every push → a rebuilt node
  // would eat a mid-press click), and acknowledges the click before any round-trip
  assert.match(RENDER, /stopRetrying: \(el\) => \{/);
  assert.match(RENDER, /b\.textContent = "Stopping…"/);
});

test("the stop control reuses the API-error card's control chrome, and the countdown uses tabular digits", () => {
  // a control matches a control (one treatment per information type) — the two cards read as one family
  assert.match(CSS, /\.retrying-stop \{[^}]*color: var\(--dim\)/);
  assert.match(CSS, /\.retrying-stop \{[^}]*border: 1px solid var\(--rail\)/);
  assert.match(CSS, /\.retrying-stop:disabled \{[^}]*cursor: default/);
  // tabular so the ticking number never jitters the row
  assert.match(CSS, /\.retrying-countdown \{[^}]*font-variant-numeric: tabular-nums/);
});

test("the error line wears the SAME 0.9em as the retrying line (one size per information type), muted", () => {
  assert.match(CSS, /\.retrying-err \{[^}]*font-size: 0\.9em/);
  assert.match(CSS, /\.retrying-err \{[^}]*color: color-mix\(in srgb, #e67e22 55%, var\(--dim\)\)/);
});

test("renderRetried is a static, muted 'Recovered after N retries' note (pluralized)", () => {
  const body = RENDER.slice(RENDER.indexOf("function renderRetried("), RENDER.indexOf("// Compact a token count"));
  assert.match(body, /el\("div", "turn turn-retried"\)/);
  assert.match(body, /`Recovered after \$\{n\} \$\{n === 1 \? "retry" : "retries"\}`/);
  assert.doesNotMatch(body, /metaDots/, "the recovered note is static — no loader animation");
});

test("the retrying element is tinted the amber retrying STATUS color (#e67e22), matching the tab border", () => {
  // it must read as the SAME state the amber tab outline shows (.tab.tab-retrying { --state: #e67e22 })
  assert.match(CSS, /\.retrying-line \{[^}]*color: #e67e22/);
  assert.match(CSS, /\.turn-retrying \.dot \{[^}]*background: #e67e22/);
  assert.match(CSS, /\.turn-retrying \.meta-dots i \{[^}]*background: #e67e22/);   // loader dots amber, not the default accent blue
  assert.match(CSS, /\.tab\.tab-retrying \{ --state: #e67e22/);                    // same status color as the border
});

test("the recovered note is muted (dim), not amber — it's a resolved historical marker", () => {
  // the effort note shares this rule now (grouped selector) — still muted, same treatment (2026-07-16)
  assert.match(CSS, /\.retried-line, \.effort-line \{[^}]*color: var\(--dim\)/);
});
