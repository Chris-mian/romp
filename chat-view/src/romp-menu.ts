// The romp status-bar button's dropdown: what the QuickPick shows when romp is
// already open — surfaces, editor actions, the kernel's settings, and the
// account usage windows up top (the user 2026-07-13: settings behind the romp
// button; usage somewhere always visible). Pure decision core: extension.ts
// renders the items and dispatches the action ids; values come from the
// kernel's /version (current settings), /usage, and /models (choice lists).

export type MenuItem = {
  label: string;
  description?: string;
  action: string;          // dispatch id, "" for non-actionable info rows
};

// "session 91% · week 44% · Fable 5 75%" — the account-wide rate-limit
// windows, worst-first coloring left to the host. Empty when no usage known.
export function usageSummary(usage: any): string {
  if (!usage) return "";
  const bits: string[] = [];
  const add = (key: string, name: string) => {
    const seg = usage[key];
    if (seg && typeof seg.pct === "number") bits.push(`${name} ${seg.pct}%`);
  };
  add("fiveHour", "session");
  add("sevenDay", "week");
  add("fable", "Fable 5");
  return bits.join(" · ");
}

// Reset countdown for the tightest window, e.g. "session resets in 2h05m".
export function usageResetLine(usage: any, nowS: number): string {
  if (!usage) return "";
  let worst: { name: string; resetsAt: number; pct: number } | null = null;
  for (const [key, name] of [["fiveHour", "session"], ["sevenDay", "week"], ["fable", "Fable 5"]] as const) {
    const seg = usage[key];
    if (seg && typeof seg.pct === "number" && seg.resetsAt && (!worst || seg.pct > worst.pct))
      worst = { name, resetsAt: seg.resetsAt, pct: seg.pct };
  }
  if (!worst) return "";
  const s = Math.max(0, worst.resetsAt - nowS);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return `${worst.name} resets in ${h ? `${h}h${String(m).padStart(2, "0")}m` : `${m}m`}`;
}

export function buildMenu(usage: any, nowS: number): MenuItem[] {
  const items: MenuItem[] = [];
  const u = usageSummary(usage);
  if (u) items.push({ label: `Usage: ${u}`, description: usageResetLine(usage, nowS), action: "usage" });
  items.push(
    { label: "Open Chat", action: "openChat" },
    { label: "Open Feed", action: "openFeed" },
    { label: "Open Timeline", action: "openTimeline" },
    { label: "Open Outline", action: "openFleet" },
    { label: "Cite File in Chat Composer", action: "cite" },
    { label: "Open Session Worktree", action: "worktree" },
    { label: "Diff Session Changes", action: "diff" },
    // Opens the romp-styled gear modal in the feed (the SAME settings UI the
    // browser renders — the user 2026-07-13), not a native picker.
    { label: "Settings", description: "the romp settings modal", action: "settings" },
  );
  return items;
}
