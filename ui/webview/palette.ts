// The command palette overlay (Cmd/Ctrl+P) — Obsidian's shape: a card centered near the top,
// a type-ahead input, fuzzy-filtered rows with highlighted matches, arrows + Enter, Esc or a
// backdrop click to close. It lives in the SHELL document, so like the network panel it
// composites over the real panes: one centered card, the standard 0.55 dim, and the dashboard
// unchanged behind it (the one modal treatment, the user 2026-08-08).
import { commandList, PaletteCommand } from "./commands";
import { fuzzyMatch, FuzzyHit, FuzzyRange } from "./fuzzy";

// The modal vocabulary the shell's panels share (#rnet-panel / #rerr-panel): #252526 card,
// 1px #3a3a3a border, radius 10, 13px system-ui body, 11px chips. Injected as a <style> tag by
// ensure() so the palette ships as ONE dist bundle with no separate <link> to plumb through
// _landing. z-index 300: over every shell panel (net 200, log 210, restart report 220, usage 290).
const CSS =
  "#rpal-back{position:fixed;inset:0;z-index:300;display:flex;align-items:flex-start;justify-content:center;" +
  "padding:14vh 16px 16px;background:rgba(0,0,0,0.55);box-sizing:border-box}" +
  "#rpal-back[hidden]{display:none}" +
  "#rpal{width:min(560px,94%);max-height:60vh;display:flex;flex-direction:column;background:#252526;" +
  "border:1px solid #3a3a3a;border-radius:10px;box-shadow:0 12px 36px #000000aa;padding:8px;" +
  "color:#ccc;font:13px/1.6 system-ui,-apple-system,'Segoe UI',sans-serif;box-sizing:border-box}" +
  "#rpal-in{flex:0 0 auto;background:#1b1b1c;border:1px solid #3a3a3a;border-radius:6px;color:#e8eaed;" +
  "font:inherit;padding:7px 10px;outline:none;box-sizing:border-box;width:100%}" +
  "#rpal-in:focus{border-color:var(--accent,#9cd2ff)}" +
  "#rpal-list{flex:1 1 auto;overflow-y:auto;margin-top:6px}" +
  ".rpal-row{display:flex;align-items:center;gap:10px;padding:5px 10px;border-radius:6px;cursor:pointer}" +
  ".rpal-row.active{background:rgba(156,210,255,0.12)}" +   // accent-blue focus cue, not a status color
  ".rpal-title{flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}" +
  ".rpal-title b{color:var(--accent,#9cd2ff);font-weight:600}" +
  ".rpal-kbd{flex:0 0 auto;color:#9aa0a6;font-size:11px;border:1px solid #3a3a3a;border-radius:4px;padding:0 5px}" +
  ".rpal-empty{padding:8px 10px;color:#9aa0a6}";

export type Palette = { open(): void; close(): void; toggle(): void; isOpen(): boolean };

export function initPalette(opts?: { onClose?: () => void }, doc: Document = document): Palette {
  let back: HTMLElement | null = null;
  let input: HTMLInputElement;
  let list: HTMLElement;
  let rows: { cmd: PaletteCommand; el: HTMLElement }[] = [];
  let active = 0;

  // Built once, lazily; the palette is not subject to the dashboard's re-render pushes (the
  // shell document never rebuilds), so rows stay click-safe without delegation gymnastics.
  function ensure(): void {
    if (back) return;
    const style = doc.createElement("style");
    style.textContent = CSS;
    doc.head.appendChild(style);
    back = doc.createElement("div");
    back.id = "rpal-back";
    back.hidden = true;
    const panel = doc.createElement("div");
    panel.id = "rpal";
    input = doc.createElement("input");
    input.id = "rpal-in";
    input.placeholder = "Type a command…";
    input.spellcheck = false;
    list = doc.createElement("div");
    list.id = "rpal-list";
    panel.appendChild(input);
    panel.appendChild(list);
    back.appendChild(panel);
    doc.body.appendChild(back);
    input.addEventListener("input", () => render(input.value));
    back.addEventListener("keydown", onKey);
    back.addEventListener("click", (e) => { if (e.target === back) close(); });   // the dim, not the card
    list.addEventListener("mouseover", (e) => {
      const row = (e.target as HTMLElement).closest(".rpal-row");
      const i = rows.findIndex((r) => r.el === row);
      if (i >= 0) setActive(i);   // hover and keyboard share one active row, like the picker
    });
    list.addEventListener("click", (e) => {
      const row = (e.target as HTMLElement).closest(".rpal-row");
      const hit = rows.find((r) => r.el === row);
      if (hit) run(hit.cmd);
    });
  }

  function highlight(title: string, ranges: FuzzyRange[]): DocumentFragment {
    const frag = doc.createDocumentFragment();
    let at = 0;
    for (const [s, e] of ranges) {
      if (s > at) frag.appendChild(doc.createTextNode(title.slice(at, s)));
      const b = doc.createElement("b");
      b.textContent = title.slice(s, e);
      frag.appendChild(b);
      at = e;
    }
    if (at < title.length) frag.appendChild(doc.createTextNode(title.slice(at)));
    return frag;
  }

  function render(query: string): void {
    const hits = commandList()
      .map((cmd) => ({ cmd, hit: fuzzyMatch(query, cmd.title) }))
      .filter((x): x is { cmd: PaletteCommand; hit: FuzzyHit } => !!x.hit);
    hits.sort((a, b) => b.hit.score - a.hit.score);   // stable sort: ties keep registration order
    list.textContent = "";
    rows = [];
    for (const { cmd, hit } of hits) {
      const row = doc.createElement("div");
      row.className = "rpal-row";
      const title = doc.createElement("span");
      title.className = "rpal-title";
      title.appendChild(highlight(cmd.title, hit.ranges));
      row.appendChild(title);
      if (cmd.kbd) {
        const k = doc.createElement("span");
        k.className = "rpal-kbd";
        k.textContent = cmd.kbd;
        row.appendChild(k);
      }
      list.appendChild(row);
      rows.push({ cmd, el: row });
    }
    if (!rows.length) {
      const empty = doc.createElement("div");
      empty.className = "rpal-empty";
      empty.textContent = "No matching commands";
      list.appendChild(empty);
    }
    setActive(0);
  }

  function setActive(i: number): void {
    active = i;
    rows.forEach((r, j) => r.el.classList.toggle("active", j === i));
    const el = rows[i]?.el;
    if (el && el.scrollIntoView) el.scrollIntoView({ block: "nearest" });
  }

  function onKey(e: KeyboardEvent): void {
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(); }
    else if (e.key === "ArrowDown") { e.preventDefault(); if (rows.length) setActive((active + 1) % rows.length); }
    else if (e.key === "ArrowUp") { e.preventDefault(); if (rows.length) setActive((active - 1 + rows.length) % rows.length); }
    else if (e.key === "Enter") { e.preventDefault(); const r = rows[active]; if (r) run(r.cmd); }
  }

  function run(cmd: PaletteCommand): void {
    close();   // close FIRST: a command that opens its own modal must not land under the palette
    cmd.run();
  }

  function open(): void {
    ensure();
    back!.hidden = false;
    input.value = "";
    render("");
    input.focus();
  }
  function close(): void {
    if (!back || back.hidden) return;
    back.hidden = true;
    if (opts && opts.onClose) opts.onClose();
  }
  function isOpen(): boolean { return !!back && !back.hidden; }
  function toggle(): void { if (isOpen()) close(); else open(); }

  return { open, close, toggle, isOpen };
}
