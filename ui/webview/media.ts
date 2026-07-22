// Media asset URLs for the shared bundles. The kernel serves /media on the
// page origin (web), but a VS Code webview has a synthetic origin with no
// /media route — an absolute src there 404s (the loader's broken-image icon
// then SPINS on the rl-o animation, the user 2026-07-13). The VS Code host
// injects window.__rompMediaBase = <asWebviewUri of media/> before the bundle;
// every asset URL routes through here so both hosts resolve.
export function mediaSrc(name: string): string {
  const base = (typeof window !== "undefined" && (window as any).__rompMediaBase) || "/media";
  return `${base}/${name}`;
}

// Kernel HTTP endpoints the bundles fetch directly (/models, /palette,
// /commands, /followup-preview, /usage, ...). Same story as mediaSrc: the
// browser is served BY the kernel ('' → same-origin), but the VS Code
// webview's synthetic origin needs the host-injected base — without it these
// fetches fail silently and the features quietly vanish (the empty model
// picker, the user 2026-07-13). The kernel gates every request on the serve
// token, loopback included: the browser rides its cookie (seeded by the first
// ?token= page load), but a webview's cross-origin fetch carries no cookie, so
// the host also injects window.__rompKernelToken and it rides here as ?token=.
export function kernelUrl(path: string): string {
  const w: any = typeof window !== "undefined" ? (window as any) : {};
  const base = w.__rompKernelBase || "";
  const tok = w.__rompKernelToken || "";
  if (!tok) return `${base}${path}`;
  return `${base}${path}${path.includes("?") ? "&" : "?"}token=${encodeURIComponent(tok)}`;
}
