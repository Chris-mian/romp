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
  itemId: string; sid: string; name: string; text: string;
  stalled?: { why: string; since: number; note?: string | null } | null;
  nudgeFailed?: boolean;
  retrying?: { since?: number | null; count?: number } | null;
  warns?: { kind: string; t: number; msg: string }[] | null;
  blocked?: { state: string; status?: number; text?: string; tooLong?: boolean; spendLimit?: boolean } | null;
}
// sid + itemId ride along so a bell entry can JUMP back to the card it was minted from (the user
// 2026-07-28): the shell posts them back as {romp:'revealCard'} and the feed scrolls + pulses the card.
export interface BadgeNotice { kind: string; text: string; sig: string; sid: string; itemId: string; }

const cap = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

export function badgeNotices(items: BadgeItem[], seen: Set<string>): { notices: BadgeNotice[]; active: Set<string> } {
  const notices: BadgeNotice[] = [];
  const active = new Set<string>();
  for (const it of items) {
    const add = (sig: string, kind: string, text: string) => {
      active.add(sig);
      if (!seen.has(sig)) notices.push({ kind, text, sig, sid: it.sid, itemId: it.itemId });
    };
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

// A /clear boundary that settled open cards (the kernel's clearNotices payload, read from the
// episodes log's own settle record). Same episode-identity contract as the badges above: one bell
// entry per boundary (sid + its t), so a clear that silently dropped cards is always findable in
// the bell after the fact (the user 2026-07-27). The entry names the dropped cards and the way back
// (Undo clear restores the batch).
export interface ClearNoticeRow { sid: string; name: string; t: number; titles: string[]; }

export function clearBoundaryNotices(rows: ClearNoticeRow[], seen: Set<string>): { notices: BadgeNotice[]; active: Set<string> } {
  const notices: BadgeNotice[] = [];
  const active = new Set<string>();
  for (const r of rows) {
    const sig = "c|" + r.sid + "|" + r.t;
    active.add(sig);
    if (seen.has(sig)) continue;
    const n = r.titles.length;
    notices.push({ kind: "cleared", sig, sid: r.sid, itemId: "",   // no single card — the jump opens the session
      text: r.name + " — /clear dropped " + n + " open card" + (n === 1 ? "" : "s") + ": "
        + cap(r.titles.join(", "), 120) + " (Undo clear on the feed restores them)" });
  }
  return { notices, active };
}
