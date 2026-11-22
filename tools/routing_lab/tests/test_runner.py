# SPDX-License-Identifier: MIT
import contextlib
import dataclasses
import io
import os
import stat
import tempfile
import unittest
from unittest import mock

import arrangement
import cases
import ceiling
import copper
import lab
import runner
import variants

BIN = V = None
CASE18 = cases.Case("t", "x", [(1, 8, -1)], must_route=True)


def setUpModule():
    global BIN, V
    V = variants.resolve("worktree")
    BIN = variants.build(V)


class Runner(unittest.TestCase):
    def script(self, body):
        f = tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False)
        f.write("#!/bin/sh\n" + body + "\n")
        f.close()
        os.chmod(f.name, os.stat(f.name).st_mode | stat.S_IXUSR)
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_ok_case(self):
        r = runner.run_case(BIN, CASE18)
        self.assertEqual((r["status"], r["problems"]), ("ok", []))
        self.assertEqual(r["metrics"]["taps_dead"], [])
        self.assertTrue(r["metrics"]["repeat_same"])
        self.assertEqual((r["case"], r["cls"]), ("t", "x"))
        self.assertEqual((r["metrics"]["primaries"], r["metrics"]["routed_primaries"]), (2, 2))
        self.assertIn("Bridge Array", r["b"])
        self.assertIn("xbar{12x8:", r["xbar"])

    def test_a_result_says_what_kind_of_case_it_was(self):
        r = runner.run_case(BIN, CASE18)
        self.assertEqual((r["must_route"], r["about"]), (True, ""))
        scored = dataclasses.replace(CASE18, must_route=False, notes="proved routable with firmware-shaped paths")
        r = runner.run_case(BIN, scored)
        self.assertEqual((r["must_route"], r["about"]), (False, "proved routable with firmware-shaped paths"))
        self.assertIs(runner.run_case(self.script("exit 134"), CASE18)["must_route"], True)     # a crash says it too

    def test_empty_case(self):
        self.assertEqual(runner.run_case(BIN, cases.Case("e", "x", []))["status"], "empty")
        r = runner.run_case(BIN, cases.Case("e", "x", [(100, 101, -1)]))
        self.assertEqual((r["status"], r["rejected"]), ("empty", [[100, 101]]))

    def test_timeout_and_crash(self):
        self.assertEqual(runner.run_case(self.script("exec sleep 30"), CASE18, timeout=0.5)["status"], "timeout")
        r = runner.run_case(self.script("echo boom >&2; exit 134"), CASE18)
        self.assertEqual(r["status"], "crash")
        self.assertIn("boom", r["stderr"])

    def test_output_without_the_case_is_a_crash(self):
        self.assertEqual(runner.run_case(self.script("echo hello"), CASE18)["status"], "crash")

    def test_unrouted_bridge_is_a_problem_only_when_it_must_route(self):
        over = [c for c in cases.dense_cases() if c.name == "k_rows_overflow_metric"][0]
        self.assertNotEqual(runner.run_case(BIN, over)["status"], "crash")
        must = dataclasses.replace(over, must_route=True)
        self.assertEqual(runner.run_case(BIN, must)["status"], "problems")

    def test_dead_tap_is_a_problem_only_when_taps_are_required(self):
        secs = runner.parse_sections(runner.run_harness(BIN, CASE18)[0])["t"]
        secs["taps"] = "[nvscan] route 1: (none - lanes busy, short, or node unknown) tier4:\n[nvscan] route 8: B(x11,y1) K(x8,y1) -> ADC0\n"
        note = runner.judge(CASE18, secs)
        self.assertEqual((note["status"], note["metrics"]["taps"], note["metrics"]["taps_dead"]), ("ok", 2, [1]))
        self.assertTrue(any("tap" in n for n in note["notes"]))
        need = runner.judge(dataclasses.replace(CASE18, taps_required=True), secs)
        self.assertEqual(need["status"], "problems")
        secs["taps"] = "skipped: no free ADC\n"
        self.assertIsNone(runner.judge(CASE18, secs)["metrics"]["taps"])

    def test_a_different_second_routing_is_a_problem(self):
        secs = runner.parse_sections(runner.run_harness(BIN, CASE18)[0])["t"]
        secs["repeat"] = "different\n"
        r = runner.judge(CASE18, secs)
        self.assertEqual((r["status"], r["metrics"]["repeat_same"]), ("problems", False))

    def test_a_safety_refusal_is_labelled_and_is_not_a_routing_miss(self):
        r = runner.run_case(BIN, cases.Case("r", "x", [(5, 101, -1), (5, 131, -1)]))
        self.assertEqual(r["metrics"]["refused"], 1)
        self.assertTrue(any("refused by the firmware's safety check" in n for n in r["notes"]), r["notes"])
        self.assertEqual(r["metrics"]["primaries"] - r["metrics"]["routed_primaries"], 1)
        self.assertEqual(runner.run_case(BIN, CASE18)["metrics"]["refused"], 0)

    def test_blocked_pins_are_not_judged(self):
        chain = [c for c in cases.dense_cases() if c.name == "chain_all_chips"][0]     # strict claims
        self.assertEqual(runner.run_case(BIN, chain)["status"], "ok")
        blocked = runner.run_case(BIN, chain, block=[("X", 0, 2), ("X", 1, 0)])       # the first A-B lane
        self.assertEqual((blocked["status"], blocked["problems"]), ("ok", []))

    def test_required_taps_that_are_not_listed_are_a_problem(self):
        need = dataclasses.replace(CASE18, taps_required=True)
        secs = runner.parse_sections(runner.run_harness(BIN, need)[0])["t"]
        self.assertEqual(runner.judge(need, dict(secs))["status"], "ok")
        self.assertEqual(runner.judge(need, {**secs, "taps": "skipped: no free ADC\n"})["status"], "problems")
        without = {k: v for k, v in secs.items() if k != "taps"}
        self.assertEqual(runner.judge(need, without)["status"], "problems")
        self.assertEqual(runner.judge(CASE18, {**secs, "taps": "skipped: no free ADC\n"})["status"], "ok")

    def test_bridge_the_firmware_leaves_out_of_every_net_is_noted(self):
        # GND-1 then TOP_RAIL-1 would join two supplies through row 1: the
        # firmware keeps the second bridge out of every net ("Net ?")
        r = runner.run_case(BIN, cases.Case("c", "x", [(100, 1, -1), (101, 1, -1)]))
        self.assertNotIn(r["status"], ("crash", "timeout"))
        self.assertTrue(any("TOP_RAIL" in n and "left out" in n for n in r["notes"]), r["notes"])
        self.assertFalse(any(p.startswith("SHORT") for p in r["problems"]), r["problems"])

    def test_missed_counts_only_failed_bridges_the_copper_had_a_path_for(self):
        self.assertEqual(runner.run_case(BIN, CASE18)["metrics"]["missed"], 0)
        self.assertEqual(runner.run_case(self.script("exit 134"), CASE18)["metrics"]["missed"], 0)   # nothing judged
        found = [{"path": [{"chip": "A", "x": 0, "y": 0, "new": True}]}, {"path": None}, {"path": []}]
        with mock.patch.object(runner.ceiling, "missed", return_value=found):
            self.assertEqual(runner.run_case(BIN, CASE18)["metrics"]["missed"], 2)

    def test_a_change_to_the_searches_is_a_new_judge_stamp(self):
        before, read = runner._judge_stamp(), runner.Path.read_bytes
        edited = lambda path: read(path) + (b"#" if path.name == "ceiling.py" else b"")
        with mock.patch.object(runner.Path, "read_bytes", edited):
            self.assertNotEqual(runner._judge_stamp(), before)

    def test_battery_is_cached(self):
        v = variants.resolve("worktree")
        cs = [CASE18]
        runner.run_battery(v, cs)
        with mock.patch.object(runner, "run_case", side_effect=AssertionError("ran again")):
            self.assertEqual(runner.run_battery(v, cs)[0]["status"], "ok")
            # a change to how the case is judged is a different cache entry
            with self.assertRaises(AssertionError):
                runner.run_battery(v, [dataclasses.replace(CASE18, name="t_uncached_%d" % os.getpid())])

    def test_battery_keeps_order_and_runs_in_parallel(self):
        v = variants.resolve("worktree")
        cs = [cases.Case("o%d" % i, "x", [(1 + i, 8 + i, -1)]) for i in range(6)]
        self.assertEqual([r["case"] for r in runner.run_battery(v, cs, jobs=3, use_cache=False)],
                         [c.name for c in cs])


class OnAnArrangement(unittest.TestCase):
    def test_the_feed_is_off_where_the_arrangement_has_none(self):
        r = runner.run_battery(V, [CASE18], arrangement=arrangement.load("v6_feed_off"))[0]
        self.assertEqual([b for b in copper.paint(r)["bridges"] if b["infra"]], [])
        self.assertEqual((r["metrics"]["primaries"], r["arrangement"], r["feed"], r["engine"]), (1, "v6_feed_off", False, "router"))
        plain = runner.run_battery(V, [CASE18])[0]
        self.assertEqual((plain["metrics"]["primaries"], plain["arrangement"], plain["feed"]), (2, "v5", True))
        self.assertEqual(runner.run_case(BIN, CASE18, arrangement=arrangement.load("v6_feed_off"))["feed"], False)

    def test_a_wire_taken_away_is_never_used(self):                    # the design's "a blocked wire never appears in any path"
        for wires in (["KL"], ["AK"], ["/AB0", "/AB1"], [copper.BOUNCE[0]], ["IJ", "IK", "IL"]):
            a = arrangement.parse("without", {"base": "v5", "feed": False, "remove": wires})
            for r in runner.run_battery(V, lab.battery(["dense", "stress"]), arrangement=a):
                self.assertNotIn(r["status"], ("crash", "timeout"), (wires, r["case"]))
                used = {copper.wire(c["chip"], axis, c[axis.lower()]) for c in copper.paint(r)["crosspoints"] for axis in "XY"}
                self.assertEqual(used & set(wires), set(), (wires, r["case"]))
                self.assertEqual([p for p in r["problems"] if p.startswith(("SHORT", "STRAY"))], [], (wires, r["case"]))

    def test_a_missed_path_never_passes_a_wire_taken_away(self):       # Review Focus 5
        nano = next(c for c in cases.dense_cases() if c.name == "nano_dense_metric")
        old = variants.resolve("a1accf5^")                              # leaves A4-19 and A5-20 unrouted, each with a path
        plain = runner.run_battery(old, [nano])[0]
        self.assertEqual(plain["metrics"]["missed"], 2)
        for hub in ("IK", "JK"):                                        # the two paths go by way of these hub lanes
            a = arrangement.parse("no_" + hub, {"base": "v5", "remove": [hub]})
            r = runner.run_battery(old, [nano], arrangement=a)[0]
            for m in ceiling.missed(copper.paint(r), ceiling.graph(a)):
                for h in m["path"] or ():
                    self.assertNotIn(hub, (copper.wire(h["chip"], "X", h["x"]), copper.wire(h["chip"], "Y", h["y"])))
            self.assertEqual(r["metrics"]["missed"], sum(1 for m in ceiling.missed(copper.paint(r), ceiling.graph(a)) if m["path"] is not None))

    def test_the_router_refuses_what_it_cannot_route(self):            # Review Focus 4
        with self.assertRaises(arrangement.RouterCannot) as cm:
            runner.run_battery(V, [CASE18], arrangement=arrangement.load("v6_rails_on_chips"))
        self.assertRegex(str(cm.exception), r"[A-H]\.X\d+ is on (TOP_RAIL|BOTTOM_RAIL|GND)")
        self.assertIn("arrangement score v6_rails_on_chips", str(cm.exception))

    def test_a_case_on_a_dropped_node_is_unplaced_not_a_miss(self):    # Review Focus 2
        no_rail = arrangement.parse("no_top_rail", {"base": "v5", "feed": False, "pins": {"K.X4": None}})   # TOP_RAIL's one pin
        self.assertEqual(no_rail.dropped, [101])
        uses, spares = cases.Case("uses", "x", [(1, 8, -1), (101, 3, -1)]), cases.Case("spares", "x", [(1, 8, -1)])
        with mock.patch.object(runner, "run_harness", wraps=runner.run_harness) as ran:
            a, b = runner.run_battery(V, [uses, spares], arrangement=no_rail, use_cache=False)
        self.assertEqual(ran.call_count, 1)                             # only the case that can be placed is routed
        self.assertEqual((a["status"], a["problems"], a["metrics"]["primaries"], a["arrangement"]), ("unplaced", [], 0, "no_top_rail"))
        self.assertIn("TOP_RAIL", a["notes"][0])
        self.assertEqual((b["status"], b["arrangement"]), ("ok", "no_top_rail"))
        self.assertFalse(lab.fully_routed(a))
        self.assertEqual(lab.exit_code([a, b], [uses, spares], []), 0)
        self.assertEqual(lab.regressions([b, dict(b, case="uses")], [a, b]), [])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            lab.print_table(V, [a, b])
        self.assertIn("unplaced x/uses: no TOP_RAIL on no_top_rail", out.getvalue())
        with mock.patch.object(ceiling, "ask", side_effect=AssertionError("asked")):       # and the solver is not asked of it
            self.assertEqual(ceiling.verdict(a, arrangement=no_rail, use_cache=False)["verdict"], "unplaced")

    def test_a_cached_result_is_named_for_the_arrangement_asked(self):
        one, other = (arrangement.parse(n, {"base": "v5", "feed": False, "remove": ["KL"]}) for n in ("one", "other"))
        self.assertEqual(runner.run_battery(V, [CASE18], arrangement=one)[0]["arrangement"], "one")
        with mock.patch.object(runner, "run_case", side_effect=AssertionError("ran again")):
            self.assertEqual(runner.run_battery(V, [CASE18], arrangement=other)[0]["arrangement"], "other")

    def test_net_59_and_blocked_pins_do_not_mix(self):                 # Review Focus 3
        sections = runner.parse_sections(runner.run_harness(BIN, CASE18)[0])["t"]
        self.assertIn("Net 6]", sections["b"])
        high = dict(sections, b=sections["b"].replace("Net 6]", "Net 59]"))
        r = runner.judge(CASE18, high, block=[("X", 0, 2)])
        self.assertEqual(r["status"], "crash")
        self.assertIn("net 59", r["problems"][0])
        self.assertNotIn("net 59", " ".join(runner.judge(CASE18, sections, block=[("X", 0, 2)])["problems"]))
        self.assertNotEqual(runner.judge(CASE18, high)["status"], "crash")     # with nothing blocked, 59 is a net like any other


if __name__ == "__main__":
    unittest.main()
