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
