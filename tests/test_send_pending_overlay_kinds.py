"""T389: the chat's pending-send rule excludes the kernel's live overlay cards from the anchors a send may take (send-pending.ts
OVERLAY_KINDS); the kernel names those kinds in one place (kernel.py _OVERLAY_KINDS). The two lists are one list: a kind
added on either side without the other lets a send anchor on a card that sits after the queued group, and the message
draws twice until it lands (the shape the T389 lab saw). The kernel's transient live-tail keys (kernel.py
_TRANSIENT_KEY_PREFIXES, 2026-09-19) are pinned to their four mint sites, and to the gate that admits a client's key, the
same way: a prefix convention holds only while every mint, and every admission, uses one of the prefixes."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


class OverlayKindsAgree(unittest.TestCase):
    def test_the_client_anchors_rule_and_the_kernels_overlay_kinds_are_one_list(self):
        ts = open(os.path.join(ROOT, "ui", "webview", "send-pending.ts")).read()
        py = open(os.path.join(ROOT, "kernel", "kernel.py")).read()
        m_ts = re.search(r'export const OVERLAY_KINDS: ReadonlySet<string> = new Set\(\[([^\]]*)\]\);', ts)
        m_py = re.search(r'_OVERLAY_KINDS = frozenset\(\(([^)]*)\)\)', py)
        self.assertIsNotNone(m_ts, "send-pending.ts names the overlay kinds")
        self.assertIsNotNone(m_py, "kernel.py names the overlay kinds")
        ts_kinds = sorted(re.findall(r'"([a-zA-Z]+)"', m_ts.group(1)))
        py_kinds = sorted(re.findall(r'"([a-zA-Z]+)"', m_py.group(1)))
        self.assertEqual(ts_kinds, py_kinds, "one list on both sides")
        self.assertIn("apiError", ts_kinds); self.assertIn("queued", ts_kinds)
        self.assertRegex(ts, r'const stableUuid = \(e: TailEvent\): boolean => !!e\.uuid && !isOptimisticUuid\(e\.uuid\) && !isKernelEchoUuid\(e\.uuid\) && !OVERLAY_KINDS\.has\(e\.kind\);',
                         "the anchor rule reads the list")


class TransientKeysAgree(unittest.TestCase):
    """The proto-2 base's `last` skips the kernel's transient live-tail keys (kernel.py _last_anchor through _transient_key,
    2026-09-19) because each is replaced by a durable record under another key when it lands: the SDK backend's input echo
    ("echo:<hex>", minted by SdkBackend.send, or re-minted in the same form by SdkBackend._reseed_echoes at a boot for a
    mirror entry that carried no uuid), its command chip ("cmd:<t>:<name>", _ack_cmd_chip) and the Codex backend's echo
    ("echo-<hex>", CodexBackend.send). A prefix convention, not a stamp on the event, so the four mint sites are pinned to
    the tuple by source; a fifth transient key minted outside it would re-open the defect silently (its recurrence would
    read only as pusher.chatFullWhy["lastGone:<family>"] on /perf). The key SdkBackend.send takes from a client is admitted
    by kernel.py _CLIENT_QID_RE through _wire_qid, so that gate is pinned to the tuple too; the client's own echo rule
    (send-pending.ts isKernelEchoUuid, read by stableUuid beside OVERLAY_KINDS) is a consumer of the form, not what lets it
    in, and names the SDK form alone; the kernel's tuple carries that form, so the two never disagree on a key the client
    hides (the Codex form is the known gap, the client's to close). tests/test_queued_copy_identity.py drives the reseed and
    the gate behaviourally."""

    def _prefixes(self, py):
        m = re.search(r'^_TRANSIENT_KEY_PREFIXES = \(([^)]*)\)', py, re.M)
        self.assertIsNotNone(m, "kernel.py names the transient key prefixes on a line of their own")
        return re.findall(r'"([^"]+)"', m.group(1))

    def test_the_four_mint_sites_use_the_kernels_transient_prefixes(self):
        py = open(os.path.join(ROOT, "kernel", "kernel.py")).read()
        sdk = open(os.path.join(ROOT, "kernel", "sdk_backend.py")).read()
        codex = open(os.path.join(ROOT, "kernel", "codex_backend.py")).read()
        prefixes = self._prefixes(py)
        self.assertEqual(prefixes, ["echo:", "echo-", "cmd:"])
        self.assertIn('key = qid or "echo:" + uuid.uuid4().hex', sdk, "SdkBackend.send mints the echo key in the echo: form")
        self.assertIn('key = e["uuid"] if kept else "echo:" + uuid.uuid4().hex', sdk,
                      "SdkBackend._reseed_echoes keeps a mirrored echo: key or re-mints one in the same form (the fourth mint)")
        self.assertIn('uid = "cmd:%d:%s" % (t, command.lstrip("/"))', sdk, "_ack_cmd_chip mints the chip's key in the cmd: form")
        self.assertIn('echo_uuid = "echo-%s" % uuidlib.uuid4().hex[:8]', codex, "CodexBackend.send mints its echo in the echo- form")
        self.assertRegex(py, r'if e\.get\("kind"\) in _OVERLAY_KINDS or _transient_key\(_event_key\(e\)\):',
                         "_last_anchor skips a transient key the way it skips an overlay card")
        self.assertIn('"uuid": "cmdg:%d:%d"', py, "the chip's durable twin is keyed cmdg:, which no prefix covers")
        self.assertFalse(any("cmdg:".startswith(p) for p in prefixes), "the durable note is not transient")

    def test_the_clients_echo_prefix_is_one_of_the_kernels(self):
        ts = open(os.path.join(ROOT, "ui", "webview", "send-pending.ts")).read()
        py = open(os.path.join(ROOT, "kernel", "kernel.py")).read()
        m = re.search(r'export const isKernelEchoUuid = \(u\?: string\): boolean => !!u && u\.startsWith\("([^"]+)"\);', ts)
        self.assertIsNotNone(m, "send-pending.ts names the kernel echo prefix it hides")
        self.assertIn(m.group(1), self._prefixes(py))
        # the admission gate, not the consumer: the id a page sends reaches SdkBackend.send only through _wire_qid, whose regex
        # is a literal prefix then hex; that prefix is what the rule must cover (2026-09-19 review)
        g = re.search(r'^_CLIENT_QID_RE = re\.compile\(r"\^([a-z]+:)\[0-9a-f\]', py, re.M)
        self.assertIsNotNone(g, "kernel.py admits a client's id by one regex: a literal prefix, then hex")
        self.assertIn(g.group(1), self._prefixes(py), "the key the kernel takes from a client is transient")


if __name__ == "__main__":
    unittest.main()
