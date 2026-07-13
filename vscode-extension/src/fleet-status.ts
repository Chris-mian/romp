// Fleet status for the VS Code status bar + needs-you notifications, derived
// from the kernel's {type:"feed"} frames — the SAME authoritative payload the
// feed pane renders (working = the event-model working set; needs-you = the
// live cards in the Needs-input column). Pure decision core (like
// kernel-attach.ts): extension.ts owns the StatusBarItem and the actual
// vscode.window notifications.

export type FleetStatus = { working: number; needsYou: number };

// The live needs-you cards (the feed's Needs-input column). Parked/offline
// hand-offs (live:false) are chores, not interrupts — excluded.
export function needsYouAsks(frame: any): any[] {
  if (!frame || !Array.isArray(frame.asks)) return [];
  return frame.asks.filter((a: any) => a && a.column === "needs_input" && a.live !== false);
}

export function deriveStatus(frame: any): FleetStatus | null {
  if (!frame || frame.type !== "feed") return null;
  const working = new Set((Array.isArray(frame.working) ? frame.working : []).map(String)).size;
  const needsYou = new Set(needsYouAsks(frame).map((a: any) => String(a.sid))).size;
  return { working, needsYou };
}

// Which needs-you cards are NEW since the previous frame — the notification
// trigger. Event-based: a card re-entering the column after being answered is
// a fresh event and notifies again. seen === null means "first frame after
// (re)connect": baseline silently — old asks are status, not news.
export function freshNeedsYou(
  seen: ReadonlySet<string> | null,
  frame: any,
): { seen: Set<string>; fresh: any[] } {
  const asks = needsYouAsks(frame);
  const now = new Set<string>(asks.map((a: any) => String(a.itemId)));
  if (seen === null) return { seen: now, fresh: [] };
  return { seen: now, fresh: asks.filter((a: any) => !seen.has(String(a.itemId))) };
}

// The status bar face. warn=true tints the item (needs-you is the one state
// worth an ambient flag — "interrupt only when the human is the bottleneck").
export function renderStatusBar(
  offline: boolean,
  st: FleetStatus | null,
): { text: string; warn: boolean } {
  if (offline || !st) return { text: "romp: offline", warn: false };
  const bits: string[] = [];
  if (st.working) bits.push(`${st.working} working`);
  if (st.needsYou) bits.push(`${st.needsYou} need${st.needsYou === 1 ? "s" : ""} you`);
  return { text: `romp: ${bits.length ? bits.join(" · ") : "idle"}`, warn: st.needsYou > 0 };
}

// The hover detail: working session names, then each needs-you card as
// "name — text". Lines, so the host can join for a tooltip.
export function statusTooltipLines(frame: any): string[] {
  const lines: string[] = [];
  const working: string[] = [...new Set((Array.isArray(frame?.working) ? frame.working : []).map(String))] as string[];
  if (working.length) lines.push(`Working: ${working.join(", ")}`);
  for (const a of needsYouAsks(frame)) {
    const text = String(a.text || "").replace(/\s+/g, " ").trim();
    lines.push(`${a.name}: ${text.length > 80 ? text.slice(0, 79) + "…" : text}`);
  }
  return lines;
}
