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
  const body = RENDER.slice(RENDER.indexOf("function renderRetrying("), RENDER.indexOf("function renderRetried("));
  assert.match(body, /info\.attempt \|\| ev\.retries/, "payload attempt number outranks the local count");
  assert.match(body, /` of \$\{info\.max\}`/, "the retry budget shows when the payload names it");
  // next-try countdown re-derives from the epoch each re-render — no client timer to drift
  assert.match(body, /Math\.ceil\(info\.retryAt - Date\.now\(\) \/ 1000\)/);
  assert.match(body, /next try in ~\$\{waitS\}s/);
  // the error behind the backoff on its own muted line, full message in the tooltip
  assert.match(body, /el\("div", "retrying-err"\)/);
  assert.match(body, /`HTTP \$\{info\.status\}`/);
  assert.match(body, /err\.title = msg/);
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
  assert.match(CSS, /\.retried-line \{[^}]*color: var\(--dim\)/);
});
