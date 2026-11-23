# SPDX-License-Identifier: MIT
"""The firmware's fixes of plan 8, judged on the router the lab is pointed at.

The lab reads its pinned submodule unless JUMPERLOS names another checkout.
Each pair of tests holds today's behaviour on the pinned router and the fix on
a router that has it; the one that does not apply is skipped with its reason,
so a run always says which router it judged."""
import os
import unittest

import cases
import runner
import variants

ROUTER = variants.resolve("worktree")
POINTED = bool(os.environ.get("JUMPERLOS"))
SCAN_ON = b"X(measurement, net_currents, INT, 1, 0, 1, 1,"
SCAN_OFF = b"X(measurement, net_currents, INT, 0, 0, 1, 1,"


def has(path, word):
    return word in (ROUTER.src_root / path).read_text(errors="replace")


GATED = has("routing/NetsToChipConnections.cpp", "tapReserveOn")


def scan_off():
    """The router under test with the net scan off by default (the harness has
    no knob for it, so config.h is replaced for this build only)."""
    text = (ROUTER.src_root / "config.h").read_bytes()
    if text.count(SCAN_ON) != 1:
        raise RuntimeError("config.h no longer has the net_currents default line: %r" % SCAN_ON)
    return variants.resolve("worktree", overrides={"src/config.h": text.replace(SCAN_ON, SCAN_OFF)})


def binary(v):
    return variants.build(v)


def route(v, name):
    case = next(c for c in cases.dense_cases() if c.name == name)
    return runner.run_case(binary(v), case, repeat=1)


def copies(v, name):
    return route(v, name)["metrics"]["routed_duplicates"]


def sense_tap_problems(result):
    return [p for p in result["problems"] if p.startswith("no sense-tap route for ")]


class Reserve(unittest.TestCase):
    """F5: the tap reserve denies stacked copies only while the net scan is on."""

    @unittest.skipIf(GATED or POINTED, "the router under test is not the pinned one")
    def test_today_the_reserve_holds_with_the_scan_off(self):
        off = scan_off()
        for name in ("kevin_fixture_2026_09_02", "rail_stacking_light"):      # measured: 0 and 0, 3 and 3
            self.assertEqual(copies(off, name), copies(ROUTER, name), name)

    @unittest.skipUnless(GATED or POINTED, "the pinned router has no gate; set JUMPERLOS to a firmware that has")
    def test_with_the_scan_off_copies_take_the_reserve(self):
        off = scan_off()
        for name in ("kevin_fixture_2026_09_02", "rail_stacking_light"):      # measured: 0 then 2, 3 then 5
            on_r, off_r = route(ROUTER, name), route(off, name)
            self.assertEqual(off_r["metrics"]["routed_duplicates"], on_r["metrics"]["routed_duplicates"] + 2, name)
            self.assertEqual(off_r["metrics"]["routed_primaries"], on_r["metrics"]["routed_primaries"], name)
            if name == "rail_stacking_light":
                self.assertEqual(sense_tap_problems(on_r), [], on_r["problems"])
                self.assertNotEqual(sense_tap_problems(off_r), [], off_r["problems"])


if __name__ == "__main__":
    unittest.main()
