// File-preview helpers for the chat (render.ts path thumbnails and full-size renders) — the user
// 2026-07-08: when an agent produces a plot/PDF/screenshot, show the thing, not just
// its path. The bytes come from the kernel's `/file?path=…&sid=…` endpoint (extension-allowlisted,
// existence-checked, behind the same auth as every route), so a preview is only ever what the kernel
// can actually read RIGHT NOW — a deleted/hallucinated path 404s and the <img> onerror hides the thumb
// (event-based; no stale placeholders). Web dashboard only: the VS Code webview sandbox can't reach the
// kernel origin from an <img>, so callers gate on canPreview() and keep the plain click-to-open link.

import { hostOf, bareId } from "./host-prefix";
import { mediaSrc } from "./media";

// Extensions the kernel's _PREVIEW_MIME serves — keep the two lists in step (tests pin both).
const IMG_EXT = new Set(["png", "jpg", "jpeg", "gif", "webp", "bmp", "svg"]);

export type PreviewKind = "img" | "pdf";

export function previewKind(path: string): PreviewKind | null {
  const ext = path.slice(path.lastIndexOf(".") + 1).toLowerCase();
  if (IMG_EXT.has(ext)) return "img";
  if (ext === "pdf") return "pdf";
  return null;
}

// Previews load over the page's own origin, so they only work where the page IS the kernel
// (the web dashboard). In the VS Code webview (vscode-webview: origin) a relative /file URL
// resolves nowhere — callers keep the existing openFile behavior there.
export function canPreview(): boolean {
  return location.protocol === "http:" || location.protocol === "https:";
}

// LOADING CUE (the user 2026-07-31): a remote image's bytes arrive over the ssh tunnel, so for a
// beat the message showed only the path text and the picture "popped in" with nothing saying it was
// on the way. Per the loading-state rule the first thing up is the romp swirl: a mini spinning glyph
// holds the image's spot until its `load` event lands (event-based; an error still removes the whole
// box, spinner included — no backstop needed because the cue dies with its box either way). Memoized
// per URL for this page life: chat re-renders rebuild these elements constantly, and re-flashing a
// spinner over bytes the browser just painted would itself be flicker — only a URL's FIRST load spins.
const loadedOnce = new Set<string>();
function withLoadCue(box: HTMLElement, img: HTMLImageElement, url: string): void {
  if (loadedOnce.has(url)) return;
  const spin = document.createElement("img");
  spin.className = "path-load-spin";
  spin.src = mediaSrc("romp-swirl-glyph.svg");
  spin.alt = "loading preview…";
  spin.title = "loading preview…";
  box.appendChild(spin);
  img.classList.add("path-img-loading");
  img.addEventListener("load", () => {
    loadedOnce.add(url);
    spin.remove();
    img.classList.remove("path-img-loading");
  });
}

// The kernel serves the bytes; sid lets it resolve a relative path against THAT session's cwd
// (same resolution as click-to-open — kernel _resolve_open_path). A FEDERATED session's file lives
// on the REMOTE machine's disk, so a host-prefixed sid (`gpu1:‹uuid›` — see federation.ts) routes
// through this kernel's /remote/<host>/file relay, the HTTP twin of the /remote/<host>/ws splice,
// with the bare sid the remote kernel actually knows (the user 2026-07-31: mentioned plots on a
// remote session's chat never rendered — /file read the LOCAL disk and 404'd). Still a same-origin
// URL, so it works wherever the dashboard is viewed from (the phone over `tailscale serve` included).
export function fileUrl(path: string, sid?: string | null): string {
  const host = sid ? hostOf(sid) : "";
  const base = host ? "/remote/" + encodeURIComponent(host) + "/file" : "/file";
  const bare = sid ? bareId(sid) : "";
  return base + "?path=" + encodeURIComponent(path) + (bare ? "&sid=" + encodeURIComponent(bare) : "");
}

// Full-view lightbox: dark backdrop, the image at natural-but-capped size or the PDF in the browser's
// native viewer, filename caption. One singleton element; backdrop click / Esc / ✕ closes. Styles live
// in BOTH styles.css and feed.css (each page loads only its own sheet — the .romp-acted precedent).
export function openLightbox(path: string, sid?: string | null): void {
  document.getElementById("romp-lightbox")?.remove();
  const kind = previewKind(path);
  if (!kind) return;
  const wrap = document.createElement("div");
  wrap.id = "romp-lightbox";
  const inner = document.createElement("div");
  inner.className = "romp-lightbox-inner" + (kind === "pdf" ? " pdf" : "");
  if (kind === "pdf") {
    const frame = document.createElement("iframe");
    frame.className = "romp-lightbox-frame";
    frame.src = fileUrl(path, sid);
    frame.title = path;
    inner.appendChild(frame);
  } else {
    const img = document.createElement("img");
    img.className = "romp-lightbox-img";
    img.src = fileUrl(path, sid);
    img.alt = path;
    inner.appendChild(img);
  }
  const bar = document.createElement("div");
  bar.className = "romp-lightbox-bar";
  const name = document.createElement("span");
  name.className = "romp-lightbox-name";
  name.textContent = path;
  name.title = path;
  const close = document.createElement("button");
  close.className = "romp-lightbox-close";
  close.textContent = "✕";
  close.title = "close (Esc)";
  bar.append(name, close);
  inner.appendChild(bar);
  wrap.appendChild(inner);
  const dismiss = () => { wrap.remove(); document.removeEventListener("keydown", onKey, true); };
  const onKey = (ev: KeyboardEvent) => { if (ev.key === "Escape") { ev.stopPropagation(); dismiss(); } };
  close.onclick = (ev) => { ev.stopPropagation(); dismiss(); };
  wrap.onclick = (ev) => { if (ev.target === wrap) dismiss(); };   // backdrop closes; content clicks don't
  document.addEventListener("keydown", onKey, true);
  document.body.appendChild(wrap);
}

// FULL-SIZE inline render for a mentioned image in the CHAT (the user 2026-07-20, who wanted not even a
// thumbnail but a rendered image, like the user messages). Self-verifying —
// a path the kernel can't serve removes itself — and an image click still opens the lightbox. Images
// render at the user-image scale (.path-full-img mirrors .user-img's 320px cap, one size per
// information type). A PDF is a labeled CARD, not an auto-loading inline viewer (click → lightbox):
// the first cut embedded an <iframe> per mentioned PDF, and a browser set to "Download PDFs" (or one
// that declines to render inline) saved a FRESH COPY on every chat re-render — the user's Downloads
// folder silently filled with datasheet copies (2026-07-20). A fetch must be user-initiated, once.
// Web only — callers gate on canPreview and fall back per surface.
export function previewFull(path: string, sid?: string | null): HTMLElement | null {
  const kind = previewKind(path);
  if (!kind || !canPreview()) return null;
  const box = document.createElement("span");
  box.className = "path-full" + (kind === "pdf" ? " pdf" : "");
  box.title = path;
  if (kind === "pdf") {
    box.classList.add("path-full-pdfcard");
    const tag = document.createElement("span");
    tag.className = "path-thumb-tag";
    tag.textContent = "PDF";
    const nm = document.createElement("span");
    nm.className = "path-thumb-name";
    nm.textContent = path.slice(path.lastIndexOf("/") + 1);
    box.append(tag, nm);
    box.style.cursor = "pointer";
    box.title = "click to view " + path;
    box.onclick = (ev) => { ev.stopPropagation(); openLightbox(path, sid); };
    // a chip can't self-verify like an <img> — HEAD-probe (headers only, no body — never a download)
    // so a missing PDF never shows a dead card
    fetch(fileUrl(path, sid), { method: "HEAD" }).then((r) => { if (!r.ok) box.remove(); }).catch(() => box.remove());
  } else {
    const img = document.createElement("img");
    img.className = "path-full-img";
    const url = fileUrl(path, sid);
    img.src = url;
    img.alt = path;
    img.loading = "lazy";
    img.onerror = () => box.remove();
    img.onclick = (ev) => { ev.stopPropagation(); openLightbox(path, sid); };
    withLoadCue(box, img, url);   // mini swirl holds the spot until the load event (first load only)
    box.appendChild(img);
  }
  return box;
}
