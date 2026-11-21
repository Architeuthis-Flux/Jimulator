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


if __name__ == "__main__":
    unittest.main()
