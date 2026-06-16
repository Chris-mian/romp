// THE source of truth for the webview <body> skeletons — the container elements
// that decide WHAT each view renders. Consumed directly by the VS Code extension
// (buildHtml / buildFeedHtml in extension.ts).
//
// The web front end is the Python kernel (bin/romp-kernel), which carries a
// hand-PORTED copy of these bodies (grep its "ported from page-skeleton.chatBody"
// note). They are NOT auto-shared — if you add or rename a container here, mirror
// it in bin/romp-kernel by hand or the web view drifts from VS Code.
//
// Each host owns its own <head> (VS Code: a CSP meta + nonce; the browser: the
// --vscode-* theme vars) and its own trailing <script> tags (VS Code:
// asWebviewUri + nonce; the browser: an acquireVsCodeApi() shim + /dist/*). Only
// the body — the part that defines the UI — lives here. (render.ts/feed.ts already
// compile to one shared bundle each; this is the HTML that hosts those bundles.)

// Chat view: window frame, tab bar, ledger, transcript, the live-ask picker, and
// the footer (statusline + composer). The composer's attach-button tooltip is the
// one genuinely host-specific bit — VS Code intercepts drag-and-drop, a browser
// doesn't — so it's passed in.
export function chatBody(attachTitle: string): string {
  return `  <div id="winframe"></div>
  <div id="tabbar"><span id="tabs"></span></div>
  <div id="ledger" style="display:none"></div>
  <div id="content"></div>
  <div id="live-ask" style="display:none"></div>
  <div id="footer">
    <div id="statusline" class="statusline"></div>
    <div id="composer"><textarea id="composer-input" rows="1" placeholder="Message this session…  (⏎ send · ⇧⏎ newline)"></textarea><button id="composer-attach" title="${attachTitle}" aria-label="Attach file">📎</button></div>
  </div>`;
}

// The composer attach tooltip per host (drag-and-drop is intercepted only in VS Code).
export const ATTACH_TITLE_VSCODE = "Attach a file — inserts its path (drag-and-drop is intercepted by VS Code; use this or paste instead)";
export const ATTACH_TITLE_WEB = "Attach a file — inserts its path";

// Feed view: the (now hidden) head bar + the column/card list (feed.js builds the
// three state columns and their header chips inside #feed-list at runtime).
export const FEED_BODY = `  <div id="feed-head"></div>
  <div id="feed-list"></div>`;
