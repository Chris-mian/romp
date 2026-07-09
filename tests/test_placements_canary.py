#!/usr/bin/env python3
"""Segment-identity canary (the user 2026-07-09, the cleared-cards-reappear regression).

Placement keys are `fsid:t:texthash`. If ANY deployed change shifts the derivation (em.segments'
atom-text reconstruction, the hash input, _seg_key normalization), every placement recorded under the
old derivation stops matching, and the planner replays dormant history as junk cards — cleared work
pops back onto the feed with old timestamps. That is exactly what happened on 07-07/07-08: a segment-
text change stepped the hash without a PLACEMENTS_V bump, and each kernel restart re-minted cards the
user had already cleared.

This canary pins the derived seg ids for a fixed synthetic transcript. If it fails, the derivation
changed: bump jd.PLACEMENTS_V (sealing every v1 store's ready-unplaced history at the next pass) and
update these pins IN THE SAME commit. See the PLACEMENTS_V comment in bin/romp-judge for the deploy
rule. Synthetic fixtures only."""
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
jd = SourceFileLoader("romp_judge_canary", os.path.join(BIN, "romp-judge")).load_module()
em = SourceFileLoader("romp_em_canary", os.path.join(BIN, "romp-event-model")).load_module()

SID = "11111111-2222-3333-4444-555555555555"
T0 = 1780000000


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def uline(t, text, uuid, parent=None):
    return {"type": "user", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "message": {"role": "user", "content": text}, "promptSource": "typed"}


def aline(t, text, uuid, parent):
    return {"type": "assistant", "timestamp": iso(t), "uuid": uuid, "parentUuid": parent,
            "message": {"role": "assistant", "content": [{"type": "text", "text": text}],
                        "stop_reason": "end_turn"}}


# One transcript, three segment flavors: a plain typed ask, a romp-injected goal nudge (marker-bearing
# text exercises the authorship/marker-sensitive path), and a follow-up typed ask.
RECORDS = [
    uline(T0, "please add a dark-mode toggle to the settings page", "u1"),
    aline(T0 + 60, "Added the toggle and wired the persistence.", "a1", "u1"),
    uline(T0 + 120, "<!-- romp-injected -->[romp] Status check: is goal g3 finished? <!-- romp-goal-id: g3 -->",
          "u2", "a1"),
    aline(T0 + 180, "Yes, g3 is finished.", "a2", "u2"),
    uline(T0 + 240, "now rename the exported CSV columns to snake_case", "u3", "a2"),
    aline(T0 + 300, "Renamed the columns and updated the importer tests.", "a3", "u3"),
]

# The pinned derivation, recorded under PLACEMENTS_V = 2 (2026-07-09).
EXPECTED_SEG_IDS = [
    SID + ":1780000000:ca8d36fd",
    SID + ":1780000120:f03c5f4f",
    SID + ":1780000240:686c9d66",
]


class PlacementIdentityCanary(unittest.TestCase):
    def test_seg_id_derivation_is_pinned_to_placements_v(self):
        with tempfile.TemporaryDirectory() as td:
            tp = Path(td) / (SID + ".jsonl")
            tp.write_text("\n".join(json.dumps(r) for r in RECORDS) + "\n")
            sess = jd.parsed_session(SID, [str(tp)], T0 + 4000)
        ids = [seg["id"] for turn in sess["turns"] for seg in em.segments(turn)]
        self.assertEqual(
            ids, EXPECTED_SEG_IDS,
            "\n\nSegment-id derivation CHANGED. Stored placements no longer match, so dormant sessions"
            "\nwill replay their history as junk cards (the 2026-07-09 cleared-cards-reappear bug)."
            "\nIn THIS commit: bump jd.PLACEMENTS_V (seals v(n-1) stores' ready-unplaced units at the"
            "\nnext pass) and re-pin EXPECTED_SEG_IDS to the new derivation. Current PLACEMENTS_V=%d."
            % jd.PLACEMENTS_V)

    def test_placements_v_is_current(self):
        # The pins above were recorded under this version; a bump without re-pinning (or re-pinning
        # without a bump) should both fail loudly.
        self.assertEqual(jd.PLACEMENTS_V, 2, "EXPECTED_SEG_IDS was pinned under PLACEMENTS_V=2 — "
                         "re-pin the ids and this version together, in the same commit")


if __name__ == "__main__":
    unittest.main(verbosity=2)
