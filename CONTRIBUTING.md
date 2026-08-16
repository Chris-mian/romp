# Contributing

Thanks for looking at Romp.

This is a personal side project. Bug reports and pull requests are
welcome, and I'd rather hear about a problem than not. Responses may be slow, and
I may not get to everything. 

If you're interested in reporting bugs and making PRs, please try to reproduce them or ground your suggestions with the latest code at the tip of the main branch rather than a tagged release version.

## Running the tests

```bash
python3 -m pytest -q       # the Python pipeline (kernel/, cli/, postal/)
bats tests/*.bats          # the shell surfaces (hooks, postal, manager)
cd vscode-extension && npm ci && npm test
```

The Python and shell suites are also the CI gate, across Python 3.10 to 3.13 on
Linux; the macOS cells run on demand from the Actions tab (they are billed even
on a public repo, so they are not part of the per-push matrix).

Three things about the test environment are worth knowing, because all have
produced confusing failures:

- The bats suite takes about a minute on Linux and about fifteen on macOS. That
  is expected, not a hang.
- Some tests behave differently depending on whether a `tmux` binary exists on
  the machine, because romp treats "no tmux at all" as headless and falls back
  to file-derived sessions. Tests that care now pin this explicitly; if you add
  one that calls into session liveness, pin it too rather than inheriting the
  machine's state.
- On macOS, run the bats suite with a modern bash (`brew install bash`; bats
  picks it up via `env bash` when `/opt/homebrew/bin` precedes `/bin` on PATH).
  The stock `/bin/bash` 3.2 does not fail a test on a mid-test `[[ ]]`
  assertion — only the last command's status counts — so a stale assertion can
  pass silently for months. Linux CI runs bash 5 and is the arbiter; two
  assertions went stale exactly this way while CI was offline.
