// The day divider (the user 2026-08-01). A day boundary used to stack its date on its own row
// INSIDE the 47px-wide rail marker; "Yesterday" measures 52.6px bold at the default 13px, so the
// pane's overflow:hidden ate its leading "Y". Sizing the label to fit that gutter is not a fix —
// `--fs` follows --vscode-chat-font-size, so a larger chat font re-clips whatever just fit at 13px.
// The date moved to a full-width divider in the prose column, where no date string can be cut off.
//
// Two invariants worth pinning, both of which a refactor could quietly break:
//   - the divider is a SIBLING before the turn, never a child of it. .dot and .time-marker are
//     absolutely positioned against the TURN's top edge, so a divider inside the turn would push
//     the message down and strand the dot up beside the rule.
//   - every append path emits it. The windowed rebuild and the incremental tail append are separate
//     code paths; when only one had it, scrolling back rebuilt dividers that live appends had dropped.
// The chat renderer has no jsdom harness, so — like render-rail.test.ts — pin at the source.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("dayDividerFor returns a divider only on the first turn of a past day", () => {
  const fn = RENDER.slice(RENDER.indexOf("function dayDividerFor"));
  assert.match(fn.slice(0, 400), /if \(!day \|\| !date\) return null/, "every other turn gets nothing");
  assert.match(fn.slice(0, 400), /markerLabel\(epoch, prevEpoch, Date\.now\(\)\)/, "same day-boundary rule as the marker");
});

test("the divider is a sibling of the turn, never a child (the dot anchors to the turn's top)", () => {
  // a turn.insertBefore/appendChild of the divider would displace the absolutely-positioned dot
  assert.doesNotMatch(RENDER, /turn\.(insertBefore|appendChild)\(\s*(dv|dayDivider)/);
  // it is appended to the thread/fold container instead
  assert.match(RENDER, /v\.el\.appendChild\(tag\(dv\)\)/, "windowed path appends to the thread");
  assert.match(RENDER, /wrap\.appendChild\(dv\)/, "cleared-episode fold appends to the fold body");
});

test("every append path emits the divider, so scrolling back can't disagree with the live tail", () => {
  // four call sites: windowed rebuild, incremental tail append, cleared-episode fold, and the
  // comment popover's chat-parity loop (the parity bundle, 2026-08-26)
  // (the `function dayDividerFor(` definition is excluded, hence the negative lookbehind)
  const calls = RENDER.match(/(?<!function )dayDividerFor\(/g) ?? [];
  assert.equal(calls.length, 4, `expected 4 dayDividerFor() call sites, found ${calls.length}`);
});

test("the windowed divider carries data-unit so the scroll-to-unit map still resolves it", () => {
  // appendItem tags via tag(); the tail path sets it explicitly
  assert.match(RENDER, /dv\.dataset\.unit = String\(i\)/);
});

test("the incremental tail trim goes by data-unit, not by child count", () => {
  // THE subtle break this feature could cause: the hot append path used to keep
  // `spacer + (from - winStart)` CHILDREN, one per unit. A day divider makes a unit own two
  // nodes, so that count trimmed one real turn off the tail per divider in the kept range —
  // and the re-render started at `from`, so those turns were gone until a full rebuild.
  assert.doesNotMatch(RENDER, /while \(v\.el\.childNodes\.length > keep\)/, "count-based trim is gone");
  assert.match(RENDER, /while \(v\.el\.lastChild && unitOf\(v\.el\.lastChild\) >= from\)/);
  // the spacer has no data-unit, so it must map to a sentinel BELOW any real unit and end the walk
  assert.match(RENDER, /n\.dataset\.unit != null \? Number\(n\.dataset\.unit\) : -1/);
});

test("the divider label is never constrained to a fixed width", () => {
  const rule = CSS.slice(CSS.indexOf(".day-divider-label"));
  assert.doesNotMatch(rule.slice(0, 200), /\bwidth:|max-width:/, "a fixed width is the bug being closed");
  // the hairline fills the leftover room, so the label takes exactly what it needs
  assert.match(CSS, /\.day-divider::after \{[^}]*flex: 1 1 auto/);
  assert.match(CSS, /\.day-divider-label \{[^}]*flex: 0 0 auto/);
});

test("the divider label matches the rail marker's type size", () => {
  // one size for one kind of label — no new font-size on this surface.
  // Anchor each rule at the START of a line: a bare indexOf(".time-marker {") hits the compound
  // `.turn-compacting .dot, .turn-compacting .time-marker {` rule first and reads the wrong size.
  const rule = (sel: string): string => {
    const m = CSS.match(new RegExp("^\\" + sel + " \\{[^}]*\\}", "m"));
    assert.ok(m, `no top-level ${sel} rule`);
    return m[0];
  };
  const size = (s: string): string | null => (s.match(/font-size: ([\d.]+em)/) ?? [])[1] ?? null;
  assert.equal(size(rule(".day-divider")), size(rule(".time-marker")));
  assert.equal(size(rule(".day-divider")), "0.76em");
});
