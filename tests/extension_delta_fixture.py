"""Synthetic wire fixture from the real encoder (2026-09-16).

Regenerate with: python3 -m tests.extension_delta_fixture
The Python freshness test pins it to the sender and rendered shim; the Node pipe test
replays it without requiring a Python runtime in an editor developer's test command.
"""
import json
from pathlib import Path
from unittest import mock

from tests.test_view_deltas import _Stream, _bars, _feed, km, S1, S2, S3

FIXTURE = Path(__file__).parent / "fixtures" / "extension-view-deltas.json"


def fixture():
    km.jd.STATE.mkdir(parents=True, exist_ok=True)
    (km.jd.STATE / "session-hosts").write_text("off")
    km._delta_parts_cache.clear()

    def turns(prefix, n):
        return [{"id": "%s-%d" % (prefix, i), "t": 1000 - 60 * i, "end": 1030 - 60 * i} for i in range(n)]

    def msg(key):
        return {"id": key, "text": "synthetic message " + key}

    initial = {S1: turns("web", 2), S2: turns("api", 1)}
    grown = {S1: turns("web", 3), S2: turns("api", 1)}
    changed = {S1: turns("web", 3), S3: turns("tests", 1)}
    bare = {S1: [], S3: turns("tests", 2)}
    positional = {S1: [{"id": "", "t": 1}, {"id": "b2", "t": 2}], S3: turns("tests", 2)}
    duplicates = {S1: [{"id": "dup", "t": 1}, {"id": "dup", "t": 2}], S3: turns("tests", 2)}
    bars = [
        _bars(initial, [{"sid": S1, "judge": "closer", "t": 1, "t1": 2}], [msg("m1")]),
        _bars(grown, [{"sid": S1, "judge": "closer", "t": 1, "t1": 2}], [msg("m1")], now=1005),
        _bars(changed, [{"sid": S3, "judge": "planner", "t": 3, "t1": 4}], [msg("m2"), msg("m1")], now=1010, warming=True),
        _bars(changed, [], [msg("m2")], now=1015),
        _bars(changed, [], [msg("10"), msg("11")], now=1020),
        # Insertion order disagrees with JavaScript's index-key order: the real sender must supply order.
        _bars(changed, [], [msg("10"), msg("11"), msg("30"), msg("9")], now=1025),
        _bars(bare, [], [msg("9")], now=1030),
        _bars(positional, [], [{"id": "#1", "x": 0}, {"x": 1}], now=1035, warming=True),
        {k: v for k, v in _bars(positional, [], [{"id": "#1", "x": 0}, {"x": 5}], now=1040).items() if k != "warming"},
        _bars(duplicates, {S1: None}, [{"id": "#1", "x": 0}, {"x": 5}], now=1045),
        _bars({S1: [{"id": "dup", "t": 1}, {"id": "dup", "t": 9}], S3: turns("tests", 2)},
              {S1: []}, [{"id": "#1", "x": 0}, {"x": 5}], now=1050),
    ]
    feeds = [
        _feed([{"itemId": "a", "text": "first"}, {"itemId": "b", "text": "second"}], obsolete=True),
        _feed([{"itemId": "a", "text": "changed"}, {"itemId": "b", "text": "second"}], now=1005),
        _feed([{"itemId": "b", "text": "second"}, {"itemId": "c", "text": "third"}], now=1010),
        _feed([], now=1015),
    ]
    steps = []
    for kind, payloads in (("bars", bars), ("feed", feeds)):
        stream = _Stream(kind)
        with mock.patch.object(km, "_DELTA_MAX_FRACTION", 10.0):
            for payload in payloads:
                frames = stream.push(payload)
                assert len(frames) == 1
                steps.append({"wire": frames[0], "full": payload})
        # Exercise the normal size fallback, which resets this slot's revision to zero.
        if kind == "feed":
            payload = _feed([{"itemId": "large", "text": "synthetic card " * 40}], now=1020)
            frames = stream.push(payload)
            assert len(frames) == 1 and frames[0]["type"] == "feed"
            steps.append({"wire": frames[0], "full": payload})
    assert any("order" in r["wire"].get("coll", {}).get("messages", {}) for r in steps)
    rendered = km._shim("timeline", 1)
    begin, end = "// BEGIN VIEW DELTA DECODER:", "// END VIEW DELTA DECODER"
    a = rendered.index(begin)
    a = rendered.index("\n", a) + 1
    b = rendered.index(end, a)
    return {"kinds": {slot: spec[1] for slot, spec in km._DELTA_SLOTS.items()},
            "decoder": rendered[a:b], "steps": steps}


if __name__ == "__main__":
    FIXTURE.write_text(json.dumps(fixture(), indent=2) + "\n")
    print("wrote", FIXTURE.name)
