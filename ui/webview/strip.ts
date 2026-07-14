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

export type UsageWindow = {
  key: string;
  label: string;        // the rail's expanded label
  short: string;        // the compressed tag a narrow strip swaps in ("5h" / "7d" / "F5")
  pct: number;          // used % of the limit
  elapsedPct: number | null;  // % of the window elapsed (pace comparison)
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
    const rolled = seg.resetsAt && nowS > seg.resetsAt;   // the window reset since the last report
    const pct = rolled ? 0 : Math.max(0, Math.min(100, seg.pct));
    let elapsedPct: number | null = null;
    if (seg.resetsAt && span) {
      elapsedPct = Math.max(0, Math.min(100, Math.round(((nowS - (seg.resetsAt - span)) / span) * 100)));
    }
    out.push({
      key, label, short, pct, elapsedPct,
      title: `${label} — used ${pct}%`
        + (elapsedPct != null ? ` · ${elapsedPct}% through the window` : "")
        + (seg.resetsAt ? ` · resets in ${fmtReset(seg.resetsAt, nowS)}` : ""),
    });
  }
  return out;
}

// Which panes get a quick-open label when hidden (the user 2026-07-13: "chat
// outline feed — only the ones that aren't currently shown"). Timeline lives
// in VS Code's own panel, so it isn't listed.
export const STRIP_PANES: Array<{ key: string; label: string }> = [
  { key: "chat", label: "Chat" },
  { key: "fleet", label: "Outline" },
  { key: "feed", label: "Feed" },
];

export function initStrip(openSettings: () => void, post?: (m: Record<string, unknown>) => void): void {
  if (!(window as any).__rompShowStrip) return;
  if (document.getElementById("romp-strip")) return;
  const base = (window as any).__rompKernelBase || "";

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
    fetch(`${base}/restart`, { method: "POST" }).catch(() => { /* the reconnect machinery reports */ });
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
  initNetPopover(net, base, post);

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
    for (const w of usageWindows(usage, nowS)) {
      const box = document.createElement("span");
      box.className = "ru-w";
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
      bars.appendChild(mkTrack(w.pct, usageColor(w.pct)));
      if (w.elapsedPct != null) bars.appendChild(mkTrack(w.elapsedPct, "#6b7a8c"));
      const pct = document.createElement("span");
      pct.className = "ru-pct";
      pct.textContent = `${w.pct}%`;
      box.append(name, bars, pct);
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

  fetch(`${base}/usage`, { cache: "no-store" })
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
// client-diag.jsonl — the user reported the button "doing nothing" in VS Code
// (2026-07-14) while every repro outside VS Code works, so the next report
// comes with recorded evidence instead of guesses.
function initNetPopover(button: HTMLButtonElement, base: string, post?: (m: Record<string, unknown>) => void) {
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
  pop.append(row, list);
  document.body.appendChild(pop);

  const LBL: Record<string, string> = {
    up: "connected", authorizing: "authorizing…", connecting: "connecting…", starting: "connecting…",
    "no-kernel": "kernel not answering", down: "disconnected", error: "error",
  };
  let timer: ReturnType<typeof setTimeout> | undefined;
  const schedule = (ms: number) => { clearTimeout(timer); if (!pop.hidden) timer = setTimeout(refresh, ms); };
  const busy = (s: string) => s !== "up" && s !== "down" && s !== "error" && s !== "no-kernel";

  function loadHosts() {
    fetch(`${base}/ssh-hosts`, { cache: "no-store" }).then((r) => r.json()).then((d) => {
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
    fetch(`${base}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ host }) })
      .then(() => schedule(600))
      .catch(() => { b.disabled = false; b.textContent = prev; });
  }

  function renderList(ts: any[]) {
    list.textContent = "";
    button.classList.toggle("on", ts.some((t) => t.status === "up"));
    if (!ts.length) {
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
        : t.status === "down" ? "#8a8a8a" : "transparent";
      if (dot.style.background === "transparent") dot.style.boxShadow = "inset 0 0 0 1.5px var(--accent, #9cd2ff)";
      const nm = document.createElement("span");
      nm.className = "sn-name";
      nm.textContent = `${t.host} — ${LBL[t.status] || t.status}`
        + (t.outOfDate ? " · different build" : "");
      r.append(dot, nm);
      if (t.status === "up" && t.outOfDate) {
        const u = document.createElement("button");
        u.textContent = "Push";
        u.title = `Push this machine's romp to ${t.host} + restart it`;
        u.addEventListener("click", () => act("/tunnels/update", t.host, u, "Pushing…"));
        r.appendChild(u);
      }
      if (t.status === "no-kernel") {
        const s = document.createElement("button");
        s.textContent = "Start";
        s.title = `Update ${t.host} to this machine's romp, then start its kernel`;
        s.addEventListener("click", () => act("/tunnels/start", t.host, s, "Starting…"));
        r.appendChild(s);
      }
      const d = document.createElement("button");
      d.textContent = "Detach";
      d.addEventListener("click", () => act("/tunnels/detach", t.host, d, "…"));
      r.appendChild(d);
      list.appendChild(r);
    }
  }

  let diagPending = false;   // report the first /tunnels outcome of each open, not every 3s poll
  function refresh() {
    fetch(`${base}/tunnels`, { cache: "no-store" }).then((r) => r.json()).then((d) => {
      const ts = (d && d.tunnels) || [];
      if (diagPending) { diagPending = false; post?.({ type: "clientDiag", surface: "strip", what: "netFetch", data: { ok: true, tunnels: ts.length } }); }
      renderList(ts);
      schedule(ts.some((t: any) => busy(t.status)) ? 600 : 3000);   // fast while mid-attach, slow keep-alive after
    }).catch((err) => {
      // Fail loudly: an unreachable kernel renders as an error line, never a
      // silently empty box that reads as a dead button.
      if (diagPending) { diagPending = false; post?.({ type: "clientDiag", surface: "strip", what: "netFetch", data: { ok: false, err: String(err) } }); }
      list.textContent = "";
      const e = document.createElement("div");
      e.className = "sn-empty";
      e.textContent = `Couldn't reach the kernel (${base || "same origin"}) — retrying…`;
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
    post?.({ type: "clientDiag", surface: "strip", what: "netToggle", data: { open: !pop.hidden, base } });
  });
  document.addEventListener("click", (e) => {
    if (!pop.hidden && !pop.contains(e.target as Node) && e.target !== button) setOpen(false);
  });
}
