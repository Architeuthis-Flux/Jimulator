# SPDX-License-Identifier: MIT
import unittest

import cases
import copper
import runner
import variants

BIN = None


def setUpModule():
    global BIN
    BIN = variants.build(variants.resolve("worktree"))


def bridge(p, n1, n2):
    return [x for x in p["bridges"] if (x["n1"], x["n2"]) == (n1, n2)][0]


class Copper(unittest.TestCase):
    def test_series_and_parallel(self):
        self.assertEqual(copper.effective_resistance([("a", "m"), ("m", "b")], "a", "b"), 2.0)
        two = [("a", "m"), ("m", "b"), ("a", "n"), ("n", "b")]
        self.assertAlmostEqual(copper.effective_resistance(two, "a", "b"), 1.0)
        self.assertIsNone(copper.effective_resistance([("a", "m")], "a", "b"))
        self.assertEqual(copper.effective_resistance([], "a", "a"), 0.0)
        # a branch that leads nowhere changes nothing; a bridge across the middle of a square does not either
        self.assertEqual(copper.effective_resistance([("a", "m"), ("m", "b"), ("m", "dead")], "a", "b"), 2.0)
        self.assertAlmostEqual(copper.effective_resistance(two + [("m", "n")], "a", "b"), 1.0)

    def test_wire_names_and_kinds(self):
        self.assertEqual(copper.wire("A", "X", 2), "/AB0")
        self.assertEqual(copper.wire("B", "X", 0), "/AB0")
        self.assertEqual(copper.wire("A", "Y", 1), "1")
        self.assertEqual(copper.wire("K", "Y", 0), "AK")
        self.assertEqual([copper.wire_kind(n) for n in ("1", "/AB0", "AK", "IJ", "TOP_RAIL")],
                         ["row", "lane", "lane", "hub", "special"])
        self.assertEqual(copper.wire_kind(copper.wire("A", "Y", 0)), "bounce")

    def test_ground_and_the_rails_wear_the_firmwares_colours(self):
        # as the board's own LEDs show them (LEDs.cpp, assignNetColors): ground green, a power rail red, and
        # blue while that rail is set negative; every other net keeps one of the sixteen
        def colours(power):
            case = cases.Case("t", "x", [(100, 3, 0), (101, 10, 0), (102, 40, 0), (1, 8, 0)], power=power, probe=(0, 0))
            p = copper.paint(runner.run_case(BIN, case))
            return {n["label"]: n["colour"] for n in p["nets"].values()}
        got = colours((5.0, 3.3, 0.0, 0.0))
        self.assertEqual((got["Gn"], got["T"], got["B"]), (copper.GND_COLOUR, copper.RAIL_COLOUR, copper.RAIL_COLOUR))
        self.assertIn(got["6"], copper.NET_COLOURS)
        got = colours((-3.0, 3.3, 0.0, 0.0))
        self.assertEqual((got["T"], got["B"]), (copper.RAIL_NEGATIVE_COLOUR, copper.RAIL_COLOUR))
        # a result with no word of the rails' voltages (a board's own report) is taken as positive
        self.assertEqual(copper.net_colour(2), copper.RAIL_COLOUR)

    def test_paint_of_one_direct_bridge(self):
        p = copper.paint(runner.run_case(BIN, cases.Case("t", "x", [(1, 8, 0)])))      # dup 0: one path
        b = bridge(p, 1, 8)
        self.assertEqual((b["state"], b["copies"], b["hops"], b["r"], b["infra"]), ("routed", 1, 2, 2.0, False))
        net = str(b["net"])
        self.assertEqual(p["wires"]["1"]["nets"], [b["net"]])
        self.assertEqual(p["wires"]["8"]["nets"], [b["net"]])
        self.assertEqual(len([c for c in p["crosspoints"] if c["net"] == b["net"]]), 2)
        self.assertRegex(p["nets"][net]["colour"], r"^#[0-9a-f]{6}$")
        self.assertEqual(sorted(p["nets"][net]["nodes"]), [1, 8])
        lane = [w for w in p["wires"].values() if w["kind"] == "lane" and w["nets"] == [b["net"]]][0]
        self.assertTrue(all(pin["claim"] == b["net"] for pin in lane["pins"]))          # claimed at both ends
        self.assertEqual(len(lane["pins"]), 2)
        self.assertEqual(p["status"], "ok")
        self.assertTrue([x for x in p["bridges"] if x["infra"]])                        # the probe feed is there, marked

    def test_pin_marks(self):
        marks = lambda p: {(pin["chip"], pin["axis"], pin["pin"]): pin["mark"]
                           for w in p["wires"].values() for pin in w["pins"] if pin["mark"]}
        clean = copper.paint(runner.run_case(BIN, cases.Case("t", "x", [(1, 8, 0)])))
        self.assertNotIn("mismatch", marks(clean).values())
        # a path that fails late keeps its claims (sweep finding F7): held pins, claimed with no copper
        over = [c for c in cases.dense_cases() if c.name == "k_rows_overflow_metric"][0]
        self.assertIn("held", marks(copper.paint(runner.run_case(BIN, over))).values())
        # the router's own finding: a duplicate closes A.X0 without claiming it
        import generators
        fuzz = [c for c in generators.fuzz() if c.name == "fuzz_1_1"][0]
        self.assertEqual(marks(copper.paint(runner.run_case(BIN, fuzz)))[("A", "X", 0)], "mismatch")

    def test_copies_lower_the_resistance(self):
        one = copper.paint(runner.run_case(BIN, cases.Case("t", "x", [(1, 8, 0)])))
        three = copper.paint(runner.run_case(BIN, cases.Case("t", "x", [(1, 8, 2)])))
        self.assertGreater(bridge(three, 1, 8)["copies"], 1)
        self.assertLess(bridge(three, 1, 8)["r"], bridge(one, 1, 8)["r"])
        self.assertTrue(any(c["dup"] for c in three["crosspoints"]))

    def test_states_that_are_not_routing_misses(self):
        p = copper.paint(runner.run_case(BIN, cases.Case("t", "x", [(100, 101, -1), (5, 101, -1), (5, 131, -1),
                                                                    (100, 1, -1), (102, 1, -1)])))
        state = {(b["n1"], b["n2"]): b["state"] for b in p["bridges"]}
        self.assertEqual(state[(100, 101)], "rejected")
        self.assertEqual(state[(102, 1)], "left_out")
        self.assertIn("refused", (state[(5, 101)], state[(5, 131)]))
        self.assertNotIn("unrouted", state.values())
        self.assertIsNone(bridge(p, 100, 101)["r"])

    def test_an_unrouted_bridge_is_unrouted(self):
        over = [c for c in cases.dense_cases() if c.name == "k_rows_overflow_metric"][0]
        p = copper.paint(runner.run_case(BIN, over))
        self.assertEqual([b["state"] for b in p["bridges"]].count("unrouted"), 1)

    def test_a_crashed_result_paints_empty_with_its_report(self):
        p = copper.paint({"case": "c", "cls": "x", "status": "crash", "problems": ["the harness exited with 134"],
                          "notes": [], "rejected": [], "metrics": {}, "b": "", "xbar": "", "stderr": "ASAN boom"})
        self.assertEqual((p["crosspoints"], p["bridges"], p["status"]), ([], [], "crash"))
        self.assertIn("boom", p["stderr"])
        self.assertEqual(p["problems"], ["the harness exited with 134"])

    def test_metrics_carry_resistance(self):
        m = runner.run_case(BIN, cases.Case("t", "x", [(1, 8, 0), (100, 3, 0)]))["metrics"]
        self.assertEqual(m["worst_r"], 2.0)
        self.assertEqual(m["rail_worst_r"], 2.0)
        self.assertEqual(m["median_r"], 2.0)
        self.assertIsNone(runner.run_case(BIN, cases.Case("t", "x", [(1, 8, 0)]))["metrics"]["rail_worst_r"])

    def test_rails_are_reported_apart_from_signals(self):
        # GND-3 stacked three deep is the best bridge here; it must not hide in, or set, the signal column
        m = runner.run_case(BIN, cases.Case("t", "x", [(100, 3, 0)]))["metrics"]
        self.assertEqual((m["worst_r"], m["median_r"], m["rail_worst_r"]), (None, None, 2.0))


# Net 6's path 1-8 in the report of the two-bridge case below: A.X2/Y1 (row 1), then B.X0/Y1 (row 8).
HOP = "1\t6\t1\tA\t2\t1\t8\tB\t0\t1\t"
STATUS_B = "B\t6    .    .    .    7    .    .    .    .    .    .    .    .    .    .    .    \t.    6    7    "


class Faults(unittest.TestCase):
    """What the paint says of a routing that is wrong. No router here makes
    these, so the report of a good routing is edited and judged again."""

    def judged(self, edit, must_route=False):
        case = cases.Case("t", "x", [(1, 8, 0), (9, 20, 0)], must_route=must_route)
        stdout, stderr, _ = runner.run_harness(BIN, case)
        sections = runner.parse_sections(stdout)["t"]
        self.assertIn(HOP, sections["b"])                   # the report still reads as these edits expect
        self.assertIn(STATUS_B, sections["b"])
        b = edit(sections["b"])
        masks = {c: [0] * 8 for c in runner.rc.CHIPS}
        for r in runner.rc.parse_paths(b):
            if r["net"] >= 0:
                for chip, x, y in runner.rc.routed_hops(r):
                    masks[chip][y] |= 1 << x
        xbar = "xbar{12x8:%s}" % "".join("%04X" % m for c in runner.rc.CHIPS for m in masks[c])
        return runner.judge(case, dict(sections, b=b, xbar=xbar), stderr)

    def test_a_stray_is_marked_on_its_wire(self):
        # net 6's second hop lands on row 10 (B.Y3), a node in no net, and claims it properly
        result = self.judged(lambda b: b.replace(HOP, HOP[:-2] + "3\t").replace(
            STATUS_B + ".    ", STATUS_B.replace("\t.    6    7    ", "\t.    .    7    ") + "6    "))
        self.assertTrue(any(p.startswith("STRAY") for p in result["problems"]))
        wires = copper.paint(result)["wires"]
        self.assertTrue(wires["10"]["stray"])
        self.assertFalse(wires["1"]["stray"])
        self.assertFalse(wires["9"]["stray"])

    def test_a_short_through_another_nets_node_shows_both_nets(self):
        # net 6 lands on row 9, net 7's node; net 7's own bridge is not routed, so no crosspoint of 7 is there
        def edit(b):
            b = b.replace(HOP, HOP[:-2] + "2\t")
            self.assertIn("2\t7\t9\tB\t4\t2\t20\tC\t2\t6\t", b)
            b = b.replace("2\t7\t9\tB\t4\t2\t20\tC\t2\t6\t", "2\t7\t9\tB\t-1\t-1\t20\tC\t-1\t-1\t")
            return b.replace(STATUS_B, "B\t6    " + ".    " * 15 + "\t.    .    6    ")
        result = self.judged(edit)
        self.assertTrue(any(p.startswith("SHORT") for p in result["problems"]))
        self.assertEqual(copper.paint(result)["wires"]["9"]["nets"], [6, 7])

    def test_listed_as_routed_but_not_joined_is_broken_and_a_problem_on_any_class(self):
        # net 6's second hop lands on B's bounce row (B.Y0) instead of row 8, claimed consistently
        edit = lambda b: b.replace(HOP, HOP[:-2] + "0\t").replace(
            STATUS_B, STATUS_B.replace("\t.    6    7    ", "\t6    .    7    "))
        for must_route in (False, True):
            result = self.judged(edit, must_route)
            b = bridge(copper.paint(result), 1, 8)
            self.assertEqual((b["state"], b["r"]), ("broken", None))
            self.assertEqual(result["status"], "problems")
            self.assertEqual(len([p for p in result["problems"] if p.startswith("NOT CONNECTED")]), 1)
            self.assertEqual(result["metrics"]["broken"], 1)
            import lab
            self.assertFalse(lab.fully_routed(result))
        self.assertEqual(bridge(copper.paint(self.judged(lambda b: b)), 1, 8)["state"], "routed")

    def test_a_claim_without_copper_is_red_only_where_the_checker_calls_it_a_problem(self):
        # a claim left on B.X9, whose lane carries nothing
        edit = lambda b: b.replace(STATUS_B, STATUS_B.replace("6    .    .    .    7    .    .    .    .    .    ",
                                                               "6    .    .    .    7    .    .    .    .    6    "))
        mark = lambda result: [pin["mark"] for w in copper.paint(result)["wires"].values() for pin in w["pins"]
                               if (pin["chip"], pin["axis"], pin["pin"]) == ("B", "X", 9)][0]
        self.assertEqual(mark(self.judged(edit)), "held")                   # scored: the checker only notes it
        strict = self.judged(edit, must_route=True)
        self.assertTrue(any(p.startswith("CLAIM WITHOUT COPPER") for p in strict["problems"]))
        self.assertEqual(mark(strict), "mismatch")


if __name__ == "__main__":
    unittest.main()
