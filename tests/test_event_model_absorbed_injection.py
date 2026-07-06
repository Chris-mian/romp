#!/usr/bin/env python3
"""An SDK-queued romp injection absorbed mid-turn must keep its text and markers (the user 2026-07-06).

The CLI records such an injection as: a queue-operation `enqueue` with content NULL, a queued_command
ATTACHMENT at the same timestamp whose prompt is a content-block LIST carrying the full text (romp
markers included), and a later `remove` when the prompt is spliced into the running turn. The old parse
paired enqueues to attachments by TEXT only (and keyed a list prompt by its Python repr), so the
synthesized absorbed atom came out EMPTY: no text, no author, no rompAuto — an auto-nudge became an
anonymous blank prompt (plain timeline dot instead of the romp swirl, and the planner treated the nudged
turn as ordinary work instead of resolving the goal). Now the enqueue joins the attachment written at the
SAME enqueue timestamp. All records synthetic (placeholder UUIDs)."""
import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
em = SourceFileLoader("romp_em_absorbed", os.path.join(BIN, "romp-event-model")).load_module()

SID = "11111111-2222-3333-4444-555555555555"
T0 = 1781100000
NUDGE = ("Status check on the widget goal.\n"
         "<!-- romp-injected --><!-- romp-auto --><!-- romp-goal-id: %s:g1 -->" % SID)


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def rec_user(t, text, uuid, parent):
    return {"type": "user", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "message": {"role": "user", "content": text}, "promptSource": "typed"}


def rec_asst(t, text, uuid, parent, stop="end_turn"):
    return {"type": "assistant", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}],
                        "stop_reason": stop}}


class AbsorbedSdkInjection(unittest.TestCase):
    def _parse(self, prompt_payload, enqueue_content=None):
        records = [
            rec_user(T0, "build the widget", "u1", None),
            rec_asst(T0 + 10, "working on it", "a1", "u1", stop=None),
            {"type": "queue-operation", "timestamp": iso(T0 + 20), "operation": "enqueue",
             "content": enqueue_content},
            {"type": "attachment", "timestamp": iso(T0 + 20), "uuid": "att1", "parentUuid": "a1",
             "attachment": {"type": "queued_command", "prompt": prompt_payload}},
            {"type": "queue-operation", "timestamp": iso(T0 + 25), "operation": "remove",
             "content": None},
            # the CLI chains the attachment into the parent path: the next record's parent IS the
            # attachment (verified on the live corpus) — that's how the attachment lands in `kept`
            rec_asst(T0 + 30, "done, widget shipped", "a2", "att1"),
        ]
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / (SID + ".jsonl")
            p.write_text("\n".join(json.dumps(r) for r in records) + "\n")
            return em.parse_session(str(p), rompuuid=SID, now=T0 + 3600, sdk_human=True)

    def _absorbed_atom(self, sess):
        for turn in sess["turns"]:
            for a in turn["atoms"]:
                if a.get("type") == "user" and "Status check" in (em._text_of(
                        (a.get("message") or {}).get("content") or []) or ""):
                    return a
        return None

    def test_null_content_enqueue_joins_the_same_ts_attachment(self):
        # the SDK shape: enqueue content null + block-LIST attachment prompt at the same timestamp
        sess = self._parse([{"type": "text", "text": NUDGE}], enqueue_content=None)
        atom = self._absorbed_atom(sess)
        self.assertIsNotNone(atom, "the absorbed injection synthesizes a user atom WITH its text")
        self.assertEqual(atom.get("author"), "romp", "the romp-injected marker survives → author romp")
        self.assertTrue(atom.get("rompAuto"), "the romp-auto marker survives → auto-nudge flag")
        self.assertEqual(atom.get("uuid"), "att1", "anchored on the attachment record")

    def test_string_prompt_text_pairing_unchanged(self):
        # the tmux shape: enqueue carries the text, attachment prompt is a plain string — legacy path
        sess = self._parse(NUDGE, enqueue_content=NUDGE)
        atom = self._absorbed_atom(sess)
        self.assertIsNotNone(atom)
        self.assertEqual(atom.get("author"), "romp")
        self.assertTrue(atom.get("rompAuto"), "rompAuto now stamped on absorbed atoms too (was native-only)")


if __name__ == "__main__":
    unittest.main()
