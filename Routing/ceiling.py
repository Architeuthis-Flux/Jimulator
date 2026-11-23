# SPDX-License-Identifier: MIT
"""Ceilings: how far a routing is from what the copper allows.

The copper is a graph: wires joined by crosspoints, as the checker's fabric
tables give it. Over one painted result, `missed` finds for each bridge the
router failed the cheapest path the free copper still had.

The rule is the checker's: a wire carries one net, and a node outside the net
(in another net, or in no net) may not be touched.

The exact search (can this netlist be routed at all, and with how few
crosspoints) is solver/solve.py, run with OR-tools from its own environment
under build/. `problem` is what it is given and `ask` runs it; the lab works
without it.
"""
import collections
import hashlib
import heapq
import json
import os
import subprocess
from pathlib import Path

import arrangement
import copper                                       # puts test/hil on the path
import variants

import fabric_v5                                    # noqa: E402

Graph = collections.namedtuple("Graph", "edges owners ends")
FAILED = ("unrouted", "broken")                     # the router's own misses; the firmware's three "no"s are not
ASKED = ("routed",) + FAILED                        # the bridges a solver is given: all the firmware allowed
_BOARD = []                                         # the V5 fabric's graph, built once

ORTOOLS = "9.15.6755"
SOLVER_PYTHON = variants.BUILD_DIR / "solver-venv" / "bin" / "python"
SOLVE_PY = Path(__file__).resolve().parent / "solver" / "solve.py"
SETUP = "python3 Routing/lab.py solver-setup"
GRACE = 30.0                                        # seconds past its limit before the solver is given up on


class SolverMissing(ValueError):
    """The solver's environment is not there; the text ends with the command that makes it."""


def graph(fabric=fabric_v5):
    """The copper of a fabric: the V5 model, an arrangement, or anything else
    with CHIPS, X_NET, Y_NET and NODE_NET. edges[wire] is [(other wire, (chip,
    x, y))], one for every crosspoint on the wire; owners[wire] is the nodes
    whose copper the wire is; ends[(chip, x, y)] is that crosspoint's (X wire,
    Y wire). A pin with no wire (None: taken away) is no copper: it has no
    crosspoints at all."""
    board = fabric is fabric_v5 or fabric is arrangement.V5     # the same copper
    if board and _BOARD:
        return _BOARD[0]
    edges, owners, ends = {}, {}, {}
    for chip in fabric.CHIPS:
        for x, wx in enumerate(fabric.X_NET[chip]):
            for y, wy in enumerate(fabric.Y_NET[chip]):
                if wx is None or wy is None:
                    continue
                edges.setdefault(wx, []).append((wy, (chip, x, y)))
                edges.setdefault(wy, []).append((wx, (chip, x, y)))
                ends[(chip, x, y)] = (wx, wy)
    for node, wire in fabric.NODE_NET.items():
        owners.setdefault(wire, []).append(node)
    g = Graph(edges, owners, ends)
    if board:
        _BOARD.append(g)
    return g


def _wire_of(g):
    return {node: wire for wire, nodes in g.owners.items() for node in nodes}


def _path(g, a, b, ok, closed=frozenset(), limit=None, skip=frozenset()):
    """The cheapest way from wire a to wire b as [((chip, x, y), new)], or
    None. Fewest new crosspoints first, then fewest in all; a crosspoint in
    `closed` is not new. ok(wire) says whether a wire on the way may be
    passed. `limit` caps the crosspoints (exact only when none is closed);
    a crosspoint in `skip` is never used."""
    if a == b:
        return []
    best, back, heap = {a: (0, 0)}, {}, [(0, 0, a)]
    while heap:
        new, hops, w = heapq.heappop(heap)
        if (new, hops) > best[w]:
            continue
        if w == b:
            break
        if hops == limit:
            continue
        for other, xp in g.edges.get(w, ()):
            if xp in skip or (other != b and not ok(other)):
                continue
            cost = (new + (xp not in closed), hops + 1)
            if other not in best or cost < best[other]:
                best[other], back[other] = cost, (w, xp)
                heapq.heappush(heap, cost + (other,))
    if b not in back:
        return None
    path, w = [], b
    while w != a:
        w, xp = back[w]
        path.append((xp, xp not in closed))
    return path[::-1]


def missed(paint, g=None):
    """For every bridge the router failed (the probe feed included), the
    cheapest path the copper had with everything else where it is: a list of
    {n1, n2, net, infra, path, new, hops}. path is [{chip, x, y, new}] from
    n1's wire to n2's, or None when there is none; new counts the crosspoints
    that would have to be closed, hops all of them."""
    g = g or graph()
    wire_of = _wire_of(g)
    out = []
    for b in paint["bridges"]:
        if b["state"] not in FAILED:
            continue
        net = b["net"]
        mine = set(paint["nets"].get(str(net), {}).get("nodes", ()))
        closed = {(c["chip"], c["x"], c["y"]) for c in paint["crosspoints"] if c["net"] == net}

        def ok(wire):
            riding = paint["wires"].get(wire, {}).get("nets", [])
            nodes = g.owners.get(wire, [])
            return all(n in mine for n in nodes) and (riding == [net] or not riding)

        found = None
        if b["n1"] in wire_of and b["n2"] in wire_of:
            found = _path(g, wire_of[b["n1"]], wire_of[b["n2"]], ok, closed)
        path = None if found is None else [{"chip": c, "x": x, "y": y, "new": new} for (c, x, y), new in found]
        out.append({"n1": b["n1"], "n2": b["n2"], "net": net, "infra": b["infra"], "path": path,
                    "new": sum(h["new"] for h in path or ()), "hops": len(path or ())})
    return out


def spare(paint, g=None, limit=8):
    """For every routed bridge but the probe feed, the copies the free copper
    still allows: {n1, n2, net, copies, r, paths}. A copy is at most four new
    crosspoints through wires that carry no net and are no node's copper;
    copies of one bridge share no wire. Found shortest first, up to `limit`.
    r is the bridge's resistance with all of them closed (None with none).

    Each bridge is taken alone, as if all the free copper were its own, and
    the firmware holds some copper back for sense taps: this is what is
    available in copper, not what the firmware would give."""
    g = g or graph()
    wire_of, ends = _wire_of(g), g.ends
    taken = {(c["chip"], c["x"], c["y"]) for c in paint["crosspoints"]}
    out = []
    for b in paint["bridges"]:
        if b["state"] != "routed" or b["infra"] or b["n1"] not in wire_of or b["n2"] not in wire_of:
            continue
        a, z = wire_of[b["n1"]], wire_of[b["n2"]]
        used, paths = set(), []                     # wires and crosspoints the copies found so far hold
        free = lambda w: not g.owners.get(w) and not paint["wires"].get(w, {}).get("nets") and w not in used
        while len(paths) < limit:
            found = _path(g, a, z, free, limit=4, skip=taken | used)
            if not found:
                break
            paths.append([xp for xp, _ in found])
            for xp in paths[-1]:
                used |= {xp} | (set(ends[xp]) - {a, z})
        r = None
        if paths:
            edges = [ends[(c["chip"], c["x"], c["y"])] for c in paint["crosspoints"] if c["net"] == b["net"]]
            r = copper.effective_resistance(edges + [ends[xp] for path in paths for xp in path], a, z)
        out.append({"n1": b["n1"], "n2": b["n2"], "net": b["net"], "copies": len(paths), "r": r,
                    "paths": [[{"chip": c, "x": x, "y": y} for c, x, y in path] for path in paths]})
    return out


def painted(result, arrangement=None):
    """copper.paint(result) with both searches in it: paint["missed"], and on
    every bridge "spare" (the count), "r_spare" and "spare_paths". The
    searches are made on the arrangement's copper (V5's when None)."""
    g = graph(arrangement) if arrangement is not None else graph()
    paint = copper.paint(result)
    paint["missed"] = missed(paint, g)
    found = {(s["n1"], s["n2"], s["net"]): s for s in spare(paint, g)}
    for b in paint["bridges"]:
        s = found.get((b["n1"], b["n2"], b["net"]), {})
        b["spare"], b["r_spare"], b["spare_paths"] = s.get("copies", 0), s.get("r"), s.get("paths", [])
    return paint


# ---------------------------------------------------------------- the exact search

def solver_installed():
    """True when the solver's environment is there with OR-tools in it. A
    setup that could not reach the network leaves a python and nothing to
    import; that is not installed."""
    return SOLVER_PYTHON.exists() and any((SOLVER_PYTHON.parent.parent / "lib").glob("python*/site-packages/ortools"))


def problem(paint, g=None):
    """What a solver is given for one painted result, or None when there is
    nothing to route: {"bridges": [[wire a, wire b, net]], "terminals":
    {wire: net}, "crosspoints": [[chip, x, y, X wire, Y wire]], "unplaced":
    [[node, node]]}.

    The bridges are the ones the firmware allowed, the probe feed among them.
    A wire is offered when it is a terminal or no node's copper, so a node in
    no net (or in a net by a bridge the firmware refused) is never touched; a
    crosspoint is offered when both its wires are and it does not join the
    terminals of two nets. Two nodes on one piece of copper need nothing
    closed: their wire stays a terminal and the bridge is left out.

    "unplaced" is the allowed bridges with a node this copper does not have
    (an arrangement may have dropped it). They are not in "bridges": a
    netlist with any of them cannot be placed, which is neither routable nor
    not, and whoever asks must say so."""
    g = g or graph()
    wire_of = _wire_of(g)
    bridges, terminals, unplaced = [], {}, []
    for b in paint["bridges"]:
        if b["state"] not in ASKED:
            continue
        if b["n1"] not in wire_of or b["n2"] not in wire_of:
            unplaced.append([b["n1"], b["n2"]])
            continue
        a, z = wire_of[b["n1"]], wire_of[b["n2"]]
        terminals.setdefault(a, b["net"])
        terminals.setdefault(z, b["net"])
        if a != z:
            bridges.append([a, z, b["net"]])
    if not bridges and not unplaced:
        return None
    offered = lambda w: w in terminals or not g.owners.get(w)
    apart = lambda a, z: a in terminals and z in terminals and terminals[a] != terminals[z]
    return {"bridges": bridges, "terminals": terminals, "unplaced": unplaced,
            "crosspoints": [[chip, x, y, wx, wy] for (chip, x, y), (wx, wy) in g.ends.items()
                            if offered(wx) and offered(wy) and not apart(wx, wy)]}


def ask(problem, rule, seconds=20.0, fewest=True):
    """The solver's answer to one problem under one rule ("copper": any
    copper; "firmware": each bridge its own path of at most four crosspoints):
    {"verdict": "routable" | "not_routable" | "unknown", "fewest_proved",
    "closed": [[chip, x, y, net]], "seconds"}. With fewest false it stops at
    the first routing found. Raises SolverMissing when the environment is not
    there; a solver that dies, prints something else or outlives its limit by
    GRACE is "unknown" with an "error", never "not routable"."""
    if not solver_installed():
        raise SolverMissing("the exact search needs OR-tools in an environment of its own; make it once with: " + SETUP)
    question = json.dumps(dict(problem, rule=rule, seconds=seconds, fewest=fewest))
    unknown = lambda why: {"verdict": "unknown", "fewest_proved": False, "closed": [], "seconds": seconds, "error": why}
    try:
        p = subprocess.run([str(SOLVER_PYTHON), str(SOLVE_PY)], input=question, capture_output=True, text=True,
                           errors="replace", timeout=seconds + GRACE)
    except subprocess.TimeoutExpired:
        return unknown("the solver gave no answer in %g s" % (seconds + GRACE))
    except OSError as e:
        return unknown("the solver could not be started: %s" % e)
    if p.returncode != 0:
        return unknown("the solver exited with %d: %s" % (p.returncode, (p.stderr.strip().splitlines() or [""])[-1]))
    try:
        answer = json.loads(p.stdout)
        if answer["verdict"] not in ("routable", "not_routable", "unknown"):
            raise ValueError(answer["verdict"])
        # a routing is a list of [chip, x, y, net]; anything else is not an answer
        if not all(isinstance(c, list) and len(c) == 4 and isinstance(c[0], str) and isinstance(c[1], int)
                   and isinstance(c[2], int) for c in answer.setdefault("closed", [])):
            raise ValueError("closed")
    except (ValueError, KeyError, TypeError):
        return unknown("the solver's answer cannot be read: %r" % p.stdout[:200])
    return answer


def faults(problem, closed, rule):
    """What is wrong with a routing of `problem` by the lab's own copper
    model; empty when it holds. The closed crosspoints are read as copper and
    the net each is tagged with is ignored: a crosspoint that was not offered
    (which is what keeps a node in no net untouched), a piece of joined copper
    holding the terminals of two nets, a bridge whose two wires are not
    joined, and under "firmware" one whose wires are more than four
    crosspoints apart."""
    offered = {(c[0], c[1], c[2]): (c[3], c[4]) for c in problem["crosspoints"]}
    out, joined = [], {}
    for chip, x, y in sorted({(c[0], c[1], c[2]) for c in closed}):
        if (chip, x, y) not in offered:
            out.append("crosspoint %s x%s y%s is not one the problem offers" % (chip, x, y))
            continue
        wa, wb = offered[chip, x, y]
        joined.setdefault(wa, set()).add(wb)
        joined.setdefault(wb, set()).add(wa)

    def reach(start):                               # wire -> crosspoints from start
        far, queue = {start: 0}, collections.deque([start])
        while queue:
            w = queue.popleft()
            for other in joined.get(w, ()):
                if other not in far:
                    far[other] = far[w] + 1
                    queue.append(other)
        return far

    terminals, seen = problem["terminals"], set()
    for w in sorted(terminals):
        if w not in seen:
            piece = reach(w)
            seen |= set(piece)
            nets = sorted({terminals[p] for p in piece if p in terminals})
            if len(nets) > 1:
                out.append("one piece of copper (through %s) holds nets %s" % (w, " and ".join(str(n) for n in nets)))
    for a, b, net in problem["bridges"]:
        far = reach(a).get(b)
        if far is None:
            out.append("bridge %s-%s (net %s) is not joined" % (a, b, net))
        elif rule == "firmware" and far > 4:
            out.append("bridge %s-%s (net %s) is %d crosspoints end to end, over a firmware path's four" % (a, b, net, far))
    return out


def _cache_path(problem, rule, seconds, fewest):
    key = json.dumps([problem, rule, seconds, fewest], sort_keys=True).encode() + SOLVE_PY.read_bytes()
    return variants.BUILD_DIR / "ceiling" / (hashlib.sha256(key).hexdigest() + ".json")


def verdict(result, rule="firmware", seconds=20.0, use_cache=True, fewest=True, arrangement=None):
    """Can this result's netlist (the bridges the firmware allowed, as it
    built them) be routed at all under `rule`, on the arrangement's copper
    (V5's when None): {"verdict": "routable" | "not_routable" | "unknown" |
    "nothing" | "unplaced", "fewest_proved", "crosspoints",
    "router_crosspoints", "closed", "seconds", "error", "arrangement",
    "engine": "solver", "unplaced": [[node, node]]}.

    "nothing": no bridge to route. "unplaced": the netlist uses a node the
    arrangement does not have; nothing is asked. A routable answer is checked with `faults`
    and one that fails is "unknown" with the reason. So is a "not routable"
    when the router's own copper is a routing `faults` accepts: a routing
    exists, so the model is wrong. router_crosspoints counts the crosspoints
    of the router's primary paths. Answers are kept under build/ceiling, but
    never one that ends with an error. Raises SolverMissing when the solver
    has to be asked and is not there."""
    paint = copper.paint(result)
    out = {"verdict": "nothing", "fewest_proved": False, "crosspoints": None, "closed": [], "seconds": 0.0, "error": None,
           "router_crosspoints": sum(1 for c in paint["crosspoints"] if not c["dup"]),
           "arrangement": arrangement.name if arrangement is not None else "v5", "engine": "solver", "unplaced": []}
    if result.get("status") == "unplaced":          # the runner found a node missing and routed nothing: there is no netlist
        return dict(out, verdict="unplaced")
    given = problem(paint, graph(arrangement) if arrangement is not None else graph())
    if given is None:
        return out
    if given["unplaced"]:
        out.update(verdict="unplaced", unplaced=given["unplaced"])
        return out
    path = _cache_path(given, rule, seconds, fewest)
    kept = use_cache and path.exists()
    answer = json.loads(path.read_text()) if kept else ask(given, rule, seconds, fewest)
    out.update(verdict=answer["verdict"], fewest_proved=bool(answer.get("fewest_proved")),
               closed=answer.get("closed") or [], seconds=answer.get("seconds", 0.0), error=answer.get("error"))
    if out["verdict"] == "routable":
        wrong = faults(given, out["closed"], rule)
        if wrong:
            out.update(verdict="unknown", fewest_proved=False, closed=[],
                       error="the solver's answer fails the lab's own check: " + wrong[0])
        else:
            out["crosspoints"] = len(out["closed"])
    elif out["verdict"] == "not_routable" \
            and not faults(given, [[c["chip"], c["x"], c["y"], c["net"]] for c in paint["crosspoints"]], rule):
        out.update(verdict="unknown", error="the solver says this cannot be routed, yet the router routed it: the model is wrong")
    if use_cache and not kept and not out["error"]:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp%d" % os.getpid())
        tmp.write_text(json.dumps(answer))
        os.replace(tmp, path)
    return out


def solved(result, answer, arrangement=None):
    """A routable `verdict` answer as a paint of its own, on the arrangement's
    wires, for the page to draw as the picture: the solver's crosspoints, the
    nets they put on each wire, and every bridge it was given as routed, with
    its crosspoints end to end and its resistance in the solver's copper.
    None when the answer is not a routing. It is one routing of many, and not
    what the firmware's router did; its one note says so."""
    if answer.get("verdict") != "routable":
        return None
    fabric = arrangement if arrangement is not None else fabric_v5
    g = graph(fabric)
    wire_of = _wire_of(g)
    paint = copper.paint(result)
    riding, edges = {}, {}
    for chip, x, y, net in answer["closed"]:
        for w in g.ends[chip, x, y]:
            riding.setdefault(w, set()).add(net)
        edges.setdefault(net, []).append(g.ends[chip, x, y])

    def apart(net, a, z):                           # crosspoints from wire a to wire z in the net's copper
        far, queue = {a: 0}, collections.deque([a])
        while queue:
            w = queue.popleft()
            for u, v in edges.get(net, ()):
                other = v if u == w else u if v == w else None
                if other is not None and other not in far:
                    far[other] = far[w] + 1
                    queue.append(other)
        return far.get(z)

    wires = {}
    for chip in fabric.CHIPS:
        for axis, table in (("X", fabric.X_NET), ("Y", fabric.Y_NET)):
            for pin, name in enumerate(table[chip]):
                if name is not None:
                    w = wires.setdefault(name, {"kind": copper.wire_kind(name), "nets": sorted(riding.get(name, ())),
                                                "stray": False, "pins": []})
                    w["pins"].append({"chip": chip, "axis": axis, "pin": pin, "claim": None, "mark": None})
    bridges = []
    for b in paint["bridges"]:
        entry = dict(b, copies=0, hops=0, r=None, spare=0, r_spare=None, spare_paths=[])
        if b["state"] in ASKED:                     # the solver was given it, and its answer passed the lab's check
            a, z = wire_of[b["n1"]], wire_of[b["n2"]]
            entry.update(state="routed", copies=1, hops=apart(b["net"], a, z) or 0,
                         r=copper.effective_resistance(edges.get(b["net"], []), a, z))
        bridges.append(entry)
    return {"nets": paint["nets"], "wires": wires, "bridges": bridges, "missed": [],
            "crosspoints": [{"chip": chip, "x": x, "y": y, "net": net, "dup": False, "path": None}
                            for chip, x, y, net in answer["closed"]],
            "problems": [], "status": "ok", "stderr": "",
            "notes": ["the exact solver's routing on %s: one of many, and not what the firmware's router did"
                      % answer.get("arrangement", getattr(fabric, "name", "v5"))]}
