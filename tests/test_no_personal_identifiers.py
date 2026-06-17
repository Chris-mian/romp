"""No repo file may contain personal identifiers from THIS machine.

Recorded session data (prompts, transcripts, summaries, mail) lives under
~/.local/state/romp/ and ~/.claude/ — never in the repo. Test fixtures must be
synthetic: invented prompts, placeholder UUIDs, hostname TESTHOST. This test
is the backstop for that rule: it scans every tracked AND untracked
(non-ignored) file for the local hostname, the local home directory, and any
extra strings listed one per line (case-insensitive, # comments) in
${XDG_CONFIG_HOME:-~/.config}/romp/private-strings.txt — so it catches each
contributor's own identifiers on their own machine without ever embedding
anyone's identifiers here.
"""
import os
import socket
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def repo_files():
    files = []
    for args in (["git", "ls-files"],
                 ["git", "ls-files", "--others", "--exclude-standard"]):
        out = subprocess.run(args, cwd=REPO, capture_output=True, text=True)
        if out.returncode == 0:
            files += out.stdout.splitlines()
    return files


def banned_strings():
    banned = []
    host = socket.gethostname().split(".")[0]
    if len(host) >= 4:  # degenerate short hostnames would false-positive
        banned.append(host)
    home = os.path.expanduser("~")
    if home.startswith(("/Users/", "/home/")):
        banned.append(home)
    cfg = Path(os.environ.get("XDG_CONFIG_HOME",
                              os.path.expanduser("~/.config")))
    cfg = cfg / "romp" / "private-strings.txt"
    if cfg.is_file():
        banned += [line.strip() for line in cfg.read_text().splitlines()
                   if line.strip() and not line.startswith("#")]
    return banned


class NoPersonalIdentifiers(unittest.TestCase):
    def test_repo_files_clean(self):
        banned = [b.lower() for b in banned_strings()]
        hits = []
        for rel in repo_files():
            path = REPO / rel
            # A committed symlink stores its TARGET as content; read_text()
            # would FOLLOW the link (the target's bytes, or IsADirectoryError /
            # a loop error), so the target STRING — which may embed a home path
            # or username — is never scanned. Check the link target explicitly.
            if path.is_symlink():
                target = os.readlink(path).lower()
                hits += ["%s: symlink target contains %r" % (rel, b)
                         for b in banned if b in target]
                continue
            try:
                text = path.read_text(encoding="utf-8").lower()
            except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError,
                    OSError):
                continue
            hits += ["%s: contains %r" % (rel, b) for b in banned if b in text]
        self.assertEqual(
            hits, [],
            "\n".join(["personal identifiers found in repo files — replace "
                       "with synthetic data (see tests/fixtures/ and "
                       "CLAUDE.md):"] + hits))


if __name__ == "__main__":
    unittest.main()
