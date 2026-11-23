# SPDX-License-Identifier: MIT
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sheet
from cases import fabric_v5

MINI = '''(kicad_sch (paper "A4")
  (lib_symbols (symbol "X:CH446Q" (symbol "CH446Q_1_1"
    (rectangle (start -10 10) (end 10 -10))
    (pin bidirectional line (at 15 5 180) (length 5) (name "X0") (number "1"))
    (pin bidirectional line (at 15 -5 180) (length 5) (name "Y1") (number "2")))))
  (symbol (lib_id "X:CH446Q") (at 100 100 0) (property "Reference" "A2" (at 0 0 0)))
  (symbol (lib_id "X:CH446Q") (at 200 100 0) (mirror y) (property "Reference" "B1" (at 0 0 0)))
  (symbol (lib_id "Device:R") (at 300 100 0) (property "Reference" "R5" (at 0 0 0)))
  (wire (pts (xy 115 95) (xy 150 95)))
  (wire (pts (xy 150 95) (xy 150 60)))
  (wire (pts (xy 185 95) (xy 150 95)))
  (junction (at 150 95))
  (label "AB0" (at 150 70 0))
  (wire (pts (xy 115 105) (xy 130 105)))
  (global_label "1" (at 130 105 0))
  (wire (pts (xy 400 400) (xy 420 400)))
  (global_label "SOMETHING_ELSE" (at 420 400 0)))'''


class Sheet(unittest.TestCase):
    def write(self, text):
        f = tempfile.NamedTemporaryFile("w", suffix=".kicad_sch", delete=False)
        f.write(text)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return Path(f.name)

    def test_sexpr(self):
        self.assertEqual(sheet.parse_sexpr('(a "b c" (d 1.5) e)'), ["a", "b c", ["d", "1.5"], "e"])
        self.assertEqual(sheet.parse_sexpr('(a "say \\"hi\\" (now)" ())'), ["a", 'say "hi" (now)', []])

    def test_pin_point_rotations_and_mirror(self):
        self.assertEqual(sheet.pin_point((100, 100, 0), None, (15, 5)), (115, 95))       # library y is up
        self.assertEqual(sheet.pin_point((100, 100, 180), None, (15, 5)), (85, 105))
        self.assertEqual(sheet.pin_point((100, 100, 90), None, (15, 5)), (95, 85))
        self.assertEqual(sheet.pin_point((100, 100, 270), None, (15, 5)), (105, 115))
        self.assertEqual(sheet.pin_point((200, 100, 0), "y", (15, 5)), (185, 95))
        self.assertEqual(sheet.pin_point((200, 100, 0), "x", (15, 5)), (215, 105))
        # turned and mirrored: the turn first, then the flip across the sheet's own axis (r7's own
        # symbols placed this way land their pins on wire ends only in this order)
        self.assertEqual(sheet.pin_point((100, 100, 90), "y", (15, 5)), (105, 85))
        self.assertEqual(sheet.pin_point((100, 100, 90), "x", (15, 5)), (95, 115))
        self.assertEqual(sheet.pin_point((100, 100, 270), "y", (15, 5)), (95, 115))
        self.assertEqual(sheet.pin_point((100, 100, 270), "x", (15, 5)), (105, 85))
        self.assertEqual(sheet.pin_point((100, 100, 180), "y", (15, 5)), (115, 105))

    def test_a_junction_joins_a_wire_that_ends_on_the_middle_of_another(self):
        # the stub from A.X0 ends on the middle of a long wire; only the junction makes them one net
        text = MINI.split("  (wire", 1)[0] + '''
  (wire (pts (xy 115 95) (xy 150 95)))
  (wire (pts (xy 150 60) (xy 150 120)))
  (junction (at 150 95))
  (wire (pts (xy 185 95) (xy 170 95)))
  (wire (pts (xy 170 60) (xy 170 120))))'''
        with mock.patch.object(sheet.fabric_v5, "X_NET", {"A": ["/AB0"], "B": ["/BX"]}), \
             mock.patch.object(sheet.fabric_v5, "Y_NET", {"A": ["x", "1"], "B": ["x", "8"]}), \
             mock.patch.object(sheet.fabric_v5, "CHIPS", "AB"):
            o = sheet.overlay(self.write(text))
        self.assertEqual(len(o["nets"]["/AB0"]["segments"]), 2)        # joined at the junction
        self.assertEqual(len(o["nets"]["/BX"]["segments"]), 1)         # crossing with no junction: not joined

    def test_overlay_of_a_small_sheet(self):
        with mock.patch.object(sheet.fabric_v5, "X_NET", {"A": ["/AB0"], "B": ["/AB0"]}), \
             mock.patch.object(sheet.fabric_v5, "Y_NET", {"A": ["x", "1"], "B": ["x", "8"]}), \
             mock.patch.object(sheet.fabric_v5, "CHIPS", "AB"):
            o = sheet.overlay(self.write(MINI))
        self.assertEqual(o["size"], [297.0, 210.0])                                       # A4, landscape
        self.assertEqual(o["pins"]["A.X0"], [115, 95])
        self.assertEqual(o["pins"]["B.X0"], [185, 95])
        self.assertEqual(sorted(o["pins"]), ["A.X0", "A.Y1", "B.X0", "B.Y1"])
        self.assertEqual(len(o["nets"]["/AB0"]["segments"]), 3)
        self.assertEqual(o["nets"]["/AB0"]["labels"], [[150, 70]])
        self.assertEqual(o["nets"]["1"]["segments"], [[115, 105, 130, 105]])
        self.assertEqual(o["nets"]["1"]["labels"], [[130, 105]])
        self.assertEqual(o["bodies"], {"A": [90, 90, 110, 110], "B": [190, 90, 210, 110]})
        self.assertNotIn("SOMETHING_ELSE", o["nets"])                                     # not a fabric net

    def test_a_lane_drawn_as_a_bus_is_followed_between_its_two_entries(self):
        # r7 draws the breadboard-to-breadboard lanes as stubs that enter a shared bus
        text = MINI.split("  (wire", 1)[0] + '''
  (wire (pts (xy 115 95) (xy 120 95)))
  (label "AB0" (at 120 95 0))
  (bus_entry (at 120 95) (size 2 -2))
  (bus (pts (xy 122 100) (xy 122 60)))
  (bus (pts (xy 122 60) (xy 178 60)))
  (bus (pts (xy 178 60) (xy 178 100)))
  (bus (pts (xy 122 60) (xy 122 40)))
  (wire (pts (xy 185 95) (xy 180 95)))
  (label "AB0" (at 180 95 0))
  (bus_entry (at 180 95) (size -2 -2)))'''
        with mock.patch.object(sheet.fabric_v5, "X_NET", {"A": ["/AB0"], "B": ["/AB0"]}), \
             mock.patch.object(sheet.fabric_v5, "Y_NET", {"A": ["x", "1"], "B": ["x", "8"]}), \
             mock.patch.object(sheet.fabric_v5, "CHIPS", "AB"):
            o = sheet.overlay(self.write(text))
        drawn = {tuple(sorted([(s[0], s[1]), (s[2], s[3])])) for s in o["nets"]["/AB0"]["segments"]}
        self.assertEqual(drawn, {
            ((115, 95), (120, 95)), ((180, 95), (185, 95)),                        # the two stubs
            ((120, 95), (122, 93)), ((178, 93), (180, 95)),                        # the two bus entries
            ((122, 60), (122, 93)), ((122, 60), (178, 60)), ((178, 60), (178, 93)),  # the bus between them, no more
        })

    def test_a_wire_is_followed_past_the_crossbar(self):
        # what a wire's signal becomes past the fabric: a labelled net after a stage, copper with no label found by
        # a point on it, and a second label on the wire's own copper read as the wire
        text = MINI[:-1] + '''
  (wire (pts (xy 500 100) (xy 520 100)))
  (global_label "FAR" (at 520 100 0))
  (wire (pts (xy 500 120) (xy 520 120)))
  (wire (pts (xy 600 100) (xy 620 100)))
  (global_label "OTHER_NAME" (at 620 100 0)))'''
        table = {"1": [{"net": "FAR", "by": "U1A", "kind": "scale", "way": "out"},
                       {"net": "after U1B", "by": "U1B", "kind": "buffer", "way": "out"},
                       {"net": "NOT_ON_THIS_SHEET", "by": "U9", "kind": "buffer", "way": "out"}],
                 "NOT_A_WIRE_HERE": [{"net": "FAR", "by": "U1A", "kind": "scale", "way": "in"}]}
        with mock.patch.object(sheet.fabric_v5, "X_NET", {"A": ["/AB0"], "B": ["/AB0"]}), \
             mock.patch.object(sheet.fabric_v5, "Y_NET", {"A": ["x", "1"], "B": ["x", "8"]}), \
             mock.patch.object(sheet.fabric_v5, "CHIPS", "AB"), \
             mock.patch.object(sheet, "BEYOND", table), \
             mock.patch.object(sheet, "ANCHOR", {"after U1B": (510, 120)}), \
             mock.patch.object(sheet, "ALIAS", {"OTHER_NAME": "1"}):
            o = sheet.overlay(self.write(text))
        self.assertEqual(o["nets"]["FAR"], {"segments": [[500, 100, 520, 100]], "labels": [[520, 100]]})
        self.assertEqual(o["nets"]["after U1B"]["segments"], [[500, 120, 520, 120]])
        self.assertIn([600, 100, 620, 100], o["nets"]["1"]["segments"])
        self.assertEqual(o["beyond"], {"1": table["1"][:2]})         # only wires of this fabric, and copper this sheet has
        self.assertNotIn("SOMETHING_ELSE", o["nets"])

    def test_the_table_of_what_is_past_the_crossbar_names_v5s_wires(self):
        wires = {n for c in fabric_v5.CHIPS for n in fabric_v5.X_NET[c] + fabric_v5.Y_NET[c]}
        self.assertEqual([w for w in sheet.BEYOND if w not in wires], [])
        for wire, past in sheet.BEYOND.items():
            for t in past:
                self.assertIn(t["kind"], ("same", "buffer", "scale"), wire)
                self.assertIn(t["way"], ("in", "out"), wire)
        named = {t["net"] for past in sheet.BEYOND.values() for t in past}
        self.assertEqual([a for a in sheet.ANCHOR if a not in named], [])       # every point named is used
        # the eleven wires with an op-amp stage: the routable buffer's two, five ADCs, two DACs, the two rails
        staged = sorted(w for w, past in sheet.BEYOND.items() if any(t["kind"] != "same" for t in past))
        self.assertEqual(staged, sorted(["ROUTABLE_BUFFER_IN", "ROUTABLE_BUFFER_OUT", "ADC_UNBUFFERED_5V_4", "DAC_0", "DAC_1",
                                         "TOP_RAIL", "BOTTOM_RAIL"] + ["ADC_UNBUFFERED_+-8V_%d" % n for n in range(4)]))

    @unittest.skipUnless(sheet.DEFAULT_SCH.exists(), "the r7 schematic is not on this machine")
    def test_the_real_sheet_past_the_crossbars(self):
        o = sheet.overlay(sheet.DEFAULT_SCH)
        missing = [(w, t["net"]) for w, past in sheet.BEYOND.items() for t in past
                   if t["net"] not in o["nets"] or t not in o["beyond"].get(w, [])]
        self.assertEqual(missing, [])                                # r7 has all of it
        self.assertEqual([t["net"] for t in o["beyond"]["ADC_UNBUFFERED_+-8V_0"]], ["after U11A", "ADC_BUFFERED_+-8V_0"])
        self.assertGreaterEqual(len(o["nets"]["ADC_BUFFERED_+-8V_0"]["segments"]), 8)
        self.assertGreaterEqual(len(o["nets"]["after U11A"]["segments"]), 4)
        self.assertEqual(o["nets"]["DAC_2_OUT"]["segments"], [])     # drawn as two labels and no wire
        self.assertEqual(len(o["nets"]["DAC_2_OUT"]["labels"]), 2)
        self.assertGreater(len(o["nets"]["DAC_0"]["segments"]), 1)   # with the copper at the shunt, labelled R_SENSE-

    @unittest.skipUnless(sheet.DEFAULT_SCH.exists(), "the r7 schematic is not on this machine")
    def test_the_real_sheet(self):
        o = sheet.overlay(sheet.DEFAULT_SCH)
        self.assertEqual(len(o["pins"]), 288)
        self.assertEqual(len(o["bodies"]), 12)
        self.assertEqual(o["size"], [841.0, 594.0])
        self.assertEqual([n for n in fabric_v5.LANES if n not in o["nets"]], [])          # every lane has copper or a label
        self.assertEqual([str(r) for r in range(1, 61) if str(r) not in o["nets"]], [])
        # r7 is drawn with a label on nearly every crossbar pin and few wires between them
        self.assertGreater(sum(len(n["segments"]) for n in o["nets"].values()), 100)
        self.assertGreater(sum(len(n["labels"]) for n in o["nets"].values()), 300)
        # ... except the 48 breadboard-to-breadboard lanes, each followed along its bus from chip to chip
        followed = [n for n in fabric_v5.LANES if n.startswith("/") and len(o["nets"][n]["segments"]) >= 7]
        self.assertEqual(len(followed), 48)
        # the pin transform is right on real data: nearly every crossbar pin ends on a wire end or a label
        ends = {(round(x, 2), round(y, 2)) for n in o["nets"].values()
                for s in n["segments"] for x, y in ((s[0], s[1]), (s[2], s[3]))}
        ends |= {(round(x, 2), round(y, 2)) for n in o["nets"].values() for x, y in n["labels"]}
        on_copper = sum(1 for x, y in o["pins"].values() if (round(x, 2), round(y, 2)) in ends)
        self.assertGreaterEqual(on_copper, 270)                 # 288 less the eight unconnected Y0 pins and a margin

    def test_missing_schematic_says_what_to_do(self):
        with self.assertRaises(sheet.SheetUnavailable) as cm:
            sheet.build(Path("/nonexistent.kicad_sch"))
        self.assertIn("lab.py sheet", cm.exception.hint)

    def test_the_command_reports_a_missing_schematic_as_usage(self):
        import contextlib
        import io

        import lab
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(lab.main(["sheet", "/nonexistent.kicad_sch"]), 2)
        self.assertIn("/nonexistent.kicad_sch", err.getvalue())
        self.assertIn("lab.py sheet", err.getvalue())

    def test_missing_kicad_cli_says_what_to_do(self):
        with mock.patch.object(sheet, "kicad_cli", return_value=None), self.assertRaises(sheet.SheetUnavailable) as cm:
            sheet.build(self.write(MINI))
        self.assertIn("kicad-cli", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
