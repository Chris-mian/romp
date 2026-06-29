// The Fleet's per-session TOP-ROW selection, extracted pure so it's behaviorally testable (the render itself
// is DOM-coupled). One rule (the user 2026-06-27): a session's OPEN top tasks always show; its done/cleared
// top tasks AND the fully-completed tops the compaction sweep archived out of the live tree show ONLY when
// "Show completed" is on. Returns [] → the session has nothing to show and the caller skips it. (Completed
// SUB-nodes of an open task are a separate concern — the render already shows them, auto-collapsing a
// fully-done subtree to its top via defaultFold; this only governs which TOP rows appear.)

export interface RootNode {
  done?: boolean;
  cleared?: boolean;
}

/**
 * @param roots        the session's live top-level goal nodes (depth 0)
 * @param archivedTops fully-completed tops surfaced from the archive (kernel: _fleet_archived_tops)
 * @param showDone     the "Show completed" toggle
 */
export function fleetVisibleRoots<T extends RootNode>(roots: T[], archivedTops: T[], showDone: boolean): T[] {
  if (!showDone) return roots.filter((n) => !n.done && !n.cleared);   // open tops only — finished work stays hidden
  return roots.concat(archivedTops);                                   // all live tops + the archived-completed ones
}
