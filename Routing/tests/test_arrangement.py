# SPDX-License-Identifier: MIT
"""The crossbar arrangement as a file: V5 plus what differs."""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import arrangement
import fabric_v5

V5 = arrangement.V5


class Files(unittest.TestCase):
    def write(self, name, text):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / name).write_text(text)
        return str(tmp / name)

    def test_v5_is_the_fabric_model_as_it_is(self):
        self.assertEqual((V5.name, V5.feed, V5.CHIPS), ("v5", True, "ABCDEFGHIJKL"))
        self.assertEqual((V5.X_NET, V5.Y_NET, V5.NODE_NET), (fabric_v5.X_NET, fabric_v5.Y_NET, fabric_v5.NODE_NET))
        self.assertEqual((V5.changed, V5.taken, arrangement.blocks(V5)), ([], [], []))
        self.assertEqual("".join(V5.ROLE[c][0] for c in V5.CHIPS), "bbbbbbbbssss")

    def test_the_base_with_the_feed_on_or_off(self):
        self.assertIs(arrangement.base(True), V5)
        off = arrangement.base(False)
        self.assertEqual((off.name, off.feed, off.changed, arrangement.blocks(off)), ("v5, feed off", False, [], []))
        self.assertEqual(off.X_NET, V5.X_NET)

    def test_a_pin_given_another_wire_and_a_pin_taken_away(self):
        a = arrangement.parse("t", {"base": "v5", "feed": False, "remove": ["/AD1"], "pins": {"A.X7": "TOP_RAIL", "K.X2": None}})
        self.assertEqual((a.X_NET["A"][7], a.X_NET["D"][1], a.X_NET["K"][2]), ("TOP_RAIL", None, None))
        self.assertEqual(fabric_v5.X_NET["A"][7], "/AD1")               # the base is never written to
        self.assertEqual(V5.X_NET["A"][7], "/AD1")
        self.assertEqual(a.changed, [("A", "X", 7), ("D", "X", 1), ("K", "X", 2)])
        self.assertEqual(a.taken, [("D", "X", 1), ("K", "X", 2)])
        self.assertEqual((a.dropped, 139 in a.NODE_NET), ([139], False))        # BUF_IN had that one pin: the node is gone
        self.assertEqual(V5.dropped, [])
        # the same file with the feed left on the fabric is a mistake: the feed's node has no pin
        self.assertTrue(any("139" in p or "BUF_IN" in p for p in arrangement.check({"base": "v5", "pins": {"K.X2": None}})))
        # and half a lane is one too: A.X7 moved, /AD1 left on D alone
        self.assertTrue(any("/AD1" in p for p in arrangement.check({"base": "v5", "pins": {"A.X7": "TOP_RAIL"}})))

    def test_a_node_wire_may_lose_one_of_its_pins(self):
        # GND has a pin on K and one on L: giving one up is a design, not half a lane
        a = arrangement.parse("t", {"base": "v5", "pins": {"L.X15": None}})
        self.assertEqual((a.taken, a.dropped, 100 in a.NODE_NET), ([("L", "X", 15)], [], True))

    def test_the_router_can_run_only_v5_with_pins_taken_away(self):
        gone = arrangement.parse("t", {"base": "v5", "feed": False, "remove": ["KL", "/AB1"]})
        self.assertEqual(sorted(gone.taken), [("A", "X", 3), ("B", "X", 1), ("K", "X", 12), ("L", "X", 14)])
        self.assertEqual(sorted(arrangement.blocks(gone)), [("X", 0, 3), ("X", 1, 1), ("X", 10, 12), ("X", 11, 14)])
        self.assertIsNone(arrangement.why_not_router(gone))
        self.assertIs(gone.feed, False)
        rewired = arrangement.parse("t", {"base": "v5", "remove": ["/AD1"], "pins": {"A.X7": "TOP_RAIL"}})
        self.assertIsNone(arrangement.blocks(rewired))
        self.assertIn("A.X7", arrangement.why_not_router(rewired))
        self.assertIn("TOP_RAIL", arrangement.why_not_router(rewired))
        freed = arrangement.parse("t", {"base": "v5", "feed": False, "pins": {"K.X2": None}})     # a dropped node is no obstacle
        self.assertEqual(arrangement.blocks(freed), [("X", 10, 2)])

    def test_the_router_is_not_given_a_pin_the_firmware_still_routes_to(self):     # final review, 1
        # GND keeps its pin on L, so the firmware still has GND as a node and goes on closing its pin on K, blocked or not
        one_gnd = arrangement.parse("gnd_on_l", {"base": "v5", "feed": False, "pins": {"K.X15": None}})
        self.assertEqual(arrangement.check(one_gnd.data), [])                  # a good arrangement all the same: the solver's
        self.assertIsNone(arrangement.blocks(one_gnd))
        why = arrangement.why_not_router(one_gnd)
        self.assertIn("K.X15", why)
        self.assertIn("GND", why)
        gone = arrangement.parse("no_rail", {"base": "v5", "feed": False, "pins": {"K.X4": None}})    # TOP_RAIL's only pin:
        self.assertEqual((arrangement.blocks(gone), gone.dropped), ([("X", 10, 4)], [101]))           # the node is gone with it

    def test_the_feed_on_the_fabric_needs_both_its_ends(self):                 # final review, 1 (its second instance)
        # with DAC0's one pin taken away, the firmware still feeds the probe from DAC0 and closes that pin
        problems = arrangement.check({"base": "v5", "pins": {"K.X7": None}})
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("DAC0", problems[0])
        self.assertIn('"feed": false', problems[0])
        self.assertEqual(arrangement.check({"base": "v5", "feed": False, "pins": {"K.X7": None}}), [])
        self.assertEqual(arrangement.check({"base": "v5", "pins": {"K.X6": None}}), [])     # DAC1 is no end of the feed
        # nor is DAC0 the only other end: with DAC0 out of the probe's window the firmware feeds from the highest free GPIO
        for gpio in range(1, 9):
            pin = "L.X%d" % fabric_v5.X_NET["L"].index(fabric_v5.NODE_NET[130 + gpio])
            problems = arrangement.check({"base": "v5", "pins": {pin: None}})
            self.assertEqual(len(problems), 1, (pin, problems))
            self.assertIn("GPIO_%d" % gpio, problems[0])
            self.assertIn("DAC0 is not free", problems[0])              # a bridge on DAC0 moves the feed too (round 2, V1)
            self.assertEqual(arrangement.check({"base": "v5", "feed": False, "pins": {pin: None}}), [])

    def test_the_feed_is_not_forced_onto_copper_that_has_no_end_for_it(self):     # verification, F5: arrangement score's other side
        no_dac0 = arrangement.parse("no_dac0", {"base": "v5", "feed": False, "pins": {"K.X7": None}})
        with self.assertRaises(arrangement.Bad) as cm:
            arrangement.with_feed(no_dac0, True)
        self.assertIn("DAC0", cm.exception.problems[0])
        self.assertIn("no_dac0", cm.exception.problems[0])               # it names the copper, and does not tell its file
        self.assertNotIn('say "feed": false', cm.exception.problems[0])  # to say what it already says (round 2, V1)
        self.assertIs(arrangement.with_feed(no_dac0, False), no_dac0)
        self.assertTrue(arrangement.with_feed(arrangement.load("v6_feed_off"), True).feed)

    def test_a_remove_entry_that_is_no_name_is_listed_not_raised(self):        # final review, 3 (Review Focus 1)
        for odd in ([["KL"]], [{"wire": "KL"}], [7], [None]):
            problems = arrangement.check({"base": "v5", "remove": odd})
            self.assertEqual(len(problems), 1, odd)
            self.assertIn('"remove"', problems[0])
        with self.assertRaises(arrangement.Bad):
            arrangement.load(self.write("oops.json", '{"base": "v5", "remove": [["KL"]]}'))
        # and whatever else may be wrong with a file, load says Bad: the page lists the file, and nothing else stops
        with mock.patch.object(arrangement, "_build", side_effect=TypeError("unhashable type")):
            with self.assertRaises(arrangement.Bad) as cm:
                arrangement.load(self.write("odd.json", '{"base": "v5"}'))
        self.assertIn("TypeError", cm.exception.problems[0])

    def test_a_new_wire_on_one_pin_that_is_no_nodes_is_taken_for_a_misspelling(self):     # final review, a smaller item
        typo = {"base": "v5", "feed": False, "remove": ["/AD1"], "pins": {"A.X7": "TOP_RIAL"}}
        problems = arrangement.check(typo)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("TOP_RIAL", problems[0])
        self.assertIn("A.X7", problems[0])
        meant = dict(typo, nodes={"150": {"wire": "TOP_RIAL", "name": "PORT"}})         # a node's own wire may be one pin
        self.assertEqual(arrangement.check(meant), [])
        self.assertEqual(arrangement.check(dict(typo, pins={"A.X7": "TOP_RAIL"})), [])

    def test_a_bounce_row_of_a_new_name_is_no_misspelling(self):        # verification, F3/R: one-pin rows on a Y pin are a shape V5 has
        renamed = {"base": "v5", "feed": False, "pins": {"A.Y0": "A_BOUNCE"}}
        self.assertEqual(arrangement.check(renamed), [])
        ninth = {"base": "v5", "feed": False, "remove": ["/AD1"], "pins": {"A.X7": "AM", "D.X1": "AM"},
                 "chips": {"M": {"role": "bb", "x": ["AM"] + [None] * 15, "y": ["M_BOUNCE"] + ["M%d" % r for r in range(1, 8)]}},
                 "nodes": {str(200 + r): {"wire": "M%d" % r} for r in range(1, 8)}}
        self.assertEqual(arrangement.check(ninth), [])
        # V6_CROSSBAR_MATRIX A2: a bounce hub N, eight no-connect rows, two lanes to every breadboard chip
        second = ["/AB1", "/CD1", "/EF1", "/GH1", "/AC1", "/BD1", "/EG1", "/FH1"]
        freed = {}
        for lane in second:
            for chip in lane[1:3]:
                freed.setdefault(chip, []).append(fabric_v5.X_NET[chip].index(lane))
        n_x = []
        pins = {}
        for chip in "ABCDEFGH":
            for k, x in enumerate(freed[chip][:2]):
                pins["%s.X%d" % (chip, x)] = "N_%s%d" % (chip, k)
                n_x.append("N_%s%d" % (chip, k))
        hub = {"base": "v5", "feed": False, "remove": second, "pins": pins,
               "chips": {"N": {"role": "sf", "x": n_x, "y": ["N_ROW%d" % r for r in range(8)]}}}
        self.assertEqual(arrangement.check(hub), [])

    def test_a_misspelling_in_a_new_chips_own_x_list_is_caught(self):  # verification round 2, V3
        m = {"role": "sf", "x": ["TOP_RAIL", "BOTTOM_RIAL", "GND"] + [None] * 13, "y": [c + "M" for c in "ABCDEFGH"]}
        lanes = ["/%s1" % p for p in ("AB", "CD", "EF", "GH")]
        a1 = {"base": "v5", "feed": False, "chips": {"M": m}, "remove": lanes,
              "pins": {"%s.X%d" % (c, fabric_v5.X_NET[c].index("/%s1" % p)): c + "M" for p in ("AB", "CD", "EF", "GH") for c in p}}
        problems = arrangement.check(a1)
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("BOTTOM_RIAL", problems[0])
        a1["chips"]["M"]["x"][1] = "BOTTOM_RAIL"
        self.assertEqual(arrangement.check(a1), [])

    def test_a_slip_on_a_y_pin_is_caught_when_it_is_plainly_one(self):  # verification round 2, V3
        for slip in ("29 ", " GND", "TOP_RIAL"):
            problems = arrangement.check({"base": "v5", "feed": False, "pins": {"K.X0": None, "A.Y0": slip}})
            self.assertTrue(any(slip.strip() in p for p in problems), (slip, problems))
        self.assertEqual(arrangement.check({"base": "v5", "feed": False, "pins": {"A.Y0": "A_BOUNCE"}}), [])

    def test_what_round_three_found_in_the_misspelling_rule(self):      # verification round 3, W2
        lanes = ["/%s1" % p for p in ("AB", "CD", "EF", "GH")]
        pins = {"%s.X%d" % (c, fabric_v5.X_NET[c].index("/%s1" % p)): c + "M" for p in ("AB", "CD", "EF", "GH") for c in p}
        spare = ["unconnected-(M1-X%d-Pad%d)" % (x, 20 + x) for x in range(3, 16)]      # V5's own way to name a no-connect
        a1 = {"base": "v5", "feed": False, "remove": lanes, "pins": pins,
              "chips": {"M": {"role": "sf", "x": ["TOP_RAIL", "BOTTOM_RAIL", "GND"] + spare, "y": [c + "M" for c in "ABCDEFGH"]}}}
        self.assertEqual(arrangement.check(a1), [])
        for bounce in ("AY0", "DY0"):                                   # exactly as like A0 or D0 as the cutoff: no slip
            self.assertEqual(arrangement.check({"base": "v5", "feed": False, "pins": {bounce[0] + ".Y0": bounce}}), [], bounce)
        hub = {"base": "v5", "feed": False, "chips": {"N": {"role": "sf", "x": [None] * 16, "y": ["N1%d" % r for r in range(8)]}}}
        self.assertEqual(arrangement.check(hub), [])
        spaced = {"base": "v5", "feed": False, "chips": {"M": {"role": "sf", "x": [" PORT_0"] + [None] * 15, "y": [None] * 8}},
                  "nodes": {"150": {"wire": " PORT_0"}}}
        self.assertTrue(any("spaces" in p for p in arrangement.check(spaced)), arrangement.check(spaced))

    def test_every_problem_is_listed_and_kept_short(self):             # verification round 2, V3 (disputed, cheap)
        both = self.write("both.json", '{"base": "v5", "feed": false, "feed": false, "pins": {"A.X7": "TOP_RIAL", "Q.X1": null}}')
        with self.assertRaises(arrangement.Bad) as cm:
            arrangement.load(both)
        text = " ".join(cm.exception.problems)
        for part in ('"feed"', "TOP_RIAL", "Q.X1"):
            self.assertIn(part, text)
        thrice = self.write("thrice.json", '{"base": "v5", "base": "v5", "base": "v5"}')
        with self.assertRaises(arrangement.Bad) as cm:
            arrangement.load(thrice)
        self.assertEqual(len(cm.exception.problems), 1)
        deep = {"base": "v5", "about": [], "pins": {"A.X7": "TOP_RIAL"}}
        inner = deep["about"]
        for _ in range(600):
            inner.append([])
            inner = inner[0]
        problems = arrangement.check(deep)
        self.assertTrue(any('"about"' in p for p in problems) and any("TOP_RIAL" in p for p in problems), problems)
        two = self.write("two.json", '{"base": "v5", "feed": false, "chips": {"M": {"role": "sf", "role": "sf", "x": [], "y": []}, '
                                     '"N": {"role": "sf", "role": "sf", "x": [], "y": []}}}')
        with self.assertRaises(arrangement.Bad) as cm:                  # one line for each object with a key given twice
            arrangement.load(two)
        self.assertEqual(sum("twice" in p for p in cm.exception.problems), 2, cm.exception.problems)
        long_key = "k" * 5000
        for odd in ({"chips": {"M": {"role": "sf", "x": [None] * 16, "y": [None] * 8, long_key: 1}}},
                    {"nodes": {"150": {"wire": "1", long_key: 1}}}, {long_key: 1}, {"chips": {long_key: {}}}):
            self.assertTrue(all(len(p) < 300 for p in arrangement.check(dict({"base": "v5", "feed": False}, **odd))))

    def test_a_key_given_twice_in_a_file_is_listed(self):               # verification, F3: JSON keeps the last silently
        twice = self.write("twice.json", '{"base": "v5", "feed": false, "pins": {"A.X7": "TOP_RAIL"}, "pins": {"K.X2": null}}')
        with self.assertRaises(arrangement.Bad) as cm:
            arrangement.load(twice)
        self.assertTrue(any('"pins"' in p and "twice" in p for p in cm.exception.problems), cm.exception.problems)
        inner = self.write("inner.json", '{"base": "v5", "feed": false, "remove": ["/AD1"], '
                                         '"pins": {"A.X7": "TOP_RAIL", "A.X7": "BOTTOM_RAIL"}}')
        with self.assertRaises(arrangement.Bad) as cm:
            arrangement.load(inner)
        self.assertTrue(any('"A.X7"' in p for p in cm.exception.problems), cm.exception.problems)
        deep = self.write("deep.json", '{"base": "v5", "about": ' + "[" * 20000 + "]" * 20000 + "}")
        with self.assertRaises(arrangement.Bad):                        # far too deep for the JSON reader: still the file's problem
            arrangement.load(deep)

    def test_pins_and_nodes_are_written_one_way_only(self):            # verification, F3: look-alikes and odd values
        for odd in ({"pins": {"A.X07": None}}, {"pins": {"A.X٧": None}}, {"pins": {"A.X" + "1" * 5000: None}},
                    {"nodes": {"0150": {"wire": "1"}}}, {"nodes": {"1" * 5000: None}}):
            problems = arrangement.check(dict({"base": "v5", "feed": False}, **odd))
            self.assertEqual(len(problems), 1, (odd, problems))
        for odd, word in (({"about": {"k": 1}}, '"about"'), ({"nodes": {"150": {"wire": "1", "nmae": "P"}}}, "nmae"),
                          ({"nodes": {"150": {"wire": "1", "name": 7}}}, "name"),
                          ({"chips": {"M": {"role": "sf", "x": [None] * 16, "y": [None] * 8, "rotate": 90}}}, "rotate")):
            problems = arrangement.check(dict({"base": "v5", "feed": False}, **odd))
            self.assertTrue(problems and any(word in p for p in problems), (odd, problems))
        self.assertEqual(arrangement.check({"base": "v5", "feed": False, "nodes": {"150": {"wire": "1", "name": "P"}}}), [])

    def test_a_chip_and_a_node_added_and_a_node_removed(self):
        m = {"role": "sf", "x": ["TOP_RAIL", "BOTTOM_RAIL", "GND", "PORT_0"] + [None] * 12, "y": ["AM", "BM"] + [None] * 6}
        a = arrangement.parse("t", {"base": "v5", "feed": False, "chips": {"M": m}, "remove": ["/AD1", "/BD1"],
                                    "pins": {"A.X7": "AM", "B.X7": "BM"},
                                    "nodes": {"150": {"wire": "PORT_0", "name": "PORT_0"}, "139": None}})
        self.assertEqual((a.CHIPS, a.ROLE["M"], a.Y_NET["M"][:2]), ("ABCDEFGHIJKLM", "sf", ["AM", "BM"]))
        self.assertEqual((a.NODE_NET[150], a.NODE_NAME[150], 139 in a.NODE_NET), ("PORT_0", "PORT_0", False))
        self.assertEqual(len([p for p in a.changed if p[0] == "M"]), 24)        # every pin of a new chip is a change
        self.assertIsNone(arrangement.blocks(a))
        self.assertIn("M", arrangement.why_not_router(a))

    def test_what_is_wrong_with_a_file_is_listed_by_name(self):                # Review Focus 1
        bad = {"base": "v9", "feeed": True, "remove": ["NO_SUCH_WIRE"],
               "pins": {"A.X16": "x", "Q.Y1": "y", "A.Z1": "z", "A.X2": 5, "A.X3": None},
               "chips": {"A": {"role": "bb", "x": [None] * 16, "y": [None] * 8}, "mm": {}, "N": {"role": "hub", "x": [], "y": []}},
               "nodes": {"1": {"wire": "NOWHERE"}, "one": None}}
        problems = arrangement.check(bad)
        for part in ("v9", "feeed", "NO_SUCH_WIRE", "A.X16", "Q.Y1", "A.Z1", "A.X2", "/AB1", "chip A", "mm", "hub", "16", "node 1", "one"):
            self.assertTrue(any(part in p for p in problems), (part, problems))
        with self.assertRaises(arrangement.Bad) as cm:
            arrangement.parse("t", bad)
        self.assertEqual(cm.exception.problems, problems)
        self.assertEqual(arrangement.check({"base": "v5"}), [])
        self.assertEqual(arrangement.check({"base": "v5", "remove": ["/AB1"]}), [])      # both ends go: no half lane
        self.assertTrue(arrangement.check(["base", "v5"]))                     # not an object at all
        self.assertTrue(arrangement.check({"base": "v5", "pins": ["A.X1"]}))   # a key of the wrong shape

    def test_the_shipped_arrangements(self):
        self.assertEqual(arrangement.names()[0], "v5")
        self.assertLessEqual({"v6_feed_off", "v6_rails_on_chips"}, set(arrangement.names()))
        off = arrangement.load("v6_feed_off")
        self.assertEqual((off.name, off.feed, off.changed, arrangement.blocks(off)), ("v6_feed_off", False, [], []))
        rails = arrangement.load("v6_rails_on_chips")
        self.assertEqual((rails.feed, len(rails.changed), rails.taken), (False, 24, []))
        for chip in "ABCDEFGH":
            freed = [w for w, was in zip(rails.X_NET[chip], fabric_v5.X_NET[chip]) if w != was]
            self.assertEqual(freed, ["TOP_RAIL", "BOTTOM_RAIL", "GND"], chip)
        self.assertIsNone(arrangement.blocks(rails))
        self.assertTrue(rails.about and off.about)

    def test_a_file_that_is_missing_or_not_json(self):
        for name in ("no_such_arrangement", self.write("broken.json", '{"base": ')):
            with self.assertRaises(arrangement.Bad) as cm:
                arrangement.load(name)
            self.assertEqual(len(cm.exception.problems), 1)
        good = self.write("mine.json", '{"base": "v5", "feed": false, "remove": ["KL"]}')
        self.assertEqual((arrangement.load(good).name, len(arrangement.load(good).taken)), ("mine", 2))


if __name__ == "__main__":
    unittest.main()
