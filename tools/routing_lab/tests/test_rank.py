# SPDX-License-Identifier: MIT
"""The ranking: what the router loses without a wire. The sums are tested on
results made by hand; one test runs the real router with three wires gone."""
import collections
import json
import unittest
from unittest import mock

import arrangement
import cases
import copper
import lab
import rank
import runner
import variants

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


if __name__ == "__main__":
    unittest.main()
