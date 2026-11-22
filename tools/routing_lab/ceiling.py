# SPDX-License-Identifier: MIT
"""Ceilings: how far a routing is from what the copper allows.

The copper is a graph: wires joined by crosspoints, as the checker's fabric
tables give it. Over one painted result, `missed` finds for each bridge the
router failed the cheapest path the free copper still had.

The rule is the checker's: a wire carries one net, and a node outside the net
(in another net, or in no net) may not be touched.
"""
import collections
import heapq

import copper                                       # puts test/hil on the path

import fabric_v5                                    # noqa: E402

Graph = collections.namedtuple("Graph", "edges owners")
FAILED = ("unrouted", "broken")                     # the router's own misses; the firmware's three "no"s are not
_BOARD = []                                         # the V5 fabric's graph, built once


def graph(fabric=fabric_v5):
    """The copper of a fabric (anything with CHIPS, X_NET, Y_NET, NODE_NET).
    edges[wire] is [(other wire, (chip, x, y))], one for every crosspoint on
    the wire; owners[wire] is the nodes whose copper the wire is."""
    if fabric is fabric_v5 and _BOARD:
        return _BOARD[0]
    edges, owners = {}, {}
    for chip in fabric.CHIPS:
        for x, wx in enumerate(fabric.X_NET[chip]):
            for y, wy in enumerate(fabric.Y_NET[chip]):
                edges.setdefault(wx, []).append((wy, (chip, x, y)))
                edges.setdefault(wy, []).append((wx, (chip, x, y)))
    for node, wire in fabric.NODE_NET.items():
        owners.setdefault(wire, []).append(node)
    g = Graph(edges, owners)
    if fabric is fabric_v5:
        _BOARD.append(g)
    return g


def _wire_of(g):
    return {node: wire for wire, nodes in g.owners.items() for node in nodes}


def _path(g, a, b, ok, closed=frozenset(), limit=None):
    """The cheapest way from wire a to wire b as [((chip, x, y), new)], or
    None. Fewest new crosspoints first, then fewest in all; a crosspoint in
    `closed` is not new. ok(wire) says whether a wire on the way may be
    passed. `limit` caps the crosspoints (exact only when none is closed)."""
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
            if other != b and not ok(other):
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
