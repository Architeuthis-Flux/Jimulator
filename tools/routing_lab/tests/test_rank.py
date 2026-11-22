# SPDX-License-Identifier: MIT
"""The ranking: what the router loses without a wire. The sums are tested on
results made by hand; one test runs the real router with three wires gone."""
import collections
import json
import unittest
from unittest import mock

import arrangement
import cases
import ceiling
import copper
import lab
import rank
import runner
import variants
from cases import fabric_v5
from tests.test_ceiling import TINY, dense, tiny_paint
from tests.test_solver import NEEDS_SOLVER, ONE_LANE

V = None


def setUpModule():
    global V
    V = variants.resolve("worktree")


def results(routed):
    """Results by hand: {case: primaries routed}, each of 3 primaries."""
    return [dict(runner._result(cases.Case(n, "x", [(1, 8, -1)]), "ok", metrics={"primaries": 3, "routed_primaries": k, "crosspoints": 2 * k}), b="")
            for n, k in routed.items()]


class Wires(unittest.TestCase):
    def test_v5_has_ninety_four(self):
        kinds = collections.Counter(w["kind"] for w in rank.wires(arrangement.V5))
        self.assertEqual(kinds, {"lane": 48, "sf lane": 32, "bounce": 8, "hub": 6})
        self.assertEqual(len({w["wire"] for w in rank.wires(arrangement.V5)}), 94)
        self.assertEqual(len(rank.wires(arrangement.parse("t", {"base": "v5", "remove": ["KL"]}))), 93)
        self.assertEqual(sorted(rank.without(arrangement.V5, "KL").taken), [("K", "X", 12), ("L", "X", 14)])

    def test_they_come_by_kind_then_name_and_no_node_is_among_them(self):
        listed = rank.wires(arrangement.V5)
        self.assertEqual([w["kind"] for w in listed], ["lane"] * 48 + ["sf lane"] * 32 + ["bounce"] * 8 + ["hub"] * 6)
        self.assertEqual([w["wire"] for w in listed[-6:]], ["IJ", "IK", "IL", "JK", "JL", "KL"])
        self.assertEqual(listed[48]["pins"], [("A", "X", 0), ("I", "Y", 0)])              # AI
        self.assertFalse({w["wire"] for w in listed} & set(arrangement.V5.NODE_NET.values()))
        self.assertEqual({w["wire"] for w in listed if w["kind"] == "bounce"}, set(copper.BOUNCE))
        on_rails = {w["wire"] for w in rank.wires(arrangement.load("v6_rails_on_chips"))}
        self.assertEqual(len(on_rails), 94 - 12)                                           # the twelve lanes given to the rails
        self.assertFalse({"TOP_RAIL", "GND", "/AD1"} & on_rails)

    def test_an_arrangement_without_wires_is_one_a_file_could_say(self):
        off = arrangement.load("v6_feed_off")
        a = rank.without(off, "KL", "IJ")
        self.assertEqual((a.name, a.feed, len(a.taken)), ("v6_feed_off without KL, IJ", False, 4))
        self.assertEqual(arrangement.check(json.loads(json.dumps(a.data))), [])
        again = arrangement.parse("again", a.data)
        self.assertEqual((again.X_NET, again.Y_NET, again.feed), (a.X_NET, a.Y_NET, a.feed))
        self.assertEqual(len(rank.without(a, "/AB0").taken), 6)                             # and one more from that
        self.assertEqual(len(rank.wires(a)), 92)
        with self.assertRaises(ValueError) as cm:
            rank.without(off, "NO_SUCH")
        self.assertIn("NO_SUCH", str(cm.exception))
        added = rank.without(arrangement.load("v6_rails_on_chips"), "/AB0")                # from one that moves pins, too
        self.assertEqual((len(added.changed), len(added.taken)), (26, 2))


class Removal(unittest.TestCase):
    def test_loss_is_signed(self):                                      # Review Focus 6
        runs = {"v5": {"a": 3, "b": 2}, "v5 without KL": {"a": 3, "b": 3}, "v5 without AK": {"a": 1, "b": 2}}
        seen = []
        with mock.patch.object(runner, "run_battery", side_effect=lambda v, cs, **kw: results(runs[kw["arrangement"].name])):
            r = rank.removal(V, [cases.Case(n, "x", [(1, 8, -1)]) for n in "ab"], arrangement.V5, wires=["KL", "AK"],
                             progress=lambda done, of, wire: seen.append((done, of, wire)))
        by = {w["wire"]: w for w in r["wires"]}
        self.assertEqual((r["baseline"]["primaries"], r["baseline"]["fully_routed"]), (5, 1))
        self.assertEqual((by["KL"]["loss"]["primaries"], by["KL"]["loss"]["fully_routed"], by["KL"]["better"], by["KL"]["worse"]),
                         (-1, -1, ["b"], []))                           # the router does better without it: a gain, not zero
        self.assertEqual((by["AK"]["loss"]["primaries"], by["AK"]["loss"]["fully_routed"], by["AK"]["worse"]), (2, 1, ["a"]))
        self.assertEqual((by["AK"]["loss"]["crosspoints"], by["KL"]["loss"]["crosspoints"]), (-4, 2))    # after minus before
        self.assertEqual(by["AK"]["by_class"], {"x": by["AK"]["loss"]})
        self.assertEqual((by["AK"]["kind"], by["KL"]["kind"], by["KL"]["pins"]), ("sf lane", "hub", [("K", "X", 12), ("L", "X", 14)]))
        self.assertEqual((r["engine"], r["arrangement"], r["feed"]), ("router", "v5", True))
        self.assertEqual((r["cases"], r["variant"]), (2, {"name": V.name, "hash": V.hash}))
        self.assertEqual(seen, [(1, 2, "KL"), (2, 2, "AK")])
        json.dumps(r)                                                   # it is written to a file as it is

    def test_only_a_wire_that_can_be_ranked(self):
        with mock.patch.object(runner, "run_battery", side_effect=AssertionError("ran")):
            with self.assertRaises(ValueError) as cm:
                rank.removal(V, [], arrangement.V5, wires=["GND"])
        self.assertIn("GND", str(cm.exception))

    def test_on_the_real_router(self):
        off, battery = arrangement.load("v6_feed_off"), lab.battery(["dense", "real"])
        r = rank.removal(V, battery, off, wires=["KL", "AK", copper.BOUNCE[0]])
        base = runner.run_battery(V, battery, arrangement=off)
        self.assertEqual(r["baseline"]["primaries"], sum(x["metrics"]["routed_primaries"] for x in base))
        for w in r["wires"]:
            self.assertEqual(w["used_after"], 0, w["wire"])
            without = runner.run_battery(V, battery, arrangement=rank.without(off, w["wire"]))
            self.assertEqual(w["loss"]["primaries"], r["baseline"]["primaries"] - sum(x["metrics"]["routed_primaries"] for x in without))
            self.assertEqual(w["usage"], rank.usage(base)[w["wire"]])
        self.assertEqual(rank.usage(base)["AK"]["cases"],
                         sum(1 for x in base if copper.paint(x)["wires"]["AK"]["nets"]))
        self.assertGreater(rank.usage(base)["AK"]["primary"], 0)
        self.assertEqual(set(r["wires"][0]["by_class"]), {"dense", "real"})


class Need(unittest.TestCase):                                         # tiny fabrics from tests.test_ceiling
    def setUp(self):
        self.g = ceiling.graph(TINY)
        self.given = ceiling.problem(tiny_paint([(1, 3, 6, "unrouted")]), self.g)
        self.on_l0 = [["A", 0, 0, 6], ["B", 0, 0, 6]]
        self.l1 = [("A", "X", 1), ("B", "X", 1)]
        self.l0 = [("A", "X", 0), ("B", "X", 0)]

    def test_a_routing_that_never_touches_the_wire_settles_it_unasked(self):
        with mock.patch.object(ceiling, "ask", side_effect=AssertionError("asked")):
            self.assertEqual(rank.need(self.given, self.on_l0, self.l1), ("no", self.on_l0))
            self.assertEqual(rank.need(self.given, self.on_l0, [list(p) for p in self.l1]), ("no", self.on_l0))   # as a file has them

    def test_unknown_is_neither_yes_nor_no(self):                       # Review Focus 6
        for answer in ({"verdict": "unknown", "closed": []}, {"verdict": "unknown", "closed": [], "error": "the solver exited with 3"},
                       {"verdict": "not_routable", "closed": [], "error": "the solver exited with 3"},
                       {"verdict": "routable", "closed": []}):          # the last fails the lab's own check
            with mock.patch.object(ceiling, "ask", return_value=answer):
                self.assertEqual(rank.need(self.given, self.on_l0, self.l0), ("unknown", None))

    def test_the_solver_is_asked_without_the_wires_crosspoints(self):
        with mock.patch.object(ceiling, "ask", return_value={"verdict": "not_routable", "closed": []}) as asked:
            self.assertEqual(rank.need(self.given, self.on_l0, self.l0), ("yes", None))
        offered = asked.call_args.args[0]["crosspoints"]
        self.assertEqual([c for c in offered if c[3] == "L0" or c[4] == "L0"], [])
        self.assertTrue([c for c in offered if c[3] == "L1"])           # and nothing else is held back
        self.assertIs(asked.call_args.kwargs["fewest"], False)        # "is there a routing" is all that is asked
        on_l1 = [["A", 1, 0, 6], ["B", 1, 0, 6]]
        with mock.patch.object(ceiling, "ask", return_value={"verdict": "routable", "closed": on_l1}):
            self.assertEqual(rank.need(self.given, self.on_l0, self.l0), ("no", on_l1))

    @unittest.skipUnless(ceiling.solver_installed(), NEEDS_SOLVER)
    def test_with_the_real_solver(self):
        self.assertEqual(rank.need(self.given, self.on_l0, self.l0)[0], "no")           # lane L1 does as well
        one = ceiling.problem(tiny_paint([(1, 3, 6, "unrouted")], fabric=ONE_LANE), ceiling.graph(ONE_LANE))
        self.assertEqual(rank.need(one, self.on_l0, self.l0), ("yes", None))            # there is no other lane


class NeededByHand(unittest.TestCase):
    """rank.needed with the solver replaced: what is asked, and what is not."""

    def ranking(self, a, *names):
        return {"arrangement": a.name, "engine": "router", "wires": [dict(w) for w in rank.wires(a) if w["wire"] in names]}

    def test_a_routing_found_for_one_wire_settles_the_next_unasked(self):
        off, two = arrangement.load("v6_feed_off"), cases.Case("two", "x", [(1, 8, -1), (2, 9, -1)])
        paint = copper.paint(runner.run_battery(V, [two], arrangement=off)[0])
        net = {(b["n1"], b["n2"]): b["net"] for b in paint["bridges"]}
        lanes = lambda dup: {copper.wire(c["chip"], "X", c["x"]) for c in paint["crosspoints"] if bool(c["dup"]) == dup}
        self.assertEqual(lanes(False), {"/AB0", "/AB1"})                # what the router does today; the test rests on it
        self.assertIn("/AC0", lanes(True))                              # a duplicate path is not what the netlist needs
        x = lambda chip, wire: fabric_v5.X_NET[chip].index(wire)
        round_about = [["A", x("A", "/AC0"), 1, net[1, 8]], ["C", x("C", "/AC0"), 0, net[1, 8]], ["C", x("C", "/BC0"), 0, net[1, 8]],
                       ["B", x("B", "/BC0"), 1, net[1, 8]],            # 1-8 by way of chip C's bounce row,
                       ["A", x("A", "/AD0"), 2, net[2, 9]], ["D", x("D", "/AD0"), 0, net[2, 9]], ["D", x("D", "/BD0"), 0, net[2, 9]],
                       ["B", x("B", "/BD0"), 2, net[2, 9]]]            # 2-9 by way of chip D's
        seen = []
        with mock.patch.object(ceiling, "ask", return_value={"verdict": "routable", "closed": round_about}) as asked:
            r = rank.needed(V, [two], off, self.ranking(off, "/AB0", "/AB1", "KL", "/AC0"), seconds=3,
                            progress=lambda done, of, case: seen.append((done, of, case)))
        by = {w["wire"]: w for w in r["wires"]}
        # asked of /AB0 only: KL is in no routing, /AB1 is not in the one found, /AC0 is in the router's duplicates alone
        self.assertEqual(asked.call_count, 1)
        self.assertEqual([(by[n]["needed_by"], by[n]["not_needed"], by[n]["unknown"]) for n in ("/AB0", "/AB1", "KL", "/AC0")],
                         [([], 1, [])] * 4)
        self.assertEqual((r["engine"], r["rule"], r["seconds"], r["needed_cases"]), ("router and solver", "firmware", 3, 1))
        self.assertEqual(seen, [(1, 1, "two")])
        with mock.patch.object(ceiling, "ask", return_value={"verdict": "not_routable", "closed": []}) as asked:
            r = rank.needed(V, [two], off, self.ranking(off, "/AB0", "/AB1", "KL"))
        self.assertEqual([(w["wire"], w["needed_by"], w["not_needed"]) for w in r["wires"]],
                         [("/AB0", ["two"], 0), ("/AB1", ["two"], 0), ("KL", [], 1)])
        self.assertEqual(asked.call_count, 2)

    def test_a_case_with_no_routing_at_all_is_unknown_for_every_wire(self):      # Review Focus 6
        over = dense("k_rows_overflow_metric")                          # with the feed on, the router leaves a bridge of it
        with mock.patch.object(ceiling, "ask", return_value={"verdict": "unknown", "closed": []}) as asked:
            r = rank.needed(V, [over], arrangement.V5, self.ranking(arrangement.V5, "AK", "KL", "IJ"))
        self.assertEqual(asked.call_count, 1)                           # once, for a routing to start from; not once a wire
        self.assertEqual([(w["needed_by"], w["not_needed"], w["unknown"]) for w in r["wires"]],
                         [([], 0, ["k_rows_overflow_metric"])] * 3)
        self.assertEqual(r["needed_cases"], 1)
        off = arrangement.load("v6_feed_off")                           # a case with no bridge asks nothing of any wire
        with mock.patch.object(ceiling, "ask", side_effect=AssertionError("asked")):
            r = rank.needed(V, [cases.Case("none", "x", [])], off, self.ranking(off, "AK", "KL"))
        self.assertEqual((r["needed_cases"], [(w["needed_by"], w["not_needed"], w["unknown"]) for w in r["wires"]]),
                         (0, [([], 0, [])] * 2))


@unittest.skipUnless(ceiling.solver_installed(), NEEDS_SOLVER)
class Needed(unittest.TestCase):
    def test_every_lane_into_k_is_needed_when_k_is_full(self):
        off, full = arrangement.load("v6_feed_off"), [dense("k_rows_overflow_metric")]
        lanes = ["%sK" % c for c in "ABCDEFGH"]
        r = rank.needed(V, full, off, rank.removal(V, full, off, wires=lanes + ["IJ"]), seconds=20)
        by = {w["wire"]: w for w in r["wires"]}
        for lane in lanes:
            self.assertEqual((by[lane]["needed_by"], by[lane]["unknown"]), (["k_rows_overflow_metric"], []), lane)
        self.assertEqual((by["IJ"]["needed_by"], by["IJ"]["not_needed"], by["IJ"]["unknown"]), ([], 1, []))
        self.assertEqual(r["engine"], "router and solver")


if __name__ == "__main__":
    unittest.main()
