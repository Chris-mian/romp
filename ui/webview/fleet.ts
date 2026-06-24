// Fleet — a by-SESSION view of open work across the whole fleet (the user 2026-06-23). The feed groups goal
// cards by STATUS (working / needs-you / done); Fleet groups the SAME data by SESSION: every live session
// with open work, its goals listed beneath it, top to bottom. Hosted in the chat pane behind a toggle. It
// reuses the feed WS payload (m.asks) verbatim — no new kernel data. V1: one line per open goal; completed
// work is hidden behind a bottom "Show completed" checkbox (default OFF), so the default stays a true glance.
type Color = { bg: string; fg: string } | null;
type Column = "working" | "needs_input" | "completed";
interface Goal {
  itemId: string; sid: string; name: string; color: Color;
  text: string; t: number; live: boolean; column: Column;
  trgb?: [number, number, number];
  blocked?: unknown; awaiting?: { why?: string | null } | null; provisional?: boolean;
}

const vscodeApi =
  typeof (window as any).acquireVsCodeApi === "function" ? (window as any).acquireVsCodeApi() : undefined;

let goals: Goal[] = [];
let working = new Set<string>();
const DONE_KEY = "romp:fleetShowDone";
function showDone(): boolean {
  try { return localStorage.getItem(DONE_KEY) === "1"; } catch { return false; }
}
function setShowDone(on: boolean) {
  try { localStorage.setItem(DONE_KEY, on ? "1" : "0"); } catch { /* ignore */ }
}

function el(tag: string, cls?: string): HTMLElement {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  return e;
}
const isOpen = (g: Goal) => g.column !== "completed";   // open = still working or needs-you (not done)

// One session's goals, newest activity first; sessions ordered by their most recent goal.
function bySession(): Array<{ sid: string; name: string; color: Color; live: boolean; items: Goal[] }> {
  const groups = new Map<string, Goal[]>();
  for (const g of goals) (groups.get(g.sid) ?? groups.set(g.sid, []).get(g.sid)!).push(g);
  const out: Array<{ sid: string; name: string; color: Color; live: boolean; items: Goal[]; t: number }> = [];
  for (const [sid, items] of groups) {
    items.sort((a, b) => b.t - a.t);
    const head = items[0];
    out.push({ sid, name: head.name, color: head.color, live: items.some((i) => i.live), items, t: head.t });
  }
  out.sort((a, b) => b.t - a.t);
  return out;
}

function statusDot(g: Goal): HTMLElement {
  const d = el("span", "fl-dot");
  if (g.column === "completed") d.classList.add("done");
  else if (g.column === "needs_input" || g.blocked) d.classList.add("block");
  else if (g.awaiting) d.classList.add("await");
  else d.classList.add("work");
  return d;
}

function render() {
  const list = document.getElementById("fleet-list");
  if (!list) return;
  list.replaceChildren();
  const sd = showDone();
  const sessions = bySession()
    .map((s) => ({ ...s, items: s.items.filter((g) => sd || isOpen(g)) }))
    .filter((s) => s.items.length > 0);   // hide a session with nothing to show

  if (!sessions.length) {
    const empty = el("div", "fl-empty");
    empty.textContent = sd ? "No work across the fleet yet." : "No open work — every session is clear.";
    list.appendChild(empty);
  }

  for (const s of sessions) {
    const sec = el("div", "fl-session");
    const head = el("div", "fl-head");
    if (working.has(s.sid)) head.appendChild(el("span", "fl-workdot"));
    const nm = el("span", "fl-name");
    nm.textContent = s.name;
    if (s.color?.bg) nm.style.color = s.color.bg;
    head.appendChild(nm);
    head.title = "Open this session";
    head.onclick = () => vscodeApi?.postMessage({ type: "openSession", id: s.sid });
    sec.appendChild(head);

    for (const g of s.items) {
      const row = el("div", "fl-goal" + (g.column === "completed" ? " done" : ""));
      row.appendChild(statusDot(g));
      const tx = el("span", "fl-text");
      tx.textContent = g.text || "(untitled)";
      if (g.trgb) tx.style.color = `rgb(${g.trgb[0]},${g.trgb[1]},${g.trgb[2]})`;
      row.appendChild(tx);
      row.title = "Open this session";
      row.onclick = () => vscodeApi?.postMessage({ type: "openSession", id: g.sid });
      sec.appendChild(row);
    }
    list.appendChild(sec);
  }
}

function mountFoot() {
  const foot = document.getElementById("fleet-foot");
  if (!foot) return;
  foot.replaceChildren();
  const lbl = el("label", "fl-toggle");
  const cb = document.createElement("input");
  cb.type = "checkbox";
  cb.checked = showDone();
  cb.addEventListener("change", () => { setShowDone(cb.checked); render(); });
  lbl.appendChild(cb);
  lbl.appendChild(document.createTextNode("Show completed"));
  foot.appendChild(lbl);
}

window.addEventListener("message", (e: MessageEvent) => {
  const m = e.data;
  if (!m || m.type !== "feed") return;
  goals = Array.isArray(m.asks) ? (m.asks as Goal[]) : [];
  working = new Set(Array.isArray(m.working) ? m.working : []);
  render();
});

mountFoot();
render();

export {};   // make this a MODULE (own scope) so its el/vscodeApi/Column don't collide with feed.ts (a global script)
