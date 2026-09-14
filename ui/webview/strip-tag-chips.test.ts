// THE STRIP'S SELECTED TAGS AS CHIPS (T413, the user 2026-09-14): when the strip is NOT grouping tabs by tag, every selected
// tag shows as the standard chip just LEFT of the tags button, so the selection reads without opening the menu; grouping,
// the tags are the section headings and nothing sits beside the button. The run is BOUNDED for the many-tags case (the
// user rule of 2026-09-09): the first chips, then one plain "+N more" chip that opens the menu; and a run that would wrap
// the right end onto a new row yields (hidden) rather than add a row, the button's accent still saying the strip is
// narrowed. The "no tags" pick is not a tag and draws no chip on the strip (T405's ruling stands). Executed: the bounded
// run and the shared sync over a stub document; pinned: the host's place, the mode gate, the fit check, the sheets.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const ui = (...p: string[]) => fs.readFileSync(path.resolve(process.cwd(), "..", "ui", ...p), "utf8");
const RENDER = ui("webview", "render.ts");
const MENU = ui("webview", "tag-menu.ts");
const CSS = ui("webview", "styles.css");

type Node = { tag: string; attrs: Record<string, string>; kids: Node[]; text?: string; style: Record<string, string>; title?: string; className?: string;
              handlers: Record<string, (e?: unknown) => void>; setAttribute(k: string, v: string): void; getAttribute(k: string): string | null;
              appendChild(c: Node): void; addEventListener(k: string, fn: (e?: unknown) => void): void; textContent: string; classList: { toggle(c: string, on?: boolean): void; add(c: string): void; contains(c: string): boolean } };
function stubDocument() {
  const mk = (tag: string): Node => {
    const n: Node = { tag, attrs: {}, kids: [], style: {}, handlers: {}, className: "",
      get textContent() { return this.kids.map((k) => k.tag === "#text" ? k.text || "" : k.textContent).join(""); },
      set textContent(v: string) { this.kids = v ? [{ tag: "#text", text: v } as Node] : []; },
      setAttribute(k, v) { this.attrs[k] = v; if (k === "class") this.className = v; }, getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
      appendChild(c) { this.kids.push(c); }, addEventListener(k, fn) { this.handlers[k] = fn; },
      classList: { toggle: (c, on) => { const has = (n.className || "").split(" ").includes(c); const want = on === undefined ? !has : on; n.className = (n.className || "").split(" ").filter((x) => x && x !== c).concat(want ? [c] : []).join(" "); },
                   add: (c) => { if (!(n.className || "").split(" ").includes(c)) n.className = ((n.className || "") + " " + c).trim(); }, contains: (c) => (n.className || "").split(" ").includes(c) } };
    return n;
  };
  const g = globalThis as any;
  const saved = { document: g.document };
  g.document = { createElement: mk, createTextNode: (t: string) => ({ tag: "#text", text: t }) };
  return { mk, restore: () => { g.document = saved.document; } };
}
const label = (n: Node): string => n.kids.map((k) => k.tag === "#text" ? (k.text || "") : label(k)).join("");
const UNIONS = ["infra", "web", "api", "docs", "tests", "auth", "deploy", "data"].map((name, i) => ({ name, color: "#" + (0x4ec9b0 + i * 1111).toString(16).padStart(6, "0"), members: [], ids: [], localId: null, locals: [], remotes: [] }));

test("chipRun bounds a selection: the first N and the count of the rest (the many-tags case), whole when it fits", () => {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const m = require("./tag-menu");
  assert.deepEqual(m.chipRun(["a", "b"], 3), { shown: ["a", "b"], more: 0 }, "two of a limit of three: all shown, nothing more");
  assert.deepEqual(m.chipRun(["a", "b", "c"], 3), { shown: ["a", "b", "c"], more: 0 }, "exactly the limit: all shown");
  assert.deepEqual(m.chipRun(["a", "b", "c", "d", "e", "f", "g", "h"], 3), { shown: ["a", "b", "c"], more: 5 }, "eight of three: three shown, five more");
  assert.deepEqual(m.chipRun([], 3), { shown: [], more: 0 });
  assert.deepEqual(m.chipRun(["a", "b", "c", "d"], 0), { shown: ["a", "b", "c", "d"], more: 0 }, "no limit (0) shows everything");
});

test("syncTagFilter with a limit builds the first chips and one plain '+N more' chip naming the rest, tags only (the none pick draws no chip on the strip)", () => {
  const { mk, restore } = stubDocument();
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const m = require("./tag-menu");
    const btn = mk("button"), host = mk("span");
    let opened = 0; btn.handlers.click = () => { opened++; }; (btn as any).click = () => btn.handlers.click();
    m.syncTagFilter(btn, host, { none: true, tags: UNIONS.map((u) => u.name) }, UNIONS, () => undefined, "inline", { limit: 3, tagsOnly: true });
    assert.equal(host.kids.length, 4, "three chips and the more chip");
    assert.deepEqual(host.kids.slice(0, 3).map((k) => label(k).replace("✕", "")), ["infra", "web", "api"], "the first three selected tags, in the unions' order");
    const more = host.kids[3];
    assert.equal(label(more), "+5 more", "the rest as one count, in the user's terms");
    assert.equal(more.className, "tag-chip-more");
    assert.match(more.title || "", /docs, tests, auth, deploy, data/, "its title names the rest");
    more.handlers.click({ stopPropagation() { /* the strip's own click */ } });
    assert.equal(opened, 1, "the more chip opens the menu through the button");
    assert.equal(btn.attrs["aria-pressed"], "true", "the button still says narrowed");
    // few: every chip, no more chip; the none pick alone: no chip at all, the accent alone
    m.syncTagFilter(btn, host, { tags: ["web", "auth"] }, UNIONS, () => undefined, "inline", { limit: 3, tagsOnly: true });
    assert.deepEqual(host.kids.map((k) => label(k).replace("✕", "")), ["web", "auth"]);
    m.syncTagFilter(btn, host, { none: true }, UNIONS, () => undefined, "inline", { limit: 3, tagsOnly: true });
    assert.equal(host.kids.length, 0, "narrowed to no tags: nothing on the strip (T405), the accent says it");
    assert.equal(btn.attrs["aria-pressed"], "true");
    // without the option the phone mount's behaviour stands: every chip, the none chip included
    m.syncTagFilter(btn, host, { none: true, tags: ["web"] }, UNIONS, () => undefined);
    assert.deepEqual(host.kids.map((k) => label(k).replace("✕", "")), ["no tags", "web"]);
  } finally { restore(); }
});

test("the strip: the chips host sits left of the button in the tag box, fed only outside group mode, bounded to three, fitted to the row", () => {
  assert.match(RENDER, /const tagChipsHost = el\("span", "tab-tagchips"\);/, "the host is built");
  assert.match(RENDER, /tagBox\.append\(tagChipsHost, tagBtn\);/, "and sits LEFT of the button in the tag box");
  assert.match(RENDER, /syncTagFilter\(tagBtn, plan\.sectioned \? null : tagChipsHost, surfaceLens\(v, "chat"\), unions, \(l\) => \{/, "sectioned (grouping on and a tag holding a visible tab, the plan's own reading): no host, the headings show the tags; otherwise the chips");
  assert.match(RENDER, /\}, "inline", \{ limit, tagsOnly: true \}\);/, "the chip count is the fit's to set (three, then fewer on a short row); the none pick draws none");
  const iEnd = RENDER.indexOf("  bar.appendChild(end);\n"), iFeed = RENDER.indexOf("    stripFit = () => fitStripChips(end, tagChipsHost, feed);"), iFit = RENDER.indexOf("  stripFit();\n");
  assert.ok(iEnd > 0 && iFeed > iEnd && iFit > iFeed, "the fit runs once the right end is on the bar, through the closure the strip's observer re-runs");
  assert.match(MENU, /export function chipRun<T>\(items: T\[\], limit: number\): \{ shown: T\[\]; more: number \}/);
  assert.match(MENU, /opts\?: \{ limit\?: number; tagsOnly\?: boolean \}/, "the sync's options");
  const box = CSS.match(/\n\.tab-tagchips \{[^}]*\}/)![0];
  assert.match(box, /display: inline-flex;/); assert.match(box, /min-width: 0;/); assert.match(box, /overflow: hidden;/); assert.match(box, /margin-right: 4px;/);
  assert.match(CSS, /\n\.tab-tagchips:empty \{ display: none; \}/, "an empty host takes no room");
  assert.match(CSS, /\n\.tab-tagchips \.tag-chip-more \{ cursor: pointer; \}/, "the more chip is a click");
});

// ROUND TWO (the manager's read of 2026-09-14): (1) the host's [hidden] was defeated by its author display, so the fit hid nothing
// and the run added a strip row at narrow widths; (2) the fit shrinks the run chip by chip before it hides it, and a run that
// would clip yields too; (3) the tags box and the right end shrink before the controls do; (4) the fit re-runs on the strip's
// resize, where before its verdict stood until some other input rebuilt the strip.
test("round two: the hidden host is out of the flow, the fit steps the run down before it hides, the shrink chain reaches the host, and a resize re-runs the fit", () => {
  assert.match(CSS, /\n\.tab-tagchips\[hidden\] \{ display: none; \}/, "[hidden] loses to author display (the sheet's standing trap): the fit's hide needs its own rule");
  const tagbox = CSS.match(/\n\.tab-tagbox \{[^}]*\}/)![0];
  assert.match(tagbox, /flex-wrap: nowrap;/, "the box never wraps the run under the button"); assert.match(tagbox, /min-width: 0;/, "and lets the run shrink");
  const end = CSS.match(/\n\.tab-strip-end \{[^}]*\}/)![0];
  assert.match(end, /min-width: 0;/, "the right end lets its content shrink: the run gives before the controls do");
  assert.match(RENDER, /^const STRIP_CHIP_LIMIT = 3;/m, "the run's full count, one name");
  const fit = RENDER.slice(RENDER.indexOf("function fitStripChips("), RENDER.indexOf("\n}\n", RENDER.indexOf("function fitStripChips(")));
  assert.match(fit, /^function fitStripChips\(end: HTMLElement, host: HTMLElement, feed: \(limit: number\) => void\): void \{/, "the fit feeds the run itself");
  assert.match(fit, /feed\(STRIP_CHIP_LIMIT\);/, "the full run first (the button's state syncs in the same call, host or none)");
  assert.match(fit, /host\.hidden = true;\s*\n\s*const without = end\.offsetTop;\s*\n\s*host\.hidden = false;/, "the right end's row read with the host out of the flow");
  assert.match(fit, /const fits = \(\) => end\.offsetTop === without && host\.scrollWidth <= host\.clientWidth \+ 1;/, "a run stands when the end keeps its row and no chip is clipped");
  assert.match(fit, /for \(let limit = STRIP_CHIP_LIMIT - 1; limit >= 1; limit--\) \{\s*\n\s*feed\(limit\);\s*\n\s*if \(fits\(\)\) return;\s*\n\s*\}\s*\n\s*host\.hidden = true;/, "then chip by chip, and hidden when even one chip and the count do not fit");
  assert.match(RENDER, /^let stripFit: \(\(\) => void\) \| null = null;/m, "the last paint's fit, kept for the observer");
  assert.match(RENDER, /tabRowObserver = new ResizeObserver\(\(\) => \{ stripFit\?\.\(\); paintTabRowLines\(bar\); \}\);/, "a resize re-runs the fit, then the hairlines follow the rows");
});
