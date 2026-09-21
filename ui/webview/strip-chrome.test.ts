// THE TAB STRIP'S CHROME (T405, the user 2026-09-13; T412; T415): (1) the strip's gear renders the EXACT glyph the shell's
// settings gear wears at the bottom right of every romp page, from ONE source (icons.ts GEAR_GLYPH: the strip imports it, the
// kernel reads it from the file when it builds the rail), so the two cannot drift; (2) the tab lock left the strip with T405 and
// since T415 is a switch in the settings card's Tab strip section, where the gear's click lands (no menu in between; the lock's
// state, drag rules and store are unchanged); (3) the strip's tag control displays no chip of its own for the none pick (the tags
// show in the strip's sections when Group tabs by tag is on, the selected tags as chips beside the button otherwise, T413); (4)
// the gear sits at the strip's farthest right, dressed as the rail's (T412). Source pins on render.ts, styles.css, icons.ts and
// kernel.py. Synthetic only.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const ui = (...p: string[]) => fs.readFileSync(path.resolve(process.cwd(), "..", ...p), "utf8");
const RENDER = ui("ui", "webview", "render.ts");
const ICONS = ui("ui", "webview", "icons.ts");
const CSS = ui("ui", "webview", "styles.css");
const KERNEL = ui("kernel", "kernel.py");
const TAGMENU = ui("ui", "webview", "tag-menu.ts");

const decodeTs = (lit: string) => lit.replace(/\\u([0-9a-fA-F]{4})/g, (_m, h) => String.fromCharCode(parseInt(h, 16)));

test("one gear, one glyph, one source: the strip renders icons.ts GEAR_GLYPH and the kernel reads the same file for the rail", () => {
  const m = /^export const GEAR_GLYPH = "((?:\\u[0-9a-fA-F]{4}|[^"\\])+)";/m.exec(ICONS);
  assert.ok(m, "icons.ts declares GEAR_GLYPH");
  const glyph = decodeTs(m![1]);
  assert.equal(glyph, "\u26ed", "the gear-without-hub character the rail has worn since 2026-06-29");
  assert.match(RENDER, /^import \{ GEAR_GLYPH, ICON_FORK \} from "\.\/icons";/m, "the strip imports it");
  assert.match(RENDER, /gear\.textContent = GEAR_GLYPH;/, "and renders exactly it");
  assert.doesNotMatch(RENDER, /M19\.4 15a1\.7 1\.7 0 0 0 \.3 1\.8/, "the strip's own gear drawing is gone");
  // the rail: the kernel's landing renders _gear_glyph(), which reads icons.ts; no literal gear character in the rail's markup line
  const rail = KERNEL.split("\n").find((l) => l.includes("id=rail-gear")) || "";
  assert.match(rail, /aria-label=Settings>" \+ _gear_glyph\(\) \+ "<\/div>"/, "the rail's markup renders the read glyph");
  assert.equal(rail.includes("\u26ed"), false, "no literal gear character in the rail's line");
  assert.match(KERNEL, /src = \(UI \/ "webview" \/ "icons\.ts"\)\.read_text\(encoding="utf-8"\)/, "_gear_glyph reads icons.ts");
  assert.match(KERNEL, /re\.search\(r'export const GEAR_GLYPH = \\x22\(\(\?:\\\\u\[0-9a-fA-F\]\{4\}\|\[\^\\x22\\\\\]\)\+\)\\x22;', src\)/,
    "with the export's own shape, the quotes as \\x22: api-health-axis.test.ts pairs kernel.py's double quotes to find the landing's rules, so no line may add an odd count");
  const added = KERNEL.slice(KERNEL.indexOf("def _gear_glyph()"), KERNEL.indexOf("\n\n", KERNEL.indexOf("def _gear_glyph()")));
  assert.equal((added.match(/"/g) || []).length % 2, 0, "_gear_glyph's body pairs its double quotes");
  // the failure-mode fallback is pinned equal to the constant, so a change to the glyph moves both or fails here
  const fb = /^_GEAR_GLYPH_FALLBACK = "((?:\\u[0-9a-fA-F]{4}|[^"\\])+)"/m.exec(KERNEL);
  assert.ok(fb, "the kernel names its fallback");
  assert.equal(decodeTs(fb![1]), glyph, "the fallback IS the constant's character");
});

test("the strip's gear opens the settings' Tab strip section directly (T415): no lock button, no menu, the keyboard belt kept", () => {
  assert.doesNotMatch(RENDER, /el\("button", "tab-lock"/, "no lock button in the strip");
  assert.doesNotMatch(RENDER, /el\("span", "tab-lockbox"\)/, "no lock box in the strip");
  assert.match(RENDER, /gear\.addEventListener\("click", \(e\) => \{ e\.stopPropagation\(\); openSettingsOn\("chat", "tabstrip"\); \}\);/, "one click, the settings at the strip's section");
  assert.doesNotMatch(RENDER, /openRowsMenu|Tab widgets…/, "no menu, no widgets row: the section holds the lock and Tab widgets follows it in the card");
  // the lock's state, its drag rules and its saveSettings road are as they were (tab-lock.test.ts pins them); only the toggle's door moved, twice (T405, T415)
  assert.match(RENDER, /const focusedGear = !!focusedEl\?\.closest\("\.tab-widgets-gear"\);/, "a keyboard press on the gear keeps the focus across the strip's rebuild");
  assert.match(RENDER, /\} else if \(focusedGear\) \(bar\.querySelector\("\.tab-widgets-gear"\) as HTMLElement \| null\)\?\.focus\(\);/);
  assert.doesNotMatch(RENDER, /focusedLock/, "the lock's own focus rule went with the button");
});

test("the strip's tag control shows the selected tags as chips left of the button outside group mode (T413), none for the no-tags pick (T405 stands)", () => {
  assert.match(RENDER, /const tagChipsHost = el\("span", "tab-tagchips"\);/, "the chips host is back (T413)");
  assert.match(RENDER, /tagBox\.append\(tagChipsHost, tagBtn\);/, "left of the button in the strip's tag box");
  assert.match(RENDER, /syncTagFilter\(tagBtn, plan\.sectioned \? null : tagChipsHost, surfaceLens\(v, "chat"\)/, "grouping: the headings carry the tags and no host is fed; otherwise the chips");
  assert.match(RENDER, /syncTagFilter\(mslot\.children\[0\] as HTMLElement, phoneLayout\(\) \? \(mslot\.children\[1\] as HTMLElement\) : null,/, "the phone header's mount builds its chips only in the phone layout: on the desktop no chip is built per paint anywhere (the T405 read)");
  assert.match(TAGMENU, /export function syncTagFilter\(btn: HTMLElement, chipsHost: HTMLElement \| null,/);
  assert.match(TAGMENU, /btn\.setAttribute\("aria-pressed", narrowed \? "true" : "false"\);\s*\n\s*if \(!chipsHost\) return;/, "the sync skips the chip loop with no host");
  // the phone header's mount is untouched: its chips still ride the slot (T161)
  assert.match(RENDER, /mslot\.append\(mBtn, mChips\);/);
});

test("the strip's right end (T412): the tags button and the gear share one invisible wrapper appended last and pushed to the farthest right; the gear is a bare glyph dressed exactly as the rail's settings gear", () => {
  // the render: the tag box goes INTO the wrapper, the gear after it with no box of its own, the wrapper is the last thing on the bar
  const iEnd = RENDER.indexOf('const end = el("span", "tab-strip-end");'), iTag = RENDER.indexOf("  end.appendChild(tagBox);\n"), iGear = RENDER.indexOf('const gear = el("button", "tab-widgets-gear") as HTMLButtonElement;'),
        iGearAppend = RENDER.indexOf("end.appendChild(gear);"), iEndAppend = RENDER.indexOf("bar.appendChild(end);");
  assert.ok(iEnd > 0 && iEnd < iTag && iTag < iGear && iGear < iGearAppend && iGearAppend < iEndAppend, "wrapper, tag box, gear, then the wrapper onto the bar");
  assert.doesNotMatch(RENDER, /tab-gearbox|gearBox/, "no box around the gear any more");
  assert.doesNotMatch(RENDER, /\n  bar\.appendChild\(tagBox\);/, "the tag box no longer sits after the + tab on its own");
  assert.match(RENDER, /const settingsReachable = !!\(\(window as any\)\.__rompShowStrip \|\| inRompShell\(\)\);/, "the gear is everywhere the strip is; only its Tab widgets row asks whether a settings gear can be reached");
  // the wrapper: the auto margin pushes it right; the + tab's height as its floor, so a controls-only wrapped line stands as tall
  const end = CSS.match(/\n\.tab-strip-end \{[^}]*\}/)![0];
  assert.match(end, /margin-left: auto;/); assert.match(end, /min-height: 31px;/);
  assert.doesNotMatch(end, /border|background/, "nothing visible on the wrapper");
  assert.match(CSS, /\nbody\.dense-chrome \.tab-strip-end \{ min-height: 25px; \}/, "dense follows");
  assert.doesNotMatch(CSS, /\.tab-gearbox/, "the gear box's rules are gone");
  // the gear: the rail action's dress, value for value, read from the kernel's own rules so the two cannot drift
  const railAct = KERNEL.match(/"\.rail-act\{([^"]*)"\s*\n\s*"([^"]*)\}"/);
  assert.ok(railAct, "the kernel's .rail-act rule located");
  const rail = railAct![1] + railAct![2];
  const railColor = rail.match(/color:(#[0-9a-f]+)/i)![1], railRadius = rail.match(/border-radius:(\d+px)/)![1], railPad = rail.match(/padding:([^;]+);/)![1], railMargin = rail.match(/margin:([^;]+);/)![1];
  const railActive = KERNEL.match(/"\.rail-act:active\{transform:(scale\([0-9.]+\))\}"/)![1];
  const railSize = KERNEL.match(/"#rail-gear\{font-size:(\d+px)\}"/)![1];
  const railHover = KERNEL.match(/"\.rail-act:hover\{color:(#[0-9a-f]+);background:(rgba\([^)]*\))\}"/i)!;
  const railLight = KERNEL.match(/"body\.theme-light \.rail-act\{color:(#[0-9A-Fa-f]+)\}"/)!, railLightHover = KERNEL.match(/"body\.theme-light \.rail-act:hover\{color:(#[0-9A-Fa-f]+);background:(rgba\([^)]*\))\}"/)!;
  const gear = CSS.match(/\n\.tab-widgets-gear \{[^}]*\}/)![0];
  assert.match(gear, new RegExp("font-size: " + railSize + ";"), "the rail gear's glyph size");
  assert.match(gear, /line-height: 1;/); assert.match(gear, new RegExp("padding: " + railPad.replace(/(\d+)px/g, "$1px").replace(" ", " ") + ";"), "the rail action's padding");
  assert.match(gear, /border: 0;/); assert.match(gear, /background: transparent;/); assert.match(gear, new RegExp("border-radius: " + railRadius + ";"));
  assert.match(gear, new RegExp("margin: " + railMargin + ";"), "the rail action's margin, 4px from its bar's end (round two, low 1)");
  assert.match(CSS, new RegExp("\\n\\.tab-widgets-gear:active \\{ transform: " + railActive.replace(/[()]/g, "\\$&") + "; \\}"), "the rail action's press");
  assert.match(gear, new RegExp("color: " + railColor + ";"), "the rail action's rest colour, the same literal");
  assert.doesNotMatch(gear, /var\(--card-border\)|var\(--dim\)/, "no card border, no dim token: the rail's own values");
  const hover = CSS.match(/\n\.tab-widgets-gear:hover \{[^}]*\}/)![0];
  assert.match(hover, new RegExp("color: " + railHover[1] + ";")); assert.match(hover, new RegExp("background: " + railHover[2].replace(/[()]/g, "\\$&").replace(/,/g, ", ?") + ";"), "the rail's hover wash");
  assert.doesNotMatch(hover, /border|accent/, "no accent border on hover: the rail's hover has none");
  // the light theme: the rail's light colours are the chat's own light tokens (--dim and --fg carry those two values), so the overrides use the tokens
  const light = CSS.match(/\nbody\.theme-light \.tab-widgets-gear \{[^}]*\}/)![0], lightHover = CSS.match(/\nbody\.theme-light \.tab-widgets-gear:hover \{[^}]*\}/)![0];
  const lightBlock = CSS.match(/\nbody\.theme-light \{[\s\S]*?\n\}/)![0];
  assert.equal(lightBlock.match(/--dim: (#[0-9A-Fa-f]+);/)![1].toLowerCase(), railLight[1].toLowerCase(), "the light rest colour is the light --dim value");
  assert.equal(lightBlock.match(/--fg: (#[0-9A-Fa-f]+);/)![1].toLowerCase(), railLightHover[1].toLowerCase(), "the light hover colour is the light --fg value");
  assert.match(light, /color: var\(--dim\);/); assert.match(lightHover, /color: var\(--fg\);/);
  assert.match(lightHover, new RegExp("background: " + railLightHover[2].replace(/[()]/g, "\\$&").replace(/,/g, ", ?") + ";"));
  // dense: the 19px glyph inside the 25px row by the padding alone (19 + 3 + 3), no border to count
  assert.match(CSS, /\nbody\.dense-chrome \.tab-widgets-gear \{ margin: 0 4px; padding: 3px 0; \}/, "dense restates the margin: the rail's 1px above and below would carry the box past the 25px row; dense-chrome-layout.test.ts measures it");
  assert.doesNotMatch(CSS, /\.tab-lockbox|\n\.tab-lock \{|\n\.tab-lock\.on \{/, "the lock button's rules are gone");
});

// the rows menu, executed over a stub document (the tag-menu tests' harness): rows, the ✓, a switch keeps the menu and
// repaints, an action closes it, Enter presses, Escape closes and hands the focus back
type Node = { tag: string; attrs: Record<string, string>; kids: Node[]; style: Record<string, string>; handlers: Record<string, (e?: any) => void>;
              dataset: Record<string, string>; offsetWidth: number; offsetHeight: number; textContent: string; innerHTML?: string; tabIndex?: number; title?: string;
              parent?: Node | null; removed?: boolean; focused?: boolean; text?: string;
              setAttribute(k: string, v: string): void; getAttribute(k: string): string | null; appendChild(c: Node): void; addEventListener(k: string, fn: (e?: any) => void): void;
              remove(): void; focus(): void; getBoundingClientRect(): { left: number; right: number; top: number; bottom: number }; children: Node[] };
function harness() {
  let focused: Node | null = null;
  const mk = (tag: string): Node => {
    const n: any = { tag, attrs: {}, kids: [], style: {}, handlers: {}, dataset: {}, offsetWidth: 200, offsetHeight: 100, parent: null,
      get textContent() { return this.kids.map((k: any) => k.tag === "#text" ? k.text || "" : k.textContent).join(""); },
      set textContent(v: string) { this.kids = v ? [{ tag: "#text", text: v }] : []; },
      get children() { return this.kids; },
      setAttribute(k: string, v: string) { this.attrs[k] = v; }, getAttribute(k: string) { return k in this.attrs ? this.attrs[k] : null; },
      appendChild(c: any) { c.parent = this; this.kids.push(c); }, addEventListener(k: string, fn: any) { this.handlers[k] = fn; },
      remove() { this.removed = true; if (this.parent) this.parent.kids = this.parent.kids.filter((k: any) => k !== this); },
      focus() { focused = this; }, getBoundingClientRect() { return { left: 10, right: 40, top: 10, bottom: 30 }; } };
    return n;
  };
  const g = globalThis as any;
  const saved = { document: g.document, window: g.window, localStorage: g.localStorage };
  const body = mk("body");
  g.document = { createElement: mk, createTextNode: (t: string) => ({ tag: "#text", text: t }), body, addEventListener() { /* closers */ } };
  g.window = { addEventListener() { /* storage */ }, innerWidth: 1200, innerHeight: 800 };
  g.localStorage = { setItem() { /* echo */ } };
  const restore = () => { g.document = saved.document; g.window = saved.window; g.localStorage = saved.localStorage; };
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const mod = require("./tag-menu");
  return { mk, body, mod, focused: () => focused, restore };
}
const label = (n: Node): string => n.kids.map((k) => k.tag === "#text" ? (k.text || "") : label(k)).join("");

test("the rows-menu helper is gone with its one caller (T415): the tag menu's card and ✓ grammar stay for the tags menu", () => {
  assert.doesNotMatch(TAGMENU, /openRowsMenu|RowsMenuRow|rowsMenu/, "no rows menu in the menu module");
  assert.match(TAGMENU, /background:var\(--check-bg, #1EA1EB\)/, "the ✓ badge serves the tags menu");
});

test("the ✓ badge is stated once in tag-menu.ts: checkMark draws it for every row that is current (T413)", () => {
  assert.equal((TAGMENU.match(/background:var\(--check-bg, #1EA1EB\);color:#fff;/g) || []).length, 1, "one builder for the mark");
});

test("the gear's title and label name the settings, and the gear is drawn only where a settings card can open (T415)", () => {
  assert.match(RENDER, /if \(settingsReachable\) \{\s*\n\s*const gear = el\("button", "tab-widgets-gear"\) as HTMLButtonElement;/);
  assert.match(RENDER, /gear\.title = "Tab strip settings";/);
  assert.doesNotMatch(RENDER, /Tab strip: lock/, "the old titles are gone");
});
