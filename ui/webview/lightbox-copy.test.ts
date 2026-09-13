// The lightbox Copy button (the user 2026-08-31): beside download, it puts the IMAGE ITSELF on the
// clipboard — and it must copy the DISPLAYED bytes, so the source is the current img element's src
// (pin param already baked in) read at CLICK time, which also keeps arrow-stepping retarget-free.
// preview.ts has import-time DOM side effects → source pins + an executed replica of the decisions
// (optimistic-send.test.ts precedent).
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const PREVIEW = fs.readFileSync(
  path.resolve(process.cwd(), "..", "ui", "webview", "preview.ts"), "utf8");
const CSS = fs.readFileSync(
  path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");

test("the button exists only where the clipboard API does — honest absence, never a dead control", () => {
  assert.match(PREVIEW, /if \(curImg && typeof ClipboardItem !== "undefined" && navigator\.clipboard && navigator\.clipboard\.write\) \{/);
  // img kind only: curImg is set in the img branch; the pdf branch never sets it
  assert.match(PREVIEW, /let curImg: \(\(\) => HTMLImageElement\) \| null = null;/);
  assert.match(PREVIEW, /curImg = \(\) => img;/);
});

test("copy reads the CURRENT img's src at click time — pin rides, arrow-stepping needs no retarget", () => {
  assert.match(PREVIEW, /const src = curImg!\(\)\.src;/);
  // the pin param is baked into src by mkImg…
  assert.match(PREVIEW, /im\.src = fileUrl\(e\.path, e\.sid\) \+ \(e\.pin \? "&pin=" \+ encodeURIComponent\(e\.pin\) : ""\);/);
  // …and step() rebinds the closure variable the accessor reads
  assert.match(PREVIEW, /img\.replaceWith\(next\);\s*\n\s*img = next;/);
});

test("write() runs synchronously in the gesture — the ClipboardItem takes the png PROMISE", () => {
  assert.match(PREVIEW, /const png = \(async \(\) => \{/);
  assert.match(PREVIEW, /navigator\.clipboard\.write\(\[new ClipboardItem\(\{ "image\/png": png \}\)\]\)/);
});

test("a png source writes directly; anything else re-encodes to png through a canvas", () => {
  assert.match(PREVIEW, /if \(blob\.type === "image\/png"\) return blob;/);
  assert.match(PREVIEW, /await createImageBitmap\(blob\)/);
  assert.match(PREVIEW, /cv\.toBlob\(\(b\) => \(b \? res\(b\) : rej\(new Error\("png encode failed"\)\)\), "image\/png"\)/);
});

test("the click acknowledges immediately and failures state why — both self-restore", () => {
  // the file viewer's glyph swap (T367, shared since T385): a check and "Copied", a cross whose words carry the reason
  assert.match(PREVIEW, /\(\) => say\(ICON_CHECK, "Copied", "ok", 1400\),/);
  assert.match(PREVIEW, /\(e\) => say\(ICON_CROSS, "Copy failed: " \+ \(\(e && \(e as Error\)\.message\) \|\| String\(e\)\), "err", 3000\)\);/);
  assert.match(PREVIEW, /const say = \(icon: string, word: string, cls: string, ms: number \| null\) => \{\s*\n\s*btn\.innerHTML = icon; btn\.title = word; btn\.setAttribute\("aria-label", word\);/);
  // the viewer's click-safety (T385 review): the press dims in its own tick, and ONE restore timer is cleared on every swap
  assert.match(PREVIEW, /ev\.stopPropagation\(\);\s*\/\/ copying must not also dismiss\s*\n\s*say\(COPY_SVG, "Copy image", "", null\);[^\n]*\n\s*btn\.classList\.add\("fileview-busy"\);/, "the same-tick acknowledgement, after the one state-setter reset the glyph and cleared a pulse's pending restore (review, round two)");
  assert.match(PREVIEW, /btn\.classList\.remove\("ok", "err", "fileview-busy"\); if \(cls\) btn\.classList\.add\(cls\);/);
  assert.match(PREVIEW, /if \(copyTimer\) \{ window\.clearTimeout\(copyTimer\); copyTimer = null; \}\s*\n\s*if \(ms !== null\) copyTimer = window\.setTimeout\(\(\) => say\(COPY_SVG, "Copy image", "", null\), ms\);/, "one timer, cleared on every swap");
  assert.match(PREVIEW, /ev\.stopPropagation\(\);\s*\/\/ copying must not also dismiss/);
});

test("the copy button wears the download control's exact dress — the file viewer's glyph button (T385), one control vocabulary", () => {
  assert.match(PREVIEW, /dl\.className = "fileview-btn fileview-icon romp-lightbox-dl";/);
  assert.match(PREVIEW, /btn\.className = "fileview-btn fileview-icon romp-lightbox-copy";/);
  assert.doesNotMatch(CSS, /\.romp-lightbox-dl, \.romp-lightbox-copy \{/, "the lightbox's own chip rules are gone: the shared .fileview-btn rules dress both");
  assert.match(CSS, /^\.fileview-btn\.fileview-icon\.ok \{ color: var\(--accent\); border-color: var\(--accent\); \}/m, "the ack colours are the shared rules'");
  assert.match(CSS, /^\.fileview-btn\.fileview-icon\.err \{ color: var\(--err\); border-color: var\(--err\); \}/m);
});

// ── executed replica: the two decisions ───────────────────────────────────────────────────────────

test("replica: click-time read copies what a step put on screen, pin included", () => {
  // mirrors mkImg + step + the copy handler's read
  const fileUrl = (p: string) => "/file?path=" + encodeURIComponent(p) + "&sid=s1";
  const mkSrc = (p: string, pin?: string) => fileUrl(p) + (pin ? "&pin=" + encodeURIComponent(pin) : "");
  let img = { src: mkSrc("plots/run1.png", "v1") };      // opened on a pinned historical version
  const curImg = () => img;
  assert.ok(curImg().src.includes("pin=v1"), "the pinned version is the copy source, not the live file");
  img = { src: mkSrc("plots/run2.jpg") };                // arrow-step rebinds the closure variable
  assert.equal(curImg().src, mkSrc("plots/run2.jpg"), "after a step the copy source IS the new image");
});

test("replica: only a png blob skips the re-encode", () => {
  const route = (blobType: string) => (blobType === "image/png" ? "direct" : "reencode");
  assert.equal(route("image/png"), "direct");
  assert.equal(route("image/jpeg"), "reencode");
  assert.equal(route("image/webp"), "reencode");
  assert.equal(route(""), "reencode", "an untyped blob still lands on the one type clipboards accept");
});
