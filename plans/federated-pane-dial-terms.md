# Federated panes dial the remote with the page's own terms

Status: design (docs). The code PR follows once this is read and gated.

A dashboard that attaches another kernel as a remote shows that kernel's sessions as tabs, and each
pane's frames ride a relay socket. Today the hub page dials the remote with almost none of the terms
its own local dial states, so on the remote kernel a hub-served pane is a term-less client: the
cold-tab diet, the active-tab gate, the skeleton shape, the provisional row and the per-client
diagnostic rows never apply to a remote session. This doc states that gap precisely, decides which
terms a federated pane must carry and how the hub page carries them, names the observable a served
lab can pin without a second machine, and records the interim lever and the risks.

The reported symptom this closes ran on exactly this road: the user's long thread, on a laptop-served
hub page over a devbox remote, showed no history and could not scroll. (The `_tail_lo` clamp fixed
separately was a latent bug, not that incident; the frame the relay delivered is the open thread.)

## 1. The premise, in code (re-verified at main 38fe13f4)

**The hub page's remote dial**, `ui/webview/federation.ts:1632`:

```
const url = `${proto}${location.host}/remote/${encodeURIComponent(host)}/ws?app=${encodeURIComponent(this.app)}`
  + (w ? `&wid=${encodeURIComponent(w)}` : "");
```

So a remote socket carries `app` and (if present) `wid`, and nothing else.

**The served page's OWN local dial**, `kernel/kernel.py:53333` (the chat shim):

```
"/ws?app=%s&delta=1&iid="+IID + (wid?"&wid="+wid:"") + (active?"&active="+active:"")
  + (reconnect?"&reconnect=1&proto="+readyProto:"") + (COL?"&col="+COL:"")
  + ((SKEL||(RESTART_DIET&&!everConnected))?"&skeleton=1":"") + (APP is the Outline pane ? "&provrows=1" : "")
```

So the local dial states `app`, `delta=1`, `iid`, `wid`, `active`, `reconnect=1&proto=<n>` (on a
redial), `col`, `skeleton=1` (a later column or the restart diet), and `provrows=1` (the Outline
pane's app). The remote dial URL omits eight of these, but `proto` is already carried to the remote
another way (the relayed `ready`, see section 3), so the real gap is seven terms: `delta`, `iid`,
`active`, `reconnect` (on a redial), `col`, `skeleton`, `provrows`.

**The splice**, `_remote_ws` at `kernel/kernel.py:63164` serves `/remote/<host>/ws`: it pops the
browser `token`, sets the remote kernel's own token, adds `relay=1` (`:63187`, PR 1699), forwards the
rest of the query verbatim and only the six WebSocket upgrade headers (not `Origin`/`User-Agent`),
then splices the two sockets byte for byte. It synthesizes none of the eight terms: whatever
`federation.ts` puts on the remote dial URL is exactly what the remote kernel's handshake reads.

**The handshake**, `_ws` at `kernel/kernel.py:63045` parses the query at `:63049` and stamps the
flags onto the client dict at `:63050`-`:63095`, then registers the client and files its open row.

## 2. What each term buys on the remote kernel

Every term below is read at the handshake (`_ws`, kernel.py) and drives a branch. A remote pane that
omits it gets the fail-safe (usually the pre-diet whole-board behaviour), which is why a remote
session never diets, never skeletons, and never renders a provisional row.

| Term | Read at | What it buys |
| --- | --- | --- |
| `app` | 63050 | which pane; gates `skeleton` (chat only) and `provrows` (Outline only); scopes the push loops |
| `wid` | 63051 | per-viewer routing: `_send_to_view` (44888) delivers tab-switch and reveal frames to one window, not a broadcast (empty wid broadcasts) |
| `iid` | 63052 | the per-page instance id: `_register_ws_client` (44580) retires any other live socket with the same iid (reconnect supersedes its own dead socket); also a field on the wsopen diag row |
| `active` | 63053 | the active session: active-tab-first build order (49473), and the one FULL session a skeleton/reconnect client gets (`_resolve_reconnect` reads it, 45688) |
| `delta=1` | 63076 | the bars/feed delta wire (`_send_slot_delta`, 45994); applies to the bars/feed slot family, not chat sessions |
| `reconnect`+`proto` | 63054, 63095 | a redial with no `ready`: the term IS the handshake (sets `handshake=True`, the chat proto); `_resolve_reconnect` (45647) holds the page's prior sessions as skeletons and serves the active tab full |
| `skeleton=1` | 63055 | the cold-tab diet: one full session frame (the active tab) plus a skeleton list and one status per other tab, instead of the whole board (~17 frames); `_send_chat_or_status` (45714) |
| `provrows=1` | 63056 | the Outline pane renders its own create-in-flight row, so the cold-tab gate may skip cold tabs (49490); without it the gate stands down and every ledger slice is built |
| `col` | 63057 | log only (45318); column focus is arbitrated client-side |

**The client kind for the diagnostic row.** `_dial_kind` (`kernel.py:44602`) sets `client["kind"]`
to `page`, `relay`, or `hub`, recorded in the wsopen row by `_note_ws_open` (`:44639`). A federated
dial already reads as `relay` because the splice injects `relay=1` (before PR 1699 the extension
host's dial, with no `Origin`/`User-Agent`, misread as relay from header absence alone). So the
remote already labels a hub pane's socket `relay`; what it cannot do is tell one hub pane from
another, because the `iid` is absent.

## 3. Decision: which terms a federated pane carries, and how

**The hub page dials each remote socket with the same terms its local dial states for that app.**
The relay forwards them unchanged (it already does), so the remote kernel's gate, diet, rows and
diagnostics then apply to a remote session exactly as to a local one. Concretely:

- **`iid`**, the pane's own instance id, namespaced so it is globally unique on the remote kernel
  (see the risk in section 6). This is the single most load-bearing term: it makes the remote's
  reconnect-supersession and its per-pane diagnostic row work.
- **`skeleton=1`**, for a chat pane that is a later column or is on the restart diet, so the remote
  diets the cold tabs. When the hub is watching a tab on ANOTHER host, this host is dialed `skeleton=1`
  with no `active`, and the kernel diets ALL its tabs (every one a skeleton, none full) so the diet
  reaches every attached host, not only the watched one. This no-active diet is scoped to the RELAY
  client (`kind == "relay"`): a LOCAL served page also dials `skeleton=1` with no active in real
  states (a reload whose blob names no tab, a fresh profile with no blob), so it keeps the fail-safe
  whole push until a served lab proves its page-side recovery (a follow-up).
- **`active`**, the pane's active session, so the remote builds that one full and skeletons the
  rest.
- **`provrows=1`**, for the Outline pane, so the remote's cold-tab gate stays on and the pane owns
  its provisional row.
- **`reconnect`** on a redial: a redial posts no `ready`, so its dial term `reconnect=1&proto=<n>`
  IS the redial's handshake, and the handshake honours a URL `proto` only inside the reconnect arm
  (kernel.py:63095). So a redial of a federated pane must carry `reconnect=1` with the proto the page
  last declared, the way the local shim's redial does.
- **`col`**, the column, carried for parity (log only today).
- **`delta=1`, `wid`**, already applicable; `wid` is already carried, `delta` should be carried for
  the bars/feed panes.

**`proto` is already carried, and is not a missing term.** The hub page tells every remote socket the
page's protocol by relaying the page's `ready`: `federation.ts:883` keeps `pageProto` from the page's
own `ready`, `:1411` re-sends `{type: "ready", proto}` to every open remote socket when the page's
`ready` fires, and `:1678` sends it on each remote socket's open. So the remote already serves the
proto-2 windowed wire to a hub chat pane on a fresh dial, and the reported incident's frame was a
proto-2 frame with a numeric tailLo. On a fresh dial proto rides that relayed `ready` (not the URL,
which the handshake ignores outside the reconnect arm); on a redial it rides the URL's
`reconnect=1&proto=<n>`, which is why `reconnect` is in the list above.

**How the hub page learns the rest.** Each is available to the page already: `wid` from
`dashboardWid()`; the `iid` is the pane's own; the active session and column are the pane's own
state. Nothing new needs to cross the relay from the remote for the hub to state these, they are the
PAGE's terms, which is the whole point.

**Stable vs mutable terms.** `app`, `wid`, `iid`, `skeleton`, `provrows` are fixed for the
life of a pane and ride the dial URL (proto rides the relayed `ready`, above). `active` and `col`
change at runtime; the local page re-stamps
`active` on a tab switch over the live socket (kernel.py:61881), so the federated pane sends the same
runtime updates over the relay socket rather than relying on the dial URL alone. The dial URL carries
the active session at open as the initial value.

**The kind.** `relay=1` is enough to classify the socket; the doc does not forward the page's kind as
a distinct `page-through-relay` value. Adding the per-pane `iid` already makes the diagnostic row
name the individual pane, which is what the missing information was; the coarse `relay` kind stays.

## 4. The observable a served lab pins (no second machine)

The federation labs already run two lab kernels on one box: a hub plus a second kernel checked in as
host `TESTHOST`, over the loopback, no ssh. The shared recipe (`tests/test_file_preview_remote_served.py`,
`tests/test_composer_placeholder_remote_served.py`, `tests/test_chat_split_host_served.py`): the
`_kernel` helper boots each hermetic kernel (`kernel_env` in `tests/test_ship_reship_served.py:169`),
a `POST /checkin?token=` records the peer, and a poll of `GET /tunnels?token=` waits for the
`TESTHOST` row to read `status==up` and `hasToken`; the browser dials the remote only then.

The pinnable observables (all read today by served or unit drivers):

- **`coldSkipped`**, the cold-tab-gate skip counter in `/perf` `builds.chat` (read by
  `tests/test_cold_boot_diet_browser.py`). This is the headline: with the terms absent it stays 0 for
  a remote session's builds (the diet never applies, tonight's boot read); with the fix it goes above
  zero on the remote kernel while the hub page holds the remote pane.
- **The skeleton set**, `#tabs .tab-skeleton` in the DOM and the `m.skeleton` array on the tab
  frame; a remote chat pane should show skeleton tabs, none today.
- **The provisional row**, `provRows` gating (`_plain_outline` vs `_flagged_outline`, kernel.py
  49490) for a remote Outline pane.
- **The wsopen diagnostic row**, `client-diag.jsonl` with `kind` and `iid`; a remote pane's row
  should name a per-pane `iid`, not the absent one that reads as an anonymous relay.

The new lab combines the two-kernel harness with a chat (and Outline) pane over the remote, a shape
no current lab has (the diet/Outline lab is single-kernel and local, the remote labs do not drive the
diet). Red first: with the remote dial stating `app`+`wid` alone, the remote kernel's `coldSkipped`
is 0 and the remote frame carries no skeleton set; with the page's terms carried, both hold.

## 5. The interim lever

The "Whole chat frames" switch is the reversible lever, held while this lands. It is a state file
`whole-chat-frames.json` seeded by `ROMP_CHAT_FLOOR0=1` at boot or toggled in the gear;
`_whole_chat_frames_on()` (kernel.py:8300) makes `_chat_floor0_of` return True (`:46731`), so every
chat tab builds from the render FLOOR at turn 0 (build_session's `floor`) instead of the assembly
document's cut. It is ON for the devbox kernel now.

Precisely what it does and does not do: it sets the build floor to turn 0, so the pre-cut region is
built eagerly rather than left as lazy pre-cut atoms above a document's cut. It does NOT force the
whole transcript onto the wire: the frame is still the tail slice of `WIRE_TAIL` (250) events with a
head gap and `headKnown` false (the pre-stage-1b shape, `head_from = max(0, total - WIRE_TAIL)` at
kernel.py:46856, independent of the floor), and the page fills the regions above it on demand. Its
measured cost is about three times per cold long-tab build. So it is a build-floor lever, not a wire
lever, and it does not carry the diet, the active-tab gate, the skeleton shape, the provisional row
or the per-pane diagnostic, those need the terms. It turns OFF (uncheck the gear; the env only seeds
when the file is absent) once this code lands and a remote pane carries `skeleton`/`active` (and
proto by the relayed ready) and can fill its own regions.

## 6. Risks

- **An `iid` minted by the hub colliding with a local page's.** On the remote kernel the `iid` is the
  reconnect-supersession key: `_register_ws_client` retires any other live socket sharing it
  (kernel.py:44580). A hub pane that dials with a bare page `iid` could collide with a local page's
  `iid` on the remote (or with another hub's), and the remote would retire a live, unrelated socket.
  So the `iid` a hub pane sends MUST be namespaced to be unique across the remote's clients, prefix
  it with the hub's own `wid` (or host identity) so a hub pane's `iid` can never equal a local page's.
  The doc requires this as part of carrying `iid`.
- **The redial path carrying stale terms.** `federation.ts` `connect(conn)` reuses the stored
  `conn.url` built once at dial time (`:1632` sets it, `connect` reads it). If the mutable terms
  (`active`, `col`) were baked into that URL, a redial would carry a stale snapshot after the user
  switched tabs. So the dial URL carries only the stable terms plus the active session AT OPEN, and a
  redial rebuilds the URL from current state (or the pane re-sends `active` over the socket on open,
  as the local page does). Either way a redial of a federated pane must carry the same terms as the
  first dial, evaluated fresh.
