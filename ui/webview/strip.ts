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
  pct: number;          // used % of the limit
  elapsedPct: number | null;  // % of the window elapsed (pace comparison)
  title: string;        // hover detail
};

// The rail's window set: [key, span seconds, expanded label].
const WINS: Array<[string, number, string]> = [
  ["fiveHour", 5 * 3600, "5 hours"],
  ["sevenDay", 7 * 86400, "7 days"],
  ["fable", 7 * 86400, "Fable 5"],
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
  for (const [key, span, label] of WINS) {
    const seg = usage && usage[key];
    if (!seg || typeof seg.pct !== "number") continue;
    const rolled = seg.resetsAt && nowS > seg.resetsAt;   // the window reset since the last report
    const pct = rolled ? 0 : Math.max(0, Math.min(100, seg.pct));
    let elapsedPct: number | null = null;
    if (seg.resetsAt && span) {
      elapsedPct = Math.max(0, Math.min(100, Math.round(((nowS - (seg.resetsAt - span)) / span) * 100)));
    }
    out.push({
      key, label, pct, elapsedPct,
      title: `${label} — used ${pct}%`
        + (elapsedPct != null ? ` · ${elapsedPct}% through the window` : "")
        + (seg.resetsAt ? ` · resets in ${fmtReset(seg.resetsAt, nowS)}` : ""),
    });
  }
  return out;
}

export function initStrip(openSettings: () => void): void {
  if (!(window as any).__rompShowStrip) return;
  if (document.getElementById("romp-strip")) return;

  const strip = document.createElement("div");
  strip.id = "romp-strip";
  const usageWrap = document.createElement("div");
  usageWrap.id = "strip-usage";
  const spacer = document.createElement("div");
  spacer.className = "strip-spacer";
  const gear = document.createElement("button");
  gear.id = "strip-gear";
  gear.title = "romp settings";
  gear.textContent = "⛭";
  gear.addEventListener("click", (e) => { e.stopPropagation(); openSettings(); });
  strip.append(usageWrap, spacer, gear);
  document.body.appendChild(strip);

  function render(usage: any) {
    const nowS = Math.floor(Date.now() / 1000);
    usageWrap.textContent = "";
    for (const w of usageWindows(usage, nowS)) {
      const box = document.createElement("span");
      box.className = "ru-w";
      box.title = w.title;
      const name = document.createElement("span");
      name.className = "ru-name";
      name.textContent = w.label;
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
  }

  window.addEventListener("message", (ev: MessageEvent) => {
    const m = ev.data;
    if (!m) return;
    if (m.type === "usage") render(m.usage || null);                      // live: host-relayed timeline forwards
    else if (m.type === "stripShow") strip.style.display = m.show ? "" : "none";  // feed-over-chat rule
  });

  const base = (window as any).__rompKernelBase || "";
  fetch(`${base}/usage`, { cache: "no-store" })
    .then((r) => r.json())
    .then((u) => render(u))
    .catch(() => { /* the live pushes fill it in */ });
}
