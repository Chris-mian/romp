// The file viewer in the FEED pane (the user 2026-08-08). Clicking a file path in the chat used to post
// `openFile`, which the kernel served by running an opener on ITS OWN machine — the wrong screen when the
// dashboard is read from another device, and nothing at all on a kernel with no desktop, because the
// opener was macOS-only. The bytes have to reach the browser, so the click now routes to a viewer fed by
// the same /file route the image thumbnails use. Source pins (no jsdom for these modules) + executed
// replicas of the pure helpers.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const web = (f: string) => fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", f), "utf8");
const VIEW = web("file-view.ts");
const RENDER = web("render.ts");
const FEED = web("feed.ts");
const FEED_CSS = web("feed.css");

test("openPath routes by HOST: the feed viewer on the web, the editor in VS Code", () => {
  assert.match(RENDER, /function openPath\(path: string, sid\?: string \| null\): void/);
  // web dashboard inside the shell → relay up; the chat and the feed are different documents
  assert.match(RENDER, /const web = location\.protocol === "http:" \|\| location\.protocol === "https:";/);
  assert.match(RENDER, /if \(web && window\.parent !== window\) \{/);
  assert.match(RENDER, /window\.parent\.postMessage\(\{ romp: "viewFile", path, sid: sid \|\| activeId \|\| null \}, "\*"\);/);
  // everything else (VS Code, or /chat opened standalone with no shell) keeps the kernel-side opener
  assert.match(RENDER, /vscodeApi\.postMessage\(sid \? \{ type: "openFile", path, id: sid \} : \{ type: "openFile", path \}\);/);
});

test("every file-link surface in the chat goes through openPath — no direct openFile posts left", () => {
  for (const call of [/openPath\(path\);/, /openPath\(open, relative \? activeId : null\);/,
                      /openPath\(p, id \|\| null\);/]) assert.match(RENDER, call);
  // the ONLY openFile postMessage left in render.ts is openPath's own fallback branch
  assert.equal((RENDER.match(/type: "openFile"/g) || []).length, 2,
               "both remaining mentions are the two arms of openPath's fallback");
});

test("the shell relays chat → feed, and restores a pane it had to turn on", () => {
  const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "kernel", "kernel.py"), "utf8");
  assert.match(KERNEL, /if\(m\.romp==='viewFile'\)\{var vf=document\.getElementById\('f-feed'\);/);
  // a feed pane the user had toggled OFF is turned on for the viewer and put back on close — the viewer
  // must never silently rearrange the layout they chose
  assert.match(KERNEL, /window\.__rompFeedWasOff=true;/);
  assert.match(KERNEL, /if\(m\.romp==='viewFileClosed'&&window\.__rompFeedWasOff\)\{window\.__rompFeedWasOff=false;/);
  assert.match(KERNEL, /window\.__rompMobileTab&&window\.__rompMobileTab\('feed'\)/, "phone: one pane at a time");
  assert.match(KERNEL, /window\.__rompMobileTab=show;/, "…which means the mobile switcher has to be exposed");
});

test("the viewer is a singleton that fills the pane and always tells the shell when it closes", () => {
  assert.match(VIEW, /document\.getElementById\("romp-fileview"\)\?\.remove\(\);/, "re-opening replaces, never stacks");
  assert.match(VIEW, /window\.parent\.postMessage\(\{ romp: "viewFileClosed" \}, "\*"\);/);
  // Esc and ✕ are the same close path, so the shell's restore can't be skipped by one of them
  assert.match(VIEW, /close\.addEventListener\("click", closeFileView\);/);
  assert.match(VIEW, /if \(e\.key !== "Escape" \|\| !document\.getElementById\("romp-fileview"\)\) return;/);
  assert.match(FEED, /initFileView\(\);/, "the feed boots the listener");
  assert.match(FEED_CSS, /\.fileview \{ position: fixed; inset: 0;/);
});

test("it waits with the romp loader and fails with the kernel's own words, never a blank pane", () => {
  assert.match(VIEW, /romp-swirl-glyph\.svg/, "loading-state rule: the swirl goes up first");
  assert.match(VIEW, /fileview-dot/);
  // a 404/413/415 body IS the explanation (the 413 names the size and the cap) — show it, don't swallow it
  assert.match(VIEW, /if \(!r\.ok\) return r\.text\(\)\.then\(\(t\) => \{ throw new Error\(t \|\| \("HTTP " \+ r\.status\)\); \}\);/);
  assert.match(VIEW, /const why = el\("div", "fileview-err"\);/);
  // a reply that lands after the user closed the viewer paints nothing
  assert.match(VIEW, /if \(!document\.getElementById\("romp-fileview"\)\) return;/);
});

test("it reuses fileUrl, so a REMOTE session's file is relayed from the host that owns it", () => {
  assert.match(VIEW, /import \{ fileUrl \} from "\.\/preview";/);
  assert.match(VIEW, /fetch\(fileUrl\(path, sid\), \{ cache: "no-store" \}\)/);
});

// executed: the extension→language map must never GUESS. highlightAuto on a config file or a log picks a
// language at random and paints it as information the file does not contain.
test("langFor maps known extensions and returns null rather than guessing", () => {
  const LANG: Record<string, string> = {
    py: "python", pyi: "python", js: "javascript", jsx: "javascript", mjs: "javascript",
    cjs: "javascript", ts: "typescript", tsx: "typescript", json: "json", jsonc: "json",
    yaml: "yaml", yml: "yaml", sh: "bash", bash: "bash", zsh: "bash", bats: "bash",
    html: "xml", htm: "xml", xml: "xml", svg: "xml", vue: "xml", css: "css", scss: "css",
    md: "markdown", markdown: "markdown", diff: "diff", patch: "diff",
  };
  const langFor = (p: string): string | null => LANG[p.slice(p.lastIndexOf(".") + 1).toLowerCase()] || null;
  assert.equal(langFor("kernel/kernel.py"), "python");
  assert.equal(langFor("ui/webview/render.TS"), "typescript");   // case-insensitive
  assert.equal(langFor("notes.md"), "markdown");
  for (const p of ["server.log", "Makefile", "a.conf", "data.csv", "x.rs"]) {
    assert.equal(langFor(p), null, p + " has no registered grammar → plain, not a guess");
  }
  assert.doesNotMatch(VIEW, /hljs\.highlightAuto\(/, "auto-detection is what this map exists to avoid");
});

// ── formatting (the user 2026-08-09): the hljs palette, Raw ⇄ Rendered for markdown, and word wrap ──

// A. The viewer wraps every token in .hljs-* spans, but the feed page loads ONLY feed.css — with no
// palette there the highlighting rendered colorless. Both sheets must carry the SAME palette (one
// treatment, two sheets — the .romp-acted precedent), so this pins every rule in both and catches drift.
test("the hljs token palette lives in feed.css too, identical to the chat's", () => {
  const STYLES = web("styles.css");
  const rules = [
    /\.hljs \{ color: #d8c6a8; background: transparent; \}/,
    /\.hljs-keyword, \.hljs-built_in, \.hljs-literal, \.hljs-type \{ color: #c98a6a; \}/,
    /\.hljs-string, \.hljs-attr, \.hljs-regexp \{ color: #9fb878; \}/,
    /\.hljs-number \{ color: #d4a36a; \}/,
    /\.hljs-comment, \.hljs-quote \{ color: #6f6a5f; font-style: italic; \}/,
    /\.hljs-title, \.hljs-title\.function_, \.hljs-section \{ color: #e1c08d; \}/,
    /\.hljs-name, \.hljs-tag \{ color: #c98a6a; \}/,
    /\.hljs-params, \.hljs-variable, \.hljs-property \{ color: #d8c6a8; \}/,
    /\.hljs-meta \{ color: #9a8f7a; \}/,
    /\.hljs-attribute \{ color: #cdaf7e; \}/,
    /\.hljs-addition \{ color: #9fb878; \}/,
    /\.hljs-deletion \{ color: var\(--err\); \}/,
  ];
  for (const r of rules) {
    assert.match(FEED_CSS, r, "feed.css is missing a palette rule: " + r.source);
    assert.match(STYLES, r, "styles.css drifted from the shared palette: " + r.source);
  }
});

// B, executed: the persisted view-format prefs. RENDERED is the markdown default (the user's explicit
// call, 2026-08-09) and any malformed stored value reads as the defaults — a corrupt entry may cost the
// preference, never the viewer (feed-view-state's parseViewState contract).
test("format prefs: rendered is the markdown default, and a corrupt entry reads as the defaults", () => {
  type Fmt = { md: "rendered" | "raw"; wrap: boolean };
  const parseFmt = (raw: string | null): Fmt => {
    const def: Fmt = { md: "rendered", wrap: false };
    if (!raw) return def;
    try {
      const o = JSON.parse(raw) as { md?: unknown; wrap?: unknown };
      if (!o || typeof o !== "object") return def;
      return { md: o.md === "raw" ? "raw" : "rendered", wrap: o.wrap === true };
    } catch { return def; }
  };
  assert.deepEqual(parseFmt(null), { md: "rendered", wrap: false }, "first open: rendered, unwrapped");
  assert.deepEqual(parseFmt('{"md":"raw","wrap":true}'), { md: "raw", wrap: true }, "the round-trip");
  assert.deepEqual(parseFmt("not json"), { md: "rendered", wrap: false });
  assert.deepEqual(parseFmt('{"md":"purple","wrap":"yes"}'), { md: "rendered", wrap: false },
                   "foreign values fall to the defaults field by field");
  // replica ↔ source
  assert.match(VIEW, /const def: FileViewFmt = \{ md: "rendered", wrap: false \};/);
  assert.match(VIEW, /return \{ md: o\.md === "raw" \? "raw" : "rendered", wrap: o\.wrap === true \};/);
  // …and the prefs persist in localStorage, the feed-view-state call: per-BROWSER view state that must
  // survive a kernel restart without a round-trip to the thing that just restarted
  assert.match(VIEW, /const FMT_KEY = "romp:fileviewFmt";/);
  assert.match(VIEW, /localStorage\.getItem\(FMT_KEY\)/);
  assert.match(VIEW, /localStorage\.setItem\(FMT_KEY, JSON\.stringify\(f\)\)/);
});

// B: the toggle itself — markdown only, and the rendered path is sanitized. These are arbitrary bytes
// off a disk and marked emits raw HTML verbatim, so DOMPurify sits between it and .innerHTML with the
// same profile the chat's md() uses (render.ts).
test("Raw ⇄ Rendered exists for markdown ONLY, and nothing reaches innerHTML unsanitized", () => {
  assert.match(VIEW, /const isMd = langFor\(path\) === "markdown";/);
  // the two buttons are built inside the isMd gate — a .py file shows no Rendered/Raw toggle
  assert.match(VIEW, /if \(isMd\) \{\s*\n\s*for \(const mode of \["rendered", "raw"\] as const\)/);
  assert.match(VIEW, /const rendered = isMd && fmt\.md === "rendered";/, "non-md never renders as prose");
  assert.match(VIEW, /import DOMPurify from "dompurify";/);
  assert.match(VIEW, /box\.innerHTML = DOMPurify\.sanitize\(dirty, \{ USE_PROFILES: \{ html: true \}, ADD_DATA_URI_TAGS: \["img"\] \}\);/);
  // a README's links open a NEW tab rather than navigating the feed pane's iframe away
  assert.match(VIEW, /target = "_blank"/);
  assert.match(VIEW, /rel = "noopener"/);
  // fenced blocks highlight only a NAMED, registered language — same no-guessing rule as langFor
  assert.match(VIEW, /if \(!lang \|\| !hljs\.getLanguage\(lang\)\) return;/);
  // the prose typography exists on this sheet (the chat's .md block is the reference aesthetic)
  assert.match(FEED_CSS, /\.fileview-md \{/);
  assert.match(FEED_CSS, /\.fileview-md pre code \{/);
  // toggles acknowledge in the same synchronous tick: click → save → renderBody, which flips .on
  assert.match(VIEW, /b\.addEventListener\("click", \(\) => \{ fmt\.md = mode; saveFmt\(fmt\); renderBody\(\); \}\);/);
  assert.match(VIEW, /b\.classList\.toggle\("on", on\);/);
  assert.match(FEED_CSS, /\.fileview-btn\.on \{ color: var\(--accent\); border-color: var\(--accent\);/);
});

// C, executed: wrap mode's numbering. A flat gutter misaligns the moment one logical line wraps onto
// several visual lines, so wrap mode restructures — each logical line is a .fv-cl row numbered by a CSS
// counter — instead of shipping a drifting column. hljs spans can cross newlines, so each row must
// re-open what the previous row left unclosed (render.ts's wrapCodeLines balance walk).
test("wrap mode: per-line rows, spans rebalanced across newlines, no phantom trailing row", () => {
  const wrapNumberedHtml = (html: string): string => {
    const lines = html.split("\n");
    if (lines.length && lines[lines.length - 1] === "") lines.pop();
    let open: string[] = [];
    return lines.map((ln) => {
      const prefix = open.join("");
      const re = /<span[^>]*>|<\/span>/g; let m; const stack = open.slice();
      while ((m = re.exec(ln))) { if (m[0] === "</span>") stack.pop(); else stack.push(m[0]); }
      const suffix = "</span>".repeat(Math.max(0, stack.length));
      open = stack;
      return `<span class="fv-cl"><span class="fv-ct">${prefix}${ln}${suffix}</span></span>`;
    }).join("");
  };
  // a string token spanning a newline: closed at the end of row 1, re-opened at the start of row 2
  const out = wrapNumberedHtml('<span class="hljs-string">"a\nb"</span>\nplain');
  const rows = out.split('<span class="fv-cl">').filter(Boolean);
  assert.equal(rows.length, 3, "three logical lines, three rows");
  for (const row of rows) {
    const opens = (row.match(/<span[^>]*>/g) || []).length;
    const closes = (row.match(/<\/span>/g) || []).length;
    // +1: the .fv-cl open itself was consumed as the split delimiter
    assert.equal(opens + 1, closes, "a row must close every span it opens: " + row);
  }
  assert.match(rows[0], /<span class="hljs-string">"a<\/span>/);
  assert.match(rows[1], /^<span class="fv-ct"><span class="hljs-string">b"<\/span>/);
  assert.equal((wrapNumberedHtml("a\n").match(/fv-cl/g) || []).length, 1,
               "a trailing newline is not a phantom row — same rule as the gutter");
  // replica ↔ source
  assert.match(VIEW, /return `<span class="fv-cl"><span class="fv-ct">\$\{prefix\}\$\{ln\}\$\{suffix\}<\/span><\/span>`;/);
});

// C: the toggle and the CSS that carries the honest gutter answer
test("the Wrap toggle persists, hides with rendered prose, and its numbers still never copy", () => {
  assert.match(VIEW, /wrapBtn\.addEventListener\("click", \(\) => \{ fmt\.wrap = !fmt\.wrap; saveFmt\(fmt\); renderBody\(\); \}\);/);
  // wrap mode returns BEFORE the sibling gutter is built — a misaligned column cannot exist
  assert.match(VIEW, /if \(wrapLines\) \{[\s\S]*?return wrap;\s*\}\s*const gutter = el\("div", "fileview-gutter"\);/);
  // plain files wrap too: no grammar → the text is HTML-escaped before the line walk
  assert.match(VIEW, /code\.innerHTML = wrapNumberedHtml\(hl !== null \? hl : escapeHtml\(text\)\);/);
  assert.match(FEED_CSS, /\.fileview-pre\.fileview-wrap \{ white-space: pre-wrap/);
  assert.match(FEED_CSS, /\.fileview-wrap \.fv-cl::before \{[\s\S]*?counter-increment: fvln/);
  assert.match(FEED_CSS, /\.fileview-wrap \.fv-cl::before \{[\s\S]*?user-select: none/);
  // wrap governs the pre view only — rendered prose always wraps — so the button leaves with it
  assert.match(VIEW, /wrapBtn\.hidden = rendered;/);
  assert.match(VIEW, /wrapBtn\.classList\.toggle\("on", fmt\.wrap\);/, "pressed state flips synchronously");
});

// executed: the gutter is a SIBLING of the code, so selecting the code copies it without line numbers
test("the line gutter numbers every line and drops a trailing newline's phantom line", () => {
  const lines = (text: string): string[] => {
    const l = text.split("\n");
    if (l.length && l[l.length - 1] === "") l.pop();
    return l;
  };
  assert.deepEqual(lines("a\nb\nc\n").length, 3, "a trailing newline is not a fourth line");
  assert.deepEqual(lines("a\nb\nc").length, 3);
  assert.deepEqual(lines(""), []);
  assert.match(VIEW, /gutter\.textContent = lines\.map\(\(_, i\) => String\(i \+ 1\)\)\.join\("\\n"\);/);
  assert.match(VIEW, /wrap\.appendChild\(gutter\); wrap\.appendChild\(pre\);/, "sibling, not inside the pre");
  assert.match(FEED_CSS, /\.fileview-gutter \{[\s\S]*?user-select: none;/);
});
