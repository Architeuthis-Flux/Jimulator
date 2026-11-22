# SPDX-License-Identifier: MIT
import hashlib
import json
import unittest

import arrangement
import fabric_view
from cases import fabric_v5


class FabricView(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v = fabric_view.layout()

    def test_every_wire_and_chip_is_drawn(self):
        names = {n for c in fabric_v5.CHIPS for n in fabric_v5.X_NET[c] + fabric_v5.Y_NET[c]}
        self.assertEqual(set(self.v["wires"]), names)
        self.assertEqual(set(self.v["chips"]), set(fabric_v5.CHIPS))
        self.assertEqual({c["role"] for k, c in self.v["chips"].items() if k in "ABCDEFGH"}, {"bb"})
        self.assertEqual({c["role"] for k, c in self.v["chips"].items() if k in "IJKL"}, {"sf"})

    def test_a_wire_touches_every_pin_it_has(self):
        for chip in fabric_v5.CHIPS:
            for axis, nets in (("X", fabric_v5.X_NET[chip]), ("Y", fabric_v5.Y_NET[chip])):
                for pin, name in enumerate(nets):
                    self.assertTrue(fabric_view.touches(self.v["wires"][name]["d"],
                                                        fabric_view.pin_point(self.v, chip, axis, pin)),
                                    (chip, axis, pin, name))

    def test_a_wire_runs_through_its_row_or_column_of_the_grid(self):
        # so a crosspoint's dot, at the centre of its cell, sits on both of its wires
        cell = self.v["cell"]
        for chip in fabric_v5.CHIPS:
            c = self.v["chips"][chip]
            for x in (0, 7, 15):
                for y in (0, 3, 7):
                    centre = (c["x"] + cell // 2 + cell * x, c["y"] + cell // 2 + cell * y)
                    self.assertTrue(fabric_view.touches(self.v["wires"][fabric_v5.X_NET[chip][x]]["d"], centre))
                    self.assertTrue(fabric_view.touches(self.v["wires"][fabric_v5.Y_NET[chip][y]]["d"], centre))

    def test_no_two_wires_share_a_track(self):
        self.assertEqual(fabric_view.overlaps(self.v), [])      # collinear overlapping segments of different wires

    def test_wires_are_orthogonal(self):
        for name, w in self.v["wires"].items():
            for (x1, y1), (x2, y2) in fabric_view.segments(w["d"]):
                self.assertTrue(x1 == x2 or y1 == y2, name)

    def test_chips_do_not_overlap_and_fit(self):
        cell = self.v["cell"]
        boxes = [(c["x"], c["y"], c["x"] + 16 * cell, c["y"] + 8 * cell) for c in self.v["chips"].values()]
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                self.assertTrue(a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])
        w, h = self.v["size"]
        self.assertTrue(all(0 <= x0 and x1 <= w and 0 <= y0 and y1 <= h for x0, y0, x1, y1 in boxes))
        for name, wire in self.v["wires"].items():
            for p, q in fabric_view.segments(wire["d"]):
                for x, y in (p, q):
                    self.assertTrue(0 <= x <= w and 0 <= y <= h, name)

    def test_every_node_has_a_pad_on_its_wire(self):
        self.assertEqual(set(self.v["pads"]), set(fabric_v5.NODE_NET.values()))
        self.assertEqual(len([p for p in self.v["pads"].values() if p["group"] == "row"]), 60)
        for name, pad in self.v["pads"].items():
            self.assertTrue(fabric_view.touches(self.v["wires"][name]["d"], (pad["x"], pad["y"])), name)
        self.assertEqual(self.v["pads"]["GND"]["label"], "GND")
        self.assertEqual(self.v["pads"]["GPIO_20"]["label"], "GPIO_1")       # the firmware's name, not KiCad's
        points = [(p["x"], p["y"]) for p in self.v["pads"].values()]
        self.assertEqual(len(set(points)), len(points))

    def test_helpers(self):
        d = "M 0,0 L 10,0 L 10,20 M 30,5 L 40,5"
        self.assertEqual(fabric_view.segments(d), [((0, 0), (10, 0)), ((10, 0), (10, 20)), ((30, 5), (40, 5))])
        self.assertTrue(fabric_view.touches(d, (10, 13)))
        self.assertFalse(fabric_view.touches(d, (20, 5)))


V5_DRAWING = "539a967c686fbfe54ee71e216468f95265ba5d1bb8a1d51116d63275dffb2566"     # layout() as it was before arrangements


def lane_pin(chip, name):
    return "%s.X%d" % (chip, fabric_v5.X_NET[chip].index(name))


def buses():
    """Four wires of a shape V5 has none of, each on a pin of chip A, of chip E and of chip K: BUS_0 to BUS_2 on X
    pins (K's are its hub lanes'), BUS_3 on A's row 1, an X pin of E and K's row 3."""
    pins = {"A.Y1": "BUS_3", lane_pin("E", "/DE0"): "BUS_3", "K.Y3": "BUS_3"}
    for n, (a_lane, e_lane, k_pin) in enumerate((("/AB0", "/EF0", "K.X12"), ("/AC0", "/EG0", "K.X13"), ("/AD0", "/EH0", "K.X14"))):
        pins.update({lane_pin("A", a_lane): "BUS_%d" % n, lane_pin("E", e_lane): "BUS_%d" % n, k_pin: "BUS_%d" % n})
    return arrangement.parse("buses", {"base": "v5", "feed": False, "pins": pins, "remove": [
        "/AB0", "/EF0", "KL", "/AC0", "/EG0", "IK", "/AD0", "/EH0", "JK", "/DE0", "DK"]})


class AnyArrangement(unittest.TestCase):
    def sound(self, view, a):
        """What every drawing must hold, whatever the arrangement."""
        self.assertEqual(fabric_view.overlaps(view), [])
        w, h = view["size"]
        for name, wire in view["wires"].items():
            for (x1, y1), (x2, y2) in fabric_view.segments(wire["d"]):
                self.assertTrue(x1 == x2 or y1 == y2, name)
                self.assertTrue(0 <= min(x1, x2) and max(x1, x2) <= w and 0 <= min(y1, y2) and max(y1, y2) <= h, name)
        for chip in a.CHIPS:
            self.assertIn(chip, view["chips"])
            for axis, nets in (("X", a.X_NET[chip]), ("Y", a.Y_NET[chip])):
                for pin, name in enumerate(nets):
                    if name is not None:
                        self.assertTrue(fabric_view.touches(view["wires"][name]["d"], fabric_view.pin_point(view, chip, axis, pin)),
                                        (chip, axis, pin, name))
        self.assertEqual(set(view["wires"]), set(a.pins()))               # a wire with no pin left is not drawn
        for name in set(a.NODE_NET.values()) & set(view["wires"]):       # every node there is has a pad on its wire
            pad = view["pads"][name]
            self.assertTrue(fabric_view.touches(view["wires"][name]["d"], (pad["x"], pad["y"])), name)
        points = [(p["x"], p["y"]) for p in view["pads"].values()]
        self.assertEqual(len(set(points)), len(points))

    def test_v5_is_drawn_exactly_as_before(self):
        for view in (fabric_view.layout(), fabric_view.layout(arrangement.V5)):
            drawn = {k: v for k, v in view.items() if k not in ("taken", "changed")}
            self.assertEqual(hashlib.sha256(json.dumps(drawn, sort_keys=True).encode()).hexdigest(), V5_DRAWING)
            self.assertEqual((view["taken"], view["changed"]), ([], []))
        off = fabric_view.layout(arrangement.load("v6_feed_off"))       # the same copper: the same drawing
        self.assertEqual({k: v for k, v in off.items()}, fabric_view.layout())

    def test_a_rail_on_nine_pins_is_drawn_and_crosses_no_other_track(self):     # Review Focus 7
        rails = arrangement.load("v6_rails_on_chips")
        view = fabric_view.layout(rails)
        self.assertEqual(fabric_view.overlaps(view), [])
        self.assertEqual(len(view["changed"]), 24)
        for wire in ("TOP_RAIL", "BOTTOM_RAIL", "GND"):
            pins = [(c, "X", x) for c in rails.CHIPS for x, w in enumerate(rails.X_NET[c]) if w == wire]
            self.assertGreaterEqual(len(pins), 9)
            for chip, axis, pin in pins:
                self.assertTrue(fabric_view.touches(view["wires"][wire]["d"], fabric_view.pin_point(view, chip, axis, pin)), (wire, chip, pin))
        self.assertNotIn("/AD1", view["wires"])
        self.sound(view, rails)
        self.assertEqual(view["wires"]["TOP_RAIL"]["kind"], "bus")
        self.assertEqual(view["pads"]["TOP_RAIL"]["label"], "TOP_RAIL")
        self.assertGreater(view["size"][1], fabric_view.layout()["size"][1])       # the buses' band is made room for

    def test_pins_taken_away_and_a_chip_added(self):
        without = arrangement.parse("t", {"base": "v5", "remove": ["KL", "/AB1"]})
        gone = fabric_view.layout(without)
        self.assertEqual(len(gone["taken"]), 4)
        self.assertIn({"chip": "K", "axis": "X", "pin": 12}, gone["taken"])
        self.assertFalse({"KL", "/AB1"} & set(gone["wires"]))
        self.assertEqual(fabric_view.overlaps(gone), [])
        self.sound(gone, without)
        m = {"role": "sf", "x": ["TOP_RAIL", "BOTTOM_RAIL", "GND"] + [None] * 13, "y": [c + "M" for c in "ABCDEFGH"]}
        wider = arrangement.parse("t", {"base": "v5", "chips": {"M": m}, "remove": ["/%s1" % p for p in ("AB", "CD", "EF", "GH")],
                                        "pins": {"%s.X%d" % (c, fabric_v5.X_NET[c].index("/%s1" % p)): c + "M"
                                                 for p in ("AB", "CD", "EF", "GH") for c in p}})
        view = fabric_view.layout(wider)
        self.assertEqual((view["chips"]["M"]["role"], fabric_view.overlaps(view)), ("sf", []))
        self.assertGreater(view["size"][0], fabric_view.layout()["size"][0])
        self.assertEqual(len({(c["x"], c["y"]) for c in view["chips"].values()}), 13)
        self.sound(view, wider)

    def test_wires_of_a_shape_never_seen_get_levels_of_their_own(self):         # Review Focus 7
        a = buses()
        view = fabric_view.layout(a)
        self.sound(view, a)
        self.assertGreater(view["size"][1], fabric_view.layout()["size"][1])
        self.assertEqual([view["wires"]["BUS_%d" % n]["kind"] for n in range(4)], ["bus"] * 4)
        self.assertNotIn("1", view["wires"])                              # row 1 gave its pin up
        self.assertNotIn("1", view["pads"])


if __name__ == "__main__":
    unittest.main()
