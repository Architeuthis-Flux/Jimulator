# SPDX-License-Identifier: MIT
import contextlib
import io
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import cases
import fidelity
import lab
import variants

BIN = None


def setUpModule():
    global BIN
    BIN = variants.build(variants.resolve("worktree"))


class Fidelity(unittest.TestCase):
    def setUp(self):                                # a capture made by the harness itself, alternator 1
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.dir = self.tmp / "board_selftest"
        out = fidelity.replay(BIN, None, alternator=1)          # None: default stacks, all dense cases
        self.dir.mkdir()
        for name, s in out.items():
            (self.dir / f"{name}.b.txt").write_text(s["b"])
            (self.dir / f"{name}.xbar.txt").write_text(s["xbar"])

    def test_stack_from_b(self):
        self.assertEqual(fidelity.stack_from_b("pathDuplicates: 9\ndacDuplicates: 9\nrailsDuplicates: 9\n"
                                               "gpioDuplicates: 0\nadcDuplicates: 0\n"), (9, 9, 9, 0, 0))
        self.assertEqual(fidelity.stack_from_b("\r\npathDuplicates: 2\r\ndacDuplicates: 0\r\nrailsDuplicates: 3\r\n"
                                               "gpioDuplicates: 1\r\nadcDuplicates: 4\r\n"), (2, 3, 0, 1, 4))

    def test_replay_covers_the_suite_in_order(self):
        out = fidelity.replay(BIN, None, alternator=0)
        self.assertEqual(list(out), [c.name for c in cases.dense_cases()])
        self.assertIn("Bridge Array", out["chain_all_chips"]["b"])

    def test_own_capture_passes_under_one_parity(self):
        ok, diffs = fidelity.check(self.dir, "worktree")
        self.assertTrue(ok, diffs[:5])
        self.assertEqual(diffs, [])

    def test_a_moved_row_fails_and_names_the_case(self):
        p = self.dir / "chain_all_chips.b.txt"
        rows = p.read_text().split("\n")
        i = next(i for i, l in enumerate(rows) if re.match(r"\d+\t", l))
        cols = rows[i].split("\t")
        cols[4] = str((int(cols[4]) + 1) % 16)
        rows[i] = "\t".join(cols)
        p.write_text("\n".join(rows))
        ok, diffs = fidelity.check(self.dir, "worktree")
        self.assertFalse(ok)
        self.assertTrue(any("chain_all_chips" in d for d in diffs))

    def test_a_changed_claim_or_crosspoint_is_a_difference(self):
        p = self.dir / "gnd_spread.xbar.txt"
        text = p.read_text()
        hexs = re.search(r"xbar\{12x8:([0-9a-f]{384})\}", text).group(1)
        flipped = ("%04x" % (int(hexs[:4], 16) ^ 0x8000)) + hexs[4:]
        p.write_text(text.replace(hexs, flipped))
        ok, diffs = fidelity.check(self.dir, "worktree")
        self.assertFalse(ok)
        self.assertTrue(any("gnd_spread" in d and "crosspoint" in d for d in diffs), diffs)

    def test_missing_capture_is_a_difference(self):
        (self.dir / "gnd_spread.b.txt").unlink()
        ok, diffs = fidelity.check(self.dir, "worktree")
        self.assertFalse(ok)
        self.assertTrue(any("gnd_spread" in d for d in diffs))

    def test_variant_defaults_to_the_hash_in_the_directory_name(self):
        named = self.tmp / "board_HEAD"
        shutil.copytree(self.dir, named)
        self.assertTrue(fidelity.check(named)[0])
        with self.assertRaises(ValueError):
            fidelity.check(self.tmp / "no_such_capture")

    def test_cli(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = lab.main(["fidelity", str(self.dir), "--variant", "worktree"])
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("PASS", out.getvalue())
        (self.dir / "gnd_spread.b.txt").unlink()
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = lab.main(["fidelity", str(self.dir), "--variant", "worktree"])
        self.assertEqual(code, 1)
        self.assertIn("gnd_spread", out.getvalue())

    def test_run_says_when_no_board_capture_exists(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            lab.main(["run", "--classes", "dense", "--case", "chain_all_chips"])
        self.assertIn("not verified against a board", out.getvalue())


if __name__ == "__main__":
    unittest.main()
