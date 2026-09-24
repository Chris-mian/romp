// "Restart session" — the ONE row, built once for both menus that offer it: the chat strip's tab menu
// (render.ts showTabMenu) and the Sessions pane's row menu (fleet.ts showSessionMenu). The user asked for
// one action (2026-09-23) in place of End then Revive, the only in-product way a long-lived session could
// get onto a newly installed CLI — two destructive-looking steps through a confirm dialog for something
// that destroys nothing. The kernel's restartSession op relaunches the session's own process in place.
//
// What this module owns, so the two menus cannot drift:
//   * the gesture — idle restarts with no dialog, a working one confirms first (restartConfirmDetail
//     names what the click interrupts, the End dialog's shape); Cancel posts nothing;
//   * the ACKNOWLEDGEMENT (ui/CLAUDE.md's button rule: a post-and-wait control disables, changes its own
//     label and self-restores). The row latches to "Restarting…" on the click and the card stays up under
//     it — a restart changes nothing else on screen, by design, so the row is the only place the click can
//     show. It re-arms on the kernel's own reply for that sid (restarted / restartFailed / an unknownOp
//     refusal from a kernel older than this page), never on a clock;
//   * the latch is keyed by SID, never held on a node: the strip and the Sessions pane both rebuild on
//     every kernel push and the menu card outlives them, so a card reopened while a restart is in flight
//     shows the latched row too, and a settled sid restores a row only while its node is still connected.
import { addMenuItem, closeContextMenu, ConfirmButton } from "./ctx-menu";
import { RESTART_LABEL, RESTART_BUSY_LABEL, RESTART_SUBLINE, RESTART_BUSY_SUBLINE, restartConfirmDetail } from "./clear-confirm";

const inFlight = new Set<string>();                 // sids this page has asked to restart and not heard back about
const latched = new Map<string, HTMLElement>();     // …and the row showing it, while that card is still up

/** Is a restart this page asked for still in flight for `sid`? */
export function restartInFlight(sid: string): boolean { return inFlight.has(sid); }

/** The kernel answered for `sid` (restarted, restartFailed, or an unknownOp refusal of the op): the latch
 *  lifts and any row still on screen re-arms in place. Idempotent — a sid with no latch settles to nothing. */
export function settleRestart(sid: string): void {
  inFlight.delete(sid);
  const row = latched.get(sid);
  latched.delete(sid);
  if (row && row.isConnected) dress(row, false);
}

/** Does restarting a session in this state interrupt anything? `working` and `compacting` are the chat's
 *  own reading of a turn in flight; `awaitingBg` is a session that is idle itself while background work it
 *  dispatched runs on — and that work is retired with the client it belongs to (the reconnect's
 *  _drop_live_work), so it is interrupted too. Every other state costs nothing and takes no dialog. */
export function restartInterrupts(state: string | null | undefined): boolean {
  return state === "working" || state === "compacting" || state === "awaitingBg";
}

/** The confirm's title, the End dialog's shape. */
export function restartConfirmTitle(name: string): string { return `Restart “${name}”?`; }

/** The confirm's buttons: no danger mark — a restart destroys nothing (that is the whole claim the dialog
 *  is making), it only interrupts. */
export const RESTART_BUTTONS: ConfirmButton[] = [{ label: "Restart session", value: "restart" }, { label: "Cancel", value: "" }];

function dress(row: HTMLElement, busy: boolean): void {
  const label = row.querySelector(".ctx-item-label");
  const sub = row.querySelector(".ctx-item-sub");
  if (label) label.textContent = busy ? RESTART_BUSY_LABEL : RESTART_LABEL;
  if (sub) sub.textContent = busy ? RESTART_BUSY_SUBLINE : RESTART_SUBLINE;
  if (busy) row.setAttribute("aria-disabled", "true"); else row.removeAttribute("aria-disabled");
}

export interface RestartRowCtx {
  name: string;                 // the session as the user calls it, for the confirm's title
  working: boolean;             // a turn in flight or queued → confirm first; idle → straight through
  titles: string[];             // its open tops, named in the confirm as the End dialog names them
  icon?: HTMLElement | null;    // the menu's drawn icon, where that menu draws them
  confirm: (title: string, detail: string, buttons: ConfirmButton[], cb: (v: string | null) => void) => void;
  post: () => void;             // the page's own postMessage of { type: "restartSession", id: sid }
}

/** Append the Restart session row to `menu` for `sid`. */
export function addRestartRow(menu: HTMLElement, sid: string, ctx: RestartRowCtx): HTMLElement {
  const go = (row: HTMLElement) => {
    inFlight.add(sid);
    if (row.isConnected) { latched.set(sid, row); dress(row, true); }   // the acknowledgement, before the kernel round trip
    ctx.post();
  };
  const row = addMenuItem(menu, {
    icon: ctx.icon || null,
    className: "ctx-item-restart",
    label: RESTART_LABEL,
    sub: RESTART_SUBLINE,
    keepOpen: true,             // the row acts in place: the card stays up under the latched label
    pick: (r) => {
      if (restartInFlight(sid)) return;                 // already asked (the aria-disabled row's belt)
      if (!ctx.working) { go(r); return; }              // idle: no dialog for a click that costs nothing
      // it is working: the dialog IS this click's acknowledgement, so the card goes first rather than
      // sitting under the overlay's dim (the Sessions pane's Delete order)
      closeContextMenu();
      ctx.confirm(restartConfirmTitle(ctx.name), restartConfirmDetail(ctx.titles), RESTART_BUTTONS,
        (v) => { if (v === "restart") go(r); });        // Cancel, Escape, the backdrop: nothing posted
    },
  });
  if (restartInFlight(sid)) { latched.set(sid, row); dress(row, true); }   // a card reopened mid-restart
  return row;
}
