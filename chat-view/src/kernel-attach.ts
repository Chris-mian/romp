// kernel-attach — the ensure-then-attach decision, factored OUT of any front end so it can be unit
// tested headlessly (extension.ts can't be imported in a node test — it pulls in `vscode`).
//
// The rule (the user's 2026-06-13 ruling): a front end NEVER spawns the kernel itself. It attaches to
// a manager-owned kernel on its configured port; if none is there, it asks the `romp --on` manager to
// ENSURE one (the manager spawns + owns it), then waits for it to come up and attaches. This keeps a
// single owner (no invisible orphans, no two front ends fighting over the port) while still giving the
// "point a front end at a port and a kernel appears" UX.

export interface AttachDeps {
  // resolves true once a kernel is serving /healthz on the target port
  healthz: () => Promise<boolean>;
  // POST manager /ensure?port=N — resolves true iff the manager answered (i.e. a manager is running)
  ensureViaManager: () => Promise<boolean>;
  // await-able sleep (injected so tests run instantly)
  delay: (ms: number) => Promise<void>;
  // How long to wait for a freshly-ensured kernel to start serving. A RESTART
  // (romp --refresh) also lands here — healthz is down while the manager
  // respawns, and a cold kernel boot (reconcile + bundle check) can take well
  // over 5s — so the budget must cover a restart, not just a clean spawn
  // (the user 2026-07-13: a reload during a refresh raised the failure toast
  // even though the kernel was up seconds later).
  pollTries?: number;   // default 40
  pollMs?: number;      // default 250  → ~10s total
}

export type AttachResult =
  | { ok: true }
  | { ok: false; reason: "no-manager" }        // nothing serving the port AND no manager to ask
  | { ok: false; reason: "kernel-didnt-start" }; // manager acked but the kernel never came up (port in use?)

export async function ensureThenAttach(d: AttachDeps): Promise<AttachResult> {
  // 1. Already a kernel on our port? Attach straight away — the common case.
  if (await d.healthz()) return { ok: true };
  // 2. None there — ask the manager to ensure one. If the manager isn't running, we can't proceed.
  if (!(await d.ensureViaManager())) return { ok: false, reason: "no-manager" };
  // 3. Manager is bringing it up (or already owns it) — poll until it's serving.
  const tries = d.pollTries ?? 40;
  const ms = d.pollMs ?? 250;
  for (let i = 0; i < tries; i++) {
    await d.delay(ms);
    if (await d.healthz()) return { ok: true };
  }
  // 4. Manager answered but no kernel came up — most often the port is held by a foreign process.
  return { ok: false, reason: "kernel-didnt-start" };
}

// Should this many CONSECUTIVE failed attach rounds interrupt the user? One
// round can fail transiently (attaching in the middle of a kernel restart);
// the caller's retry loop runs another round seconds later, and only a
// PERSISTENT failure is the user's problem — a false interrupt is a broken
// flow state.
export function warnAfter(consecutiveFailures: number): boolean {
  return consecutiveFailures >= 2;
}
