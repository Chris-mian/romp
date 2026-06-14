// Cache policy for kernel-served pages + assets. HTML pages and the dynamically-loaded bundles must
// never be cached, or a kernel restart wouldn't surface new code (an open page would keep its stale
// bundle). The Restart control itself lives in the timeline controls row (romp-timeline-view.js) and
// POSTs the kernel's same-origin /restart, which relays to the `romp on` manager's /restart-all.
export const NO_STORE: Readonly<Record<string, string>> = { "Cache-Control": "no-store" };
