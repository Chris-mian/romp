// STATUS-LINE WIDGETS (T409, the user 2026-09-13): the items the line above the composer carries besides its fixed
// parts are WIDGETS in a registry, on the model of the tab-title widgets (tab-widgets.ts): composed onto the line in a
// configured set and order, and configured from the settings gear (the Chat tab's Status line section), where each
// widget is a row showing what it draws (a live rendering over a synthetic session record), an on/off switch and its
// own options. The user's word: the model, the effort and the context stay (fixed, with the state chip and its timer,
// the mode and fast controls, the stop button and the transient lines); the folder and the git branch are widgets
// that default on; the session's name is a widget that defaults off (the tab above already names it); the host is a
// widget that defaults off and renders only for a session on another machine. No gear on the line itself: the
// settings section is the whole entry point.
//
// ONE module for both bundles: the chat (render.ts composes the line from it) and the gear (gear.js renders the rows'
// live demos from the same render functions), so a row's demo and the line can never draw a widget differently. Pure
// over the DOM it is handed (document.createElement), so node tests drive it on a tiny DOM.
//
// Two SLOTS: `left`, before the state chip; `right`, leading the right cluster ahead of the controls. The store is
// settings.statusWidgets = { on, order, opts } (widget-prefs.ts, the tab widgets' shape and rules), per browser like
// every gear setting. The two keys the widgets replace, showBranch and showSessionBadge, stay in the store as MIRRORS
// (settings.ts): every save writes them from the prefs, and nobody reads them. A store with no statusWidgets reads the
// widgets' defaults whatever those keys say (the one-shot migration, see statusWidgetPrefs): the branch's default
// flipped on under a fresh key, never under the old one, since the gear's whole-object saves had merged the old default
// into every store, which is also why the old value is no choice.
import { badgeSpec } from "./session-badge";
import { type WidgetOption, type WidgetPrefs, emptyWidgetPrefs, normalizeWidgetPrefs, orderWidgets, sanitizeOrder, widgetOn, widgetOpts } from "./widget-prefs";

export type StatusSlot = "left" | "right";
/** The slice of the session record the widgets read. */
export interface StatusRecord {
  id: string;
  name: string;
  color: { bg?: string | null } | null;
  cwd: string;
  gitBranch: string;
  workTree: { dir: string; branch: string } | null;
  host: string;   // the host a REMOTE session runs on (host-prefix.ts hostOf), "" for a local one
}
export interface StatusWidget {
  id: string;                 // "folder" | "branch" | "name" | "host" | a contributor's id
  label: string;              // the settings row's name
  description: string;        // one line: what it shows and when
  defaultOn: boolean;         // the default set
  slot: StatusSlot;
  options?: WidgetOption[];
  render(rec: StatusRecord, opts: Record<string, string>): HTMLElement | null;   // null = nothing on this line
  demo: StatusRecord;         // what the settings row renders over
}
export type StatusWidgetPrefs = WidgetPrefs;

// the demo's NAME is the placeholder session_name (T415 part two, the user 2026-09-14: new copy, wanted in every demo tab and in the
// name widget's demo chip), worn in the identity colour the way a real tab wears its name; the sid stays the demo's
export const DEMO_RECORD: StatusRecord = {
  id: "demo", name: "session_name", color: { bg: "#9cd2ff" }, cwd: "/home/user/projects/notes-api",
  gitBranch: "search-module", workTree: null, host: "TESTHOST",
};

const REGISTRY: StatusWidget[] = [];

/** Register a widget (by id: a second registration replaces the first). Registration order is the default order. */
export function registerStatusWidget(w: StatusWidget): void {
  const i = REGISTRY.findIndex((x) => x.id === w.id);
  if (i >= 0) REGISTRY[i] = w; else REGISTRY.push(w);
}
export function statusWidgets(): StatusWidget[] { return REGISTRY.slice(); }
export function statusWidget(id: string): StatusWidget | undefined { return REGISTRY.find((w) => w.id === id); }

/** The stored prefs, normalized; with no stored object, nothing set, so every widget's own default rules (the branch
 *  on, the session name off). The two keys the widgets replaced, showBranch and showSessionBadge, are NOT read here or
 *  anywhere: the one-shot migration (the user's open call, decided through the manager 2026-09-13). A store that carries
 *  them without statusWidgets got them from a gear whose whole-object save merged its own default into every store
 *  (true for stores first saved 2026-06-23 to 2026-08-10, false after), so the value is no choice; the widget defaults
 *  apply, and the keys become mirrors (legacyOfStatusPrefs) from the first save of the prefs. A reader who had turned
 *  the branch off deliberately sees it return once and turns it off again: the store cannot tell that gesture from the
 *  gear's default, which is why it was the user's call. */
export function statusWidgetPrefs(v: unknown): StatusWidgetPrefs {
  const o = normalizeWidgetPrefs(v);
  if (o) { o.order = sanitizeOrder(o.order, (id) => REGISTRY.some((w) => w.id === id)); return o; }
  return emptyWidgetPrefs();
}

/** The prefs as the two legacy keys, for the mirror older readers keep reading. */
export function legacyOfStatusPrefs(prefs: StatusWidgetPrefs): { showBranch: boolean; showSessionBadge: boolean } {
  const br = statusWidget("branch"), nm = statusWidget("name");
  return { showBranch: br ? widgetOn(prefs, br) : prefs.on.branch === true,
           showSessionBadge: nm ? widgetOn(prefs, nm) : prefs.on.name === true };
}

export function statusWidgetOn(prefs: StatusWidgetPrefs, w: StatusWidget): boolean { return widgetOn(prefs, w); }
export function statusWidgetOpts(prefs: StatusWidgetPrefs, w: StatusWidget): Record<string, string> { return widgetOpts(prefs, w); }

/** The registered widgets in composition order (widget-prefs.ts orderWidgets), filtered to one slot when asked. */
export function orderedStatusWidgets(prefs: StatusWidgetPrefs, slot?: StatusSlot): StatusWidget[] {
  const out = orderWidgets(prefs, REGISTRY);
  return slot ? out.filter((w) => w.slot === slot) : out;
}

/** Compose one slot onto the line: every enabled widget of the slot, in order, appended when it renders something.
 *  Returns the nodes appended. */
export function composeStatusWidgets(host: HTMLElement, slot: StatusSlot, rec: StatusRecord, prefs: StatusWidgetPrefs): HTMLElement[] {
  const out: HTMLElement[] = [];
  for (const w of orderedStatusWidgets(prefs, slot)) {
    if (!widgetOn(prefs, w)) continue;
    let node: HTMLElement | null = null;
    try { node = w.render(rec, widgetOpts(prefs, w)); } catch { node = null; }   // a contributed widget's throw never costs the line
    if (!node) continue;
    host.appendChild(node);
    out.push(node);
  }
  return out;
}

/** The settings rows' visual order: the left slot's widgets, then the right slot's, each in composition order. The
 *  line has no divider row (the user's word: its slots stay the registry's), so a drag or an arrow key moves a row
 *  within its slot's group only (gear.js holds it there with a cue); this is the list it reorders and stores back. */
export function statusListOrder(prefs: StatusWidgetPrefs): string[] {
  return [...orderedStatusWidgets(prefs, "left").map((w) => w.id), ...orderedStatusWidgets(prefs, "right").map((w) => w.id)];
}

/** A rendering made INERT for a demo or a preview: the folder's click act and its link dress go (review round two: in the
 *  VS Code chat panel the gear mounts in the delegate's own document, and a demo's act posted a real openFolder for the
 *  demo path), and so does the click clause of its title, which would promise what nothing delivers (round three, low 3);
 *  the path stays, so it still reads on hover. The walk over [data-act] reaches a folder nested in a composed line. */
export function makeInert<T extends HTMLElement>(node: T): T {
  const strip = (n: HTMLElement) => {
    n.removeAttribute("data-act"); n.removeAttribute("data-cwd"); n.removeAttribute("data-id"); n.classList.remove("folder-link");
    if (n.title) n.title = n.title.replace(/\s+·\s+click to [^·]*$/, "");
  };
  strip(node);
  node.querySelectorAll<HTMLElement>("[data-act]").forEach(strip);
  return node;
}

/** A settings row's live rendering: the widget over its demo record, as the line would draw it, made inert. */
export function renderStatusWidgetDemo(w: StatusWidget, prefs: StatusWidgetPrefs): HTMLElement | null {
  try { const n = w.render(w.demo, widgetOpts(prefs, w)); return n ? makeInert(n) : null; } catch { return null; }
}

// ── the folder's pieces, shared with render.ts (they lived there until T409) ──────────────────────────────────────

function el(tag: string, cls: string): HTMLElement { const e = document.createElement(tag); e.className = cls; return e; }

/** The small inline-SVG folder in the romp line-icon style (16-unit viewBox, currentColor, so it inherits the dim
 *  statusline tint and brightens on the folder-link hover): the monochrome replacement for the folder emoji beside
 *  the statusline directory (the user 2026-07-15). Trusted constant markup. */
export const FOLDER_ICON_SVG = '<svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" '
  + 'stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">'
  + '<path d="M2 12.6 a1 1 0 0 1-1-1 V4.4 a1 1 0 0 1 1-1 H5.9 a1 1 0 0 1 0.7 0.3 L7.8 5 '
  + 'H13 a1 1 0 0 1 1 1 V11.6 a1 1 0 0 1-1 1 Z"/></svg>';
export function folderIconNode(): HTMLElement {
  const span = el("span", "status-dir-icon");
  span.innerHTML = FOLDER_ICON_SVG;
  return span;
}

/** A click on a folder location OPENS it. On the web the click BROWSES the folder in the dashboard (the user
 *  2026-08-14), the affordance that works from every device, where OS-open acted on the KERNEL's machine; where the
 *  listing opens is decided at the click (render.ts openBrowse). In VS Code the browser overlay does not exist, so the
 *  click keeps opening the folder host-side. The act rides data attributes a document-level delegate reads, so the
 *  per-push rebuild cannot drop it; the session id rides along so a REMOTE session's click SSHes out instead of no-op'ing
 *  on a local path (2026-07-03). */
export function folderLink(elem: HTMLElement, cwd: string, sid?: string,
                           web: boolean = typeof location !== "undefined" && (location.protocol === "http:" || location.protocol === "https:")): void {
  if (!cwd) return;
  elem.dataset.act = web ? "browseFiles" : "openFolder";   // the act names the intent; openBrowse routes it
  elem.dataset.cwd = cwd;
  if (sid) elem.dataset.id = sid;
  elem.classList.add("folder-link");
  elem.title = cwd + (elem.dataset.act === "browseFiles"
    ? "  ·  click to browse this folder" : "  ·  click to open this folder");
}

// ── the built-in widgets ────────────────────────────────────────────────

// The SESSION NAME (the user 2026-09-09): the name on its identity colour, the colour its tab label and timeline lane
// wear, before the state chip, so the line reads "<session> · Working". Off by default (the maintainers 2026-09-10,
// the user again on T409: the tab above already names it; it earns its place in split columns). Left slot.
registerStatusWidget({
  id: "name", label: "Session name", defaultOn: false, slot: "left",
  description: "the session's name on its colour, before the state chip; the tab above already names it",
  demo: DEMO_RECORD,
  render(rec) {
    const bs = badgeSpec(rec);
    if (!bs) return null;
    const b = el("span", "chip chip-session");
    b.textContent = bs.text;
    if (bs.bg) b.style.background = bs.bg;
    b.title = bs.text;   // the full name when the chip clips a long one
    return b;
  },
});

// The FOLDER (the user 2026-06-23): the session's working directory (the current one; a tab-menu move changes it),
// leading the right cluster. By name (the basename) or, on the option, the full path; the full path on hover either
// way, and a click opens it (folderLink). Nothing when no directory is known.
registerStatusWidget({
  id: "folder", label: "Folder", defaultOn: true, slot: "right",
  description: "the directory the session runs in, by name; the full path on hover, a click opens it",
  options: [{ key: "show", label: "Show", default: "name",
              choices: [{ value: "name", label: "Name only" }, { value: "path", label: "Full path" }] }],
  demo: DEMO_RECORD,
  render(rec, opts) {
    if (!rec.cwd) return null;
    const dir = el("span", opts.show === "path" ? "status-dir status-dir-full" : "status-dir");
    dir.appendChild(folderIconNode());
    const cwd = rec.cwd.replace(/\/+$/, "");
    dir.appendChild(document.createTextNode(" " + (opts.show === "path" ? cwd : (cwd.split("/").pop() || cwd))));
    folderLink(dir, rec.cwd, rec.id);
    return dir;
  },
});

// The GIT BRANCH (the user 2026-06-23; off by default from 2026-08-10, on again by the user's word on T409), just
// right of the folder: the WORKTREE's branch when the session works in one, else the registered directory's. Read
// from the TOP-LEVEL session fields, never the head system event: that event is windowed out of the wire tail on
// any long session, which used to blank the branch on most sessions (the user 2026-06-30).
registerStatusWidget({
  id: "branch", label: "Git branch", defaultOn: true, slot: "right",
  description: "the branch the session is on, the worktree's when it runs in one; nothing when no branch is known",
  demo: DEMO_RECORD,
  render(rec) {
    const liveBr = (rec.workTree && rec.workTree.branch) || rec.gitBranch;
    if (!liveBr) return null;
    const br = el("span", "status-branch");
    br.textContent = "⎇ " + liveBr;
    br.title = rec.workTree ? `worktree ${rec.workTree.dir} · git branch: ${liveBr}` : "git branch: " + liveBr;
    return br;
  },
});

// The HOST (T409): the name of the machine a REMOTE session runs on, nothing for a local one, so a local install never
// sees it. Off by default (the user's word); the one fact the line lacks once sessions span hosts.
registerStatusWidget({
  id: "host", label: "Host", defaultOn: false, slot: "right",
  description: "the host's name when the session runs on another machine; nothing for a local session",
  demo: DEMO_RECORD,
  render(rec) {
    if (!rec.host) return null;
    const h = el("span", "status-branch status-host");
    h.textContent = "@ " + rec.host;
    h.title = "runs on " + rec.host;
    return h;
  },
});
