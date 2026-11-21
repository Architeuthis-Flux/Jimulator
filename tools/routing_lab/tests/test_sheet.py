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
