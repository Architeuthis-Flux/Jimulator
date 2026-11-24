# SPDX-License-Identifier: MIT
"""The firmware's fixes of plan 8, judged on the router the lab is pointed at.

The lab reads its pinned submodule unless JUMPERLOS names another checkout.
Each pair of tests holds today's behaviour on the pinned router and the fix on
a router that has it; the one that does not apply is skipped with its reason,
so a run always says which router it judged."""
import dataclasses
import os
import subprocess
import unittest

import cases
import lab
import runner
import variants

ROUTER = variants.resolve("worktree")
POINTED = bool(os.environ.get("JUMPERLOS"))
SCAN_ON = b"X(measurement, net_currents, INT, 1, 0, 1, 1,"
SCAN_OFF = b"X(measurement, net_currents, INT, 0, 0, 1, 1,"


def has(path, word):
    return word in (ROUTER.src_root / path).read_text(errors="replace")


GATED = has("routing/NetsToChipConnections.cpp", "tapReserveOn")
FALLS = has("routing/InfraPaths.h", "infraNoteRouting")
GPIO_FEED_UNROUTED = "unrouted primary path 0: BUFFER_IN-GPIO_6 (net 6)"


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


def case_named(cls, name):
    return next(c for c in lab.battery([cls]) if c.name == name)


def feed_three_times(v):
    """gnd_two_rows_every_chip with the feed GPIO-first, sent three times to
    one harness process: three rebuilds, the feed's state kept between them
    as a board keeps it."""
    case = case_named("stress", "gnd_two_rows_every_chip")
    copies = [dataclasses.replace(case, name=n, probe=(1, 1)) for n in ("feed_one", "feed_two", "feed_three")]
    p = subprocess.run([str(binary(v))], input="".join(c.to_protocol() for c in copies),
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError("the harness exited with %d: %s" % (p.returncode, p.stderr[-2000:]))
    sections = runner.parse_sections(p.stdout)
    missing = [c.name for c in copies if c.name not in sections]
    if missing:
        raise RuntimeError("the harness printed nothing for %s" % ", ".join(missing))
    return [runner.judge(c, sections[c.name], p.stderr, ()) for c in copies]


def unrouted(result):
    return [n for n in result["notes"] if "unrouted" in n]


class Feed(unittest.TestCase):
    """F4: a probe feed whose pair did not route falls back to its next viable
    candidate one rebuild later, and stays there."""

    @unittest.skipIf(FALLS or POINTED, "the router under test is not the pinned one")
    def test_today_a_gpio_feed_that_cannot_route_stays_unrouted(self):
        for r in feed_three_times(ROUTER):                                     # measured: 16, 16, 16
            self.assertEqual(r["metrics"]["routed_primaries"], 16, r["case"])
            self.assertIn(GPIO_FEED_UNROUTED, r["notes"], r["case"])

    @unittest.skipUnless(FALLS or POINTED, "the pinned router has no fallback; set JUMPERLOS to a firmware that has")
    def test_the_feed_falls_back_and_stays(self):
        one, two, three = feed_three_times(ROUTER)                             # measured: 16, then 17, then 17
        self.assertEqual(one["metrics"]["routed_primaries"], 16)
        self.assertIn(GPIO_FEED_UNROUTED, one["notes"])
        self.assertEqual(two["metrics"]["routed_primaries"], 17, two["notes"])
        self.assertEqual(two["status"], "ok", two["problems"])
        self.assertEqual(two["problems"], [])
        self.assertEqual(unrouted(two), [])
        self.assertIn("[BUF_IN,DAC_0,", two["b"].partition("Bridge Array")[2])
        self.assertEqual(three["b"], two["b"])

    def test_the_batteries_do_not_see_it(self):
        # In these three DAC 0 is the case's own, so the GPIO feed has nothing to fall back to.
        for cls, name in (("dense", "k_rows_overflow_metric"), ("edge", "edge_1_10"), ("beyond", "nine_k_nets")):
            r = runner.run_case(binary(ROUTER), case_named(cls, name))
            self.assertTrue(r["metrics"]["repeat_same"], name)
            self.assertTrue(any(n.startswith("unrouted primary path 0: BUFFER_IN-GPIO_6") for n in r["notes"]),
                            (name, r["notes"]))


if __name__ == "__main__":
    unittest.main()
