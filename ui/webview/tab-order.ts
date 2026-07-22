// The chat tab strip's order is the kernel's order, VERBATIM. The kernel (bin/romp-kernel `_ordered`) is the
// single source of truth and is a pure positional list — no activity / mtime / idle / status input, so it
// never reshuffles on its own. The client must not re-derive it: a tab moves ONLY when the user drags it
// (rewrites the list), a new session arrives (appends at the end), or a tab closes (drops out). NOTHING else.
//
// This is the whole ordering model, extracted so it's unit-testable. The old client kept a PARALLEL order
// (an `effIdx` + `firstSeen` tiebreaker re-sort run on every status push) that diverged from the kernel and
// made tabs jump around on ordinary activity — the bug the kernel's own tests could never catch, because
// they tested the (stable) kernel, not this client layer (the user 2026-06-27, who just wanted it stable —
// additions by subtraction).

/**
 * The render order after a kernel `tabOrder` push: adopt the kernel's order verbatim, but keep any tab the
 * client already knows that the push doesn't carry yet (a `session` push that beat its `tabOrder` push) —
 * appended at the end — so a just-arrived tab never vanishes; the next push reconciles it into place.
 * Deduped; non-string entries dropped.
 *
 * @param kernelOrder the authoritative SID order from the kernel's tabOrder push
 * @param local       the client's current order (preserves transient, not-yet-pushed tabs)
 * @param known       whether the client actually has a tab for this id (a session arrived / is a placeholder)
 */
export function reconcileTabOrder(
  kernelOrder: readonly string[],
  local: readonly string[],
  known: (id: string) => boolean,
): string[] {
  const kernel = kernelOrder.filter((id): id is string => typeof id === "string");
  const inKernel = new Set(kernel);
  const extras = local.filter((id) => typeof id === "string" && !inKernel.has(id) && known(id));
  const out: string[] = [];
  const seen = new Set<string>();
  for (const id of [...kernel, ...extras]) {
    if (!seen.has(id)) {
      seen.add(id);
      out.push(id);
    }
  }
  return out;
}
