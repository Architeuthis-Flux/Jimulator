# SPDX-License-Identifier: MIT
import contextlib
import http.client
import json
import os
import subprocess
import threading
import unittest
from unittest import mock

import server
import variants

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(LAB))
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
        self.assertEqual(info["classes"], ["dense", "real", "typical", "fuzz", "stress", "beyond", "edge"])
        self.assertEqual(info["variants"][0], {"spec": "worktree", "name": "worktree"})
        self.assertEqual(info["ohms"], 60)
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
        self.assertTrue(r["baseline"]["name"].startswith("HEAD@"))

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
        self.assertIn(run["variant"]["hash"], self.srv.runs)            # the newest stays

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
