// Where a click on a FILE or a FOLDER opens: one ladder, two callers (render.ts openPath for a file link,
// openBrowse for a folder), pure and DOM-free so the table runs for real in tests (file-route.test.ts,
// browse-route.test.ts). The caller reads every input at CLICK time:
//   framed     window.parent !== window: a shell exists to relay to. Standalone /chat has no shell and no
//              other pane, so everything opens in place there.
//   filesOpen  the shell's Files-pane bit (render.ts panesOn.files, cached from the shell's own broadcast):
//              the pane is ON SCREEN, a desktop column toggled on or the tab showing on a phone.
//   filesAvail the shell's word that the Files control exists (render.ts panesAvail.files, the same broadcast):
//              the gear's Files row (Settings, General, Panes) is on (off by default since T317b). Off, there is no pane to
//              bring forward, so a click that would have gone there opens here (T317).
// A verdict names the TARGET: "pane" is the Files pane (the shell brings a closed one forward; the click is
// the gesture), "here" is this document, the viewer or the file browser as a modal over the pane that was
// clicked, and "editor" (a folder in VS Code) is the host editor's own opener.

export type FileRoute = "pane" | "here";
export type BrowseRoute = FileRoute | "editor";

/** A FILE link. An OPEN Files pane takes the click: the pane being open IS the intent, and a file that opened as a modal
 *  over the chat while the pane sat there empty was the bug. Closed, the file opens HERE, over the pane that was clicked.
 *  The setting that once let a click bring a closed pane forward is gone (T404, the user 2026-09-13: the behaviour follows
 *  whether the Files pane is open); the one preference lost is a closed pane brought forward on every click. */
export function fileLinkRoute(framed: boolean, filesOpen: boolean, filesAvail: boolean = true): FileRoute {
  if (!framed) return "here";
  if (filesOpen && filesAvail) return "pane";
  return "here";
}

/** A FOLDER click (the folder shown under the chat, the system context card's Directory row, a tab menu's
 *  Browse files, a chat-hosted viewer's directory link; render.ts openBrowse) walks the SAME ladder as a
 *  file link: an open Files pane takes the listing, and otherwise the browser opens over the chat as it
 *  always has (T404: no setting names a closed pane any more). Web only: in VS Code the folder link keeps
 *  the editor's own opener (asFolderLink's openFolder act), so the ladder is never asked. */
export function browseRoute(web: boolean, framed: boolean, filesOpen: boolean, filesAvail: boolean = true): BrowseRoute {
  if (!web) return "editor";
  return fileLinkRoute(framed, filesOpen, filesAvail);
}
