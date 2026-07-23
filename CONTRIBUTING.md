# Contributing

Thanks for looking at romp.

**This is a personal side project.** Bug reports and pull requests are genuinely
welcome, and I'd rather hear about a problem than not. Responses may be slow, and
I may not get to everything. That's the honest expectation to set rather than
promise a turnaround I can't keep.

## Reporting a bug

Open an issue and include:

- the output of `romp --version` (it reports the working tree, the running
  kernel, and the built bundles separately, and a mismatch between them is a
  common cause of "the UI doesn't match the code")
- your OS and Python version
- what you expected and what happened

## Running the tests

```bash
python3 -m pytest -q       # the Python pipeline (kernel/, cli/, postal/)
bats tests/*.bats          # the shell surfaces (hooks, postal, manager)
cd vscode-extension && npm ci && npm test
```

The Python and shell suites are also the CI gate, across Python 3.10 to 3.13 on
Linux and macOS.

Two things about the test environment are worth knowing, because both have
produced confusing failures:

- The bats suite takes about a minute on Linux and about fifteen on macOS. That
  is expected, not a hang.
- Some tests behave differently depending on whether a `tmux` binary exists on
  the machine, because romp treats "no tmux at all" as headless and falls back
  to file-derived sessions. Tests that care now pin this explicitly; if you add
  one that calls into session liveness, pin it too rather than inheriting the
  machine's state.

## A note on what goes in the repo

romp reads real session data (prompts, transcripts, messages), and none of it
belongs in the repository. Test fixtures are synthetic: invented prompt text,
placeholder UUIDs, hostname `TESTHOST`. `tests/test_no_personal_identifiers.py`
enforces this mechanically against your own machine's identifiers, and you can
add your own strings to `~/.config/romp/private-strings.txt` (untracked, one per
line) so the check covers whatever is specific to you.

## Pull requests

`main` requires a PR with passing CI. Branch, push, open a PR, and let the checks
run. If a change fixes a bug or adds behaviour, it should land with a test that
covers it.
