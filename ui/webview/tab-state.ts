// THE TAB STRIP'S STATE → CLASS RULE, in one place. The tab itself wears it (render.ts renderTabs),
// and a folded section header's member-derived summary pip (tab groups, 2026-09-04) reads the SAME rule
// — the header once classed any "blocked" member red, while the strip distinguishes an on-you block
// from a transient API error that auto-retries (amber, needs no attention), so a folded group showed a
// red "waiting on you" pip over a tab that, unfolded, was amber. The header is a LABEL (the user
// 2026-09-06): it wears no state class of its own; the pip below is the member-derived mark a fold
// must not hide. Pure and DOM-free so it runs in node tests; the Status interface in render.ts is a
// superset of the shape read here.
export interface TabStateLike {
  state?: string;
  apiTooLong?: boolean;
  apiSpendLimit?: boolean;
  apiModelLimit?: boolean;
  apiAuthErr?: boolean;
  apiRefusal?: boolean;
  needsYou?: boolean | null;   // the FEED's per-session needs-you verdict (build_session's status; null before the first feed build)
}

/** The tab's state class for a status, or "" for a state with no tab treatment (ready/idle). */
export function tabStateClass(s: TabStateLike | null | undefined): string {
  const st = s?.state || "";
  if (st === "working") return "tab-working";
  // "blocked" is an API error. An on-YOU one — "prompt is too long" (compact), a monthly spend cap
  // (raise it, the user 2026-07-14), a spent model allowance (switch model, the user 2026-08-01), an
  // auth failure, or a safeguards refusal (rewrite the ask, the user 2026-08-15) — is alarm-red
  // dashed; a TRANSIENT API error is auto-retrying and needs no attention → the amber retrying
  // treatment, not red (the user 2026-06-29).
  if (st === "blocked") return (s!.apiTooLong || s!.apiSpendLimit || s!.apiModelLimit || s!.apiAuthErr || s!.apiRefusal) ? "tab-blocked" : "tab-retrying";
  if (st === "needsInput" || st === "awaiting") return "tab-awaiting";   // legacy name = an older remote kernel
  if (st === "retrying") return "tab-retrying";                          // amber: soft-blocked on an API auto-retry
  if (st === "compacting" || st === "clearing") return "tab-compacting"; // both: a context op in flight
  if (st === "closed") return "tab-closed";                              // dead session: read-only, struck-through label
  return "";
}

/** THE RINGS a tab can wear, in PRECEDENCE order (the rings-as-widgets change, 2026-09-14): each is a widget of the
 *  tab-widget registry (tab-widgets.ts, slot "ring") with its own switch in the settings' Tab widgets section, and a
 *  tab wears ONE at a time, the first in this order whose switch is on and whose test holds. Red over magenta over
 *  amber: a live prompt or an API stop only you can clear says "stopped on you"; a card of the session's under
 *  Needs you says something needs you, whatever else the session is doing; a transient API retry needs no
 *  attention at all. This is the pure, DOM-free twin of the registry's composition (composeTabRing), read by the
 *  folded header's pip below, so the strip and the pip cannot disagree; tab-widgets.test.ts pins the two equal over
 *  every synthetic status and every switch set. */
export type RingId = "ring-needs-you" | "ring-waiting-on-you" | "ring-retrying";
export const RING_ORDER: readonly RingId[] = ["ring-needs-you", "ring-waiting-on-you", "ring-retrying"];
export const RING_TEST: Record<RingId, (s: TabStateLike | null | undefined) => boolean> = {
  // the RED ring: a LIVE prompt (a permission or picker prompt, tab-awaiting), or an API stop only you can clear
  // (tab-blocked: prompt too long, a spend cap, a spent model allowance, an auth failure, a refusal)
  "ring-needs-you": (s) => { const c = tabStateClass(s); return c === "tab-awaiting" || c === "tab-blocked"; },
  // the MAGENTA ring (the Needs you ring; yellow until 2026-09-21, the ask ring of 2026-09-13): the feed filed a card of this session under needs-you (status.needsYou,
  // the kernel's per-session read of the feed's needs_input column in build_session, the same verdict the
  // section-at-a-glance row's chip and the feed's Blocked list speak, so the three can never disagree) and the tab is
  // not dead. The session may be idle, awaiting background work or still WORKING while the card waits, and the ring
  // shows in every one of those, composed with the working dot rather than replacing it: a session with something
  // waiting on you should grab attention without a click, even while it goes on working. Only TRUE is a verdict: null
  // (no feed build yet) and false are the same nothing, as is an older kernel's absent field. The test itself no
  // longer stands down under the red states; the composition's first-on-ring rule does, so with the red ring switched
  // off a stopped session with a card wears the magenta, which is true of that tab.
  "ring-waiting-on-you": (s) => s?.needsYou === true && tabStateClass(s) !== "tab-closed",
  // the AMBER ring: the state retrying, or blocked with none of the on-you flags (the API is backing off and retrying
  // on its own)
  "ring-retrying": (s) => tabStateClass(s) === "tab-retrying",
};
/** The ring a tab wears for a status: the first of RING_ORDER whose switch (`on`; every ring on by default) is on and
 *  whose test holds; null for none. */
export function tabRingId(s: TabStateLike | null | undefined, on: (id: RingId) => boolean = () => true): RingId | null {
  for (const id of RING_ORDER) if (on(id) && RING_TEST[id](s)) return id;
  return null;
}

export type SectionPip = "blocked" | "ask" | "retrying" | "working";

/** A folded header's ONE pip for its members' states, in the tab's own colours and by the tab's own rule, under the
 *  same ring switches (`on`) the members' tabs wear, so a fold never shows a colour no unfolded tab would: red when a
 *  member wears the red ring (stopped on you); else magenta when one wears the magenta ring (a card that needs you,
 *  whatever else it is doing); else gold when one is working; else amber when one wears the amber ring
 *  (stalled on an API error that is auto-retrying: shown only when nothing in the group is making progress, since it
 *  is not on you); null when nothing is happening. */
export function sectionPip(states: ReadonlyArray<TabStateLike | null | undefined>, on: (id: RingId) => boolean = () => true): SectionPip | null {
  const rings = states.map((s) => tabRingId(s, on));
  if (rings.includes("ring-needs-you")) return "blocked";
  if (rings.includes("ring-waiting-on-you")) return "ask";
  if (states.some((s) => tabStateClass(s) === "tab-working")) return "working";
  if (rings.includes("ring-retrying")) return "retrying";
  return null;
}

/** The pip's phrase for ONE session (and the bare phrase when no name is known). */
export const SECTION_PIP_TITLE: Record<SectionPip, string> = {
  blocked: "a session in this group is stopped on you",
  ask: "a session in this group has a card that needs you",
  working: "a session in this group is working",
  retrying: "a session in this group hit an API error and is retrying on its own",
};

/** The same four for SEVERAL sessions, counted: a singular phrase before a list of names read as one
 *  session, then two. */
export const SECTION_PIP_TITLE_MANY: Record<SectionPip, (n: number) => string> = {
  blocked: (n) => `${n} sessions in this group are stopped on you`,
  ask: (n) => `${n} sessions in this group have a card that needs you`,
  working: (n) => `${n} sessions in this group are working`,
  retrying: (n) => `${n} sessions in this group hit an API error and are retrying on their own`,
};

/** The ring each pip kind names (the working pip is the state's, not a ring's). */
const PIP_RING: Record<Exclude<SectionPip, "working">, RingId> = { blocked: "ring-needs-you", ask: "ring-waiting-on-you", retrying: "ring-retrying" };

export interface TabMemberLike { name?: string; status?: TabStateLike | null }

/** The members whose own tab wears the pip's colour, under the same switches: the sessions its tooltip names, in
 *  strip order. A working session that also wears a ring is named under both kinds. */
export function sectionPipMembers(kind: SectionPip, members: ReadonlyArray<TabMemberLike | null | undefined>, on: (id: RingId) => boolean = () => true): string[] {
  const names: string[] = [];
  const wears = (s: TabStateLike | null | undefined) => kind === "working" ? tabStateClass(s) === "tab-working" : tabRingId(s, on) === PIP_RING[kind];
  for (const m of members) if (m && wears(m.status)) names.push(String(m.name || "").trim() || "(unnamed)");
  return names;
}

/** The pip's hover text: the rule's phrase — singular for one session, counted for several — then the
 *  sessions by name. */
export function sectionPipTitle(kind: SectionPip, names: readonly string[]): string {
  if (!names.length) return SECTION_PIP_TITLE[kind];
  const phrase = names.length === 1 ? SECTION_PIP_TITLE[kind] : SECTION_PIP_TITLE_MANY[kind](names.length);
  return `${phrase}: ${names.join(", ")}`;
}

/** The state dot every tab carries (T262g, the user 2026-09-08: the strip's row count flapped with a tab's state).
 *  A tab's width must not depend on its state: the dot's slot is laid out in EVERY state and merely hidden when the
 *  state has no dot ("tab-dot none"), so a session starting or finishing work cannot add or remove a row of the strip
 *  and slide the transcript under the reader by a row's height. working → the solid dot; awaitingBg → the await-green
 *  dot; a missing state → the gray ring; opening → the accent loader dot; compacting → null (its animated bar takes
 *  the slot); everything else → the hidden slot. */
export function tabDotClass(st: string | undefined | null): string | null {
  if (st === "compacting") return null;
  if (st === "working") return "tab-dot";
  if (st === "awaitingBg") return "tab-dot await";
  if (!st) return "tab-dot unknown";
  if (st === "opening") return "tab-dot opening";
  return "tab-dot none";
}

/** What a tab's dot says on hover (the user 2026-07-22: each pip explains itself, the same titles the feed's
 *  DOT_TIP speaks), beside the class rule above so the two can never disagree on what a dot means: working,
 *  awaitingBg, a missing state and opening have a title; the hidden slot ("tab-dot none") and the compacting
 *  bar (no dot) say nothing. render.ts sets it on the slot tabDotClass classed. */
export function tabDotTitle(st: string | undefined | null): string | null {
  if (st === "working") return "working — a turn is running right now";
  if (st === "awaitingBg") return "awaiting — idle, but background work it dispatched is still running";
  if (!st) return "state unknown — romp couldn't read this session's live state";
  if (st === "opening") return "opening — this session is still starting up";
  return null;
}
