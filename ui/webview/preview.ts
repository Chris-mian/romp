// File-preview helpers shared by the chat (render.ts path thumbnails) and the feed (feed.ts artifact
// strips) — the user 2026-07-08: when an agent produces a plot/PDF/screenshot, show the thing, not just
// its path. The bytes come from the kernel's `/file?path=…&sid=…` endpoint (extension-allowlisted,
// existence-checked, behind the same auth as every route), so a preview is only ever what the kernel
// can actually read RIGHT NOW — a deleted/hallucinated path 404s and the <img> onerror hides the thumb
// (event-based; no stale placeholders). Web dashboard only: the VS Code webview sandbox can't reach the
// kernel origin from an <img>, so callers gate on canPreview() and keep the plain click-to-open link.

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

// The kernel serves the bytes; sid lets it resolve a relative path against THAT session's cwd
// (same resolution as click-to-open — kernel _resolve_open_path).
export function fileUrl(path: string, sid?: string | null): string {
  return "/file?path=" + encodeURIComponent(path) + (sid ? "&sid=" + encodeURIComponent(sid) : "");
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

// A thumbnail element for `path`: an <img> that REMOVES ITSELF if the kernel can't serve the file
// (404/413 → onerror), so a mentioned-but-missing path costs nothing. Click opens the lightbox.
// PDFs get a labeled doc-chip instead of pixels (no server-side rendering); same click behavior.
export function previewThumb(path: string, sid?: string | null): HTMLElement | null {
  const kind = previewKind(path);
  if (!kind || !canPreview()) return null;
  const box = document.createElement("span");
  box.className = "path-thumb";
  box.title = "click to preview " + path;
  if (kind === "pdf") {
    box.classList.add("pdf");
    const tag = document.createElement("span");
    tag.className = "path-thumb-tag";
    tag.textContent = "PDF";
    const nm = document.createElement("span");
    nm.className = "path-thumb-name";
    nm.textContent = path.slice(path.lastIndexOf("/") + 1);
    box.append(tag, nm);
    // a chip can't self-verify like an <img> — probe so a missing PDF never shows a dead chip
    fetch(fileUrl(path, sid), { method: "HEAD" }).then((r) => { if (!r.ok) box.remove(); }).catch(() => box.remove());
  } else {
    const img = document.createElement("img");
    img.className = "path-thumb-img";
    img.src = fileUrl(path, sid);
    img.alt = path;
    img.loading = "lazy";
    img.onerror = () => box.remove();
    box.appendChild(img);
  }
  box.onclick = (ev) => { ev.stopPropagation(); openLightbox(path, sid); };
  return box;
}

// FULL-SIZE inline render for a mentioned image in the CHAT (the user 2026-07-20: "not even a
// thumbnail — a rendered image, like the user messages"). Same self-verification as previewThumb —
// a path the kernel can't serve removes itself — and an image click still opens the lightbox. Images
// render at the user-image scale (.path-full-img mirrors .user-img's 320px cap, one size per
// information type). A PDF is a labeled CARD, not an auto-loading inline viewer (click → lightbox):
// the first cut embedded an <iframe> per mentioned PDF, and a browser set to "Download PDFs" (or one
// that declines to render inline) saved a FRESH COPY on every chat re-render — the user's Downloads
// folder silently filled with datasheet copies (2026-07-20). A fetch must be user-initiated, once.
// Web only — callers gate on canPreview and fall back per surface. The feed's artifact strips
// deliberately KEEP previewThumb: cards stay glanceable, the chat is where the full render lives.
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
    img.src = fileUrl(path, sid);
    img.alt = path;
    img.loading = "lazy";
    img.onerror = () => box.remove();
    img.onclick = (ev) => { ev.stopPropagation(); openLightbox(path, sid); };
    box.appendChild(img);
  }
  return box;
}
