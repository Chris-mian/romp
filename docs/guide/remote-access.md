# Self-hosted and remote access

You run Romp yourself and reach it from wherever you are, with no hosted
service in between.

The kernel runs on your machine and serves the dashboard on
`127.0.0.1:7433`, to a browser tab or the VS Code / Cursor extension.
Everything Romp stores stays local; the only external traffic is the `claude`
CLI you already use.

## More machines, one fleet

Federation is the heart of remote access: every machine runs its own kernel,
and attached machines present as a single fleet.

![One fleet across your phone, your laptop, and a remote host](../assets/guide/federation.png){ width="100%" }

Once a host is attached:

- Its sessions appear as `host:name` tabs and timeline lanes next to your
  local ones, and you drive them from the same chat.
- Its task cards share the feed, so one glance covers every machine.
- Sessions message each other across machines through the same postal
  service, so an agent on your desktop can hand work to one on the server.

Setup is one install and one click:

1. On the remote machine: clone romp and run `./install.sh`
   (`ROMP_NO_EXT=1` skips the editor extension on a headless box). Make sure
   `ssh <host>` works non-interactively.
2. In your dashboard: open the network icon in the top bar and attach the
   host.

The attach fetches the remote kernel's token over ssh, opens the tunnels, and
starts the remote kernel if it isn't running.

## Your phone

```bash
romp --serve on      # expose the kernel to your tailnet, token-gated
romp --serve off     # back to local-only
```

With [Tailscale](https://tailscale.com) on the phone, the full dashboard is
in your pocket: check the feed, answer a blocked card, start a session.
