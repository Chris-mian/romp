// Card trouble badges mirror into the shell's notification bell (the user 2026-07-27): anything that
// shows as a problem chip on a card — a judge warning, a stalled hold, a failed follow-up, an
// API-error block, a retry storm — ALSO logs one entry in the bell, so problems are findable in one
// place after the fact. The chip on the card stays exactly as it was; the bell entry is the durable
// copy of the moment it appeared.
//
// Pure: the caller passes the previously-notified signature set and gets back fresh notices + the
// now-active set. A signature keys the EPISODE (card + kind + the badge's own since/t), the same
// event-identity idea as the limit/judge signatures: per-push re-renders and page reloads don't
// re-log, a badge that clears leaves the active set (so a recurrence logs afresh), and a NEW episode
// of the same kind (different since/t) is a new entry.

export interface BadgeItem {
  itemId: string; name: string; text: string;
  stalled?: { why: string; since: number; note?: string | null } | null;
  nudgeFailed?: boolean;
  retrying?: { since?: number | null; count?: number } | null;
  warns?: { kind: string; t: number; msg: string }[] | null;
  blocked?: { state: string; status?: number; text?: string; tooLong?: boolean; spendLimit?: boolean } | null;
}
export interface BadgeNotice { kind: string; text: string; sig: string; }

const cap = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

export function badgeNotices(items: BadgeItem[], seen: Set<string>): { notices: BadgeNotice[]; active: Set<string> } {
  const notices: BadgeNotice[] = [];
  const active = new Set<string>();
  const add = (sig: string, kind: string, text: string) => {
    active.add(sig);
    if (!seen.has(sig)) notices.push({ kind, text, sig });
  };
  for (const it of items) {
    for (const w of it.warns ?? []) {
      add("w|" + it.itemId + "|" + w.t + "|" + w.kind, "warn", it.name + " — warning: " + cap(w.msg, 100));
    }
    if (it.stalled) {
      add("s|" + it.itemId + "|" + it.stalled.since, "stalled",
        it.name + " — stalled: " + cap(it.stalled.note || it.stalled.why, 100));
    }
    if (it.nudgeFailed) {
      add("n|" + it.itemId, "nudge", it.name + " — follow-up failed on “" + cap(it.text, 50) + "”");
    }
    if (it.retrying) {
      add("r|" + it.itemId + "|" + (it.retrying.since || 0), "retry", it.name + " — API retry storm");
    }
    // only the API-error block is an ERROR; a permission ask / picker is ordinary Needs-you traffic
    if (it.blocked && it.blocked.state === "apiError") {
      const b = it.blocked;
      const what = b.spendLimit ? "spend limit reached"
        : b.tooLong ? "prompt too long (needs compaction)"
        : "API error" + (b.status ? " " + b.status : "");
      add("e|" + it.itemId + "|" + (b.status || "") + "|" + (b.spendLimit ? "sl" : b.tooLong ? "tl" : ""),
        "apierror", it.name + " — " + what);
    }
  }
  return { notices, active };
}
