# SPDX-License-Identifier: MIT
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import variants

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(LAB))


class Variants(unittest.TestCase):
    def test_override_paths_must_stay_under_src(self):
        self.assertEqual(variants.safe_override_path("src/routing/./NetsToChipConnections.cpp"),
                         "src/routing/NetsToChipConnections.cpp")
        for bad in ("../etc/passwd", "/etc/passwd", "src/../../x.cpp", "src/routing/../../../x",
                    "tools/x.cpp", "src", ""):
            with self.assertRaises(ValueError, msg=bad):
                variants.safe_override_path(bad)

    def test_worktree_builds_and_is_cached(self):
        v = variants.resolve("worktree")
        b1 = variants.build(v)
        t = os.path.getmtime(b1)
        self.assertEqual(variants.build(v), b1)
        self.assertEqual(os.path.getmtime(b1), t)

    def test_git_ref_variant_builds(self):
        self.assertTrue(os.access(variants.build(variants.resolve("HEAD")), os.X_OK))

    def test_directory_spec_is_that_checkout(self):
        self.assertEqual(variants.resolve(REPO).hash, variants.resolve("worktree").hash)
        with self.assertRaises(ValueError):
            variants.resolve("/nonexistent/place")

    def test_override_changes_hash_and_broken_code_reports_the_compiler(self):
        base = variants.resolve("worktree")
        bad = variants.resolve("worktree", {"src/routing/NetsToChipConnections.cpp": b"this is not C++\n"})
        self.assertNotEqual(base.hash, bad.hash)
        with self.assertRaises(variants.BuildError) as cm:
            variants.build(bad)
        self.assertIn("error", cm.exception.stderr)

    def test_override_outside_src_is_refused(self):
        with self.assertRaises(ValueError):
            variants.resolve("worktree", {"../outside.cpp": b"int x;\n"})

    def test_harness_edit_changes_hash(self):
        before = variants.resolve("worktree").hash
        with tempfile.TemporaryDirectory() as tmp:
            changed = Path(tmp) / "harness"
            shutil.copytree(variants.HARNESS_DIR, changed)
            with open(changed / "lab_harness.cpp", "a") as f:
                f.write("// touched\n")
            with mock.patch.object(variants, "HARNESS_DIR", changed):
                self.assertNotEqual(variants.resolve("worktree").hash, before)


if __name__ == "__main__":
    unittest.main()
