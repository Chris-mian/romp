// Parent-death watchdog. The `romp on` manager OWNS the kernel and stops it on a clean shutdown — but a
// manager that's SIGKILL'd, crashes, or whose terminal is closed never runs its shutdown handler, so the
// kernel is reparented to init and lingers as an orphan (the user hit exactly this, 2026-06-13). The
// kernel therefore watches its manager and exits the moment it vanishes.
//
// Cross-platform on purpose (romp targets macOS + Linux): a portable poll of process.kill(pid, 0) — the
// existence/permission probe that sends NO signal — rather than Linux-only PR_SET_PDEATHSIG. A manual
// `romp-serve` launch (no manager) passes pid 0 → no watchdog: that kernel is the user's to stop.

export function isAlive(pid: number): boolean {
  if (!pid || pid <= 0) return false;
  try {
    process.kill(pid, 0);          // signal 0 sends nothing; it just checks existence + permission
    return true;
  } catch (e: any) {
    return !!e && e.code === "EPERM";   // EPERM = process exists but isn't ours → still ALIVE; ESRCH = gone
  }
}

// Poll `pid` every `everyMs`; call `onGone` the first time it's no longer alive, then stop polling.
// Returns the timer (unref'd so the watchdog never keeps the kernel alive by itself), or null when there
// is no manager to watch (pid ≤ 0).
export function watchParent(pid: number, onGone: () => void, everyMs = 2000): NodeJS.Timeout | null {
  if (!pid || pid <= 0) return null;
  const t = setInterval(() => {
    if (!isAlive(pid)) { clearInterval(t); onGone(); }
  }, everyMs);
  if (t && typeof t.unref === "function") t.unref();
  return t;
}
