# SPDX-License-Identifier: MIT
"""A board's own output as a result: what a Jumperless prints for `b`, read
from a raw serial log, from text copied out of a terminal (tabs turned to
spaces), with or without the port-7 crossbar dump."""
import re
import unittest
from pathlib import Path

import board
import copper
import lab

CAPTURES = lab.FIDELITY_DIR / "board_0621e4f44e23"          # the dense suite as a V5 printed it, 2026-11-21


def capture(name, crossbar=True):
    text = (CAPTURES / (name + ".b.txt")).read_text(errors="replace")
    return text + ((CAPTURES / (name + ".xbar.txt")).read_text() if crossbar else "")


def coloured(text):
    """As the firmware sends it: a colour code in front of every path row, a reset after the table."""
    text = re.sub(r"(?m)^(\d+\t)", "\x1b[38;5;196m\\1", text)
    return text.replace("Chip Status", "\x1b[0mChip Status")


def copied(text):
    """As a terminal gives it back when copied: no tab left, columns padded with spaces."""
    return "\n".join(line.expandtabs(8) for line in text.replace("\r", "").split("\n"))


def drawn(result):
    """What the page draws from: the copper, and what became of each bridge."""
    p = copper.paint(result)
    return ([(c["chip"], c["x"], c["y"], c["net"], c["dup"]) for c in p["crosspoints"]],
            [(b["n1"], b["n2"], b["net"], b["state"], b["copies"], b["r"]) for b in p["bridges"]],
            {name: (w["nets"], [(pin["claim"], pin["mark"]) for pin in w["pins"]]) for name, w in p["wires"].items()})


class Board(unittest.TestCase):
    def test_a_capture_is_judged_and_painted_like_a_harness_run(self):
        r = board.result("same_chip_pairs.b.txt", capture("same_chip_pairs"))
        self.assertEqual((r["case"], r["cls"], r["status"], r["problems"]), ("same_chip_pairs", "board", "ok", []))
        self.assertEqual((r["metrics"]["primaries"], r["metrics"]["routed_primaries"], r["metrics"]["crosspoints"]), (7, 7, 16))
        self.assertEqual(r["metrics"]["missed"], 0)
        crosspoints, bridges, _ = drawn(r)
        self.assertEqual(len(crosspoints), 16)
        self.assertEqual({state for *_, state, _, _ in bridges}, {"routed"})
        self.assertFalse([n for n in r["notes"] if "crossbar" in n])           # the dump was there and agrees

    def test_every_capture_reads_the_same_raw_coloured_or_copied_from_a_terminal(self):
        names = sorted(p.name[:-len(".b.txt")] for p in CAPTURES.glob("*.b.txt"))
        self.assertEqual(len(names), 21)
        for name in names:
            raw = capture(name)
            want = drawn(board.result(name, raw))
            self.assertTrue(want[0], name)                                     # something is drawn at all
            self.assertFalse([n for n in board.result(name, raw)["notes"] if "may be missing" in n], name)
            for how, text in (("coloured", coloured(raw)), ("copied", copied(raw)), ("both", copied(coloured(raw))),
                              ("in a log", "Jumperless> b\r\n" + raw + "\r\n\tMenu\r\nA\tnot a status row\r\n")):
                self.assertEqual(drawn(board.result(name, text)), want, (name, how))

    def test_an_unrouted_bridge_and_held_pins_come_through(self):
        r = board.result("over", copied(capture("k_rows_overflow_metric")))
        _, bridges, wires = drawn(r)
        self.assertEqual([(n1, n2, state) for n1, n2, _, state, _, _ in bridges if state != "routed"], [(139, 136, "unrouted")])
        self.assertIn("held", {mark for _, pins in wires.values() for _, mark in pins})
        self.assertEqual((r["metrics"]["primaries"], r["metrics"]["routed_primaries"]), (13, 12))

    def test_without_the_crossbar_dump_it_says_what_was_not_checked(self):
        with_dump, without = (board.result("c", capture("chain_all_chips", crossbar=x)) for x in (True, False))
        self.assertEqual(drawn(without), drawn(with_dump))
        self.assertEqual(without["problems"], [])
        note = [n for n in without["notes"] if "crossbar" in n]
        self.assertEqual(len(note), 1)
        self.assertIn(":crossbar", note[0])

    def test_a_crossbar_dump_that_disagrees_is_a_problem(self):
        text = capture("same_chip_pairs")
        dump = re.search(r"xbar\{12x8:([0-9A-F]{384})\}", text).group(1)
        sent_elsewhere = text.replace(dump, "8000" + dump[4:])                  # A.x15/y0 closed, nothing planned there
        r = board.result("c", sent_elsewhere)
        self.assertEqual(r["status"], "problems")
        self.assertTrue(any("A" in p and "15" in p for p in r["problems"]), r["problems"])

    def test_the_last_report_in_the_text_is_the_one_shown(self):
        both = capture("chain_all_chips", crossbar=False) + "\r\n" + capture("same_chip_pairs", crossbar=False)
        self.assertEqual(drawn(board.result("c", both)), drawn(board.result("c", capture("same_chip_pairs", crossbar=False))))

    def test_what_is_not_a_report_says_so(self):
        for text in ("", "hello", "Bridge Array\n\nPaths\n", capture("same_chip_pairs").split("Chip Status")[0]):
            with self.assertRaises(ValueError) as cm:
                board.result("x", text)
            self.assertIn("b report", str(cm.exception))

    def test_a_path_table_that_did_not_come_through_is_an_error_not_an_empty_drawing(self):
        wrapped = re.sub(r"(?m)^(\d+)\t(\S+)\t", "\\1\t\\2\n\t", capture("same_chip_pairs"))    # every row cut in two
        with self.assertRaises(ValueError) as cm:
            board.result("x", wrapped)
        self.assertIn("path table", str(cm.exception))

    def test_a_report_only_partly_wrapped_is_refused_not_drawn_wrong(self):
        # only the row with four hops is cut, after its path type: what is left still looks like a two-hop row,
        # and read that way the board would be shown with a bridge "listed as routed, not connected"
        raw = capture("same_chip_pairs", crossbar=False)
        cut = re.sub(r"(?m)^(\d+\t[^\n]*?) \t", "\\1\n", raw, count=1)
        self.assertNotEqual(cut, raw)
        for how, text in (("with tabs", cut), ("copied", copied(cut)), ("cut inside the hops", raw.replace("K \t12 \t3 \t", "K \t12 \t3\n", 1))):
            with self.assertRaises(ValueError) as cm:
                board.result("x", text)
            self.assertIn("path table", str(cm.exception), how)

    def test_a_bridge_entry_split_by_a_line_break_is_refused(self):
        # dropped silently, its copper would touch nodes in no net and read as a stray
        raw = capture("same_chip_pairs")
        self.assertIn("[3,4,Net 7]", raw)
        with self.assertRaises(ValueError) as cm:
            board.result("x", raw.replace("[3,4,Net 7]", "[3,4,Net\n7]"))
        self.assertIn("Bridge Array", str(cm.exception))

    def test_the_last_whole_report_is_used_when_a_fragment_follows(self):
        whole = capture("same_chip_pairs", crossbar=False)
        want = drawn(board.result("c", whole))
        menu = "\r\n  Bridge Array\tShow paths and chip status\r\n  Net List\tShow the nets\r\n"       # the debug menu names it too
        again_cut_short = capture("chain_all_chips", crossbar=False).split("Chip Status")[0]
        for how, tail in (("a menu", menu), ("a second report cut short", again_cut_short)):
            self.assertEqual(drawn(board.result("c", whole + tail)), want, how)

    def test_a_node_this_fabric_does_not_have_is_an_error_with_its_name(self):
        with self.assertRaises(ValueError) as cm:
            board.result("x", capture("same_chip_pairs").replace("[1,2,Net 6]", "[1,WARP_CORE,Net 6]"))
        self.assertIn("WARP_CORE", str(cm.exception))

    def test_names_are_made_safe(self):
        for given, want in (("my capture (1).txt", "my_capture__1_"), ("nano.b.txt", "nano"), ("../../etc/passwd", "passwd"),
                            ("", "board"), (".hidden", "hidden"), ("x" * 300, "x" * 60)):
            self.assertEqual(board.result(given, capture("same_chip_pairs"))["case"], want, given)


if __name__ == "__main__":
    unittest.main()
