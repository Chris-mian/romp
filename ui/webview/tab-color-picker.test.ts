// Right-click a tab → a color picker in the context menu: the romp identity palette as circles, the session's
// current one ringed; clicking one recolors the session (the user 2026-06-29). Source pins against render.ts —
// the menu builds DOM at right-click time, so a behavioral jsdom run isn't needed to lock the shape.
import { test } from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");

test("the palette is fetched once from the kernel /palette (the client doesn't own the palette list)", () => {
  assert.match(RENDER, /let paletteColors: string\[\] = \[\];/);
  assert.match(RENDER, /fetch\("\/palette"/);
  // the swatches are built from the fetched list, not a hard-coded array of hexes
  assert.match(RENDER, /for \(const bg of paletteColors\)/);
});

test("a palette switch (gear → Session colors) pushes the new swatch set to open tabs", () => {
  // the kernel re-broadcasts {type:"palette"} after setPalette; the menu offers the NEW set without a reload
  assert.match(RENDER, /m\.type === "palette" && Array\.isArray\(m\.colors\)\) paletteColors = m\.colors;/);
});

test("showTabMenu renders a swatch per palette color, ringing the session's current one", () => {
  // a swatch row, gated on the palette having loaded
  assert.match(RENDER, /if \(paletteColors\.length\) \{/);
  assert.match(RENDER, /for \(const bg of paletteColors\) \{/);
  // the current color gets the .sel ring (case-insensitive match against the session color)
  assert.match(RENDER, /"ctx-swatch" \+ \(bg\.toLowerCase\(\) === cur \? " sel" : ""\)/);
  assert.match(RENDER, /sw\.style\.background = bg;/);
  // clicking a swatch dismisses the menu and recolors
  assert.match(RENDER, /dismissTabMenu\(\); setSessionColor\(id, bg\);/);
});

test("setSessionColor optimistically repaints and posts setSessionColor to the kernel", () => {
  assert.match(RENDER, /function setSessionColor\(id: string, bg: string\)/);
  // optimistic: update the session + placeholder color, repaint now
  assert.match(RENDER, /const color: Color = \{ bg, fg: "#ffffff" \};/);
  assert.match(RENDER, /if \(s\) s\.color = color;/);
  assert.match(RENDER, /if \(meta\) meta\.color = color;/);
  assert.match(RENDER, /renderTabs\(\);/);
  // then tell the kernel (it persists + re-broadcasts)
  assert.match(RENDER, /postMessage\(\{ type: "setSessionColor", id, bg \}\)/);
});
