# SPDX-License-Identifier: MIT
import os
import re
import unittest

import generators
import runner
import variants

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = str(variants.REPO)                   # the firmware checkout


class Generators(unittest.TestCase):
    def test_seeded_and_deterministic(self):
        self.assertEqual([c.digest() for c in generators.fuzz(3, 50)], [c.digest() for c in generators.fuzz(3, 50)])
        self.assertNotEqual(generators.fuzz(3, 50)[0].digest(), generators.fuzz(4, 50)[0].digest())
        self.assertEqual([c.digest() for c in generators.typical(1, 20)],
                         [c.digest() for c in generators.typical(1, 20)])
        self.assertEqual([c.name for c in generators.fuzz(3, 3)], ["fuzz_3_0", "fuzz_3_1", "fuzz_3_2"])
        self.assertEqual(generators.typical(2, 1)[0].name, "typical_2_0")

    def test_everything_generated_is_legal_and_in_range(self):
        everything = generators.fuzz(1, 300) + generators.typical(1, 100) + generators.stress() + generators.beyond()
        for c in everything:
            self.assertTrue(generators.legal([(a, b) for a, b, _ in c.bridges]), c.name)
            self.assertTrue(all(n in generators.USER_NODES for a, b, _ in c.bridges for n in (a, b)), c.name)
            self.assertFalse(c.must_route, c.name)
        self.assertTrue(all(4 <= len(c.bridges) <= 20 for c in generators.typical(1, 100)))
        self.assertTrue(all(1 <= len(c.bridges) <= 12 for c in generators.fuzz(1, 300)))
        self.assertEqual(len({c.name for c in everything}), len(everything))
        self.assertFalse(generators.legal([(100, 1), (101, 1)]))
        self.assertFalse(generators.legal([(5, 5)]))
        self.assertTrue(generators.legal([(100, 1), (1, 2), (101, 3)]))

    def test_forbidden_pairs_match_the_firmware(self):
        import subprocess
        binary = variants.build(variants.resolve("worktree"))
        out = subprocess.run([str(binary), "--forbidden-pairs"], capture_output=True, text=True, check=True).stdout
        firmware = {frozenset(int(v) for v in l.split()) for l in out.splitlines() if l.strip()}
        self.assertEqual({frozenset(p) for p in generators.FORBIDDEN_PAIRS}, firmware)

    def test_legal_refuses_what_the_firmware_refuses(self):
        self.assertFalse(generators.legal([(5, 101), (5, 131)]))       # a GPIO and a rail through row 5
        self.assertFalse(generators.legal([(116, 3), (3, 4), (4, 107)]))  # UART_TX and DAC1, two hops apart
        self.assertFalse(generators.legal([(131, 101)]))               # directly
        self.assertTrue(generators.legal([(100, 1), (106, 1)]))        # GND with DAC0: the firmware allows it
        self.assertFalse(generators.legal([(106, 2), (107, 2)]))       # DAC0 with DAC1: the DAC nets keep them apart

    def test_no_generated_case_is_refused_by_the_firmware(self):
        # beyond() is left out: max_bridges_random overflows the firmware's net tables on purpose
        every = generators.typical() + generators.fuzz() + generators.stress()
        rs = runner.run_battery(variants.resolve("worktree"), every)
        bad = [(r["case"], r["rejected"], r["metrics"]["refused"]) for r in rs
               if r["rejected"] or r["metrics"]["refused"] or any("left out of every net" in n for n in r["notes"])]
        self.assertEqual(bad, [])
        self.assertEqual([r["case"] for r in rs if r["status"] == "empty"], [])

    def test_classes(self):
        self.assertEqual({c.cls for c in generators.fuzz(1, 5)}, {"fuzz"})
        self.assertEqual({c.cls for c in generators.typical(1, 5)}, {"typical"})
        self.assertEqual({c.cls for c in generators.stress()}, {"stress"})
        self.assertEqual({c.cls for c in generators.beyond()}, {"beyond"})

    def test_stress_names(self):
        by = {c.name: c for c in generators.stress()}
        self.assertEqual(len([n for n in by if n.startswith("flood_")]), 16)
        self.assertLessEqual({"six_hub_lanes", "one_net_forty_nodes", "max_duplicates", "gnd_two_rows_every_chip",
                              "corner_rows_to_specials"}, set(by))
        self.assertEqual(by["flood_A_gpio"].bridges, [(i, 130 + i, -1) for i in range(1, 8)])
        self.assertEqual(len(by["one_net_forty_nodes"].bridges), 39)
        self.assertEqual({n for a, b, _ in by["one_net_forty_nodes"].bridges for n in (a, b)}.__len__(), 40)
        self.assertTrue(all(d == 7 for _, _, d in by["max_duplicates"].bridges))

    def test_beyond_cases(self):
        by = {c.name: c for c in generators.beyond()}
        self.assertEqual(set(by), {"every_nano_pin", "nine_k_nets", "max_bridges_random"})
        self.assertEqual(len(by["every_nano_pin"].bridges), 22)
        self.assertEqual(len(by["nine_k_nets"].bridges), 9)
        with open(os.path.join(REPO, "src", "JumperlessDefines.h")) as f:
            v5_max = [int(n) for n in re.findall(r"#define MAX_BRIDGES (\d+)", f.read())][-1]
        self.assertEqual(len(by["max_bridges_random"].bridges), v5_max)

    def test_no_generated_case_crashes_the_router(self):
        rs = runner.run_battery(variants.resolve("worktree"),
                                generators.stress() + generators.beyond() + generators.fuzz(1, 200))
        bad = [(r["case"], r["problems"], r["stderr"][-400:]) for r in rs if r["status"] in ("crash", "timeout")]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
