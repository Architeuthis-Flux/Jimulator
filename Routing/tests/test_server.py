# SPDX-License-Identifier: MIT
import contextlib
import http.client
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.parse
from unittest import mock

import copper
import server
import variants

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = str(variants.REPO)                   # the firmware checkout
DEFAULT = object()


class Reply:
    def __init__(self, status, headers, body):
        self.status, self.headers, self.body = status, headers, body

    @property
    def json(self):
        return json.loads(self.body)


class Client:
    """Talks to one running server the way the page does, unless told otherwise."""

    def __init__(self, srv):
        self.srv = srv
        self.port = srv.server_address[1]

    def request(self, method, path, body=None, token=DEFAULT, headers=None, raw=None):
        headers = dict(headers or {})
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=120)
        conn.putrequest(method, path, skip_host=True)
        conn.putheader("Host", headers.pop("Host", "127.0.0.1:%d" % self.port))
        if token is DEFAULT:
            token = self.srv.token
        if token is not None:
            conn.putheader("X-Lab-Token", token)
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else b"")
        if body is not None or raw is not None:
            conn.putheader("Content-Type", "application/json")
            conn.putheader("Content-Length", str(len(data)))
        for k, v in headers.items():
            conn.putheader(k, v)
        conn.endheaders()
        if data:
            conn.send(data)
        r = conn.getresponse()
        reply = Reply(r.status, dict(r.getheaders()), r.read().decode(errors="replace"))
        conn.close()
        return reply

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, body, **kw):
        return self.request("POST", path, body=body, **kw)


@contextlib.contextmanager
def running(trees=()):
    srv = server.make_server(0, trees)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield Client(srv)
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join()


class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stack = contextlib.ExitStack()
        cls.c = cls.stack.enter_context(running())
        cls.srv = cls.c.srv

    @classmethod
    def tearDownClass(cls):
        cls.stack.close()

    def test_binds_loopback_and_inlines_the_token(self):
        self.assertEqual(self.srv.server_address[0], "127.0.0.1")
        page = self.c.get("/", token=None)
        self.assertEqual(page.status, 200)
        self.assertIn(self.srv.token, page.body)
        self.assertNotIn("__LAB_TOKEN__", page.body)
        self.assertTrue(self.srv.url.startswith("http://127.0.0.1:"))

    def test_api_needs_the_token_and_a_local_origin(self):
        self.assertEqual(self.c.get("/api/info", token=None).status, 403)
        self.assertEqual(self.c.get("/api/info", token="wrong").status, 403)
        self.assertEqual(self.c.get("/api/info", headers={"Origin": "http://evil.example"}).status, 403)
        self.assertEqual(self.c.get("/api/info", headers={"Host": "evil.example"}).status, 403)
        self.assertEqual(self.c.get("/api/info").status, 200)
        self.assertEqual(self.c.get("/api/info", headers={"Origin": "http://127.0.0.1:%d" % self.c.port}).status, 200)
        self.assertEqual(self.c.get("/api/info", headers={"Host": "localhost:%d" % self.c.port}).status, 200)
        with mock.patch.object(variants, "build", side_effect=AssertionError("built for a stranger")):
            body = {"variant": "worktree", "classes": ["dense"]}
            self.assertEqual(self.c.post("/api/run", body, token=None).status, 403)
            self.assertEqual(self.c.post("/api/run", body, headers={"Origin": "http://evil.example"}).status, 403)

    def test_the_page_with_its_token_is_not_served_to_another_host_name(self):
        # DNS rebinding: a foreign name pointed at 127.0.0.1 must not be able to read the token out of the page
        self.assertEqual(self.c.get("/", token=None, headers={"Host": "evil.example:%d" % self.c.port}).status, 403)

    def test_static_files_stay_inside_web(self):
        for path in ("/../lab.py", "/%2e%2e/lab.py", "/web/../../lab.py", "/build/bin", "/..%2flab.py", "//etc/passwd"):
            self.assertIn(self.c.get(path, token=None).status, (403, 404), path)

    def test_info(self):
        info = self.c.get("/api/info").json
        self.assertEqual(info["classes"], ["example", "dense", "real", "typical", "fuzz", "stress", "beyond", "edge"])
        self.assertEqual(info["variants"][0], {"spec": "worktree", "name": "worktree"})
        self.assertEqual(info["ohms"], 42)                               # measured on a board, per crosspoint
        # what each class is and how many cases it runs, for the page to say what a run covers
        self.assertEqual(sorted(info["about"]), sorted(info["classes"]))
        self.assertEqual([info["about"][c]["cases"] for c in ("dense", "typical", "fuzz", "stress", "beyond", "edge")],
                         [21, 200, 2000, 21, 3, 12])
        self.assertTrue(all(len(a["what"]) > 20 for a in info["about"].values()))
        self.assertIn("must route", info["about"]["dense"]["what"])
        self.assertIn("A", info["fabric"]["chips"])
        self.assertIn(info["verified"], (True, False))                  # True once a board capture has passed
        with mock.patch.object(server.lab, "FIDELITY_DIR", server.LAB / "no-captures-here"):
            self.assertIs(self.c.get("/api/info").json["verified"], False)
        self.assertIn(info["sheet"], (True, False))

    def test_page_files_are_served_and_parse(self):
        for path, kind in (("/lab.js", "javascript"), ("/lab.css", "css")):
            r = self.c.get(path, token=None)
            self.assertEqual(r.status, 200, path)
            self.assertIn(kind, r.headers["Content-Type"])
        self.assertEqual(subprocess.run(["node", "--check", str(server.WEB_DIR / "lab.js")]).returncode, 0)
        page = self.c.get("/", token=None).body
        self.assertNotRegex(page, r'(src|href)="https?://')          # nothing from the network
        for anchor in ('id="battery"', 'id="fabric"', 'id="case"', 'id="build-error"'):
            self.assertIn(anchor, page)
        for text in (self.c.get("/lab.js", token=None).body, self.c.get("/lab.css", token=None).body):
            self.assertNotRegex(text, r"https?://(?!www\.w3\.org/)")  # only the SVG namespace

    def test_info_names_every_node(self):
        nodes = self.c.get("/api/info").json["nodes"]
        self.assertEqual(nodes["1"], {"wire": "1", "name": "1"})
        self.assertEqual(nodes["131"], {"wire": "GPIO_20", "name": "GPIO_1"})
        self.assertEqual(nodes["100"]["wire"], "GND")

    def test_run_and_case(self):
        r = self.c.post("/api/run", {"variant": "worktree", "baseline": None, "classes": ["dense"]}).json
        self.assertEqual(len(r["rows"]), 21)
        self.assertNotIn("b", r["rows"][0])
        self.assertNotIn("stderr", r["rows"][0])
        self.assertIn("worst_r", r["rows"][0]["metrics"])
        self.assertIn("fully_routed", r["rows"][0])
        self.assertEqual(r["variant"]["name"], "worktree")
        c = self.c.get("/api/case?variant=%s&case=chain_all_chips" % r["variant"]["hash"]).json
        self.assertIn("Bridge Array", c["result"]["b"])
        self.assertTrue(c["paint"]["crosspoints"])
        self.assertEqual(c["paint"]["missed"], [])                      # the paint carries both copper searches
        self.assertTrue(all({"spare", "r_spare", "spare_paths"} <= set(b) for b in c["paint"]["bridges"]))
        self.assertEqual(self.c.get("/api/case?variant=%s&case=nope" % r["variant"]["hash"]).status, 404)
        self.assertEqual(self.c.get("/api/case?variant=nohash&case=chain_all_chips").status, 404)
        self.assertEqual(self.c.post("/api/run", {"variant": "worktree", "classes": ["nope"]}).status, 400)
        self.assertEqual(self.c.post("/api/run", {"variant": "no-such-ref-anywhere", "classes": ["dense"]}).status, 400)

    def test_baseline_rows_and_regressions(self):
        r = self.c.post("/api/run", {"variant": "worktree", "baseline": "HEAD", "classes": ["dense"]}).json
        self.assertEqual(r["regressions"], [])
        self.assertIn("base", r["rows"][0])
        self.assertIn("metrics", r["rows"][0]["base"])
        self.assertTrue(r["baseline"]["name"].startswith(variants.REPO.name + "@"))    # named by the checkout

    def test_uploaded_file_makes_a_variant_and_a_broken_one_reports_the_compiler(self):
        bad = {"base": "worktree", "files": {"src/routing/NetsToChipConnections.cpp": "this is not C++\n"}}
        r = self.c.post("/api/run", {"variant": bad, "classes": ["dense"]})
        self.assertEqual(r.status, 200)
        self.assertIn("error", r.json["build_error"])
        self.assertIn("1 file", r.json["variant"]["name"])
        escape = {"variant": {"base": "worktree", "files": {"../x": "y"}}, "classes": ["dense"]}
        self.assertEqual(self.c.post("/api/run", escape).status, 400)
        huge = {"variant": {"base": "worktree", "files": {"src/a.h": "x" * 6_000_000}}, "classes": ["dense"]}
        self.assertEqual(self.c.post("/api/run", huge).status, 413)

    def test_only_named_directories_are_variants(self):
        self.assertEqual(self.c.post("/api/run", {"variant": "/tmp", "classes": ["dense"]}).status, 400)
        self.assertEqual(self.c.post("/api/run", {"variant": REPO, "classes": ["dense"]}).status, 400)
        # a relative path is never a directory variant either: only a git ref
        self.assertEqual(self.c.post("/api/run", {"variant": ".", "classes": ["dense"]}).status, 400)
        self.assertEqual(self.c.get("/api/watch?spec=%s" % REPO).status, 400)
        with running(trees=[REPO]) as named:
            self.assertEqual(named.post("/api/run", {"variant": REPO, "classes": ["dense"]}).status, 200)
            self.assertIn({"spec": REPO, "name": os.path.basename(REPO)}, named.get("/api/info").json["variants"])

    def test_a_save_during_the_build_is_retried_once(self):
        real, calls = variants.build, []

        def flaky(v, sanitize=True):
            calls.append(v)
            if len(calls) == 1:
                raise variants.BuildError("the sources changed while the harness was building; run again")
            return real(v, sanitize)

        with mock.patch.object(variants, "build", side_effect=flaky):
            r = self.c.post("/api/run", {"variant": "worktree", "classes": ["dense"]}).json
        self.assertNotIn("build_error", r)
        self.assertEqual(len(calls), 2)

    def test_paths_lists_tracked_files_by_basename(self):
        self.assertEqual(self.c.get("/api/paths?name=NetsToChipConnections.cpp").json["paths"],
                         ["src/routing/NetsToChipConnections.cpp"])
        self.assertEqual(self.c.get("/api/paths?name=nope.cpp").json["paths"], [])
        self.assertEqual(self.c.get("/api/paths?name=../../etc/passwd").json["paths"], [])
        self.assertEqual(self.c.get("/api/paths").json["paths"], [])
        self.assertGreater(len(self.c.get("/api/paths?name=board.h").json["paths"]), 0)

    def test_the_page_has_what_task_5_adds(self):
        page = self.c.get("/", token=None).body
        for anchor in ('id="live"', 'id="uploads"', 'id="compare"'):
            self.assertIn(anchor, page)

    def test_a_request_that_goes_wrong_inside_still_gets_an_answer(self):
        # each of these used to close the connection with no answer at all
        upload = {"variant": {"base": "worktree", "files": {"src/routing": "x"}}, "classes": ["real"]}
        r = self.c.post("/api/run", upload)                             # the upload's path is a directory
        self.assertEqual(r.status, 400)
        self.assertIn("src/routing", r.json["error"])
        self.assertEqual(self.c.get("/%00", token=None).status, 404)
        self.assertEqual(self.c.get("/api/info", token="töken").status, 403)
        for length in ("abc", "-1"):
            self.assertEqual(self.c.request("POST", "/api/run", headers={"Content-Length": length}).status, 400, length)
        with mock.patch.object(variants, "resolve", side_effect=RuntimeError("boom")):
            r = self.c.post("/api/run", {"variant": "worktree", "classes": ["real"]})
            self.assertEqual(r.status, 500)
            self.assertIn("boom", r.json["error"])
        self.assertEqual(self.c.get("/api/info").status, 200)           # and the server is still there

    def test_a_ref_with_no_src_is_a_bad_variant_not_a_crash(self):
        first = subprocess.run(["git", "-C", REPO, "rev-list", "--max-parents=0", "HEAD"],
                               capture_output=True, text=True).stdout.split()[0]
        if subprocess.run(["git", "-C", REPO, "cat-file", "-e", first + ":src"], capture_output=True).returncode == 0:
            self.skipTest("this repository's first commit already has src/")
        r = self.c.post("/api/run", {"variant": first, "classes": ["real"]})
        self.assertEqual(r.status, 400)
        self.assertIn("src", r.json["error"])

    def test_a_failed_upload_leaves_no_scratch_tree(self):
        scratch = lambda: set((variants.BUILD_DIR / "variants").glob("*.tmp*"))
        before = scratch()
        self.c.post("/api/run", {"variant": {"base": "worktree", "files": {"src/routing": "x"}}, "classes": ["real"]})
        self.assertEqual(scratch(), before)

    def test_runs_are_kept_by_case_and_old_variants_are_dropped(self):
        self.c.post("/api/run", {"variant": "worktree", "classes": ["real"]})
        run = self.c.post("/api/run", {"variant": "worktree", "classes": ["dense"]}).json
        name = "kevin_state_2026-09-07"                                 # a real case, after a dense-only run
        self.assertEqual(self.c.get("/api/case?variant=%s&case=%s" % (run["variant"]["hash"], name)).status, 200)
        for i in range(server.MAX_RUNS + 3):
            self.srv.runs["old%d" % i] = {}
        self.c.post("/api/run", {"variant": "worktree", "classes": ["real"]})
        self.assertEqual(len(self.srv.runs), server.MAX_RUNS)
        self.assertIn((run["variant"]["hash"], "v5"), self.srv.runs)    # the newest stays, under its variant and its arrangement

    def test_the_page_may_not_be_framed(self):
        self.assertEqual(self.c.get("/", token=None).headers.get("X-Frame-Options"), "DENY")

    def test_the_page_draws_the_sheet(self):
        self.assertIn('id="sheet"', self.c.get("/", token=None).body)
        js = self.c.get("/lab.js", token=None).body
        for used in ("/api/sheet", "sheet/backdrop.svg"):
            self.assertIn(used, js)
        self.assertNotIn("not built yet", js)                          # the placeholder is gone
        self.assertEqual(subprocess.run(["node", "--check", str(server.WEB_DIR / "lab.js")]).returncode, 0)

    def test_the_page_draws_missed_paths_and_spare_copies(self):
        js = self.c.get("/lab.js", token=None).body
        for used in ("function drawGhost", "state.ghost", "spare_paths", "metrics.missed", "the copper had a path"):
            self.assertIn(used, js)
        self.assertEqual(subprocess.run(["node", "--check", str(server.WEB_DIR / "lab.js")]).returncode, 0)
        for text in (js, self.c.get("/lab.css", token=None).body):
            self.assertNotRegex(text, r"https?://(?!www\.w3\.org/)")  # still nothing from the network
        self.assertIn(".ghost", self.c.get("/lab.css", token=None).body)

    def test_info_says_whether_the_solver_is_there(self):
        self.assertIs(self.c.get("/api/info").json["solver"], server.ceiling.solver_installed())
        with mock.patch.object(server.ceiling, "SOLVER_PYTHON", server.Path("/nonexistent/python")):
            self.assertIs(self.c.get("/api/info").json["solver"], False)

    def test_ceiling_answers_the_verdict_with_the_solvers_routing_as_a_paint(self):
        run = self.c.post("/api/run", {"variant": "worktree", "classes": ["dense"]}).json
        fixed = {"verdict": "routable", "fewest_proved": True, "crosspoints": 2, "router_crosspoints": 16,
                 "closed": [["A", 2, 1, 6], ["B", 0, 1, 6]], "seconds": 0.3, "error": None}
        ask = {"variant": run["variant"]["hash"], "case": "same_chip_pairs", "rule": "firmware", "seconds": 100000}
        with mock.patch.object(server.ceiling, "solver_installed", return_value=True), \
                mock.patch.object(server.ceiling, "verdict", return_value=fixed) as asked:
            r = self.c.post("/api/ceiling", ask)
            self.assertEqual(r.status, 200, r.body)
            self.assertEqual((r.json["verdict"], r.json["crosspoints"], r.json["router_crosspoints"]), ("routable", 2, 16))
            self.assertEqual(r.json["paint"]["crosspoints"], [{"chip": "A", "x": 2, "y": 1, "net": 6},
                                                              {"chip": "B", "x": 0, "y": 1, "net": 6}])
            # every wire the closed crosspoints touch: the lane, row 1, row 8
            self.assertEqual(r.json["paint"]["wires"], {"/AB0": {"nets": [6]}, "1": {"nets": [6]}, "8": {"nets": [6]}})
            self.assertEqual(asked.call_args.args[0]["case"], "same_chip_pairs")
            self.assertEqual(asked.call_args.args[1:], ("firmware", 120))             # the limit is clamped to 1..120
            self.c.post("/api/ceiling", dict(ask, rule="copper", seconds=0))
            self.assertEqual(asked.call_args.args[1:], ("copper", 1))
            self.assertEqual(self.c.post("/api/ceiling", dict(ask, seconds="soon")).status, 400)
            self.assertEqual(self.c.post("/api/ceiling", dict(ask, rule="magic")).status, 400)
            self.assertEqual(self.c.post("/api/ceiling", dict(ask, case="nope")).status, 404)
            self.assertEqual(self.c.post("/api/ceiling", dict(ask, variant="nohash")).status, 404)
            self.assertEqual(self.c.post("/api/ceiling", dict(ask, variant={"a": 1})).status, 404)
            asked.return_value = dict(fixed, verdict="not_routable", closed=[], crosspoints=None)
            self.assertEqual(self.c.post("/api/ceiling", ask).json["paint"], {"crosspoints": [], "wires": {}})
        with mock.patch.object(server.ceiling, "SOLVER_PYTHON", server.Path("/nonexistent/python")):
            r = self.c.post("/api/ceiling", ask)                                      # asked for real: no solver
            self.assertEqual(r.status, 409)
            self.assertIn("lab.py solver-setup", r.json["hint"])

    def test_the_page_asks_the_solver(self):
        js = self.c.get("/lab.js", token=None).body
        for used in ("/api/ceiling", "function askCeiling", "draw the solver's routing", "Cannot be routed, proved",
                     "Not known after", "info.solver", "lab.py solver-setup"):
            self.assertIn(used, js)
        self.assertEqual(subprocess.run(["node", "--check", str(server.WEB_DIR / "lab.js")]).returncode, 0)
        self.assertNotRegex(js, r"https?://(?!www\.w3\.org/)")

    def test_board_output_is_judged_kept_and_served_like_a_run(self):
        captures = server.lab.FIDELITY_DIR / "board_0621e4f44e23"
        text = (captures / "k_rows_overflow_metric.b.txt").read_text(errors="replace")
        r = self.c.post("/api/board", {"name": "my bench.txt", "text": text})
        self.assertEqual(r.status, 200, r.body)
        run = r.json
        self.assertEqual((run["variant"], run["baseline"], run["board"], run["shown"]),
                         ({"name": "board output", "hash": "board"}, None, True, "my_bench"))
        row = [x for x in run["rows"] if x["case"] == "my_bench"][0]
        self.assertEqual((row["cls"], row["metrics"]["routed_primaries"], row["metrics"]["primaries"]), ("board", 12, 13))
        self.assertNotIn("b", row)
        case = self.c.get("/api/case?variant=board&case=my_bench").json       # drawn as any case is
        self.assertTrue(case["paint"]["crosspoints"])
        self.assertIn("Bridge Array", case["result"]["b"])
        self.assertTrue(any("crossbar" in n for n in case["result"]["notes"]))
        # a second upload joins the first; the same name again replaces it
        more = (captures / "same_chip_pairs.b.txt").read_text(errors="replace")
        run = self.c.post("/api/board", {"name": "second", "text": more}).json
        self.assertEqual(sorted(x["case"] for x in run["rows"]), ["my_bench", "second"])
        run = self.c.post("/api/board", {"name": "my bench.txt", "text": more}).json
        self.assertEqual(len(run["rows"]), 2)
        self.assertEqual([x["metrics"]["primaries"] for x in run["rows"] if x["case"] == "my_bench"], [7])
        with mock.patch.object(server.ceiling, "solver_installed", return_value=True), \
                mock.patch.object(server.ceiling, "verdict", return_value={"verdict": "unknown", "closed": [], "error": None}):
            self.assertEqual(self.c.post("/api/ceiling", {"variant": "board", "case": "second", "rule": "firmware"}).status, 200)

    def test_board_output_that_cannot_be_read_is_a_400_with_the_reason(self):
        for body in ({"name": "x", "text": "hello"}, {"name": "x"}, {"text": 5}, {"name": ["x"], "text": "hello"}):
            r = self.c.post("/api/board", body)
            self.assertEqual(r.status, 400, body)
            self.assertIn("b report", r.json["error"])
        self.assertEqual(self.c.get("/api/info").status, 200)

    def test_the_page_takes_board_output_and_zooms_by_how_far_it_is_scrolled(self):
        js = self.c.get("/lab.js", token=None).body
        for used in ("/api/board", "function looksLikeBoard", '"paste"', "state.run.board", "event.deltaMode", "event.ctrlKey",
                     "is not answering"):
            self.assertIn(used, js)
        self.assertNotIn("0.85", js)                                    # the fixed step a trackpad fired sixty times a second
        self.assertIn('id="drop-hint"', self.c.get("/", token=None).body)
        self.assertEqual(subprocess.run(["node", "--check", str(server.WEB_DIR / "lab.js")]).returncode, 0)
        self.assertNotRegex(js, r"https?://(?!www\.w3\.org/)")

    def test_the_page_says_what_is_running_and_what_is_shown(self):
        page = self.c.get("/", token=None).body
        self.assertIn('id="showing"', page)
        self.assertIn('value="42"', page)
        self.assertNotIn("live</label>", page)                           # "live ohms per crosspoint" read as one setting
        self.assertIn("re-run on save", page)
        js = self.c.get("/lab.js", token=None).body
        for used in ("function renderShowing", "info.about", "must route", "Not a run of the router"):
            self.assertIn(used, js)
        run = self.c.post("/api/run", {"variant": "worktree", "classes": ["dense"]}).json
        case = self.c.get("/api/case?variant=%s&case=chain_all_chips" % run["variant"]["hash"]).json["result"]
        self.assertIs(case["must_route"], True)
        self.assertIn("must_route", run["rows"][0])
        self.assertEqual(subprocess.run(["node", "--check", str(server.WEB_DIR / "lab.js")]).returncode, 0)

    def test_info_lists_the_arrangements_and_a_broken_file_does_not_stop_the_page(self):     # Review Focus 1
        listed = {a["name"]: a for a in self.c.get("/api/info").json["arrangements"]}
        self.assertEqual(list(listed)[0], "v5")
        self.assertEqual({n: (a["feed"], a["engine"]) for n, a in listed.items()},
                         {"v5": (True, "router"), "v6_feed_off": (False, "router"), "v6_rails_on_chips": (False, "solver")})
        self.assertIsNone(listed["v6_feed_off"]["why"])
        self.assertRegex(listed["v6_rails_on_chips"]["why"], r"A\.X\d+ is on TOP_RAIL")
        with tempfile.TemporaryDirectory() as tmp:
            for good in server.arrangement.DIR.glob("*.json"):
                shutil.copy(good, tmp)
            with open(os.path.join(tmp, "mine.json"), "w") as f:
                json.dump({"base": "v5", "pins": {"A.X16": "x"}, "colour": "blue"}, f)
            with open(os.path.join(tmp, "odd.json"), "w") as f:         # a mistake of a shape nobody wrote a rule for
                json.dump({"base": "v5", "remove": [["KL"]]}, f)
            with mock.patch.object(server.arrangement, "DIR", server.Path(tmp)):
                info = self.c.get("/api/info")
                self.assertEqual(info.status, 200, info.body)
                mine = [a for a in info.json["arrangements"] if a["name"] == "mine"][0]
                self.assertNotIn("engine", mine)
                self.assertTrue(any("A.X16" in p for p in mine["problems"]) and any("colour" in p for p in mine["problems"]))
                self.assertEqual(len(info.json["arrangements"]), 5)
                self.assertTrue([a for a in info.json["arrangements"] if a["name"] == "odd"][0]["problems"])
                bad = self.c.get("/api/fabric?arrangement=mine")
                self.assertEqual((bad.status, bad.json["problems"]), (400, mine["problems"]))
                self.assertEqual(self.c.post("/api/run", {"variant": "worktree", "classes": ["dense"], "arrangement": "mine"}).status, 400)

    def test_fabric_of_an_arrangement(self):
        r = self.c.get("/api/fabric?arrangement=v6_rails_on_chips")
        self.assertEqual(r.status, 200, r.body)
        self.assertEqual(len(r.json["fabric"]["changed"]), 24)
        self.assertEqual(r.json["fabric"]["wires"]["TOP_RAIL"]["kind"], "bus")
        self.assertEqual(r.json["nodes"]["101"], {"wire": "TOP_RAIL", "name": "TOP_RAIL"})
        self.assertEqual((r.json["arrangement"]["name"], r.json["arrangement"]["engine"], r.json["arrangement"]["feed"]),
                         ("v6_rails_on_chips", "solver", False))
        self.assertEqual(self.c.get("/api/fabric?arrangement=v5").json["fabric"], self.c.get("/api/info").json["fabric"])
        self.assertEqual(self.c.get("/api/fabric?arrangement=nope").status, 404)
        self.assertEqual(self.c.get("/api/fabric?arrangement=%s" % urllib.parse.quote(
            str(server.arrangement.DIR / "v6_feed_off.json"))).status, 404)        # a name, never a path
        self.assertEqual(self.c.get("/api/fabric").json["arrangement"]["name"], "v5")

    def test_a_run_on_an_arrangement(self):
        r = self.c.post("/api/run", {"variant": "worktree", "classes": ["dense"], "arrangement": "v6_feed_off"})
        self.assertEqual(r.status, 200, r.body)
        self.assertEqual((r.json["arrangement"]["name"], r.json["arrangement"]["engine"]), ("v6_feed_off", "router"))
        self.assertEqual({(row["arrangement"], row["feed"], row["engine"]) for row in r.json["rows"]}, {("v6_feed_off", False, "router")})
        self.assertEqual(sum(row["fully_routed"] for row in r.json["rows"]), 21)       # the K overflow routes with the feed off
        plain = self.c.post("/api/run", {"variant": "worktree", "classes": ["dense"]}).json
        self.assertEqual((plain["arrangement"]["name"], plain["rows"][0]["feed"]), ("v5", True))
        refused = self.c.post("/api/run", {"variant": "worktree", "classes": ["dense"], "arrangement": "v6_rails_on_chips"})
        self.assertEqual(refused.status, 400)
        self.assertRegex(refused.json["error"], r"A\.X\d+ is on TOP_RAIL")              # Review Focus 4
        self.assertEqual(self.c.post("/api/run", {"variant": "worktree", "classes": ["dense"], "arrangement": "nope"}).status, 404)
        both = self.c.post("/api/run", {"variant": "worktree", "baseline": "HEAD", "classes": ["dense"],
                                        "arrangement": "v6_feed_off"}).json
        self.assertEqual({row["base"]["metrics"]["primaries"] == row["metrics"]["primaries"] for row in both["rows"]}, {True})

    def test_runs_on_two_arrangements_are_kept_apart(self):
        feed = lambda run, name: [b for b in self.c.get("/api/case?variant=%s&arrangement=%s&case=chain_all_chips" % (
            run["variant"]["hash"], name)).json["paint"]["bridges"] if b["infra"]]
        for order in (("v5", "v6_feed_off"), ("v6_feed_off", "v5")):
            for name in order:
                run = self.c.post("/api/run", {"variant": "worktree", "classes": ["dense"], "arrangement": name}).json
            self.assertEqual((len(feed(run, "v5")), len(feed(run, "v6_feed_off"))), (1, 0), order)
        self.assertEqual(len(feed(run, "v5")), len([b for b in self.c.get(      # with no arrangement named, V5's
            "/api/case?variant=%s&case=chain_all_chips" % run["variant"]["hash"]).json["paint"]["bridges"] if b["infra"]]))
        self.assertEqual(self.c.get("/api/case?variant=%s&arrangement=nope&case=chain_all_chips" % run["variant"]["hash"]).status, 404)

    def test_a_case_of_a_run_without_a_wire_is_searched_and_asked_on_that_copper(self):
        without = server.arrangement.parse("no_kl", {"base": "v5", "feed": False, "remove": ["KL"]})
        self.c.post("/api/run", {"variant": "worktree", "classes": ["dense"]})
        with mock.patch.object(server.arrangement, "load", return_value=without), \
                mock.patch.object(server.arrangement, "names", return_value=["v5", "no_kl"]):
            run = self.c.post("/api/run", {"variant": "worktree", "classes": ["dense"], "arrangement": "no_kl"}).json
        self.assertEqual(run["arrangement"]["name"], "no_kl")
        fixed = {"verdict": "unknown", "fewest_proved": False, "crosspoints": None, "router_crosspoints": 16, "closed": [],
                 "seconds": 0.3, "error": None}
        ask = {"variant": run["variant"]["hash"], "run": "no_kl", "case": "same_chip_pairs", "rule": "firmware"}
        with mock.patch.object(server.ceiling, "solver_installed", return_value=True), \
                mock.patch.object(server.ceiling, "verdict", return_value=fixed) as asked, \
                mock.patch.object(server.ceiling, "painted", wraps=server.ceiling.painted) as painted:
            self.assertEqual(self.c.post("/api/ceiling", ask).status, 200)
            self.assertIs(asked.call_args.kwargs["arrangement"], without)             # the solver is asked on the run's copper
            self.assertEqual(self.c.post("/api/ceiling", dict(ask, run="v5")).status, 200)
            self.assertIs(asked.call_args.kwargs["arrangement"], server.arrangement.V5)       # and of the run on V5, on V5's
            self.assertEqual(self.c.post("/api/ceiling", dict(ask, run="never_ran")).status, 404)
            self.c.get("/api/case?variant=%s&arrangement=no_kl&case=same_chip_pairs" % run["variant"]["hash"])
            self.assertIs(painted.call_args.args[1], without)                         # and so are the missed and spare paths

    def test_ceiling_on_another_arrangement_than_the_run_answers_the_solvers_routing_as_a_picture(self):
        run = self.c.post("/api/run", {"variant": "worktree", "classes": ["dense"], "arrangement": "v6_feed_off"}).json
        fixed = {"verdict": "routable", "fewest_proved": True, "crosspoints": 2, "router_crosspoints": 12, "seconds": 0.3,
                 "error": None, "closed": [["A", 7, 1, 6], ["A", 7, 2, 6]], "arrangement": "v6_rails_on_chips",
                 "engine": "solver", "unplaced": []}
        ask = {"variant": run["variant"]["hash"], "run": "v6_feed_off", "arrangement": "v6_rails_on_chips",
               "case": "same_chip_pairs", "rule": "firmware"}
        with mock.patch.object(server.ceiling, "solver_installed", return_value=True), \
                mock.patch.object(server.ceiling, "verdict", return_value=fixed) as asked:
            r = self.c.post("/api/ceiling", ask)
            self.assertEqual(r.status, 200, r.body)
            self.assertEqual(asked.call_args.kwargs["arrangement"].name, "v6_rails_on_chips")
            solved = r.json["solved"]
            self.assertEqual((r.json["arrangement"], solved["wires"]["TOP_RAIL"]["nets"], solved["status"]),
                             ("v6_rails_on_chips", [6], "ok"))
            self.assertIn("exact solver", solved["notes"][0])
            self.assertEqual(len(solved["wires"]["TOP_RAIL"]["pins"]), 9)
            self.assertEqual(r.json["paint"]["wires"]["TOP_RAIL"], {"nets": [6]})
            asked.return_value = dict(fixed, verdict="unknown", closed=[], crosspoints=None)
            self.assertIsNone(self.c.post("/api/ceiling", ask).json["solved"])
            self.assertEqual(self.c.post("/api/ceiling", dict(ask, arrangement="nope")).status, 404)
            # a netlist with the probe feed in it is never asked of an arrangement without one
            self.c.post("/api/run", {"variant": "worktree", "classes": ["dense"]})
            asked.reset_mock()
            r = self.c.post("/api/ceiling", dict(ask, run="v5"))
            self.assertEqual(r.status, 409)
            self.assertIn("probe feed on the fabric", r.json["error"])
            self.assertIn("v6_rails_on_chips has it off", r.json["error"])
            asked.assert_not_called()
            self.assertEqual(self.c.post("/api/ceiling", dict(ask, run="v5", arrangement="v5")).status, 200)
            del ask["arrangement"]                                                   # none named: the run's own
            self.c.post("/api/ceiling", ask)
            self.assertEqual(asked.call_args.kwargs["arrangement"].name, "v6_feed_off")

    def test_the_page_draws_the_solvers_routing_on_the_arrangement_picked(self):
        js = self.c.get("/lab.js", token=None).body
        for used in ("arrangement: state.arrangement", ".solved", "one of many; not the firmware's router",
                     "Cannot be placed on", "function solvedShown"):
            self.assertIn(used, js)
        self.assertEqual(subprocess.run(["node", "--check", str(server.WEB_DIR / "lab.js")]).returncode, 0)

    def test_the_page_picks_an_arrangement(self):
        js = self.c.get("/lab.js", token=None).body
        for used in ("/api/fabric?arrangement=", "state.arrangement", "function pickArrangement", "the firmware's router",
                     "probe feed ", "the sheet is V5's own; this arrangement is drawn on the Fabric tab", "&arrangement="):
            self.assertIn(used, js)
        self.assertRegex(js, r"variant\.hash \+ \"/\" \+ \S*arrangement\S* \+ \"/\" \+ name")    # the case store's key
        page = self.c.get("/", token=None).body
        self.assertIn('id="arrangement"', page)
        self.assertLess(page.index('id="baseline"'), page.index('id="arrangement"'))
        css = self.c.get("/lab.css", token=None).body
        for rule in (".pin-taken", ".pin-changed"):
            self.assertIn(rule, css)
            self.assertNotIn("--problem", css[css.index(rule):].split("}")[0])        # red means a problem and nothing else
        self.assertEqual(subprocess.run(["node", "--check", str(server.WEB_DIR / "lab.js")]).returncode, 0)

    def ranking(self, hash_, name="v6_feed_off", **more):
        """A ranking as lab.py rank writes one, of two wires."""
        wire = lambda name, kind, pins, loss: {
            "wire": name, "kind": kind, "pins": pins, "usage": {"cases": 3, "primary": 4, "duplicate": 0},
            "loss": {"primaries": loss, "fully_routed": 0, "crosspoints": 2, "worst_r": 0.0}, "by_class": {}, "worse": [],
            "better": [], "used_after": 0}
        return dict({"arrangement": name, "feed": False, "engine": "router", "variant": {"name": "worktree", "hash": hash_},
                     "nodes_as_v5": True, "cases": 21, "baseline": {"primaries": 210, "fully_routed": 21, "crosspoints": 670, "worst_r": 4.0},
                     "wires": [wire("KL", "hub", [["K", "X", 12], ["L", "X", 14]], -1),
                               wire("AK", "sf lane", [["A", "X", 9], ["K", "Y", 0]], 4)]}, **more)

    def test_rank_answers_the_ranking_on_file_or_says_how_to_make_one(self):
        hash_ = self.c.get("/api/watch?spec=worktree").json["hash"]
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(server.rank, "DIR", server.Path(tmp)):
            missing = self.c.get("/api/rank?variant=worktree&arrangement=v6_feed_off")
            self.assertEqual((missing.status, missing.json["hint"]), (404, "python3 Routing/lab.py rank --needed"))
            server.rank.save(self.ranking(hash_))
            r = self.c.get("/api/rank?variant=worktree&arrangement=v6_feed_off")
            self.assertEqual(r.status, 200, r.body)
            self.assertEqual(([w["wire"] for w in r.json["wires"]], r.json["arrangement"], r.json["engine"]),
                             (["KL", "AK"], "v6_feed_off", "router"))
            self.assertRegex(r.json["made"], r"^20\d\d-\d\d-\d\d \d\d:\d\d$")
            self.assertEqual(self.c.get("/api/rank?variant=worktree&arrangement=v5").status, 404)       # another arrangement's
            self.assertEqual(self.c.get("/api/rank?variant=worktree&arrangement=nope").status, 404)
            self.assertEqual(self.c.get("/api/rank?variant=worktree").status, 404)                      # v5 when none is named

    def test_rank_now_runs_the_routers_part_once_at_a_time_and_says_how_far_it_is(self):
        hash_ = self.c.get("/api/watch?spec=worktree").json["hash"]
        seen, second = [], []

        def removal(v, case_list, a, wires=None, progress=None):
            progress(1, 2, "KL")
            seen.append(self.c.get("/api/job").json)
            second.append(self.c.post("/api/rank", {"variant": "worktree", "arrangement": "v6_feed_off", "classes": ["dense"]}).status)
            progress(2, 2, "AK")
            return self.ranking(v.hash, a.name, cases=len(case_list))

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(server.rank, "DIR", server.Path(tmp)), \
                mock.patch.object(server.rank, "removal", side_effect=removal) as ranked, \
                mock.patch.object(server.rank, "needed", side_effect=AssertionError("the solver's part is not started from the page")):
            r = self.c.post("/api/rank", {"variant": "worktree", "arrangement": "v6_feed_off", "classes": ["dense"]})
            self.assertEqual(r.status, 200, r.body)
            self.assertEqual((r.json["cases"], r.json["arrangement"], [w["wire"] for w in r.json["wires"]]), (21, "v6_feed_off", ["KL", "AK"]))
            self.assertEqual(seen, [{"what": "ranking", "done": 1, "of": 2, "wire": "KL"}])
            self.assertEqual(second, [409])                              # one at a time
            self.assertEqual(self.c.get("/api/job").json, {"what": None, "done": 0, "of": 0, "wire": None})
            self.assertEqual(ranked.call_args.args[2].name, "v6_feed_off")
            self.assertEqual(self.c.get("/api/rank?variant=worktree&arrangement=v6_feed_off").json["wires"], r.json["wires"])   # the same file
            refused = self.c.post("/api/rank", {"variant": "worktree", "arrangement": "v6_rails_on_chips", "classes": ["dense"]})
            self.assertEqual(refused.status, 400)                        # the router cannot route it; nothing is left running
        with mock.patch.object(server.rank, "removal", side_effect=server.arrangement.RouterCannot("the firmware's router cannot route x")):
            self.assertEqual(self.c.post("/api/rank", {"variant": "worktree", "arrangement": "v6_feed_off", "classes": ["dense"]}).status, 400)
        self.assertIsNone(self.c.get("/api/job").json["what"])
        self.assertEqual(self.c.post("/api/rank", {"variant": "worktree", "classes": ["nope"]}).status, 400)

    def test_a_ranking_made_again_keeps_what_the_solver_proved(self):
        hash_ = "f" * 64
        need = lambda w, by: dict(w, needed_by=by, not_needed=20 - len(by), unknown=[])
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(server.rank, "DIR", server.Path(tmp)):
            first = self.ranking(hash_, engine="router and solver", rule="firmware", seconds=5.0, needed_cases=20)
            first["wires"] = [need(first["wires"][0], []), need(first["wires"][1], ["k_rows_all_eight"])]
            server.rank.save(first)
            again = self.ranking(hash_)
            again["wires"][1]["loss"]["primaries"] = 7                   # the router's part made anew
            written = server.rank.save(again)
            with open(server.rank.path(hash_, "v6_feed_off")) as f:
                self.assertEqual(json.load(f), written)
        self.assertEqual((written["engine"], written["needed_cases"], written["rule"]), ("router and solver", 20, "firmware"))
        self.assertEqual([(w["loss"]["primaries"], w["needed_by"]) for w in written["wires"]], [(-1, []), (7, ["k_rows_all_eight"])])

    def test_a_run_without_wires_names_them_and_hands_back_the_file(self):
        body = {"variant": "worktree", "classes": ["dense"], "arrangement": "v6_feed_off", "without": ["KL", "IJ"]}
        r = self.c.post("/api/run", body)
        self.assertEqual(r.status, 200, r.body)
        made = r.json["arrangement"]
        self.assertEqual((made["name"], made["engine"], made["feed"]), ("v6_feed_off without KL, IJ", "router", False))
        self.assertEqual(server.arrangement.check(json.loads(made["json"])), [])
        self.assertEqual(len(server.arrangement.parse("pasted", json.loads(made["json"])).taken), 4)
        self.assertEqual({row["arrangement"] for row in r.json["rows"]}, {"v6_feed_off without KL, IJ"})
        quoted = urllib.parse.quote(made["name"])
        case = self.c.get("/api/case?variant=%s&arrangement=%s&case=chain_all_chips" % (r.json["variant"]["hash"], quoted))
        self.assertEqual(case.status, 200, case.body)
        used = {copper.wire(c["chip"], "X", c["x"]) for c in case.json["paint"]["crosspoints"]}
        self.assertFalse(used & {"KL", "IJ"})
        drawn = self.c.get("/api/fabric?arrangement=%s" % quoted)        # what was run can be drawn, and run again, by its name
        self.assertEqual((drawn.status, len(drawn.json["fabric"]["taken"]), drawn.json["arrangement"]["json"]), (200, 4, made["json"]))
        self.assertEqual(self.c.post("/api/run", dict(body, arrangement=made["name"], without=["/AB0"])).json["arrangement"]["name"],
                         "v6_feed_off without KL, IJ without /AB0")
        self.assertNotIn("json", self.c.post("/api/run", dict(body, without=[])).json["arrangement"])
        for bad in (["NO_SUCH"], "KL", [7]):
            refused = self.c.post("/api/run", dict(body, without=bad))
            self.assertEqual(refused.status, 400, bad)
        self.assertIn("NO_SUCH", self.c.post("/api/run", dict(body, without=["NO_SUCH"])).json["error"])

    def test_the_page_has_the_ranking_tab(self):
        js = self.c.get("/lab.js", token=None).body
        for used in ("/api/rank", "/api/job", "function drawHeat", "Run without these", "Rank now", "without: ",
                     "lab.py rank --needed", "needed: the exact solver proves"):
            self.assertIn(used, js)
        page = self.c.get("/", token=None).body
        self.assertIn('data-side="ranking"', page)                    # the right panel's other face, not a view
        self.assertNotIn('data-tab="ranking"', page)
        css = self.c.get("/lab.css", token=None).body
        self.assertIn(".heat", css)
        for rule in re.findall(r"[^{}]*\.heat[^{}]*\{[^}]*\}", css):
            self.assertNotIn("--problem", rule)                          # the heat uses no red
            self.assertNotIn("#ff5252", rule)
        self.assertEqual(subprocess.run(["node", "--check", str(server.WEB_DIR / "lab.js")]).returncode, 0)

    def test_a_netlist_made_by_hand_is_routed_on_the_arrangement_named(self):
        def bridges_of(run):
            case = self.c.get("/api/case?variant=%s&arrangement=%s&case=drawn" % (
                run["variant"]["hash"], urllib.parse.quote(run["arrangement"]["name"])))
            self.assertEqual(case.status, 200, case.body)
            asked = [b for b in case.json["paint"]["bridges"] if not b["infra"]]
            return {frozenset((b["n1"], b["n2"])) for b in asked}, len(case.json["paint"]["bridges"]) - len(asked)

        body = {"variant": "worktree", "arrangement": "v5", "bridges": [[1, 8], [3, 101]]}
        r = self.c.post("/api/route", body)
        self.assertEqual(r.status, 200, r.body)
        self.assertEqual((r.json["drawn"], r.json["arrangement"]["name"], r.json["baseline"], r.json["regressions"]), (True, "v5", None, []))
        self.assertEqual([(x["case"], x["cls"], x["fully_routed"], x["must_route"], x["engine"]) for x in r.json["rows"]],
                         [("drawn", "drawn", True, False, "router")])
        self.assertEqual(bridges_of(r.json), ({frozenset((1, 8)), frozenset((3, 101))}, 1))     # and the probe feed's
        off = self.c.post("/api/route", dict(body, arrangement="v6_feed_off")).json
        self.assertEqual((off["arrangement"]["name"], bridges_of(off)[1]), ("v6_feed_off", 0))
        again = self.c.post("/api/route", dict(body, arrangement="v6_feed_off", bridges=[[2, 9]])).json   # the netlist as it now is
        self.assertEqual((len(again["rows"]), bridges_of(again)[0]), (1, {frozenset((2, 9))}))
        self.assertEqual(self.c.post("/api/route", {"arrangement": "v5", "bridges": [[1, 8]]}).status, 400)          # no variant
        self.assertEqual(self.c.post("/api/route", dict(body, arrangement="nope")).status, 404)
        with mock.patch.object(variants, "build", side_effect=variants.BuildError("x.cpp:1: error: no")):
            broken = self.c.post("/api/route", dict(body, bridges=[[4, 12]]))
        self.assertEqual((broken.status, broken.json["which"]), (200, "variant"))
        self.assertIn("x.cpp:1: error: no", broken.json["build_error"])

    def test_a_netlist_made_by_hand_on_copper_the_router_cannot_route_goes_to_the_solver(self):
        r = self.c.post("/api/route", {"variant": "worktree", "arrangement": "v6_rails_on_chips", "bridges": [[1, 101]]})
        self.assertEqual(r.status, 200, r.body)
        on = r.json["arrangement"]                                      # the harness made the netlist on V5's copper, feed off
        self.assertEqual((on["name"], on["engine"], on["feed"], r.json["rows"][0]["feed"]), ("v5, feed off", "router", False, False))
        fixed = {"verdict": "routable", "fewest_proved": True, "crosspoints": 1, "router_crosspoints": 2, "seconds": 0.1,
                 "error": None, "closed": [["A", 7, 1, 2]], "arrangement": "v6_rails_on_chips", "engine": "solver", "unplaced": []}
        with mock.patch.object(server.ceiling, "solver_installed", return_value=True), \
                mock.patch.object(server.ceiling, "verdict", return_value=fixed) as asked:
            said = self.c.post("/api/ceiling", {"variant": r.json["variant"]["hash"], "run": on["name"], "case": "drawn",
                                                "arrangement": "v6_rails_on_chips", "rule": "firmware"})
        self.assertEqual(said.status, 200, said.body)
        self.assertEqual(asked.call_args.kwargs["arrangement"].name, "v6_rails_on_chips")
        self.assertEqual(said.json["solved"]["wires"]["TOP_RAIL"]["nets"], [2])

    def test_a_netlist_made_by_hand_that_cannot_be_one_is_refused_with_the_reason(self):
        body = {"variant": "worktree", "arrangement": "v5"}
        for bridges, word in (([[1, 999]], "999"), ([[1, 1]], "two different"), ([], "bridge"), ([[1]], "two different"),
                              ([[1, "8"]], "two different"), ([[1, True]], "two different"), ("1-8", "bridge"),
                              ([[i + 1, i + 2] for i in range(201)], "200")):
            with mock.patch.object(variants, "build", side_effect=AssertionError("built for a netlist that is none")):
                r = self.c.post("/api/route", dict(body, bridges=bridges))
            self.assertEqual(r.status, 400, bridges)
            self.assertIn(word, r.json["error"], bridges)
        self.assertEqual(self.c.post("/api/route", body).status, 400)                      # no bridges at all
        no_rail = server.arrangement.parse("no_rail", {"base": "v5", "feed": False, "pins": {"K.X4": None}})
        with mock.patch.object(server.arrangement, "load", return_value=no_rail), \
                mock.patch.object(server.arrangement, "names", return_value=["v5", "no_rail"]):
            r = self.c.post("/api/route", dict(body, arrangement="no_rail", bridges=[[1, 101]]))
        self.assertEqual((r.status, r.json["rows"][0]["status"]), (200, "unplaced"))       # a node it dropped: placed nowhere, not refused
        self.assertIn("TOP_RAIL", r.json["rows"][0]["notes"][0])

    def test_the_page_makes_a_netlist_by_clicks_on_nodes(self):
        js = self.c.get("/lab.js", token=None).body
        for used in ("/api/route", "function routeDrawn", "function clickNode", "start from the case shown", "state.drawn",
                     'event.key === "Escape"'):
            self.assertIn(used, js)
        self.assertRegex(js, r"view\.append\([^)]*\bhits, pads\b")       # the pads lie over the wires' hit areas: a click lands on them
        page = self.c.get("/", token=None).body
        self.assertIn('id="drawn"', page)
        self.assertIn(".pad.from", self.c.get("/lab.css", token=None).body)
        self.assertEqual(subprocess.run(["node", "--check", str(server.WEB_DIR / "lab.js")]).returncode, 0)

    def test_a_bridge_added_to_a_case_is_routed_with_that_cases_settings(self):       # verification, F4
        run = self.c.post("/api/run", {"variant": "worktree", "classes": ["dense"]}).json
        own = self.c.get("/api/case?variant=%s&arrangement=v5&case=same_chip_pairs" % run["variant"]["hash"]).json
        pairs = [list(p) for p in sorted({tuple(sorted((b["n1"], b["n2"]))) for b in own["paint"]["bridges"] if not b["infra"]})]
        body = {"variant": "worktree", "arrangement": "v5", "bridges": pairs, "from": {"cls": "dense", "case": "same_chip_pairs"}}
        same = self.c.post("/api/route", body)
        self.assertEqual(same.status, 200, same.body)
        row, mine = same.json["rows"][0], [r for r in run["rows"] if r["case"] == "same_chip_pairs"][0]
        for k in ("crosspoints", "routed_duplicates", "primaries"):
            self.assertEqual(row["metrics"][k], mine["metrics"][k], k)  # nothing added: the case as the run routed it
        self.assertIn("same_chip_pairs", row["about"])
        plain = self.c.post("/api/route", dict(body, **{"from": None})).json["rows"][0]
        self.assertNotEqual(plain["metrics"]["crosspoints"], mine["metrics"]["crosspoints"])     # defaults are not the case's
        more = self.c.post("/api/route", dict(body, bridges=pairs + [[20, 25]])).json["rows"][0]
        self.assertEqual(more["metrics"]["primaries"], mine["metrics"]["primaries"] + 1)
        for bad in ({"cls": "dense", "case": "nope"}, "same_chip_pairs", {"cls": "nope", "case": "x"}, {"case": "same_chip_pairs"}):
            self.assertEqual(self.c.post("/api/route", dict(body, **{"from": bad})).status, 400, bad)

    def test_a_case_with_nothing_added_routes_as_the_run_did_whatever_order_the_page_sends(self):   # round 2, V4
        run = self.c.post("/api/run", {"variant": "worktree", "classes": ["beyond"]}).json
        for row in run["rows"]:
            paint = self.c.get("/api/case?variant=%s&arrangement=v5&case=%s" % (run["variant"]["hash"], row["case"])).json["paint"]
            seen, pairs = set(), []
            for b in paint["bridges"]:                                  # as the page's shownBridges() sends them
                if not b["infra"] and frozenset((b["n1"], b["n2"])) not in seen:
                    seen.add(frozenset((b["n1"], b["n2"])))
                    pairs.append([b["n1"], b["n2"]])
            got = self.c.post("/api/route", {"variant": "worktree", "arrangement": "v5", "bridges": pairs,
                                             "from": {"cls": "beyond", "case": row["case"]}}).json["rows"][0]["metrics"]
            for k in ("primaries", "routed_primaries", "crosspoints", "routed_duplicates"):
                self.assertEqual(got[k], row["metrics"][k], (row["case"], k))

    def test_bridges_added_to_a_case_go_after_all_of_its_own(self):   # verification round 3, W3: a pair listed three times
        crafted = server.cases.Case("crafted", "dense", [(1, 2, -1), (1, 2, -1), (1, 2, -1), (10, 20, -1), (30, 40, -1)])
        sent = []
        real = server.runner.run_battery
        with mock.patch.object(server.lab, "battery", return_value=[crafted]), \
                mock.patch.object(server.runner, "run_battery", side_effect=lambda v, cs, **kw: sent.append(cs) or real(v, cs, **kw)):
            r = self.c.post("/api/route", {"variant": "worktree", "arrangement": "v5", "bridges": [[1, 2], [10, 20], [30, 40], [50, 55]],
                                           "from": {"cls": "dense", "case": "crafted"}})
        self.assertEqual(r.status, 200, r.body)
        self.assertEqual([b[:2] for b in sent[-1][0].bridges], [(1, 2), (10, 20), (30, 40), (50, 55)])

    def test_a_ranking_of_copper_the_file_no_longer_has_is_marked(self):          # verification, F2/R
        with tempfile.TemporaryDirectory() as tmp:
            arr, rk = server.Path(tmp) / "arr", server.Path(tmp) / "rank"
            arr.mkdir()
            (arr / "foo.json").write_text(json.dumps({"base": "v5", "feed": False}))
            with mock.patch.object(server.arrangement, "DIR", arr), mock.patch.object(server.rank, "DIR", rk):
                hash_ = self.c.get("/api/watch?spec=worktree").json["hash"]
                server.rank.save(self.ranking(hash_, "foo", fabric=server.rank.fabric_of(server.arrangement.load("foo"))))
                self.assertIs(self.c.get("/api/rank?variant=worktree&arrangement=foo").json["stale"], False)
                (arr / "foo.json").write_text(json.dumps({"base": "v5", "feed": False, "remove": ["KL"]}))
                self.assertIs(self.c.get("/api/rank?variant=worktree&arrangement=foo").json["stale"], True)

    def test_the_page_after_the_final_review(self):
        js = self.c.get("/lab.js", token=None).body
        for used in ("function shownBridges",                    # a clicked bridge is added to the case on screen
                     "state.v5nodes",                             # a node the arrangement dropped still has its name
                     "the router routes more without it",         # a gain has its own tint and its own words
                     "are not part of a ranking",                 # dropped files and the Ranking tab
                     "save its file first",                       # an arrangement that is no file cannot be named to lab.py
                     "state.rankingFor === wanted",               # a ranking that lands late is not shown for another arrangement
                     # after the verification workflow:
                     "from: state.drawnFrom",                     # the case's settings go with its bridges
                     "state.drawnFrom = null",                    # a new run on screen starts a click afresh
                     "if (state.arrangement !== asked",           # an arrangement picked while a route is out: routed again
                     'picked().engine === "solver"',              # the solver is named only where it is the one routing
                     "r.stale", "r.set_aside",                    # the Ranking tab says when a ranking is of other copper
                     "JSON.stringify(state.arrangement)"):        # a name with a space stays one argument
            self.assertIn(used, js)
        self.assertNotIn("click Run, or change the netlist again", js)
        self.assertNotIn("!state.drawn.length && state.current", js)  # a click starts from the case on screen, not an old netlist
        # round 2 (V4): the box is drawn busy as soon as the page is; a press then says why; a build error keeps no clicked
        # bridge; the picker leaves a route in flight to route again by itself
        self.assertRegex(js, r"state\.busy = true;\n(\s*const asked = state\.arrangement;\n)?\s*renderDrawn\(\);")
        self.assertEqual(len(re.findall(r"state\.busy = true;\n(?:\s*const asked = state\.arrangement;\n)?\s*renderDrawn\(\);", js)), 3)
        self.assertIn('showProblem("A run is in flight: wait for it, then change the netlist made by hand.")', js)
        self.assertEqual(js.count("if (added) state.drawn = state.drawn.filter((pair) => pair !== added);"), 2)
        self.assertIn("if (state.run && state.run.drawn && !state.busy) await routeDrawn();", js)
        # close-out: a case shown with no bridges in its paint (a crash, a timeout, a case that cannot be placed) is no
        # case to add to: a click starts a netlist of its own, and the box does not say "added to the case shown"
        self.assertIn("function caseToAddTo()", js)
        self.assertEqual(js.count("caseToAddTo()"), 3)                  # defined, and asked in clickNode and in renderDrawn
        self.assertEqual(subprocess.run(["node", "--check", str(server.WEB_DIR / "lab.js")]).returncode, 0)

    def test_watch_reports_the_tree_hash(self):
        self.assertEqual(self.c.get("/api/watch?spec=worktree").json["hash"], variants.resolve("worktree").hash)

    def test_sheet_says_how_to_build_it_when_it_is_missing(self):
        with mock.patch.object(server, "SHEET_DIR", server.SHEET_DIR / "not-there"):
            r = self.c.get("/api/sheet")
            self.assertEqual(r.status, 404)
            self.assertIn("lab.py sheet", r.json["hint"])

    def test_sheet_is_served_once_it_is_built(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(server, "SHEET_DIR", Path(tmp)):
            (Path(tmp) / "overlay.json").write_text(json.dumps({"size": [841.0, 594.0], "nets": {}, "pins": {"A.X0": [1, 2]},
                                                                "bodies": {}}))
            (Path(tmp) / "backdrop.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
            self.assertEqual(self.c.get("/api/sheet").json["pins"], {"A.X0": [1, 2]})
            r = self.c.get("/sheet/backdrop.svg", token=None)
            self.assertEqual(r.status, 200)
            self.assertIn("svg", r.headers["Content-Type"])
            self.assertIs(self.c.get("/api/info").json["sheet"], True)

    def test_unknown_api_path_is_404_and_bad_json_is_400(self):
        self.assertEqual(self.c.get("/api/nope").status, 404)
        self.assertEqual(self.c.request("POST", "/api/run", raw=b"{not json").status, 400)
        self.assertEqual(self.c.request("POST", "/api/run", raw=b"[1, 2]").status, 400)


if __name__ == "__main__":
    unittest.main()
