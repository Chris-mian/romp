#!/usr/bin/env node
// Render the docs' Mermaid diagrams to standalone SVGs.
//
// WHY pre-render instead of letting the browser do it. Material for MkDocs
// renders Mermaid at page load and injects its own theme CSS into the SVG,
// keyed on --md-mermaid-* variables it defines under `:root>*`. Those variables
// then win by INHERITANCE over anything the page sets on :root, so the diagrams
// came out with near-white labels on the pale node fills we ask for and could
// not be read. Fighting that from the page's stylesheet proved unreliable.
//
// Rendering here instead makes the diagram a finished artifact: its styling is
// sealed inside the SVG, nothing at page load can recolour it, the page no
// longer fetches Mermaid from a CDN, and the output can be eyeballed before it
// ships. Sources stay editable as .mmd files beside the output: edit one,
// re-run this, commit both.
//
// Usage:  node scripts/render-diagrams.mjs [--check]
//   --check  render and compare, exit non-zero if any SVG is out of date
import { readFileSync, writeFileSync, mkdirSync, existsSync, readdirSync } from "fs";
import { dirname, resolve } from "path";
import { fileURLToPath } from "url";
import { chromium } from "playwright";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const OUT = resolve(ROOT, "docs/assets/diagrams");
const CHECK = process.argv.includes("--check");

// Sources live beside their output as .mmd files. Edit one, re-run this, commit
// both. The .md pages reference only the rendered .svg.
const SRC = resolve(ROOT, "docs/assets/diagrams");

// The palette the diagrams are authored against: light node fills, so labels
// must be dark. Set here rather than per-diagram so all six stay consistent.
const THEME = {
  primaryTextColor: "#111827",
  nodeTextColor: "#111827",
  textColor: "#111827",
  lineColor: "#9aa4b2",         // arrows, on the page's dark background
  edgeLabelBackground: "#e5e7eb",
  fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif",
  fontSize: "15px",
};

// Edge labels were the smallest type on the page; give them the node size and a
// light chip so they read against the dark background.
const EXTRA_CSS = `
  .edgeLabel, .edgeLabel p, .edgeLabel span { font-size: 14px !important; line-height: 1.35 !important; }
  .edgeLabel, .edgeLabel p { background-color: #e5e7eb !important; color: #111827 !important; }
  .nodeLabel, .nodeLabel p, .nodeLabel code { color: #111827 !important; }
  .nodeLabel code, .edgeLabel code { background: rgba(0,0,0,.07); padding: 0 .25em; border-radius: 3px; }
  .cluster rect { fill: rgba(255,255,255,.04) !important; stroke: #9aa4b2 !important; }
  .cluster .nodeLabel { color: #cdd5dd !important; }
`;

mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage();
// Mermaid is loaded from a CDN here, at BUILD time — the published page ships
// only the finished SVG and fetches nothing.
await page.setContent(`<!doctype html><meta charset="utf-8"><body><div id="x"></div></body>`);
await page.addScriptTag({ url: "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js" });

let stale = 0, wrote = 0;
const sources = readdirSync(SRC).filter((f) => f.endsWith(".mmd")).sort();
for (const mmd of sources) {
    const graph = readFileSync(resolve(SRC, mmd), "utf8");
    const name = mmd.replace(/\.mmd$/, ".svg");
    const svg = await page.evaluate(
      async ([graph, theme, css]) => {
        window.mermaid.initialize({
          startOnLoad: false, theme: "base", themeVariables: theme, themeCSS: css,
          flowchart: { htmlLabels: true, useMaxWidth: true },
        });
        const { svg } = await window.mermaid.render("d" + Math.floor(Math.random() * 1e9), graph);
        return svg;
      },
      [graph, THEME, EXTRA_CSS]
    );
    // Mermaid emits width="100%" with no height (useMaxWidth). That is fine for
    // an inline SVG, but an <img> has no intrinsic size to work from and lays
    // out at 0x0. Give it the viewBox's dimensions so it has an aspect ratio;
    // the viewBox stays, so CSS width still scales it responsively.
    const vb = /viewBox="0 0 ([\d.]+) ([\d.]+)"/.exec(svg);
    let sized = vb
      ? svg.replace(/^<svg([^>]*)width="100%"/, `<svg$1width="${Math.round(+vb[1])}" height="${Math.round(+vb[2])}"`)
           .replace(/style="max-width:[^"]*"/, "")
      : svg;
    // An <img> parses the file as XML, which is stricter than the HTML parser
    // Mermaid writes for. Void tags left open ("<br>") abort the whole parse and
    // the image lays out at 0x0 with no visible error. Close them, and namespace
    // the foreignObject content, so the file stands alone.
    sized = sized
      .replace(/<br\s*>/g, "<br/>")
      .replace(/<(hr|img)\b([^>]*[^/])>/g, "<$1$2/>")
      .replace(/<foreignObject/g, '<foreignObject xmlns:xhtml="http://www.w3.org/1999/xhtml"')
      .replace(/<div(?![^>]*xmlns)/g, '<div xmlns="http://www.w3.org/1999/xhtml"');
    const dest = resolve(OUT, name);
    const prev = existsSync(dest) ? readFileSync(dest, "utf8") : "";
    // Mermaid mints a random id per render, so compare with ids normalised out.
    const norm = (s) => s.replace(/\bd\d{6,}\b/g, "ID").replace(/my-svg|graph-div/g, "ID");
    if (norm(prev) === norm(sized)) { console.log("unchanged", name); continue; }
    if (CHECK) { console.log("STALE", name); stale++; continue; }
    writeFileSync(dest, sized);
    console.log("wrote", name);
  wrote++;
}
await browser.close();
if (CHECK && stale) { console.error(`\n${stale} diagram(s) out of date — run: node scripts/render-diagrams.mjs`); process.exit(1); }
console.log(`\n${wrote} written into docs/assets/diagrams/`);
