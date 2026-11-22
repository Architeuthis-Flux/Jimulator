# SPDX-License-Identifier: MIT
"""The lab against what is already known about the router: the dense suite
is clean at this commit, and two bugs that were fixed on 2026-09-03 show up
again when the lab is pointed at the commits before their fixes."""
import os
import unittest

import cases
import runner
import variants

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ROUTER = "src/routing/NetsToChipConnections.cpp"


class AtMain(unittest.TestCase):
    def test_every_must_route_dense_case_is_clean(self):
        dense = cases.dense_cases()
        rs = {r["case"]: r for r in runner.run_battery(variants.resolve("worktree"), dense)}
        for c in dense:
            r = rs[c.name]
            self.assertNotIn(r["status"], ("crash", "timeout"), (c.name, r["stderr"][-400:]))
            if c.must_route:
                self.assertEqual(r["status"], "ok", (c.name, r["problems"]))
                self.assertEqual(r["metrics"]["routed_primaries"], r["metrics"]["primaries"], c.name)
            if c.taps_required:
                self.assertEqual(r["metrics"]["taps_dead"], [], c.name)
                self.assertGreater(r["metrics"]["taps"], 0, c.name)
        m = rs["nano_dense_metric"]["metrics"]                  # 12 bridges plus the probe feed
        self.assertEqual((m["primaries"], m["routed_primaries"]), (13, 13))


class History(unittest.TestCase):
    def run_at(self, ref, name, old, new):
        """The dense case `name` routed by the router as it was at `ref`. If
        that commit does not build against today's stubs, the same regression
        is put back into today's router instead (replace `old` with `new`),
        so the lab is always shown catching it. Returns (result, exact)."""
        case = next(c for c in cases.dense_cases() if c.name == name)
        try:
            v = variants.resolve(ref)
            variants.build(v)
            exact = True
        except variants.BuildError as e:
            with open(os.path.join(REPO, ROUTER)) as f:
                source = f.read()
            self.assertEqual(source.count(old), 1, "the line to revert is no longer in the router")
            v = variants.resolve("worktree", {ROUTER: source.replace(old, new).encode()})
            exact = False
            print("\n  %s: %s does not build against today's stubs (%s); reverted one line of today's router instead"
                  % (name, ref, e))
        return runner.run_battery(v, [case])[0], exact

    def test_before_the_hub_tier_two_nano_bridges_fail(self):
        r, exact = self.run_at("a1accf5^", "nano_dense_metric",
                               "\n  rescueViaHubs(startIndex);", "\n  // rescueViaHubs(startIndex);")
        m = r["metrics"]
        self.assertNotIn(r["status"], ("crash", "timeout"), r["stderr"][-400:])
        if exact:
            self.assertEqual((m["primaries"], m["routed_primaries"]), (13, 11))
        else:
            self.assertEqual(m["primaries"], 13)
            self.assertLess(m["routed_primaries"], 13)

    def test_missed_counts_bridges_the_copper_could_carry(self):
        dense = cases.dense_cases()
        old = {r["case"]: r for r in runner.run_battery(variants.resolve("a1accf5^"), dense)}
        new = {r["case"]: r for r in runner.run_battery(variants.resolve("worktree"), dense)}
        self.assertEqual(old["nano_dense_metric"]["metrics"]["missed"], 2)        # A4-19 and A5-20, four crosspoints each
        self.assertEqual(new["nano_dense_metric"]["metrics"]["missed"], 0)
        self.assertEqual(sum(r["metrics"]["missed"] for r in new.values()), 0)    # every dense case today

    def test_before_the_bounce_pin_fix_claims_are_wrong(self):
        r, _ = self.run_at("f41e755^", "kevin_fixture_2026_09_02",
                           "int xMapBB = xMapForChipLane0(bb, sfChip);",
                           "int xMapBB = xMapForChipLane0(globalState.connections.paths[i].chip[0], bb);")
        self.assertNotIn(r["status"], ("crash", "timeout"), r["stderr"][-400:])
        self.assertTrue(any("UNCLAIMED" in p or "CLAIM WITHOUT COPPER" in p or "WRONG CLAIM" in p
                            for p in r["problems"]), r["problems"])


if __name__ == "__main__":
    unittest.main()
