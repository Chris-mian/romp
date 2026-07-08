#!/usr/bin/env python3
"""Card-first filing (the user 2026-07-08): the planner picks the CARD, not a leaf from a flat list —
open_menu returns tree (DFS) order, _menu_text renders indentation, _card_route_subs walks a deep sub
target up to its card and asks the scoped placer (place_llm) only when the card actually has open
sub-goals, with any placer failure attaching at the card; _coerce_place floors onto the newest CARD.
All fixtures SYNTHETIC."""
import os
import shutil
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

HERE = os.path.dirname(os.path.realpath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
jd = SourceFileLoader("romp_judge_cardfirst", os.path.join(BIN, "romp-judge")).load_module()

SID = "11111111-2222-3333-4444-555555555555"
NOW = 1781100000


def node(nid, text, parent=None, t=NOW - 600, done=False, **kw):
    nd = {"id": nid, "text": text, "parentId": parent, "nodeComplete": done,
          "blocked": False, "cleared": False, "trail": [], "t": t, "mt": t}
    nd.update(kw)
    return nd


def store(*nodes):
    return {"rompUuid": SID, "seq": len(nodes), "placements": {}, "status": {},
            "nodes": {nd["id"]: nd for nd in nodes}}


def gid(n):
    return "%s:g%d" % (SID, n)


class MenuTreeOrder(unittest.TestCase):
    """open_menu groups each card's open subtree under it depth-first (cards oldest-first), so the
    planner sees structure instead of a flat time-ordered list."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        jd._rebind_state(Path(self.td))

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def test_dfs_groups_children_under_their_card(self):
        st = store(node(gid(1), "Card A", t=100),
                   node(gid(2), "Card B", t=200),
                   node(gid(3), "step under A", parent=gid(1), t=300),
                   node(gid(4), "sub-step of A's step", parent=gid(3), t=400))
        menu = jd.open_menu(st)
        self.assertEqual([nd["id"] for nd in menu], [gid(1), gid(3), gid(4), gid(2)],
                         "A's whole open subtree rides under A; B follows as the next card")

    def test_menu_text_indents_by_depth(self):
        st = store(node(gid(1), "Card A", t=100),
                   node(gid(2), "step", parent=gid(1), t=200),
                   node(gid(3), "deeper", parent=gid(2), t=300))
        lines = jd._menu_text(st, jd.open_menu(st)).split("\n")
        self.assertEqual(lines[0], "1. Card A")
        self.assertEqual(lines[1], "    2. step")
        self.assertEqual(lines[2], "        3. deeper")

    def test_menu_text_anchors_an_orphan_to_its_card_in_words(self):
        # a scoped list can hold a sub-goal whose card is not on it (e.g. the nudge/delegation
        # subset menus): it renders flush-left but names the card it lives inside
        st = store(node(gid(1), "Card A", t=100),
                   node(gid(2), "buried step", parent=gid(1), t=200))
        text = jd._menu_text(st, [st["nodes"][gid(2)]])
        self.assertEqual(text, "1. buried step  (inside: Card A)")


class CardRouting(unittest.TestCase):
    """_card_route_subs: subs route to the card; the placer runs only when the card has open
    sub-goals; every failure mode lands at the card."""

    def setUp(self):
        self.td = tempfile.mkdtemp()
        jd._rebind_state(Path(self.td))

    def tearDown(self):
        shutil.rmtree(self.td, ignore_errors=True)

    def _tree(self):
        return store(node(gid(1), "Card A", t=100),
                     node(gid(2), "step", parent=gid(1), t=200),
                     node(gid(3), "deeper", parent=gid(2), t=300),
                     node(gid(4), "Card B", t=400))

    def test_bare_card_sub_makes_no_placer_call(self):
        st = store(node(gid(1), "Card A", t=100), node(gid(2), "Card B", t=200))
        menu = jd.open_menu(st)
        jd.place_llm = lambda *a, **k: self.fail("placer must not be called for a card with no open sub-goals")
        ops = jd._card_route_subs(st, [{"do": "sub", "under": 2, "text": "x", "why": "w"}], menu)
        self.assertEqual(ops[0]["under"], 2, "a bare card is its own spot; one call total")

    def test_deep_target_walks_up_and_placer_picks_the_spot(self):
        st = self._tree()
        menu = jd.open_menu(st)                       # DFS: A, step, deeper, B
        calls = []
        jd.place_llm = lambda text, why, card_menu, **k: calls.append(card_menu) or '{"under": 2}'
        ops = jd._card_route_subs(st, [{"do": "sub", "under": 3, "text": "x", "why": "w"}], menu)
        self.assertEqual(ops[0]["under"], 2, "the placer's pick (#2 = step) re-points the op")
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].startswith("1. Card A"), "the scoped tree leads with the card as #1")
        self.assertNotIn("Card B", calls[0], "the placer sees only the chosen card's subtree")

    def test_placer_failure_attaches_at_the_card(self):
        st = self._tree()
        menu = jd.open_menu(st)
        jd.place_llm = lambda *a, **k: "no json here"
        ops = jd._card_route_subs(st, [{"do": "sub", "under": 3, "text": "x", "why": "w"}], menu)
        self.assertEqual(ops[0]["under"], 1, "unusable placer reply → the card itself")

    def test_placer_out_of_range_attaches_at_the_card(self):
        st = self._tree()
        menu = jd.open_menu(st)
        jd.place_llm = lambda *a, **k: '{"under": 99}'
        ops = jd._card_route_subs(st, [{"do": "sub", "under": 2, "text": "x", "why": "w"}], menu)
        self.assertEqual(ops[0]["under"], 1)

    def test_placer_false_routes_to_card_with_no_call(self):
        st = self._tree()
        menu = jd.open_menu(st)
        jd.place_llm = lambda *a, **k: self.fail("prompt/live runs never make the second call")
        ops = jd._card_route_subs(st, [{"do": "sub", "under": 3, "text": "x", "why": "w"}],
                                  menu, placer=False)
        self.assertEqual(ops[0]["under"], 1)

    def test_non_sub_ops_and_ref_subs_pass_through(self):
        st = self._tree()
        menu = jd.open_menu(st)
        jd.place_llm = lambda *a, **k: self.fail("nothing here should consult the placer")
        ops = [{"do": "mint", "text": "new", "why": "w"},
               {"do": "sub", "ref": 1, "text": "x", "why": "w"},
               {"do": "done", "goal": 2, "why": "w"}]
        routed = jd._card_route_subs(st, [dict(o) for o in ops], menu)
        self.assertEqual(routed, ops)


class CoercePlaceCard(unittest.TestCase):
    """The never-lose-a-user-message floor files under the newest CARD, not the newest leaf."""

    def test_floor_targets_newest_card(self):
        st = store(node(gid(1), "Old card", t=50),
                   node(gid(2), "New card", t=100),
                   node(gid(3), "newest node is a leaf", parent=gid(2), t=200))
        menu = jd.open_menu(st)                       # DFS: Old, New, leaf
        ops = jd._coerce_place(menu, "USER ASKED: keep me")
        self.assertEqual(ops[0]["do"], "sub")
        self.assertEqual(menu[ops[0]["under"] - 1]["id"], gid(2),
                         "the floor lands on the newest card, never chained under a leaf")

    def test_empty_board_still_mints(self):
        self.assertEqual(jd._coerce_place([], "USER ASKED: hello")[0]["do"], "mint")


class PlacePromptPins(unittest.TestCase):
    def test_depth_budget_lives_in_place_sys(self):
        self.assertIn("%d levels deep" % jd.MAX_DEPTH, jd.PLACE_SYS,
                      "the depth budget is embedded in the placer prompt, kept in sync with MAX_DEPTH")

    def test_plan_prompts_describe_the_tree_menu(self):
        for sys_prompt in (jd.PLAN_SYS, jd.PLAN_PROMPT_SYS):
            self.assertIn("top-level **card", sys_prompt,
                          "both planner runs file subs against top-level cards")


if __name__ == "__main__":
    unittest.main()
