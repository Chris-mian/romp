// One context menu for the panes that had none (the Sessions pane first; the user 2026-09-16, who wanted a right-click
// on a session's row to rename or delete it). The card and its rows are the chat's `.ctx-menu` and `.ctx-item` dress,
// which every romp menu wears through the theme tokens styles.css defines (ui/CLAUDE.md: one menu vocabulary), so a pane
// that loads that sheet needs no rule of its own. The menu is placed inside the viewport, dismissed on a press outside
// it, Escape, any scroll or the window's blur, and reachable from the keyboard (arrows and Home/End move, Enter or Space
// picks, Escape closes). Every romp menu opens through it since v0.16.0's tidy: the chat's tab and selection menus,
// the feed's card menu and the file browser's row menu (each built the same rows by hand before, with its own
// dismissal listeners and no keyboard). A menu with rows the standard shape cannot express (the tab menu's colour
// swatches and its flyouts) builds the card with menuCard(), appends its own nodes beside addMenuItem() rows, and
// shows it with showMenuCard(): the placement, the dismissal, the keyboard and the focus return are one code path.
//
// The confirm box beside it is the chat's confirm dialog (`showConfirm` in render.ts) in the same classes, for a pane
// that has to ask before it acts: the Sessions pane's Delete asks with the strip's own title, detail and buttons.

export interface CtxItem {
  label: string;
  sub?: string;            // the quiet second line under the label
  danger?: boolean;        // a destructive row: the label in the error colour
  icon?: HTMLElement | null;   // a drawn icon before the body (the tab menu's toggles, the card menu's bell)
  className?: string;      // extra classes on the row, for a caller's own rule or pin
  title?: string;
  pick: () => void;        // runs after the menu has closed
}
export interface CtxMenuOpts {
  className?: string;      // extra classes on the card
  id?: string;             // the card's id, for a sheet or a pin that addresses it (the file browser's #fb-ctx)
  viaKeyboard?: boolean;   // opened from the keyboard: the first row takes the focus, so arrows move at once
  onClose?: () => void;    // after the card is gone and the focus returned
}

const MARGIN = 4;

/** Where a card of `w` by `h` opens for a pointer at (`x`, `y`) inside a `vw` by `vh` viewport: to the right and below
 *  the pointer when it fits, flipped to the left or above when it does not, and never past the viewport's edge. */
export function placeMenu(x: number, y: number, w: number, h: number, vw: number, vh: number): { left: number; top: number } {
  let left = x, top = y;
  if (left + w + MARGIN > vw) left = Math.max(MARGIN, x - w);
  if (top + h + MARGIN > vh) top = Math.max(MARGIN, y - h);
  return { left: Math.max(MARGIN, Math.min(left, vw - w - MARGIN)), top: Math.max(MARGIN, Math.min(top, vh - h - MARGIN)) };
}

let openMenu: HTMLElement | null = null;
let teardown: (() => void) | null = null;

/** The open context menu's card, or null: a caller's gate (the chat holds its typing shortcuts while a menu is up). */
export function contextMenuOpen(): HTMLElement | null { return openMenu; }

/** Close the open context menu, if any. */
export function closeContextMenu(): void {
  if (teardown) { const t = teardown; teardown = null; t(); }
  if (openMenu) { openMenu.remove(); openMenu = null; }
}

/** A detached card in the menu dress, for a caller that appends its own rows before showMenuCard() places it. */
export function menuCard(opts: CtxMenuOpts = {}): HTMLElement {
  const menu = document.createElement("div");
  menu.className = "ctx-menu" + (opts.className ? " " + opts.className : "");
  if (opts.id) menu.id = opts.id;
  menu.setAttribute("role", "menu");
  menu.tabIndex = -1;
  return menu;
}

/** The standard row, appended to `menu`: icon, label and sub-line in the chat's `.ctx-item` classes; a click closes
 *  the menu and runs the pick. */
export function addMenuItem(menu: HTMLElement, it: CtxItem): HTMLElement {
  const row = document.createElement("div");
  row.className = "ctx-item ctx-item-toggle" + (it.danger ? " ctx-item-danger" : "") + (it.className ? " " + it.className : "");
  row.setAttribute("role", "menuitem");
  row.tabIndex = -1;
  if (it.title) row.title = it.title;
  if (it.icon) row.appendChild(it.icon);
  const body = document.createElement("span"); body.className = "ctx-item-body";
  const label = document.createElement("span"); label.className = "ctx-item-label"; label.textContent = it.label; body.appendChild(label);
  if (it.sub) { const sub = document.createElement("span"); sub.className = "ctx-item-sub"; sub.textContent = it.sub; body.appendChild(sub); }
  row.appendChild(body);
  row.addEventListener("click", (ev) => { ev.stopPropagation(); closeContextMenu(); it.pick(); });
  menu.appendChild(row);
  return row;
}

/** A divider between two sections of `menu`. */
export function addMenuSep(menu: HTMLElement): HTMLElement {
  const sep = document.createElement("div"); sep.className = "ctx-sep";
  menu.appendChild(sep);
  return sep;
}

// a key pressed inside a field the menu holds (the tab menu's new-tag input) is the field's, except Escape
function typingIn(t: EventTarget | null): boolean {
  const e = t as HTMLElement | null;
  return !!e && (e.tagName === "INPUT" || e.tagName === "TEXTAREA" || e.tagName === "SELECT" || e.isContentEditable);
}

/** Show a card built with menuCard() at (`x`, `y`): placed inside the viewport, dismissed on a press outside it, Escape,
 *  any scroll outside it or the window's blur, its top-level rows reachable from the keyboard, and the focus handed back
 *  to the element that had it when the card closes. One menu at a time: an open one closes first. */
export function showMenuCard(menu: HTMLElement, x: number, y: number, opts: CtxMenuOpts = {}): HTMLElement {
  closeContextMenu();
  const opener = document.activeElement as HTMLElement | null;
  // the card's own rows (never a flyout's, which is a nested card): every one focusable, so the arrows reach the rows a
  // caller built by hand beside the standard ones
  const rows = (): HTMLElement[] => {
    const out: HTMLElement[] = [];
    for (const c of Array.from(menu.children)) {
      if (!c.classList.contains("ctx-item")) continue;
      const r = c as HTMLElement;
      if (!r.hasAttribute("role")) r.setAttribute("role", "menuitem");
      if (!r.hasAttribute("tabindex")) r.tabIndex = -1;
      out.push(r);
    }
    return out;
  };
  rows();
  const move = (list: HTMLElement[], from: number, step: number) => {
    if (!list.length) return;
    const to = (from + step + list.length) % list.length;
    list[to].focus();
  };
  menu.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); closeContextMenu(); return; }
    if (typingIn(ev.target)) return;
    const list = rows();
    const at = list.indexOf(document.activeElement as HTMLElement);
    // every key the menu consumes stops here: a surface under the card (the file browser's listing, whose document-level
    // handler walks its rows on the same arrows) must never see it as its own (round two of the tidy)
    if (ev.key === "Tab") { ev.preventDefault(); ev.stopPropagation(); closeContextMenu(); }   // Tab leaves the menu: the card goes with the focus (the opener has it back)
    else if (ev.key === "ArrowDown") { ev.preventDefault(); ev.stopPropagation(); move(list, at, 1); }
    else if (ev.key === "ArrowUp") { ev.preventDefault(); ev.stopPropagation(); move(list, at < 0 ? list.length : at, -1); }
    else if (ev.key === "Home") { ev.preventDefault(); ev.stopPropagation(); list[0]?.focus(); }
    else if (ev.key === "End") { ev.preventDefault(); ev.stopPropagation(); list[list.length - 1]?.focus(); }
    else if ((ev.key === "Enter" || ev.key === " ") && at >= 0) { ev.preventDefault(); ev.stopPropagation(); list[at].click(); }
  });
  // the menu never becomes the row's click: a press inside it stays inside it
  for (const ev of ["mousedown", "pointerdown", "contextmenu"]) menu.addEventListener(ev, (e) => { e.stopPropagation(); if (ev === "contextmenu") e.preventDefault(); });
  // focus leaving the card for anywhere outside it closes the card: an open menu never outlives its focus
  menu.addEventListener("focusout", (e) => { const to = e.relatedTarget as Node | null; if (to && !menu.contains(to)) closeContextMenu(); });
  document.body.appendChild(menu);
  const r = menu.getBoundingClientRect();
  const at = placeMenu(x, y, r.width, r.height, window.innerWidth, window.innerHeight);
  menu.style.left = at.left + "px"; menu.style.top = at.top + "px";
  // dismissal: a press outside the card, Escape anywhere (marked on the event, so a surface whose own Escape listens
  // later at the same phase yields to the menu's), any scroll outside it, the window losing focus
  const onDown = (e: Event) => { if (!menu.contains(e.target as Node)) closeContextMenu(); };
  const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { e.preventDefault(); closeContextMenu(); } };
  const onScroll = (e: Event) => { if (!menu.contains(e.target as Node)) closeContextMenu(); };
  const onBlur = () => closeContextMenu();
  document.addEventListener("pointerdown", onDown, true);
  document.addEventListener("keydown", onKey, true);
  document.addEventListener("scroll", onScroll, true);
  window.addEventListener("blur", onBlur);
  const done = opts.onClose;
  teardown = () => {
    document.removeEventListener("pointerdown", onDown, true);
    document.removeEventListener("keydown", onKey, true);
    document.removeEventListener("scroll", onScroll, true);
    window.removeEventListener("blur", onBlur);
    // the focus goes back where it came from, and only then: the card holds it (or it fell to the body as the card
    // went), the opener still stands, and this document has the focus; a close that followed the focus elsewhere
    // (another frame, a field outside) moves nothing
    const active = document.activeElement;
    if (opener && opener !== document.body && opener.isConnected && document.hasFocus()
        && (menu.contains(active) || active === document.body || active === null)) opener.focus({ preventScroll: true });
    if (done) done();
  };
  openMenu = menu;
  const list = rows();
  if (opts.viaKeyboard && list.length) list[0].focus(); else menu.focus();
  return menu;
}

/** Open a context menu at (`x`, `y`) with `items`; returns the card. */
export function openContextMenu(x: number, y: number, items: CtxItem[], opts: CtxMenuOpts = {}): HTMLElement {
  const menu = menuCard(opts);
  for (const it of items) addMenuItem(menu, it);
  return showMenuCard(menu, x, y, opts);
}

export interface ConfirmButton { label: string; value: string; danger?: boolean; }

let confirmFinish: ((value: string) => void) | null = null;   // the open box's settle, so a replacing box settles it first (its listener and callback never leak)

/** The chat's confirm dialog for a pane: `cb` gets the pressed button's value, or "" for Cancel, Escape and the backdrop
 *  (the chat's cb reads "" as nothing to do). One box at a time. */
export function openConfirmBox(title: string, detail: string, buttons: ConfirmButton[], cb: (value: string) => void): HTMLElement {
  if (confirmFinish) confirmFinish("");   // a box already open answers Cancel and goes, its Escape listener with it
  document.getElementById("confirm")?.remove();
  const overlay = document.createElement("div"); overlay.className = "picker-overlay confirm-overlay"; overlay.id = "confirm";
  const box = document.createElement("div"); box.className = "picker-box confirm-box";
  const h = document.createElement("div"); h.className = "confirm-title"; h.textContent = title;
  const d = document.createElement("div"); d.className = "confirm-detail"; d.textContent = detail;
  const actions = document.createElement("div"); actions.className = "confirm-actions";
  let settled = false;
  const finish = (value: string) => {
    if (settled) return;
    settled = true;
    if (confirmFinish === finish) confirmFinish = null;
    document.removeEventListener("keydown", onKey, true);
    overlay.remove();
    cb(value);
  };
  confirmFinish = finish;
  const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); finish(""); } };
  for (const b of buttons) {
    const btn = document.createElement("button"); btn.type = "button";
    btn.className = "picker-action confirm-btn" + (b.danger ? " danger" : "");
    btn.textContent = b.label;
    btn.addEventListener("click", (e) => { e.stopPropagation(); finish(b.value); });
    actions.appendChild(btn);
  }
  overlay.addEventListener("click", (e) => { if (e.target === overlay) finish(""); });
  box.append(h, d, actions);
  overlay.appendChild(box);
  document.addEventListener("keydown", onKey, true);
  document.body.appendChild(overlay);
  const first = actions.querySelector("button") as HTMLButtonElement | null;
  first?.focus();
  return overlay;
}
