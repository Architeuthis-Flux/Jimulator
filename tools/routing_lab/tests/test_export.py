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

import arrangement
import export
import lab
import rank
import server
import variants

STATIC = re.compile(r"window\.LAB_STATIC = (\{.*?\});\n", re.S)


def carried(path):
    """What an exported page carries."""
    return json.loads(STATIC.search(Path(path).read_text()).group(1))


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
        self.assertIs(data["info"]["sheet"], False)                    # the sheet backdrop does not travel,
        self.assertIs(data["info"]["solver"], False)                   # nor does the solver
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

    def test_a_run_on_an_arrangement_travels_with_its_copper_and_its_ranking(self):
        out = self.tmp / "v6.html"
        with mock.patch.object(rank, "DIR", self.tmp / "rank"):
            export.write(out, "worktree", classes=("dense",), arrangement_name="v6_feed_off")
            self.assertIsNone(carried(out)["rank"])                    # no ranking on file: none travels
            a = arrangement.load("v6_feed_off")
            rank.save(rank.removal(variants.resolve("worktree"), lab.battery(["dense"]), a, wires=["KL"]))
            export.write(out, "worktree", classes=("dense",), arrangement_name="v6_feed_off")
        data = carried(out)
        self.assertEqual(data["run"]["arrangement"]["name"], "v6_feed_off")
        self.assertIs(data["run"]["arrangement"]["feed"], False)
        self.assertFalse(any(c["result"]["feed"] for c in data["cases"].values()))       # routed with the feed off
        self.assertEqual([r["name"] for r in data["info"]["arrangements"]], ["v6_feed_off"])   # the one it ran on, only
        self.assertEqual(data["info"]["fabric"], json.loads(json.dumps(server.fabric_view.layout(a))))
        self.assertEqual([w["wire"] for w in data["rank"]["wires"]], ["KL"])
        self.assertIs(data["rank"]["stale"], False)
        self.assertTrue(data["rank"]["made"])
        self.assertEqual(data["rank"]["variant"], data["run"]["variant"])              # one router, one name on the page
        self.assertNotIn(str(Path.home()), out.read_text())

    def test_a_run_on_v5_says_so_and_carries_no_ranking_it_does_not_have(self):
        out = self.tmp / "v5.html"
        with mock.patch.object(rank, "DIR", self.tmp / "rank"):
            export.write(out, "worktree", classes=("real",))
        data = carried(out)
        self.assertEqual(data["run"]["arrangement"]["name"], "v5")
        self.assertEqual([r["name"] for r in data["info"]["arrangements"]], ["v5"])
        self.assertIsNone(data["rank"])

    def test_copper_the_router_cannot_route_is_refused_and_nothing_is_written(self):
        out = self.tmp / "rails.html"
        with self.assertRaises(arrangement.RouterCannot):
            export.write(out, "worktree", classes=("real",), arrangement_name="v6_rails_on_chips")
        self.assertFalse(out.exists())

    def test_the_command_takes_an_arrangement(self):
        out = self.tmp / "cli.html"
        with mock.patch.object(rank, "DIR", self.tmp / "rank"), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(lab.main(["export", str(out), "--classes", "real", "--arrangement", "v6_feed_off"]), 0)
        self.assertEqual(carried(out)["run"]["arrangement"]["name"], "v6_feed_off")

    def test_the_exported_page_shows_the_arrangement_and_the_ranking_it_carries(self):
        js = (server.WEB_DIR / "lab.js").read_text()
        self.assertIn("state.arrangement = STATIC.run.arrangement.name", js)       # drawn on the copper it ran on
        self.assertIn('pathname === "/api/rank" && STATIC.rank', js)               # the ranking carried is the one shown
        self.assertIn('hidden = !STATIC.rank', js)                                 # the tab is there when there is one
        self.assertNotIn('a ranking is asked of the server', js)

    def test_the_page_fits_a_phone_and_its_drawing_takes_fingers(self):
        js = (server.WEB_DIR / "lab.js").read_text()
        css = (server.WEB_DIR / "lab.css").read_text()
        self.assertIn("@media (max-width: 900px)", css)                # one column on a narrow screen
        self.assertIn("touch-action: none", css)                       # the drawing, not the page, takes the fingers
        self.assertIn("const zoomAbout", js)                           # the wheel and two fingers zoom the same way
        self.assertIn("fingers.size === 2", js)
        for colour in ("#2f3654", "#2b3350", "#252839", "#24273a", "#343a55", "#0f1017"):
            self.assertEqual(css.count(colour), 1, colour)             # each ground is named once, so a theme can swap it

    def test_clean_empties_the_caches(self):
        for name in ("results", "variants", "bin", "sheet", "ceiling", "solver-venv"):
            (self.tmp / name).mkdir()
            (self.tmp / name / "f").write_text("x" * 1000)
        with mock.patch.object(variants, "BUILD_DIR", self.tmp), contextlib.redirect_stdout(io.StringIO()) as said:
            self.assertEqual(lab.main(["clean"]), 0)
        # the sheet and the solver's environment are kept: small or slow to remake, and one needs the network
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ["sheet", "solver-venv"])
        self.assertIn("freed", said.getvalue())


if __name__ == "__main__":
    unittest.main()
