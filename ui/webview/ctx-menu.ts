// One context menu for the panes that had none (the Sessions pane first; the user 2026-09-16, who wanted a right-click
// on a session's row to rename or delete it). The card and its rows are the chat's `.ctx-menu` and `.ctx-item` dress,
// which every romp menu wears through the theme tokens styles.css defines (ui/CLAUDE.md: one menu vocabulary), so a pane
// that loads that sheet needs no rule of its own. The menu is placed inside the viewport, dismissed on a press outside
// it, Escape, any scroll or the window's blur, and reachable from the keyboard (arrows and Home/End move, Enter or Space
// picks, Escape closes). The tab strip, the feed's card menu and the file browser's row menu build the same rows by
// hand today; moving them onto this builder is a later tidy, not this change.
//
// The confirm box beside it is the chat's confirm dialog (`showConfirm` in render.ts) in the same classes, for a pane
// that has to ask before it acts: the Sessions pane's Delete asks with the strip's own title, detail and buttons.

export interface CtxItem { label: string; sub?: string; danger?: boolean; pick: () => void; }
export interface CtxMenuOpts { className?: string; viaKeyboard?: boolean; onClose?: () => void; }

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

/** Close the open context menu, if any. */
export function closeContextMenu(): void {
  if (teardown) { const t = teardown; teardown = null; t(); }
  if (openMenu) { openMenu.remove(); openMenu = null; }
}

/** Open a context menu at (`x`, `y`) with `items`; returns the card. One menu at a time: an open one closes first. */
export function openContextMenu(x: number, y: number, items: CtxItem[], opts: CtxMenuOpts = {}): HTMLElement {
  closeContextMenu();
  const menu = document.createElement("div");
  menu.className = "ctx-menu" + (opts.className ? " " + opts.className : "");
  menu.setAttribute("role", "menu");
  menu.tabIndex = -1;
  const rows: HTMLElement[] = [];
  for (const it of items) {
    const row = document.createElement("div");
    row.className = "ctx-item ctx-item-toggle" + (it.danger ? " ctx-item-danger" : "");
    row.setAttribute("role", "menuitem");
    row.tabIndex = -1;
    const body = document.createElement("span"); body.className = "ctx-item-body";
    const label = document.createElement("span"); label.className = "ctx-item-label"; label.textContent = it.label; body.appendChild(label);
    if (it.sub) { const sub = document.createElement("span"); sub.className = "ctx-item-sub"; sub.textContent = it.sub; body.appendChild(sub); }
    row.appendChild(body);
    row.addEventListener("click", (ev) => { ev.stopPropagation(); closeContextMenu(); it.pick(); });
    menu.appendChild(row);
    rows.push(row);
  }
  const move = (from: number, step: number) => {
    if (!rows.length) return;
    const to = (from + step + rows.length) % rows.length;
    rows[to].focus();
  };
  menu.addEventListener("keydown", (ev) => {
    const at = rows.indexOf(document.activeElement as HTMLElement);
    if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); closeContextMenu(); }
    else if (ev.key === "Tab") { ev.preventDefault(); closeContextMenu(); }   // Tab leaves the menu: the card goes with the focus (onClose returns it to the opener)
    else if (ev.key === "ArrowDown") { ev.preventDefault(); move(at, 1); }
    else if (ev.key === "ArrowUp") { ev.preventDefault(); move(at < 0 ? rows.length : at, -1); }
    else if (ev.key === "Home") { ev.preventDefault(); rows[0]?.focus(); }
    else if (ev.key === "End") { ev.preventDefault(); rows[rows.length - 1]?.focus(); }
    else if ((ev.key === "Enter" || ev.key === " ") && at >= 0) { ev.preventDefault(); ev.stopPropagation(); rows[at].click(); }
  });
  // the menu never becomes the row's click: a press inside it stays inside it
  for (const ev of ["mousedown", "pointerdown", "contextmenu"]) menu.addEventListener(ev, (e) => { e.stopPropagation(); if (ev === "contextmenu") e.preventDefault(); });
  // focus leaving the card for anywhere outside it closes the card: an open menu never outlives its focus
  menu.addEventListener("focusout", (e) => { const to = e.relatedTarget as Node | null; if (to && !menu.contains(to)) closeContextMenu(); });
  document.body.appendChild(menu);
  const r = menu.getBoundingClientRect();
  const at = placeMenu(x, y, r.width, r.height, window.innerWidth, window.innerHeight);
  menu.style.left = at.left + "px"; menu.style.top = at.top + "px";
  // dismissal: a press outside the card, Escape anywhere, any scroll, the window losing focus
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
    if (done) done();
  };
  openMenu = menu;
  if (opts.viaKeyboard && rows.length) rows[0].focus(); else menu.focus();
  return menu;
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
