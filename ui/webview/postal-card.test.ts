// T302 (the user 2026-09-10, after seeing old and new postal cards side by side): the kind is coloured TEXT in the
// old chip colours, the delivery state is an icon at the head's right edge (sent / delivered / read / parked /
// bounced / recalled, from what the kernel files), both ENDS wear their sessions' colours (the peer's chip, then
// this session's own), the incoming card wears the peer's hue as a tint on its own ground (back since 2026-09-11), and a sent card whose message has not landed wears the
// pending send's own provisional dress (the queued bubble's class and rule). Source pins (render.ts has
// import-time DOM side effects); the pure module is executed in postal-state.test.ts.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
function fn(name: string): string {
  const i = RENDER.indexOf("function " + name + "(");
  return RENDER.slice(i, RENDER.indexOf("\n}\n", i));
}
const CARD = fn("renderPostalService");

test("the kind is coloured text in the meta slot, never a chip, at prose weight, in three colormap hues", () => {
  assert.match(RENDER, /import \{ kindLabel, deliveryOf, deliveryTitle[^}]*\} from "\.\/postal-state";/);
  assert.match(CARD, /const kind = kindLabel\(intent \? intent\.cls : null\);/);
  assert.match(CARD, /meta = el\("span", "postal-kind postal-kind-" \+ intent\.cls\); meta\.textContent = kind;/);
  assert.doesNotMatch(CARD, /postal-service-intent|notice-chip/, "no chip");
  // T320 (the user 2026-09-10): the word is NOT bold (the prose weight), and the three colours are TOKENS on ONE
  // three hues from the aurora colormap (T371: coordinate green, question teal-blue, delegate purple, the two the user
  // confused farthest apart), each with a light-theme re-ink (the parity test holds every one at 4.5:1 on its grounds)
  assert.match(CSS, /\.postal-kind \{ font-weight: 400; \}/, "prose weight, not bold");
  assert.doesNotMatch(CSS, /\.postal-kind \{ font-weight: (600|700|bold)/);
  // (T371: three hues from the aurora colormap, the two the user confused farthest apart; postal-kind-ramp.test.ts
  // holds the stops, the hue distances and the light re-ink, these the values)
  assert.match(CSS, /\.postal-kind-delegate \{ color: var\(--postal-delegate, #9088f0\); \}/);
  assert.match(CSS, /\.postal-kind-coordinate \{ color: var\(--postal-coordinate, #54b204\); \}/);
  assert.match(CSS, /\.postal-kind-question \{ color: var\(--postal-question, #42a9b0\); \}/);
  assert.match(CSS, /\n  --postal-coordinate: #54b204;\s+--postal-delegate: #9088f0;\s+--postal-question: #42a9b0;/, "the dark tokens: the ramp's first, last and fourth stops");
  const light = CSS.slice(CSS.indexOf("body.theme-light {"), CSS.indexOf("\n}\n", CSS.indexOf("body.theme-light {")));
  assert.match(light, /--postal-coordinate: #386f18;\s+--postal-delegate: #5f57ab;\s+--postal-question: #0d6d73;/, "the light tokens: the same hues, deepened");
  // three hues, not one ramp: the eye tells the kinds apart by hue, so no luminance order is pinned any more (T337's
  // monotone ladder is retired with the line); the mapping sentence sits beside the tokens
  assert.match(CSS, /coordinate = the ramp's first stop \(green\), question = its fourth stop \(teal-blue\), delegate = its\s+last stop \(purple\)/, "the mapping sits beside the tokens");
  // under the narrow container query the head WRAPS: the gist takes its own full-width line, word-wise, and the kind
  // word keeps the first line whole and inside the card (T313; the 4ch floor that squeezed the gist into a letter
  // column beside the ends is gone)
  assert.match(CSS, /@container \(max-width: 360px\) \{\n  \.turn-postal-service \.notice-head \{ flex-wrap: wrap; \}\n  \.turn-postal-service \.notice-head > \.notice-gist \{ flex: 1 0 100%; order: 1; min-width: 0;\n    white-space: normal; overflow: visible; text-overflow: clip; overflow-wrap: break-word; \}\n\}/);
  assert.doesNotMatch(CSS, /min-width: min\(100%, 4ch\)/, "no character-wide gist column anywhere");
  assert.doesNotMatch(CSS, /@container \(max-width: 360px\) \{\n  \.turn-postal-service \.notice-meta/, "the meta no longer shrinks under it");
  // never truncated: the postal meta stays rigid
  assert.match(CSS, /\.turn-postal-service \.notice-meta \{ flex: 1 0 auto; display: inline-flex; align-items: baseline; gap: 7px; min-width: 0; \}/,
    "the postal meta never shrinks (the kind word stays whole) and grows to the head's edge to carry the icon (T313)");
});

test("the incoming card wears the peer's hue at its ground's own lightness, in both themes; the sent card does not", () => {
  // the user 2026-09-11, who missed the tint T302 had removed the day before on their own side-by-side ruling. A hue at
  // the ground's lightness, not a mix: a mix lifts the ground and the dimmest kind word fell under the ramp's 4.5:1 floor
  assert.match(CSS, /\.turn-postal-service\.postal-service-in \.notice:not\(\.notice-slim\) \{\n  background: oklch\(from var\(--notice-rail, var\(--box-bg\)\) var\(--postal-wash-l, 0\.263\) var\(--postal-wash-c, 0\.03\) h\); \}/,
               "one declaration: the rail's hue (the peer's colour) at the ground's lightness and a gentle chroma, each token with a fallback");
  assert.match(CSS, /\n  --postal-wash-l: 0\.263;  --postal-wash-c: 0\.03;/, "the dark ground's lightness and the chroma, beside the kind tokens");
  assert.match(CSS, /\n  --postal-wash-l: 0\.919;  --postal-wash-c: 0\.045;/, "the light ground's lightness and a stronger chroma for the cream's warm hue, in the light block");
  assert.doesNotMatch(CSS, /theme-light[^{}]*postal-service-in[^{}]*\{[^}]*background/, "no theme takes it back");
  assert.doesNotMatch(CSS, /postal-service-out[^{}]*\{[^}]*oklch\(from var\(--notice-rail/, "the sent card is untinted");
  assert.match(fn("renderPostalService"), /rail: ev\.color \? ev\.color\.bg : undefined/, "the rail is the peer's colour, so the hue is the peer's");
});

const STATE = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "postal-state.ts"), "utf8");

test("the delivery state is one icon per state at the head's right edge, each with a worded title", () => {
  // the glyph map lives in the pure module (postal-state.test.ts executes it: the T337 ladder); the renderer imports it
  for (const st of ["sent", "delivered", "read", "parked", "bounced", "recalled"]) {
    assert.match(STATE, new RegExp("^  " + st + ": '<", "m"), st + " has a glyph");
  }
  assert.match(STATE, /export const DELIVERY_GLYPHS: Record<PostalDeliveryState, string>/);
  assert.doesNotMatch(RENDER, /const DELIVERY_GLYPHS/, "one map, in the module");
  assert.match(RENDER, /import \{ kindLabel, deliveryOf, deliveryTitle, DELIVERY_GLYPHS, type PostalDelivery, type PostalReceipt \} from "\.\/postal-state";/);
  assert.doesNotMatch(RENDER, /type PostalDeliveryState/, "the state type left the renderer with the map");
  // the mark's wrapper (T337, the user 2026-09-10 wanting the circled check): a 16-unit box drawn at 14 px, a 1.5 stroke,
  // round caps and joins, no fill unless a rung says so; the read rung's check is knocked out in the page colour by the
  // sheet (a presentation attribute cannot carry a var())
  assert.match(fn("deliveryIcon"), /'<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" '\s*\+ 'stroke-width="1\.5" stroke-linecap="round" stroke-linejoin="round">' \+ DELIVERY_GLYPHS\[d\.state\] \+ "<\/svg>"/);
  assert.match(CSS, /\.postal-delivery-read \.postal-mark-check \{ stroke: var\(--bg\); \}/, "the read rung's check is cut out of the filled circle");
  assert.match(STATE, /export const MARK_CHECK_CLASS = "postal-mark-check";/);
  assert.match(fn("deliveryIcon"), /span\.dataset\.state = d\.state;/);
  assert.match(fn("deliveryIcon"), /span\.setAttribute\("role", "img"\);/, "a labelled span is announced only with an image role");
  assert.match(fn("deliveryIcon"), /const title = deliveryTitle\(d, clockOf\);[^\n]*\n\s*setTip\(span, title\);[^\n]*\n\s*span\.setAttribute\("role", "img"\);[^\n]*\n\s*span\.setAttribute\("aria-label", title\);/);
  assert.match(CARD, /const delivery = deliveryOf\(ev\);/);
  assert.match(CARD, /turn\.querySelector\("\.notice-meta"\)\?\.appendChild\(deliveryIcon\(delivery\)\);/);
  assert.match(CSS, /\.postal-delivery \{ flex: 0 0 auto; margin-left: auto;/, "the right edge");
  // on a fold-less card whose one line wraps, the icon sits on the FIRST line like the glyph, not centred over the block
  // the icon rides inside the META slot (T313): a one-line flex box the head aligns by baseline, so it sits on the kind
  // word's line, the first, however the gist wraps — and on a phone-width head the two wrap as one unit
  assert.match(RENDER, /turn\.querySelector\("\.notice-meta"\)\?\.appendChild\(deliveryIcon\(delivery\)\);/);
  // …and the meta always exists when there is an icon: a kind-less legacy card (no declared kind, no leading token) with
  // a delivery state gets an EMPTY meta slot, so no icon is ever appended straight to the head (T313 review find)
  assert.match(RENDER, /if \(!meta && delivery\) meta = el\("span", "postal-meta-empty"\);/);
  assert.doesNotMatch(RENDER, /notice-head"\)\?\.appendChild\(deliveryIcon/, "no second path for the icon");
  assert.doesNotMatch(CSS, /\.postal-delivery \{ align-self: flex-start; margin-top: 4px; \}/, "no first-line nudge left: the meta's line IS the first line");
  assert.match(CSS, /\.postal-delivery-read \{ color: var\(--accent\); \}/);
  assert.match(CSS, /\.postal-delivery-parked \{ color: var\(--warn\); \}/);
  assert.match(CSS, /\.postal-delivery-bounced \{ color: var\(--st-blocked-bg\); \}/);
  // the words "delivered" / "parked" left the meta text: no meta words are pushed any more
  assert.doesNotMatch(CARD, /meta\.push\(/);
  // the event carries the ledger's receipt
  assert.match(RENDER, /receipt\?: PostalReceipt;/);
});

test("both ends wear their sessions' colours as bold names, no chip (T390); a narrow head keeps its dot", () => {
  assert.match(CARD, /const src = el\("span", "notice-src-ends"\);/);
  // the own end is the session that OWNS the transcript being built (a comment popover's parent, a subagent
  // viewer's session), the same chain every other owner lookup in the file uses (review, 2026-09-10)
  assert.match(CARD, /const ownId = renderingOwnerSid \?\? renderingSid \?\? activeId;/);
  assert.match(CARD, /const own = ownId && sessions\.has\(ownId\) \? sessions\.get\(ownId\) : undefined;/);
  // the working dot is the peer end's; the own end never gains one from the next working frame (no flap)
  assert.match(fn("refreshPostalDots"), /querySelectorAll\("\.notice-src-peer"\)/);
  assert.match(CARD, /ev\.direction === "in" \? "from " : "to "/);
  assert.match(CARD, /ev\.direction === "in" \? " to " : " from "/);
  // the two ends: the name itself, bold, in the identity colour; the peer's host prefix muted as the tab wears it, the own
  // end's through hostNameNodes; no chip class, no --peer-fg (nothing is filled that the fg would read on)
  assert.match(CARD, /const peer = el\("span", "notice-src-end notice-src-peer"\);\s*\n\s*peer\.append\(\.\.\.hostPartsNodes\(ev\.peerHost, ev\.peer\)\);/);
  assert.match(CARD, /const self = el\("span", "notice-src-end notice-src-self"\);/);
  assert.match(CARD, /nm\.append\(\.\.\.hostNameNodes\(own\.name, ownId\)\);/, "the host label muted, as the tab wears it");
  assert.match(CARD, /if \(own\.color\) self\.style\.setProperty\("--peer-bg", own\.color\.bg\);/);
  assert.doesNotMatch(CARD, /notice-src-chip|--peer-fg/, "no chip class and no chip foreground on either end");
  assert.doesNotMatch(RENDER, /notice-src-chip/, "the chip class is gone from the file");
  assert.match(CSS, /\.notice-src-end \{ letter-spacing: 0\.02em; text-transform: none; font-weight: 700;\s*\n\s*color: var\(--peer-bg, var\(--fg\)\);[^\n]*\n\s*color: oklch\(from var\(--peer-bg, var\(--fg\)\) var\(--peer-ink-l, l\) c h\); \}/,
    "bold, inked from the identity colour at the theme's lightness, the colour itself first for an engine without relative colours; no background, padding or radius");
  assert.match(CSS, /--peer-ink-l: max\(l, 0\.72\);/, "the dark theme inks the colour at its own lightness, lifted to the palette sweep's floor (T390 fold)");
  assert.match(CSS, /--peer-ink-l: 0\.46;/, "the cream theme deepens it on its own hue");
  assert.match(CSS, /@container \(max-width: 520px\) \{\n  \.turn-postal-service \.notice-src-self \{ display: inline-block; width: 10px; height: 10px; padding: 0; border-radius: 50%; align-self: center; overflow: hidden;\s*\n\s*background: var\(--peer-bg, var\(--overlay-10\)\); \}/, "the collapsed own end is the one filled dot");
  assert.match(CSS, /\.turn-postal-service \.notice-src-self \.notice-src-name \{ display: none; \}/);
});

test("the old 6% mix and its hook stay gone; incoming keeps border + rail, sent stays slim", () => {
  assert.doesNotMatch(CSS, /\.notice-peer > \.notice:not\(\.notice-slim\)/, "the retired hook's rule stays gone");
  assert.doesNotMatch(CSS, /color-mix\(in srgb, var\(--notice-rail, transparent\) 6%/, "the mix that lifted the ground stays gone: the tint is a hue at the ground's lightness (below)");
  assert.match(CARD, /rail: ev\.color \? ev\.color\.bg : undefined,/, "the rail still names the peer");
  // the shared notice rule (a body → a card, head-only → slim) stands, and the postal card overrides it for ONE
  // direction: incoming keeps its box even with nothing to fold; sent stays slim
  assert.match(fn("notice"), /const boxed = collapsible \|\| acts\.length > 0;/);
  assert.match(CARD, /if \(ev\.direction === "in"\) \{ turn\.classList\.add\("notice-boxed"\); turn\.querySelector\("\.notice"\)\?\.classList\.remove\("notice-slim"\); \}/);
  // …and a boxed card with nothing to fold still WRAPS its one line (T294's rule, now keyed on the fold, not on
  // slimness): an ellipsis with nothing behind it to click is the dead end the rule forbids (review, 2026-09-10)
  assert.match(CSS, /\.turn-postal-service \.notice:not\(\.notice-collapsible\) \.notice-gist \{ white-space: normal; overflow: visible; text-overflow: clip; overflow-wrap: anywhere; \}/);
  assert.match(CSS, /\.turn-postal-service \.notice:not\(\.notice-collapsible\) \.notice-glyph \{ align-self: flex-start; margin-top: 4px; \}/);
  assert.doesNotMatch(CARD, /notice-peer/, "the wash hook is gone with the wash");
});

test("a sent card that has not landed wears the pending send's own provisional dress: the same class and rule", () => {
  assert.match(CARD, /if \(ev\.direction === "out" && \(delivery\.state === "sent" \|\| delivery\.state === "parked"\)\) \{\s*\n\s*turn\.querySelector\("\.notice"\)\?\.classList\.add\("queued-bubble"\);/);
  // the pending bubble's rule reaches the notice by selectors on the SAME declaration block, no lookalike copy: the
  // notice of EITHER density, since a sent card boxed by its fold is a .notice with no .notice-slim, and `.notice` alone
  // (0,1,0) later in the file used to win that card's border, background and radius back from `.queued-bubble` (0,1,0);
  // `.notice.queued-bubble` (0,2,0) outranks it. The slim selector (0,3,0) stays: `.notice.notice-slim` (0,2,0) is
  // later in the file too and would otherwise take the slim card's dress back from `.notice.queued-bubble`.
  assert.match(CSS, /\.queued-bubble, \.notice\.queued-bubble, \.notice\.notice-slim\.queued-bubble,\s*\n\.turn\.echo \.user-bubble\.cmd-row\.echo-bubble \{/, "…and the echo of a slash command joins the list (T403)");
  // the width reset reaches both densities the same way: the boxed card keeps the column too, so it never snaps from
  // the bubble's 72% to the full width when the receipt lands
  assert.match(CSS, /\.notice\.queued-bubble, \.notice\.notice-slim\.queued-bubble \{ max-width: none; display: block; \}/, "the row keeps its width at either density (the same specificities as the shared rule, later)");
  // the bubble's border + padding move the head line down: the rail dot follows, as it does for a boxed card
  assert.match(CARD, /turn\.classList\.add\("postal-provisional"\)/);
  assert.match(CSS, /\.turn-postal-service\.postal-provisional > \.dot, \.turn-postal-service\.postal-provisional > \.time-marker \{ top: 18px; \}/);
  assert.equal((CSS.match(/border: 1px dashed color-mix\(in srgb, var\(--you\) 55%, transparent\)/g) || []).length, 1,
               "one dashed --you border rule in the file: the bubble's");
  // T337 (the review of the kind colours): the dress FADES BY ITS COLOURS, not by an element opacity that dimmed every
  // colour inside (the kind word read below 4.5:1 on the wash): the old 10% / 65% / 0.85 are folded into 8.5% / 55% /
  // an 85% --fg ink, the ink is a custom property the notice's gist and body read (their own rules set --fg back), and
  // the head's own colours stay whole
  const SHARED = ".queued-bubble, .notice.queued-bubble, .notice.notice-slim.queued-bubble,";   // the list runs on to the echo of a slash command (T403)
  assert.ok(CSS.indexOf(SHARED) > 0, "the shared provisional rule is where the slice looks");
  const bubble = CSS.slice(CSS.indexOf(SHARED), CSS.indexOf("\n}\n", CSS.indexOf(SHARED)));
  assert.doesNotMatch(bubble, /opacity:/, "no element opacity on the provisional dress");
  assert.match(bubble, /--prov-ink: color-mix\(in srgb, var\(--fg\) 85%, transparent\);/);
  assert.match(bubble, /background: color-mix\(in srgb, var\(--you\) 8\.5%, transparent\);/);
  assert.match(bubble, /color: var\(--prov-ink\);/);
  assert.match(CSS, /\.notice\.queued-bubble \.notice-gist, \.notice\.queued-bubble \.notice-body \{ color: var\(--prov-ink\); \}/, "the words fade with the dress");
  assert.doesNotMatch(CSS, /queued-bubble[^\n]*\.postal-kind/, "nothing re-colours the kind word on the provisional card: the token reads there as it is");
  // the old opacity lifts are ink lifts now, and no queued-bubble rule carries an opacity at all: the hovered cancelable
  // bubble and the bubble being edited bring the words to full ink, and a notice romp itself queued (T243) keeps its
  // landed card's full ink under the wrapper
  assert.match(CSS, /\.queued-bubble\.cancelable:hover \{ --prov-ink: var\(--fg\); border-color: var\(--accent\); \}/);
  assert.match(CSS, /\.queued-bubble\.queued-romp \{ background: transparent; border: 0; padding: 0; --prov-ink: var\(--fg\); \}/);
  assert.doesNotMatch(CSS, /\.queued-bubble[^\n{]*\{[^}]*\bopacity:/, "no queued-bubble rule sets an opacity: the fade and its lifts are the ink");
  assert.match(CSS, /\.queued-bubble\.cancelable \{ position: relative; padding-right: 30px; transition: color \.1s, border-color \.1s, background \.1s; \}/, "the transition names what changes");
});

test("the postal card's head carries no tooltip restating its kind badge (the user 2026-09-12)", () => {
  // the badge already says coordination, delegation or question; a hover that repeated it was one more thing to read
  assert.match(RENDER, /cls: "turn-postal-service postal-service-" \+ ev\.direction \}\);/, "the notice spec ends at the class: no tip");
  assert.ok(!RENDER.includes('"interaction type: "'), "the restating sentence is gone");
});
