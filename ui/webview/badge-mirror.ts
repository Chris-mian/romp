// Card trouble badges mirror into the shell's notification bell (the user 2026-07-27): anything that
// shows as a problem chip on a card — a judge warning, a failed follow-up, an API-error block, a
// retry storm — ALSO logs one entry in the bell, so problems are findable in one place after the
// fact. The chip on the card stays exactly as it was; the bell entry is the durable copy of the
// moment it appeared.
//
// DELIBERATELY NOT MIRRORED: the stalled hold. A stall is romp's nudge gate waiting out one of its
// own revivers (a judge call mid-flight, a reply still being judged), and almost every episode ends
// in seconds — the judge rules, or the auto-nudge fires and the session picks the work back up.
// That is the machinery working, not a problem, and mirroring it filled the log with "stalled" rows
// for holds nobody ever saw on a card (the user 2026-07-29). The chip on the card is the live
// surface; a stall that actually defeats the nudge escalates to nudgeFailed, which logs below.
//
// Pure: the caller passes the previously-notified signature set and gets back fresh notices + the
// now-active set. A signature keys the EPISODE (card + kind + the badge's own since/t), the same
// event-identity idea as the limit/judge signatures: per-push re-renders and page reloads don't
// re-log, a badge that clears leaves the active set (so a recurrence logs afresh), and a NEW episode
// of the same kind (different since/t) is a new entry.

import { apiErrorReason } from "./api-error-reason";
import { hostOf } from "./host-prefix";

export interface BadgeItem {
  itemId: string; sid: string; name: string; text: string;
  nudgeFailed?: boolean;
  retrying?: { since?: number | null; count?: number; max?: number | null; status?: number | string | null; networkDown?: boolean | null; rateLimitType?: string | null } | null;
  warns?: { kind: string; t: number; msg: string }[] | null;
  blocked?: { state: string; status?: number; text?: string; tooLong?: boolean; spendLimit?: boolean; modelLimit?: boolean; refusal?: boolean } | null;
}
// sid + itemId ride along so a bell entry can JUMP back to the card it was minted from (the user
// 2026-07-28): the shell posts them back as {romp:'revealCard'} and the feed scrolls + pulses the card.
export interface BadgeNotice { kind: string; text: string; sig: string; sid: string; itemId: string; }

const cap = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

/** The CARD-side signature prefixes badgeNotices mints (a judge warning, a failed follow-up, a retry storm, an API-error
 *  block). The rings (clears, SDK problems, syncs) use others (c|, and the rows' own sigs). */
export const CARD_SIG_PREFIXES = ["w|", "n|", "r|", "e|"];

/** The card-side signatures already in the persisted seen set, verbatim. For a frame that carries NO cards because none
 *  was built (the Task tracking switch's off frame, T404 round five): the mirror stores only the ACTIVE set, which re-arms a
 *  cleared badge because a card that left the payload takes its sigs with it; a payload that was never built is not that,
 *  so its cards' marks are kept, and every card would otherwise re-mint its bell row on the return to on. */
/** The host segment of a card mark (T404 rounds seven and eight): appended last as "|@host" for a remote card and as a
 *  bare "|@" for a local one (the local host's key is the empty string), so a mark with NO segment is one stored before
 *  round seven, whose host nobody can tell. No other segment starts with "@" (item ids, clocks, kinds, statuses), so the
 *  last "|@" is the host's. */
export const SIG_HOST_SEP = "|@";
export function withSigHost(bare: string, host: string): string { return bare + SIG_HOST_SEP + host; }
export function hasSigHost(sig: string): boolean { return sig.lastIndexOf(SIG_HOST_SEP) >= 0; }
export function sigHost(sig: string): string {
  const i = sig.lastIndexOf(SIG_HOST_SEP);
  return i < 0 ? "" : sig.slice(i + SIG_HOST_SEP.length);
}

/** …and PER HOST since round seven: every card mark when `hosts` is true (the switch's own off frame: nothing was built),
 *  else the marks of the hosts named (a merged frame carrying an off host's stand-in, or missing a pending host's frame,
 *  beside the others'), plus every mark with no host segment at all (stored before round seven: its host cannot be told,
 *  so it is kept while any host's cards are unknown and rewritten with its host the next time its card is seen; a
 *  finite set that only shrinks). A host whose cards are in hand has its marks prune by absence as ever, the local host's
 *  included (its marks carry the empty segment, round eight); a host that is off mints nothing while off, so the marks
 *  kept for it are the ones its cards carried at the flip and grow by nothing: the store stays bounded however long a
 *  host stays off. */
export function keepCardSigs(seen: Iterable<string>, hosts: true | ReadonlySet<string> = true): string[] {
  return Array.from(seen).filter((sig) => CARD_SIG_PREFIXES.some((p) => sig.startsWith(p))
    && (hosts === true || !hasSigHost(sig) || hosts.has(sigHost(sig))));
}

/** The pane's reading of a frame's cards (T404 rounds six to eight): true when the frame is the switch's own stand-in
 *  (`off`: a single kernel's, or the local kernel's word over a merged frame; nothing was built, every host's cards are
 *  unknown); the set of hosts whose cards are not in hand when a merged frame names any, the OFF hosts (their frame is
 *  the stand-in, `offHosts`) and the PENDING hosts (attached, no frame yet, `pendingHosts`: on a reload the first merged
 *  frame names every remote host here, and reading their cards as gone pruned every remote mark and re-rang every remote
 *  warn, round eight); false when every card is in hand. A card not in hand is not a card gone, whichever of the two
 *  reasons. Truthy is the ONE gate every writer in the page that prunes, retires or forgets by absence stands behind. */
export type CardsUnknown = boolean | ReadonlySet<string>;
export function frameCardsUnknown(m: { off?: unknown; offHosts?: unknown; pendingHosts?: unknown } | null | undefined): CardsUnknown {
  if (!m) return false;
  if (m.off === true) return true;
  const hosts = new Set<string>();
  for (const list of [m.offHosts, m.pendingHosts]) if (Array.isArray(list)) for (const h of list) if (typeof h === "string") hosts.add(h);
  return hosts.size ? hosts : false;
}

/** The card half of one mirror write: the notices minted from the cards on screen and the marks the store keeps. With
 *  the cards known, the live cards' marks alone (a mark whose card left the frame is pruned by absence); with them
 *  unknown, the live cards' marks plus the stored card marks of the hosts whose cards are unknown (every host's when the
 *  frame is the switch's own stand-in), since an absent card of theirs sits behind a stand-in frame rather than having
 *  left; the on hosts' absent marks still prune, which keeps the store bounded while a host stays off. */
export function badgeCardHalf(items: BadgeItem[], seen: Set<string>, cardsUnknown: CardsUnknown): ReturnType<typeof badgeNotices> {
  const minted = badgeNotices(items, seen);
  if (!cardsUnknown) return minted;
  return { notices: minted.notices, active: new Set([...minted.active, ...keepCardSigs(seen, cardsUnknown)]) };
}

export function badgeNotices(items: BadgeItem[], seen: Set<string>): { notices: BadgeNotice[]; active: Set<string> } {
  const notices: BadgeNotice[] = [];
  const active = new Set<string>();
  for (const it of items) {
    // A card's mark names its host as a trailing segment (T404 rounds seven and eight; the local host's is the empty one):
    // federation prefixes the sid, never the itemId, so without it a stored mark could not be told apart by host, and one
    // host's off frame had the mirror keep or prune EVERY host's marks together. A mark stored in the old shape (no
    // segment) still reads as seen, so the upgrade rings nothing; it is rewritten in the new shape on this write and the
    // old one leaves by absence.
    const host = hostOf(it.sid);
    const add = (bare: string, kind: string, text: string) => {
      const sig = withSigHost(bare, host);
      active.add(sig);
      if (!seen.has(sig) && !seen.has(bare)) notices.push({ kind, text, sig, sid: it.sid, itemId: it.itemId });
    };
    for (const w of it.warns ?? []) {
      add("w|" + it.itemId + "|" + w.t + "|" + w.kind, "warn", it.name + " — warning: " + cap(w.msg, 100));
    }
    if (it.nudgeFailed) {
      add("n|" + it.itemId, "nudge", it.name + " — follow-up failed on “" + cap(it.text, 50) + "”");
    }
    if (it.retrying) {
      // Name the failure behind the storm, not just that one exists — "API retry storm" was true of every
      // cause and actionable for none (the user 2026-07-29). The count says whether it is nearly out of road.
      const r = it.retrying;
      const why = apiErrorReason(r);
      const n = r.count ? ` (attempt ${r.count}${r.max ? " of " + r.max : ""})` : "";
      add("r|" + it.itemId + "|" + (r.since || 0), "retry",
        it.name + " — API retry storm" + n + (why ? ": " + why : ""));
    }
    // only the API-error block is an ERROR; a permission ask / picker is ordinary Needs-you traffic
    if (it.blocked && it.blocked.state === "apiError") {
      const b = it.blocked;
      // spendLimit / tooLong / modelLimit / refusal already read as plain words; apiErrorReason covers them too,
      // so the whole verdict comes from one place and the bell can't describe a failure differently than the chat
      // does. The signature's class slot keeps each on-you class a distinct EPISODE from a plain error on the
      // same card (a refusal often replaces a transient error mid-storm and must still mint its own entry).
      const onYou = b.spendLimit || b.tooLong || b.modelLimit || b.refusal;
      const what = apiErrorReason(b) || "API error" + (b.status ? " " + b.status : "");
      add("e|" + it.itemId + "|" + (b.status || "") + "|" + (b.spendLimit ? "sl" : b.tooLong ? "tl" : b.modelLimit ? "ml" : b.refusal ? "rf" : ""),
        "apierror", it.name + " — " + (b.status && !onYou ? "API error " + b.status + ": " : "") + what);
    }
  }
  return { notices, active };
}

// A /clear boundary that settled open cards (the kernel's clearNotices payload, read from the
// episodes log's own settle record). Same episode-identity contract as the badges above: one bell
// entry per boundary (sid + its t), so a clear that silently dropped cards is always findable in
// the bell after the fact (the user 2026-07-27). The entry names the dropped cards and the way back
// (Undo restores the batch).
export interface ClearNoticeRow { sid: string; name: string; t: number; titles: string[]; ended?: boolean; }   // ended: a session death finalized these cards (2026-08-13), not a /clear

export function clearBoundaryNotices(rows: ClearNoticeRow[], seen: Set<string>): { notices: BadgeNotice[]; active: Set<string> } {
  const notices: BadgeNotice[] = [];
  const active = new Set<string>();
  for (const r of rows) {
    const sig = "c|" + r.sid + "|" + r.t;
    active.add(sig);
    if (seen.has(sig)) continue;
    const n = r.titles.length;
    // an ENDED row is a session death that finalized open cards (2026-08-13) — same channel as the
    // /clear drop, its own phrasing: nothing here is restorable by Undo, the session is gone
    notices.push(r.ended
      ? { kind: "ended", sig, sid: r.sid, itemId: "",
          text: r.name + " ended with " + n + " open card" + (n === 1 ? "" : "s") + ": "
            + cap(r.titles.join(", "), 120) }
      : { kind: "cleared", sig, sid: r.sid, itemId: "",   // no single card — the jump opens the session
          text: r.name + " — /clear dropped " + n + " open card" + (n === 1 ? "" : "s") + ": "
            + cap(r.titles.join(", "), 120) + " (Undo on the feed restores them)" });
  }
  return { notices, active };
}

// SDK-backend problems (the kernel's sdkNotices payload — SdkBackend._log's problem ring). Same
// episode-identity contract: the kernel signs each OCCURRENCE (its start + the ring's sequence), so
// re-renders and reloads never re-log, while a repeat of the same failure is a NEW occurrence and logs
// again (the bell's own coalescing turns a flood into one counted row). Until 2026-07-28 these went to
// the kernel log alone, so a session whose thread died just looked odd, with nothing to look at.
export interface SdkNoticeRow { sig: string; t: number; text: string; }

export function sdkProblemNotices(rows: SdkNoticeRow[], seen: Set<string>): { notices: BadgeNotice[]; active: Set<string> } {
  const notices: BadgeNotice[] = [];
  const active = new Set<string>();
  for (const r of rows ?? []) {
    if (!r || !r.sig || !r.text) continue;   // a blank line is not an entry
    active.add(r.sig);
    if (seen.has(r.sig)) continue;
    notices.push({ kind: "sdk", text: cap(r.text, 240), sig: r.sig, sid: "", itemId: "" });
  }
  return { notices, active };
}

// Automatic fleet syncs (the kernel's syncNotices payload — the ring _auto_push_remote / _auto_pull_remote
// / _auto_ask_peer write their outcome to). The user asked for these on 2026-07-30: romp moves commits
// between machines on its own, and until now the only trace was a phase line in the network panel that
// disappeared the moment the sync finished — so a push that landed, and a push that failed while you were
// looking elsewhere, both ended up equally invisible. SUCCESSES log too, deliberately: the point is a
// record of what romp did to your machines, not just an alarm.
//
// The Log is a browser-side store the kernel cannot write to, which is why this rides the payload and
// mirrors here rather than being appended server-side. Same episode-identity contract as the SDK ring:
// the kernel signs each occurrence (its start + the ring's sequence).
//
// `kind` (review find, 2026-09-08): the ring also carries the kernel's state-file faults (a store that
// could not be read, or held bytes it could not parse and moved aside). Filed under "sync" they wore
// the machine-sync label, and muting that log (the one kind that records successes, so a plausible
// mute) silenced every disk-fault notice with it. The kernel names the row's kind; this side ALLOWLISTS
// it, so a remote kernel's payload can only ever land in one of the two kinds the bell knows here.
export interface SyncNoticeRow { sig: string; t: number; text: string; ok?: boolean; kind?: string }

export function syncNotices(rows: SyncNoticeRow[], seen: Set<string>): { notices: BadgeNotice[]; active: Set<string> } {
  const notices: BadgeNotice[] = [];
  const active = new Set<string>();
  for (const r of rows ?? []) {
    if (!r || !r.sig || !r.text) continue;
    active.add(r.sig);
    if (seen.has(r.sig)) continue;
    notices.push({ kind: r.kind === "refused" ? "refused" : "sync", text: cap(r.text, 240), sig: r.sig, sid: "", itemId: "" });
  }
  return { notices, active };
}
