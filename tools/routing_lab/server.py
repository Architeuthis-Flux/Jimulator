# SPDX-License-Identifier: MIT
"""The routing lab's local server: the page, and an API over the battery.

It compiles and runs C++ it is handed, so it is closed to everything but its
own page:

- it listens on 127.0.0.1 only;
- every request must name this server as its Host (a foreign name pointed at
  127.0.0.1 gets nothing, not even the page that holds the token), and an
  Origin header, when present, must be this server's;
- every /api/ request must carry the token the server made at start, which
  only its own page is given;
- a variant is "worktree", a git ref, or a directory named when the server
  was started; uploaded files must land under src/.
"""
import hmac
import http.server
import json
import os
import secrets
import urllib.parse
from pathlib import Path

import copper
import fabric_view
import lab
import runner
import variants

LAB = Path(__file__).resolve().parent
WEB_DIR = LAB / "web"
SHEET_DIR = variants.BUILD_DIR / "sheet"
MAX_UPLOAD = 5_000_000
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".json": "application/json"}


class Refused(Exception):
    """An answer that is an error: (status, message)."""

    def __init__(self, status, message, **extra):
        super().__init__(message)
        self.status, self.body = status, dict(error=message, **extra)


class LabServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port, trees):
        super().__init__(("127.0.0.1", port), Handler)
        self.token = secrets.token_urlsafe(24)
        self.trees = [str(Path(t).expanduser().resolve()) for t in trees]
        self.runs = {}                      # variant hash -> {case name: result}

    @property
    def url(self):
        return "http://127.0.0.1:%d/" % self.server_address[1]


def make_server(port=0, trees=()):
    return LabServer(port, trees)


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "RoutingLab"

    def log_message(self, fmt, *args):      # quiet: the page shows what matters
        pass

    # --- answers -------------------------------------------------------------
    def send(self, status, body, content_type="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    # --- who is asking ---------------------------------------------------------
    def check_caller(self, api):
        port = self.server.server_address[1]
        hosts = ("127.0.0.1:%d" % port, "localhost:%d" % port)
        if self.headers.get("Host") not in hosts:
            raise Refused(403, "this server answers only as 127.0.0.1 or localhost")
        origin = self.headers.get("Origin")
        if origin is not None and origin not in tuple("http://" + h for h in hosts):
            raise Refused(403, "requests from other pages are refused")
        if api and not hmac.compare_digest(self.headers.get("X-Lab-Token", ""), self.server.token):
            raise Refused(403, "missing or wrong token")

    # --- routing ---------------------------------------------------------------
    def do_GET(self):
        self.handle_request("GET")

    def do_POST(self):
        self.handle_request("POST")

    def handle_request(self, method):
        url = urllib.parse.urlsplit(self.path)
        query = dict(urllib.parse.parse_qsl(url.query))
        api = url.path.startswith("/api/")
        try:
            self.check_caller(api)
            if not api:
                if method != "GET":
                    raise Refused(405, "GET only")
                return self.static(url.path)
            handler = getattr(self, "api_%s_%s" % (method.lower(), url.path[5:].replace("/", "_")), None)
            if handler is None:
                raise Refused(404, "no such API call")
            body = self.read_json() if method == "POST" else None
            self.send(200, handler(query, body))
        except Refused as e:
            self.send(e.status, e.body)
        except BrokenPipeError:
            pass

    def read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_UPLOAD + 200_000:
            # Read past it (up to a limit) without keeping it, so the sender
            # gets this answer and not a broken connection.
            left = min(length, 8 * MAX_UPLOAD)
            while left > 0:
                chunk = self.rfile.read(min(left, 1 << 16))
                if not chunk:
                    break
                left -= len(chunk)
            raise Refused(413, "upload too large (5 MB at most)")
        try:
            body = json.loads(self.rfile.read(length) or b"null")
        except ValueError:
            raise Refused(400, "the request body is not JSON") from None
        if not isinstance(body, dict):
            raise Refused(400, "the request body must be a JSON object")
        return body

    def static(self, path):
        if path == "/":
            page = (WEB_DIR / "index.html").read_text().replace("__LAB_TOKEN__", self.server.token)
            return self.send(200, page.encode(), TYPES[".html"])
        if path == "/sheet/backdrop.svg":
            target = SHEET_DIR / "backdrop.svg"
        else:
            target = (WEB_DIR / urllib.parse.unquote(path).lstrip("/")).resolve()
            if WEB_DIR.resolve() not in target.parents:
                raise Refused(404, "not found")
        if not target.is_file() or target.suffix not in TYPES:
            raise Refused(404, "not found")
        self.send(200, target.read_bytes(), TYPES[target.suffix])

    # --- variants ----------------------------------------------------------------
    def resolve(self, wanted):
        """A Variant from what the page sent: a spec, or {"base": spec, "files": {path: text}}."""
        base, files = (wanted.get("base", "worktree"), wanted.get("files") or {}) if isinstance(wanted, dict) \
            else (wanted, {})
        if not isinstance(base, str) or not base or not isinstance(files, dict):
            raise Refused(400, "a variant is a name, or {base, files}")
        if sum(len(str(text)) for text in files.values()) > MAX_UPLOAD:
            raise Refused(413, "upload too large (5 MB at most)")
        directory = os.path.isabs(os.path.expanduser(base))
        if directory and str(Path(base).expanduser().resolve()) not in self.server.trees:
            raise Refused(400, "%s is not a tree this server was started with (--tree)" % base)
        try:
            overrides = {path: str(text).encode() for path, text in files.items()} or None
            return variants.resolve(base, overrides, allow_directory=directory)
        except ValueError as e:
            raise Refused(400, str(e)) from None

    def battery_of(self, wanted, case_list):
        """(variant, results). A file saved while the build ran makes the build
        refuse to file its binary; resolve again and build once more."""
        for attempt in (0, 1):
            v = self.resolve(wanted)
            try:
                results = runner.run_battery(v, case_list)
            except variants.BuildError as e:
                if attempt == 0 and "sources changed" in e.stderr:
                    continue
                e.variant = v
                raise
            self.server.runs[v.hash] = {r["case"]: r for r in results}
            return v, results

    # --- API -----------------------------------------------------------------------
    def api_get_info(self, query, body):
        named = [{"spec": t, "name": os.path.basename(t)} for t in self.server.trees]
        return {"classes": lab.CLASSES, "variants": [{"spec": "worktree", "name": "worktree"}] + named,
                "verified": lab.verified_against_a_board(), "ohms": 60, "fabric": fabric_view.layout(),
                "sheet": (SHEET_DIR / "overlay.json").is_file()}

    def api_post_run(self, query, body):
        classes = body.get("classes") or ["dense", "real"]
        try:
            case_list = lab.battery(classes)
        except (ValueError, TypeError) as e:
            raise Refused(400, str(e)) from None
        if "variant" not in body:
            raise Refused(400, "no variant")
        try:
            v, results = self.battery_of(body["variant"], case_list)
        except variants.BuildError as e:
            return {"build_error": e.stderr, "which": "variant", "variant": {"name": e.variant.name}}
        base_v = base = None
        if body.get("baseline"):
            try:
                base_v, base = self.battery_of(body["baseline"], case_list)
            except variants.BuildError as e:
                return {"build_error": e.stderr, "which": "baseline", "variant": {"name": e.variant.name}}
        before = {r["case"]: r for r in base or []}
        return {"variant": {"name": v.name, "hash": v.hash},
                "baseline": {"name": base_v.name, "hash": base_v.hash} if base_v else None,
                "rows": [row(r, before.get(r["case"])) for r in results],
                "regressions": lab.regressions(base, results) if base else []}

    def api_get_case(self, query, body):
        result = self.server.runs.get(query.get("variant"), {}).get(query.get("case"))
        if result is None:
            raise Refused(404, "no such run or case; run the battery first")
        return {"result": result, "paint": copper.paint(result)}

    def api_get_watch(self, query, body):
        return {"hash": self.resolve(query.get("spec", "worktree")).hash}

    def api_get_sheet(self, query, body):
        overlay = SHEET_DIR / "overlay.json"
        if not overlay.is_file():
            raise Refused(404, "the KiCad sheet has not been built", hint="python3 tools/routing_lab/lab.py sheet")
        return json.loads(overlay.read_text())


def row(result, base=None):
    """A result without its report text, for the table."""
    out = {k: v for k, v in result.items() if k not in ("b", "xbar", "stderr")}
    out["fully_routed"] = lab.fully_routed(result)
    if base is not None:
        out["base"] = {"status": base["status"], "metrics": base["metrics"], "problems": base["problems"],
                       "fully_routed": lab.fully_routed(base)}
    return out
