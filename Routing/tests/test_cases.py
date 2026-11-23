# SPDX-License-Identifier: MIT
import os
import py_compile
import re
import tempfile
import unittest

import variants               # puts the firmware checkout's test/hil on the path

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = str(variants.REPO)
HIL = str(variants.HIL)

import cases
import routing_cases


class Cases(unittest.TestCase):
    def tmp_yaml(self, text):
        f = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
        f.write(text)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_dense_cases_match_the_hil_suite(self):
        d = cases.dense_cases()
        self.assertEqual(len(d), 21)
        by = {c.name: c for c in d}
        self.assertTrue(by["all_28_chip_pairs"].must_route)
        self.assertFalse(by["nano_dense_metric"].must_route)
        self.assertEqual(sorted(c.name for c in d if c.taps_required),
                         sorted(n for n, _, _, _, e in routing_cases.CASES if e == ("taps",)))
        self.assertEqual(len([c for c in d if c.taps_required]), 5)
        k = by["kevin_fixture_2026_09_02"]                       # stacking (2, 3, 0)
        self.assertIn((1, 101, 3), k.bridges)
        self.assertIn((6, 131, 0), k.bridges)
        self.assertEqual(k.power, (0.0, 0.0, 0.0, 0.0))

    def test_protocol_text(self):
        c = cases.Case("t", "x", [(1, 8, -1)])
        self.assertEqual(c.to_protocol([("X", 0, 2)]),
                         "case t\nstack 2 3 0 0 0\npower 0 0 3.33 0\nprobe 1 0\nblock X 0 2\nbridge 1 8 -1\nend\n")

    def test_digest_changes_with_the_case(self):
        a = cases.Case("t", "x", [(1, 8, -1)])
        self.assertEqual(a.digest(), cases.Case("t", "x", [(1, 8, -1)]).digest())
        self.assertNotEqual(a.digest(), cases.Case("t", "x", [(1, 8, 0)]).digest())

    def test_json_round_trip(self):
        c = cases.Case("t", "real", [(1, 8, -1), (100, 3, 2)], stack=(1, 2, 3, 4, 5), power=(1.5, 2.5, 3.0, 0.0),
                       probe=(0, 1), must_route=True, taps_required=True, notes="n")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "c.json")
            cases.save_json(c, path)
            self.assertEqual(cases.load_json(path), c)

    def test_state_import_resets_the_stamped_count(self):
        c = cases.import_state(HIL + "/slot3_snapshot_2026-08-26.yaml", "slot3")
        gp = [b for b in c.bridges if 131 <= b[0] <= 138 or 131 <= b[1] <= 138]
        self.assertTrue(gp)
        self.assertTrue(all(b[2] == -1 for b in gp))
        self.assertIn((10, 101, 3), c.bridges)                   # an explicit count that is not stackPaths stays

    def test_state_import_reads_names_and_settings(self):
        c = cases.import_state(HIL + "/kevin_state_2026-09-07_2303.yaml", "kevin")
        self.assertEqual(len(c.bridges), 13)
        self.assertIn((6, 131, -1), c.bridges)
        self.assertEqual(c.stack[:3], (2, 3, 0))
        self.assertEqual(c.power, (4.40, 7.40, 2.50, 0.60))
        self.assertEqual((c.name, c.cls), ("kevin", "real"))

    def test_unknown_node_name_is_named(self):
        bad = self.tmp_yaml("bridges:\n  - {n1: IC41_P1, n2: 3}\n")
        with self.assertRaisesRegex(ValueError, r"IC41_P1.*%s" % re.escape(os.path.basename(bad))):
            cases.import_state(bad, "bad")
        with self.assertRaisesRegex(ValueError, "no bridges section"):
            cases.import_state(self.tmp_yaml("just some text\n"), "bad")
        self.assertEqual(cases.node_id("rp_uart_tx"), 116)
        self.assertEqual(cases.node_id("ISENSE_MINUS"), 109)
        self.assertEqual(cases.node_id(7), 7)
        self.assertEqual(cases.node_id("TOP_R"), 101)

    def test_state_import_reads_fields_in_any_order(self):
        doc = ("bridges:\n"
               "  - {n2: GND, n1: 5}\n"
               "  - {n1: 6, n2: TOP_RAIL, color: pink, dup: 4}\n"
               "  - {n1: NANO_AREF, n2: 7}\n"
               "config:\n  routing: {stackPaths: 2, stackRails: 3, stackDacs: 0}\n")
        c = cases.import_state(self.tmp_yaml(doc), "any")
        self.assertEqual(c.bridges, [(5, 100, -1), (6, 101, 4), (85, 7, -1)])

    def test_state_import_refuses_a_bridge_line_it_cannot_read(self):
        for doc in ("bridges:\n  - n1: 5\n    n2: 6\n",                  # block style
                    "bridges:\n  - [5, 6]\n",                            # a list
                    "bridges:\n  - {n1: 5}\n"):                          # no second node
            with self.assertRaisesRegex(ValueError, "bridge line"):
                cases.import_state(self.tmp_yaml(doc), "bad")

    def test_case_names_are_safe_file_and_protocol_names(self):
        for bad in ("a b", "../x", "x#y", "a/b", ".hidden", "", "n" * 101):
            with self.assertRaises(ValueError, msg=bad):
                cases.Case(bad, "x", [])
        self.assertEqual(cases.Case("kevin_state_2026-09-07", "x", []).name, "kevin_state_2026-09-07")

    def test_checked_in_real_cases_load(self):
        names = sorted(os.listdir(os.path.join(LAB, "cases", "real")))
        self.assertEqual(names, ["kevin_state_2026-09-07.json", "slot3_snapshot_2026-08-26.json"])
        for n in names:
            self.assertEqual(cases.load_json(os.path.join(LAB, "cases", "real", n)).cls, "real")

    def test_the_bench_suite_is_there_and_the_dense_cases_are_the_labs_own(self):
        py_compile.compile(HIL + "/test_routing_dense.py", doraise=True)       # the firmware checkout's bench test
        # the cases began there; the lab carries them beside itself (the firmware's copy is its own)
        self.assertEqual(os.path.dirname(os.path.abspath(routing_cases.__file__)), LAB)


if __name__ == "__main__":
    unittest.main()
