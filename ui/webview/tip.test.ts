// The ONE tooltip treatment (2026-08-28): every styled tooltip on the webview surfaces shares one
// behavior module (tip.ts — instant-in, TIP_GRACE_MS grace-out, flip + clamp, prune-on-anchor-gone)
// and ONE dress, the `.romp-tip` rule byte-mirrored in styles.css and feed.css (the .ctx-menu
// precedent — the feed page loads only feed.css). Tokens only, so themes restyle every tip at once.
// Source pins like feed-interrupting.test.ts, plus behavior via the real tip.ts module in jsdom-less
// string form (the show/hide paths are pinned at the source level — no DOM harness here).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const W = (f: string) => fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", f), "utf8");
const TIP = W("tip.ts");
const STYLES = W("styles.css");
const FEEDCSS = W("feed.css");
const FEED = W("feed.ts");
const RENDER = W("render.ts");
const MODULE = W("status-controls.ts");   // the status line's controls moved here from render.ts (T415 part two)
const FLEET = W("fleet.ts");
const FLEETCSS = W("fleet-pane.css");

// pull the `.romp-tip { ... }` block out of a sheet
function tipBlock(css: string, name: string): string {
  const m = css.match(/\.romp-tip \{[^}]*\}/);
  assert.ok(m, name + " carries the .romp-tip dress");
  return m![0];
}

test("ONE dress: .romp-tip is byte-identical in styles.css and feed.css (the .ctx-menu precedent)", () => {
  assert.equal(tipBlock(STYLES, "styles.css"), tipBlock(FEEDCSS, "feed.css"));
});

test("the dress is tokens-only — no raw hex or rgba, so themes restyle every tip for free", () => {
  const block = tipBlock(STYLES, "styles.css");
  assert.doesNotMatch(block, /#[0-9a-fA-F]{3}/, "no raw hex in the shared dress");
  assert.doesNotMatch(block, /rgba?\(/, "no raw rgb/rgba in the shared dress");
  // the load-bearing tokens: surface, border, radius, shadow — the values every migrated tip adopted
  for (const tok of ["--vscode-editorWidget-background", "--surface-raised", "--box-border",
                     "--radius-toast", "--shadow-toast", "--fg"]) {
    assert.ok(block.includes(`var(${tok}`) || block.includes(`, var(${tok}`), `dress uses ${tok}`);
  }
});

test("behavior: instant show on mouseenter, one grace constant on leave, prune on anchor-gone", () => {
  // INSTANT in — the mouseenter listener calls showTip directly, no intent timer anywhere on the show path
  assert.match(TIP, /anchor\.addEventListener\("mouseenter", \(\) => showTip\(anchor/);
  assert.match(TIP, /export const TIP_GRACE_MS = 160;/, "the one grace-out constant");
  assert.match(TIP, /window\.setTimeout\(hideTip, TIP_GRACE_MS\)/, "grace-out uses the constant");
  // hoverable tips cancel the grace on entry; document click/scroll drop the tip at once (event-based)
  assert.match(TIP, /tipEl\.addEventListener\("mouseenter"/);
  assert.match(TIP, /document\.addEventListener\("click", hideTip, true\);/);
  assert.match(TIP, /document\.addEventListener\("scroll", hideTip, true\);/);
  // anchor-gone prune (the feed age-tip's 1s-vanish fix): hide ONLY when the anchor left the DOM
  assert.match(TIP, /if \(tipAnchor && !tipAnchor\.isConnected\) hideTip\(\);/);
  // setTip strips the native title so the browser tooltip never doubles the styled one
  assert.match(TIP, /anchor\.removeAttribute\("title"\);/);
});

test("feed: the age tip rides wireTip with prune semantics — the 1s-vanish fix is not regressed", () => {
  assert.match(FEED, /import \{ wireTip, setTip, pruneTip \} from "\.\/tip";/);
  assert.match(FEED, /wireTip\(elm, \(tip\) => \{/, "age provenance popover is a shared tip");
  assert.match(FEED, /\{ place: "above" \}/, "the age stamp's story reads above the stamp");
  assert.match(FEED, /pruneTip\(\);/, "each render prunes only a torn-out anchor, never an alive hover");
});

test("upgraded spots wire through setTip — the native title= on them is gone", () => {
  // feed badges + the card bell
  assert.match(FEED, /setTip\(intingBadge, "stop sent/);
  assert.match(FEED, /setTip\(a\._blocked as HTMLElement, it\.blocked\.what/);
  assert.match(FEED, /setTip\(a\._apiBadge as HTMLElement,/);
  assert.match(FEED, /setTip\(a\._jauthBadge as HTMLElement,/);
  assert.match(FEED, /setTip\(a\._retryBadge as HTMLElement,/);
  assert.match(FEED, /setTip\(btn, say\);/, "the card bell's tip");
  assert.doesNotMatch(FEED, /intingBadge\.title =/);
  assert.doesNotMatch(FEED, /a\._blocked\.title =/);
  assert.doesNotMatch(FEED, /a\._apiBadge\.title =/);
  assert.doesNotMatch(FEED, /a\._jauthBadge\.title =/);
  assert.doesNotMatch(FEED, /a\._retryBadge\.title =/);
  // statusline meta badges, the stop button (two lines: label + explanation), composer attach/send
  assert.match(MODULE, /setTip\(btn, kind === "model" \? "change model \(sends \/model\)"/);   // the badges build in status-controls.ts (T415 part two)
  assert.match(RENDER, /setTip\(btn, stuck\s*\n\s*\? "Stop retrying\\ninterrupt this thread/);
  assert.match(RENDER, /setTip\(attach, "Attach a file"\)/);
  assert.match(RENDER, /setTip\(sendBtn, "Send \(Enter\)"\)/);
  assert.doesNotMatch(RENDER, /btn\.title = kind === "model"/);
  assert.doesNotMatch(RENDER, /btn\.title = stuck/);
  // icon-only buttons keep an accessible name once the title is stripped
  assert.match(RENDER, /attach\.setAttribute\("aria-label", "Attach a file"\)/);
  assert.match(FEED, /btn\.setAttribute\("aria-label", say\);/);
});

test("fleet hover card: instant-in, shared grace, dressed on the tip tokens", () => {
  assert.match(FLEET, /import \{ TIP_GRACE_MS \} from "\.\/tip";/);
  assert.doesNotMatch(FLEET, /hoverShowT/, "the 120ms intent debounce is gone — instant-in");
  assert.match(FLEET, /window\.setTimeout\(hideHoverCard, TIP_GRACE_MS\);/);
  // the dress tokens (styles.css loads before fleet-pane.css on both hosts, so they resolve)
  assert.match(FLEETCSS, /\.fl-hover\{[^}]*background:var\(--vscode-editorWidget-background,var\(--surface-raised\)\)/);
  assert.match(FLEETCSS, /\.fl-hover\{[^}]*border:1px solid var\(--box-border\)/);
  assert.match(FLEETCSS, /\.fl-hover\{[^}]*border-radius:var\(--radius-toast\)/);
  assert.match(FLEETCSS, /\.fl-hover\{[^}]*box-shadow:var\(--shadow-toast\)/);
});

test("the chat tab tip keeps its mono body + width cap but wears the same surface tokens", () => {
  const m = STYLES.match(/\.tab-tip \{[\s\S]*?\n\}/);
  assert.ok(m, "styles.css carries .tab-tip");
  const block = m![0];
  assert.match(block, /background: var\(--vscode-editorWidget-background, var\(--surface-raised\)\)/);
  assert.match(block, /border: 1px solid var\(--box-border\)/);
  assert.match(block, /border-radius: var\(--radius-toast\)/);
  assert.match(block, /box-shadow: var\(--shadow-toast\)/);
  assert.match(block, /font-family: var\(--mono\)/, "the mono body stays — it's paths/branch/model");
  assert.match(block, /max-width: calc\(100vw - 12px\)/, "its own pane-width cap stays");
});
