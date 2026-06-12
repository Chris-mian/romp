// romp feed — a stream of rounded "deliverable cards" on a backdrop. Each card is
// ONE deliverable (a turn's "did" phrase) from some session, newest on top. The
// session name links to that session's tab; the checkbox dismisses the card; the
// message expands to a (pre-generated) action paragraph.
//
// Rendering is KEYED + INCREMENTAL: cards are kept alive across the host's live
// pushes and updated in place — never torn down — so hovering one doesn't flicker
// when the fleet streams new deliverables in.

interface FeedItem {
  itemId: string;
  sid: string;
  name: string;
  color: { bg: string; fg: string } | null;
  did: string;
  ask: string;
  t: number;            // epoch seconds
  live: boolean;
  trgb: [number, number, number];   // hawaii recency color — tints the CARD background
  relevance: "DONE" | "DECISION" | "DETAILS" | "UNTAGGED";
  origin?: "user" | "agent";        // who prompted the turn: the user typed vs a peer's message
  inAsk?: boolean;                  // this reply is linked into some ask → renders inside it, not standalone
  standalone?: boolean;             // host-computed standalone-card eligibility (user-origin + DONE/DECISION + unlinked + past REQUESTS_FLOOR)
}

// Relevance: a per-card colored label (DONE/DECISION/DETAILS; UNTAGGED gets none)
// PLUS header toggle "badges" that turn each class off/on. All on by default;
// UNTAGGED is always visible (no toggle). Per-card dismiss is separate curation.
const RELEVANCES = ["DONE", "DECISION", "DETAILS"] as const;
const RELEVANCE_LABEL: Record<string, string> = { DONE: "done", DECISION: "decision", DETAILS: "details" };
const relevanceFilter = new Set<string>(RELEVANCES);

// Origin: agent-prompted turns (peer postal messages, not the user's asks) are
// HIDDEN by default — the feed is the user's inbox, not the fleet's internal chatter.
// The header "internal N" chip toggles them back on.
let showInternal = false;

// Asks inbox (the DEFAULT view; request registry REQUESTS.md): one persistent
// card per OPEN ask of the user's, sorted into THREE state columns derived from each
// ask's newest link. Clear (the user-only, binary) removes it — inbox-zero. The
// deliverables stream is the safety-net behind the header toggle.
interface AskLinked { did: string; relevance: string; t: number; reply_id: string; status: "done" | "question" | "update"; sid: string; name: string; color?: { bg: string; fg: string } | null; trgb?: [number, number, number]; answer?: boolean }
interface DecisionBrief { context: string; question: string; options: string[] | null; sid: string; t: number }
interface AskQuestion { reply_id: string; sid: string; name: string; t: number; brief: DecisionBrief | null; qtype?: "decision" | "action" | "idea"; nodeId?: string }
interface AskPath { name: string; sid: string; color: { bg: string; fg: string } | null; since: number; lastPhrase: string }
// One node of the ask's request DAG (flat list, root first; nest via children ids;
// a node under two parents appears in both → render twice, dim the repeat).
interface AskTreeNode {
  id: string; kind: "ask" | "handoff"; text: string; who: string;
  whoSid: string; whoColor: { bg: string; fg: string } | null;   // agent → colored session link
  whoWorking?: boolean;                                          // that agent is currently WORKING → yellow dot before its name
  status: "done" | "question" | "open"; t: number; last: number;
  trgb?: [number, number, number];                               // last-activity recency tint (timestamp)
  children: string[]; rows: AskLinked[];
}
interface AskItem {
  itemId: string; sid: string; name: string; color: { bg: string; fg: string } | null;
  text: string; t: number; created: number; live: boolean;
  done: number; needsYou: number; linked: AskLinked[]; turnId: string;
  trgb: [number, number, number];
  column: "asks" | "needs_input" | "completed";   // host-decided (DAG path accounting), not newest-link
  openQuestions: AskQuestion[];                    // live unanswered DECISIONs → decision sub-cards
  openPaths: AskPath[];                            // open leaves → "waiting on X" drop-point lines
  reopened?: boolean;                              // resurrected: a question arrived AFTER the user cleared it
  // liveness reveal (host-computed, decides nothing): outline color = what an
  // automated "still being worked?" rule WOULD say; the tooltip carries the why.
  liveness?: "active" | "delegated" | "stalled" | "settled";
  livenessWhy?: string;
  autoFiled?: boolean;                             // settled → moved to COMPLETED by the auto-filing rule (keeps the green ring)
  explicitDone?: boolean;                          // every path explicitly DONE-stamped → blue ring (blue+green when settled agrees)
  waiting?: boolean;                               // paused on an EXTERNAL event → held in Working, ⏳ chip, no ring
  turnIds?: string[];                              // typed turns that minted/amended this card
  // the owning session is live-blocked (permission/picker) ON this card's work →
  // the card itself files under BLOCKED (the user's ruling 2026-06-11)
  blocked?: { state: string; since: number; what: string };
  suspects?: Array<{ mid: string; to: string; t: number; snippet: string; why: string }>;  // ⚠ possible missed handoffs (host sweep)
  groupTitle?: string;                             // host: this ask shares a typed turn with siblings → the group's title
  groupN?: number;                                 // host: sibling count for that turn (>1 ⇒ fold into one group card)
  tree: AskTreeNode[];                             // the ask's DAG, rendered as a tree in the expanded body
}
// A GROUP = N sibling asks minted by ONE typed turn (shared turnId), folded into a
// single card. DERIVED at render time from the current asks, so membership shrinks
// as the user clears members (a lone survivor falls back to a normal single card).
interface AskGroup {
  turnId: string; title: string; members: AskItem[];   // members sorted chronologically
  name: string; color: { bg: string; fg: string } | null; sid: string;   // shared asking session
  t: number; trgb: [number, number, number]; column: Column; live: boolean;
}
let asks: AskItem[] = [];
let viewAsks = true;           // asks inbox is the default; deliverables behind the toggle
const expandedAsks = new Set<string>();
// Per-node collapse state, key = askId + ":" + nodeId. INVERTED sense: a node is
// EXPANDED (its history rows AND its descendant subtree visible) by default;
// collapsing it adds the key here and hides its WHOLE subtree. Empty set = the
// tree is fully open, which matches the always-expanded look it had before
// collapse was deepened to cover children, not just rows.
const collapsedNodes = new Set<string>();
let fullscreenAskId: string | null = null; // ask itemId OR group key "g:<turnId>" shown in the modal (single-click)
let modalRenderedId: string | null = null; // last target the modal body was built for → reset body cache on change
let hoverAskId: string | null = null;      // transient hover focus (white border + previewed journey)
let pinnedAskId: string | null = null;     // double-click PIN (persists after hover-leave)
// effective focus = hover ?? pinned; the white border + lit timeline journey follow it.
function applyFocus() {
  const eff = hoverAskId ?? pinnedAskId;
  for (const [id, card] of askEls) card.classList.toggle("focused", id === eff);
  for (const [tid, card] of groupEls) card.classList.toggle("focused", "g:" + tid === eff);
}
const askEls = new Map<string, HTMLElement>();
// Group cards keyed by turnId, stored under "g:"+turnId. The focus state
// (hoverAskId/pinnedAskId) holds EITHER a raw ask itemId OR a group key
// "g:"+turnId; applyFocus + focusAnchorId understand both.
const groupEls = new Map<string, HTMLElement>();

// A session LIVE-blocked on the user (permission prompt / stuck picker) — a session
// STATE, not an ask. Rendered as a distinct card pinned to the top of NEEDS INPUT;
// no Clear (self-resolves when the user acts), whole-card click → openSession.
interface Blocked {
  sid: string; name: string; color: { bg: string; fg: string } | null;
  state: "permission" | "picker"; since: number; what: string;
}
let blocked: Blocked[] = [];
const blockedEls = new Map<string, HTMLElement>();

// The three columns. The HOST decides each ask's column by DAG path accounting
// (completed only when every subgraph node is DONE); we just map its snake_case.
type Column = "asks" | "needsInput" | "completed";
function askColumn(it: AskItem): Column {
  if (it.blocked) return "needsInput";   // a live permission/picker block files the card under BLOCKED
  return it.column === "needs_input" ? "needsInput" : it.column === "completed" ? "completed" : "asks";
}

// How opaque the recency tint is over the (black) page — low = a faint, very
// see-through wash of the hawaii color; the colormap itself darkens with age.
const TINT_ALPHA = 0.22;
interface Detail { id: string; t?: number; paragraph: string; next_steps?: string[]; src?: string; }
type DetailState = { state: "loading" | "ready" | "failed"; reason?: string; data?: Detail };

const vscodeApi =
  typeof (window as any).acquireVsCodeApi === "function" ? (window as any).acquireVsCodeApi() : undefined;

let items: FeedItem[] = [];
// names of sessions currently WORKING → a working dot before that name everywhere
// it renders (card titles, modal title, group name). Pushed in each feed message.
let workingSet = new Set<string>();
// Ensure a `.fwork-dot` sits immediately before `nameEl` iff `on` (idempotent on
// re-render). The name's own text/color are untouched.
function setWorkDot(nameEl: HTMLElement | null, on: boolean) {
  if (!nameEl) return;
  const prev = nameEl.previousElementSibling;
  const has = !!prev && prev.classList.contains("fwork-dot");
  if (on && !has) nameEl.parentElement?.insertBefore(el("span", "fwork-dot"), nameEl);
  else if (!on && has) prev!.remove();
}
let hostNow = Math.floor(Date.now() / 1000);
let showDismissed = false;
let dismissedCount = 0;
let canUndoClear = false;   // host: cleared.jsonl has rows → the UndoClear button shows
// Expand-for-detail: which items are open, plus the per-item detail we've fetched.
// Both survive a host re-render (render() reconstructs the open blocks from these).
const expanded = new Set<string>();
const details = new Map<string, DetailState>();
const cardEls = new Map<string, HTMLElement>();   // itemId -> live card element (reused)

function el(tag: string, cls?: string): HTMLElement {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  return e;
}

function relAge(sec: number): string {
  const s = Math.max(0, sec);
  if (s < 60) return `${Math.round(s)}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

function dayLabel(t: number, now: number): string {
  const d = new Date(t * 1000);
  const ymd = (x: Date) => `${x.getFullYear()}-${x.getMonth()}-${x.getDate()}`;
  if (ymd(d) === ymd(new Date(now * 1000))) return "Today";
  if (ymd(d) === ymd(new Date((now - 86400) * 1000))) return "Yesterday";
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

// ---- header (built once, then updated in place): title + "N need input" + live ----
let headerBuilt = false;
let elTitle: HTMLElement, elMeta: HTMLElement;

function ensureHeader() {
  if (headerBuilt) return;
  const head = document.getElementById("feed-head")!;
  head.innerHTML = "";
  elTitle = el("span", "fh-title"); elTitle.textContent = "romp";
  elMeta = el("span", "fh-meta");
  head.append(elTitle, elMeta);    // no toggles, chips, or buttons — one view, nothing clickable
  headerBuilt = true;
}

// Standalone deliverable cards: a user-origin reply NOT linked to any ask, tagged
// DONE or DECISION (the granular/unexpected work the user never explicitly asked
// for). Linked replies, agent-internal turns, and routine (details) turns never
// get their own card.
function standaloneItems(): FeedItem[] {
  return items.filter((i) => i.standalone);   // host-computed (gated by REQUESTS_FLOOR) — avoids flooding the columns with pre-registry backlog
}

function updateHeader() {
  ensureHeader();
  // "N need input" = the actionable count: asks whose newest link is a DECISION
  // plus standalone DECISION deliverables (everything sitting in column 2).
  const needInput = asks.filter((a) => askColumn(a) === "needsInput").length
    + standaloneItems().filter((i) => i.relevance === "DECISION").length;
  const liveN = new Set([
    ...asks.filter((a) => a.live).map((a) => a.sid),
    ...items.filter((i) => i.live).map((i) => i.sid),
  ]).size;
  elMeta.innerHTML = `<span class="fh-need">${needInput} need input</span>`
    + (liveN ? ` · <span class="fh-live">${liveN} live</span>` : ``);
}

// ---- standalone deliverable card (same v2 anatomy as an ask card) ----
// row 1 = deliverable text + age; row 2 = owner name + [+] [Clear] right-aligned
// (no tally — a standalone deliverable has no subgraph). Clear shares the asks'
// cleared.jsonl (reply ids work in askClear). Whole-card click locates the turn.
function makeCard(it: FeedItem): HTMLElement {
  const card = el("div", "fitem");
  card.dataset.key = "i:" + it.itemId;
  card.dataset.id = it.itemId;
  card.title = "click for detail";

  const main = el("div", "fitem-main");
  const row1 = el("div", "fask-row1");
  const title = el("div", "fcard-title nav");      // the deliverable phrase (headline)
  title.title = "jump to this on the timeline";
  const time = el("span", "ftime");
  row1.append(title, time);
  const row2 = el("div", "fask-row2");
  const idwrap = el("div", "fask-id");
  const name = el("a", "fname"); name.title = "open this session";
  idwrap.append(name);
  const actions = el("div", "fask-actions");
  const clr = el("button", "fdismiss"); clr.textContent = "Clear"; clr.title = "clear this item (inbox-zero)";
  actions.append(clr);
  row2.append(idwrap, actions);
  main.append(row1, row2);
  card.append(main);

  // same click model as ask cards: body → modal, title → locate the originating
  // REQUEST (anchor:'prompt'), i.e. where the user wrote it — not the agent's work line.
  // The deliverable's itemId IS its typed turn (request + reply share the id), so the
  // anchor just selects the prompt glyph over the work bar.
  card.onclick = () => { fullscreenAskId = "i:" + it.itemId; renderModal(); };
  title.onclick = (ev) => { ev.stopPropagation(); vscodeApi?.postMessage({ type: "showOnTimeline", itemId: it.itemId, sid: it.sid, t: it.t, anchor: "prompt" }); };
  name.onclick = (ev) => { ev.stopPropagation(); vscodeApi?.postMessage({ type: "openSession", id: it.sid }); };
  clr.onclick = (ev) => {
    ev.stopPropagation();
    card.classList.add("dismissing");
    vscodeApi?.postMessage({ type: "askClear", itemId: it.itemId });   // reply ids share cleared.jsonl
    setTimeout(() => { if (cardEls.get(it.itemId) === card && card.classList.contains("dismissing")) { card.remove(); cardEls.delete(it.itemId); } }, 180);
  };

  const a = card as any;
  a._time = time; a._name = name; a._title = title;
  return card;
}

function updateCard(card: HTMLElement, it: FeedItem) {
  const a = card as any;
  card.className = "fitem" + (it.live ? " live" : " dead");
  const [r, g, b] = it.trgb;
  card.style.background = `rgba(${r}, ${g}, ${b}, ${TINT_ALPHA})`;
  card.style.borderColor = `rgba(${r}, ${g}, ${b}, ${Math.min(TINT_ALPHA + 0.2, 0.9)})`;
  a._title.textContent = it.did;
  a._name.textContent = it.name;
  if (it.color) a._name.style.color = it.color.bg;
  setWorkDot(a._name, workingSet.has(it.name));   // working dot before the session name
  a._time.textContent = relAge(hostNow - it.t);
}

// ---- expand → detail ----
function toggleExpand(id: string) {
  if (expanded.has(id)) { expanded.delete(id); render(); return; }
  expanded.add(id);
  const d = details.get(id);
  if (!d || d.state === "failed") {       // not fetched yet, or retry after a failure
    const it = items.find((i) => i.itemId === id);
    // Only DONE/DECISION get a generated paragraph; DETAILS/UNTAGGED don't, so the
    // host reads cache-only for them and never spawns (no "generating…" wait).
    const generate = it ? (it.relevance === "DONE" || it.relevance === "DECISION") : false;
    details.set(id, { state: "loading" });
    vscodeApi?.postMessage({ type: "expand", itemId: id, generate });
  }
  render();
}

// Expanded view: the ASK (original request) on top, the RESPONSE below it.
// Response = the generated detail paragraph for DONE/DECISION; for routine items
// (no paragraph) it falls back to the deliverable summary. Signature-guarded so an
// open, hovered card never flickers on a host repush.
function renderExpandInto(slot: HTMLElement, it: FeedItem) {
  const d = details.get(it.itemId);
  const respSig = !d || d.state === "loading" ? "loading"
    : d.state === "failed" ? "f:" + (d.reason || "")
    : "r:" + (d.data?.paragraph || "") + "¦" + (d.data?.next_steps || []).join("¦");
  const sig = "a:" + it.ask + "||" + respSig;
  if ((slot as any)._sig === sig) return;
  (slot as any)._sig = sig;
  slot.innerHTML = "";
  const box = el("div", "fexpand");

  // ASK (top)
  const askWrap = el("div", "fx-ask");
  const askLab = el("div", "fx-label"); askLab.textContent = "Ask";
  const askBody = el("div", "fx-body"); askBody.textContent = it.ask || "(no recorded request)";
  askWrap.append(askLab, askBody);
  box.appendChild(askWrap);

  // RESPONSE (below)
  const respWrap = el("div", "fx-resp");
  const respLab = el("div", "fx-label"); respLab.textContent = "Response";
  respWrap.appendChild(respLab);
  if (!d || d.state === "loading") {
    const b = el("div", "fx-body loading"); b.textContent = "Generating…"; respWrap.appendChild(b);
  } else if (d.state === "failed") {
    // routine/legacy → no paragraph; the deliverable summary IS the response
    const b = el("div", "fx-body"); b.textContent = it.did; respWrap.appendChild(b);
  } else {
    const para = el("div", "fx-body"); para.textContent = d.data!.paragraph; respWrap.appendChild(para);
    if (Array.isArray(d.data!.next_steps) && d.data!.next_steps.length) {
      const ul = el("ul", "fdetail-steps");
      for (const s of d.data!.next_steps) { const li = document.createElement("li"); li.textContent = s; ul.appendChild(li); }
      respWrap.appendChild(ul);
    }
  }
  box.appendChild(respWrap);
  slot.appendChild(box);
}

// ---- ask cards (the inbox unit) ----
// Anatomy: row 1 = ask text (bold, full width) + age top-right; row 2 = owner name
// (identity color, clickable) + evidence tally text, with [+] and [Clear] right-
// ---- ask card (the inbox unit) ----
// Collapsed: row1 = ask text + age; row2 = worker name + reopened badge | Clear
// (no [+], no tally). Click the CARD → expand + light the DAG path on the timeline.
// Expanded body = the request DAG as a tree of NODES (state machine only); each
// node clicks to reveal its OWN reply history; ? nodes carry a decision sub-card.
function makeAskCard(it: AskItem): HTMLElement {
  const card = el("div", "fitem ask");
  card.dataset.key = "a:" + it.itemId;

  const main = el("div", "fitem-main");
  // ROW 1 — ask title (left, hit-area fits its text) · age (top right)
  const row1 = el("div", "fask-row1");
  const title = el("div", "fcard-title nav"); title.title = "locate this in the text";
  const time = el("span", "ftime");
  row1.append(title, time);
  // ROW 2 — agent (left, hit-area fits its text) · [reopened?] [Clear] (right)
  const row2 = el("div", "fask-row2");
  const idwrap = el("div", "fask-id");
  const name = el("a", "fname"); name.title = "open this session";
  idwrap.append(name);
  const actions = el("div", "fask-actions");
  const reBadge = el("span", "fask-reopened"); reBadge.textContent = "reopened"; reBadge.title = "a question arrived after you cleared this"; reBadge.style.display = "none";
  const blkBadge = el("a", "fask-blocked"); blkBadge.style.display = "none";   // ⏸ live permission/picker block → click opens the session
  const waitBadge = el("span", "fask-wait"); waitBadge.textContent = "⏳ waiting"; waitBadge.style.display = "none";
  waitBadge.title = "paused on an EXTERNAL event (CI, build, a peer's reply) — not on you; stays in Working, exempt from auto-filing; lifts when new work lands";
  const suspBadge = el("a", "fask-suspect"); suspBadge.style.display = "none";   // ⚠ possible missed handoff → modal evidence + Report
  const stallBadge = el("a", "fask-suspect"); stallBadge.style.display = "none"; // ⚠ stalled delegation (exception bucket, formerly a dashed ring)
  const clr = el("button", "fdismiss"); clr.textContent = "Clear"; clr.title = "clear this ask (inbox-zero; the one human-asserted fact)";
  actions.append(stallBadge, suspBadge, waitBadge, blkBadge, reBadge, clr);
  row2.append(idwrap, actions);
  // the user's handoff spec (2026-06-10): below the main session, list the OTHER
  // sessions this ask was handed to — but only while they are LIVE-WORKING on
  // an unfinished branch. Idle or finished recipients disappear; presence on
  // the list therefore always means active, so the dot is always on.
  const handoffs = el("div", "fask-handoffs");
  main.append(row1, row2, handoffs);        // no expand button — body click opens the modal
  card.append(main);
  // Follow-up lives in the modal now (the user 2026-06-10), not on the card.

  // title → locate the typed turn; agent → open session; Clear → inbox-zero. These
  // stopPropagation so the card-body single/double handlers don't also fire.
  title.onclick = (ev) => { ev.stopPropagation(); vscodeApi?.postMessage({ type: "showAskPath", itemId: it.itemId }); };
  name.onclick = (ev) => { ev.stopPropagation(); vscodeApi?.postMessage({ type: "openSession", id: it.sid }); };
  clr.onclick = (ev) => {
    ev.stopPropagation();
    card.classList.add("dismissing");
    vscodeApi?.postMessage({ type: "askClear", itemId: it.itemId });
    setTimeout(() => { if (askEls.get(it.itemId) === card && card.classList.contains("dismissing")) { card.remove(); askEls.delete(it.itemId); } }, 180);
  };
  // HOVER (120ms intent debounce so sweeps don't spam) → white border + preview
  // this card's timeline journey. LEAVE → restore the pinned card's journey, or
  // clear if none pinned.
  let hoverTimer: number | undefined;
  card.addEventListener("mouseenter", () => {
    hoverTimer = window.setTimeout(() => {
      hoverTimer = undefined;
      hoverAskId = it.itemId; applyFocus();
      vscodeApi?.postMessage({ type: "showAskPath", itemId: it.itemId, locate: false });
    }, 120);
  });
  card.addEventListener("mouseleave", () => {
    if (hoverTimer) { clearTimeout(hoverTimer); hoverTimer = undefined; }
    if (hoverAskId === it.itemId) {
      hoverAskId = null; applyFocus();
      const pin = focusAnchorId(pinnedAskId);
      if (pin) vscodeApi?.postMessage({ type: "showAskPath", itemId: pin, locate: false });   // back to the pin (ask or group)
      else vscodeApi?.postMessage({ type: "showAskPath", itemId: it.itemId, off: true });      // clear
    }
  });
  // card BODY single click → open the modal; double click → pin/unpin (locks the
  // journey in place; hovering others still previews, leave returns to the pin).
  // Debounced ~220ms so a double never opens the modal first.
  let pending: number | undefined;
  card.addEventListener("click", () => {
    if (pending) { clearTimeout(pending); pending = undefined; return; }   // 2nd click — let dblclick handle it
    pending = window.setTimeout(() => {
      pending = undefined;
      fullscreenAskId = it.itemId;
      vscodeApi?.postMessage({ type: "showAskPath", itemId: it.itemId, locate: false });
      render();
    }, 220);
  });
  card.addEventListener("dblclick", () => {
    if (pending) { clearTimeout(pending); pending = undefined; }
    pinnedAskId = pinnedAskId === it.itemId ? null : it.itemId;
    applyFocus();
    // double-click = PIN + jump the TIMELINE to the painted DAG (the user's
    // ruling: hover/single-click only highlight; only a double pans)
    if (pinnedAskId === it.itemId) vscodeApi?.postMessage({ type: "showAskPath", itemId: it.itemId, locate: false, jump: true });
    else if (!pinnedAskId && hoverAskId !== it.itemId) vscodeApi?.postMessage({ type: "showAskPath", itemId: it.itemId, off: true });
  });

  const a = card as any;
  a._title = title; a._name = name; a._time = time; a._reopened = reBadge;
  a._blocked = blkBadge; a._wait = waitBadge; a._susp = suspBadge; a._stall = stallBadge;
  a._handoffs = handoffs;
  return card;
}

function updateAskCard(card: HTMLElement, it: AskItem) {
  const a = card as any;
  const anom = lvAnomaly(it);
  card.className = "fitem ask" + (it.live ? " live" : " dead") + (it.itemId === (hoverAskId ?? pinnedAskId) ? " focused" : "") + (it.itemId === pinnedAskId ? " pinned" : "")
    + (anom ? " lv-" + anom : "");
  card.title = it.livenessWhy ? `${it.liveness}: ${it.livenessWhy}` : "";
  const [r, g, b] = it.trgb;
  card.style.background = `rgba(${r}, ${g}, ${b}, ${TINT_ALPHA})`;
  card.style.borderColor = `rgba(${r}, ${g}, ${b}, ${Math.min(TINT_ALPHA + 0.2, 0.9)})`;
  a._title.textContent = it.text;
  a._name.textContent = it.name;
  if (it.color) a._name.style.color = it.color.bg;
  setWorkDot(a._name, workingSet.has(it.name));   // working dot before the session name
  a._time.textContent = relAge(hostNow - it.t);
  a._reopened.style.display = it.reopened ? "" : "none";
  a._wait.style.display = it.waiting ? "" : "none";   // ⏳ paused on an external event
  // ⚠ stalled: an unfinished delegation nobody is working — exception bucket
  // (the user 2026-06-12-eve: this is a should-not-happen, not a ring)
  const stalled = it.liveness === "stalled" && askColumn(it) === "asks";
  a._stall.style.display = stalled ? "" : "none";
  if (stalled) {
    a._stall.textContent = "⚠ stalled";
    a._stall.title = (it.livenessWhy || "an unfinished handoff nobody is working") + " — nudge or revive that session, mark done if moot, or file a report";
    a._stall.onclick = (ev: Event) => { ev.stopPropagation(); fullscreenAskId = it.itemId; renderModal(); };
  }
  // ⚠ possible missed handoff: deterministic-sweep evidence → review + report in the modal
  const sn = it.suspects?.length || 0;
  a._susp.style.display = sn ? "" : "none";
  if (sn) {
    a._susp.textContent = sn > 1 ? `⚠ ${sn} handoffs?` : "⚠ handoff?";
    a._susp.title = it.suspects![0].why + " — click to review the evidence and file a report";
    a._susp.onclick = (ev: Event) => { ev.stopPropagation(); fullscreenAskId = it.itemId; renderModal(); };
  }
  // ⏸ live block badge: the session is stopped mid-turn on a permission prompt /
  // picker FOR THIS CARD's work — the card files under BLOCKED while it lasts
  a._blocked.style.display = it.blocked ? "" : "none";
  if (it.blocked) {
    a._blocked.textContent = it.blocked.state === "permission" ? "⏸ approval" : "⏸ picker";
    a._blocked.title = it.blocked.what + " — click to open the session";
    a._blocked.onclick = (ev: Event) => { ev.stopPropagation(); vscodeApi?.postMessage({ type: "openSession", id: it.sid }); };
  }
  // the user's handoff spec (2026-06-10): every session this ask was handed to,
  // ANYWHERE in its tree (not just the last hop), shown below the main session
  // — bold, identity color, always with the working dot — but ONLY while that
  // session is live-working and its branch is unfinished. Idle or finished →
  // the line disappears. The main session stays on its own row above.
  const ho = a._handoffs as HTMLElement;
  ho.innerHTML = "";
  const hseen = new Set<string>();
  for (const n of it.tree || []) {
    if (n.kind !== "handoff" || n.status === "done") continue;       // finished branch → gone
    if (!n.whoSid || n.who === it.name || hseen.has(n.whoSid)) continue;
    if (!workingSet.has(n.who)) continue;                            // idle → gone
    hseen.add(n.whoSid);
    const line = el("div", "fask-handoff-line");
    const nm = el("a", "fask-handoff"); nm.textContent = n.who;
    if (n.whoColor) nm.style.color = n.whoColor.bg;
    nm.title = n.text || "open this session";
    nm.onclick = (ev) => { ev.stopPropagation(); vscodeApi?.postMessage({ type: "openSession", id: n.whoSid }); };
    line.appendChild(nm);
    setWorkDot(nm, true);                  // presence == actively working, dot always on
    ho.appendChild(line);
  }
  ho.style.display = ho.children.length ? "" : "none";
}

// Resolve a focus key (set on hoverAskId/pinnedAskId) to the itemId the timeline
// path-preview understands: a raw ask id maps to itself; a group key "g:<turnId>"
// maps to its FIRST (chronological) live member (v1 — siblings share the turn).
// Returns null if the key is empty or the group has no live members left.
function focusAnchorId(key: string | null): string | null {
  if (!key) return null;
  if (key.startsWith("g:")) {
    const tid = key.slice(2);
    // by turnId only — finds the survivor even after a dissolving group's members lose groupTitle
    const members = asks.filter((a) => a.turnId === tid).sort((a, b) => a.t - b.t);
    return members.length ? members[0].itemId : null;
  }
  return key;
}

// Liveness ANOMALY (the user's simplification, 2026-06-11): ring a card only when
// its computed liveness DISAGREES with the column it's filed in — agreement is
// the normal case and carries no information.
//   ASKS + settled    → green ring: nothing can move this without you; it really
//                       belongs in COMPLETED (or AWAITING) — likely a missed DONE.
//   ASKS + stalled    → dashed orange ring: an unfinished handoff nobody is
//                       working — a dropped delegation that will never finish.
//   COMPLETED + active → gold ring: filed done, but the owning session is mid-turn
//                       — it may still be chewing on this.
// Everything else (active/delegated in ASKS, anything in AWAITING) is expected:
// no ring. delegated/stalled are impossible in COMPLETED by construction (an
// unfinished handoff keeps the fold from completing). Tooltips stay on every card.
// Rings (the user's simplification, 2026-06-12-eve): rings exist ONLY in
// COMPLETED, where every card arrived one of two ways — the judge model stamped
// it done, or the auto-filer noticed nothing was moving it. Agreement is the
// expected state and gets NO ink:
//   no ring          = judged done AND settled — both agree; Clear with confidence
//   green            = auto-filed only — the judge never stamped it; verify, then
//                      Clear (right) or Follow up (wrong); either click is a label
//   blue             = judged done only — not settled yet (often still mid-turn
//                      on it, or waiting); glance before clearing
// Everything formerly ring-coded in WORKING is now either invisible (settled
// auto-files within a tick) or an amber ⚠ badge (stalled = exception bucket).
function lvAnomaly(it: AskItem): "settled" | "done" | null {
  if (askColumn(it) !== "completed") return null;
  const auto = !!it.autoFiled || it.liveness === "settled";
  const judged = !!it.explicitDone;
  if (judged && auto) return null;
  if (auto) return "settled";
  if (judged) return "done";
  return null;
}

// A member's rolled-up status → the chat-timeline mark vocabulary (● done /
// ? needs the user / ○ not finished), derived from the host's per-ask column.
function memberStatus(m: AskItem): "done" | "question" | "open" {
  const c = askColumn(m);
  return c === "completed" ? "done" : c === "needsInput" ? "question" : "open";
}
function memberMark(m: AskItem): string {
  const s = memberStatus(m);
  return s === "done" ? "●" : s === "question" ? "?" : "○";
}

// Fold N sibling asks (shared turnId) into one AskGroup. Column = WORST member
// (any needs-input → needsInput; else any open → asks; else completed). Identity
// (name/color/sid) is the shared asking session; age/tint follow the newest member.
function buildGroup(turnId: string, members: AskItem[]): AskGroup {
  const ms = members.slice().sort((a, b) => a.t - b.t);                       // chronological
  const repr = ms.reduce((x, y) => (y.t > x.t ? y : x), ms[0]);               // most-recent → freshest age/tint
  const column: Column = ms.some((m) => askColumn(m) === "needsInput") ? "needsInput"
    : ms.some((m) => askColumn(m) === "asks") ? "asks" : "completed";
  return {
    turnId, title: ms[0].groupTitle || ms[0].text, members: ms,
    name: ms[0].name, color: ms[0].color, sid: ms[0].sid,
    t: repr.t, trgb: repr.trgb, column, live: ms.some((m) => m.live),
  };
}

// ---- grouped sibling-asks card ----
// One card for a whole typed turn that minted several asks: title = the turn
// summary; one line per member (status circle + member text), the circles filling
// in (○ → ●) as each sub-part completes. Body click → modal (members stacked).
// Clear clears EVERY member. Hover/pin/focus mirror the ask card, keyed by group.
function makeGroupCard(g: AskGroup): HTMLElement {
  const card = el("div", "fitem ask fgroup");
  card.dataset.key = "g:" + g.turnId;
  const fkey = "g:" + g.turnId;

  const main = el("div", "fitem-main");
  const row1 = el("div", "fask-row1");
  const title = el("div", "fcard-title nav"); title.title = "locate this in the text";
  const time = el("span", "ftime");
  row1.append(title, time);
  const row2 = el("div", "fask-row2");
  const idwrap = el("div", "fask-id");
  const name = el("a", "fname"); name.title = "open this session";
  const count = el("span", "fgroup-count");
  idwrap.append(name, count);
  const actions = el("div", "fask-actions");
  const clr = el("button", "fdismiss"); clr.textContent = "Clear"; clr.title = "clear ALL sub-asks of this request (inbox-zero)";
  actions.append(clr);
  row2.append(idwrap, actions);
  const memberList = el("div", "fgroup-members");
  main.append(row1, row2, memberList);
  card.append(main);

  const m0 = () => ((card as any)._g as AskGroup | undefined)?.members?.[0];
  title.onclick = (ev) => { ev.stopPropagation(); const m = m0(); if (m) vscodeApi?.postMessage({ type: "showAskPath", itemId: m.itemId }); };
  name.onclick = (ev) => { ev.stopPropagation(); const cur = (card as any)._g as AskGroup; if (cur?.sid) vscodeApi?.postMessage({ type: "openSession", id: cur.sid }); };
  clr.onclick = (ev) => {
    ev.stopPropagation();
    const cur = (card as any)._g as AskGroup;
    card.classList.add("dismissing");
    for (const m of cur.members) vscodeApi?.postMessage({ type: "askClear", itemId: m.itemId });   // clear every member
    // only finalize if a render in the 180ms window didn't revive (re-render clears
    // .dismissing) or replace this card — else a stale timeout yanks the wrong one
    setTimeout(() => { if (groupEls.get(cur.turnId) === card && card.classList.contains("dismissing")) { card.remove(); groupEls.delete(cur.turnId); } }, 180);
  };
  // hover (120ms intent) → white border + preview the group's timeline journey
  // (first member). leave → restore the pin (ask OR group) or clear.
  let hoverTimer: number | undefined;
  card.addEventListener("mouseenter", () => {
    hoverTimer = window.setTimeout(() => {
      hoverTimer = undefined;
      hoverAskId = fkey; applyFocus();
      const m = m0(); if (m) vscodeApi?.postMessage({ type: "showAskPath", itemId: m.itemId, locate: false });
    }, 120);
  });
  card.addEventListener("mouseleave", () => {
    if (hoverTimer) { clearTimeout(hoverTimer); hoverTimer = undefined; }
    if (hoverAskId === fkey) {
      hoverAskId = null; applyFocus();
      const pin = focusAnchorId(pinnedAskId);
      if (pin) vscodeApi?.postMessage({ type: "showAskPath", itemId: pin, locate: false });
      else { const m = m0(); if (m) vscodeApi?.postMessage({ type: "showAskPath", itemId: m.itemId, off: true }); }
    }
  });
  // body single-click → modal; double-click → pin/unpin (debounced ~220ms).
  let pending: number | undefined;
  card.addEventListener("click", () => {
    if (pending) { clearTimeout(pending); pending = undefined; return; }
    pending = window.setTimeout(() => {
      pending = undefined;
      fullscreenAskId = fkey;
      const m = m0(); if (m) vscodeApi?.postMessage({ type: "showAskPath", itemId: m.itemId, locate: false });
      render();
    }, 220);
  });
  card.addEventListener("dblclick", () => {
    if (pending) { clearTimeout(pending); pending = undefined; }
    pinnedAskId = pinnedAskId === fkey ? null : fkey;
    applyFocus();
    const m = m0();
    // double-click = PIN + jump the TIMELINE (same contract as single cards)
    if (pinnedAskId === fkey && m) vscodeApi?.postMessage({ type: "showAskPath", itemId: m.itemId, locate: false, jump: true });
    else if (!pinnedAskId && hoverAskId !== fkey && m) vscodeApi?.postMessage({ type: "showAskPath", itemId: m.itemId, off: true });
  });

  const a = card as any;
  a._title = title; a._name = name; a._time = time; a._count = count; a._members = memberList;
  return card;
}

function updateGroupCard(card: HTMLElement, g: AskGroup) {
  const a = card as any;
  a._g = g;                                          // current group for the (reused) handlers
  const fkey = "g:" + g.turnId;
  const eff = hoverAskId ?? pinnedAskId;
  // group ring = the first member whose liveness disagrees with its column
  // (anomalies only, like single cards); agreement renders nothing
  let lv: ReturnType<typeof lvAnomaly> = null; let lvWhy = "";
  for (const m of g.members) {
    const a = lvAnomaly(m);
    if (a) { lv = a; lvWhy = m.livenessWhy || ""; break; }
  }
  card.className = "fitem ask fgroup" + (g.live ? " live" : " dead")
    + (fkey === eff ? " focused" : "") + (fkey === pinnedAskId ? " pinned" : "")
    + (lv ? " lv-" + lv : "");
  card.title = lvWhy ? `${lv}: ${lvWhy}` : "";
  const [r, gg, b] = g.trgb;
  card.style.background = `rgba(${r}, ${gg}, ${b}, ${TINT_ALPHA})`;
  card.style.borderColor = `rgba(${r}, ${gg}, ${b}, ${Math.min(TINT_ALPHA + 0.2, 0.9)})`;
  a._title.textContent = g.title;
  a._name.textContent = g.name;
  if (g.color) a._name.style.color = g.color.bg;
  setWorkDot(a._name, workingSet.has(g.name));   // working dot before the session name
  a._time.textContent = relAge(hostNow - g.t);
  a._count.textContent = "· " + g.members.length + " parts";
  // member lines — rebuilt only when the member set or any member's status changes
  const memSig = g.members.map((m) => m.itemId + ":" + memberStatus(m)).join("|");
  if (a._memSig !== memSig) {
    a._memSig = memSig;
    const host = a._members as HTMLElement; host.innerHTML = "";
    for (const m of g.members) {
      const line = el("div", "fgroup-member st-" + memberStatus(m));
      const dot = el("span", "fgroup-dot"); dot.textContent = memberMark(m); line.appendChild(dot);
      const txt = el("span", "fgroup-mtext"); txt.textContent = m.text; line.appendChild(txt);
      host.appendChild(line);
    }
  }
}

function answerQuestion(name: string, text: string, question?: string) {
  if (!text.trim()) return;
  // `question` = the card's displayed question text; the host prefixes the
  // delivered prompt with it so the session sees WHAT is being answered (same
  // idea as the follow-up box's `Follow-up on "<title>": …`).
  vscodeApi?.postMessage({ type: "answerQuestion", name, text, question });   // delivered as the session's next typed prompt
}

// Transient hover-highlight signal: hovering a modal line emits its event id(s);
// the host writes timeline-hover.json {id, ids, nonce} (debounced) and db_timeline
// draws a light transient outline on the matching timeline events. null = clear.
// Hovering a PARENT line sends the union of everything underneath it.
function hoverEmit(ids: string | string[] | null) {
  if (Array.isArray(ids)) vscodeApi?.postMessage({ type: "hoverHighlight", ids });
  else vscodeApi?.postMessage({ type: "hoverHighlight", id: ids });
}
// Everything this node covers, for union hover: its delegation-message dot (or
// the ask's typed-turn dot at the root) + every report under it, recursively.
function collectHoverIds(it: AskItem, node: AskTreeNode, byId: Map<string, AskTreeNode>, out: string[], walked: Set<string>) {
  if (walked.has(node.id)) return;
  walked.add(node.id);
  out.push(node.kind === "handoff" ? node.id : it.turnId);
  for (const r of node.rows) out.push(r.reply_id);
  for (const c of node.children || []) { const k = byId.get(c); if (k) collectHoverIds(it, k, byId, out, walked); }
}

// Node STATE → mark, exactly three (the user's model: completed / needing input /
// not finished), in the chat timeline's visual language: ● filled green = done,
// ○ hollow = not finished, ? = needs the user. Status is ROLLED-UP host-side (a
// node is ● when every path below it ends done; a ○ or ? anywhere below
// propagates up), so a completed ask reads as a column of filled dots. The
// disclosure triangle is the only arrow — no glyph shares its shape.
function nodeMark(n: AskTreeNode): string {
  if (n.status === "done") return "●";
  if (n.status === "question") return "?";
  return "○";
}
function nodeStatusClass(n: AskTreeNode): string {
  if (n.status === "done") return "done";
  if (n.status === "question") return "question";
  return "open";
}
function questionForNode(node: AskTreeNode, briefs: Map<string, AskQuestion>): AskQuestion {
  for (const r of node.rows) { const q = briefs.get(r.reply_id); if (q) return q; }
  return { reply_id: node.id, sid: "", name: node.who, t: node.last, brief: null };   // synthetic: answer the node owner
}

// True if any DESCENDANT of `node` is itself a question. Node status is ROLLED UP
// (a ? anywhere below makes every ancestor ?), so this distinguishes the ACTUAL
// pending question (the LOWEST ? in a branch) from its rolled-up ancestors — only
// the lowest one renders a reply box (the user 2026-06-10). Cycle-safe (DAG).
function hasQuestionDescendant(node: AskTreeNode, byId: Map<string, AskTreeNode>): boolean {
  const stack = [...(node.children || [])];
  const seen = new Set<string>();
  while (stack.length) {
    const cid = stack.pop()!;
    if (seen.has(cid)) continue; seen.add(cid);
    const c = byId.get(cid); if (!c) continue;
    if (c.status === "question") return true;
    for (const gc of c.children || []) stack.push(gc);
  }
  return false;
}

// Re-render trigger: per-node expansion + node states + which questions have briefs.
function treeSig(it: AskItem): string {
  return it.tree.map((n) =>
    n.id + n.status + n.rows.length + (n.whoWorking ? "W" : "") + (collapsedNodes.has(it.itemId + ":" + n.id) ? "c" : "")).join("|")
    + "‖" + it.openQuestions.map((q) => q.reply_id + (q.brief ? "b" : "")).join(",");
}

// Render the DAG as a Linux-style node tree (modal body only). Sig-guarded so a
// host re-push never collapses a node the user just opened or clobbers a
// half-typed answer.
function renderTreeBody(host: HTMLElement, it: AskItem) {
  const sig = treeSig(it);
  if ((host as any)._sig === sig) return;
  (host as any)._sig = sig;
  host.innerHTML = "";
  if (!it.tree.length) { const b = el("div", "fx-body"); b.textContent = "No work yet."; host.appendChild(b); return; }
  const box = el("div", "ftree");
  const byId = new Map(it.tree.map((n) => [n.id, n] as const));
  const briefs = new Map(it.openQuestions.map((q) => [q.reply_id, q] as const));
  const seen = new Set<string>();
  const root = it.tree[0];
  // pass root.who as parentWho → the root isn't re-attributed (the modal header credits it)
  renderTreeNode(box, it, root, byId, briefs, seen, 0, root.who);
  host.appendChild(box);
}

// Hierarchy is shown by INDENTATION alone (no ASCII tree connectors — the
// disclosure triangles + indent levels already carry the structure; the user's
// de-clutter ruling 2026-06-10).
const TREE_INDENT_EM = 1.4;

function renderTreeNode(box: HTMLElement, it: AskItem, node: AskTreeNode, byId: Map<string, AskTreeNode>, briefs: Map<string, AskQuestion>, seen: Set<string>, depth: number, parentWho: string) {
  const repeat = seen.has(node.id);
  const nodeKey = it.itemId + ":" + node.id;
  const expandable = !repeat && (node.rows.length > 0 || (node.children || []).length > 0);
  const line = el("div", "ftree-node st-" + nodeStatusClass(node) + (repeat ? " repeat" : ""));
  // the event this line stands for (handoff → its postal msg id; root → the typed
  // turn) — lets a chat rail-dot hover ring this line back (applyExtHover)
  line.dataset.eid = node.kind === "handoff" ? node.id : it.turnId;
  if (depth) line.style.paddingLeft = (depth * TREE_INDENT_EM) + "em";
  // disclosure triangle: ▶ collapsed / ▼ expanded; non-expandable nodes get a blank spacer (no pointer)
  const tri = el("span", "ftree-tri" + (expandable ? " nav" : " empty"));
  tri.textContent = expandable ? (collapsedNodes.has(nodeKey) ? "▶" : "▼") : "";
  // ONLY the triangle toggles expand/collapse (the user 2026-06-10). stopPropagation
  // so the click doesn't bubble to the line, whose click navigates instead.
  if (expandable) tri.onclick = (ev) => { ev.stopPropagation(); if (collapsedNodes.has(nodeKey)) collapsedNodes.delete(nodeKey); else collapsedNodes.add(nodeKey); render(); };
  line.appendChild(tri);
  const mark = el("span", "ftree-mark"); mark.textContent = nodeMark(node); line.appendChild(mark);
  const txt = el("span", "ftree-text"); txt.textContent = node.text || "(node)"; line.appendChild(txt);
  if (node.who && node.who !== parentWho) {
    const who = el("a", "ftree-who"); who.title = node.whoWorking ? "open this session (working now)" : "open this session";
    who.appendChild(document.createTextNode("→ "));
    // working dot LEFT of the name (after the arrow): the agent this is handed to is
    // live-working, so the user knows the item is likely to get finished
    if (node.whoWorking) who.appendChild(el("span", "ftree-who-dot"));
    who.appendChild(document.createTextNode(node.who));
    if (node.whoColor) who.style.color = node.whoColor.bg;
    who.onclick = (ev) => { ev.stopPropagation(); if (node.whoSid) vscodeApi?.postMessage({ type: "openSession", id: node.whoSid }); };
    line.appendChild(who);
  }
  const meta = el("span", "ftree-meta");
  meta.textContent = node.status === "question" ? "needs you" : relAge(hostNow - node.last);
  if (node.status !== "question" && node.trgb) meta.style.color = "rgb(" + node.trgb.join(",") + ")";   // Hawaii recency tint
  line.appendChild(meta);
  // open LEAF = a drop point: the path ended here without a completion or a
  // question. the user can adjudicate it done — the host appends a correction row
  // that completes the card AND becomes linker training data (corrections loop).
  if (!repeat && node.status === "open" && !(node.children || []).length) {
    const fix = el("a", "ftree-fix"); fix.textContent = "mark done";
    fix.title = "record this as completed — also teaches the filing pipeline";
    fix.onclick = (ev) => {
      ev.stopPropagation();
      vscodeApi?.postMessage({ type: "askMarkDone", nodeId: node.id, decisionRef: node.rows.length ? node.rows[node.rows.length - 1].reply_id : null });   // rows are oldest-first; the newest is the verdict to correct
    };
    line.appendChild(fix);
  }
  // Whole-line click NAVIGATES to this node's timeline anchor — the same target
  // the line-hover highlights (collectHoverIds: handoff → its own event id, ask →
  // the ask's turn). The triangle (above) is the only thing that toggles collapse.
  if (!repeat) {
    line.classList.add("nav");
    const navId = node.kind === "handoff" ? node.id : it.turnId;
    const navSid = node.kind === "handoff" ? (node.whoSid || node.id.split(":")[0]) : it.sid;
    const navT = node.kind === "handoff" ? node.t : it.t;
    line.onclick = (ev) => { ev.stopPropagation(); vscodeApi?.postMessage({ type: "showOnTimeline", itemId: navId, sid: navSid, t: navT }); };
  }
  // hovering a parent line highlights the UNION of everything underneath it on
  // the timeline; leaf reports highlight just themselves (in the rows below)
  if (!repeat) {
    line.addEventListener("mouseenter", () => {
      const ids: string[] = [];
      collectHoverIds(it, node, byId, ids, new Set());
      hoverEmit(ids);
    });
    line.addEventListener("mouseleave", () => hoverEmit(null));
  }
  box.appendChild(line);
  if (repeat) return;                                   // dim repeat: line only, no descent
  seen.add(node.id);
  // ? node → decision sub-card, but ONLY on the LOWEST ? in the branch (the actual
  // pending question). Rolled-up ? ancestors keep their ? marker but render no box,
  // so there's a single reply box per real question, not one at every level (the user).
  if (node.status === "question" && !hasQuestionDescendant(node, byId))
    box.appendChild(buildDecisionCard(questionForNode(node, briefs), node.text, depth + 1));
  // node history (rows) — progressive, only when this node was clicked open.
  // the user's ruling: every report that arrived IS a completed sub-thing — it
  // gets a filled green dot. (State still lives on the node line: the dot on a
  // report never holds anything open.) The one exception is the report that IS
  // the currently-open question — that keeps its ?.
  if (!collapsedNodes.has(nodeKey)) {
    // ONE chronological stream per level (the user's ruling): reports and
    // delegations interleave by the time their line DISPLAYS — a report's own
    // time, a delegation's rolled-up last-activity. Each visible sibling list
    // reads oldest → newest; deeper levels re-sort within their own parent
    // (cross-branch disorder when expanded is accepted).
    const entries: { t: number; render: () => void }[] = [];
    for (const r of node.rows) {
      entries.push({ t: r.t, render: () => {
        const row = el("div", "frow nav st-" + r.status + (r.answer ? " st-answer" : ""));
        row.dataset.eid = r.reply_id;   // chat rail-dot hover rings this row back
        row.style.paddingLeft = ((depth + 1) * TREE_INDENT_EM + 1) + "em";
        // ↩ = the user's recorded ANSWER (an explicit child event, not agent work)
        const rm = el("span", "frow-mark"); rm.textContent = r.answer ? "↩" : r.status === "question" ? "?" : "●"; row.appendChild(rm);
        const rt = el("span", "flinked-did"); rt.textContent = r.did; row.appendChild(rt);
        const ra = el("span", "ftime"); ra.textContent = relAge(hostNow - r.t);
        if (r.trgb) ra.style.color = "rgb(" + r.trgb.join(",") + ")";   // Hawaii recency tint
        row.appendChild(ra);
        row.title = "jump to this on the timeline";
        row.onclick = (ev) => { ev.stopPropagation(); vscodeApi?.postMessage({ type: "showOnTimeline", itemId: r.reply_id, sid: r.sid || r.reply_id.split(":")[0], t: r.t }); };
        row.addEventListener("mouseenter", () => hoverEmit(r.reply_id)); row.addEventListener("mouseleave", () => hoverEmit(null));   // transient timeline highlight
        box.appendChild(row);
      } });
    }
    // collapsed node hides its WHOLE subtree — descendants render only when this
    // node is expanded. This is what makes the collapse "deep".
    const kids = (node.children || []).map((c) => byId.get(c)).filter(Boolean) as AskTreeNode[];
    for (const k of kids) {
      entries.push({ t: k.last, render: () => renderTreeNode(box, it, k, byId, briefs, seen, depth + 1, node.who) });
    }
    entries.sort((a, b) => a.t - b.t);
    for (const e of entries) e.render();
  }
}

// Needs-you sub-card under a ? node, shaped by what the user owes (qtype):
// decision/idea → context + question + option buttons + free-text answer box;
// action → context + the thing to do + a "Done — I did it" button (typing in
// the session does NOT cross an action off; this click is what closes it, via
// the host's mark-done correction). `depth` indents it one level under its node.
function buildDecisionCard(q: AskQuestion, fallbackQuestion: string, depth: number): HTMLElement {
  const wrap = el("div", "fq-wrap"); wrap.style.paddingLeft = (depth * TREE_INDENT_EM + 1) + "em";
  const card = el("div", "fq");
  const b = q.brief;
  if (b && b.context) { const ctx = el("div", "fq-context"); ctx.textContent = b.context; card.appendChild(ctx); }
  const qText = (b && b.question) || fallbackQuestion || "";
  const qt = el("div", "fq-question"); qt.textContent = qText || "Needs your input"; card.appendChild(qt);
  // false-awaiting escape hatch (BOTH qtypes — actions need it as much as
  // questions): completes the item AND files the labeled example ("wrongly
  // routed to Awaiting") the classifier trains on — the teaching counterpart
  // of Clear, same correction path as "mark done"
  const notNeeded = el("a", "fq-notneeded"); notNeeded.textContent = "didn't need me";
  notNeeded.title = "record this as wrongly routed to Awaiting — also teaches the filing pipeline";
  notNeeded.onclick = (ev) => {
    ev.stopPropagation();
    vscodeApi?.postMessage({ type: "askMarkDone", nodeId: q.nodeId, decisionRef: q.reply_id,
      note: "the user marked this as not needing input (false awaiting)" });
  };
  if (q.qtype === "action") {
    // a to-do, not a question → amber to-do styling + a ☐ glyph on the task line;
    // "✓ Done — I did it" is the ONLY control (typing can't cross an action off —
    // the click closes it via the host's mark-done correction path).
    card.classList.add("fq-action");
    const box = el("span", "fq-todo-box"); box.textContent = "☐"; qt.prepend(box);
    const form = el("div", "fq-form");
    const didIt = el("button", "fq-send fq-done"); didIt.textContent = "✓ Done — I did it";
    didIt.onclick = (ev) => {
      ev.stopPropagation();
      vscodeApi?.postMessage({ type: "askMarkDone", nodeId: q.nodeId, decisionRef: q.reply_id });
    };
    form.appendChild(didIt);
    card.appendChild(form);
    card.appendChild(notNeeded);
    wrap.appendChild(card);
    return wrap;
  }
  if (b && b.options && b.options.length) {
    const opts = el("div", "fq-opts");
    for (const opt of b.options) {
      const btn = el("button", "fq-opt"); btn.textContent = opt;
      btn.onclick = (ev) => { ev.stopPropagation(); answerQuestion(q.name, opt, qText); };
      opts.appendChild(btn);
    }
    card.appendChild(opts);
  }
  const form = el("div", "fq-form");
  const inp = document.createElement("input");
  inp.type = "text"; inp.className = "fq-input"; inp.placeholder = "type an answer…";
  inp.onclick = (ev) => ev.stopPropagation();
  inp.onkeydown = (ev) => { if (ev.key === "Enter") { ev.preventDefault(); answerQuestion(q.name, inp.value, qText); inp.value = ""; } };
  const send = el("button", "fq-send"); send.textContent = "Send";
  send.onclick = (ev) => { ev.stopPropagation(); answerQuestion(q.name, inp.value, qText); inp.value = ""; };
  form.append(inp, send);
  card.appendChild(form);
  card.appendChild(notNeeded);
  wrap.appendChild(card);
  return wrap;
}

// auto-grow the follow-up composer like the main message box (capped a few lines)
function growFollowUp(ta: HTMLTextAreaElement) {
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight, 120) + "px";
}

// ⛶ full-screen tree modal over the whole feed (deep hierarchies, full width).
// Header credits the ask (title · agent · age · Clear); body = the state tree with
// progressive per-node history. Driven by fullscreenAskId; re-rendered each push.
function renderModal() {
  let m = document.getElementById("feed-modal");
  // The open target is EITHER a single ask (itemId) OR a group ("g:<turnId>" key).
  const isGroup = !!fullscreenAskId && fullscreenAskId.startsWith("g:");
  const tid = isGroup ? fullscreenAskId!.slice(2) : "";
  // Collect by turnId only (NOT groupTitle) so a dissolving group is detected even
  // if its survivors lost the flag; a group down to ONE member converts to that
  // survivor's normal single-ask modal rather than closing.
  const gMembers = isGroup ? asks.filter((a) => a.turnId === tid).sort((a, b) => a.t - b.t) : [];
  if (isGroup && gMembers.length === 1) fullscreenAskId = gMembers[0].itemId;
  const grp = isGroup && gMembers.length >= 2 ? buildGroup(tid, gMembers) : null;
  // …OR a standalone deliverable ("i:<itemId>") — same modal chrome, body = the
  // ask/response detail that used to inline under the old [+] button.
  const fitem = (fullscreenAskId && fullscreenAskId.startsWith("i:"))
    ? items.find((i) => i.itemId === fullscreenAskId!.slice(2)) : null;
  // …OR a synthetic blocked-session card ("b:<sid>") — its modal is the ERROR
  // explanation (what's suspicious + what to note for a correction), nothing else.
  const blk = (fullscreenAskId && fullscreenAskId.startsWith("b:"))
    ? blocked.find((b) => "b:" + b.sid === fullscreenAskId) : null;
  const it = (fullscreenAskId && !fullscreenAskId.startsWith("g:") && !fullscreenAskId.startsWith("i:") && !fullscreenAskId.startsWith("b:"))
    ? asks.find((a) => a.itemId === fullscreenAskId) : null;
  if (!it && !grp && !fitem && !blk) { if (m) { m.remove(); hoverEmit(null); } modalRenderedId = null; return; }   // closed / dissolved → clear hover highlight
  if (!m) {
    m = el("div", ""); m.id = "feed-modal";
    const inner = el("div", "feed-modal-inner");
    const head = el("div", "feed-modal-head");
    const ttl = el("div", "feed-modal-title"); ttl.id = "feed-modal-title";
    const agent = el("a", "fname feed-modal-agent"); agent.id = "feed-modal-agent";
    const age = el("span", "ftime feed-modal-age"); age.id = "feed-modal-age";
    const fup = el("button", "fdismiss ffollow feed-modal-follow"); fup.id = "feed-modal-follow"; fup.textContent = "Follow up"; fup.title = "send a follow-up to this session — the card returns to ASKS"; fup.style.display = "none";
    const clr = el("button", "fdismiss feed-modal-clear"); clr.id = "feed-modal-clear"; clr.textContent = "Clear";
    const close = el("button", "feed-modal-close"); close.textContent = "✕"; close.title = "close (Esc)";
    close.onclick = () => { fullscreenAskId = null; renderModal(); };
    head.append(ttl, agent, age, fup, clr, close);
    // Follow-up composer (single completed ask only): toggled by the Follow up
    // button; Enter/Send delivers `Follow-up on "<title>": …` and reopens the card.
    const fubox = el("div", "ffollow-box feed-modal-follow-box"); fubox.id = "feed-modal-follow-box"; fubox.style.display = "none";
    const fuin = el("textarea", "fq-input feed-modal-follow-input") as HTMLTextAreaElement; fuin.id = "feed-modal-follow-input"; fuin.placeholder = "follow up on this…"; fuin.rows = 1;
    fuin.addEventListener("input", () => growFollowUp(fuin));
    const fusend = el("button", "fq-send feed-modal-follow-send"); fusend.id = "feed-modal-follow-send"; fusend.textContent = "Send";
    fubox.append(fuin, fusend);
    const body = el("div", "feed-modal-body"); body.id = "feed-modal-body";
    const rep = el("div", "feed-modal-report"); rep.id = "feed-modal-report";
    inner.append(head, fubox, body, rep);
    m.appendChild(inner);
    m.onclick = (ev) => { if (ev.target === m) { fullscreenAskId = null; renderModal(); } };  // backdrop closes
    document.body.appendChild(m);
  }
  const body = document.getElementById("feed-modal-body") as HTMLElement;
  // reset the body cache when the open target changes (ask↔group, or a different one)
  // Shared follow-up composer wiring (single-ask AND group modals): the button
  // toggles the box, Enter sends (Shift+Enter = newline), Escape closes. Only
  // the keys we act on are swallowed — everything else (Cmd/Ctrl+V paste, copy,
  // select-all) propagates so VS Code's webview clipboard handler can run.
  function wireFollowUp(fupEl: HTMLButtonElement, fuboxEl: HTMLElement, fuinEl: HTMLTextAreaElement, fusendEl: HTMLButtonElement, send: (txt: string) => void) {
    fupEl.style.display = "";
    const submit = () => { const txt = fuinEl.value.trim(); if (!txt) return; send(txt); fuinEl.value = ""; fuinEl.style.height = ""; fuboxEl.style.display = "none"; };
    fupEl.onclick = () => { const show = fuboxEl.style.display === "none"; fuboxEl.style.display = show ? "" : "none"; if (show) fuinEl.focus(); };
    fusendEl.onclick = submit;
    fuinEl.onkeydown = (ev) => {
      if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); ev.stopPropagation(); submit(); }
      else if (ev.key === "Escape") { ev.stopPropagation(); fuboxEl.style.display = "none"; }
    };
  }

  if (modalRenderedId !== fullscreenAskId) {
    body.innerHTML = ""; (body as any)._sig = "";
    // a fresh target gets a fresh, collapsed follow-up composer
    const fb0 = document.getElementById("feed-modal-follow-box") as HTMLElement | null;
    if (fb0) { fb0.style.display = "none"; const i0 = document.getElementById("feed-modal-follow-input") as HTMLTextAreaElement | null; if (i0) { i0.value = ""; i0.style.height = ""; } }
    // fresh open shows ONE level (the user's ruling): the root's reports + its
    // direct children as lines, everything beneath those children folded until
    // clicked. Seeding overrides any unfolds left from a previous open.
    for (const mem of (it ? [it] : grp ? grp.members : [])) {
      const rootId = mem.tree.length ? mem.tree[0].id : null;
      for (const n of mem.tree) {
        const key = mem.itemId + ":" + n.id;
        if (n.id === rootId) collapsedNodes.delete(key);
        else if (n.rows.length || (n.children || []).length) collapsedNodes.add(key);
      }
      // EXCEPTION to one-level (the user): expand the branch DOWN to each pending
      // question so its reply box is reachable without manual unfolding — only that
      // branch's ancestors, never the whole tree.
      const byId = new Map(mem.tree.map((n) => [n.id, n] as const));
      const root = mem.tree[0];
      if (root) {
        const walk = (n: AskTreeNode, ancestors: string[]) => {
          if (n.status === "question" && !hasQuestionDescendant(n, byId))
            for (const aid of ancestors) collapsedNodes.delete(mem.itemId + ":" + aid);   // open the path to the box
          const next = [...ancestors, n.id];
          for (const cid of n.children || []) { if (next.includes(cid)) continue; const c = byId.get(cid); if (c) walk(c, next); }
        };
        walk(root, []);
      }
    }
  }
  modalRenderedId = fullscreenAskId;
  const ttlEl = document.getElementById("feed-modal-title") as HTMLElement;
  const agent = document.getElementById("feed-modal-agent") as HTMLElement;
  const ageEl = document.getElementById("feed-modal-age") as HTMLElement;
  const clrEl = document.getElementById("feed-modal-clear") as HTMLElement;
  const fupEl = document.getElementById("feed-modal-follow") as HTMLButtonElement;
  const fuboxEl = document.getElementById("feed-modal-follow-box") as HTMLElement;
  const fuinEl = document.getElementById("feed-modal-follow-input") as HTMLTextAreaElement;
  const fusendEl = document.getElementById("feed-modal-follow-send") as HTMLButtonElement;
  // modal title = a locate link, same as the collapsed card's title (the user
  // 2026-06-10: every title should jump to the thing in the text/timeline)
  ttlEl.classList.add("nav");
  ttlEl.title = "locate this in the text";
  clrEl.style.display = "";   // re-shown here because the blocked branch below hides it
  if (grp) {
    ttlEl.textContent = grp.title;
    ttlEl.onclick = () => vscodeApi?.postMessage({ type: "showAskPath", itemId: grp.members[0].itemId });
    agent.textContent = grp.name; if (grp.color) agent.style.color = grp.color.bg; setWorkDot(agent, workingSet.has(grp.name));
    agent.onclick = () => vscodeApi?.postMessage({ type: "openSession", id: grp.sid });
    ageEl.textContent = relAge(hostNow - grp.t);
    clrEl.onclick = () => { for (const mem of grp.members) vscodeApi?.postMessage({ type: "askClear", itemId: mem.itemId }); fullscreenAskId = null; renderModal(); };
    // follow-up on a group goes to the session that took the typed prompt — one
    // message prefixed with the GROUP title, filed under the first member's ask
    wireFollowUp(fupEl, fuboxEl, fuinEl, fusendEl, (txt) =>
      vscodeApi?.postMessage({ type: "askFollowUp", itemId: grp.members[0].itemId, title: grp.title, text: txt }));
    renderGroupModalBody(body, grp.members);
    renderReportInto(document.getElementById("feed-modal-report")!, grp.members[0].itemId,
      grp.members.flatMap((mm) => mm.suspects || []));
  } else if (it) {
    ttlEl.textContent = it.text;
    ttlEl.onclick = () => vscodeApi?.postMessage({ type: "showAskPath", itemId: it.itemId });
    agent.textContent = it.name; if (it.color) agent.style.color = it.color.bg; setWorkDot(agent, workingSet.has(it.name));
    agent.onclick = () => vscodeApi?.postMessage({ type: "openSession", id: it.sid });
    ageEl.textContent = relAge(hostNow - it.t);
    clrEl.onclick = () => { vscodeApi?.postMessage({ type: "askClear", itemId: it.itemId }); fullscreenAskId = null; renderModal(); };
    // follow-up works in ANY state (the user 2026-06-10) — asks, awaiting, or completed;
    // toggling the button reveals the composer.
    wireFollowUp(fupEl, fuboxEl, fuinEl, fusendEl, (txt) =>
      vscodeApi?.postMessage({ type: "askFollowUp", itemId: it.itemId, text: txt }));
    renderTreeBody(body, it);
    renderReportInto(document.getElementById("feed-modal-report")!, it.itemId, it.suspects);
  } else if (fitem) {
    ttlEl.textContent = fitem.did;
    ttlEl.onclick = () => vscodeApi?.postMessage({ type: "showOnTimeline", itemId: fitem.itemId, sid: fitem.sid, t: fitem.t, anchor: "prompt" });
    agent.textContent = fitem.name; if (fitem.color) agent.style.color = fitem.color.bg; setWorkDot(agent, workingSet.has(fitem.name));
    agent.onclick = () => vscodeApi?.postMessage({ type: "openSession", id: fitem.sid });
    ageEl.textContent = relAge(hostNow - fitem.t);
    clrEl.onclick = () => { vscodeApi?.postMessage({ type: "askClear", itemId: fitem.itemId }); fullscreenAskId = null; renderModal(); };
    fupEl.style.display = "none"; fuboxEl.style.display = "none";   // standalone deliverable: no follow-up
    // fetch the detail once (same machinery the old inline [+] used)
    const d = details.get(fitem.itemId);
    if (!d || d.state === "failed") {
      details.set(fitem.itemId, { state: "loading" });
      vscodeApi?.postMessage({ type: "expand", itemId: fitem.itemId,
        generate: fitem.relevance === "DONE" || fitem.relevance === "DECISION" });
    }
    renderStandaloneTreeInto(body, fitem);
    renderReportInto(document.getElementById("feed-modal-report")!, fitem.itemId, undefined);
  } else if (blk) {
    // ERROR-FLAG modal (the user's ruling 2026-06-11): a synthetic blocked card is
    // inherently suspicious — explain the miss and what a correction needs.
    ttlEl.textContent = "Unattributed blocked session";
    ttlEl.classList.remove("nav"); ttlEl.onclick = null; ttlEl.title = "";
    agent.textContent = blk.name; if (blk.color) agent.style.color = blk.color.bg; setWorkDot(agent, workingSet.has(blk.name));
    agent.onclick = () => vscodeApi?.postMessage({ type: "openSession", id: blk.sid });
    ageEl.textContent = "blocked " + relAge(hostNow - blk.since).replace(/ ago$/, "");
    clrEl.style.display = "none";                                   // nothing to clear — self-resolves
    fupEl.style.display = "none"; fuboxEl.style.display = "none";   // and nothing to follow up on
    renderBlockedSuspectInto(body, blk);
    renderReportInto(document.getElementById("feed-modal-report")!, "blocked:" + blk.sid, undefined);
  }
}

// ⚠ Report box (the user's three-bucket model, 2026-06-11): the EXCEPTION path.
// Shown in every card modal; when the deterministic sweep attached missed-handoff
// suspects, their evidence renders above it and the category preselects. Filing
// posts askReport -> requests/reports.jsonl: a labeled failure example for the
// next prompt rework. Normal actions (Clear, answer, mark done) are NOT reports;
// this box is only for "the system got something wrong".
function renderReportInto(host: HTMLElement, itemId: string, suspects?: Array<{ mid: string; to: string; t: number; snippet: string; why: string }>) {
  const sig = "rep:" + itemId + ":" + (suspects?.length || 0);
  if ((host as any)._sig === sig) return;
  (host as any)._sig = sig;
  host.innerHTML = "";
  if (suspects?.length) {
    const lab = el("div", "fx-label fsuspect-lab"); lab.textContent = "\u26a0 possible missed handoff"; host.appendChild(lab);
    for (const sp of suspects) {
      const row = el("div", "fx-body fsuspect");
      row.textContent = `${sp.why} (${relAge(hostNow - sp.t)}): \u201c${sp.snippet}\u2026\u201d`;
      host.appendChild(row);
    }
    const hint = el("div", "fx-body fsuspect-hint");
    hint.textContent = "Real handoff? File the report below as 'missed handoff'. False alarm? File it as 'other' and say so. Both teach the classifier.";
    host.appendChild(hint);
  }
  const toggle = el("a", "frep-toggle"); toggle.textContent = "\u26a0 Report an exception";
  toggle.title = "something here is wrong (wrong column, missed handoff, junk card\u2026) \u2014 describe it and it becomes a labeled example for prompt refinement";
  const box = el("div", "frep-box"); box.style.display = suspects?.length ? "" : "none";
  const sel = document.createElement("select"); sel.className = "frep-sel";
  for (const [v, lab2] of [
    ["not-done", "this is shown as done but isn't"],
    ["missed-handoff", "this WAS a real handoff (confirm the ⚠)"],
    ["false-flag", "this flag/badge is wrong (false alarm)"],
    ["other", "something else — describe it"],
  ] as const) { const o = document.createElement("option"); o.value = v; o.textContent = lab2; sel.appendChild(o); }
  if (suspects?.length) sel.value = "missed-handoff";
  const ta = document.createElement("textarea"); ta.className = "frep-input"; ta.placeholder = "what happened / what should have happened\u2026"; ta.rows = 2;
  const send = el("button", "fq-send frep-send"); send.textContent = "File report";
  send.onclick = () => {
    vscodeApi?.postMessage({ type: "askReport", itemId, category: sel.value, text: ta.value.trim() });
    ta.value = ""; box.style.display = "none";
    toggle.textContent = "\u2713 report filed"; setTimeout(() => { toggle.textContent = "\u26a0 Report an exception"; }, 2500);
  };
  toggle.onclick = () => { box.style.display = box.style.display === "none" ? "" : "none"; };
  box.append(sel, ta, send);
  host.append(toggle, box);
}

// Body of the unattributed-blocked modal. This card type exists ONLY to flag a
// registry error: under the every-prompt-mints-an-ask rule, a live blocked turn
// that no card claims means capture or linking failed (or the card was cleared
// — the benign overlap). It is NOT a supported steady-state card.
function renderBlockedSuspectInto(host: HTMLElement, b: Blocked) {
  const sig = "blk:" + b.sid + ":" + b.state;
  if ((host as any)._sig === sig) return;
  (host as any)._sig = sig;
  host.innerHTML = "";
  const mk = (label: string, text: string) => {
    const lab = el("div", "fx-label"); lab.textContent = label;
    const bod = el("div", "fx-body"); bod.textContent = text;
    host.append(lab, bod);
  };
  mk("What this card is",
    `${b.name} is stopped mid-turn (${b.what}), but no card claims the turn it is blocked on. ` +
    "Every typed prompt is supposed to mint or amend an ask, so an unclaimed live turn means the " +
    "registry missed something. This card exists only to flag that miss — and to keep the block " +
    "itself visible so you can act on it (click the session name to answer the prompt).");
  mk("Likely causes",
    "1) The prompt that started this work never minted an ask — the capture model under-fired; " +
    "its verdict for the turn is in requests/decision-log.jsonl (ask-capture row, verdict/backstop fields). " +
    "2) You already cleared the card this work belongs to — benign; the card vanishes when you unblock the session. " +
    "3) The work hasn't been linked to its ask yet — a linking miss if this persists after the turn ends.");
  mk("To file a correction",
    "Note the session name, when you typed the prompt behind this work, and which ask it should have " +
    "been filed under (or the new ask it should have minted). Tell any session to record it — the row " +
    "becomes a labeled regression example in corrections.jsonl, and the next capture-prompt rework " +
    "trains against it.");
}

// Standalone completion rendered in the SAME visual language as ask cards
// (the user 2026-06-10: "I would prefer if that particular simple card had a
// consistent formatting to all the other ones"): a one-node tree — root line
// = the prompt that caused it, one green ● report row = the deliverable,
// pending next-steps as hollow ○ rows, and the written paragraph beneath as
// secondary detail instead of the old ASK/RESPONSE block.
function renderStandaloneTreeInto(host: HTMLElement, fitem: FeedItem) {
  const d = details.get(fitem.itemId);
  const det = d && d.data ? d.data : undefined;
  const sig = "st:" + fitem.itemId + ":" + fitem.relevance + ":" + (det ? (det.paragraph || "") + "¦" + (det.next_steps || []).join("¦") : "…");
  if ((host as any)._sig === sig) return;
  (host as any)._sig = sig;
  host.innerHTML = "";
  const box = el("div", "ftree");
  // root = the typed prompt this work answered (● — the work is finished)
  const root = el("div", "ftree-node st-done nav");
  root.appendChild(el("span", "ftree-tri empty"));
  const mark = el("span", "ftree-mark"); mark.textContent = "●"; root.appendChild(mark);
  const txt = el("span", "ftree-text"); txt.textContent = fitem.ask || fitem.did; root.appendChild(txt);
  const meta = el("span", "ftree-meta"); meta.textContent = relAge(hostNow - fitem.t);
  meta.style.color = "rgb(" + fitem.trgb.join(",") + ")";
  root.appendChild(meta);
  root.onclick = () => vscodeApi?.postMessage({ type: "showOnTimeline", itemId: fitem.itemId, sid: fitem.sid, t: fitem.t, anchor: "prompt" });
  box.appendChild(root);
  // the deliverable = one green report row (same vocabulary as ask trees)
  const row = el("div", "frow nav st-done");
  row.style.paddingLeft = (TREE_INDENT_EM + 1) + "em";
  const rm = el("span", "frow-mark"); rm.textContent = "●"; row.appendChild(rm);
  const rt = el("span", "flinked-did"); rt.textContent = fitem.did; row.appendChild(rt);
  const ra = el("span", "ftime"); ra.textContent = relAge(hostNow - fitem.t); row.appendChild(ra);
  row.title = "jump to this on the timeline";
  row.onclick = (ev) => { ev.stopPropagation(); vscodeApi?.postMessage({ type: "showOnTimeline", itemId: fitem.itemId, sid: fitem.sid, t: fitem.t }); };
  box.appendChild(row);
  // what's still pending (next-steps) = hollow circles, like any open path
  if (det && Array.isArray(det.next_steps)) {
    for (const s of det.next_steps) {
      const nr = el("div", "frow st-open");
      nr.style.paddingLeft = (TREE_INDENT_EM + 1) + "em";
      const nm = el("span", "frow-mark"); nm.textContent = "○"; nr.appendChild(nm);
      const nt = el("span", "flinked-did"); nt.textContent = s; nr.appendChild(nt);
      box.appendChild(nr);
    }
  }
  host.appendChild(box);
  // the JLD paragraph stays, dimmer, as secondary detail under the tree
  const par = el("div", "fx-body fstandalone-par");
  par.textContent = det && det.paragraph ? det.paragraph : d && d.state === "loading" ? "…" : "";
  if (par.textContent) host.appendChild(par);
  // false-awaiting escape hatch, standalone flavor: a standalone item sits in
  // Awaiting purely on its relevance tag (no ? node, so no decision card to host
  // the link) — clears the item AND files the mis-tag label for the classifier
  if (fitem.relevance !== "DONE") {
    const notNeeded = el("a", "fq-notneeded"); notNeeded.textContent = "didn't need me";
    notNeeded.title = "record this as wrongly routed to Awaiting — also teaches the filing pipeline";
    notNeeded.onclick = (ev) => {
      ev.stopPropagation();
      vscodeApi?.postMessage({ type: "itemNotNeeded", itemId: fitem.itemId });
      fullscreenAskId = null; renderModal();
    };
    host.appendChild(notNeeded);
  }
}

// Group modal body: each member's own flat tree stacked, member text as its root
// line, chronological. Sig-guarded (member set + per-member tree sigs) so a host
// repush doesn't tear down an open subtree. Collapse state lives in collapsedNodes
// (keyed by itemId:nodeId), so it survives even a full rebuild here.
function renderGroupModalBody(host: HTMLElement, members: AskItem[]) {
  const sig = members.map((m) => m.itemId + "@" + treeSig(m)).join("‖");
  if ((host as any)._sig === sig) return;
  (host as any)._sig = sig;
  host.innerHTML = "";
  for (const m of members) {
    const sec = el("div", "fgroup-modal-member");
    renderTreeBody(sec, m);   // renders m.tree rooted at m's ask node → member text IS the root line
    host.appendChild(sec);
  }
}

// ---- SYNTHETIC blocked-session card: an ERROR FLAG, not a card type ----
// A blocked session normally surfaces as its OWN ask card moving to BLOCKED
// (host annotates it via the turn→card join). This synthetic card renders only
// when NO card claims the blocked turn — which the every-prompt-mints rule says
// should never happen — so it is inherently suspicious and wears the ⚠ badge;
// the badge's modal explains the miss and what a correction needs. NO Clear
// (self-resolves when the user acts); whole-card click opens the session.
function makeBlockedCard(b: Blocked): HTMLElement {
  const card = el("div", "fitem blocked");
  card.dataset.key = "b:" + b.sid;
  const main = el("div", "fitem-main");
  const row1 = el("div", "fask-row1");
  const title = el("div", "fcard-title");
  const time = el("span", "ftime");
  row1.append(title, time);
  const row2 = el("div", "fask-row2");
  const idwrap = el("div", "fask-id");
  const name = el("span", "fname");
  idwrap.append(name);
  const warn = el("a", "fask-suspect"); warn.textContent = "⚠ unattributed";
  warn.title = "no card claims this blocked turn — that's a registry miss; click for what it means and how to correct it";
  warn.onclick = (ev) => { ev.stopPropagation(); fullscreenAskId = "b:" + b.sid; renderModal(); };
  const hint = el("span", "blocked-hint"); hint.textContent = "click to answer →"; // picker only
  row2.append(idwrap, warn, hint);
  main.append(row1, row2);
  card.append(main);
  // Read the CURRENT state on click (the card is reused across state flips, so the
  // closure must not capture the creation-time state): picker → drive it via a
  // QuickPick (answerPicker); permission → just open the session.
  card.onclick = () => {
    const cur = (card as any)._b as Blocked | undefined;
    if (!cur) return;
    if (cur.state === "picker") vscodeApi?.postMessage({ type: "answerPicker", name: cur.name });
    else if (cur.sid) vscodeApi?.postMessage({ type: "openSession", id: cur.sid });
  };
  const a = card as any;
  a._title = title; a._name = name; a._time = time; a._hint = hint;
  return card;
}

function updateBlockedCard(card: HTMLElement, b: Blocked) {
  const a = card as any;
  a._b = b;                                          // current state for the click handler
  a._title.textContent = b.what;
  a._name.textContent = b.name;
  if (b.color) a._name.style.color = b.color.bg;
  a._time.textContent = "blocked " + relAge(hostNow - b.since).replace(/ ago$/, "");
  const isPicker = b.state === "picker";
  a._hint.style.display = isPicker ? "" : "none";    // affordance hint only for actionable picker cards
  card.title = isPicker ? "click to answer the picker" : "open this session";
  card.classList.toggle("actionable", isPicker);
}

// A column entry is an ask card, a standalone deliverable card, or a blocked-
// session state card; the reconcile picks the right builder + cache map by kind.
type Entry =
  | { kind: "ask"; t: number; ask: AskItem }
  | { kind: "group"; t: number; group: AskGroup }
  | { kind: "item"; t: number; item: FeedItem }
  | { kind: "blocked"; t: number; blocked: Blocked };

// UndoClear (top right): restore the most recently cleared card — the host pops
// the newest cleared.jsonl row. Built fresh wherever the top strip renders: on
// the legend row when columns exist, and on the empty state too (clearing the
// LAST card is exactly when undo is wanted).
function makeUndoClearBtn(): HTMLElement {
  const b = el("button", "fdismiss fh-undoclear");
  b.id = "feed-undoclear";
  b.textContent = "UndoClear";
  b.title = "restore the most recently cleared card";
  b.onclick = (ev) => { ev.stopPropagation(); vscodeApi?.postMessage({ type: "undoClear" }); };
  return b;
}

// Build the three columns (Asks | Awaiting | Completed) inside #feed-list once;
// rebuild if torn down (empty state). "Awaiting" (the user's ruling 2026-06-10):
// matches the session-chip vocabulary — anything here awaits HIM (a question,
// an action like reload, an idea), red like the awaiting chip.
function ensureCols(list: HTMLElement) {
  if (!document.getElementById("feed-cols")) {
    list.innerHTML = "";
    const cols = el("div", "feed-cols"); cols.id = "feed-cols";
    // "Working" (the user's rename, 2026-06-11): every card is an ASK; the left
    // column holds the ones being worked — internal keys keep the old names
    for (const [key, label] of [["asks", "Working"], ["needsInput", "Blocked"], ["completed", "Completed"]] as const) {
      const col = el("div", "feed-col col-" + key);
      const head = el("div", "feed-col-head");
      const name = el("span", "feed-col-name"); name.textContent = label;
      const count = el("span", "feed-col-count"); count.id = "col-" + key + "-count";
      head.append(name, count);
      const body = el("div", "feed-col-list"); body.id = "col-" + key + "-list";
      col.append(head, body);
      cols.appendChild(col);
    }
    // liveness legend: rings mark ANOMALIES only — cards whose live state
    // disagrees with the column they're filed in (agreement shows nothing)
    const legend = el("div", "lv-legend");
    // rings live ONLY in Completed; agreement gets no ink (see the "?" help)
    for (const [k, lab, tip] of [
      ["settled", "auto-filed",
        "GREEN RING (Completed only) — auto-filed without a done-stamp.\n\n"
        + "Nothing was moving this card (owner quiet on it, no open handoffs), so it filed itself, "
        + "but the judge model never stamped the work done. If it IS done, Clear: that click records "
        + "the judge missed a stamp. If it is NOT, Follow up: that records the auto-filer was wrong. "
        + "Either way one ordinary click becomes a labeled example for the next prompt rework.\n\n"
        + "No ring at all means the judge AND the auto-filer agree it is done: Clear with confidence."],
      ["done", "judged done",
        "BLUE RING (Completed only) — done-stamped but not settled.\n\n"
        + "The judge stamped every path done, but the liveness detector still sees motion: usually the "
        + "owning session is mid-turn (possibly on this very card) or the card waits on something. "
        + "Glance before you Clear; if new work lands and links here, the card returns to Working on "
        + "its own.\n\nNo ring at all means both systems agree: Clear with confidence."],
    ] as const) {
      const chip = el("span", "lv-chip lv-" + k); chip.textContent = lab; chip.title = tip;
      legend.appendChild(chip);
    }
    legend.appendChild(makeUndoClearBtn());   // pinned right via margin-left:auto
    const helpBtn = el("a", "lv-help"); helpBtn.textContent = "?";
    helpBtn.title = "how to read this feed — categories, rings, and what each needs from you";
    helpBtn.onclick = () => toggleHelp(true);
    legend.appendChild(helpBtn);
    list.appendChild(legend);
    list.appendChild(cols);
  }
  return {
    asks: document.getElementById("col-asks-list")!,
    needsInput: document.getElementById("col-needsInput-list")!,
    completed: document.getElementById("col-completed-list")!,
    asksCount: document.getElementById("col-asks-count")!,
    needsInputCount: document.getElementById("col-needsInput-count")!,
    completedCount: document.getElementById("col-completed-count")!,
  };
}

// Keyed in-place reconcile of ONE column (mixes ask + standalone cards; a card
// whose column changed is MOVED, not rebuilt — no hover flicker). Records each key
// in `globalDesired` for the cross-column cache cleanup the caller runs after.
function reconcileCol(listEl: HTMLElement, entries: Entry[], globalDesired: Set<string>) {
  const existing = new Map<string, HTMLElement>();
  for (const c of Array.from(listEl.children) as HTMLElement[]) {
    const k = c.dataset.key;
    if (k) existing.set(k, c); else c.remove();
  }
  const ordered: HTMLElement[] = [];
  const colDesired = new Set<string>();
  for (const e of entries) {
    let key: string, card: HTMLElement;
    if (e.kind === "ask") {
      key = "a:" + e.ask.itemId;
      card = askEls.get(e.ask.itemId) || makeAskCard(e.ask);
      askEls.set(e.ask.itemId, card);
      updateAskCard(card, e.ask);
    } else if (e.kind === "group") {
      key = "g:" + e.group.turnId;
      card = groupEls.get(e.group.turnId) || makeGroupCard(e.group);
      groupEls.set(e.group.turnId, card);
      updateGroupCard(card, e.group);
    } else if (e.kind === "blocked") {
      key = "b:" + e.blocked.sid;
      card = blockedEls.get(e.blocked.sid) || makeBlockedCard(e.blocked);
      blockedEls.set(e.blocked.sid, card);
      updateBlockedCard(card, e.blocked);
    } else {
      key = "i:" + e.item.itemId;
      card = cardEls.get(e.item.itemId) || makeCard(e.item);
      cardEls.set(e.item.itemId, card);
      updateCard(card, e.item);
    }
    globalDesired.add(key); colDesired.add(key);
    ordered.push(card);
  }
  for (const [k, c] of existing) if (!colDesired.has(k)) c.remove();
  let cur: ChildNode | null = listEl.firstChild;
  for (const node of ordered) {
    if (cur === node) { cur = cur.nextSibling; continue; }
    listEl.insertBefore(node, cur);
  }
  if (!entries.length) { const e = el("div", "feed-col-empty"); e.textContent = "—"; listEl.appendChild(e); }
}

// THE view: one screen, three columns merging open asks with standalone
// completions; cards move between columns as links arrive.
function render() {
  const list = document.getElementById("feed-list")!;
  const prevScroll = list.scrollTop;
  const standalone = standaloneItems();

  if (!asks.length && !standalone.length && !blocked.length) {
    list.innerHTML = ""; askEls.clear(); groupEls.clear(); cardEls.clear(); blockedEls.clear();
    const e = el("div", "feed-empty"); e.textContent = "Nothing open — inbox zero.";
    list.appendChild(e);
    if (canUndoClear) list.appendChild(makeUndoClearBtn());
    return;
  }

  const cols = ensureCols(list);
  const undoBtn = document.getElementById("feed-undoclear");
  if (undoBtn) undoBtn.style.display = canUndoClear ? "" : "none";
  const buckets: Record<Column, Entry[]> = { asks: [], needsInput: [], completed: [] };
  // Derive sibling GROUPS at render time, keyed by the shared typed turn (turnId).
  // Only host-flagged asks (groupTitle) participate, and a turn needs ≥2 current
  // members to fold — a lone survivor (siblings cleared) renders as a single card.
  const byTurn = new Map<string, AskItem[]>();
  for (const a of asks) {
    if (!a.groupTitle || !a.turnId) continue;
    const arr = byTurn.get(a.turnId) || []; arr.push(a); byTurn.set(a.turnId, arr);
  }
  const grouped = new Set<string>();   // itemIds folded into a group → excluded from single ask cards
  for (const [tid, members] of byTurn) {
    if (members.length < 2) continue;
    members.forEach((m) => grouped.add(m.itemId));
    const g = buildGroup(tid, members);
    buckets[g.column].push({ kind: "group", t: g.t, group: g });
  }
  for (const a of asks) { if (grouped.has(a.itemId)) continue; buckets[askColumn(a)].push({ kind: "ask", t: a.t, ask: a }); }
  for (const it of standalone) buckets[it.relevance === "DONE" ? "completed" : "needsInput"].push({ kind: "item", t: it.t, item: it });
  for (const k of Object.keys(buckets) as Column[]) buckets[k].sort((x, y) => y.t - x.t);   // newest first
  // blocked-session cards pin to the TOP of NEEDS INPUT (a live state, not an ask),
  // longest-blocked first (smallest `since`).
  const blockedEntries: Entry[] = blocked.slice()
    .sort((a, b) => a.since - b.since)
    .map((b) => ({ kind: "blocked", t: b.since, blocked: b }));
  buckets.needsInput = [...blockedEntries, ...buckets.needsInput];

  const desired = new Set<string>();
  reconcileCol(cols.asks, buckets.asks, desired);
  reconcileCol(cols.needsInput, buckets.needsInput, desired);
  reconcileCol(cols.completed, buckets.completed, desired);
  cols.asksCount.textContent = String(buckets.asks.length);
  cols.needsInputCount.textContent = String(buckets.needsInput.length);
  cols.completedCount.textContent = String(buckets.completed.length);

  for (const id of Array.from(askEls.keys())) if (!desired.has("a:" + id)) { askEls.get(id)?.remove(); askEls.delete(id); }
  for (const tid of Array.from(groupEls.keys())) if (!desired.has("g:" + tid)) { groupEls.get(tid)?.remove(); groupEls.delete(tid); }
  for (const id of Array.from(cardEls.keys())) if (!desired.has("i:" + id)) { cardEls.get(id)?.remove(); cardEls.delete(id); }
  for (const id of Array.from(blockedEls.keys())) if (!desired.has("b:" + id)) { blockedEls.get(id)?.remove(); blockedEls.delete(id); }

  list.scrollTop = prevScroll;
  renderModal();   // keep the ⛶ full-screen tree (if open) in sync with this push
  applyExtHover(); // reconcile/renderModal may have rebuilt nodes — re-apply the rail-dot outlines (cards AND modal rows)
}

// ---- help overlay (the user 2026-06-11): the "?" in the legend opens this. ----
// Copy follows the JLD method: lead with what the reader does, plain declarative
// sentences, one idea each. Organized by the user's three buckets so he can tell
// at a glance whether a marker is routine, a teaching click, or a bug to report.
function toggleHelp(show: boolean) {
  let h = document.getElementById("feed-help");
  if (!show) { h?.remove(); return; }
  if (h) return;
  h = el("div", ""); h.id = "feed-help";
  const inner = el("div", "feed-help-inner");
  const close = el("button", "feed-modal-close feed-help-close"); close.textContent = "✕"; close.title = "close (Esc)";
  close.onclick = () => toggleHelp(false);
  inner.appendChild(close);
  // rich(): colored words render IN their color (the user 2026-06-12-eve), so the
  // help shows what the feed shows. Segment = plain string | [text, colorClass].
  const rich = (cls: string, segs: Array<string | [string, string]>) => {
    const d = el("div", cls);
    for (const sg of segs) {
      if (typeof sg === "string") d.appendChild(document.createTextNode(sg));
      else { const sp = el("span", "hl hl-" + sg[1]); sp.textContent = sg[0]; d.appendChild(sp); }
    }
    inner!.appendChild(d);
  };
  rich("fh2", ["How to read this feed"]);
  rich("fbody", ["Every card is something you asked for. Cards move between columns on their own. ",
    "You do two things: answer what is in Blocked, and clear what is in Completed. ",
    "Clear is the only way a card dies."]);
  rich("fh3", ["The columns"]);
  rich("fbody", ["WORKING: an agent is on it, a delegation is pending, or it is ", ["⏳ waiting", "cyan"],
    " on an outside event (CI, a build, a peer). Nothing here needs you. "]);
  rich("fbody", [["BLOCKED", "red"], ": you are the blocker. Answer the question, do the action, or click ",
    ["⏸ approval", "red"], " to approve the prompt. A card marked reopened came back after you cleared it: treat it as new."]);
  rich("fbody", [["COMPLETED", "blue"], ": at rest. Every card here was either stamped done by the judge model, ",
    "auto-filed because nothing was moving it, or both. The rings say which:"]);
  rich("fbody", ["No ring: judged done and settled. The two systems agree. Clear with confidence."]);
  rich("fbody", [["green ring", "green"], ": auto-filed only. The judge never stamped it. If it is done, Clear. ",
    "If it is not, Follow up. Each of those ordinary clicks is recorded as a labeled example, and the next ",
    "prompt rework trains on them. That is the whole teaching loop: you never do anything extra."]);
  rich("fbody", [["blue ring", "blue"], ": judged done only, not settled. Usually the owner is still mid-turn, ",
    "possibly on this card. Glance before clearing; new linked work pulls the card back to Working by itself."]);
  rich("fh3", [["⚠ exceptions", "amber"], " (amber)"]);
  rich("fbody", ["These should not happen. Each is a bug worth a minute. Open the card, read the evidence, and use ",
    ["⚠ Report an exception", "amber"], " at the bottom of the modal: pick a category, say what you saw. ",
    "Each report stores a snapshot of the card and becomes a labeled failure example."]);
  rich("fbody", [["⚠ stalled", "amber"], ": a delegation died and nobody will finish it. Nudge or revive the ",
    "named session, or mark the branch done if it is moot."]);
  rich("fbody", [["⚠ handoff?", "amber"], ": a message between agents was dismissed as FYI and the recipient ",
    "then did work belonging to no card. Opus audits every such case automatically, repairing real ",
    "handoffs and dismissing coincidences, so this badge appears only when it answered 'unsure'. ",
    "Read the evidence and settle it in the report box."]);
  rich("fbody", [["⚠ unattributed", "amber"], ": a blocked session that no card claims. ",
    "A brand-new standalone deliverable card is the same bucket: both should be impossible now."]);
  rich("fh3", ["Inside a card"]);
  rich("fbody", ["The tree is the ask's full history: ● finished work, ? a pending question, ○ a branch still open, ",
    ["↩", "blue"], " your own recorded answers. Rows jump to the work they name; hovering lights the same ",
    "moments in the chat and on the timeline."]);
  h.appendChild(inner);
  h.onclick = (ev) => { if (ev.target === h) toggleHelp(false); };
  document.body.appendChild(h);
}

window.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && document.getElementById("feed-help")) { toggleHelp(false); return; }
  if (e.key === "Escape" && fullscreenAskId) { fullscreenAskId = null; renderModal(); }
});

window.addEventListener("message", (e: MessageEvent) => {
  const m = e.data;
  if (!m) return;
  if (m.type === "feed") {
    items = Array.isArray(m.items) ? m.items : [];
    asks = Array.isArray(m.asks) ? m.asks : [];
    blocked = Array.isArray(m.blocked) ? m.blocked : [];
    workingSet = new Set(Array.isArray(m.working) ? m.working : []);
    hostNow = typeof m.now === "number" ? m.now : Math.floor(Date.now() / 1000);
    if (typeof m.dismissedCount === "number") dismissedCount = m.dismissedCount;
    if (typeof m.showDismissed === "boolean") showDismissed = m.showDismissed;
    if (typeof m.canUndoClear === "boolean") canUndoClear = m.canUndoClear;
    render();
  } else if (m.type === "detail" && m.itemId) {
    details.set(m.itemId, { state: "ready", data: m.detail });
    if (expanded.has(m.itemId) || fullscreenAskId === "i:" + m.itemId) render();
  } else if (m.type === "detailPending" && m.itemId) {
    if (details.get(m.itemId)?.state !== "ready") details.set(m.itemId, { state: "loading" });
    if (expanded.has(m.itemId) || fullscreenAskId === "i:" + m.itemId) render();
  } else if (m.type === "detailFailed" && m.itemId) {
    details.set(m.itemId, { state: "failed", reason: m.reason });
    if (expanded.has(m.itemId) || fullscreenAskId === "i:" + m.itemId) render();
  } else if (m.type === "hoverCards") {
    // rail-dot hover in the CHAT panel → white-outline the card(s) built from
    // that turn, plus the matching ROWS inside an open modal (eid). The host
    // fans the same hover out to the timeline.
    extHoverKeys = new Set(Array.isArray(m.keys) ? m.keys.map(String) : []);
    extHoverEid = typeof m.eid === "string" && m.eid ? m.eid : null;
    applyExtHover();
  } else if (m.type === "openCard" && typeof m.key === "string") {
    // rail-dot click → open this card's modal (key is fullscreenAskId-shaped:
    // ask itemId, "i:<itemId>" standalone, "g:<turnId>" group). hl = the clicked
    // turn's event id: ring its row(s) and scroll the first one into view.
    fullscreenAskId = m.key;
    if (typeof m.hl === "string" && m.hl) extHoverEid = m.hl;
    renderModal();
    applyExtHover();
    if (extHoverEid) document.querySelector(".dot-hl[data-eid]")?.scrollIntoView({ block: "center" });
  } else if (m.type === "pickerOptions" && typeof m.name === "string") {
    // the host read the blocked session's live resume-picker screen — show the
    // same options in-page; a choice goes back as keystrokes (transport only,
    // the user decides — the never-auto-answer rule holds).
    showPickerDialog(String(m.name), Array.isArray(m.options) ? m.options.map(String) : []);
  }
});

// ---- in-page resume-picker dialog (the answerPicker flow, no native QuickPick) ----
function showPickerDialog(name: string, options: string[]) {
  document.getElementById("picker-dialog")?.remove();
  if (!options.length) return;   // host already toasted "no longer on screen"
  const overlay = el("div", "pickdlg-overlay"); overlay.id = "picker-dialog";
  const box = el("div", "pickdlg-box");
  const title = el("div", "pickdlg-title");
  title.textContent = `${name} is waiting on the resume picker — choose to answer it`;
  box.append(title);
  options.forEach((opt, i) => {
    const btn = el("button", "pickdlg-opt");
    btn.textContent = opt;
    btn.onclick = () => {
      vscodeApi?.postMessage({ type: "answerPickerChoice", name, n: i });
      overlay.remove();
    };
    box.append(btn);
  });
  const cancel = el("button", "pickdlg-opt pickdlg-cancel");
  cancel.textContent = "Cancel";
  cancel.onclick = () => overlay.remove();
  box.append(cancel);
  overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
  document.body.appendChild(overlay);
  (box.querySelector("button") as HTMLElement | null)?.focus();
}

// White outline for cards named by a chat rail-dot hover — and, when a modal is
// open, for the modal rows/node-lines whose event matches (data-eid, set in
// renderTreeNode). Re-applied after each render() since reconcile/renderModal
// may rebuild nodes mid-hover.
let extHoverKeys = new Set<string>();
let extHoverEid: string | null = null;
function applyExtHover() {
  document.querySelectorAll<HTMLElement>("[data-key]").forEach((c) => {
    c.classList.toggle("dot-hl", extHoverKeys.has(c.dataset.key || ""));
  });
  document.querySelectorAll<HTMLElement>("[data-eid]").forEach((c) => {
    c.classList.toggle("dot-hl", !!extHoverEid && c.dataset.eid === extHoverEid);
  });
}

// Keep "Xm ago" honest between host pushes (host reposts ~1×/min for color fade).
setInterval(() => {
  const now = Math.floor(Date.now() / 1000);
  for (const [id, card] of cardEls) {
    const it = items.find((i) => i.itemId === id);
    const t = (card as any)._time as HTMLElement | undefined;
    if (it && t) t.textContent = relAge(now - it.t);
  }
  for (const [id, card] of askEls) {
    const it = asks.find((a) => a.itemId === id);
    const t = (card as any)._time as HTMLElement | undefined;
    if (it && t) t.textContent = relAge(now - it.t);
  }
  for (const [id, card] of blockedEls) {
    const b = blocked.find((x) => x.sid === id);
    const t = (card as any)._time as HTMLElement | undefined;
    if (b && t) t.textContent = "blocked " + relAge(now - b.since).replace(/ ago$/, "");
  }
}, 15000);

vscodeApi?.postMessage({ type: "ready" });
