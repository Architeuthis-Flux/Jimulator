# SPDX-License-Identifier: MIT
import dataclasses
import os
import shutil
import subprocess
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

    def test_a_router_from_before_the_tap_trace_still_builds(self):
        # 2026-09-03, before RouteSafety.cpp had routeTrace: the harness must
        # not need symbols an older router lacks
        self.assertTrue(os.access(variants.build(variants.resolve("a1accf5^")), os.X_OK))

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

    def test_build_sh_copes_with_spaces_in_paths(self):
        with tempfile.TemporaryDirectory(prefix="V5 Pile ") as tmp:
            os.symlink(os.path.join(REPO, "src"), os.path.join(tmp, "src"))
            out = os.path.join(tmp, "out dir", "lab_harness")
            p = subprocess.run([str(variants.HARNESS_DIR / "build.sh"), os.path.join(tmp, "src"), out],
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr[-800:])
            self.assertTrue(os.access(out, os.X_OK))

    def test_a_tree_that_changes_during_the_build_is_not_cached(self):
        # a live tree whose hash no longer matches after the build: the binary must not be filed under the old hash
        stale = dataclasses.replace(variants.resolve("worktree"), hash="0" * 64)
        shutil.rmtree(variants.BUILD_DIR / "bin" / stale.hash, ignore_errors=True)
        with self.assertRaisesRegex(variants.BuildError, "changed"):
            variants.build(stale)
        self.assertFalse((variants.BUILD_DIR / "bin" / stale.hash).exists())

    def test_resolve_is_thread_safe(self):
        import threading
        override = {"src/routing/NetsToChipConnections.cpp": b"// thread test %d\n" % os.getpid()}
        results, errors = [], []

        def work():
            try:
                results.append(variants.resolve("worktree", override).hash)
            except Exception as e:                      # noqa: BLE001 - the test reports whatever a thread hit
                errors.append(repr(e))

        threads = [threading.Thread(target=work) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(set(results)), 1)

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
