// The kernel base URL a romp WEBVIEW fetches directly (the model pickers' /models, the gear's /palette
// and /version, the strip's /usage). A webview's script runs on the CLIENT: when VS Code is connected
// to a remote machine, `http://127.0.0.1:<kernel port>` names the client's own loopback, where no kernel
// listens. VS Code's answer is `env.asExternalUri`: for an http(s) uri it "automatically establishes a
// port forwarding tunnel from the local machine to `target` on the remote and returns a local uri to
// the tunnel", and is a no-op when the extension runs on the client — so the same call gives the right
// base on both hosts. A webview `portMapping` for the port is declared as well (extension.ts
// kernelPortMapping), but it did not carry a webview's fetch over Remote-SSH on its own (the kernel's
// /perf counters showed zero GET /models across an hour of use with the mapping in place, 2026-09-22),
// and the API docs say not to rely on a cached resolution: the tunnel can be closed by the user, so the
// base is re-resolved every time a webview's HTML is built.
//
// Pure and injectable: the resolver takes the `asExternalUri` function and a uri constructor, so the
// unit tests drive it with fakes and the extension hands it `vscode.env.asExternalUri` / `vscode.Uri.parse`.

export type Stringable = { toString(): string };
export type AsExternalUri = (target: Stringable) => Thenable<Stringable>;

// The loopback base the extension host itself uses (node-side fetches with the serve token).
export function loopbackKernelBase(host: string, port: number): string {
  return `http://${host}:${port}`;
}

// The ORIGIN of a resolved uri — scheme://host[:port], no path, no trailing slash — which is what
// media.ts kernelUrl prepends to a route and what a CSP connect-src token names. A resolution that
// is not http(s) (an unexpected scheme from a host we do not know) falls back to the loopback base:
// a wrong base fails exactly like today, a thrown parse would take the whole pane down.
export function originOf(resolved: string, fallback: string): string {
  try {
    const u = new URL(String(resolved));
    if (u.protocol !== "http:" && u.protocol !== "https:") return fallback;
    return u.origin;
  } catch {
    return fallback;
  }
}

// Resolve the base a webview should fetch: the loopback base handed through `asExternalUri`, reduced
// to its origin. A resolver that throws (no remote authority yet, a tunnel refused) yields the
// loopback base — the local case's right answer, and the remote case's honest one (the fetch fails
// as it did before, and the pane's own "no list yet" wording says so).
export async function externalKernelBase(asExternalUri: AsExternalUri, uriOf: (s: string) => Stringable,
                                         host: string, port: number): Promise<string> {
  const local = loopbackKernelBase(host, port);
  try {
    const resolved = await asExternalUri(uriOf(local + "/"));
    return originOf(resolved.toString(), local);
  } catch {
    return local;
  }
}
