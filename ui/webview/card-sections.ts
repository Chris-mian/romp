// THE CARD'S SECTIONS, one builder for the feed card and the Needs you box's row (plans/needs-you.md, "the row carries what the card
// carries", the user 2026-09-23): the press toggles Background · Summary · Stalled · N sub-goals · Awaiting task in the card's order, the
// one-open rule with its default, the state behind them (secChoice by item id, the tree's expanded branches), and the bodies they drive
// (the background paragraph, the distill line, the stall note, the sub-goal tree, the awaited rows). Moved here verbatim from feed.ts
// (2026-09-24) so the chat page's row draws the same disclosure from the same fields and never a second copy; what the two pages do
// differently rides SectionEnv (the collapsed-by-default preference, the node click zones, the PR repo for links, the live durations,
// opening a session). Every host that shows an item's sections registers here (registerSectionHost), so a press on any of them reaches
// them all: the feed card, its focused-section copy and the chat box's row are one twin set for the item.
import { linkifyPrRefs } from "./pr-links";
import { hostPartsNodes } from "./host-prefix";
import { awaitWord, groupRows, waitsNote, GROUP_TITLE, ROW_KIND_OF_LEGACY, type AwaitRow } from "./spin-caption";

function el(tag: string, cls?: string): HTMLElement {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  return e;
}

export interface NodeLogRow {
  kind: string; src: string; why?: string | null;
  at?: number | null; evT?: number | null; anchorUuid?: string | null;
}

export interface AskTreeNode {
  born?: { kind: string; via: string; why: string; healed?: boolean } | null;   // T319: a step the session started on its own
                                                                                //   (via: workflow | agent | work); why it sits under this goal
  id: string; kind: "ask" | "handoff"; text: string; who: string;
  whoSid: string; whoColor: { bg: string; fg: string } | null;   // agent → colored session link
  whoWorking?: boolean;                                          // that agent is currently WORKING → yellow dot before its name
  status: "done" | "question" | "open"; t: number; last: number;
  mt?: number;                                                   // last-modified (done/block segment) → blocked/done nodes deep-link to where they RESOLVED, not where they were minted
  anchorUuid?: string | null;                                    // EXACT turn uuid for this node's WORK target (where it resolved — an assistant turn); mark/time zones jump here. null when unresolvable
  promptAnchorUuid?: string | null;                              // EXACT turn uuid for this node's PROMPT target = the user's minting message (a user turn) → prompt-intent jumps (title, text) resolve BY ID (kernel 92e23ff)
  derived?: boolean;                                             // done by roll-up/roll-down (kernel), not explicit → DIMMED ✓ disc
  qderived?: boolean;                                            // "question" by roll-UP (the block lives in a descendant) → tooltip says so; the actual ask carries its own ⏸ below (kernel flatten, the user 2026-07-11)
  auth?: "open" | "done";                                        // AUTHORITATIVE tier: mirrors an item on the agent's OWN to-do list → solidity=authority disc (open = bold accent ring; done = heaviest check). Absent = plain judge-inferred node.
  followupPending?: boolean;                                     // this sub was optimistically reopened by a per-sub follow-up → "↻ Followed up" chip (kernel flatten, judges 047264f)
  summary?: string | null;                                       // the DISTILLER's key takeaway for a completed goal (artifact or 1-3 sentences) → the modal's auto-line for a DONE node (kernel flatten 78fc97b)
  blockSummary?: string | null;                                  // the BLOCK-distiller's decision brief for a blocked goal → the modal's auto-line for a BLOCKED node (kernel 466393c); null until produced
  summaryAnchorUuid?: string | null;                            // the brief/summary line's own landing (kernel T388): the text atom that carries it
  summaryAnchorQuote?: string | null;                           // …and its located span, sent as the click's quote
  relayNote?: string | null;   // a far host still holds a relayed question after its wait ended (kernel relayCarried) → its own dim line under the brief, never a brief paragraph
  trgb?: [number, number, number];                               // last-activity recency tint (timestamp)
  cleared?: boolean;                                             // user-cleared sub (nodeOverride op:clear) → struck-through faded row + "cleared" chip; the mark stays tied to status (box = done, the user 2026-07-26)
  reviewedEarlier?: boolean;                                     // this done sub predates the top's review boundary (kernel flatten ↔ jd.review_boundary, the distiller's own scoping) → collapsed behind one "N reviewed earlier" row (the user 2026-08-19)
  parked?: { n: number } | null;                                 // LEAPFROGGED open row (kernel _parked_rows, the user 2026-08-24): nothing filed under it while n younger siblings were dispatched past it → quiet "parked" tag + the card's dim sub-goals suffix; retires on its own delegation edge or any verdict
  log?: NodeLogRow[] | null;                                     // the node's newest verdict rows (kernel _node_log_rows, non-done only) → the modal's per-item story (the user 2026-07-20)
  children: string[];
}

/** The fields of a feed item the sections read: the card's AskItem satisfies it, and so does the chat box's row (the kernel's _needs_you_rows
 *  carries every one of them from the same feed item). */
export interface SectionItem {
  itemId: string; sid: string;
  background?: string | null;
  summary?: string | null; blockSummary?: string | null;
  tree?: AskTreeNode[] | null;
  stalled?: { why: string; since?: number; note?: string | null; blocked?: boolean } | null;
  awaiting?: { why?: string | null; kind?: string | null; since?: number | null; count?: number | null; tasks?: string[] | null;
               peers?: { name: string; host?: string; sid?: string; color?: { bg: string; fg: string } | null }[] | null;
               items?: AwaitRow[] | null } | null;
}

/** What a page supplies to the shared builder: its collapsed-by-default preference, how a sub-goal row's zones are wired, the PR repo for
 *  a row's links, the live duration nodes, and how a peer's session is opened. */
export interface SectionEnv {
  collapsed(): boolean;
  wireNode(it: SectionItem, node: AskTreeNode, mark: HTMLElement, txt: HTMLElement, wire: boolean): void;
  repoOf(sid: string | undefined): string | null;
  durNodes(since: number | null | undefined): (string | HTMLElement)[];
  openSession(sid: string): void;
}

// the twin set per item: every host element that shows the item's sections (a feed card, its focused-section copy, the chat box's row);
// hosts that left the document are dropped on the next read, so nothing has to unregister
const hosts = new Map<string, Set<HTMLElement>>();
export function registerSectionHost(itemId: string, a: HTMLElement): void {
  let set = hosts.get(itemId);
  if (!set) { set = new Set(); hosts.set(itemId, set); }
  set.add(a);
}
export function unregisterSectionHost(itemId: string, a: HTMLElement): void {   // a host that sheds its sections (the Needs you row turned credential row) leaves the set
  const set = hosts.get(itemId); if (!set) return;
  set.delete(a); if (!set.size) hosts.delete(itemId);
}
export function sectionHosts(itemId: string): HTMLElement[] {
  const set = hosts.get(itemId);
  if (!set) return [];
  for (const a of Array.from(set)) if (!a.isConnected) set.delete(a);
  if (!set.size) hosts.delete(itemId);
  return Array.from(set);
}
// THE CHOICE ACROSS DOCUMENTS (plans/needs-you.md, the row carries what the card carries): the card lives in the feed page and the Needs you
// row in the chat page, two documents in the shell, each with its own copy of this module and its own secChoice. A pick on either reaches the
// other over a BroadcastChannel (same origin; the shell's panes are), which persists nothing: a reload starts at the default as before, and a
// page without the channel (a VS Code webview is its own origin, so nobody listens) keeps its own choice. The receiver re-applies to every
// host it has for the item with the item and environment each host remembered.
const sectionChannel: BroadcastChannel | null = typeof BroadcastChannel === "function" ? new BroadcastChannel("romp-card-sections") : null;
(sectionChannel as unknown as { unref?: () => void } | null)?.unref?.();   // Node has a BroadcastChannel too, and an open one holds its event loop: the node test run hung on the first module that imports this (2026-09-24); a browser's channel has no unref, so the call is nothing there
sectionChannel?.addEventListener("message", (ev: MessageEvent) => {
  const d = ev.data as { id?: unknown; choice?: unknown } | null;
  if (!d || typeof d.id !== "string" || !["bg", "summary", "subgoals", "tasks", "stall", "none"].includes(d.choice as string)) return;
  secChoice.set(d.id, d.choice as "bg" | "summary" | "subgoals" | "tasks" | "stall" | "none");
  for (const c of sectionHosts(d.id)) { const h = c as any; if (h._it && h._sectionEnv) applySections(h, h._it, !!h._distillShown, h._sectionEnv); }
});

export const secChoice = new Map<string, "bg" | "summary" | "subgoals" | "tasks" | "stall" | "none">();
export function resolveSec(id: string, hasAwaitTasks = false, collapsed = false): "bg" | "summary" | "subgoals" | "tasks" | "stall" | "none" {
  // an awaiting-on-tasks card OPENS its task list by default (the user 2026-08-23: the wait is the
  // one thing to read on that card); an explicit user pick and collapsed mode still win
  return secChoice.get(id) ?? (collapsed ? "none" : hasAwaitTasks ? "tasks" : "summary");
}
// The Stalled body's text: the staller's plain-language note when the judge has written one, else the
// kernel's own mechanical reason. Never a waiting-on-the-judge placeholder — a stalled card always has
// something true to say about why it is stuck, because the kernel knew the reason before the judge was
// ever asked. That is the whole point of grounding this surface in the mechanical why.
export function stallText(st: { why: string; note?: string | null } | null | undefined): string {
  if (!st) return "";
  const note = (st.note || "").trim();
  return note || ("Nothing is moving this: romp is waiting on " + st.why + ".");
}
// Per-node EXPAND state for a CARD's inline sub-goal tree, keyed "itemId:nodeId" (the user 2026-07-08, who referred to the
// little triangle-y icons from the outline view). A node is COLLAPSED by default; membership here means the
// user clicked its triangle open. So the tree opens showing only the top level and expands on demand — like
// the modal's one-level view. Empty default = everything collapsed. (Its OWN state, not the modal's
// `collapsedNodes`, which uses the inverse sense + its own seeding.)
export const cardTreeExpanded = new Set<string>();

export const CLEARED_TIP = "you cleared this off the board — no longer needed; the box still shows whether it was done";
export function clearedTag(): HTMLElement {
  const tag = el("span", "fcleared-tag");
  tag.textContent = "cleared";
  tag.title = CLEARED_TIP;
  return tag;
}

// The parked row's plain-language story (the user 2026-08-24: a queued ask silently sat 40 minutes
// while the same card's younger items were dispatched one after another, and nothing said so). One
// quiet word on the row, the explanation on hover — a hint, never a needs-you alarm; the kernel
// retires it the instant the row gets its own delegation or any verdict (_parked_rows).
export function parkedTag(n: number): HTMLElement {
  const tag = el("span", "fparked-tag");
  tag.textContent = "parked";
  tag.title = "nothing has happened here yet — " + n + " newer ask" + (n === 1 ? " was" : "s were")
    + " dispatched past this one; this tag clears on its own dispatch or any ruling";
  return tag;
}

export function nodeStatusClass(n: AskTreeNode): string {
  if (n.cleared) return "cleared";
  if (n.status === "done") return "done";
  if (n.status === "question") return "question";
  return "open";
}

export const TREE_INDENT_EM = 1.4;

// Fill + wire the card's THREE mutually-exclusive sections — Background, Summary, Sub-goals (the user
// 2026-07-08). At most ONE open at a time (or none): clicking the open one closes it, clicking another
// switches. Each button shows only when it has content to reveal — bg present / a produced takeaway/brief /
// the goal has sub-goals — so an unavailable choice falls back to "none". The bg/summary BODIES live in
// `_secs`; the sub-goal TREE lives in `_checklist` below. stopPropagation on every toggle — the card-body
// click opens the modal.
export function applySections(a: any, it: SectionItem, distillShown: boolean, env: SectionEnv): void {
  a._distillShown = distillShown;   // remembered on the host, so a twin's re-apply from a press on another host uses its own
  a._it = it; a._sectionEnv = env;   // and its item and its page's environment, for a re-apply from another document's pick (the channel below)
  const id = it.itemId;
  const bg = distillShown && it.background ? it.background : null;
  // does the card have a sub-goal tree to show? (the root has a non-handoff child — handoffs live in the
  // delegations section). byId/root are reused by the tree builder below.
  const tree = it.tree || [];
  const byId = new Map(tree.map((n) => [n.id, n] as const));
  const root = tree.find((n) => n.id === it.itemId) || tree[0];
  // DIRECT sub-goals only — one level below (the user 2026-07-15): the button reads "3 sub-goals" for the
  // goal's immediate children, matching what the tree first shows when opened; deeper levels aren't folded
  // into this headline number — the user drills into them by expanding a child's ▶ triangle. Distinct
  // non-handoff direct children, deduped once. (Was the whole-subtree count, every depth.)
  let subCount = 0;
  if (root) {
    const seenC = new Set<string>([root.id]);
    for (const cid of (root.children || [])) {
      if (seenC.has(cid)) continue;
      seenC.add(cid);
      const n = byId.get(cid);
      if (!n || n.kind === "handoff") continue;
      subCount++;
    }
  }
  const hasSubs = subCount > 0;
  // live background tasks (the user 2026-07-13): when the card is AWAITING on tasks, the compact
  // "Awaiting task" pill joins the section toggles and expands this list (the old boxed caption is gone)
  const taskList = ((it.awaiting && it.awaiting.tasks) || []).filter(Boolean);
  // …and since slice 2 (2026-09-05) the awaited ROWS, grouped by kind — agents, commands, watches,
  // peers — so the pill shows for ANY wait the kernel can enumerate, not only a bg-task one (a wait on
  // live subagents had no clickable affordance on the card). An older kernel ships descriptions only;
  // they read as rows of the legacy kind's group, so the list never goes blank on a mixed deployment.
  const awKind = (it.awaiting && it.awaiting.kind) || "";
  const awItems: AwaitRow[] = ((it.awaiting && it.awaiting.items) || []).filter((r) => r && r.kind);
  const taskRows: AwaitRow[] = awItems.length ? awItems
    : taskList.map((d) => ({ kind: ROW_KIND_OF_LEGACY[awKind] || "commands", label: d }));
  const hasTasks = taskRows.length > 0;
  // resolve the selection (default = summary open), falling back to "none" if the chosen section is empty
  // the stall note (the user 2026-07-23) — shown whenever the kernel says romp is holding this card, with
  // or without a judge-written note, since `why` alone already answers "why is nothing happening"
  const stall = it.stalled && it.stalled.why ? it.stalled : null;
  let choice = resolveSec(id, hasTasks, env.collapsed());
  if (choice === "bg" && !bg) choice = "none";
  if (choice === "summary" && !distillShown) choice = "none";
  if (choice === "subgoals" && !hasSubs) choice = "none";
  if (choice === "tasks" && !hasTasks) choice = "none";
  if (choice === "stall" && !stall) choice = "none";
  const pick = (want: "bg" | "summary" | "subgoals" | "tasks" | "stall") => (ev: Event) => {
    ev.stopPropagation();
    secChoice.set(id, choice === want ? "none" : want);   // click the showing one → off; else switch to it
    // both elements of the card (T347): the disclosure is the CARD's, so the board's element and the focused
    // section's copy show the same section after a pick on either; and the Needs you row in the chat page, another document (the box
    // content round), through the channel
    const twins = sectionHosts(id);
    if (twins.length) { for (const c of twins) applySections(c as any, (c as any)._it ?? it, (c as any)._distillShown ?? distillShown, env); }
    else applySections(a, it, distillShown, env);
    sectionChannel?.postMessage({ id, choice: secChoice.get(id) });
  };
  // Background toggle — visible only when there IS background; pressed (.on) when its body is showing
  a._bgBtn.style.display = bg ? "" : "none";
  a._bgBtn.classList.toggle("on", choice === "bg");
  a._bgBtn.setAttribute("aria-pressed", choice === "bg" ? "true" : "false");
  a._bgBtn.title = choice === "bg" ? "hide the background" : "show the background";
  a._bgBody.style.display = choice === "bg" ? "" : "none";
  if (choice === "bg") a._bgBody.textContent = bg as string;
  a._bgBtn.onclick = pick("bg");
  // Summary toggle
  a._takeBtn.style.display = distillShown ? "" : "none";
  a._takeBtn.classList.toggle("on", choice === "summary");
  a._takeBtn.setAttribute("aria-pressed", choice === "summary" ? "true" : "false");
  a._takeBtn.title = choice === "summary" ? "hide the summary" : "show the summary";
  (a._distill as HTMLElement).style.display = choice === "summary" ? "" : "none";
  a._takeBtn.onclick = pick("summary");
  // Stalled toggle — same press-toggle as the others; its colour is the difference (see .fask-stallbtn)
  a._stallBtn.style.display = stall ? "" : "none";
  a._stallBtn.classList.toggle("on", choice === "stall");
  a._stallBtn.setAttribute("aria-pressed", choice === "stall" ? "true" : "false");
  a._stallBtn.title = stall
    ? (choice === "stall" ? "hide why this is stalled" : "romp is holding this — show why")
    : "";
  a._stallBody.style.display = choice === "stall" ? "" : "none";
  if (choice === "stall") a._stallBody.textContent = stallText(stall);
  a._stallBtn.onclick = pick("stall");
  // Sub-goals toggle — visible only when the goal HAS sub-goals; pressed when the tree is showing
  const subBtn = a._subBtn as HTMLElement;
  subBtn.style.display = hasSubs ? "" : "none";
  subBtn.textContent = subCount === 1 ? "1 sub-goal" : subCount + " sub-goals";
  // dim " · N parked" suffix (the user 2026-08-24): the card-level gist of the row tags. Counts ONLY
  // rows the checklist this button toggles can actually reach — the same walk, stopping at handoff
  // nodes (delegations render in their own section) and at the root (the card head, not a row) — so
  // the suffix never advertises rows no expansion reveals (review 2026-08-24; a parked ask under a
  // LIVE delegation is the modal tree's to show).
  let parkedCount = 0;
  if (root) {
    const pseen = new Set<string>([root.id]);
    const pwalk = (nid: string) => {
      const n = byId.get(nid);
      if (!n || n.kind === "handoff" || pseen.has(n.id)) return;
      pseen.add(n.id);
      if (n.parked && n.parked.n) parkedCount++;
      for (const c of n.children || []) pwalk(c);
    };
    for (const c of (root.children || [])) pwalk(c);
  }
  if (hasSubs && parkedCount) {
    const pk = el("span", "fask-subparked");
    pk.textContent = " · " + parkedCount + " parked";
    subBtn.appendChild(pk);
  }
  subBtn.classList.toggle("on", choice === "subgoals");
  subBtn.setAttribute("aria-pressed", choice === "subgoals" ? "true" : "false");
  subBtn.title = choice === "subgoals" ? "hide the sub-goals" : "show the sub-goals";
  subBtn.onclick = pick("subgoals");
  // "Awaiting task" pill (the user 2026-07-13) — visible only while live bg tasks exist; the mini swirl
  // inside keeps the "in flight" cue; pressed when the task list is showing. No preachy tooltip.
  // "Awaiting", not "Waiting on": the chat chip and timeline badge already label this exact state
  // Awaiting, and two words for one state read as two states (the user 2026-08-13).
  const taskBtn = a._taskBtn as HTMLElement;
  taskBtn.style.display = hasTasks ? "" : "none";
  // the KIND words the pill (the user 2026-08-15): "Awaiting watch", "Awaiting 3 agents" — the wait's
  // class in the visible label (tooltips are dead on the touch PWA). ONE rule with the chat chip and
  // the awaiting box (awaitWord, slice 2): one row → its word, several of a kind → count + word, mixed
  // kinds → the number alone ("Awaiting 4"); a single named peer → its name in identity colour.
  const pillPeers = (it.awaiting && it.awaiting.peers) || [];
  const pillWord = awaitWord(awKind, (it.awaiting && it.awaiting.count) ?? taskRows.length, taskRows);
  const pillLbl = a._taskLbl as HTMLElement;
  pillLbl.replaceChildren("Awaiting ");
  if (pillPeers.length === 1 && taskRows.every((r) => r.kind === "peer")) {
    const nm = el("span", "fask-waiton-name");
    nm.replaceChildren(...hostPartsNodes(pillPeers[0].host, pillPeers[0].name));
    if (pillPeers[0].color && pillPeers[0].color.bg) nm.style.color = pillPeers[0].color.bg;
    pillLbl.appendChild(nm);
  } else pillLbl.append(pillWord);
  // the wait's elapsed time rides the pill exactly as it rides the awaiting box and the working
  // narration — a stuck wait must be glanceable everywhere the state shows (the user 2026-08-23) —
  // as a stamped duration the 15 s live pass keeps moving (durNodes, the live twin of waitedSuffix)
  pillLbl.append(...env.durNodes(it.awaiting && it.awaiting.since));   // the waited time, live (durSpan)
  taskBtn.classList.toggle("on", choice === "tasks");
  taskBtn.setAttribute("aria-pressed", choice === "tasks" ? "true" : "false");
  taskBtn.title = choice === "tasks" ? "hide the tasks" : "show the tasks";
  taskBtn.onclick = pick("tasks");
  // the bg/summary/stall BODIES container shows only when one of those is open (the tree is a separate
  // element). "stall" MUST be here: stallBody lives inside _secs, so without it the Stalled toggle pressed
  // .on while its body stayed inside a display:none parent — the button "selected but nothing happened"
  // (the user 2026-07-23, the very first click on the day-old section).
  a._secs.style.display = (choice === "bg" || choice === "summary" || choice === "stall") ? "" : "none";
  // the inline sub-goal TREE (in _checklist), shown only when choice === "subgoals". Whole subtree, indented
  // by depth, with the outline's ▶/▼ disclosure triangles to fold branches (the user 2026-07-08). Same
  // inclusion rules as the modal's renderTreeNode: skip handoffs, a node reached under two parents renders
  // ONCE (dim ".repeat", not re-descended). renderTree() re-runs itself on a triangle toggle (collapse state
  // changed) without touching the buttons.
  const cl = a._checklist as HTMLElement;
  const renderTree = () => {
    cl.innerHTML = "";
    // the TASK list (the user 2026-07-13): same view/spot as the sub-goal checklist — one row per live
    // background task, a small spinning swirl as its mark (in flight), the task's own description as text
    if (choice === "tasks") {
      // …grouped by KIND since slice 2 (2026-09-05): a small dim header per group when more than one
      // shows (agents / commands / watches / peers), labels only — the chat's box carries the controls
      const groups = groupRows(taskRows);
      const peerByName = new Map(pillPeers.map((p) => [p.name, p]));
      // one row; `sub` = a NESTED row (what the agent above it is itself waiting on, kernel `waits`,
      // 2026-09-10): indented, the first under its agent led by a small dim "waiting on", the rest by its
      // blank twin so the marks align; a nested row with waits of its own says their count in its label —
      // one level drawn, like the chat's box. Labels only here; the chat box carries the controls.
      const taskRow = (r: AwaitRow, sub: "first" | "rest" | null): HTMLElement => {
        const row = el("div", "fcheck ftask" + (sub ? " ftask-sub" : ""));
        if (sub) { const on = el("span", "ftask-waits-on" + (sub === "first" ? "" : " ftask-waits-blank")); on.textContent = sub === "first" ? "waiting on" : ""; row.appendChild(on); }
        const tri = el("span", "fcheck-tri empty");
        const mark = el("span", "fcheck-mark");
        mark.appendChild(el("span", "fask-awaiting-swirl ftask-swirl"));
        const txt = el("span", "fcheck-text");
        const p = r.kind === "peer" ? peerByName.get(r.label || "") : undefined;
        if (p) {
          // a peer row names the session the way the awaiting box does: identity colour, quiet host prefix,
          // click opens the session (the standard session-chip gesture)
          txt.replaceChildren(...hostPartsNodes(p.host, p.name));
          if (p.color && p.color.bg) txt.style.color = p.color.bg;
          if (p.sid) {
            const sid = p.sid;
            txt.title = "waiting on " + p.name + " — click opens the session";
            txt.style.cursor = "pointer";
            txt.onclick = (ev: Event) => { ev.stopPropagation(); env.openSession(sid); };
          }
        } else txt.textContent = r.label || r.kind;
        const deeper = sub ? waitsNote(r) : "";
        if (deeper) { const dp = el("span", "ftask-deeper"); dp.textContent = " · waiting on " + deeper; txt.appendChild(dp); }
        row.append(tri, mark, txt);
        return row;
      };
      for (const g of groups) {
        if (groups.length > 1) { const gh = el("div", "ftask-group"); gh.textContent = GROUP_TITLE[g.kind] || "Other"; cl.appendChild(gh); }
        for (const r of g.rows) {
          cl.appendChild(taskRow(r, null));
          ((r.waits || []).filter((w) => w && w.kind)).forEach((w, i) => cl.appendChild(taskRow(w, i === 0 ? "first" : "rest")));
        }
      }
      cl.style.display = cl.children.length ? "" : "none";
      return;
    }
    if (choice !== "subgoals" || !root) { cl.style.display = "none"; return; }
    const rows: { node: AskTreeNode; depth: number; repeat: boolean; expandable: boolean; collapsed: boolean }[] = [];
    const seen = new Set<string>([root.id]);   // a child linking back to the root counts as a repeat (as the modal)
    const walk = (nid: string, depth: number) => {
      const n = byId.get(nid);
      if (!n || n.kind === "handoff") return;   // delegations render in their own section, not the checklist
      const repeat = seen.has(n.id);
      const expandable = !repeat && (n.children || []).some((c) => { const cn = byId.get(c); return !!cn && cn.kind !== "handoff"; });
      // DEFAULT COLLAPSED (the user 2026-07-08): the tree opens showing only the top level; a branch is
      // expanded only once its triangle was clicked (in cardTreeExpanded), just like the modal's one-level view.
      const collapsed = expandable && !cardTreeExpanded.has(id + ":" + n.id);
      rows.push({ node: n, depth, repeat, expandable, collapsed });
      if (repeat || collapsed) return;           // a repeat is dim + NOT re-descended; a collapsed branch is hidden
      seen.add(n.id);
      for (const c of n.children || []) walk(c, depth + 1);
    };
    // REVIEWED-EARLIER fold (the user 2026-08-19): direct children whose outcomes the user already
    // reviewed (kernel reviewedEarlier, from the SAME boundary the distiller scopes the takeaway with)
    // collapse behind one row, so a re-completed card presents only the new work — the old material is
    // one click away, never gone. Fresh rows first; the fold row sits below them.
    // …counting what the walk RENDERS: a handoff child is skipped by walk (delegations live in their own section), so a
    // reviewed handoff counted in the label made "3 reviewed earlier" open to two rows (the 2026-09-18 read)
    const shown = (c: string) => { const n = byId.get(c); return !!n && n.kind !== "handoff"; };
    const revKids = (root.children || []).filter((c) => shown(c) && !!byId.get(c)?.reviewedEarlier);
    const freshKids = (root.children || []).filter((c) => shown(c) && !byId.get(c)?.reviewedEarlier);
    const revOpen = cardTreeExpanded.has(id + ":reviewed");
    for (const c of freshKids) walk(c, 0);
    const freshEnd = rows.length;
    // the fold's kids sit ONE level under the fold row, their visual parent (depth 1, the modal outline's indent), never
    // flush with the fresh rows above it (the user's 2026-09-18 screenshot: the reviewed rows read as a second batch of
    // fresh ones); their own children indent from there
    if (revOpen) for (const c of revKids) walk(c, 1);
    const paintRow = ({ node: s, depth, repeat, expandable, collapsed }: typeof rows[number]) => {
      const row = el("div", "fcheck " + nodeStatusClass(s) + (s.auth ? " auth-" + s.auth : "") + (repeat ? " repeat" : ""));
      if (depth) row.style.paddingLeft = (depth * TREE_INDENT_EM) + "em";   // same per-level indent as the modal outline
      // disclosure triangle: ▶ collapsed / ▼ expanded; a non-expandable node gets a blank same-width spacer so
      // marks stay aligned. Only the triangle toggles (stopPropagation so the row click still opens the modal).
      const tri = el("span", "fcheck-tri" + (expandable ? " nav" : " empty"));
      tri.textContent = expandable ? (collapsed ? "▶" : "▼") : "";
      if (expandable) tri.onclick = (ev: Event) => {
        ev.stopPropagation();
        const k = id + ":" + s.id;
        if (cardTreeExpanded.has(k)) cardTreeExpanded.delete(k); else cardTreeExpanded.add(k);
        renderTree();
      };
      const mark = el("span", "fcheck-mark");
      // ✓ blue disc (done) / ⏸ red pause (question = blocked) / empty ring (not done) — the SAME notation as the
      // ledger checklist + Fleet (the user 2026-06-24). The OPEN mark is an empty element the CSS draws as a
      // 13px hollow circle matching the done disc's size (the user 2026-07-08: the ○ glyph read too small);
      // AUTHORITATIVE keeps the glyph, .auth-* only rings it. Blocked ROLLS UP (kernel flatten, the user
      // 2026-07-11): an ancestor of a blocked sub wears the ⏸ too, so the block is visible even while the
      // branch is collapsed — its tooltip points DOWN to the real ask.
      mark.textContent = s.status === "done" ? "✓" : s.status === "question" ? "⏸" : "";
      if (s.status === "question") mark.title = s.qderived ? "a sub-goal inside it needs you: expand to find it" : "needs you";
      const txt = el("span", "fcheck-text"); txt.textContent = s.text; linkifyPrRefs(txt, env.repoOf(it.sid));
      row.append(tri, mark, txt);
      if (s.cleared) row.appendChild(clearedTag());   // the strike alone doesn't say WHY — see CLEARED_TIP
      if (s.parked && s.parked.n && !s.cleared) row.appendChild(parkedTag(s.parked.n));   // leapfrogged — see parkedTag
      // clicks match the modal tree node exactly (text → the message, checkbox → where it resolved) via the
      // SAME wireNodeZones; a dim repeat is display-only (wire=false).
      env.wireNode(it, s, mark, txt, !repeat);
      cl.appendChild(row);
    };
    rows.slice(0, freshEnd).forEach(paintRow);
    if (revKids.length) {
      // the fold row: same gesture grammar as a branch triangle — click toggles, state survives
      // re-renders via cardTreeExpanded (keyed per card), and the label carries the count. Its expanded state
      // is "expanded", NEVER "open": "open" is the not-done STATUS class (.fcheck.open .fcheck-mark draws the
      // hollow 13px ring), so the open fold wore the ring and its ✓ glyph sat low inside it, a checkmark that
      // moved down in its box the moment the fold was opened (the user's 2026-09-18 screenshot)
      const row = el("div", "fcheck freviewed" + (revOpen ? " expanded" : ""));
      const tri = el("span", "fcheck-tri nav"); tri.textContent = revOpen ? "▼" : "▶";
      const mark = el("span", "fcheck-mark"); mark.textContent = "✓";
      const txt = el("span", "fcheck-text");
      txt.textContent = revKids.length + " reviewed earlier";
      row.title = "sub-goals you reviewed before your follow-up — the update above doesn't re-present them";
      row.onclick = (ev: Event) => {
        ev.stopPropagation();
        const k = id + ":reviewed";
        if (cardTreeExpanded.has(k)) cardTreeExpanded.delete(k); else cardTreeExpanded.add(k);
        renderTree();
      };
      row.append(tri, mark, txt);
      cl.appendChild(row);
    }
    rows.slice(freshEnd).forEach(paintRow);
    cl.style.display = cl.children.length ? "" : "none";
  };
  renderTree();
}

// THE STATE BADGES of the card's name row, as the Needs you box's row wears them too (plans/needs-you.md): one place for their words and
// tooltips, read by the feed card (updateAskCard) and the row builder. The peer-facing ones (awaiting a peer, a delegation's origin or
// handoff) build their nodes here, since the peer's name wears its identity colour and a quiet host prefix on both surfaces.
export const BADGE_WORDS = {
  rejudging: { text: "↩ re-judging", title: "you followed up — no longer waiting on you; the judge will resolve it or re-block it on the next pass" },
  nudgeFailed: { text: "follow-up failed", title: "romp followed up once; the response didn't resolve it and it won't be re-asked — it's waiting on you" },
  interrupting: { text: "interrupting…", title: "stop sent — waiting for this session to reach a stopping point" },
  interrupted: { text: "interrupted", title: "you stopped this session mid-turn; romp won't follow up on its own until you message it again" },
} as const;

export interface BadgeItem {
  recheck?: boolean | null; rejudging?: boolean | null; nudgeFailed?: boolean | null;
  nudged?: { count: number; times: number[] } | null;
  interrupting?: boolean | null; interrupted?: boolean | null;
  waitingOn?: { peerSid?: string; name: string; color?: { bg: string; fg: string } | null; inCycle?: boolean; kind?: string; since?: number | null } | null;
  origin?: { peer: string; peerSid: string; peerHost?: string; color?: { bg: string; fg: string } | null; live?: boolean } | null;
  handoffTo?: { peer: string; peerSid: string; peerHost?: string; color?: { bg: string; fg: string } | null } | null;
}

/** The badges the card's name row shows for this item, in the card's order, as fresh elements: re-judging, follow-up failed, interrupting or
 *  interrupted (the card's own precedence: follow-up failed outranks both interrupt words, and the two interrupt words never show together),
 *  awaiting a peer (or handed off to one, or a deadlock), a delegation's origin. `clockHM` formats the nudge times in the tooltip. */
export function stateBadges(it: BadgeItem, env: { durNodes(since: number | null | undefined): (string | HTMLElement)[]; openSession(sid: string): void; clockHM(t: number): string }): HTMLElement[] {
  const out: HTMLElement[] = [];
  const badge = (cls: string, text: string, title: string) => { const b = el("span", cls); b.textContent = text; b.title = title; return b; };
  if (it.recheck || it.rejudging) out.push(badge("fask-followedup", BADGE_WORDS.rejudging.text, BADGE_WORDS.rejudging.title));
  if (it.nudgeFailed) {
    const b = badge("fask-nudgefailed", BADGE_WORDS.nudgeFailed.text, BADGE_WORDS.nudgeFailed.title);
    if (it.nudged && it.nudged.times && it.nudged.times.length) b.title = `romp followed up ${it.nudged.count}× (${it.nudged.times.map(env.clockHM).join(", ")}); the response didn't resolve it and it won't be re-asked — it's waiting on you`;
    out.push(b);
  }
  if (it.interrupting && !it.nudgeFailed) out.push(badge("fask-interrupting", BADGE_WORDS.interrupting.text, BADGE_WORDS.interrupting.title));
  if (it.interrupted && !it.interrupting && !it.nudgeFailed) out.push(badge("fask-interrupted", BADGE_WORDS.interrupted.text, BADGE_WORDS.interrupted.title));
  const wo = it.waitingOn;
  if (wo) {
    const b = el("span", "fask-waiton" + (wo.inCycle ? " fask-waiton-cycle" : ""));
    const pre = el("span", "fask-waiton-pre"); pre.textContent = wo.inCycle ? "Deadlock " : wo.kind === "delegate" ? "Handed off to " : "Awaiting ";
    const name = el("span", "fask-waiton-name"); name.textContent = wo.name; if (wo.color && wo.color.bg) name.style.color = wo.color.bg;
    b.append(pre, name);
    const dur = env.durNodes(wo.since); if (dur.length) { const w = el("span", "fask-waiton-dur"); w.append(...dur); b.appendChild(w); }
    b.title = wo.inCycle ? "MUTUAL WAIT — this session and " + wo.name + " are each waiting on the other (a deadlock); auto-nudge surfaces it instead of nudging"
      : wo.kind === "delegate" ? "this session handed work to " + wo.name + " and acts when the result comes back — not stalled, so auto-nudge skips it"
      : "this session has an unanswered message out to " + wo.name + " — waiting on its reply, not stalled, so auto-nudge skips it";
    out.push(b);
  }
  if (it.origin && it.origin.peer) {
    const og = el("a", "fask-origin" + (it.origin.live === false ? " fask-origin-absorbed" : ""));
    const pre = el("span", "fask-origin-pre"); pre.textContent = "↪ from ";
    const peer = el("span", "fask-origin-peer"); peer.replaceChildren(...hostPartsNodes(it.origin.peerHost, it.origin.peer)); if (it.origin.color) peer.style.color = it.origin.color.bg;
    og.append(pre, peer);
    og.title = (it.origin.live === false ? "delegated by " + it.origin.peer + "; their linked entry closed with this card" : "delegated by " + it.origin.peer + " — clearing this card also clears their linked entry") + " · click opens the session";
    const sid = it.origin.peerSid; og.onclick = (ev: Event) => { ev.stopPropagation(); env.openSession(sid); };
    out.push(og);
  }
  if (it.handoffTo && it.handoffTo.peerSid) {
    const og = el("a", "fask-origin");
    const pre = el("span", "fask-origin-pre"); pre.textContent = "↪ delegated to ";
    const peer = el("span", "fask-origin-peer"); peer.replaceChildren(...hostPartsNodes(it.handoffTo.peerHost, it.handoffTo.peer)); if (it.handoffTo.color && it.handoffTo.color.bg) peer.style.color = it.handoffTo.color.bg;
    og.append(pre, peer); og.title = "this card's work was handed to " + it.handoffTo.peer + " · click opens the session";
    const sid = it.handoffTo.peerSid; og.onclick = (ev: Event) => { ev.stopPropagation(); env.openSession(sid); };
    out.push(og);
  }
  return out;
}
