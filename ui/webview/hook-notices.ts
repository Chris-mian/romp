// A slash command that fires lifecycle hooks (e.g. /compact) echoes each one back as a hook-execution
// notice — "PreCompact [~/.claude/hooks/tmux-status.sh] completed successfully". These used to render as a
// wall of gray prose (the user 2026-06-30: "render those messages from the hooks in some way besides just
// regular text"). Parse them out so the chat can render each as a compact "⚙ Hook ✓" chip instead.
//
// The notice shape is invariant across hook events: "<HookName> [<path>] completed successfully". Kept in its
// own module so the parse is unit-tested directly (render.ts itself is a bundled webview script).

export interface HookNotice {
  evt: string;   // the hook event name, e.g. "PreCompact" / "PostCompact" / "SessionStart"
  path: string;  // the hook script path (shown on hover, not inline)
}

// Global so `.replace` and `.exec` share it; callers reset lastIndex before iterating.
const HOOK_NOTICE = /([A-Za-z][A-Za-z]+)\s+\[([^\]]+)\]\s+completed successfully/g;

// Returns the parsed notices plus whatever prose is left once they're stripped (e.g. /compact's leading
// "Compacted"), or null when the text carries no hook notice at all (a normal assistant message).
export function parseHookNotices(text: string): { notices: HookNotice[]; lead: string } | null {
  if (!text) return null;
  const notices: HookNotice[] = [];
  HOOK_NOTICE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = HOOK_NOTICE.exec(text))) notices.push({ evt: m[1], path: m[2] });
  if (!notices.length) return null;
  const lead = text.replace(HOOK_NOTICE, "").replace(/\s+/g, " ").trim();
  return { notices, lead };
}
