# SPDX-License-Identifier: MIT
import dataclasses
import os
import stat
import tempfile
import unittest
from unittest import mock

import cases
import runner
import variants

BIN = None
CASE18 = cases.Case("t", "x", [(1, 8, -1)], must_route=True)


def setUpModule():
    global BIN
    BIN = variants.build(variants.resolve("worktree"))


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


if __name__ == "__main__":
    unittest.main()
