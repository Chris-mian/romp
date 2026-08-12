#!/usr/bin/env python3
"""_ask_fill_chosen: structured AskUserQuestion answers for the chat's "answered Claude's question"
box. The tool_result records answers as `"<q>"="<a>"` pairs; we fill each block's `chosen` from them,
handling single/multi question, multiSelect (joined 'A, B, C'), and free-text 'Other'. Synthetic only."""
import os
from importlib.machinery import SourceFileLoader
import tempfile

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "bin")
# Hermetic state BEFORE the loads — they resolve their state root at import time, and only
# pytest runs conftest's floor (a bare unittest or script run otherwise writes REAL state).
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp()
os.environ.pop("ROMP_STATE_DIR", None)  # a live kernel's export outranks the XDG floor
SourceFileLoader("romp_event_model", os.path.join(BIN, "romp-event-model")).load_module()
SourceFileLoader("romp_judge", os.path.join(BIN, "romp-judge")).load_module()
os.environ["ROMP_KERNEL_NO_OPEN"] = "1"
km = SourceFileLoader("romp_kernel_aa", os.path.join(BIN, "romp-kernel")).load_module()


def _blk(q, multi=False, header=None):
    return {"question": q, "header": header, "multiSelect": multi, "options": [], "chosen": []}


def test_single_question_picked_option():
    b = [_blk("Pick a color")]
    km._ask_fill_chosen(b, 'Your questions have been answered: "Pick a color"="Blue"')
    assert b[0]["chosen"] == ["Blue"]


def test_free_text_other_is_kept_verbatim_not_split():
    b = [_blk("Pick a color")]
    km._ask_fill_chosen(b, '"Pick a color"="chartreuse, actually"')
    assert b[0]["chosen"] == ["chartreuse, actually"], "single-select free-text is one value, commas and all"


def test_multiselect_splits_joined_labels():
    b = [_blk("Pick features", multi=True)]
    km._ask_fill_chosen(b, '"Pick features"="Alpha, Beta, Gamma"')
    assert b[0]["chosen"] == ["Alpha", "Beta", "Gamma"]


def test_multi_question_matches_by_question():
    b = [_blk("First?"), _blk("Second?")]
    km._ask_fill_chosen(b, '"First?"="yes" "Second?"="no"')
    assert b[0]["chosen"] == ["yes"] and b[1]["chosen"] == ["no"]


def test_unanswered_stays_empty():
    b = [_blk("Pending?")]
    km._ask_fill_chosen(b, "")
    assert b[0]["chosen"] == []
