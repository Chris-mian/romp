// The romp strip — VS Code's stand-in for the web shell's bottom rail: the
// account usage windows (the rail's used-over-elapsed bar pairs) and the
// settings gear, docked below the chat composer / the feed's control bar
// (the user 2026-07-13). The web shell keeps its own rail, so the strip
// renders ONLY where the host opts in (window.__rompShowStrip, injected by
// the VS Code builders); when chat and feed are both visible the host hides
// the chat's copy (a {type:"stripShow"} message) — feed wins.
//
// Usage data: an initial GET /usage via the host-injected kernel base, then
// live {type:"usage"} pushes relayed by the host from the timeline view's
// forwards — the same event source the web rail rides.
//
// Every kernel fetch routes through media.ts kernelUrl(): it prepends the
// host-injected base AND appends ?token= when the host injected one — the
// kernel gates every request on the serve token (loopback included), and a
// webview's cross-origin fetch carries no cookie.
import { kernelUrl } from "./media";

export type UsageWindow = {
  readout?: string;     // overrides the % readout (a spend row shows dollars)
  key: string;
  label: string;        // the rail's expanded label
  short: string;        // the compressed tag a narrow strip swaps in ("5h" / "7d" / "F5")
  pct: number | null;   // used % of the limit / budget (LAST-KNOWN when unknown — drawn faded); null = no honest denominator (a spend row with no budget)
  elapsedPct: number | null;  // % of the window elapsed (pace comparison)
  unknown: boolean;     // the window reset since the last report — the reading no longer describes the present
  title: string;        // hover detail
};

// The rail's window set: [key, span seconds, expanded label, compressed tag].
const WINS: Array<[string, number, string, string]> = [
  ["fiveHour", 5 * 3600, "5 hours", "5h"],
  ["sevenDay", 7 * 86400, "7 days", "7d"],
  ["fable", 7 * 86400, "Fable 5", "F5"],
];

// The rail's usage color ramp: green under 70%, amber under 90%, red at 90+.
export function usageColor(pct: number): string {
  return pct >= 90 ? "#c0392b" : pct >= 70 ? "#e0b020" : "#54B204";
}

export function fmtAgo(ep: number, nowS: number): string {
  const dt = Math.max(0, nowS - ep);
  const d = Math.floor(dt / 86400);
  const h = Math.floor((dt % 86400) / 3600);
  const m = Math.floor((dt % 3600) / 60);
  return ((d ? `${d}d ` : "") + (h || d ? `${h}h ` : "") + `${m}m`).trim() + " ago";
}

export function fmtReset(resetsAt: number, nowS: number): string {
  const dt = resetsAt - nowS;
  if (dt <= 0) return "soon";
  const d = Math.floor(dt / 86400);
  const h = Math.floor((dt % 86400) / 3600);
  const m = Math.floor((dt % 3600) / 60);
  return (d ? `${d}d ` : "") + (h || d ? `${h}h ` : "") + `${m}m`;
}

// /usage payload → the windows worth drawing (unreported windows drop out).
export function usageWindows(usage: any, nowS: number): UsageWindow[] {
  const out: UsageWindow[] = [];
  for (const [key, span, label, short] of WINS) {
    const seg = usage && usage[key];
    if (!seg || typeof seg.pct !== "number") continue;
    const rolled = !!(seg.resetsAt && nowS > seg.resetsAt);   // the window reset since the last report
    // A rolled window's reading no longer describes the PRESENT window — that is UNKNOWN, not 0
    // (the user 2026-07-31: a remote whose kernel had no live session to ask sat on a days-old
    // snapshot, and the rail drew a confident 0% beside a live account's real bars). The last-known
    // fill still draws — FADED, with a "?" readout — so unknown and genuinely-empty can never be
    // confused. Same fail-loudly rule as every other stale source.
    const pct = Math.max(0, Math.min(100, seg.pct));
    let elapsedPct: number | null = null;
    if (!rolled && seg.resetsAt && span) {
      elapsedPct = Math.max(0, Math.min(100, Math.round(((nowS - (seg.resetsAt - span)) / span) * 100)));
    }
    out.push({
      key, label, short, pct, elapsedPct, unknown: rolled,
      title: rolled
        ? `${label} — window reset ${fmtAgo(seg.resetsAt, nowS)} and no reading has arrived since — current usage unknown (last known ${pct}%)`
        : `${label} — used ${pct}%`
          + (elapsedPct != null ? ` · ${elapsedPct}% through the window` : "")
          + (seg.resetsAt ? ` · resets in ${fmtReset(seg.resetsAt, nowS)}` : ""),
    });
  }
  return out;
}

export function fmtTok(n: number): string {
  if (n >= 1e9) return (n / 1e9).toFixed(1).replace(/\.0$/, "") + "B";
  if (n >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1).replace(/\.0$/, "") + "k";
  return String(n);
}

// API-key SPEND windows mirror the subscription bars' grammar exactly — same rows, same labels,
// same twin tracks — so flipping between the two auth modes reads instantly (the user 2026-08-04, who
// asked for "5 hours / week / month, visually similar"). A row FILLS only when spend-budgets.json names
// that window's budget: the fill is spend-over-budget, and without a cap there is no honest fraction —
// the row then carries plain dollars in the readout slot and no used-track. Rolling windows (5h/7d)
// have no reset boundary, so only month-to-date draws the elapsed track. Keyed on the spend windows'
// PRESENCE, not the apiKey flag: with per-session auth a host's payload carries bars AND its key's
// spend at once (the user 2026-08-08), and the strip should show both, not silently drop the dollars.
export const SPEND_WINS: Array<[string, string, string]> = [
  ["fiveHour", "5 hours", "5h"],
  ["sevenDay", "7 days", "7d"],
  ["month", "Month", "mo"],
];
export function spendWindows(usage: any, nowS: number): UsageWindow[] {
  const sp = usage && usage.spend;
  if (!sp) return [];
  const out: UsageWindow[] = [];
  for (const [key, label, short] of SPEND_WINS) {
    const seg = sp[key];
    if (!seg || typeof seg.usd !== "number") continue;
    const budget = typeof seg.budget === "number" && seg.budget > 0 ? seg.budget : null;
    const pct = budget != null ? Math.max(0, Math.min(100, Math.round((seg.usd / budget) * 100))) : null;
    let elapsedPct: number | null = null;
    if (key === "month" && budget != null) {
      const d = new Date(nowS * 1000);
      const dim = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
      elapsedPct = Math.max(0, Math.min(100, Math.round(((d.getDate() - 1 + d.getHours() / 24) / dim) * 100)));
    }
    const turns = seg.turns || 0;
    out.push({
      key, label, short, pct, elapsedPct, unknown: false,
      // dollars AND tokens stay VISIBLE (the user 2026-08-05 — the hover-only split hid them again);
      // WHOLE dollars, no cents, matching the rail everywhere (the user 2026-08-09)
      readout: "$" + Math.round(seg.usd) + " · " + fmtTok(seg.tok || 0) + " tok",
      title: label + " — $" + Math.round(seg.usd) + " · " + fmtTok(seg.tok || 0) + " tokens · "
        + turns + " turn" + (turns === 1 ? "" : "s")
        + (budget != null ? " · " + pct + "% of the $" + budget + " budget"
           : " · no budget set — dollars only, no fill (set one in spend-budgets.json)")
        + " · API-key billing",
    });
  }
  return out;
}

// Which panes get a quick-open label when hidden (the user 2026-07-13, who wanted chat,
// outline, and feed — only the ones that aren't currently shown). Timeline lives
// in VS Code's own panel, so it isn't listed.
export const STRIP_PANES: Array<{ key: string; label: string }> = [
  { key: "chat", label: "Chat" },
  { key: "fleet", label: "Outline" },
  { key: "feed", label: "Feed" },
];

export function initStrip(openSettings: () => void, post?: (m: Record<string, unknown>) => void): void {
  if (!(window as any).__rompShowStrip) return;
  if (document.getElementById("romp-strip")) return;

  const strip = document.createElement("div");
  strip.id = "romp-strip";
  const usageWrap = document.createElement("div");
  usageWrap.id = "strip-usage";
  // Quick-opens for the panes NOT currently on screen — the host pushes the
  // hidden-set ({type:"stripPanes"}) on every panel create/dispose/view-state.
  const panesWrap = document.createElement("div");
  panesWrap.id = "strip-panes";
  // ↻ kernel restart — the rail's #rrefresh twin. The pipes reconnect and the
  // host reloads the webviews on their own once the kernel is back.
  const refresh = document.createElement("button");
  refresh.id = "strip-refresh";
  refresh.title = "Restart the romp kernel";
  refresh.textContent = "↻";
  refresh.addEventListener("click", (e) => {
    e.stopPropagation();
    refresh.disabled = true;
    fetch(kernelUrl("/restart"), { method: "POST" }).catch(() => { /* the reconnect machinery reports */ });
    setTimeout(() => { refresh.disabled = false; }, 8000);   // pure failsafe re-arm; the reload normally lands first
  });
  // Remote kernels — the rail's #rail-net twin (same endpoints; the shell keeps
  // its own copy until federation unifies them).
  const net = document.createElement("button");
  net.id = "strip-net";
  net.title = "Remote kernels";
  net.innerHTML = "<svg viewBox='0 0 16 16' width='15' height='15'>"
    + "<path d='M8 5 L8 8 M3 11 L3 8 L13 8 L13 11' fill='none' stroke='currentColor' stroke-width='1' stroke-linejoin='round'/>"
    + "<rect x='6' y='1' width='4' height='4' rx='0.6' fill='currentColor'/>"
    + "<rect x='1' y='11' width='4' height='4' rx='0.6' fill='currentColor'/>"
    + "<rect x='11' y='11' width='4' height='4' rx='0.6' fill='currentColor'/></svg>";
  const gear = document.createElement("button");
  gear.id = "strip-gear";
  gear.title = "romp settings";
  gear.textContent = "⛭";
  gear.addEventListener("click", (e) => { e.stopPropagation(); openSettings(); });
  // The actions travel as ONE cluster pushed to the right edge (margin-left:auto,
  // not a spacer item): the strip WRAPS rather than overflow into a horizontal
  // scrollbar (the user 2026-07-13), and a wrapped cluster keeps its right pin
  // on whatever row it lands on — a spacer only pushes within its own row.
  const acts = document.createElement("div");
  acts.className = "strip-acts";
  acts.append(refresh, net, gear);
  strip.append(usageWrap, panesWrap, acts);
  document.body.appendChild(strip);
  initNetPopover(net, post);

  // The compress ladder, MEASURED (the user 2026-07-14): fixed width thresholds
  // stepped the labels down while free space remained (with every pane open there
  // are no quick-open buttons, so the strip's real content is far narrower than
  // any hardcoded threshold could know). Instead the bars are fluid (strip.css:
  // .ru-bars flex-basis 54px, min-width 18px — they compress continuously as the
  // pane narrows) and a tier is stepped only when the bars are actually pinched
  // below comfort, or the strip has wrapped. Tiers on #romp-strip[data-tier]:
  // 0 full label · 1 short tag · 2 no % readout · 3 bars only. offsetWidth/Top
  // (layout px) keep the math zoom-independent under the host's uiZoom.
  const BAR_COMFORT = 34;
  function fit() {
    if (!usageWrap.childElementCount) { strip.removeAttribute("data-tier"); return; }
    for (let t = 0; ; t++) {
      strip.dataset.tier = String(t);
      if (t >= 3) return;   // narrowest tier — from here the fluid bars + row wrap absorb the rest
      const bars = usageWrap.querySelector(".ru-bars") as HTMLElement | null;
      const pinched = !!bars && bars.offsetWidth < BAR_COMFORT;
      const wrapped = acts.offsetTop >= usageWrap.offsetTop + usageWrap.offsetHeight - 1;
      if (!pinched && !wrapped) return;
    }
  }
  let fitW = 0;
  try {
    new ResizeObserver(() => {
      const w = strip.offsetWidth;
      if (Math.abs(w - fitW) < 1) return;   // our own tier flips / wraps only change height
      fitW = w;
      fit();
    }).observe(strip);
  } catch { /* no ResizeObserver → the fluid bars + wrap still prevent overflow */ }

  function renderPanes(hidden: Record<string, boolean>) {
    panesWrap.textContent = "";
    for (const p of STRIP_PANES) {
      if (!hidden[p.key]) continue;
      const b = document.createElement("button");
      b.className = "strip-pane";
      b.textContent = p.label;
      b.title = `Open the ${p.label} pane`;
      b.addEventListener("click", (e) => { e.stopPropagation(); post?.({ type: "openPane", pane: p.key }); });
      panesWrap.appendChild(b);
    }
    fit();
  }



  function render(usage: any) {
    const nowS = Math.floor(Date.now() / 1000);
    usageWrap.textContent = "";
    // ONE loop, one row builder: subscription windows and API spend windows are the same element, so
    // the two auth modes cannot drift apart visually (the user 2026-08-04)
    for (const w of usageWindows(usage, nowS).concat(spendWindows(usage, nowS))) {
      const box = document.createElement("span");
      box.className = "ru-w" + (w.unknown ? " ru-unk" : "");
      box.title = w.title;
      // Both the expanded label and the compressed tag render; the [data-tier]
      // ladder in strip.css shows exactly one (or neither at the narrowest tier),
      // so a tier flip never needs a JS re-render.
      const name = document.createElement("span");
      name.className = "ru-name";
      const nameFull = document.createElement("span");
      nameFull.className = "ru-name-full";
      nameFull.textContent = w.label;
      const nameShort = document.createElement("span");
      nameShort.className = "ru-name-short";
      nameShort.textContent = w.short;
      name.append(nameFull, nameShort);
      const bars = document.createElement("span");
      bars.className = "ru-bars";
      const mkTrack = (pct: number, color: string) => {
        const track = document.createElement("span");
        track.className = "ru-track";
        const fill = document.createElement("span");
        fill.className = "ru-fill";
        fill.style.width = `${pct}%`;
        fill.style.background = color;
        track.appendChild(fill);
        return track;
      };
      if (w.unknown) {
        // NO BARS AT ALL for an unknown window (the user 2026-07-31, round 2): a faded last-known fill
        // still draws a value, and we do not have one — the length itself is the lie. The bars' slot
        // holds a single "?" instead, keeping the row's alignment; the last-known number stays in the
        // hover, explicitly labelled. The % readout is dropped too — the "?" IS the readout, and it
        // survives the narrow tiers, where .ru-pct is hidden but the bars slot is always drawn.
        const q = document.createElement("span");
        q.className = "ru-qmark";
        q.textContent = "?";
        bars.appendChild(q);
        box.append(name, bars);
      } else {
        if (w.pct != null) bars.appendChild(mkTrack(w.pct, usageColor(w.pct)));   // no honest denominator → no fill
        if (w.elapsedPct != null) bars.appendChild(mkTrack(w.elapsedPct, "#6b7a8c"));
        const pct = document.createElement("span");
        pct.className = "ru-pct";
        pct.textContent = w.readout ?? `${w.pct}%`;
        box.append(name, bars, pct);
      }
      usageWrap.appendChild(box);
    }
    fit();
  }

  window.addEventListener("message", (ev: MessageEvent) => {
    const m = ev.data;
    if (!m) return;
    if (m.type === "usage") render(m.usage || null);                      // live: host-relayed timeline forwards
    else if (m.type === "stripShow") strip.style.display = m.show ? "" : "none";  // feed-over-chat rule
    else if (m.type === "stripPanes") renderPanes(m.hidden || {});        // which quick-opens to offer
  });

  fetch(kernelUrl("/usage"), { cache: "no-store" })
    .then((r) => r.json())
    .then((u) => render(u))
    .catch(() => { /* the live pushes fill it in */ });
}

// The remote-kernels popover — the strip twin of the web shell's rail-net
// popover (_LANDING_REMOTES_JS in bin/romp-kernel): same kernel endpoints
// (/ssh-hosts, /tunnels, /tunnels/detach|update|start), leaner chrome. The two
// copies unify when client federation reaches VS Code; until then remote
// SESSIONS render only in the browser — this manages the kernel's tunnels.
//
// The button acknowledges every toggle (.open accent chrome) and each toggle
// posts a clientDiag breadcrumb through the host to the kernel's
// client-diag.jsonl — the user reported the button doing nothing in VS Code
// (2026-07-14) while every repro outside VS Code works, so the next report
// comes with recorded evidence instead of guesses.
function initNetPopover(button: HTMLButtonElement, post?: (m: Record<string, unknown>) => void) {
  const pop = document.createElement("div");
  pop.id = "strip-net-pop";
  pop.hidden = true;
  const row = document.createElement("div");
  row.className = "sn-attach";
  const sel = document.createElement("select");
  const attach = document.createElement("button");
  attach.textContent = "Attach";
  row.append(sel, attach);
  const list = document.createElement("div");
  list.id = "sn-list";
  // "Automatically update" (the user 2026-07-24) — the fleet-wide alternative to a modal landing mid-screen
  // on every advance. Panel-wide, under the list, since it applies to all hosts rather than one row. Mirrors
  // the web popover's copy: the two must say the same thing.
  const autoL = document.createElement("label");
  autoL.className = "sn-auto";
  const autoCb = document.createElement("input");
  autoCb.type = "checkbox";
  const autoT = document.createElement("span");
  autoT.textContent = "Automatically update";
  autoL.append(autoCb, autoT);
  autoL.title = "Keep attached machines on this machine\n\n"
    + "When a machine is connected and its romp is simply BEHIND this one — your commits only add to what it "
    + "already has — romp pushes your build to it and restarts its kernel, in the background, without asking. "
    + "The network icon animates while that runs; hover it for the live phase.\n\n"
    + "It never fires when a push could destroy anything: a machine holding its own commits, or one whose "
    + "build this repo doesn't recognise, is left alone and keeps its manual Push button. Uncommitted local "
    + "edits are never sent — only what you have committed.";
  autoCb.addEventListener("change", () => {
    const on = autoCb.checked;
    autoCb.disabled = true;
    fetch(kernelUrl("/tunnels/autoupdate"), { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ on }) })
      .then((rp) => rp.json())
      .then((d) => {
        autoCb.disabled = false;
        if (d && d.ok) { autoCb.checked = !!d.on; schedule(600); }
        else { autoCb.checked = !on; }   // the kernel refused — show what is actually in force
      })
      .catch(() => { autoCb.disabled = false; autoCb.checked = !on; });
  });
  pop.append(row, list, autoL);
  document.body.appendChild(pop);

  const LBL: Record<string, string> = {
    up: "connected", authorizing: "authorizing…", connecting: "connecting…", starting: "connecting…",
    "no-kernel": "kernel not answering", down: "disconnected", error: "error",
  };
  // Every status explains itself on hover (the user 2026-07-22: learn it from tooltips, not the CLI).
  // Mirrors the web popover's TIP map — the two copies must say the same thing.
  const TIP: Record<string, string> = {
    up: "Connected: the ssh tunnel is open and that machine's romp kernel is answering through it. Its sessions appear in your tabs and timeline.",
    authorizing: "Opening an ssh connection and reading that machine's access token. Needs `ssh <host>` to work without a prompt.",
    connecting: "The ssh tunnel is up; waiting for the remote kernel to answer on its port.",
    starting: "The ssh tunnel is up; waiting for the remote kernel to answer on its port.",
    "no-kernel": "The tunnel is open but no romp kernel is answering on that machine. Start pushes this machine's romp there and boots it.",
    down: "The ssh tunnel is not up. romp keeps retrying on its own, waiting longer between tries the longer it stays down, so a machine that comes back is picked up without you doing anything. Try now dials immediately.",
    error: "The connection failed. Hover the status text for the reason romp got back. romp keeps retrying in the background.",
  };
  let timer: ReturnType<typeof setTimeout> | undefined;
  const schedule = (ms: number) => { clearTimeout(timer); if (!pop.hidden) timer = setTimeout(refresh, ms); };
  const busy = (s: string) => s !== "up" && s !== "down" && s !== "error" && s !== "no-kernel";

  function loadHosts() {
    fetch(kernelUrl("/ssh-hosts"), { cache: "no-store" }).then((r) => r.json()).then((d) => {
      const hs: string[] = (d && d.hosts) || [];
      sel.innerHTML = hs.length
        ? hs.map((h) => `<option value="${h}">${h}</option>`).join("")
        : `<option value="">(no ~/.ssh/config hosts)</option>`;
    }).catch(() => { sel.innerHTML = `<option value="">(kernel unreachable)</option>`; });   // loud, never silently empty
  }

  function act(path: string, host: string, b: HTMLButtonElement, busyText: string) {
    b.disabled = true;
    const prev = b.textContent;
    b.textContent = busyText;
    fetch(kernelUrl(path), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ host }) })
      .then(() => schedule(600))
      .catch(() => { b.disabled = false; b.textContent = prev; });
  }

  // A trust change confirms on a LATER poll, and renderList rebuilds every poll — so a snapshot
  // fetched before the change repainted the OLD level after it, which read as "didn't hold" and
  // invited a second click (the user 2026-07-27). Pending survives re-renders: the select shows the
  // CHOSEN level, disabled with the accent applying cue, until a snapshot agrees (the confirming
  // event — no timer). A refused write deletes the entry, so the next render honestly reverts.
  const pendingTrust = new Map<string, string>();

  // A native <select>'s open dropdown dies with its DOM node, and renderList rebuilds every row each
  // poll — at the connecting-phase 600ms cadence (schedule below) the trust picker's options dismissed
  // the instant they opened (the user 2026-08-04: click it and "it just immediately unclicks"; fine
  // once the host is up, whose 3s cadence usually leaves room). So the popover DEFERS the rebuild while
  // a trust select is engaged — focus/mousedown arms it, blur or a made choice releases — and flushes
  // the newest deferred snapshot on release: the timeline's defer-don't-rebuild idiom (_pointerHeld),
  // select-flavored. Event-based, no timers; reopening the popover resets the latch (a hidden popover
  // can never blur its way free, and its select is gone anyway).
  let trustEngaged = false;
  let deferredRender: (() => void) | null = null;
  const releaseTrust = () => {
    trustEngaged = false;
    const flush = deferredRender;
    deferredRender = null;
    if (flush) flush();
  };

  function renderList(ts: any[], known: any[] = []) {
    if (trustEngaged) { deferredRender = () => renderList(ts, known); return; }   // mid-pick — land it after
    list.textContent = "";
    button.classList.toggle("on", ts.some((t) => t.status === "up"));
    if (!ts.length && !known.length) {
      const e = document.createElement("div");
      e.className = "sn-empty";
      e.textContent = "No remotes attached.";
      list.appendChild(e);
      return;
    }
    for (const t of ts) {
      const r = document.createElement("div");
      r.className = "sn-row";
      const dot = document.createElement("span");
      dot.className = "sn-dot";
      dot.style.background = t.status === "up" ? "var(--accent, #9cd2ff)"
        : (t.status === "error" || t.status === "no-kernel") ? "#E5534B"
        : (t.status === "down") ? "#8a8a8a" : "transparent";
      if (dot.style.background === "transparent") dot.style.boxShadow = "inset 0 0 0 1.5px var(--accent, #9cd2ff)";
      dot.title = TIP[t.status] || "";
      const nm = document.createElement("span");
      nm.className = "sn-name";
      // Version drift names HOW it differs, matching the web popover: behind N (a push delivers
      // exactly those), ahead N (a pull collects them), diverged, or different build (sha unknown
      // here). Shas + the remote commit's date ride the tooltip (progressive disclosure).
      // STALE (the user 2026-07-28): drift comes from the sha of the LAST SUCCESSFUL poll, and only an `up`
      // row polled this pass. Drawn as fact, a host unreachable for hours still announced "behind 2 commits"
      // right beside the word "disconnected" — two claims that cannot both be current. Keep the number (a
      // blank is less useful) but name it as remembered, and date it in the tooltip.
      const stale = !!t.stale;
      const seen = t.lastOk ? new Date(t.lastOk * 1000).toLocaleTimeString() : "";
      let ver = "";
      if (t.outOfDate) {
        const bb = t.behindBy, ab = t.aheadBy;
        ver = " · different build";
        if (typeof bb === "number" && typeof ab === "number") {
          ver = bb > 0 && ab > 0 ? " · diverged"
            : ab > 0 ? ` · ahead ${ab} commit${ab === 1 ? "" : "s"}`
            : bb > 0 ? ` · behind ${bb} commit${bb === 1 ? "" : "s"}` : ver;
        }
        if (stale) ver = ver.replace(" · ", " · last known: ");
      }
      nm.textContent = `${t.host} — ${LBL[t.status] || t.status}` + ver;
      nm.title = (TIP[t.status] || "")
        + (t.outOfDate ? `\n\nRunning ${t.kernelSha || "?"}${t.kernelDate ? " from " + t.kernelDate : ""}; this machine is at ${t.localSha || "?"}.` : "")
        + (stale && t.outOfDate ? `\nLast confirmed ${seen || "not since this kernel started"}; not re-checked while ${LBL[t.status] || t.status}.` : "")
        + (t.outOfDate && t.checkinPeer
          ? (t.askPull
            ? " No ssh path from this machine (it checked in over its own tunnel), so Update asks it to fast-forward itself over the link it holds."
            : " No ssh path from this machine (it checked in over its own tunnel) — sync from its own dashboard.")
          : "");
      r.append(dot, nm);
      // Federation trust (per-host): trusted = full two-way postal; directed (default) = its mail is
      // HELD for your approval; isolated = dashboard only, no postal. The gate lives in the bus.
      const trust = document.createElement("select");
      trust.className = "sn-trust";
      trust.title = `What happens to postal mail from ${t.host}. trusted: delivered straight to `
        + "your sessions. directed: held for your approval. isolated: none, dashboard only.";
      // Each option carries its own plain gloss: the bare words are romp's vocabulary, not English, and a
      // dropdown whose meaning only appears on hover makes you uncover every option before you can choose.
      const TRUSTW: Record<string, string> = {
        trusted: "trusted (auto-accept)", directed: "directed (held for you)", isolated: "isolated (no mail)",
      };
      let pend = pendingTrust.get(t.host);
      if (pend && (t.trust || "directed") === pend) { pendingTrust.delete(t.host); pend = undefined; }
      for (const lvl of ["trusted", "directed", "isolated"]) {
        const o = document.createElement("option");
        o.value = lvl; o.textContent = TRUSTW[lvl];
        if ((pend || t.trust || "directed") === lvl) o.selected = true;
        trust.appendChild(o);
      }
      if (pend) { trust.disabled = true; trust.classList.add("sn-applying"); }
      trust.addEventListener("focus", () => { trustEngaged = true; });      // keyboard path
      trust.addEventListener("mousedown", () => { trustEngaged = true; });  // pointer path, before the popup opens
      trust.addEventListener("blur", releaseTrust);
      trust.addEventListener("change", () => {
        pendingTrust.set(t.host, trust.value);   // ack on the click; re-renders show the chosen level
        trust.disabled = true;
        trust.classList.add("sn-applying");
        fetch(kernelUrl("/tunnels/trust"), { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ host: t.host, trust: trust.value }) })
          .then((rp) => rp.json())
          .then((d) => { if (!(d && d.ok)) pendingTrust.delete(t.host); schedule(600); })
          .catch(() => { pendingTrust.delete(t.host); schedule(600); });
        releaseTrust();   // the choice is made — land any deferred snapshot now (pendingTrust keeps it painted)
      });
      r.appendChild(trust);
      if (pend) {
        const pn = document.createElement("span");
        pn.className = "sn-pend";
        pn.textContent = "applying…";
        r.appendChild(pn);
      }
      // A push romp is ALREADY doing needs no button — it would only invite a duplicate of the work in
      // flight. The row shows the live phase instead (below); the manual Push returns if it fails.
      const apx = !!(t.autoPush && (t.autoPush.phase === "pushing" || t.autoPush.phase === "waiting"
        || t.autoPush.phase === "pulling" || t.autoPush.phase === "asking"));
      // Every button is gated on the action being PROVABLY possible (the user 2026-07-28, whose laptop was
      // offered a push that could never run). Push needs an ssh route from here AND a straight fast-forward:
      // a checked-in host has no route, and a diverged — or unknown — remote build is refused by the
      // remote's own ancestor check every time (a commit this repo has never seen cannot be an ancestor of
      // its HEAD). Those states get the action that CAN work instead: Pull when the remote is strictly
      // ahead, Update when a checked-in peer is behind, else the drift word and its tooltip.
      if (t.status === "up" && t.fastForward && !apx && !t.checkinPeer) {
        const u = document.createElement("button");
        u.textContent = "Push";
        u.title = `Push this machine's committed romp to ${t.host} and restart its kernel, so it runs exactly this code. `
          + `Uncommitted local edits are not sent, so commit first.`;
        u.addEventListener("click", () => act("/tunnels/update", t.host, u, "Pushing…"));
        r.appendChild(u);
      }
      if (t.status === "up" && t.askPull && !apx) {
        const a = document.createElement("button");
        a.textContent = "Update";
        a.title = `${t.host} checked in over its own tunnel, so this machine cannot push to it. This asks its romp `
          + `to pull these commits from here and restart, over the link it already holds.`;
        a.addEventListener("click", () => act("/tunnels/askpull", t.host, a, "Asking…"));
        r.appendChild(a);
      }
      if (t.status === "up" && t.fastPull && !apx && !t.checkinPeer) {
        const pl = document.createElement("button");
        pl.textContent = "Pull";
        pl.title = `Pull ${t.host}'s newer commits into this machine's romp (fast-forward only; refuses if this tree `
          + `has uncommitted changes). This kernel keeps running the old build until you restart romp.`;
        pl.addEventListener("click", () => act("/tunnels/pull", t.host, pl, "Pulling…"));
        r.appendChild(pl);
      }
      if (t.status === "no-kernel") {
        const s = document.createElement("button");
        s.textContent = "Start";
        s.title = `No kernel is answering on ${t.host}. This pushes this machine's romp there and boots its kernel.`;
        s.addEventListener("click", () => act("/tunnels/start", t.host, s, "Starting…"));
        r.appendChild(s);
      }
      const d = document.createElement("button");
      d.textContent = "Detach";
      d.title = `Close the ssh tunnel to ${t.host}. It stays in this list as a previously-attached host, `
        + `keeping its trust level, so you can re-attach in one click.`;
      d.addEventListener("click", () => act("/tunnels/detach", t.host, d, "…"));
      r.appendChild(d);
      list.appendChild(r);
      // Live automatic-update phase under the row — the work still announces itself, it just does it here
      // instead of over your screen. A FAILURE stays put and red (fail loudly) rather than vanishing into a
      // silently-stale remote.
      if (t.autoPush) {
        const ap = document.createElement("div");
        ap.className = "sn-ap" + (t.autoPush.phase === "failed" ? " bad" : "");
        ap.textContent = (t.autoPush.phase === "failed" ? "auto-update failed — " : "auto-update: ")
          + (t.autoPush.detail || t.autoPush.phase);
        ap.title = t.autoPush.phase === "failed"
          ? "romp tried to update this host automatically and could not. The manual Push button is back; it will not retry by itself until either machine's commit moves."
          : "romp is updating this host in the background.";
        list.appendChild(ap);
      }
    }
    // PREVIOUSLY ATTACHED (the user 2026-07-22): hosts attached before, kept after detach so they are one
    // click away instead of buried in the ssh-config dropdown. Dimmed, each remembering the trust level
    // last set for it — re-attaching a box marked `trusted` will not silently drop back to directed.
    if (known.length) {
      const hd = document.createElement("div");
      hd.className = "sn-khead";
      hd.textContent = "Previously attached";
      hd.title = "Hosts you have attached before. They keep the trust level you last chose, so re-attaching "
        + "restores it. Forget removes a host from this list.";
      list.appendChild(hd);
      for (const k of known) {
        const r = document.createElement("div");
        r.className = "sn-row sn-known";
        const dot = document.createElement("span");
        dot.className = "sn-dot";
        dot.style.background = "transparent";
        dot.style.boxShadow = "inset 0 0 0 1.5px #5a5a5a";
        dot.title = "Not attached right now.";
        const nm = document.createElement("span");
        nm.className = "sn-name";
        nm.textContent = `${k.host} — not attached · ${k.trust || "directed"}`;
        nm.title = "Trust level remembered from the last time this host was attached; re-attaching restores it.";
        r.append(dot, nm);
        const ra = document.createElement("button");
        ra.textContent = "Re-attach";
        ra.title = `Open the ssh tunnel to ${k.host} again, restoring its remembered trust level.`;
        ra.addEventListener("click", () => act("/tunnels", k.host, ra, "Attaching…"));
        const fg = document.createElement("button");
        fg.textContent = "Forget";
        fg.title = `Remove ${k.host} from this list. It does not touch the host itself; attaching again will re-add it.`;
        fg.addEventListener("click", () => act("/tunnels/forget", k.host, fg, "…"));
        r.append(ra, fg);
        list.appendChild(r);
      }
    }
  }

  let diagPending = false;   // report the first /tunnels outcome of each open, not every 3s poll
  function refresh() {
    fetch(kernelUrl("/tunnels"), { cache: "no-store" }).then((r) => r.json()).then((d) => {
      const ts = (d && d.tunnels) || [];
      if (diagPending) { diagPending = false; post?.({ type: "clientDiag", surface: "strip", what: "netFetch", data: { ok: true, tunnels: ts.length } }); }
      if (!autoCb.disabled) autoCb.checked = !!(d && d.autoUpdate);   // mirror the kernel; never clobber a write in flight
      renderList(ts, (d && d.known) || []);
      // An automatic push in flight counts as busy: the button marches while romp works in the background,
      // and the poll runs fast so the phase reads live.
      const pushing = ts.some((t: any) => t.autoPush && (t.autoPush.phase === "pushing" || t.autoPush.phase === "waiting" || t.autoPush.phase === "pulling"));
      button.classList.toggle("busy", ts.some((t: any) => busy(t.status)) || pushing);
      schedule(ts.some((t: any) => busy(t.status)) || pushing ? 600 : 3000);   // fast while mid-attach/pushing, slow keep-alive after
    }).catch((err) => {
      // Fail loudly: an unreachable kernel renders as an error line, never a
      // silently empty box that reads as a dead button.
      if (diagPending) { diagPending = false; post?.({ type: "clientDiag", surface: "strip", what: "netFetch", data: { ok: false, err: String(err) } }); }
      list.textContent = "";
      const e = document.createElement("div");
      e.className = "sn-empty";
      e.textContent = `Couldn't reach the kernel (${(window as any).__rompKernelBase || "same origin"}) — retrying…`;
      list.appendChild(e);
      schedule(3000);
    });
  }

  attach.addEventListener("click", () => {
    if (!sel.value) return;
    act("/tunnels", sel.value, attach, "Attaching…");
    setTimeout(() => { attach.disabled = false; attach.textContent = "Attach"; }, 2000);
  });
  const setOpen = (open: boolean) => {
    pop.hidden = !open;
    button.classList.toggle("open", open);   // instant acknowledgment on the button itself
    if (!open) clearTimeout(timer);
    trustEngaged = false; deferredRender = null;   // a toggled popover starts (or leaves) unengaged — no stale latch
  };
  button.addEventListener("click", (e) => {
    e.stopPropagation();
    setOpen(pop.hidden);
    if (!pop.hidden) {
      // Instant content before any round-trip: the box never opens blank.
      if (!list.childElementCount) {
        const e2 = document.createElement("div");
        e2.className = "sn-empty";
        e2.textContent = "Checking remotes…";
        list.appendChild(e2);
      }
      // Anchor just above the strip however many rows it wrapped to. offsetWidth
      // math is layout-px; style px are layout px too, so this stays zoom-safe.
      const strip = document.getElementById("romp-strip");
      if (strip) pop.style.bottom = `${strip.offsetHeight + 6}px`;
      diagPending = true;
      loadHosts();
      refresh();
    }
    post?.({ type: "clientDiag", surface: "strip", what: "netToggle",
             data: { open: !pop.hidden, base: (window as any).__rompKernelBase || "" } });
  });
  document.addEventListener("click", (e) => {
    if (!pop.hidden && !pop.contains(e.target as Node) && e.target !== button) setOpen(false);
  });
}
