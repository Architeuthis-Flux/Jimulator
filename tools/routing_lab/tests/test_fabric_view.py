# SPDX-License-Identifier: MIT
import unittest

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


if __name__ == "__main__":
    unittest.main()
