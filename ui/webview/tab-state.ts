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

/** THE ASK RING (the user 2026-09-13): "tab-ask" when the feed files a card of this session under needs-you —
 *  it asked something, a decision is pending, a peer's message waits for a say, a stall needs eyes — and the
 *  tab is not already red or dead; else "". A SECOND class beside the state class, not a state of its own:
 *  the session may be idle, awaiting background work or still WORKING while the card waits, and the ring
 *  must show in every one of those (a session with something waiting on you should grab attention without a
 *  click, even while it goes on working in the background), so it composes with the working dot rather than
 *  replacing it. The red ring — a LIVE prompt (tab-awaiting) or an API stop only you can clear (tab-blocked)
 *  — already says "needs you now" and outranks it; a closed tab is past tense and wears nothing. It does
 *  outrank the amber retrying ring: a transient API retry needs no attention, the ask does (styles.css orders
 *  the outline rules to match). Reads status.needsYou: the kernel's per-session read of the feed's needs_input
 *  column (build_session), the same verdict the section-at-a-glance row's chip and the feed's Blocked list
 *  speak, so the three can never disagree; null (no feed build yet) and false are the same nothing. */
export function tabAskClass(s: TabStateLike | null | undefined): string {
  if (s?.needsYou !== true) return "";
  const st = tabStateClass(s);
  return st === "tab-awaiting" || st === "tab-blocked" || st === "tab-closed" ? "" : "tab-ask";
}

/** Every class a tab wears for its status: the state class, then the ask ring (either may be absent). */
export function tabClasses(s: TabStateLike | null | undefined): string[] {
  return [tabStateClass(s), tabAskClass(s)].filter(Boolean);
}

export type SectionPip = "blocked" | "ask" | "retrying" | "working";

/** A folded header's ONE pip for its members' states, in the tab's own colours and by the tab's own
 *  rule: red when a member is blocked on you or waiting for you; else yellow when one has something
 *  waiting on you (the ask ring, whatever else it is doing); else gold when one is working; else
 *  amber when one is stalled on an API error that is auto-retrying (shown only when nothing in the
 *  group is making progress — it is not on you); null when nothing is happening. */
export function sectionPip(states: ReadonlyArray<TabStateLike | null | undefined>): SectionPip | null {
  const cls = states.flatMap(tabClasses);
  if (cls.some((c) => c === "tab-blocked" || c === "tab-awaiting")) return "blocked";
  if (cls.includes("tab-ask")) return "ask";
  if (cls.includes("tab-working")) return "working";
  if (cls.includes("tab-retrying")) return "retrying";
  return null;
}

/** The pip's phrase for ONE session (and the bare phrase when no name is known). */
export const SECTION_PIP_TITLE: Record<SectionPip, string> = {
  blocked: "a session in this group is blocked or waiting on you",
  ask: "a session in this group has something waiting on you",
  working: "a session in this group is working",
  retrying: "a session in this group hit an API error and is retrying on its own",
};

/** The same four for SEVERAL sessions, counted: a singular phrase before a list of names read as one
 *  session, then two. */
export const SECTION_PIP_TITLE_MANY: Record<SectionPip, (n: number) => string> = {
  blocked: (n) => `${n} sessions in this group are blocked or waiting on you`,
  ask: (n) => `${n} sessions in this group have something waiting on you`,
  working: (n) => `${n} sessions in this group are working`,
  retrying: (n) => `${n} sessions in this group hit an API error and are retrying on their own`,
};

const PIP_CLASSES: Record<SectionPip, readonly string[]> = {
  blocked: ["tab-blocked", "tab-awaiting"], ask: ["tab-ask"], working: ["tab-working"], retrying: ["tab-retrying"],
};

export interface TabMemberLike { name?: string; status?: TabStateLike | null }

/** The members whose own tab wears the pip's color — the sessions its tooltip names, in strip order. A tab
 *  wears up to two classes (the state and the ask ring), so a member matches on any of them. */
export function sectionPipMembers(kind: SectionPip, members: ReadonlyArray<TabMemberLike | null | undefined>): string[] {
  const names: string[] = [];
  for (const m of members) if (m && tabClasses(m.status).some((c) => PIP_CLASSES[kind].includes(c))) names.push(String(m.name || "").trim() || "(unnamed)");
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
