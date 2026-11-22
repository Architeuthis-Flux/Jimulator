# SPDX-License-Identifier: MIT
import contextlib
import io
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import export
import lab
import variants

STATIC = re.compile(r"window\.LAB_STATIC = (\{.*?\});\n", re.S)


class Export(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_one_file_with_everything_inlined(self):
        out = self.tmp / "run.html"
        size = export.write(out, "worktree", classes=("dense",))
        html = out.read_text()
        self.assertEqual(size, len(html.encode()))
        self.assertNotRegex(html, r'<script[^>]+src=|<link[^>]+href=|https?://(?!www\.w3\.org)')
        data = json.loads(STATIC.search(html).group(1))
        self.assertEqual(len(data["run"]["rows"]), 21)
        self.assertIn("chain_all_chips", data["cases"])
        chain = data["cases"]["chain_all_chips"]["paint"]
        self.assertTrue(chain["crosspoints"])
        self.assertEqual(chain["missed"], [])                          # the copper searches travel with the paint
        self.assertTrue(any(b["spare"] and b["spare_paths"] for b in chain["bridges"]))
        self.assertIs(data["info"]["sheet"], False)                    # the sheet backdrop does not travel
        self.assertEqual(data["info"]["variants"], [])
        self.assertTrue(data["when"])
        self.assertNotIn("__LAB_TOKEN__", html)                        # no token,
        self.assertNotIn(str(Path.home()), html)                       # no home path

    def test_a_directory_is_named_by_its_last_part_and_a_baseline_travels(self):
        out = self.tmp / "run.html"
        export.write(out, str(variants.REPO), baseline_spec="worktree", classes=("real",))
        html = out.read_text()
        run = json.loads(STATIC.search(html).group(1))["run"]
        self.assertEqual(run["variant"]["name"], variants.REPO.name)
        self.assertEqual(run["baseline"]["name"], "worktree")
        self.assertIn("base", run["rows"][0])
        self.assertEqual(run["regressions"], [])
        self.assertNotIn(str(Path.home()), html)

    def test_report_text_cannot_close_or_derail_the_page_script(self):
        nasty = "</script><img src=x onerror=alert(1)> <!-- <script "
        html = export.page({"info": {}, "run": {}, "cases": {"x": nasty}, "when": "today"})
        data = STATIC.search(html).group(1)
        self.assertNotIn("<", data)                                    # no tag, comment or script can open in it
        self.assertEqual(json.loads(data)["cases"]["x"], nasty)

    def test_a_home_path_with_an_accent_is_still_taken_out(self):
        with mock.patch.object(export.Path, "home", return_value=Path("/Users/josé")):
            html = export.page({"info": {}, "run": {}, "cases": {"x": "at /Users/josé/lab/build"}, "when": ""})
        self.assertEqual(json.loads(STATIC.search(html).group(1))["cases"]["x"], "at ~/lab/build")

    def test_the_command_writes_the_file(self):
        out = self.tmp / "cli.html"
        with contextlib.redirect_stdout(io.StringIO()) as said:
            self.assertEqual(lab.main(["export", str(out), "--classes", "real"]), 0)
        self.assertIn("LAB_STATIC", out.read_text())
        self.assertIn(str(out), said.getvalue())

    def test_clean_empties_the_caches(self):
        for name in ("results", "variants", "bin", "sheet"):
            (self.tmp / name).mkdir()
            (self.tmp / name / "f").write_text("x" * 1000)
        with mock.patch.object(variants, "BUILD_DIR", self.tmp), contextlib.redirect_stdout(io.StringIO()) as said:
            self.assertEqual(lab.main(["clean"]), 0)
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ["sheet"])        # the sheet is kept
        self.assertIn("freed", said.getvalue())


if __name__ == "__main__":
    unittest.main()
