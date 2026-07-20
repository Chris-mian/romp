# Peer postal buses: store-and-forward, no master, check-in trust

Status: DESIGN — awaiting the user's sign-off before implementation (approved in
principle 2026-07-20; staged build follows sign-off of this document).

## The problems this removes

Today the postal bus is a fleet-wide singleton owned by the *attaching* machine,
and cross-machine reach piggybacks on an attacher-initiated ssh:

1. **The bus dies with its owner.** The attach reverse-forwards the attacher's
   bus port onto the remote, and remote sessions dial that forwarded port as if
   it were local (remotes deliberately run no bus of their own). When the
   attacher sleeps or leaves, the remote's sessions lose postal entirely —
   including messages between two sessions on the *same* remote machine.
2. **Trust flows the wrong way for a hub.** Making the always-on server the
   attacher requires the server to hold ssh credentials into every other
   machine, including personal laptops. A compromised always-on box then owns
   everything that ever attached from it.
3. **Standalone is a special case.** A machine that is usually a "remote" has no
   bus when its link is down, so taking the laptop somewhere else silently
   breaks local messaging.
4. **Mutual attach is impossible.** Two attachers both reverse-forward their bus
   to the same fixed port on each other; the second bind fails and
   `ExitOnForwardFailure` kills the whole tunnel.

## Design in one paragraph

Every machine always runs its own bus. Buses *peer* over whatever link exists
and exchange presence and messages; a cross-host send with no live link parks in
a local per-host outbox and drains on reconnect, deduplicated by message id,
bouncing loudly if the recipient is gone by then. There is no master: a link
only ever *carries* mail, it never owns anyone's mailbox. Connectivity to a hub
is inverted into a *check-in*: the mobile machine opens one outbound ssh to the
stable machine and reverse-forwards its own kernel and bus, so the hub holds no
credentials to anyone.

Why no election: the only shared state is presence and in-flight mail. Presence
can be gossiped and honestly labeled when stale; mail needs at-least-once with
idempotent receipt. An elected master would reintroduce the single point of
failure this design exists to remove, plus split-brain on link flap. Post
offices do not elect a master; they forward, and they hold mail when the truck
cannot run.

## Pieces

### 1. Per-machine bus (stage 1)

- Every romp install ensures its own bus on the loopback postal port. The
  "no-op on remote" special case is deleted. Sessions are untouched — they dial
  the same loopback address they always have.
- Each bus carries a stable host identity (the install's host name as already
  used by dashboard federation for `host:name` ids) plus a boot epoch, so peers
  can tell a restart from a new host.
- The old attach behavior of reverse-forwarding the attacher's bus onto the
  remote at the fixed port is REMOVED in the same stage (it would collide with
  the remote's own bus). Cross-host reach moves to peering (stage 2); until
  stage 2 lands the flag keeps the old scheme selectable.

### 2. Bus peering (stage 2)

Transport: peering rides the tunnels the kernel already owns. Whenever the
kernel has a link to a peer kernel (attach today, check-in in stage 3), it also
forwards an *ephemeral local port* to the peer's bus and tells its own bus
"peer `<host>` reachable at `127.0.0.1:<port>`" — event-based, on tunnel
up/down, never polled. No fixed cross-host ports, so no bind collisions, ever.

Protocol (line-JSON over the forwarded TCP, same style as the existing bus):

- `HELLO {host, epoch}` — opens a peering exchange; a changed epoch invalidates
  cached presence for that host.
- `PRESENCE {host, agents: [...]}` — the sender's authoritative list of its own
  live sessions (name, sid, branch, working-note). Sent on HELLO, on change,
  and with each RELAY batch. Receivers store it per-host with a `seenAt`; the
  UI and `list_agents` label anything unreachable as stale ("last seen Nm ago")
  rather than dropping it silently.
- `RELAY {msg}` — one postal message for a session on the receiving host. The
  receiver delivers through its normal local path and answers `ACK {msgId}` or
  `BOUNCE {msgId, why}` (recipient not live, isolation refusal, unknown name).
- Idempotency: receivers keep a persistent window of recently-ACKed message ids
  and re-ACK duplicates without delivering. At-least-once plus dedupe is
  effectively exactly-once.

Outbox: `~/.local/state/romp/postal/outbox/<host>/` holds cross-host messages
that could not be relayed (no link, or RELAY failed). Drain triggers are
events: the kernel's "peer reachable" notification, and each new send to that
host. A drained message is removed on ACK; a BOUNCE returns to the sender as a
postal message ("could not deliver to `<name>`: <why>") — loud, never silent.

Semantics preserved:

- **Live-only at delivery.** Parking exists only for a *link* being down, never
  for a dead session. If the recipient is gone when the mail finally crosses,
  the sender gets the bounce.
- **Send-time honesty.** `send_message` to a session on an unreachable host
  succeeds as "parked for `<host>` (unreachable since `<t>`)" — the sender sees
  the parked state immediately in the tool result, and `check_sent` shows it.
- **Recall reaches the outbox.** `recall_message` deletes a still-parked
  message locally — a recall that beats the truck always wins.
- **Isolation is enforced at delivery** by the recipient's own bus, exactly as
  now; a refusal bounces and is final.

### 3. Check-in (stage 3)

`romp checkin <host>` on the mobile machine opens ONE outbound ssh to the
stable machine (same ssh option set as today's tunnels: BatchMode, keepalives,
ExitOnForwardFailure, no ControlMaster) carrying:

- `-R` ephemeral: the mobile machine's kernel port → the hub can view/drive it.
- `-R` ephemeral: the mobile machine's bus port → the hub's bus can peer.
- A handshake call to the hub kernel's `/checkin` endpoint through the same
  tunnel: `{host, kernelPort, busPort, token}` — the mobile machine *hands* its
  serve token to the hub, instead of the hub fetching it with credentials.

The hub records a checked-in host exactly like an attached remote (same
registry, same federation rows, same `host:name` sessions), marks it down when
the forward drops (event: connection death), and never initiates anything. The
mobile side supervises its own ssh (respawn on drop while checked in).

Trust consequences, stated plainly: the hub holds no way into the mobile
machine's shell, but a checked-in token does let anyone who controls the hub
view and drive the mobile machine's *romp sessions* while the check-in is up.
That is inherent in wanting the merged view from the hub. Mitigations staged
for later if wanted: per-checkin scoped tokens (view-only), and a one-tap
"check out" that kills the tunnel and invalidates the handed token.

### 3b. Spoke-to-spoke relay through a shared peer (added after the user's
### mechanics question, 2026-07-20)

Peering as specified is per-link: two machines exchange mail over a tunnel one
of them opened. Two spokes that both check in to the same hub have no direct
link — so the hub's bus RELAYS: a message addressed to a session on host C,
arriving at hub B from host A, is re-relayed by B over its own link to C, with
the same park-in-outbox behavior when B↔C is down. Rules that keep this simple
and loop-free:

- A bus relays only for hosts in its OWN live peer table (one hop; no route
  discovery, no flooding). With romp's hub-and-spoke shapes, one hop is always
  enough; a topology that needs two is a sign to check the second spoke in to
  the hub directly.
- The `ACK` is end-to-end: A keeps the message in its outbox until C's bus
  acks delivery (relayed back through B), so a hub crash mid-relay loses
  nothing — A retries, C dedupes.
- Presence gossip carries the one-hop reach too: A's `list_agents` shows C's
  sessions labeled via B ("via <hub>"), staleness compounding honestly from
  the oldest link in the chain.

### 4. What does not change

- Dashboard federation (browser-side merge, `host:` prefixing) — unchanged; it
  just gains checked-in hosts as another row source.
- The session-facing postal MCP tools keep their exact API; only the result
  strings learn the "parked" state.
- Single-machine installs: nothing observable changes at all.

## Migration

- Stage 1 ships behind `ROMP_POSTAL_PEERS=1`; default off until stage 2 passes
  its soak. With the flag off, today's singleton scheme runs untouched.
- Stage 2 flips the default on: attach stops reverse-forwarding the fixed bus
  port and starts the ephemeral peer forward. Old and new kernels must not be
  mixed across one fleet mid-migration (the `romp update <host>` p2p push
  already keeps fleet versions in step; the version-drift banner covers the
  gap).
- Stage 3 adds check-in alongside attach; attach remains for the
  hub-has-ssh-out topologies (headless boxes like jetty, where the hub holding
  ssh to a disposable box is the *right* trust direction).
- Outbox format is new state under `~/.local/state/romp/postal/`; nothing to
  migrate — the first parked message creates it.

## Testing

- Python: a two-bus harness in `tests/` — two state dirs, two buses on loopback
  ports, "tunnel" = a direct local port; covers HELLO/PRESENCE/RELAY/ACK,
  outbox park + drain + dedupe (kill the link mid-relay, reconnect, assert
  exactly-one delivery), bounce on dead recipient, recall-from-outbox,
  isolation bounce.
- bats: `romp checkin` argv/registry surface with `ROMP_SSH_BIN` stubbed (the
  existing seam), including the handshake payload and check-out.
- The no-mixed-versions rule gets a version handshake assertion in HELLO
  (refuse politely, surface a drift banner, never corrupt).

## Build order after sign-off

1. Per-machine bus + kernel→bus peer-endpoint notifications (flagged).
2. Peering protocol + outbox + dedupe + bounces + parked-state surfaces.
3. Check-in command, `/checkin` handshake, supervision, UI rows, docs
   (`docs/guide/remote-access.md` gains the laptop-anywhere story).
4. Polish: scoped tokens, check-out, phone-facing docs.
