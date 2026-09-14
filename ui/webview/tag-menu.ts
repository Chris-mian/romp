// The SHARED tag-lens menu (the user 2026-08-25): one component every webview surface mounts —
// the outline pane, the chat tab strip, the feed's local filter. (The timeline inlines its OWN copy
// of this menu in MENU_STYLE, since it may live in Obsidian's document and loads no modules; since
// T283b that copy builds the same chip rows from its palette's RESOLVED values — tagRow / TAG_CHIP_STYLE in
// ui/romp-timeline-view.js — and ui/timeline-tag-chips.test.ts pins the drift between the two.) The menu is
// multi-select toggles on ONE surface's lens: All a plain exclusive pick, (no tags) toggling with
// the ✓ when selected, and every name-keyed union tag as ITS OWN CHIP acting as a toggle button
// (the user 2026-09-09, T283: the pill every surface already wears, one tag per line with the chip
// at the left as the group-by-tag strip settled it; selected = full colour, unselected = faded, no
// colour change, aria-pressed on the chip) — the menu staying open across toggles (a settings
// panel, not a command). A CAPTIONED DIVIDER says which surface the selection governs
// ("filters these tabs") — the shared idiom, sub-line scale. One management entry, "Configure
// tags…", when the surface offers a route to the dialog.
//
// CROSS-PANE DISMISSAL is built in (the user's bug): sibling panes' pointer events never reach
// this document, so every pane WRITES a pointerdown echo (romp:menu-echo — the color-echo idiom)
// and every open menu LISTENS via the storage event, which fires only in OTHER same-origin panes:
// exactly the gap the local document closers can't cover. Mounting surfaces inherit the fix free.
//
// SUBMENU-LESS by design today; the caret/side rule for menus that DO expand lives with the
// model-version submenus: carets always face right (▸), expansion prefers the right side and
// falls left only when the right edge would clip (measured, never assumed).
import { TagUnion } from "./session-views";
import { TagLens, lensAll, toggleLens, lensChips } from "./tag-lens";

export interface TagMenuOpts {
  lens: () => TagLens;                       // the surface's current selection (re-read per repaint)
  unions: () => TagUnion[];                  // the name-keyed union rows (re-read per repaint)
  onApply: (l: TagLens, done: boolean) => void;  // done=true → the pick closes the menu (All)
  onConfigure?: () => void;                  // the one management entry, when the surface has a route
  /** a per-surface switch at the foot beside Configure tags… (the chat strip's "Group tabs by tag",
   *  tab groups 2026-09-04): ✓-marked when on; flips and repaints in place like the tag rows */
  groupToggle?: { label: string; on: () => boolean; toggle: () => void };
}

let echoInstalled = false;
/** Every pane writes the pointerdown echo ONCE per document — sibling panes' open menus close on it.
 *  Installed AT MODULE LOAD by the guard below, never lazily (the user 2026-08-26: a menu opened
 *  from the sessions panel stood through clicks in the chat — the chat imports this module but had
 *  never opened a menu, so its document held no writer). Exported for documents that mount no tag
 *  menu at all (the shell page's palette-main) to compose the same writer explicitly. */
export function installMenuEcho(): void {
  if (echoInstalled) return;
  echoInstalled = true;
  document.addEventListener("pointerdown", (e) => {
    // A press INSIDE a romp menu is interaction WITH that menu, never a click-away — broadcasting
    // it closes the very menu being used. The case that found this (T213, 2026-09-01): the
    // timeline lifts its menus into the SHELL document (same-origin top), so a tag-row press
    // landed there, the shell's copy of this writer echoed it, and the storage event bounced into
    // the timeline iframe, whose listener detached the row between its pointerdown and its click.
    // A human-length press (~100ms) always lost that race — the sessions pane's tag filter read
    // as dead — while an instant synthetic click still won it. The echo exists for presses on
    // pane CONTENT; menus mark themselves (data-tag-menu here, data-romp-menu in the timeline's
    // inlined mirror) and are skipped.
    const t = e.target as Element | null;
    if (t && typeof t.closest === "function" && t.closest("[data-tag-menu],[data-romp-menu]")) return;
    try { localStorage.setItem("romp:menu-echo", JSON.stringify({ t: Date.now() })); } catch { /* storage blocked */ }
  }, true);
}

let openMenu: HTMLElement | null = null;
export function closeTagMenu(): void {
  const m = openMenu;
  openMenu = null;   // cleared BEFORE the removal: removing a menu with a focused row fires focusout, whose closer must find nothing left to close (round two of the strip tidy)
  m?.remove();
}
// module-level closers, guarded: the model half of this module (and its constants) is importable
// from non-DOM contexts (the node test runner) — only a real document wires the listeners
if (typeof document !== "undefined") {
  installMenuEcho();   // the WRITER rides every bundle at load — a pane must broadcast before it ever opens a menu
  document.addEventListener("click", () => closeTagMenu());
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeTagMenu(); });
  try {
    window.addEventListener("storage", (e) => { if (e.key === "romp:menu-echo" && e.newValue) closeTagMenu(); });
  } catch { /* no storage events (foreign host) — local closers still apply */ }
}

/** Open (or toggle shut) the lens menu anchored under `anchor`. The ctx-family skin — the chat
 *  pane's .ctx-menu is the reference spec (CLAUDE.md menu vocabulary), worn here through the menu
 *  TOKENS (--menu-bg/--menu-fg/--menu-border/--menu-hover + --radius-menu/--shadow-menu/--check-bg)
 *  with the dark literals as var() fallbacks — every mounting page loads styles.css or feed.css,
 *  so the light theme's block re-skins the card (T226, 2026-09-02). */
export function openTagMenu(anchor: HTMLElement, opts: TagMenuOpts): void {
  const reopen = !!openMenu && openMenu.dataset.tagMenu === "1";
  closeTagMenu();
  if (reopen) return;
  const menu = document.createElement("div");
  menu.setAttribute("role", "menu");
  menu.dataset.tagMenu = "1";
  menu.setAttribute("style",
    "position:fixed;z-index:1001;min-width:180px;padding:4px;background:var(--menu-bg, #252526);" +
    "border:1px solid var(--menu-border, rgba(255,255,255,0.12));border-radius:var(--radius-menu, 6px);box-shadow:var(--shadow-menu, 0 4px 12px rgba(0,0,0,0.35));" +
    "font-size:12px;line-height:1.4;color:var(--menu-fg, #cccccc);user-select:none;");
  menu.addEventListener("click", (e) => e.stopPropagation());
  const rebuilding = { on: false };   // a toggle's repaint removes the focused row, and Chromium fires focusout for it: the closer stands down meanwhile
  menuKeys(menu, anchor, rebuilding);   // the house rows grammar (T413 round two): Escape back to the button, the arrows walking the rows, Tab out closing
  const build = () => {
    const focusAt = Array.prototype.indexOf.call(menu.children, document.activeElement);   // the focused row's place, kept across the repaint a toggle causes
    rebuilding.on = true;
    menu.textContent = "";
    const lens = opts.lens();
    // (the scope caption retired 2026-08-25 — the user: the button tooltip already names the
    // surface, so it is the ONE scope carrier and the menu opens straight onto its rows)
    // a plain row (All, (no tags), the group switch, Configure tags…): the label, the ✓ when current; the
    // tags are not rows any more but chips (below), so the colour dot the tag rows wore is gone (T283)
    // a plain row (All, the group switch, Configure tags…): the label, the ✓ when current; `checkbox` makes it the house switch
    // (role menuitemcheckbox, aria-checked, the two-state mark), which (no tags), a selection member, is
    const row = (label: string, current: boolean, dim?: boolean, checkbox?: boolean) => {
      const r = document.createElement("div");
      r.setAttribute("style", "padding:4px 22px 4px 8px;border-radius:4px;cursor:pointer;position:relative;white-space:nowrap;outline:none;"
        + (dim ? "opacity:0.85;" : ""));
      r.appendChild(document.createTextNode(label));
      if (checkbox) { r.setAttribute("role", "menuitemcheckbox"); r.setAttribute("aria-checked", current ? "true" : "false"); r.appendChild(checkMark(current)); }
      else { r.setAttribute("role", "menuitem"); if (current) r.appendChild(checkMark(true)); }
      r.addEventListener("mouseenter", () => { r.style.background = "var(--menu-hover, rgba(255,255,255,0.09))"; });
      r.addEventListener("mouseleave", () => { r.style.background = "transparent"; });
      focusableRow(r);
      menu.appendChild(r);
      return r;
    };
    row("All", lensAll(lens)).addEventListener("click", () => opts.onApply({ all: true }, true));
    row("(no tags)", !lensAll(lens) && !!lens.none, false, true)
      .addEventListener("click", () => { opts.onApply(toggleLens(lens, "none"), false); build(); });
    for (const u of opts.unions()) {
      // one tag per line, the chip at the left, lit when selected and faded when not (the same pill tagChip builds for every
      // other surface); the ROW is the control, the house switch with the two-state mark at its right (T413, the user
      // 2026-09-14: a checkbox beside each tag, the lit state kept), so a reader hears one checkbox per tag
      const on = !lensAll(lens) && (lens.tags || []).includes(u.name);
      const r = document.createElement("div");
      r.setAttribute("style", "padding:3px 22px 3px 8px;border-radius:4px;cursor:pointer;white-space:nowrap;display:flex;align-items:center;position:relative;outline:none;");
      r.setAttribute("role", "menuitemcheckbox");
      r.setAttribute("aria-checked", on ? "true" : "false");
      r.setAttribute("title", on ? "selected: click to drop it from the filter" : "click to add it to the filter");
      const chip = tagChip(u.name, u.color || null, { off: !on });
      r.appendChild(chip);
      r.appendChild(checkMark(on));
      r.addEventListener("mouseenter", () => { r.style.background = "var(--menu-hover, rgba(255,255,255,0.09))"; });
      r.addEventListener("mouseleave", () => { r.style.background = "transparent"; });
      r.addEventListener("click", () => { opts.onApply(toggleLens(lens, { tag: u.name }), false); build(); });
      focusableRow(r);
      menu.appendChild(r);
    }
    if (opts.groupToggle || opts.onConfigure) {
      const s = document.createElement("div");
      s.setAttribute("style", "height:1px;margin:4px 6px;background:var(--menu-border, rgba(255,255,255,0.12));");
      menu.appendChild(s);
    }
    if (opts.groupToggle)
      row(opts.groupToggle.label, opts.groupToggle.on(), true, true).addEventListener("click", () => { opts.groupToggle!.toggle(); build(); });   // a switch: the checkbox row with its state (the strip tidy after T413 round two)
    if (opts.onConfigure)
      row("Configure tags…", false, true).addEventListener("click", () => { closeTagMenu(); opts.onConfigure!(); });
    const back = menu.children[focusAt] as HTMLElement | undefined;   // the same place after the repaint: the rows rebuild in one order
    if (back && back.getAttribute("role")) back.focus();
    else { const first = menuRows(menu)[0]; if (first) first.tabIndex = 0; }   // no focus in the menu: the first row is the one tab stop
    rebuilding.on = false;
  };
  build();
  document.body.appendChild(menu);
  const r = anchor.getBoundingClientRect();
  const mw = menu.offsetWidth || 200;
  menu.style.left = Math.max(6, Math.min(Math.round(r.left), window.innerWidth - mw - 8)) + "px";
  // the many-tags case (T413; the rule of 2026-09-09): dozens of tags make a menu taller than the room, and one placed over its
  // own button took the release, so the click, fired at the common ancestor, closed it. The menu opens BELOW the button and caps
  // its height to the room there (above only when there is more room above), scrolling within itself; it never covers the button.
  const mh = menu.offsetHeight || 0;
  const below = window.innerHeight - 8 - (r.bottom + 4), above = r.top - 4 - 8;
  if (mh <= below || below >= above) { menu.style.top = Math.round(r.bottom + 4) + "px"; menu.style.maxHeight = Math.max(120, Math.floor(below)) + "px"; }
  else { const h = Math.min(mh, Math.max(120, Math.floor(above))); menu.style.top = Math.max(8, Math.round(r.top) - h - 4) + "px"; menu.style.maxHeight = h + "px"; }
  menu.style.overflowY = "auto";
  // the focus moves to the first row on a KEYBOARD open only, when the button held it (Enter, Space or ArrowDown on the focused button);
  // a pointer open leaves the focus where it was, the composer's (round one's rule, back after round two moved it): the press prevents
  // the button's own focus, so the button never holds it then. Either way the first row is the menu's one tab stop (the strip tidy).
  if ((anchor.ownerDocument || document).activeElement === anchor) menuRows(menu)[0]?.focus();   // the anchor's own document: the one whose focus the button can hold
  openMenu = menu;
}

/** The bounded run for a many-tags selection (T413): the first `limit` items and how many follow; 0 = no limit. */
export function chipRun<T>(items: T[], limit: number): { shown: T[]; more: number } {
  if (!limit || items.length <= limit) return { shown: items.slice(), more: 0 };
  return { shown: items.slice(0, limit), more: items.length - limit };
}

/** The menus' mark, stated once (the tag menu and the rows menu): the house ✓-in-circle from --check-bg when on; off, an empty
 *  ring in the menu's hairline, so a CHECKBOX row reads in both states (T413, the user 2026-09-14). An exclusive pick (All) or
 *  an action row shows the ✓ alone when current and nothing otherwise. `data-check` carries the state for a reader of the DOM. */
export function checkMark(on: boolean): HTMLElement {
  const c = document.createElement("span");
  c.setAttribute("data-check", on ? "true" : "false");
  c.setAttribute("aria-hidden", "true");   // decoration: the row's name is its label and its state is aria-checked, never the glyph (the strip tidy, round two)
  c.textContent = on ? "✓" : "";
  c.setAttribute("style", "position:absolute;right:6px;top:50%;transform:translateY(-50%);width:13px;height:13px;border-radius:50%;box-sizing:border-box;"
    + "display:inline-flex;align-items:center;justify-content:center;line-height:1;font-size:9px;font-weight:900;"
    + (on ? "background:var(--check-bg, #1EA1EB);color:#fff;" : "border:1px solid var(--text-muted, #9aa0a6);background:transparent;"));   // off: the muted text, 3 to 1 against the menu ground in both themes (the hairline read at 1.5, round two low 1)
  return c;
}

/** The element a closing menu hands the focus to: `anchor` while it is in the document, else its live replacement (a press may
 *  rebuild the anchor's host: the strip re-renders on a lens change), found by id, else by tag and classes among the VISIBLE
 *  matches (the phone header mounts a hidden twin of the strip's tags button), else null (a detached focus() would drop it on the body). */
function liveAnchorOf(anchor: HTMLElement): HTMLElement | null {
  if (anchor.isConnected !== false) return anchor;
  if (anchor.id) return document.getElementById(anchor.id);
  const cls = String(anchor.className || "").split(/\s+/).filter(Boolean).map((c) => "." + c).join("");
  if (!cls) return null;
  const all = Array.from(document.querySelectorAll(anchor.tagName.toLowerCase() + cls)) as HTMLElement[];
  return all.find((x) => x.getClientRects().length > 0) || all[0] || null;
}
/** the menu's rows: its children that carry a role (the separator carries none) */
function menuRows(menu: HTMLElement): HTMLElement[] { return (Array.from(menu.children) as HTMLElement[]).filter((c) => !!c.getAttribute("role")); }
/** The house rows grammar for a menu's keys (T405's rows menu; the tags menu since T413 round two): Escape closes the menu and hands
 *  the focus back to the anchor; ArrowDown and ArrowUp walk the rows, Home and End jump to the ends, neither end wraps. */
function menuKeys(menu: HTMLElement, anchor: HTMLElement, rebuilding: { on: boolean }): void {
  // Tab (or Shift+Tab) out of the menu closes it, the one-tab-stop pattern's other half (round two of the tidy: the menu stood open with
  // the focus on the body); a focus moving between the rows keeps it, a focus leaving the WINDOW (relatedTarget null, the document no
  // longer focused) is not a Tab and keeps it too, and the repaint a toggle causes (the focused row removed and rebuilt) is masked
  menu.addEventListener("focusout", (e) => {
    if (rebuilding.on) return;
    const to = (e as FocusEvent).relatedTarget as Node | null;
    if (to && menu.contains(to)) return;
    if (!to && typeof document.hasFocus === "function" && !document.hasFocus()) return;
    if (openMenu === menu) closeTagMenu();
  });
  menu.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.stopPropagation(); closeTagMenu(); liveAnchorOf(anchor)?.focus(); return; }
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp" && e.key !== "Home" && e.key !== "End") return;
    const rows = menuRows(menu);
    if (!rows.length) return;
    e.preventDefault(); e.stopPropagation();
    const at = rows.indexOf(document.activeElement as HTMLElement);
    const to = e.key === "Home" ? 0 : e.key === "End" ? rows.length - 1 : e.key === "ArrowDown" ? Math.min(rows.length - 1, at + 1) : Math.max(0, at - 1);
    rows[to].focus();
  });
}
/** A row that takes the focus and the keys (the same grammar): the hover wash while focused, Enter and Space pressing it as a click
 *  would (the row's click listeners are the press). ONE TAB STOP (the ARIA menu pattern, the strip tidy after T413 round two): every
 *  row starts at tabindex -1 and the focused row alone holds 0, roving with the focus (an arrow's or a click's), so Tab leaves the menu
 *  instead of walking its thirty-odd rows; the arrows walk them. */
function focusableRow(r: HTMLElement): void {
  r.tabIndex = -1;
  r.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); r.click(); } });
  r.addEventListener("focus", () => {
    r.style.background = "var(--menu-hover, rgba(255,255,255,0.09))";
    if (r.parentElement) for (const x of menuRows(r.parentElement)) x.tabIndex = x === r ? 0 : -1;   // the tab stop follows the focus
  });
  r.addEventListener("blur", () => { r.style.background = "transparent"; });
}

/** The shared tag-icon button (the user chose a tag glyph): identical across surfaces. It wears
 * THE BUTTON OUTLINE (the user 2026-08-25, round two: the bare glyph read weird next to the feed's
 * dressed buttons) — the feed word-button's box, stated in the same literals the feed's classes
 * resolve to (--card-border, 6px radius, the #feed-foot 1px 9px padding), so a chat/outline mount
 * computes equal to the feed instance by value, not by shared class (the 678 lesson). */
export function tagMenuButton(title: string, open: (btn: HTMLElement) => void): HTMLElement {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.title = title;
  btn.setAttribute("style", "background:transparent;border:1px solid " + TAG_BTN_BORDER_CSS + ";"
    + "border-radius:6px;padding:4px 6px;cursor:pointer;color:#9aa0a6;display:inline-flex;align-items:center;");
  btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 16 16" fill="none">'
    + '<path d="M2 7.5 L7.5 2.5 H14 V9 L8.5 14 Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>'
    + '<circle cx="11" cy="5.5" r="1.2" fill="currentColor"/></svg>';
  btn.setAttribute("aria-haspopup", "menu");
  btn.addEventListener("pointerdown", (e) => { e.preventDefault(); e.stopPropagation(); open(btn); });
  btn.addEventListener("click", (e) => e.stopPropagation());   // the click-and-hold rule: swallow the opener's own click
  // the keyboard's open (T413 round two): the press opens on the pointer and swallows its click, so Enter on the focused button did
  // nothing at all; Enter, Space and ArrowDown open it (the menu-button grammar), and the menu's first row takes the focus
  btn.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " " || e.key === "ArrowDown") { e.preventDefault(); e.stopPropagation(); open(btn); } });
  return btn;
}

// THE BUTTON CONVENTION (the user 2026-08-25): at rest (All) the tag icon is GRAY and stands
// alone; narrowed, it wears the ACCENT and the chips of everything selected render beside it —
// each tag in its color, the no-tags bucket as its own chip, a dim ✕ per chip unselecting that
// one pick. One renderer, so every mount is identical by construction; the feed's footer keeps
// its class mechanics (mode: "class" — its .on/.--dim values are pinned equal to these literals).
export const TAG_BTN_GRAY = "#9aa0a6";
export const TAG_BTN_ACCENT = "#9cd2ff";   // the romp accent (--accent) — pinned equal in feed.css/styles.css
export const TAG_BTN_BORDER = "rgba(255,255,255,0.10)";   // the feed's --card-border, stated by value (the dark theme's)
// THE BORDER BOTH BOXES READ (the tab lock's review, 2026-09-13): the themed token every sheet defines per theme (--card-border,
// styles.css and feed.css, dark and light), with the dark literal as the fallback a sheet-less host resolves to. Stated once here:
// the tag button paints it inline, the chat strip's padlock reads it through its own property, so the two boxes match in every theme
// (on the cream theme the bare literal fell to a 3 of 255 edge on both).
export const TAG_BTN_BORDER_CSS = "var(--card-border, " + TAG_BTN_BORDER + ")";
export const TAG_BTN_WASH = "rgba(156,210,255,0.12)";     // the feed .on's faint accent wash, ditto

/** THE TAG CHIP (one vocabulary, T251 — the user 2026-09-07: a group header must show its tag the way
 *  the tag is shown everywhere else): the outline pill in the tag's own colour, the shape the strip's
 *  tags bar and the feed's tag chips wear. `inheritSize` drops the pill's own 0.82em for a host that
 *  already sits at the surface's sub-line size (the group header), so no em nests inside an em (the
 *  fonts rule). The uncoloured fallback is the theme's --dim (a token, so the light theme is never
 *  handed a dark gray), with the constant as the file:// fallback.
 *  `off` is the FADED state (T283): a chip standing for an unselected toggle keeps its colour and fades
 *  to TAG_CHIP_OFF_OPACITY — the class names the state for the sheets and the pins, the inline opacity
 *  paints it on a sheet-less host, the two equal by construction. */
export const TAG_CHIP_OFF_CLASS = "tag-chip-off";
export const TAG_CHIP_OFF_OPACITY = "0.45";   // pinned equal to .tag-chip-off in styles.css / feed.css
/** THE ONE TAG CHIP (T321, the user 2026-09-10: tags render the same everywhere, and never in bold, which is the
 *  session names' weight). Every surface that shows a tag builds it here: the tab strip's group rows and its filter
 *  chips, the feed's and the outline's filter chips, the tag-lens menu's rows, the tab menu's Tags flyout, the feed's
 *  session dialog, the new-session picker's Tags row; the two documents that load no module, the landing page's spend
 *  panel (kernel.py spTagChip) and the Obsidian timeline view, inline the same bytes under drift pins. The standard: a
 *  thin 1px border and the text in the tag's own
 *  colour on a transparent ground, weight 400 and normal tracking (inline, so a bold or letter-spaced host cannot
 *  restyle it), one size per context (the chip's own 0.82em, or the host's with `inheritSize` where a row sizes it),
 *  and off = the faded chip (`off`: TAG_CHIP_OFF_CLASS at TAG_CHIP_OFF_OPACITY). A host adds layout (flex, margins)
 *  and state cues the chip never sets inline (a filter, an underline), never a weight, size, border or colour. */
export function tagChip(label: string, color?: string | null, opts?: { inheritSize?: boolean; off?: boolean }): HTMLElement {
  const col = color || ("var(--dim, " + TAG_BTN_GRAY + ")");
  const chip = document.createElement("span");
  chip.setAttribute("style", "display:inline-flex;align-items:center;gap:5px;padding:2px 7px;"
    + "border-radius:9px;" + (opts && opts.inheritSize ? "" : "font-size:0.82em;")
    + "border:1px solid " + col + ";color:" + col + ";background:transparent;white-space:nowrap;"
    + "font-weight:400;letter-spacing:normal;"
    + (opts && opts.off ? "opacity:" + TAG_CHIP_OFF_OPACITY + ";" : ""));
  if (opts && opts.off) chip.setAttribute("class", TAG_CHIP_OFF_CLASS);
  chip.appendChild(document.createTextNode(label));
  return chip;
}

export function syncTagFilter(btn: HTMLElement, chipsHost: HTMLElement | null,
                              lens: TagLens, unions: { name: string; color?: string | null; members: string[]; }[],
                              onApply: (l: TagLens) => void,
                              mode: "inline" | "class" = "inline",
                              opts?: { limit?: number; tagsOnly?: boolean }): void {   // T413, the strip: the first `limit` chips then one "+N more"; tagsOnly draws no chip for the none pick
  const narrowed = !lensAll(lens);
  if (mode === "class") btn.classList.toggle("on", narrowed);
  else {
    // inline mode mirrors the feed's .on by VALUE: accent glyph + accent border + the faint wash
    btn.style.color = narrowed ? TAG_BTN_ACCENT : TAG_BTN_GRAY;
    btn.style.borderColor = narrowed ? TAG_BTN_ACCENT : TAG_BTN_BORDER_CSS;
    btn.style.background = narrowed ? TAG_BTN_WASH : "transparent";
  }
  btn.setAttribute("aria-pressed", narrowed ? "true" : "false");
  if (!chipsHost) return;   // the button's state alone (the strip in group mode: the headings carry the tags): nothing built, nothing to drop
  chipsHost.textContent = "";
  const all = lensChips(lens, unions as never).filter((c) => !(opts && opts.tagsOnly && c.pick === "none"));
  const run = chipRun(all, (opts && opts.limit) || 0);
  for (const c of run.shown) {
    const chip = tagChip(c.label, c.color);
    const x = document.createElement("span");
    x.textContent = "✕";
    x.setAttribute("style", "cursor:pointer;opacity:0.75;color:" + TAG_BTN_GRAY + ";font-size:0.9em;");
    x.title = "remove this from the filter";
    x.addEventListener("click", (e) => { e.stopPropagation(); onApply(toggleLens(lens, c.pick)); });
    chip.appendChild(x);
    chipsHost.appendChild(chip);
  }
  if (run.more) {
    // the rest as one count in the user's terms, the plain chip (no colour: the dim), its title naming them; a press opens the
    // menu through the button, which opens on the pointer's press (its click is swallowed), so the press is what is dispatched
    const more = tagChip("+" + run.more + " more", null);
    more.setAttribute("class", "tag-chip-more");
    more.title = all.slice(run.shown.length).map((c) => c.label).join(", ");
    more.addEventListener("click", (e) => { e.stopPropagation(); if (typeof PointerEvent === "function") btn.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true, cancelable: true })); else (btn as HTMLButtonElement).click(); });
    chipsHost.appendChild(more);
  }
}

