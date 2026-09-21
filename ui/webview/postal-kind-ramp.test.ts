// T371 (the user 2026-09-12, who found coordinate and delegate alike: T337's three steps on ONE accent-hue line read as
// three tints of one blue): each theme's three kind tokens are three HUES sampled from the default progress colormap
// (aurora, bin/romp_colormap.py), the two the user confused farthest apart on the ramp. The pin reads the ramp FROM the
// colormap file, never a copied literal: the dark tokens ARE stops of it (coordinate the first, delegate the last, question
// a middle one), the light tokens hold the same three hues deepened for the cream page, and in both themes every pair
// of tokens sits a real hue distance apart and every token keeps its distance from the prose ink. The mapping is written
// once, in the :root comment beside the tokens, and this test pins that sentence; a swap of the mapping moves both.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
const COLORMAP = fs.readFileSync(path.resolve(process.cwd(), "..", "bin", "romp_colormap.py"), "utf8");
function block(opener: string): string {
  const at = CSS.indexOf(opener);
  assert.ok(at >= 0, opener + " present");
  return CSS.slice(at, CSS.indexOf("\n}", at)).replace(/\/\*[\s\S]*?\*\//g, "");   // comment-blind, like theme-parity
}
function token(blockText: string, name: string): string {
  // a bare hex, or the hex fallback of a var() (the dark --fg is var(--vscode-foreground, #cccccc))
  const m = new RegExp(name + ":\\s*(?:var\\([^,]+,\\s*)?(#[0-9a-f]{6})\\)?;", "i").exec(blockText);
  assert.ok(m, name + " declared as a hex, bare or as a var() fallback");
  return m![1].toLowerCase();
}
// the aurora ramp, dark to light, read from the colormap module's own table
function auroraStops(): string[] {
  const m = /"aurora":\s*\[([\s\S]*?)\]/.exec(COLORMAP);
  assert.ok(m, "bin/romp_colormap.py declares the aurora ramp");
  const stops = Array.from(m![1].matchAll(/\((\d+),\s*(\d+),\s*(\d+)\)/g)).map((t) =>
    "#" + [t[1], t[2], t[3]].map((v) => parseInt(v, 10).toString(16).padStart(2, "0")).join(""));
  assert.ok(stops.length >= 5, "the ramp has its stops (" + stops.length + ")");
  return stops;
}
// sRGB hex -> OKLab (Bjorn Ottosson's matrices); OKLCH from it
function oklab(hex: string): { L: number; a: number; b: number } {
  const lin = (c: number) => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
  const [r, g, b] = [1, 3, 5].map((i) => lin(parseInt(hex.slice(i, i + 2), 16) / 255));
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return { L: 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
           a: 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
           b: 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s };
}
function oklch(hex: string): { L: number; C: number; h: number } {
  const { L, a, b } = oklab(hex);
  return { L, C: Math.hypot(a, b), h: ((Math.atan2(b, a) * 180) / Math.PI + 360) % 360 };
}
const hueGap = (h: number, ref: number) => Math.abs(((h - ref + 540) % 360) - 180);
const dist = (x: { L: number; a: number; b: number }, y: { L: number; a: number; b: number }) => Math.hypot(x.L - y.L, x.a - y.a, x.b - y.b);

const STEPS = ["--postal-coordinate", "--postal-question", "--postal-delegate"];   // in ramp order: first, middle, last stop
const MIN_HUE_GAP = 50;      // degrees of OKLCH hue between any two kinds: two tints of one hue sit at 0, T337's three at 0
const INK_GAP = 0.075;       // OKLab distance from --fg, T337's floor: a lone kind word is a colour, never body text

test("dark: the three kind tokens ARE stops of the aurora ramp, coordinate the first and delegate the last, a hue apart", () => {
  const stops = auroraStops();
  const b = block(":root {");
  const hexes = STEPS.map((n) => token(b, n));
  hexes.forEach((h, i) => assert.ok(stops.includes(h), `${STEPS[i]} ${h} is not a stop of the aurora ramp (${stops.join(" ")})`));
  assert.equal(new Set(hexes).size, 3, "three different stops");
  assert.equal(hexes[0], stops[0], "coordinate is the ramp's first stop (green)");
  assert.equal(hexes[2], stops[stops.length - 1], "delegate is the ramp's last stop (purple): the two the user confused, farthest apart");
  const qi = stops.indexOf(hexes[1]);
  assert.ok(qi > 0 && qi < stops.length - 1, "question is a middle stop (teal-blue)");
  const hs = hexes.map((h) => oklch(h).h);
  for (let i = 0; i < 3; i++) for (let j = i + 1; j < 3; j++)
    assert.ok(hueGap(hs[i], hs[j]) >= MIN_HUE_GAP, `${STEPS[i]} and ${STEPS[j]} are ${hueGap(hs[i], hs[j]).toFixed(0)} degrees apart, under ${MIN_HUE_GAP}`);
  const ink = oklab(token(b, "--fg"));
  hexes.forEach((h, i) => assert.ok(dist(oklab(h), ink) >= INK_GAP, `${STEPS[i]} is ${dist(oklab(h), ink).toFixed(3)} from --fg, too close to the ink`));
});

test("light: the same three hues, each deepened on its own hue for the cream page, a hue apart and clear of the ink", () => {
  const dark = block(":root {"), light = block("body.theme-light {");
  const pairs = STEPS.map((n) => ({ name: n, d: oklch(token(dark, n)), l: oklch(token(light, n)) }));
  for (const p of pairs) {
    assert.ok(hueGap(p.l.h, p.d.h) <= 4, `${p.name}: the light hue ${p.l.h.toFixed(1)} is not the dark stop's ${p.d.h.toFixed(1)}`);
    assert.ok(p.l.L < p.d.L - 0.1, `${p.name}: the light token (L ${p.l.L.toFixed(3)}) is not deepened below the stop (L ${p.d.L.toFixed(3)})`);
  }
  for (let i = 0; i < 3; i++) for (let j = i + 1; j < 3; j++)
    assert.ok(hueGap(pairs[i].l.h, pairs[j].l.h) >= MIN_HUE_GAP, `${STEPS[i]} and ${STEPS[j]} (light) are ${hueGap(pairs[i].l.h, pairs[j].l.h).toFixed(0)} degrees apart`);
  const ink = oklab(token(light, "--fg"));
  STEPS.forEach((n) => assert.ok(dist(oklab(token(light, n)), ink) >= INK_GAP, `${n} (light) is too close to the ink`));
});

test("the mapping is written once, beside the dark tokens, and names the colormap", () => {
  assert.match(CSS, /coordinate = the ramp's first stop \(green\), question = its fourth stop \(teal-blue\), delegate = its\s+last stop \(purple\)/,
               "the :root comment states the mapping in one sentence");
  assert.match(CSS, /default progress colormap \(aurora, bin\/romp_colormap\.py\)/, "the comment names the ramp and its file");
  assert.match(CSS, /the :root comment holds the mapping/, "the light block's comment points at that one place");
});
