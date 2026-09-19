// The notice FACE's shared parts (plans/notice-cards.md; the manager's review of PR 1890, low e): the body through the one
// sanitizer and the attachment as the pinned picture where the page can reach the kernel, else its name. One module for the
// feed card, the card's modal and the chat's approval box, so the two surfaces show one face. A plain markdown renderer of its
// own: the chat's markdown module carries the math grammar and KaTeX, which the feed bundle must not (feed-bundle pins); a
// notice body is prose, code and links. Should the sanitizer itself fail (no DOM to build it on, as in a document stand-in),
// the body falls to PLAIN TEXT: nothing unsanitized ever reaches the page, and the row still says its words.
import { Marked } from "marked";
import { sanitizeMd } from "./md-sanitize";
import { stripRemoteLoads } from "./file-preview";
import { canPreview, fileUrl } from "./preview";

export interface NoticeAttachment { path: string; kind?: string; allowed?: boolean; why?: string; pin?: string | null }

const noticeMarked = new Marked({ gfm: true, breaks: true });
export function noticeBodyNodes(md: string): Node[] {
  try {
    const clean = sanitizeMd(noticeMarked.parse(md) as string);
    stripRemoteLoads(clean, (typeof window !== "undefined" && window.location ? window.location.origin : ""), "");
    return Array.from(clean.childNodes);
  } catch (e) {
    return [document.createTextNode(md)];
  }
}

/** The attachment's nodes: the pinned picture (an allowed image on a page that can reach the kernel's file route), else the
 *  file's name; nothing for no attachment or a refused one. The class names are the feed card's (fask-nimg, fask-nfile). */
export function noticeAttachmentNodes(att: NoticeAttachment | null | undefined, sid: string): HTMLElement[] {
  if (!att || !att.allowed) return [];
  let canPrev = false;
  try { canPrev = canPreview(); } catch (e) { canPrev = false; }   // no location (a document stand-in): no fetch, the file's name instead
  if (att.kind === "image" && canPrev) {
    const img = document.createElement("img"); img.className = "fask-nimg";
    img.src = fileUrl(att.path, sid) + (att.pin ? "&pin=" + encodeURIComponent(att.pin) : "");
    img.alt = att.path.split("/").pop() || "attachment"; img.title = att.path;
    return [img];
  }
  const f = document.createElement("span"); f.className = "fask-nfile";
  f.textContent = att.path.split("/").pop() || att.path; f.title = att.path + " (" + (att.kind || "file") + ")";
  return [f];
}
