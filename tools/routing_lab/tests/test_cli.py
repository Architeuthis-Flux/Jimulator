# SPDX-License-Identifier: MIT
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

import lab
import variants

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIL = os.path.join(os.path.dirname(os.path.dirname(LAB)), "test", "hil")


def run(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = lab.main(argv)
    return code, out.getvalue()


class Cli(unittest.TestCase):
    def test_run_dense_at_worktree_exits_zero(self):
        code, out = run(["run", "--classes", "dense"])
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"dense\s+21\s+20\s")           # 21 cases, 20 fully routed (the K overflow is not)
        self.assertIn("k_rows_overflow_metric", out)

    def test_battery_classes(self):
        self.assertEqual(len(lab.battery(["dense"])), 21)
        self.assertEqual({c.cls for c in lab.battery(["dense", "real", "stress"])}, {"dense", "real", "stress"})
        with self.assertRaises(ValueError):
            lab.battery(["nope"])

    def test_regressions(self):
        ok = {"case": "a", "status": "ok", "problems": [], "metrics": {"primaries": 2, "routed_primaries": 2}}
        worse = {**ok, "metrics": {"primaries": 2, "routed_primaries": 1}}
        self.assertEqual(lab.regressions([ok], [ok]), [])
        self.assertEqual(len(lab.regressions([ok], [worse])), 1)
        self.assertEqual(len(lab.regressions([ok], [{**ok, "status": "problems", "problems": ["SHORT x"]}])), 1)
        self.assertEqual(len(lab.regressions([ok], [{**ok, "status": "crash"}])), 1)
        # the same kind of problem as the baseline had is not a regression; a case only in one list is ignored
        short = {**ok, "status": "problems", "problems": ["SHORT: nets 6 7 share copper via AB0"]}
        self.assertEqual(lab.regressions([short], [{**short, "problems": ["SHORT: nets 6 9 share copper via AC0"]}]), [])
        self.assertEqual(lab.regressions([ok], [{**ok, "case": "b"}]), [])

    def test_exit_1_on_a_short_or_a_crash(self):
        short = {"case": "a", "cls": "fuzz", "status": "problems", "problems": ["SHORT: x"], "notes": [],
                 "metrics": {"primaries": 1, "routed_primaries": 1, "taps_dead": []}}
        self.assertEqual(lab.exit_code([short], [lab.cases.Case("a", "fuzz", [(1, 2, -1)])], []), 1)
        crash = {**short, "status": "crash", "problems": []}
        self.assertEqual(lab.exit_code([crash], [lab.cases.Case("a", "fuzz", [(1, 2, -1)])], []), 1)
        unrouted = {**short, "problems": ["unrouted primary path 0: 1-2 (net 6)"]}
        self.assertEqual(lab.exit_code([unrouted], [lab.cases.Case("a", "fuzz", [(1, 2, -1)])], []), 0)
        self.assertEqual(lab.exit_code([unrouted], [lab.cases.Case("a", "fuzz", [(1, 2, -1)], must_route=True)], []), 1)
        self.assertEqual(lab.exit_code([], [], ["a: routed 1/2, baseline 2/2"]), 1)

    def test_broken_variant_exits_3(self):
        with mock.patch.object(variants, "build", side_effect=variants.BuildError("x.cpp:1: error: no")):
            code, out = run(["run", "--classes", "dense"])
        self.assertEqual(code, 3)
        self.assertIn("x.cpp:1: error: no", out)

    def test_baseline_run_and_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "r.json")
            code, out = run(["run", "--classes", "dense", "--baseline", "HEAD", "--json", path])
            self.assertEqual(code, 0, out)
            self.assertIn("no regressions", out)
            with open(path) as f:
                doc = json.load(f)
        self.assertEqual(len(doc["results"]), 21)
        self.assertEqual(doc["regressions"], [])
        self.assertEqual(doc["variant"]["name"], "worktree")

    def test_single_case_prints_its_report(self):
        code, out = run(["run", "--classes", "dense", "--case", "chain_all_chips"])
        self.assertEqual(code, 0, out)
        self.assertIn("Bridge Array", out)
        self.assertEqual(run(["run", "--classes", "dense", "--case", "no_such_case"])[0], 2)

    def test_import_state_writes_a_case(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(lab, "CASES_DIR", lab.Path(tmp)):
            code, out = run(["import-state", os.path.join(HIL, "slot3_snapshot_2026-08-26.yaml"), "--name", "s3"])
            self.assertEqual(code, 0, out)
            self.assertEqual(lab.cases.load_json(os.path.join(tmp, "real", "s3.json")).name, "s3")

    def test_build_prints_the_binary(self):
        code, out = run(["build"])
        self.assertEqual(code, 0)
        self.assertTrue(os.access(out.strip().splitlines()[-1], os.X_OK), out)


if __name__ == "__main__":
    unittest.main()
