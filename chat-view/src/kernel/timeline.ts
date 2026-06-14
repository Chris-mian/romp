// The /timeline page: serves romp's timeline (obsidian/romp-timeline-view.js →
// TimelinePanel) to the browser, mirroring the VS Code trackchanges wrapper —
// the pure-Node data builder (obsidian/romp-timeline-data.js) runs HERE in the
// kernel; the DOM/SVG renderer runs in the page, wrapped with the same tiny
// Obsidian DOM-helper shim and the same host bridges (openExternal/writeOrder/
// compact/sendCommand), carried over the kernel WebSocket instead of
// vscode.postMessage. Both files are read live from the romp checkout — no
// copies to drift.
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { createRequire } from "module";

// esbuild must not bundle the runtime-resolved obsidian modules — we need the REAL runtime require.
// module.createRequire (resolving from this bundle's path) gives exactly that AND dodges esbuild's
// direct-eval warning. NOTE: do NOT "silence" it with (0, eval)("require") — indirect eval runs in
// GLOBAL scope, where `require` is undefined in the CJS bundle, so the kernel crashes on load with
// "require is not defined" (the user 2026-06-13 regression). createRequire is the correct fix.
const dynRequire: NodeRequire = createRequire(__filename);

// Locate romp's obsidian/ view-module dir: $ROMP_DIR (bin/romp-serve exports
// it) → the checkout this kernel was built in (dist/kernel.js → chat-view →
// repo) → a romp/bin on PATH → the conventional checkout location.
function findRompDir(): string | null {
  const candidates: string[] = [];
  if (process.env.ROMP_DIR) candidates.push(process.env.ROMP_DIR);
  candidates.push(path.join(__dirname, "..", ".."));
  for (const p of (process.env.PATH || "").split(path.delimiter)) {
    if (/[\\/]romp[\\/]bin$/.test(p)) candidates.push(path.dirname(p));
  }
  candidates.push(path.join(os.homedir(), "GitRepos", "romp"));
  for (const c of candidates) {
    try { if (fs.existsSync(path.join(c, "obsidian", "romp-timeline-data.js"))) return c; } catch { /* ignore */ }
  }
  return null;
}

let _loaded: { build: () => Promise<any>; viewJs: string } | null | undefined;
let _loadedKey = "";   // mtime signature of the two obsidian sources → reload when either is edited
// Re-read on MTIME CHANGE rather than caching forever: an edit to the obsidian view/data sources then
// goes live without a kernel restart (a browser reload re-fetches the page → fresh viewJs; the data
// build re-requires per poll) — this is what retires the cached-stale-view-JS trap (2026-06-12), now
// that loadTimeline no longer freezes the first read for the life of the process. Cost: two stats per
// call, and a re-require only when the mtime actually changes.
export function loadTimeline(): { build: () => Promise<any>; viewJs: string } | null {
  const dir = findRompDir();
  if (!dir) { _loaded = null; return null; }
  const dataPath = path.join(dir, "obsidian", "romp-timeline-data.js");
  const viewPath = path.join(dir, "obsidian", "romp-timeline-view.js");
  let key: string;
  try { key = fs.statSync(dataPath).mtimeMs + ":" + fs.statSync(viewPath).mtimeMs; }
  catch { _loaded = null; _loadedKey = ""; return null; }   // a source went missing
  if (_loaded !== undefined && key === _loadedKey) return _loaded;   // unchanged → cached
  try {
    try { delete (dynRequire as any).cache[dataPath]; } catch { /* not cached yet */ }   // bust the require cache so the re-require is fresh
    const mod = dynRequire(dataPath);
    const viewJs = fs.readFileSync(viewPath, "utf8");
    _loaded = typeof mod.buildTimelineData === "function" && viewJs.length > 0
      ? { build: mod.buildTimelineData, viewJs }
      : null;
  } catch { _loaded = null; }
  _loadedKey = key;
  return _loaded;
}

// The romp-tl-* styles, verbatim from the trackchanges wrapper, themed with
// the same Dark+ default vars the other kernel pages use.
const TIMELINE_CSS = `
.romp-tl-top { display: flex; align-items: center; gap: 12px; padding: 2px 0 8px; flex: 0 0 auto; }
.romp-tl-winlabel { color: var(--text-muted); font-size: 12px; min-width: 92px; }
.romp-tl-src { color: var(--text-faint); font-size: 11px; margin-left: auto; }
.romp-tl-slider { flex: 1; max-width: 420px; -webkit-appearance: none; appearance: none; height: 6px;
  border-radius: 3px; background: #2a2f37; outline: none; }
.romp-tl-slider::-webkit-slider-thumb { -webkit-appearance: none; appearance: none; width: 14px; height: 14px;
  border-radius: 50%; background: #e6edf3; cursor: pointer; }
.romp-tl-wrap { overflow-x: auto; }
.romp-tl-wrap svg { display: block; }
.romp-tl-tip { position: fixed; pointer-events: none; z-index: 1000; max-width: 320px;
  background: #1c2430; border: 1px solid #ffffff1f; border-radius: 8px; padding: 7px 9px;
  font-size: 12px; color: #e6edf3; box-shadow: 0 8px 24px #00000066; opacity: 0;
  transform: translateY(4px); transition: opacity .1s, transform .1s; }
.romp-tl-tip.show { opacity: 1; transform: translateY(0); }
.romp-tl-tip .r { display: flex; align-items: center; gap: 6px; }
.romp-tl-tip .chip { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
.romp-tl-tip .who { font-weight: 650; } .romp-tl-tip .ar { color: #6e7681; }
.romp-tl-tip .t { color: #8b949e; margin-left: 2px; font-variant-numeric: tabular-nums; }
.romp-tl-tip .k { color: #6e7681; font-size: 10px; text-transform: uppercase; letter-spacing: .04em; }
.romp-tl-tip .b { margin-top: 4px; color: #cdd9e5; }`;

export function timelineUnavailableHtml(): string {
  return `<!DOCTYPE html><html><body style="font-family:-apple-system,sans-serif;color:#999;background:#1e1e1e;padding:12px">
romp timeline needs the romp checkout (its obsidian/ modules) — run the kernel via bin/romp-serve, or set ROMP_DIR.</body></html>`;
}

// The page. Bridges go over this page's own WebSocket (app=timeline); a ?wid=
// in the page URL rides along so the kernel can route deep-link focus to the
// chat pane of the SAME browser window (the combined page sets it).
export function timelineHtml(viewJs: string): string {
  return `<!DOCTYPE html><html><head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>romp timeline</title>
<style>
  :root { --text-muted: #9aa0a6; --text-faint: #6e7681; }
  html, body { background: #1e1e1e; }
  body { margin: 0; padding: 8px 10px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif; color: #cccccc; }
  #host { width: 100%; }
  ${TIMELINE_CSS}
</style></head><body>
<div id="host"></div>
<script>
// Shim the 3 Obsidian DOM helpers TimelinePanel uses (createDiv/createSpan/createEl).
(function(){ var P = HTMLElement.prototype;
  if(!P.createEl) P.createEl = function(tag, o){ var e = document.createElement(tag); if(o&&o.cls) e.className = o.cls; if(o&&o.text) e.textContent = o.text; this.appendChild(e); return e; };
  if(!P.createDiv) P.createDiv = function(o){ return this.createEl('div', o); };
  if(!P.createSpan) P.createSpan = function(o){ return this.createEl('span', o); };
})();
(function () {
  var wid = new URLSearchParams(location.search).get("wid") || "";
  var queue = [];
  var ws = null;
  function send(m) {
    var s = JSON.stringify(m);
    if (ws && ws.readyState === 1) ws.send(s); else queue.push(s);
  }
  function connect() {
    var proto = location.protocol === "https:" ? "wss://" : "ws://";
    ws = new WebSocket(proto + location.host + "/ws?app=timeline" + (wid ? "&wid=" + encodeURIComponent(wid) : ""));
    ws.onopen = function () { for (var i = 0; i < queue.length; i++) ws.send(queue[i]); queue = []; };
    ws.onmessage = function (ev) {
      var m; try { m = JSON.parse(ev.data); } catch (e) { return; }
      if (m.type === "data") panel.update(m.data);
      else if (m.type === "activeChat" && panel.setActiveChat) panel.setActiveChat(m.activeChat);
      // Direct hover push (server.ts pushHover) — the fast path that skips the timeline-hover.json
      // write→fs.watch→rebuild, so modal/chat hover lights the timeline as instantly as the chat glow.
      else if (m.type === "hover" && panel.setHover) panel.setHover(m);
    };
    ws.onclose = function () { setTimeout(function () { location.reload(); }, 1500); };
  }
  // Bridges: the view module can't shell out from a browser. A vscode:// deep
  // link becomes a kernel deepLink (focuses the chat pane of this window).
  window.__rompTimelineOpenExternal = function (url) {
    try {
      var u = new URL(url);
      if (u.protocol === "vscode:") {
        var q = u.searchParams;
        send({ type: "deepLink", session: q.get("session"), anchor: q.get("anchor") || undefined,
               anchorT: Number(q.get("anchorT")) || undefined, anchorKind: q.get("anchorKind") || undefined,
               compose: q.get("compose") === "1" });
        if (window.parent !== window) window.parent.postMessage({ romp: "reveal", pane: "chat" }, "*");
        return;
      }
    } catch (e) { /* fall through */ }
    window.open(url, "_blank");
  };
  window.__rompTimelineWriteOrder = function (order) { send({ type: "writeOrder", order: order }); };
  window.__rompTimelineCompact = function (name) { send({ type: "compact", name: name }); };
  window.__rompTimelineSendCommand = function (name, cmd) { send({ type: "sendCommand", name: name, cmd: cmd }); };
  window.__rompConnectTimeline = function (p) { panel = p; connect(); send({ type: "ready" }); };
  var panel = null;
})();
var module = { exports: {} };
(function(module, exports){
${viewJs}
})(module, module.exports);
var TimelinePanel = module.exports.TimelinePanel;
window.__rompConnectTimeline(new TimelinePanel(document.getElementById('host')));
</script></body></html>`;
}
