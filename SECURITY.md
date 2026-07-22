# Security

romp runs a local kernel and a local message bus on your machine, and drives
Claude Code sessions on your behalf. This document states the trust model it
assumes, what that means on a shared machine, and how to report a vulnerability.

## Trust model: token-gated, same-user by file permission

Two local services run on your machine:

- the **kernel** (dashboard/API) on `127.0.0.1:7433`, and
- the **postal bus** (inter-session messaging) on `127.0.0.1` (a fixed local port).

Both bind **loopback only** (`127.0.0.1`); neither is exposed to your network by
default. On top of that, **every request requires the serve token — loopback
included** (the model Jupyter uses, for the same reason: loopback is one network
stack shared by every local UID, so it cannot be a trust boundary by itself).

The token (`~/.local/state/romp/serve-token`) is 144-bit random, stored at mode
`0600`, and compared with a constant-time check — **file permissions are the
same-user gate**. Same-user clients (the CLI, hooks, the bus, the VS Code
extension) read the file and send it as an `X-Romp-Token` header; the browser
presents it once as `?token=` (print the ready-made link with `romp --url`, or
paste the token into the login page a bare open of the dashboard serves) and
rides an `HttpOnly` cookie afterwards. An Origin check additionally protects
the browser surfaces against cross-site requests, including the WebSocket
upgrade. The only token-exempt routes are the no-side-effect liveness probes:
`/healthz`, `/version`, `/busy` on the kernel and `/ping` on the bus.

The practical consequence: another local user on a **shared machine** cannot
reach your kernel or bus — `/send` (which injects text into a live Claude
session that runs tools as you) and bus mail both require a token only your
UID can read.

## Residual cautions on shared machines

- The token gate protects against other **non-root users**. Root (or the host
  operator of a container/VM) can read any file and inspect any process — no
  userspace design changes that. Don't keep long-lived credentials on hosts
  whose root you don't trust.
- **Do not** set `ROMP_SERVE_HOST` to `0.0.0.0` or a LAN address on an untrusted
  network — the token still gates every request, but it widens the surface; use
  an ssh tunnel or `tailscale serve` instead, which keep the listener on
  loopback.
- For defense-in-depth on Linux you can still run romp inside a per-user
  **network namespace** (`unshare -n`) or rootless container, so its loopback is
  not even reachable by other users' processes.

## What is already hardened

- **Loopback-only binds** for the kernel and bus (above).
- **Serve token required on every request, loopback included**: 144-bit random,
  stored `0600`, constant-time compare; Origin gate on the dashboard and the
  WS upgrade. Federated (cross-machine) calls authorize with the remote
  machine's token, carried over ssh tunnels the local machine initiates.
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
