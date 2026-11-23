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
import dataclasses
import hmac
import http.server
import json
import os
import secrets
import subprocess
import threading
import time
import urllib.parse
from pathlib import Path

import arrangement
import board
import cases
import ceiling
import fabric_view
import lab
import rank
import runner
import variants

LAB = Path(__file__).resolve().parent
WEB_DIR = LAB / "web"
SHEET_DIR = variants.BUILD_DIR / "sheet"
MAX_UPLOAD = 5_000_000
MAX_RUNS = 6            # runs (a variant on an arrangement) whose results are held for /api/case; about 9 MB each
BOARD = "board"         # what uploaded board output is held under, where a run has its variant's hash
DRAWN = "drawn"         # the name and the class of the netlist made by clicking nodes on the page
MAX_DRAWN = 200         # bridges in it, at most
IDLE = {"what": None, "done": 0, "of": 0, "wire": None}        # /api/job when nothing long is running
RANK_HINT = "python3 tools/routing_lab/lab.py rank --needed"
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
        self.runs = {}                      # (variant hash, arrangement name) -> {case name: result}
        self.ran_on = {}                    # arrangement name -> the Arrangement its runs were made on
        self.ranking = threading.Lock()     # one ranking at a time: it takes minutes and every core
        self.job = IDLE                     # how far the ranking that is running has got (GET /api/job)

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
        self.send_header("X-Frame-Options", "DENY")          # another page cannot put this one in a frame
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
        if api and not hmac.compare_digest(self.headers.get("X-Lab-Token", "").encode(), self.server.token.encode()):
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
        except Exception as e:              # unforeseen: the page gets a reason, not a dropped connection
            self.send(500, {"error": "%s: %s" % (type(e).__name__, e)})

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0:
            raise Refused(400, "bad Content-Length")
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
            try:
                target = (WEB_DIR / urllib.parse.unquote(path).lstrip("/")).resolve()
            except ValueError:              # a NUL in the path
                raise Refused(404, "not found") from None
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

    def arrangement_of(self, name):
        """The arrangement the page named: one of the list's names (read from
        its file afresh), or one this server has run that is no file ("x
        without KL"); never a path. 404 for any other, 400 with the problems
        for a file with a mistake."""
        name = "v5" if name is None else name
        if isinstance(name, str) and name not in arrangement.names() and name in self.server.ran_on:
            return self.server.ran_on[name]
        if not isinstance(name, str) or name not in arrangement.names():
            raise Refused(404, "there is no arrangement %s" % (name,))
        try:
            return arrangement.load(name)
        except arrangement.Bad as e:
            raise Refused(400, str(e), problems=e.problems) from None

    def cases_of(self, body):
        try:
            return lab.battery(body.get("classes") or ["dense", "real"])
        except (ValueError, TypeError) as e:
            raise Refused(400, str(e)) from None

    def battery_of(self, wanted, case_list, a):
        """(variant, results) of the battery on the arrangement `a`. A file
        saved while the build ran makes the build refuse to file its binary;
        resolve again and build once more."""
        for attempt in (0, 1):
            v = self.resolve(wanted)
            try:
                results = runner.run_battery(v, case_list, arrangement=a)
            except arrangement.RouterCannot as e:
                raise Refused(400, str(e)) from None
            except variants.BuildError as e:
                if attempt == 0 and "sources changed" in e.stderr:
                    continue
                e.variant = v
                raise
            self.server.ran_on[a.name] = a
            self.keep((v.hash, a.name), results)
            return v, results

    def kept(self, variant, run, case):
        """(result, arrangement): one case of the run of a variant (its hash) on an arrangement (its name)."""
        key = (variant, run) if isinstance(variant, str) and isinstance(run, str) else None
        result = self.server.runs.get(key, {}).get(case)
        if result is None:
            raise Refused(404, "no such run or case; run the battery first")
        return result, self.server.ran_on.get(run)

    def keep(self, key, results):
        """Hold results for /api/case under (a variant's hash or BOARD, the
        arrangement's name): a run on one arrangement never stands in for a
        run on another. Kept by case, so a table from an earlier run of other
        classes still opens; the newest key is last and the oldest goes when
        there are too many."""
        kept = self.server.runs.pop(key, {})
        kept.update((r["case"], r) for r in results)
        self.server.runs[key] = kept
        while len(self.server.runs) > MAX_RUNS:
            del self.server.runs[next(iter(self.server.runs))]
        return kept

    # --- API -----------------------------------------------------------------------
    def api_get_info(self, query, body):
        return info(self.server.trees)

    def api_post_run(self, query, body):
        """The battery on an arrangement: {"variant", "baseline", "classes",
        "arrangement": name, "without": [wires]}. With "without", on the
        arrangement with those wires taken away as well; the answer's
        arrangement then carries "json", the text of a file for it."""
        case_list = self.cases_of(body)
        if "variant" not in body:
            raise Refused(400, "no variant")
        a = self.arrangement_of(body.get("arrangement"))
        gone = body.get("without") or []
        if not isinstance(gone, list) or not all(isinstance(w, str) for w in gone):
            raise Refused(400, '"without" is a list of wire names')
        if gone:
            try:
                a = rank.without(a, *gone)
            except ValueError as e:
                raise Refused(400, str(e)) from None
        try:
            v, results = self.battery_of(body["variant"], case_list, a)
        except variants.BuildError as e:
            return {"build_error": e.stderr, "which": "variant", "variant": {"name": e.variant.name}}
        base_v = base = None
        if body.get("baseline"):
            try:
                base_v, base = self.battery_of(body["baseline"], case_list, a)
            except variants.BuildError as e:
                return {"build_error": e.stderr, "which": "baseline", "variant": {"name": e.variant.name}}
        return run_answer(v, results, base_v, base, a)

    def api_post_route(self, query, body):
        """A netlist made by hand on the page ({"variant", "arrangement",
        "bridges": [[node, node], ...]}), as the case DRAWN, routed on the
        arrangement named. The firmware's router routes it when it can run
        that arrangement. When it cannot, the harness makes the netlist on
        V5's copper with the arrangement's feed (the bridges the firmware
        allows, and their nets), and the page asks the solver for the routing
        (/api/ceiling with this run and the arrangement). The answer is
        /api/run's, with "drawn" and the arrangement the harness ran on."""
        bridges = body.get("bridges")
        if not isinstance(bridges, list) or not bridges:
            raise Refused(400, "send the bridges to route: [[node, node], ...], one at least")
        if len(bridges) > MAX_DRAWN:
            raise Refused(400, "a netlist made by hand holds %d bridges at most" % MAX_DRAWN)
        for b in bridges:
            if not (isinstance(b, list) and len(b) == 2 and all(type(n) is int for n in b) and b[0] != b[1]):
                raise Refused(400, "a bridge is two different nodes, by number: %s is not" % json.dumps(b)[:60])
            for n in b:                             # the firmware makes the netlist, and it knows only V5's nodes
                if n not in arrangement.V5.NODE_NET:
                    raise Refused(400, "node %d is not a node of V5, and the firmware, which makes the netlist, knows no other" % n)
        if "variant" not in body:
            raise Refused(400, "no variant")
        a = self.arrangement_of(body.get("arrangement"))
        on = a if arrangement.blocks(a) is not None else arrangement.base(a.feed)
        case = cases.Case(DRAWN, DRAWN, [(n1, n2, -1) for n1, n2 in bridges], notes="made by hand on the page")
        src = body.get("from")
        if src is not None:                         # added to a case: routed with that case's stacking, power and probe
            if not (isinstance(src, dict) and isinstance(src.get("cls"), str) and isinstance(src.get("case"), str)):
                raise Refused(400, '"from" is {"cls", "case"}: the case whose bridges these were added to')
            try:
                found = [c for c in lab.battery([src["cls"]]) if c.name == src["case"]]
            except (ValueError, TypeError) as e:
                raise Refused(400, str(e)) from None
            if not found:
                raise Refused(400, "there is no case %s in the class %s" % (src["case"], src["cls"]))
            own = {frozenset(b[:2]): b[2] for b in found[0].bridges}      # a bridge of its own keeps its own stacking
            place = {}                                                    # and its place: the firmware routes in order
            for i, b in enumerate(found[0].bridges):
                place.setdefault(frozenset(b[:2]), i)
            bridges = sorted(bridges, key=lambda p: place.get(frozenset(p), len(found[0].bridges)))   # added ones after, as sent
            case = dataclasses.replace(
                found[0], name=DRAWN, cls=DRAWN, must_route=False, taps_required=False,
                bridges=[(n1, n2, own.get(frozenset((n1, n2)), -1)) for n1, n2 in bridges],
                notes="made by hand on the page from %s: its bridges and settings, with bridges added or taken out" % src["case"])
        try:
            v, results = self.battery_of(body["variant"], [case], on)
        except variants.BuildError as e:
            return {"build_error": e.stderr, "which": "variant", "variant": {"name": e.variant.name}}
        return dict(run_answer(v, results, a=on), drawn=True)

    def api_get_case(self, query, body):
        result, a = self.kept(query.get("variant"), query.get("arrangement", "v5"), query.get("case"))
        return {"result": result, "paint": ceiling.painted(result, a)}      # the searches, on the copper the run was on

    def api_get_fabric(self, query, body):
        """The drawing of an arrangement's copper, and its nodes."""
        a = self.arrangement_of(query.get("arrangement"))
        return {"fabric": fabric_view.layout(a), "nodes": nodes_of(a), "arrangement": arrangement_row(a)}

    def api_post_board(self, query, body):
        """What a board printed for `b` (see board.py), judged and kept as a
        case of the run named BOARD, so the page shows it as it shows any run."""
        name, text = body.get("name", ""), body.get("text")
        if not isinstance(name, str) or not isinstance(text, str):
            raise Refused(400, "send {name, text}, the text being what a board prints for its b report")
        try:
            result = board.result(name, text)
        except ValueError as e:
            raise Refused(400, str(e)) from None
        kept = self.keep((BOARD, "v5"), [result])
        return {"variant": {"name": "board output", "hash": BOARD}, "baseline": None, "regressions": [],
                "arrangement": arrangement_row(arrangement.V5),
                "rows": [row(r) for r in kept.values()], "board": True, "shown": result["case"]}

    def api_post_ceiling(self, query, body):
        """The exact solver's verdict on one case of a run (of "variant", on
        the arrangement "run"), asked on the copper of "arrangement" (the
        run's own when none is named). The answer carries the solver's routing
        twice: "paint", the part the page lays over the router's, and
        "solved", a whole paint on the arrangement's wires to draw by itself.
        The netlist is the run's, so the two must agree on the probe feed."""
        run = body.get("run", "v5")
        result, a = self.kept(body.get("variant"), run, body.get("case"))
        if body.get("arrangement", run) != run:
            a = self.arrangement_of(body["arrangement"])
            fed = bool(result.get("feed", True))
            if fed != a.feed:
                raise Refused(409, "this run has the probe feed %s the fabric and %s has it %s: run the classes on an "
                              "arrangement with the same feed first" % ("on" if fed else "off", a.name, "on" if a.feed else "off"))
        if body.get("rule") not in ("firmware", "copper"):
            raise Refused(400, "the rule is firmware or copper")
        try:
            seconds = min(120.0, max(1.0, float(body.get("seconds", 20))))      # one request holds one thread this long
        except (TypeError, ValueError):
            raise Refused(400, "seconds is a number") from None
        if not ceiling.solver_installed():
            raise Refused(409, "the solver is not installed", hint=ceiling.SETUP)
        try:
            answer = ceiling.verdict(result, body["rule"], seconds, arrangement=a)
        except ceiling.SolverMissing as e:
            raise Refused(409, str(e), hint=ceiling.SETUP) from None
        return dict(answer, paint=solver_paint(answer["closed"], a), solved=ceiling.solved(result, answer, a))

    def api_get_rank(self, query, body):
        """The ranking on file for a variant (its spec) and an arrangement, with
        when it was made, and "stale" when it is of other copper than the
        arrangement's file now has (the file was edited since)."""
        v = self.resolve(query.get("variant", "worktree"))
        a = self.arrangement_of(query.get("arrangement"))
        where = rank.path(v.hash, a.name)
        if not where.is_file():
            raise Refused(404, "this router has not been ranked on this arrangement", hint=RANK_HINT)
        doc = json.loads(where.read_text())
        wires = {w["wire"]: [list(p) for p in w["pins"]] for w in rank.wires(a)}
        return dict(doc, made=time.strftime("%Y-%m-%d %H:%M", time.localtime(where.stat().st_mtime)),
                    stale=not rank.same_copper(doc, rank.fabric_of(a), a.feed, wires, rank.nodes_as_v5(a)))

    def api_post_rank(self, query, body):
        """Make the router's part of a ranking now ({"variant", "arrangement",
        "classes"}): the battery without each wire in turn, minutes of every
        core, so one at a time. GET /api/job says how far it is. The solver's
        part can take hours and is made from the command line (RANK_HINT);
        what it proved before is kept (rank.save)."""
        case_list = self.cases_of(body)
        a = self.arrangement_of(body.get("arrangement"))
        v = self.resolve(body.get("variant", "worktree"))
        try:
            runner.taken_pins(a)
        except arrangement.RouterCannot as e:
            raise Refused(400, str(e)) from None
        if not self.server.ranking.acquire(blocking=False):
            raise Refused(409, "a ranking is being made; wait for it")

        def progress(done, of, wire):
            self.server.job = {"what": "ranking", "done": done, "of": of, "wire": wire}

        try:
            self.server.job = dict(IDLE, what="ranking")
            written = rank.save(rank.removal(v, case_list, a, progress=progress))
        except arrangement.RouterCannot as e:
            raise Refused(400, str(e)) from None
        except variants.BuildError as e:
            return {"build_error": e.stderr, "which": "variant", "variant": {"name": v.name}}
        finally:
            self.server.job = IDLE
            self.server.ranking.release()
        return dict(written, made=time.strftime("%Y-%m-%d %H:%M"))

    def api_get_job(self, query, body):
        return self.server.job

    def api_get_watch(self, query, body):
        return {"hash": self.resolve(query.get("spec", "worktree")).hash}

    def api_get_paths(self, query, body):
        """Where a dropped file belongs: the tracked files under src/ with that file name."""
        name = query.get("name", "")
        if not name or "/" in name or "\\" in name:
            return {"paths": []}
        listed = subprocess.run(["git", "-C", str(variants.REPO), "ls-files", "src"],
                                capture_output=True, text=True).stdout.splitlines()
        return {"paths": [p for p in listed if p.rsplit("/", 1)[-1] == name]}

    def api_get_sheet(self, query, body):
        overlay = SHEET_DIR / "overlay.json"
        if not overlay.is_file():
            raise Refused(404, "the KiCad sheet has not been built", hint="python3 tools/routing_lab/lab.py sheet")
        return json.loads(overlay.read_text())


def info(trees=()):
    """What the page needs before any run. Also what an exported page carries."""
    named = [{"spec": t, "name": os.path.basename(t)} for t in trees]
    return {"classes": lab.CLASSES, "variants": [{"spec": "worktree", "name": "worktree"}] + named,
            "verified": lab.verified_against_a_board(), "ohms": lab.OHMS, "about": lab.about(),
            "fabric": fabric_view.layout(), "nodes": nodes_of(arrangement.V5), "arrangements": arrangements(),
            "sheet": (SHEET_DIR / "overlay.json").is_file(), "solver": ceiling.solver_installed()}


def nodes_of(a):
    """{node number: {"wire", "name"}} for every node an arrangement has."""
    return {str(n): {"wire": wire, "name": a.NODE_NAME.get(n, str(n))} for n, wire in a.NODE_NET.items()}


def arrangement_row(a):
    """An arrangement as the page names it: its feed, who can answer for it
    ("router": the firmware's router and the solver; "solver": the solver
    only), and why the router cannot when it cannot."""
    why = arrangement.why_not_router(a)
    row = {"name": a.name, "about": a.about, "feed": a.feed, "engine": "solver" if why else "router", "why": why}
    if a.name not in arrangement.names():           # no file holds it (say "x without KL"): here is the text of one
        row["json"] = json.dumps(a.data, indent=1)
    return row


def arrangements():
    """Every arrangement there is to pick. A file with a mistake in it is
    listed with its problems and no engine, and stops nothing else."""
    out = []
    for name in arrangement.names():
        try:
            out.append(arrangement_row(arrangement.load(name)))
        except arrangement.Bad as e:
            out.append({"name": name, "problems": e.problems})
    return out


def solver_paint(closed, a=None):
    """A solver's routing ([[chip, x, y, net]]) on an arrangement's copper
    (V5's when None) as the part of a paint the page compares against: its
    crosspoints, and the nets on every wire they touch."""
    ends = (ceiling.graph(a) if a is not None else ceiling.graph()).ends
    wires = {}
    for chip, x, y, net in closed:
        for name in ends[chip, x, y]:
            nets = wires.setdefault(name, {"nets": []})["nets"]
            if net not in nets:
                nets.append(net)
    return {"crosspoints": [{"chip": chip, "x": x, "y": y, "net": net} for chip, x, y, net in closed], "wires": wires}


def run_answer(v, results, base_v=None, base=None, a=None):
    """The table of one battery run on an arrangement (V5 when None), against
    a baseline's run of the same cases on the same arrangement if there is one."""
    before = {r["case"]: r for r in base or []}
    return {"variant": {"name": v.name, "hash": v.hash}, "arrangement": arrangement_row(a or arrangement.V5),
            "baseline": {"name": base_v.name, "hash": base_v.hash} if base_v else None,
            "rows": [row(r, before.get(r["case"])) for r in results],
            "regressions": lab.regressions(base, results) if base else []}


def row(result, base=None):
    """A result without its report text, for the table."""
    out = {k: v for k, v in result.items() if k not in ("b", "xbar", "stderr")}
    out["fully_routed"] = lab.fully_routed(result)
    if base is not None:
        out["base"] = {"status": base["status"], "metrics": base["metrics"], "problems": base["problems"],
                       "fully_routed": lab.fully_routed(base)}
    return out
