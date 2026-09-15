// ONE loading treatment, ONE swirl direction (the user 2026-09-15, via romp_manager): the chat's history
// placeholders — the region gap glyph and the first-visit transcript-build wait — used a forked swirl
// (tx-swirl-spin, 1.6s, `reverse` over a -360deg keyframe = CLOCKWISE, and a sans wordmark at weight 650),
// where the product's standard loader (the .rl-* anatomy: the RompAnta wordmark with the swirl as its `o`,
// spun by rl-spin at 7s COUNTER-clockwise, plus the .rl-dots) turns the other way, slower, in the brand face.
// This pins the family onto that one treatment: no swirl keyframe in the webview CSS turns clockwise, no
// animation reverses one to get there, and the loader's forked keyframes (tx-swirl-spin, fileview-spin) are
// gone — the chat placeholders build through rompLoaderInner and the file viewer rides a shared keyframe.
// Source pins over the webview sheets + render.ts (the tab-order.ts pattern; no jsdom). Synthetic only.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const WEBVIEW = path.resolve(process.cwd(), "..", "ui", "webview");
const cssFiles = fs.readdirSync(WEBVIEW).filter((f) => f.endsWith(".css"));
const css: Record<string, string> = {};
for (const f of cssFiles) css[f] = fs.readFileSync(path.join(WEBVIEW, f), "utf8");
const RENDER = fs.readFileSync(path.join(WEBVIEW, "render.ts"), "utf8");

// every @keyframes block, by file, as { name, body }
function keyframes(sheet: string): { name: string; body: string }[] {
  const out: { name: string; body: string }[] = [];
  const re = /@keyframes\s+([A-Za-z0-9-]+)\s*\{/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(sheet))) {
    // walk to the matching close brace (keyframes bodies nest one level of { } per stop)
    let depth = 1, i = re.lastIndex;
    for (; i < sheet.length && depth > 0; i++) {
      if (sheet[i] === "{") depth++;
      else if (sheet[i] === "}") depth--;
    }
    out.push({ name: m[1], body: sheet.slice(re.lastIndex, i - 1) });
  }
  return out;
}

test("no swirl/spin keyframe in the webview CSS turns CLOCKWISE (every rotation is counter-clockwise, a negative angle)", () => {
  for (const f of cssFiles) {
    for (const k of keyframes(css[f])) {
      const rots = k.body.match(/rotate\(\s*(-?\d+)deg\)/g) || [];
      for (const r of rots) {
        const deg = Number((r.match(/rotate\(\s*(-?\d+)deg\)/) as RegExpMatchArray)[1]);
        assert.ok(deg <= 0, `${f} @keyframes ${k.name} rotates to ${deg}deg (clockwise); the loader family turns counter-clockwise (a negative angle), like rl-spin: ${r}`);
      }
    }
  }
});

test("no animation in the webview CSS uses `reverse` to spin a swirl the wrong way (the direction lives in the keyframe alone)", () => {
  for (const f of cssFiles) {
    // the animation shorthand only — never flex's `wrap-reverse`, nor prose in a comment
    const decls = css[f].match(/animation:[^;}]*/g) || [];
    for (const d of decls) {
      assert.ok(!/\breverse\b/.test(d), `${f} has an animation using reverse: ${d.trim()}. A reversed swirl turns clockwise; give the keyframe a -360deg turn instead.`);
    }
  }
});

test("the chat loader family shares ONE keyframe: the forked tx-swirl-spin and fileview-spin are gone", () => {
  assert.ok(!/@keyframes\s+tx-swirl-spin\b/.test(css["styles.css"]), "tx-swirl-spin (the chat placeholders' forked reverse-spin) is removed");
  for (const f of cssFiles) {
    assert.ok(!/@keyframes\s+fileview-spin\b/.test(css[f]), `${f}: the file viewer's forked fileview-spin is removed (folded onto the shared keyframe)`);
  }
  // the forked placeholder classes are gone too
  for (const cls of ["tx-loading-swirl", "tx-loading-wordmark", "tx-loading-dots", "tx-gap-swirl", "tx-gap-r", "tx-gap-mp"]) {
    assert.ok(!css["styles.css"].includes("." + cls), `styles.css: the forked class .${cls} is removed`);
    assert.ok(!RENDER.includes('"' + cls + '"'), `render.ts: nothing builds .${cls} any more`);
  }
});

test("the chat history placeholders build through the ONE standard loader (rompLoaderInner), scaled by rl-sm", () => {
  // the region gap glyph
  assert.match(RENDER, /function gapGlyph\(\): HTMLElement \{\s*\n\s*const w = el\("div", "tx-gap-glyph"\);\s*\n\s*w\.appendChild\(rompLoaderInner\("", \{ wordmark: true, cls: "rl-sm" \}\)\);/,
    "gapGlyph appends rompLoaderInner, not a forked swirl");
  // the first-visit transcript build's wait
  assert.match(RENDER, /const ld = el\("div", "tx-loading"\);\s*\n\s*ld\.appendChild\(rompLoaderInner\("", \{ wordmark: true, cls: "rl-sm" \}\)\);/,
    "the first-visit build's wait appends rompLoaderInner");
  // rompLoaderInner takes the size-modifier class and drops the caption line when empty
  assert.match(RENDER, /function rompLoaderInner\(caption: string, opts\?: \{ wordmark\?: boolean; cls\?: string \}\)/, "rompLoaderInner takes an optional size-modifier class");
  assert.match(RENDER, /const inner = el\("div", "rl-in" \+ \(opts\?\.cls \? " " \+ opts\.cls : ""\)\);/, "…applied to .rl-in");
  assert.match(RENDER, /if \(caption\) \{ const cap = el\("div", "revive-cap"\);[^\n]*\}\s*\n\s*else inner\.append\(word, dots\);/, "…and no caption line for an inline placeholder");
  // the size modifier exists and scales the wordmark (the em-based swirl scales with it): no new keyframe
  assert.match(css["styles.css"], /\.rl-in\.rl-sm \.rl-word \{ font-size: \d+px; \}/, "rl-sm scales the wordmark's font-size (rl-o is .65em, so the swirl scales too)");
});

test("the file viewer's loader rides a shared counter-clockwise keyframe at the loader pace, in each sheet that styles it", () => {
  assert.match(css["styles.css"], /\.fileview-load img \{[^}]*animation: rl-spin 7s linear infinite;/, "styles.css: .fileview-load img spins on rl-spin (the shared loader keyframe), 7s");
  assert.match(css["feed.css"], /\.fileview-load img \{[^}]*animation: fask-swirl-spin 7s linear infinite;/, "feed.css: .fileview-load img spins on the feed sheet's own shared swirl keyframe, 7s counter-clockwise");
});
