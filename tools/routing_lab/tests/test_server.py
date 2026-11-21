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
        self.assertEqual(info["classes"], ["dense", "real", "typical", "fuzz", "stress", "beyond"])
        self.assertEqual(info["variants"][0], {"spec": "worktree", "name": "worktree"})
        self.assertEqual(info["ohms"], 60)
        self.assertIn("A", info["fabric"]["chips"])
        self.assertIs(info["verified"], False)
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

    def test_watch_reports_the_tree_hash(self):
        self.assertEqual(self.c.get("/api/watch?spec=worktree").json["hash"], variants.resolve("worktree").hash)

    def test_sheet_says_how_to_build_it_when_it_is_missing(self):
        with mock.patch.object(server, "SHEET_DIR", server.SHEET_DIR / "not-there"):
            r = self.c.get("/api/sheet")
            self.assertEqual(r.status, 404)
            self.assertIn("lab.py sheet", r.json["hint"])

    def test_unknown_api_path_is_404_and_bad_json_is_400(self):
        self.assertEqual(self.c.get("/api/nope").status, 404)
        self.assertEqual(self.c.request("POST", "/api/run", raw=b"{not json").status, 400)
        self.assertEqual(self.c.request("POST", "/api/run", raw=b"[1, 2]").status, 400)


if __name__ == "__main__":
    unittest.main()
