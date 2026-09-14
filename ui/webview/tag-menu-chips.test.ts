// THE TAG-LENS MENU'S TAGS ARE CHIPS (the user 2026-09-09, T283): each union tag renders as the shared
// tag chip and acts as a toggle button — selected = full colour, unselected = faded (its colour kept),
// aria-pressed on the chip, one tag per line with the chip at the left, the menu staying open across
// toggles. All and (no tags) keep the row grammar (All the exclusive pick), the group switch row is
// unchanged. Executed against a stub document (the tab-groups pattern: no jsdom) plus source pins on
// tag-menu.ts and the two sheets. Synthetic tags only.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const ui = (...p: string[]) => fs.readFileSync(path.resolve(process.cwd(), "..", "ui", ...p), "utf8");
const MENU = ui("webview", "tag-menu.ts");
const CSS = ui("webview", "styles.css");
const FEED_CSS = ui("webview", "feed.css");
const OPEN = MENU.slice(MENU.indexOf("export function openTagMenu"), MENU.indexOf("export function tagMenuButton"));
const LOOP = OPEN.slice(OPEN.indexOf("for (const u of opts.unions())"), OPEN.indexOf("if (opts.groupToggle || opts.onConfigure)"));

type Node = { tag: string; attrs: Record<string, string>; kids: Node[]; text?: string; style: Record<string, string>;
              handlers: Record<string, () => void>; setAttribute(k: string, v: string): void; getAttribute(k: string): string | null;
              appendChild(c: Node): void; addEventListener(k: string, fn: () => void): void; remove(): void;
              getBoundingClientRect(): { left: number; right: number; top: number; bottom: number };
              offsetWidth: number; offsetHeight: number; textContent: string; dataset: Record<string, string> };

/** The real openTagMenu against a stub document; returns the menu's rows and the recorded applies. */
function open(lens: { all?: boolean; none?: boolean; tags?: string[] }, unions: { name: string; color: string }[]) {
  const created: Node[] = [];
  const mk = (tag: string): Node => {
    const n: Node = { tag, attrs: {}, kids: [], style: {}, handlers: {}, offsetWidth: 200, offsetHeight: 100, dataset: {},
      get textContent() { return this.kids.map((k) => k.tag === "#text" ? k.text || "" : k.textContent).join(""); },
      set textContent(v: string) { this.kids = v ? [{ tag: "#text", text: v } as Node] : []; },
      setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
      appendChild(c) { this.kids.push(c); }, addEventListener(k, fn) { this.handlers[k] = fn; }, remove() { /* detached */ },
      getBoundingClientRect() { return { left: 10, right: 40, top: 10, bottom: 30 }; } };
    created.push(n); return n;
  };
  const g = globalThis as any;
  const saved = { document: g.document, window: g.window, localStorage: g.localStorage };
  const body = mk("body");
  g.document = { createElement: mk, createTextNode: (t: string) => ({ tag: "#text", text: t }), body, addEventListener() { /* closers */ } };
  g.window = { addEventListener() { /* storage */ }, innerWidth: 1200, innerHeight: 800 };
  g.localStorage = { setItem() { /* echo */ } };
  const applies: { lens: unknown; done: boolean }[] = [];
  let current = lens;
  // the stub document stays installed until close(): the rows' click handlers rebuild the menu through it
  const restore = () => { g.document = saved.document; g.window = saved.window; g.localStorage = saved.localStorage; };
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const mod = require("./tag-menu");
    mod.closeTagMenu();
    mod.openTagMenu(mk("button"), {
      lens: () => current,
      unions: () => unions.map((u) => ({ ...u, members: [], ids: [], localId: null, locals: [], remotes: [] })),
      onApply: (l: unknown, done: boolean) => { applies.push({ lens: l, done }); current = l as typeof lens; },
    });
    const menu = body.kids[body.kids.length - 1];
    return { menu, applies, rows: () => menu.kids, created, close: () => { mod.closeTagMenu(); restore(); } };
  } catch (e) { restore(); throw e; }
}

const label = (n: Node): string => n.kids.map((k) => k.tag === "#text" ? (k.text || "") : label(k)).join("");   // recursive: the return type is stated (tsc strict)
// T413 (the user 2026-09-14): each tag ROW is the house switch (role menuitemcheckbox, aria-checked) with a two-state mark at its
// right (the ✓-in-circle when selected, an empty ring when not), the chip lit or faded beside it; the chip itself is decorative
const chipOf = (row: Node) => row.kids.find((k) => k.tag === "span" && /border:1px solid/.test(k.attrs.style || "")) as Node | undefined;
const markOf = (row: Node) => row.kids.find((k) => k.tag === "span" && "data-check" in k.attrs) as Node | undefined;

test("each union tag is its own row switch: role menuitemcheckbox + aria-checked, the chip full colour when selected and faded when not, the mark a ✓ or a ring (T413)", () => {
  const m = open({ tags: ["infra"] }, [{ name: "infra", color: "#54B204" }, { name: "qa", color: "#3355aa" }]);
  const rows = m.rows();
  assert.equal(label(rows[0]), "All"); assert.equal(label(rows[1]), "(no tags)");
  const infra = chipOf(rows[2])!, qa = chipOf(rows[3])!;
  assert.ok(infra && qa, "the two tags render as chips, one per row, after All and (no tags)");
  assert.equal(rows[2].attrs.role, "menuitemcheckbox"); assert.equal(rows[2].attrs["aria-checked"], "true", "the row is the checkbox and reads selected");
  assert.equal(rows[3].attrs.role, "menuitemcheckbox"); assert.equal(rows[3].attrs["aria-checked"], "false");
  assert.equal(infra.attrs["aria-pressed"], undefined, "the chip carries no control role of its own any more: the row does");
  assert.equal(infra.attrs.role, undefined);
  assert.doesNotMatch(infra.attrs.style, /opacity/, "a selected chip stands at full opacity (the lit state kept)");
  assert.equal(infra.attrs["class"], undefined, "…and wears no off class");
  assert.match(infra.attrs.style, /border:1px solid #54B204;color:#54B204;/, "the chip keeps the tag's own colour");
  assert.equal(qa.attrs["class"], "tag-chip-off", "an unselected chip wears the faded class");
  assert.match(qa.attrs.style, /opacity:0\.45;/, "…and paints the same fade inline for a sheet-less host");
  assert.match(qa.attrs.style, /border:1px solid #3355aa;color:#3355aa;/, "faded, not recoloured");
  const on = markOf(rows[2])!, off = markOf(rows[3])!;
  assert.ok(on && off, "each tag row carries the mark");
  assert.equal(on.attrs["data-check"], "true"); assert.equal(label(on), "✓", "selected: the house ✓-in-circle");
  assert.match(on.attrs.style, /background:var\(--check-bg, #1EA1EB\)/);
  assert.equal(off.attrs["data-check"], "false"); assert.equal(label(off), "", "unselected: an empty ring, so the checkbox reads in both states");
  assert.match(off.attrs.style, /border:1px solid var\(--menu-border, rgba\(255,255,255,0\.12\)\)/);
  assert.equal(label(rows[2]).replace("✓", ""), "infra"); assert.equal(label(rows[3]), "qa");
  m.close();
});

test("clicking a tag's row toggles that tag and the menu stays open and repaints, the row's aria-checked and mark following", () => {
  const m = open({ tags: ["infra"] }, [{ name: "infra", color: "#54B204" }, { name: "qa", color: "#3355aa" }]);
  const before = m.rows().length;
  m.rows()[3].handlers.click();   // qa: off → on
  assert.deepEqual(m.applies, [{ lens: { none: undefined, tags: ["infra", "qa"] }, done: false }], "the toggle applies without closing (done=false)");
  const rows = m.rows();
  assert.equal(rows.length, before, "repainted in place: the same rows");
  assert.equal(rows[3].attrs["aria-checked"], "true", "the row now reads selected");
  assert.equal(label(markOf(rows[3])!), "✓"); assert.equal(chipOf(rows[3])!.attrs["class"], undefined);
  rows[2].handlers.click();       // infra: on → off
  assert.equal(m.rows()[2].attrs["aria-checked"], "false");
  assert.equal(label(markOf(m.rows()[2])!), ""); assert.equal(chipOf(m.rows()[2])!.attrs["class"], "tag-chip-off");
  m.close();
});

test("All and (no tags) keep the row grammar: All is the exclusive pick that closes the menu; (no tags), a selection member, wears the two-state mark too", () => {
  const m = open({ none: true, tags: ["infra"] }, [{ name: "infra", color: "#54B204" }]);
  const rows = m.rows();
  assert.equal(rows[1].attrs.role, "menuitemcheckbox"); assert.equal(rows[1].attrs["aria-checked"], "true", "(no tags) selected: a checkbox row like the tags");
  assert.equal(label(markOf(rows[1])!), "✓");
  assert.ok(!rows[0].kids.some((k) => k.tag === "span" && label(k) === "✓"), "All not selected → no ✓");
  assert.equal(markOf(rows[0]), undefined, "All is the exclusive pick: the ✓ when current, no ring otherwise");
  rows[0].handlers.click();
  assert.deepEqual(m.applies.at(-1), { lens: { all: true }, done: true }, "All applies as the exclusive pick and closes");
  m.close();
});

test("source pins: the tag rows build through the shared tagChip, the row is the switch, the mark is the house token; the state is a class the two sheets define at the same opacity", () => {
  assert.match(LOOP, /const chip = tagChip\(u\.name, u\.color \|\| null, \{ off: !on \}\);/, "the pill every surface wears, faded when off");
  assert.match(LOOP, /r\.setAttribute\("role", "menuitemcheckbox"\);\s*\n\s*r\.setAttribute\("aria-checked", on \? "true" : "false"\);/, "the row is the checkbox");
  assert.doesNotMatch(LOOP, /aria-pressed/, "the chip carries no control role: one control per row");
  assert.match(LOOP, /r\.appendChild\(checkMark\(on\)\);/, "the two-state mark at the row's right");
  assert.match(MENU, /function checkMark\(on: boolean\): HTMLElement \{/, "one builder for the mark, the tag menu's and the rows menu's: the ✓-in-circle from --check-bg when on, an empty ring in the menu's hairline when off");
  assert.match(MENU, /border:1px solid var\(--menu-border, rgba\(255,255,255,0\.12\)\);background:transparent;/);
  assert.match(MENU, /export const TAG_CHIP_OFF_CLASS = "tag-chip-off";/);
  assert.match(MENU, /export const TAG_CHIP_OFF_OPACITY = "0\.45";/);
  for (const [name, sheet] of [["styles.css", CSS], ["feed.css", FEED_CSS]] as const)
    assert.match(sheet, /\n\.tag-chip-off \{ opacity: 0\.45; \}\n/, name + " defines the faded class at the inline value");
  // the ✓ grammar survives for All: the row helper paints the on mark from the token
  assert.match(OPEN, /else if \(current\) r\.appendChild\(checkMark\(true\)\);/);
  assert.match(OPEN, /row\("All", lensAll\(lens\)\)/); assert.match(OPEN, /row\("\(no tags\)", !lensAll\(lens\) && !!lens\.none, false, true\)/, "(no tags): a two-state row");
});
