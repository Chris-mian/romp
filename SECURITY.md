# Security

romp runs a local kernel and a local message bus on your machine, and drives
Claude Code sessions on your behalf. This document states the trust model it
assumes, what that means on a shared machine, and how to report a vulnerability.

## Trust model: one machine, one user

romp is designed for a **single-user machine** — your laptop or a host only you
log into. Two local services run there:

- the **kernel** (dashboard/API) on `127.0.0.1:7433`, and
- the **postal bus** (inter-session messaging) on `127.0.0.1` (a fixed local port).

Both bind **loopback only** (`127.0.0.1`); neither is exposed to your network by
default. The kernel's side-effecting routes (`/send`, `/interrupt`, `/end`,
tunnel management) and the postal bus treat **any process that can reach
loopback as authorized**. On a single-user machine that set is exactly "you and
the programs you run," which is the intended boundary.

A serve token (`~/.local/state/romp/serve-token`, mode `0600`, compared with a
constant-time check) additionally gates access when the kernel is reached
**off-box** (e.g. through a `tailscale serve` proxy or an ssh tunnel), and an
Origin/Host check protects the browser dashboard against cross-site requests.
The token is *not* required for direct loopback requests — that is the
single-user assumption above, made explicit.

## Shared / multi-user machines

On a host with **more than one human user**, the trust model above does not
hold: `127.0.0.1` is a single network stack shared by every local UID, so
another logged-in user can reach your kernel and bus. Because `/send` injects
text into a live Claude session — which then runs tools and shell commands as
you — the practical consequence is that **another local user could drive your
agents**, i.e. run code as you. The postal bus likewise lets any local process
spoof inter-session mail.

There is no per-user loopback isolation on stock Linux or macOS, so the
mitigation is **process/network isolation**, not a firewall rule:

- **Preferred:** run romp only on a machine you alone log into.
- **Linux, per-user isolation:** run romp inside a per-user **network namespace**
  (`unshare -n`), a **rootless container**, or a **VM**, so its loopback is not
  shared with other users' processes.
- **Do not** set `ROMP_SERVE_HOST` to `0.0.0.0` or a LAN address on an untrusted
  network — that exposes the kernel beyond loopback. (It requires the serve
  token, but still widens the surface; use an ssh tunnel or `tailscale serve`
  instead, which keep the listener on loopback.)

A code-level hardening — requiring the serve token even for loopback requests to
side-effecting routes, and authenticating the bus — is a natural next step for
multi-user support; it is deliberately not enabled today because local callers
(the Stop hook, the CLI, bus clients) currently rely on unauthenticated
loopback. If you need romp on a shared host, open an issue.

## What is already hardened

- **Loopback-only binds** for the kernel and bus (above).
- **Serve token** for off-box access: 144-bit random, stored `0600`, constant-time
  compare; Origin/Host gate on the dashboard.
- **Path-traversal guards** on every id/name/message-id that becomes a filesystem
  path component under the mail and outbox roots (`_safe_id`), so a crafted
  reference like `../../etc` is rejected before any path join.
- **No shell interpolation:** subprocess calls use argv lists (no `shell=True`);
  untrusted message text reaching a tmux pane goes through bracketed paste, not
  key interpretation; remote `ssh` targets are validated and argv-guarded with
  `--`.
- **Output sanitization:** model output and message content rendered in the
  dashboard/webview pass through DOMPurify; the VS Code webview runs under a
  strict nonce CSP with `localResourceRoots` limited to the extension's assets.
- **No unsafe deserialization:** no `pickle`, `eval`, `exec`, or non-safe YAML on
  untrusted data.

## Network access

romp makes one outbound request by default: it fetches a public model-pricing
table (`raw.githubusercontent.com/.../model_prices_and_context_window.json`)
every few hours to label context/cost. The response is parsed strictly as
numeric pricing. No telemetry or session data is sent anywhere.

## Reporting a vulnerability

Please report security issues privately via GitHub Security Advisories on the
repository rather than opening a public issue. Include a description, affected
version/commit, and a reproduction if you have one.
