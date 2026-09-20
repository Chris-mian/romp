// THE PANE PROTOCOL'S SOURCE CHECK for the shell's BUNDLES (plans/panes-as-data.md, section 5). The shell's first inline
// script defines window.__rompPaneSourceOk: a message counts only when its immediate source is a same-origin iframe of
// this document not marked data-protocol=none (a URL-source pane is a plain sandboxed iframe; a frame nested in a pane is
// not a pane). A bundle's `message` listener reads it through here and FAILS CLOSED: no check on the page, no message
// acted on; a check that throws or answers anything but true refuses too. tests/test_pane_registry.py takes the census
// of every shell listener, inline and bundled.
export function paneSourceOk(e: MessageEvent, w: Window = window): boolean {
  const f = (w as unknown as { __rompPaneSourceOk?: unknown }).__rompPaneSourceOk;
  if (typeof f !== "function") return false;
  try { return (f as (ev: MessageEvent) => unknown)(e) === true; } catch { return false; }
}
