// The reader's input event, read off the one the page is dispatching (window.event, which the browser sets for the
// duration of a dispatch): a handler running inside a click, a key, or a pointer or touch press or release is the
// reader's gesture; a message frame, a timer, an animation frame or a render is not. Two panes consult it (T416
// round two): the feed, so a post a render makes (a handler assignment once missing its braces posted a jump on
// every push) can never read as a jump the reader made; the chat, so the tab change it announces to the shell says
// whether the reader made it, and the feed's hover-freeze yields to the reader's own gesture and to nothing else.
export const INPUT_EVENT_TYPES: ReadonlySet<string> = new Set([
  "click", "auxclick", "dblclick", "contextmenu",
  "keydown", "keyup", "keypress",
  "pointerdown", "pointerup", "mousedown", "mouseup", "touchstart", "touchend",
]);

/** Whether `current` (window.event during a dispatch) is the reader's input. */
export function isInputEvent(current: unknown): boolean {
  if (!current || typeof current !== "object") return false;
  const type = (current as { type?: unknown }).type;
  return typeof type === "string" && INPUT_EVENT_TYPES.has(type);
}

/** The page is inside the dispatch of the reader's input event. */
export function inInputEvent(w: { event?: unknown } = window as unknown as { event?: unknown }): boolean {
  return isInputEvent(w.event);
}
