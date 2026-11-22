# SPDX-License-Identifier: MIT
"""Two arrangements scored on the same netlists. The sums are tested with a
pretend solver; one test asks the real one."""
import unittest
from unittest import mock

import arrangement
import cases
import ceiling
import edge
import runner
import score
import variants
from tests.test_ceiling import dense

NEEDS_SOLVER = "the solver is not installed: python3 tools/routing_lab/lab.py solver-setup"
V = None


def setUpModule():
    global V
    V = variants.resolve("worktree")


def fake(verdict_of):
    """ceiling.verdict replaced: verdict_of(case name, arrangement name) -> (verdict, crosspoints, proved)."""
    def answer(result, rule, seconds, use_cache=True, fewest=True, arrangement=None):
        verdict, n, proved = verdict_of(result["case"], arrangement.name if arrangement else "v5")
        return {"verdict": verdict, "crosspoints": n, "fewest_proved": proved, "closed": [], "error": None, "unplaced": [],
                "router_crosspoints": 0, "seconds": 0.0, "arrangement": arrangement.name if arrangement else "v5", "engine": "solver"}
    return mock.patch.object(ceiling, "verdict", side_effect=answer)


class Score(unittest.TestCase):
    def test_what_only_one_arrangement_fits_is_named(self):
        table = {("a_case", "v6_feed_off"): ("routable", 10, True), ("a_case", "v5"): ("not_routable", None, False),
                 ("b_case", "v6_feed_off"): ("unknown", None, False), ("b_case", "v5"): ("routable", 12, False),
                 ("c_case", "v6_feed_off"): ("routable", 8, True), ("c_case", "v5"): ("routable", 9, True)}
        three = [cases.Case(n, "x", [(1, 8, -1)]) for n in ("a_case", "b_case", "c_case")]
        seen = []
        with fake(lambda case, arr: table[case, arr]):
            s = score.compare(V, three, arrangement.load("v6_feed_off"), progress=lambda done, of, case: seen.append((done, of, case)))
        self.assertEqual((s["a"], s["b"], s["feed"], s["engine"]), ("v6_feed_off", "v5", False, "solver"))
        self.assertEqual((s["summary"]["only_a"], s["summary"]["only_b"]), (["a_case"], []))       # unknown is not "does not fit"
        self.assertEqual((s["summary"]["proved_on_both"], s["summary"]["fewest"]), (1, {"a": 8, "b": 9}))
        self.assertEqual((s["summary"]["a"]["unknown"], s["summary"]["b"]["not_routable"]), (1, 1))
        self.assertEqual((s["summary"]["cases"], s["summary"]["errors"]), (3, []))
        self.assertNotIn("closed", s["rows"][0]["a"])
        self.assertEqual(seen, [(1, 3, "a_case"), (2, 3, "b_case"), (3, 3, "c_case")])

    def test_an_answer_that_does_not_stand_is_an_error_not_a_verdict(self):
        def answer(result, rule, seconds, use_cache=True, fewest=True, arrangement=None):
            return {"verdict": "unknown", "crosspoints": None, "fewest_proved": False, "closed": [], "unplaced": [],
                    "error": "the solver died" if arrangement.name == "v5" else None}
        with mock.patch.object(ceiling, "verdict", side_effect=answer):
            s = score.compare(V, [cases.Case("c", "x", [(1, 8, -1)])], arrangement.load("v6_feed_off"))
        self.assertEqual((s["summary"]["errors"], s["summary"]["b"]["unknown"]), (["c"], 1))

    def test_both_are_asked_the_same_netlist_with_the_feed_as_the_first_has_it(self):
        seen = []
        with fake(lambda case, arr: ("routable", 2, True)), \
                mock.patch.object(runner, "run_battery", side_effect=lambda v, cs, **kw: seen.append(kw.get("arrangement")) or
                                  [dict(runner._result(c, "ok"), b="x") for c in cs]):
            score.compare(V, [cases.Case("c", "x", [(1, 8, -1)])], arrangement.load("v6_rails_on_chips"))
        self.assertEqual([(a.feed, a.changed, arrangement.blocks(a)) for a in seen], [(False, [], [])])   # V5's copper, feed off, once

    def test_the_same_random_lists_are_grown_on_both(self):
        grown = []

        def grow(binary, rng, name, seconds=20.0, longest=80, rule="firmware", arrangement=None, reasons=None):
            grown.append((rng.random(), arrangement.name, arrangement.feed))
            if arrangement.name == "v5" and len(grown) > 2:
                reasons["next_is"] = "unplaced"
                return None                                              # not one bridge proved: its first cannot be placed
            return cases.Case(name, "edge", [(1, 8, -1)]), {"bridges": 67 if arrangement.name != "v5" else 61,
                                                               "closed": [], "next_is": "unknown"}

        with mock.patch.object(edge, "grow", side_effect=grow) as grew:
            score.lengths(V, arrangement.load("v6_rails_on_chips"), lists=1, rule="copper")
            self.assertEqual({call.kwargs["rule"] for call in grew.call_args_list}, {"copper"})    # the rule asked for, not the default
            grown.clear()
            out = score.lengths(V, arrangement.load("v6_rails_on_chips"), lists=2)
        self.assertEqual([(r["list"], r["a"]["bridges"], r["b"]["bridges"]) for r in out], [(0, 67, 61), (1, 67, 0)])
        self.assertEqual((out[0]["a"]["next_is"], out[1]["b"]["next_is"]), ("unknown", "unplaced"))
        self.assertEqual(grown[0][0], grown[1][0])                       # one list, grown on both
        self.assertNotEqual(grown[0][0], grown[2][0])                    # and another list after it
        self.assertEqual({g[1:] for g in grown}, {("v6_rails_on_chips", False), ("v5", False)})    # both with the first's feed

    @unittest.skipUnless(ceiling.solver_installed(), NEEDS_SOLVER)
    def test_rails_on_every_chip_against_v5(self):
        two = [dense("rail_stacking_light"), dense("isense_loop_stacked")]
        s = score.compare(V, two, arrangement.load("v6_rails_on_chips"), seconds=20)
        by = {r["case"]: r for r in s["rows"]}
        self.assertEqual((by["rail_stacking_light"]["a"]["crosspoints"], by["rail_stacking_light"]["b"]["crosspoints"]), (6, 10))
        self.assertEqual((s["summary"]["proved_on_both"], s["summary"]["fewest"]), (2, {"a": 13, "b": 18}))


if __name__ == "__main__":
    unittest.main()
