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

    def test_the_tabs_pick_a_view_and_a_view_can_have_a_panel_of_its_own(self):
        js = (server.WEB_DIR / "lab.js").read_text()
        css = (server.WEB_DIR / "lab.css").read_text()
        html = (server.WEB_DIR / "index.html").read_text()
        # the view's tabs pick a view and nothing else: the fabric, the sheet, the crossbars as the board prints them
        self.assertEqual(re.findall(r'data-tab="(\w+)"', html), ["fabric", "sheet", "xbar"])
        self.assertIn('id="xbar"', html)
        for function in ("function drawXbar(", "function shortWire("):
            self.assertIn(function, js)
        self.assertIn(".xchip", css)
        # the ranking is the right panel's other face, and a quiet one
        self.assertEqual(re.findall(r'data-side="(\w+)"', html), ["case", "ranking"])
        self.assertIn("function showSide(", js)
        self.assertNotIn('state.tab === "ranking"', js)
        self.assertNotIn('state.tab !== "ranking"', js)
        # zoom has buttons of its own in the drawing's corner: out, fit, in
        self.assertIn('id="zoom"', html)
        self.assertEqual(re.findall(r'data-zoom="(\w+)"', html), ["out", "fit", "in"])
        self.assertIn('"zoomby"', js)
        # a view can be given a panel of its own (a tab dragged onto a side of a panel, or the dock button), and put back
        for function in ("function popOut(", "function dockBack(", "function viewPanel("):
            self.assertIn(function, js)
        self.assertIn('id="pop"', html)
        self.assertIn(".viewpanel", css)
        self.assertRegex(css, r"#tip \{[^}]*position: fixed")            # a tip follows the pointer in whichever panel the view is
        self.assertIn("function zoomView(how, which = state.tab)", js)   # and such a panel zooms its own view
        self.assertIn(".vrow > .flexi", css)                              # the panel that takes what is left is never squeezed away
        # the crossbars' lines and blocks are drawn over the board's letters, in boxes one letter wide: they join in any font
        self.assertRegex(css, r"\.xchip \.xl, \.xchip \.xblock \{[^}]*width: 1ch")

    def test_the_page_is_told_every_chips_pins(self):
        pins = server.pins_of(arrangement.V5)                              # for the crossbars drawn as the board prints them
        self.assertEqual(sorted(pins), list("ABCDEFGHIJKL"))
        self.assertEqual((len(pins["K"]["x"]), len(pins["K"]["y"])), (16, 8))
        self.assertEqual(pins["K"]["x"][2], "ROUTABLE_BUFFER_IN")
        self.assertEqual(pins["A"]["y"][1], "1")
        self.assertEqual(server.pins_of(arrangement.load("v6_rails_on_chips"))["A"]["x"][7], "TOP_RAIL")
        self.assertIsNone(server.pins_of(rank.without(arrangement.V5, "KL"))["K"]["x"][12])     # a pin taken away is no wire
        self.assertEqual(server.info()["pins"], pins)
        out = self.tmp / "pins.html"
        with mock.patch.object(rank, "DIR", self.tmp / "rank"):
            export.write(out, "worktree", classes=("real",), arrangement_name="v6_feed_off")
        self.assertEqual(carried(out)["info"]["pins"]["L"]["x"][0], "30")

    def test_the_kicad_sheet_travels_beside_the_page_when_asked_for(self):
        built = self.tmp / "sheet"
        built.mkdir()
        (built / "overlay.json").write_text(json.dumps({"size": [10, 20], "bodies": {}, "theme": None}))
        (built / "backdrop.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
        out = self.tmp / "site" / "run.html"
        out.parent.mkdir()
        with mock.patch.object(server, "SHEET_DIR", built), mock.patch.object(rank, "DIR", self.tmp / "rank"):
            export.write(out, "worktree", classes=("real",), backdrop="sheet-r7.svg")
            data = carried(out)
            self.assertIs(data["info"]["sheet"], True)
            self.assertEqual(data["sheet"]["size"], [10, 20])              # what /api/sheet answers
            self.assertEqual(data["backdrop"], "sheet-r7.svg")             # fetched from beside the page, by this name
            self.assertEqual((out.parent / "sheet-r7.svg").read_text(), (built / "backdrop.svg").read_text())
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(lab.main(["export", str(out), "--classes", "real", "--backdrop", "r7.svg"]), 0)
            self.assertTrue((out.parent / "r7.svg").is_file())
            for bad in ("../up.svg", "a/b.svg", ""):                       # a file name beside the page, nothing else
                with self.assertRaises(ValueError):
                    export.write(out, "worktree", classes=("real",), backdrop=bad)
        with mock.patch.object(server, "SHEET_DIR", self.tmp / "not-built"), self.assertRaises(ValueError) as e:
            export.write(out, "worktree", classes=("real",), backdrop="sheet-r7.svg")
        self.assertIn("lab.py sheet", str(e.exception))                    # not built: says how to build it
        js = (server.WEB_DIR / "lab.js").read_text()
        self.assertIn("STATIC.sheet", js)
        self.assertIn("STATIC.backdrop", js)
        self.assertIn("function loadBackdrop", js)                         # 10 MB: fetched when the tab is first opened

    def test_the_exported_page_shows_the_arrangement_and_the_ranking_it_carries(self):
        js = (server.WEB_DIR / "lab.js").read_text()
        self.assertIn("state.arrangement = STATIC.run.arrangement.name", js)       # drawn on the copper it ran on
        self.assertIn('pathname === "/api/rank" && STATIC.rank', js)               # the ranking carried is the one shown
        self.assertIn('hidden = !STATIC.rank', js)                                 # the tab is there when there is one
        self.assertNotIn('a ranking is asked of the server', js)

    def test_a_lane_clicked_on_the_ranking_is_lit_in_the_table_and_in_the_drawing(self):
        js = (server.WEB_DIR / "lab.js").read_text()
        css = (server.WEB_DIR / "lab.css").read_text()
        at = js.index("function toggleTakeAway")
        self.assertNotIn("if (STATIC) return", js[at:at + 700])        # an exported page lights a lane too
        self.assertIn("scrollIntoView", js)                            # picked in the drawing, its row comes into sight
        self.assertIn('classList.toggle("picking"', js)
        self.assertNotIn("line-through", css)                          # lit, not crossed out
        self.assertRegex(css, r"#ranking tr\.case\.take td \{[^}]*var\(--sel\)")
        self.assertRegex(css, r"\.wire\.heat\.take \{[^}]*drop-shadow")
        self.assertIn("svg.picking .wire.heat:not(.take)", css)        # the others step back
        self.assertNotIn("stroke-dasharray: 2 3", css)                 # a picked wire is no longer dashed

    def test_the_page_answers_to_hands(self):
        js = (server.WEB_DIR / "lab.js").read_text()
        css = (server.WEB_DIR / "lab.css").read_text()
        html = (server.WEB_DIR / "index.html").read_text()
        # three panels: each moves onto a side of another by its plate, the lines between them size them, a panel
        # folds to its bar, and the browser keeps all of it; in one column the drawing's lower edge sizes it
        for function in ("function installPanels", "function buildLayout", "function movePanel", "function splitBetween",
                         "function resetLayout", "function keptLayout"):
            self.assertIn(function, js)
        self.assertIn('"lab.layout.v1"', js)
        self.assertIn("--view-h", css)
        self.assertIn("--view-h", js)
        for part in ('data-panel="tests"', 'data-panel="view"', 'data-panel="case"', 'class="plate"', 'class="fold"'):
            self.assertIn(part, html)
        for rule in (".vrow", ".vcol", ".split", ".dropbar", ".panel.shut", ".plate"):
            self.assertIn(rule, css)
        # the arrow keys move through the list last used, and Escape lets go
        self.assertIn("function installKeys", js)
        for key in ("ArrowDown", "ArrowUp", "Home", "End", "Escape"):
            self.assertIn(key, js)
        # a click says what was clicked (a phone has no hover) and lights it: a wire with no net, a chip, a problem's net
        self.assertIn('id="said"', html)
        self.assertRegex(css, r"#said \{[^}]*position: absolute")       # over the drawing: what it says moves nothing
        for function in ("function say(", "function touchWire(", "function named(", "function point(", "function letGo("):
            self.assertIn(function, js)
        self.assertIn("state.sort", js)                                # the battery sorts by a column, as the ranking does
        self.assertIn(".wire.pick", css)
        self.assertIn(".bridges tr.at", css)

    def test_the_page_fits_a_phone_and_its_drawing_takes_fingers(self):
        js = (server.WEB_DIR / "lab.js").read_text()
        css = (server.WEB_DIR / "lab.css").read_text()
        self.assertIn("@media (max-width: 1200px)", css)                # one column on a narrow screen
        self.assertIn("touch-action: none", css)                       # the drawing, not the page, takes the fingers
        self.assertIn("const zoomAbout", js)                           # the wheel and two fingers zoom the same way
        self.assertIn("fingers.size === 2", js)
        for ground in ("--head:", "--hover:", "--sel:", "--btn:", "--pad:", "--tip:"):
            self.assertEqual(css.count(ground), 1, ground)             # each ground is named once, so a theme can swap it

    def test_the_page_looks_like_jumperless_on_a_ships_console(self):
        js = (server.WEB_DIR / "lab.js").read_text()
        css = (server.WEB_DIR / "lab.css").read_text()
        html = (server.WEB_DIR / "index.html").read_text()
        # the palette is the Jumperless one, under the names its stylesheet sets: greys and never black, the rainbow, the magenta
        for token in ("var(--jl-bg, #27272b)", "var(--jl-surface, #323238)", "var(--jl-accent-3, #fc0289)", "var(--jl-r1, #f03060)",
                      "var(--jl-r12, #e86828)"):
            self.assertIn(token, css)
        for black in ("#000;", "#000 ", "#16171f", "#0f1017"):
            self.assertNotIn(black, css)
        self.assertIn('"Archivo Narrow"', css)                         # narrow capital labels,
        self.assertIn('"IBM Plex Mono"', css)                          # numbers in a mono face,
        self.assertIn("Michroma", css)                                 # the wide face for the title and the plates' numbers
        self.assertGreaterEqual(css.count("clip-path: polygon("), 5)   # corners are cut, not rounded
        self.assertNotIn("border-radius: 9px", css)
        self.assertIn("prefers-reduced-motion", css)
        # the last things that did nothing: a legend key shows its kind alone, the counts and the status tag answer
        self.assertEqual(html.count('data-kind="'), 6)
        for function in ("function onlyKind(", "function renderHud(", "function keepUi(", "function keptUi("):
            self.assertIn(function, js)
        self.assertIn('"lab.ui.v1:"', js)                              # the page opens where it was left
        self.assertIn('ArrowLeft: "left", ArrowRight: "right", ArrowUp: "top", ArrowDown: "bottom"', js)   # a plate moves its panel by the keys too
        self.assertIn('\\25B2', css)                                   # a problem wears a mark as well as the red
        self.assertNotIn('var(--r1)', css.split('--rainbow:')[1].split(';', 1)[1])   # the reddish pink stays out of the page's furniture
        self.assertIn('aria-pressed', js)
        self.assertIn('id="hud"', html)
        self.assertIn("svg[data-only]", css)

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
