// The tab menu's Billing flyout takes the user's shape (T387, the user 2026-09-12): the session's billings to pick from,
// then, only when there is more than one to choose from, a rule and ONE entry, Set default billing, which opens a
// further submenu holding exactly the same entries with the machine's default check-marked; a click sets the default;
// no sub-line anywhere. An Automatic way back to the helper rule sits at the END of that submenu behind its own rule,
// only while an explicit default stands (the manager's call for the user, to be vetoed there). render.ts has
// import-time DOM side effects, so openBillingFly is LIFTED (esbuild's ts loader, the browse-route idiom) with the
// real billingChoices, placeFlyBeside and wireFlyout beside it, and run on a tiny DOM whose handlers can be fired.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";
import { createRequire } from "node:module";

const requireCjs = createRequire(__filename);
const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
const ts = (code: string): string => requireCjs("esbuild").transformSync(code, { loader: "ts" }).code;

type El = {
  tag: string; className: string; textContent: string; title: string; children: El[]; parent: El | null; dataset: Record<string, string>;
  attrs: Record<string, string>; style: Record<string, string>; handlers: Record<string, Array<(ev: unknown) => void>>;
  classList: { add: (...c: string[]) => void; remove: (...c: string[]) => void; contains: (c: string) => boolean };
  appendChild: (c: El) => El; append: (...c: El[]) => void; remove: () => void; setAttribute: (k: string, v: string) => void;
  addEventListener: (t: string, fn: (ev: unknown) => void) => void; querySelector: (sel: string) => El | null; querySelectorAll: (sel: string) => El[];
  getBoundingClientRect: () => { left: number; right: number; top: number; bottom: number; width: number; height: number }; fire: (t: string) => void;
};
function has(e: El, cls: string): boolean { return e.className.split(/\s+/).includes(cls); }
function matches(e: El, sel: string): boolean {
  // selectors the flyout code uses: ".a", ".a.b" and ".a .b" (descendant: matched by the caller walking)
  return sel.split(".").filter(Boolean).every((c) => has(e, c));
}
function walk(e: El, out: El[] = []): El[] { for (const c of e.children) { out.push(c); walk(c, out); } return out; }
function mkEl(tag: string, cls = ""): El {
  const e: El = {
    tag, className: cls, textContent: "", title: "", children: [], parent: null, dataset: {}, attrs: {}, style: {}, handlers: {},
    classList: {
      add: (...c) => { const s = new Set(e.className.split(/\s+/).filter(Boolean)); c.forEach((x) => s.add(x)); e.className = [...s].join(" "); },
      remove: (...c) => { e.className = e.className.split(/\s+/).filter((x) => x && !c.includes(x)).join(" "); },
      contains: (c) => has(e, c),
    },
    appendChild: (c) => { e.children.push(c); c.parent = e; return c; },
    append: (...cs) => { cs.forEach((c) => e.appendChild(c)); },
    remove: () => { const p = e.parent; if (p) { p.children.splice(p.children.indexOf(e), 1); e.parent = null; } },
    setAttribute: (k, v) => { e.attrs[k] = v; },
    addEventListener: (t, fn) => { (e.handlers[t] = e.handlers[t] || []).push(fn); },
    querySelector: (sel) => { const parts = sel.trim().split(/\s+/); if (parts.length === 1) return walk(e).find((c) => matches(c, sel)) || null;
      const outer = walk(e).filter((c) => matches(c, parts[0])); for (const o of outer) { const inner = walk(o).find((c) => matches(c, parts[1])); if (inner) return inner; } return null; },
    querySelectorAll: (sel) => walk(e).filter((c) => matches(c, sel)),
    getBoundingClientRect: () => ({ left: 300, right: 460, top: 200, bottom: 224, width: 160, height: 24 }),
    fire: (t) => { for (const fn of e.handlers[t] || []) fn({ stopPropagation: () => {}, preventDefault: () => {} }); },
  };
  return e;
}
function lines(e: El): string[] { return e.children.map((c) => has(c, "ctx-sep") ? "---" : (c.textContent || c.querySelector(".ctx-item-label")?.textContent || "")); }
function subLines(e: El): number { return e.querySelectorAll(".ctx-item-sub").length; }

type Avail = { login?: boolean; key?: boolean; loginWhy?: string; keyWhy?: string; default?: string; defaultExplicit?: boolean };
function lift(avail: Avail, auth = "", acct = "") {
  const a = RENDER.indexOf("    const openBillingFly = (): HTMLElement | null => {");
  const b = RENDER.indexOf('    wireFlyout(menu, item, ".ctx-sub-billing"', a);
  assert.ok(a > 0 && b > a, "openBillingFly: anchors not found; re-anchor");
  const helpers = ["function billingChoices(", "function authLoginChoices(", "function authChoiceCurrent(", "function placeFlyBeside(", "function wireFlyout("].map((anchor) => {   // the two login helpers the merged slice calls (T346)
    const h = RENDER.indexOf(anchor); if (h < 0) return "";
    return RENDER.slice(h, RENDER.indexOf("\n}\n", h) + 2);
  }).join("\n");
  const code = ts(helpers + "\nconst HOVER_INTENT_MS = 120;\n" + RENDER.slice(a, b) + "\nreturn openBillingFly;");
  const posted: unknown[] = []; const dismissed: number[] = [];
  const menu = mkEl("div", "ctx-menu"); const item = mkEl("div", "ctx-item ctx-item-toggle ctx-item-billing"); menu.appendChild(item);
  const H = { st: { auth, authAcct: acct }, avail, id: "11111111-2222-3333-4444-555555555555", posted, dismissed };
  const prelude = `
    const el = (tag, cls) => mkEl(tag, cls || "");
    const st = H.st, avail = H.avail, id = H.id;
    const hostOf = () => "";
    const dismissTabMenu = () => { H.dismissed.push(1); };
    const vscodeApi = { postMessage: (m) => { H.posted.push(m); } };
    const window = { innerWidth: 1100, innerHeight: 700, setTimeout: (fn) => { fn(); return 1; }, clearTimeout: () => {} };
    const clearTimeout = window.clearTimeout;
  `;
  const open = (new Function("H", "mkEl", "menu", "item", prelude + code) as (h: unknown, m: typeof mkEl, me: El, it: El) => () => El | null)(H, mkEl, menu, item);
  const sub = open();
  assert.ok(sub, "the flyout opened");
  return { sub: sub!, menu, item, posted, dismissed };
}
const BOTH = { login: true, key: true, default: "key", defaultExplicit: false };

test("both billings pickable, no explicit default: the picks, a rule, ONE Set default billing entry, and no sub-line anywhere", () => {
  const { sub } = lift(BOTH, "", "user@example.com");
  assert.deepEqual(lines(sub), ["Login (user@example.com)", "API key", "---", "Set default billing"]);
  assert.equal(subLines(sub), 0, "no sub-line under anything: the entries are self-explanatory");
  const entry = sub.children[3];
  assert.ok(has(entry, "ctx-item-setdefault") && has(entry, "ctx-item"), entry.className);
  assert.equal(entry.querySelector(".ctx-caret")?.textContent, "▸", "the entry opens a further submenu: the caret says so");
  assert.equal(sub.querySelectorAll(".ctx-radio").length, 0, "the radio group is gone");
  assert.equal(sub.querySelectorAll(".ctx-sub-head").length, 0, "…and its head with the note");
});

test("the Set default billing entry opens a nested submenu INSIDE the flyout holding exactly the list's entries, none marked before an explicit default", () => {
  const { sub, posted, dismissed } = lift(BOTH, "key", "user@example.com");
  const entry = sub.children[3];
  entry.fire("click");
  const d = sub.querySelector(".ctx-sub-default");
  assert.ok(d, "the nested submenu is appended inside the Billing flyout, so leaving both closes both");
  assert.ok(has(d!, "ctx-sub") && has(d!, "ctx-menu"), d!.className);
  assert.deepEqual(lines(d!), ["Login (user@example.com)", "API key"], "the same entries as the list above, in the same order");
  assert.deepEqual(d!.children.map((c) => has(c, "current")), [false, false], "no explicit default: nothing is check-marked");
  assert.equal(d!.querySelectorAll(".ctx-sep").length, 0, "no Automatic and no rule while the default is automatic already");
  assert.equal(subLines(d!), 0);
  assert.ok(d!.children.every((c) => c.dataset.scope === "machine"));
  d!.children[0].fire("click");
  assert.deepEqual(posted, [{ type: "setAuth", id: "11111111-2222-3333-4444-555555555555", value: "login", scope: "machine" }], "a click sets the machine default");
  assert.equal(dismissed.length, 1, "and closes the menu");
  assert.ok(d!.style.left && d!.style.top, "placed beside its row by the shared placement rule");
  assert.ok(sub.style.left && sub.style.top);
});

test("an explicit default is check-marked in the nested submenu, and Automatic sits at the END behind its own rule; the marked entry posts nothing, Automatic posts auto", () => {
  const { sub, posted, dismissed } = lift({ login: true, key: true, default: "login", defaultExplicit: true }, "", "");
  sub.children[3].fire("click");
  const d = sub.querySelector(".ctx-sub-default")!;
  assert.deepEqual(lines(d), ["Login", "API key", "---", "Automatic"]);
  assert.deepEqual(d.children.map((c) => has(c, "current")), [true, false, false, false], "the explicit default wears the check");
  assert.equal(subLines(d), 0, "Automatic carries no sub-line either");
  d.children[0].fire("click");
  assert.deepEqual(posted, [], "the current default posts nothing");
  assert.equal(dismissed.length, 1, "…and dismisses the menu, as the picks list does on its current entry (review)");
  d.children[3].fire("click");
  assert.deepEqual(posted, [{ type: "setAuth", id: "11111111-2222-3333-4444-555555555555", value: "auto", scope: "machine" }], "Automatic clears the explicit default (the helper rule again)");
});

test("one billing to choose from (the other side unavailable here): no rule, no Set default billing entry; the unavailable side still listed, greyed", () => {
  const { sub } = lift({ login: true, key: false, keyWhy: "no apiKeyHelper configured", default: "login", defaultExplicit: false }, "", "");
  assert.deepEqual(lines(sub), ["Login", "API key"]);
  assert.ok(has(sub.children[1], "disabled") && sub.children[1].title === "no apiKeyHelper configured");
  assert.equal(sub.querySelectorAll(".ctx-sep").length, 0);
  assert.equal(sub.querySelectorAll(".ctx-item-setdefault").length, 0);
});

test("an older kernel that does not say whether the default is explicit shows no Set default billing entry", () => {
  const { sub } = lift({ login: true, key: true, default: "key" }, "", "");
  assert.deepEqual(lines(sub), ["Login", "API key"]);
  assert.equal(sub.querySelectorAll(".ctx-item-setdefault").length, 0);
});

test("the session's own pick list is unchanged: the current pick marked, a disabled entry posts nothing, the current pick dismisses and posts nothing", () => {
  const { sub, posted, dismissed } = lift({ login: false, loginWhy: "no Claude login signed in on this machine", key: true, default: "key", defaultExplicit: false }, "key", "");
  assert.deepEqual(sub.children.map((c) => has(c, "current")), [false, true]);
  sub.children[0].fire("click");
  assert.deepEqual(posted, []);
  assert.equal(dismissed.length, 0, "a disabled entry leaves the menu up");
  sub.children[1].fire("click");
  assert.deepEqual(posted, [], "the current pick posts nothing");
  assert.equal(dismissed.length, 1, "…and dismisses");
});

test("an available, non-current pick posts the per-session setAuth with NO scope key, and dismisses", () => {
  const { sub, posted, dismissed } = lift(BOTH, "key", "user@example.com");
  sub.children[0].fire("click");
  assert.deepEqual(posted, [{ type: "setAuth", id: "11111111-2222-3333-4444-555555555555", value: "login" }], "the session switcher: id and value, no scope");
  assert.equal(dismissed.length, 1);
});

test("source: ONE entry-list function feeds both menus, both flyouts ride wireFlyout and the shared placement rule", () => {
  const a = RENDER.indexOf("    const openBillingFly = (): HTMLElement | null => {");
  const BILL = RENDER.slice(a, RENDER.indexOf('    wireFlyout(menu, item, ".ctx-sub-billing"', a));
  assert.match(RENDER, /^function billingChoices\(st: Status, avail: AuthAvail\): Array<\{ label: string; value: string; why: string \}> \{/m);
  assert.equal((BILL.match(/billingChoices\(/g) || []).length, 1, "one call; the nested submenu iterates the SAME array");
  assert.match(BILL, /const choices = billingChoices\(st, avail\);/);
  assert.match(BILL, /const pickable = choices\.filter\(\(c\) => !c\.why\);\s*\n\s*if \(pickable\.length > 1 && avail\.default && avail\.defaultExplicit !== undefined\) \{/, "the rule and the entry only with more than one billing to choose from, from a kernel that reports the flag");
  assert.match(BILL, /wireFlyout\(sub, setDef, "\.ctx-sub-default", \(\) => openDefaultFly\(\)\);/, "the nested level rides the same hover-intent road, scoped to the Billing flyout");
  assert.match(BILL, /placeFlyBeside\(setDef, d\);/); assert.match(BILL, /placeFlyBeside\(item, sub\);/);
  assert.match(RENDER, /^function placeFlyBeside\(anchor: HTMLElement, fly: HTMLElement\): void \{/m);
  assert.doesNotMatch(BILL, /ctx-sub-head|ctx-radio|autoWord|machineChoices|Default for /, "the Default group, its head, note and radios are gone");
  assert.doesNotMatch(BILL, /ctx-item-sub/, "no sub-line is built anywhere in the flyout");
  assert.equal((RENDER.match(/type: "setAuth"/g) || []).length, 2, "two senders: the session pick and the machine default (the census in feed-cap-offer.test.ts)");
});

test("styles: the head and note rules are gone; both flyouts keep a menu's width with long labels truncating", () => {
  assert.doesNotMatch(CSS, /\.ctx-sub-head/, "no group head any more");
  assert.match(CSS, /^\.ctx-sub-billing, \.ctx-sub-default \{ max-width: 22em; \}/m);
  assert.match(CSS, /^\.ctx-sub-billing \.ctx-item, \.ctx-sub-default \.ctx-item \{ overflow: hidden; text-overflow: ellipsis; \}/m);
  // the review: the nested level keeps the flyout's row size (0.92em compounded once more before), and the entry's caret lines
  // up with the Billing and Tags carets (no check-mark room on a row that opens a submenu)
  assert.match(CSS, /^\.ctx-sub-default \{ font-size: 1em; \}/m);
  assert.match(CSS, /^\.ctx-sub\.ctx-sub-billing > \.ctx-item\.ctx-item-setdefault \{ padding-right: 10px; \}/m);
  // the tiebreak, computed (the lightbox bar's lesson): the caret rule must outrank the generic .ctx-sub .ctx-item padding, which
  // comes later in the sheet and would win a tie
  const spec = (sel: string): [number, number, number] => [(sel.match(/#[\w-]+/g) || []).length, (sel.match(/\.[\w-]+|\[[^\]]+\]|:(?!:)[\w-]+(\([^)]*\))?/g) || []).length,
    (sel.replace(/#[\w-]+|\.[\w-]+|\[[^\]]+\]|::?[\w-]+(\([^)]*\))?/g, " ").match(/(^|\s)[a-zA-Z][\w-]*/g) || []).length];
  const wins = (a: number[], b: number[]) => a[0] !== b[0] ? a[0] > b[0] : a[1] !== b[1] ? a[1] > b[1] : a[2] > b[2];
  const caretRule = (CSS.match(/^([^{}\n]*ctx-item-setdefault[^{}\n]*)\{ padding-right: 10px; \}/m) || [])[1];
  const genericRule = (CSS.match(/^([^{}\n]*)\{ padding-right: 26px; position: relative; \}/m) || [])[1];
  assert.ok(caretRule && genericRule, "both padding rules found");
  assert.ok(wins(spec(caretRule.trim()), spec(genericRule.trim())), "the caret rule outranks the generic submenu padding: " + caretRule + " vs " + genericRule);
});
