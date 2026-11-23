# SPDX-License-Identifier: MIT
"""Paint: one routing result as copper.

Which net is on which wire and crosspoint, what the chip status claims at
every pin, and what each bridge ended up as: routed (with its copies and its
resistance), unrouted, or one of the three ways the firmware says no. The
page draws from this and nothing else.

Resistance is in units of one crosspoint: a direct two-crosspoint path is
2.0, two of them in parallel are 1.0. Wire copper counts as zero.
"""
import re
import statistics
from pathlib import Path

import variants                                                         # puts JumperlOS/test/hil on the path

HIL = variants.HIL

import routing_check as rc                                              # noqa: E402
from fabric_v5 import BOUNCE, CHIPS, LANES, NODE_NAME, NODE_NET, X_NET, Y_NET      # noqa: E402

HUBS = {"IJ", "IK", "IL", "JK", "JL", "KL"}
RAIL_NODES = (100, 101, 102)                # GND, TOP_RAIL, BOTTOM_RAIL
FEED_NODE = 139                             # ROUTABLE_BUFFER_IN: the probe feed's end of an infra bridge
NET_LABEL = {v: k for k, v in rc.NET_TOKEN.items() if k != "E"}     # 1 -> "Gn", 2 -> "T", ...

# Ground and the two power rails wear the firmware's own colours, as the board's LEDs show them (LEDs.cpp,
# assignNetColors: railNetColors, and 0x03031e for a rail sitting negative), brightened for a screen: ground green,
# a rail red, a rail set negative blue. They are nets 1, 2 and 3.
GND_COLOUR, RAIL_COLOUR, RAIL_NEGATIVE_COLOUR = "#00ff44", "#ff2222", "#5f5fff"

# Sixteen colours for every other net, that stay apart on a dark ground. None is red: on a wire red is a rail's
# colour, and a problem's red is drawn with a white edge (lab.css).
NET_COLOURS = ["#4fc3f7", "#aed581", "#ffb74d", "#ba68c8", "#4db6ac", "#fff176", "#7986cb", "#f48fb1",
               "#81d4fa", "#c5e1a5", "#ffcc80", "#ce93d8", "#80cbc4", "#e6ee9c", "#9fa8da", "#bcaaa4"]


def net_colour(net, power=None):
    """A net's colour. `power` is the case's (top rail, bottom rail, ...) in volts; without it a rail is taken as
    positive."""
    if net == 1:
        return GND_COLOUR
    if net in (2, 3):
        return RAIL_NEGATIVE_COLOUR if power and power[net - 2] < -0.1 else RAIL_COLOUR
    return NET_COLOURS[net % len(NET_COLOURS)]


def wire(chip, axis, pin):
    """The fabric's name for the copper on one chip pin."""
    return (X_NET if axis == "X" else Y_NET)[chip][pin]


def wire_kind(name):
    if name in BOUNCE:
        return "bounce"
    if name in HUBS:
        return "hub"
    if name in LANES:
        return "lane"
    if name.isdigit():
        return "row"
    return "special"


def effective_resistance(edges, a, b):
    """Resistance between wires a and b when every edge is one crosspoint
    (1.0) joining two wires. None when they are not connected."""
    if a == b:
        return 0.0
    neighbours = {}
    for u, v in edges:
        if u != v:
            neighbours.setdefault(u, []).append(v)
            neighbours.setdefault(v, []).append(u)
    seen, stack = {a}, [a]
    while stack:
        for n in neighbours.get(stack.pop(), ()):
            if n not in seen:
                seen.add(n)
                stack.append(n)
    if b not in seen:
        return None
    # Node voltages with b grounded and one unit of current into a: L v = i.
    nodes = [n for n in seen if n != b]
    index = {n: i for i, n in enumerate(nodes)}
    size = len(nodes)
    m = [[0.0] * (size + 1) for _ in range(size)]
    for n in nodes:
        i = index[n]
        for other in neighbours[n]:
            m[i][i] += 1.0
            if other != b:
                m[i][index[other]] -= 1.0
    m[index[a]][size] = 1.0
    for col in range(size):                         # Gaussian elimination, partial pivoting
        pivot = max(range(col, size), key=lambda r: abs(m[r][col]))
        m[col], m[pivot] = m[pivot], m[col]
        for r in range(col + 1, size):
            f = m[r][col] / m[col][col]
            if f:
                for c in range(col, size + 1):
                    m[r][c] -= f * m[col][c]
    v = [0.0] * size
    for r in range(size - 1, -1, -1):
        v[r] = (m[r][size] - sum(m[r][c] * v[c] for c in range(r + 1, size))) / m[r][r]
    return round(v[index[a]], 6)


def _pin_mark(w, claim, closed_here, strict):
    """How a pin's claim sits with the copper, by the checker's own rules.
    "mismatch": the wire carries one net and this pin is claimed for another
    (WRONG CLAIM), or is free although a crosspoint is closed on it
    (UNCLAIMED X/Y), or is the free far end of a lane a net rides (UNCLAIMED
    WIRE: another net could close onto it). "held": claimed, but no net rides
    the wire (a reservation, a culled duplicate's leftover, a blocked pin);
    where the checker counts that as a problem (strict), it is a mismatch."""
    riding = w["nets"]
    if len(riding) == 1:
        if claim is not None:
            return None if claim == riding[0] else "mismatch"
        return "mismatch" if closed_here or w["kind"] in ("lane", "hub", "bounce") else None
    if not riding and claim is not None:
        return "mismatch" if strict else "held"
    return None


def _empty(result):
    return {"nets": {}, "crosspoints": [], "wires": {}, "bridges": [], "problems": list(result.get("problems", [])),
            "notes": list(result.get("notes", [])), "status": result.get("status"), "stderr": result.get("stderr", "")}


def paint(result):
    """The copper of one result. See the module docstring."""
    if result.get("status") in ("crash", "timeout", "empty") or not result.get("b"):
        return _empty(result)
    b = result["b"]
    rows = [r for r in rc.parse_paths(b) if r["net"] >= 0]
    status = rc.parse_chip_status(b)

    # closed crosspoints, one entry per (place, net); a primary's entry wins over a duplicate's
    closed = {}
    for r in rows:
        for chip, x, y in rc.routed_hops(r):
            key = (chip, x, y, r["net"])
            if key not in closed or (closed[key]["dup"] and not r["dup"]):
                closed[key] = {"chip": chip, "x": x, "y": y, "net": r["net"], "path": r["path"], "dup": r["dup"]}
    crosspoints = [closed[k] for k in sorted(closed)]

    riding = {}                                     # wire -> the nets that close a crosspoint on it
    edges = {}                                      # net -> [(x wire, y wire)]
    for c in crosspoints:
        wx, wy = wire(c["chip"], "X", c["x"]), wire(c["chip"], "Y", c["y"])
        for w in (wx, wy):
            riding.setdefault(w, set()).add(c["net"])
        edges.setdefault(c["net"], []).append((wx, wy))

    array = rc.parse_bridge_array(b)                # the bridges the firmware put in a net
    node_net = {n: net for n1, n2, net in array for n in (n1, n2)}
    owners = {}                                     # wire -> the nodes that are this wire
    for node, name in NODE_NET.items():
        owners.setdefault(name, []).append(node)
    # the checker counts a claim with no copper as a problem only in strict cases, and then lists every one
    strict = any(p.startswith("CLAIM WITHOUT COPPER") for p in result.get("problems", ()))

    closed_pins = {(c["chip"], "X", c["x"]) for c in crosspoints} | {(c["chip"], "Y", c["y"]) for c in crosspoints}
    wires = {}
    for chip in CHIPS:
        xs, ys = status.get(chip, ([None] * 16, [None] * 8))
        for axis, claims in (("X", xs), ("Y", ys)):
            for pin, claim in enumerate(claims):
                name = wire(chip, axis, pin)
                if name not in wires:
                    # Where a net rides a node's wire, the node's own net is on it too (two nets: a short), and
                    # a node in no net is a stray: the checker's rules, so the drawing agrees with its verdict.
                    on, mine = set(riding.get(name, ())), owners.get(name, [])
                    stray = bool(on) and any(n not in node_net for n in mine)
                    if on:
                        on |= {node_net[n] for n in mine if n in node_net}
                    wires[name] = {"kind": wire_kind(name), "nets": sorted(on), "stray": stray, "pins": []}
                w = wires[name]
                w["pins"].append({"chip": chip, "axis": axis, "pin": pin, "claim": claim,
                                  "mark": _pin_mark(w, claim, (chip, axis, pin) in closed_pins, strict)})

    nets = {}
    for n1, n2, net in array:
        entry = nets.setdefault(str(net), {"label": NET_LABEL.get(net, str(net)),
                                           "colour": net_colour(net, result.get("power")), "nodes": []})
        for node in (n1, n2):
            if node not in entry["nodes"]:
                entry["nodes"].append(node)

    refused = {frozenset(pair) for pair in result.get("refused", [])}
    bridges = []
    for n1, n2, net in array:
        mine = [r for r in rows if {r["node1"], r["node2"]} == {n1, n2}]
        primary = next((r for r in mine if not r["dup"]), None)
        routed = primary is not None and rc.path_is_routed(primary)
        state = "routed" if routed else ("refused" if frozenset((n1, n2)) in refused else "unrouted")
        r = None
        if routed and n1 in NODE_NET and n2 in NODE_NET:
            r = effective_resistance(edges.get(net, []), NODE_NET[n1], NODE_NET[n2])
            if r is None:
                state = "broken"                    # the path table lists it; its copper does not join the two nodes
        bridges.append({"n1": n1, "n2": n2, "net": net, "state": state,
                        "copies": sum(1 for x in mine if rc.path_is_routed(x)) if routed else 0,
                        "hops": len(rc.routed_hops(primary)) if routed else 0,
                        "r": r, "infra": FEED_NODE in (n1, n2)})
    for kind in ("left_out", "rejected"):
        for n1, n2 in result.get(kind, []):
            bridges.append({"n1": n1, "n2": n2, "net": None, "state": kind, "copies": 0, "hops": 0, "r": None,
                            "infra": False})

    return {"nets": nets, "crosspoints": crosspoints, "wires": wires, "bridges": bridges,
            "problems": list(result["problems"]), "notes": list(result["notes"]), "status": result["status"],
            "stderr": result.get("stderr", "")}


def resistance_metrics(result):
    """worst_r, median_r over the routed signal bridges, rail_worst_r over
    those with GND or a rail at one end (reported apart: stacking makes them
    the best bridges of a case), and broken: bridges listed as routed whose
    copper does not join. None where there is no such bridge. The probe feed
    is not a user bridge."""
    bridges = [b for b in paint(result)["bridges"] if not b["infra"]]
    routed = [b for b in bridges if b["state"] == "routed" and b["r"] is not None]
    on_rail = lambda b: b["n1"] in RAIL_NODES or b["n2"] in RAIL_NODES
    rs = [b["r"] for b in routed if not on_rail(b)]
    rails = [b["r"] for b in routed if on_rail(b)]
    return {"worst_r": max(rs) if rs else None,
            "median_r": round(statistics.median(rs), 6) if rs else None,
            "rail_worst_r": max(rails) if rails else None,
            "broken": [[b["n1"], b["n2"], b["net"]] for b in bridges if b["state"] == "broken"]}


def left_out_pairs(b):
    """Bridges the firmware kept out of every net ("Net ?" in the Bridge Array)."""
    return [[rc.node_of_name(a), rc.node_of_name(c)] for a, c in re.findall(r"\[([^,\]]+),([^,\]]+),Net \?\]", b)]
