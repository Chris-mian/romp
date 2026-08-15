// A mentioned image/PDF renders FULL-SIZE in the chat (the user 2026-07-20, who wanted not even a thumbnail
// but a rendered image, similar to how it renders the user messages), AT its mention — the figure
// follows the block whose prose names it (the user 2026-08-15) — absolute OR relative path; the
// kernel resolves a relative one against the session's cwd exactly like click-to-open. Per surface:
// web renders via previewFull (kernel /file bytes → <img> at the user-image scale / a PDF card;
// kernel-verified paths fail LOUDLY with a retry chip, only unverified ones self-remove); the VS Code
// webview can't reach the kernel origin from an <img>, so images ride the SAME host data-URL flow the
// user-message pictures use (imgRequest, now carrying the session id) and PDFs keep the click-to-open
// link. Source pins.
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as fs from "node:fs";
import * as path from "node:path";

const PREVIEW = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "preview.ts"), "utf8");
const RENDER = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "render.ts"), "utf8");
const CSS = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "styles.css"), "utf8");
const FEED = fs.readFileSync(path.resolve(process.cwd(), "..", "ui", "webview", "feed.ts"), "utf8");
const KERNEL = fs.readFileSync(path.resolve(process.cwd(), "..", "kernel", "kernel.py"), "utf8");

test("previewFull renders the image itself; a PDF is a click-to-view CARD, never an auto-loading frame", () => {
  assert.match(PREVIEW, /export function previewFull\(path: string, sid\?: string \| null, verified = false\): HTMLElement \| null/);
  assert.match(PREVIEW, /img\.className = "path-full-img";/);
  // NO inline <iframe> for PDFs (2026-07-20): a browser set to "Download PDFs" saved a fresh copy on
  // EVERY chat re-render — the Downloads folder silently filled. The fetch must be user-initiated.
  const pf = PREVIEW.slice(PREVIEW.indexOf("export function previewFull"));
  assert.doesNotMatch(pf, /createElement\("iframe"\)/, "no auto-loading PDF frame in the chat strip");
  assert.match(pf, /box\.classList\.add\("path-full-pdfcard"\);/);
  assert.match(pf, /box\.onclick = \(ev\) => \{ ev\.stopPropagation\(\); openLightbox\(path, sid\); \};/);
  // the HEAD probe (headers only — never a download) still removes a dead UNVERIFIED card; a
  // kernel-verified card skips it — a transient probe failure must not erase a real file's card
  assert.match(pf, /if \(!verified\) fetch\(fileUrl\(path, sid\), \{ method: "HEAD" \}\)/);
});

test("a kernel-VERIFIED preview fails LOUDLY: a retry chip holds the figure's spot, never silent removal", () => {
  const pf = PREVIEW.slice(PREVIEW.indexOf("export function previewFull"));
  // unverified (old kernel, no pathLinks verdict) keeps self-removal — there the error means "no such file"
  assert.match(pf, /if \(!verified\) \{ box\.remove\(\); return; \}/);
  assert.match(pf, /chip\.className = "path-full-retry";/);
  assert.match(pf, /chip\.onclick = \(ev\) => \{ ev\.stopPropagation\(\); build\(true\); \};/, "tap to retry rebuilds the img");
  assert.match(pf, /img\.src = bust \? url \+ "&r=" \+ Date\.now\(\) : url;/, "a retry cache-busts the failed entry");
  // the render layer feeds the verdict: spacePaths and pathLinks hits are kernel-stat'd paths
  assert.match(RENDER, /const kernelVerified = new Set<string>\(\);/);
  assert.match(RENDER, /if \(!isUri && typeof fixed === "string"\) kernelVerified\.add\(open\);/);
  assert.match(CSS, /\.path-full-retry \{ display: inline-flex;/, "visible chrome — the chip has chat-sheet css");
});

test("the chat uses the FULL render on web, and the host data-URL flow for images in VS Code", () => {
  assert.match(RENDER, /const full = canPreview\(\) \? previewFull\(p, activeId, kernelVerified\.has\(p\)\)\s*\n\s*: previewKind\(p\) === "img" \? buildPathImg\(p\) : null;/);
  assert.doesNotMatch(RENDER, /previewThumb/, "the chat no longer renders mention thumbnails — full renders now");
});

test("figures render AT their mention: after the block naming them; same-block figures share a strip", () => {
  // path → first mention element, captured in BOTH linkify passes (space paths and the token walker)
  assert.match(RENDER, /const mentionAt = new Map<string, HTMLElement>\(\);/);
  assert.match(RENDER, /mentionAt\.set\(tok, code\);/, "the space-path pass anchors on its code span");
  assert.match(RENDER, /mentionAt\.set\(open, link\);/, "the token walker anchors on the link it minted");
  assert.match(RENDER, /const BLOCK_SEL = "p, li, h1, h2, h3, h4, h5, h6, blockquote, td, th";/);
  assert.match(RENDER, /anchor\.insertAdjacentElement\("afterend", strip\);/, "a paragraph's figure lands right after it");
  assert.match(RENDER, /\/\^\(LI\|TD\|TH\)\$\/\.test\(anchor\.tagName\)/, "a list item keeps its figure inside, under its bullet");
  assert.match(RENDER, /previewable\.slice\(0, 4\)/, "the wallpaper cap stays");
});

test("VS Code's pending image chip pulses while the host round-trip is in flight; a failed one doesn't", () => {
  assert.match(RENDER, /"user-img-path" \+ \(imgFailed\.has\(p\) \? "" : " img-pending"\)/);
  assert.match(CSS, /\.user-img-path\.img-pending::after \{ content: " ···";/);
  assert.match(CSS, /prefers-reduced-motion: reduce\) \{ \.user-img-path\.img-pending::after \{ animation: none;/);
});

test("imgRequest carries the session id so RELATIVE mentioned paths resolve against the session cwd", () => {
  assert.match(RENDER, /vscodeApi\.postMessage\(\{ type: "imgRequest", path: p, id: activeId \}\);/);
  assert.match(KERNEL, /_img_data_url\(_resolve_open_path\(p, msg\.get\("id"\)\)\)/);
});

test("full-size images wear the user-image scale — one size per information type", () => {
  assert.match(CSS, /\.path-full-img \{[^}]*max-height: 320px/);
  assert.match(CSS, /\.user-img \{[^}]*max-height: 320px/);
  assert.match(CSS, /\.path-full-pdfcard \{/);
});

test("previewThumb is gone with the feed's artifact strips (2026-08-14) — the full render is the one preview", () => {
  assert.doesNotMatch(PREVIEW, /previewThumb/, "no orphaned thumbnail builder");
});
