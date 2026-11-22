# SPDX-License-Identifier: MIT
"""Exact search over a crossbar fabric with CP-SAT.

Run with the Python that has OR-tools (lab.py solver-setup). One JSON problem
on stdin, one JSON answer on stdout. Knows nothing of the lab or of V5: wires
are names, a crosspoint joins two of them, a wire carries one net.

in:  {"bridges": [[wire a, wire b, net]], "terminals": {wire: net},
      "crosspoints": [[chip, x, y, wire, wire]],
      "rule": "copper" | "firmware", "seconds": limit, "fewest": true}
out: {"verdict": "routable" | "not_routable" | "unknown", "fewest_proved": bool,
      "closed": [[chip, x, y, net]], "seconds": taken}

"copper": every bridge's two wires end up joined by its net's closed
crosspoints, by any way through the copper. With "fewest" false the search
stops at the first routing it finds. A malformed problem is exit 2.
"""
import collections
import json
import sys
import time

from ortools.sat.python import cp_model


def read(text):
    p = json.loads(text)
    bridges = [(str(a), str(b), net) for a, b, net in p["bridges"]]
    terminals = {str(w): net for w, net in p["terminals"].items()}
    crosspoints = [(str(chip), int(x), int(y), str(wa), str(wb)) for chip, x, y, wa, wb in p["crosspoints"]]
    if p["rule"] not in ("copper", "firmware"):
        raise ValueError("unknown rule %r" % (p["rule"],))
    for a, b, net in bridges:
        if terminals.get(a) != net or terminals.get(b) != net:
            raise ValueError("bridge %s-%s is not between two terminals of net %r" % (a, b, net))
    return bridges, terminals, crosspoints, p["rule"], float(p["seconds"]), bool(p.get("fewest", True))


def components(bridges):
    """The wires each net's bridges tie together: [(net, [wires])]. One net
    is one group unless a bridge between two of its parts was not given."""
    parent = {}

    def find(w):
        while parent.setdefault(w, w) != w:
            w = parent[w]
        return w

    for a, b, _ in bridges:
        parent[find(a)] = find(b)
    groups = collections.defaultdict(list)
    for a, b, net in bridges:
        for w in (a, b):
            if w not in groups[net, find(w)]:
                groups[net, find(w)].append(w)
    return [(net, wires) for (net, _), wires in groups.items()]


def solve(bridges, terminals, crosspoints, rule, seconds, fewest):
    if rule != "copper":
        raise ValueError("rule %r is not built yet" % rule)
    nets = sorted({net for _, _, net in bridges})
    wires = sorted({w for c in crosspoints for w in c[3:]} | set(terminals))
    m = cp_model.CpModel()

    # "this wire is that net's": fixed for a terminal, else at most one net's
    owns = {}
    for w in wires:
        if w not in terminals:
            for net in nets:
                owns[w, net] = m.NewBoolVar("")
            m.AddAtMostOne(owns[w, net] for net in nets)
    may = lambda w, net: terminals[w] == net if w in terminals else True

    # "this crosspoint is closed for that net", which needs both its wires to be the net's
    closed = {}
    at = collections.defaultdict(list)              # wire -> [(crosspoint index, the wire across it)]
    for i, (_, _, _, wa, wb) in enumerate(crosspoints):
        at[wa].append((i, wb))
        at[wb].append((i, wa))
        for net in nets:
            if may(wa, net) and may(wb, net):
                closed[i, net] = m.NewBoolVar("")
                for w in (wa, wb):
                    if w not in terminals:
                        m.AddImplication(closed[i, net], owns[w, net])

    # any copper: each group of wires its bridges tie together is one tree. One
    # of them sends a unit of flow to each of the others, through the net's
    # closed crosspoints only.
    for net, group in components(bridges):
        need, root = len(group) - 1, group[0]
        flow = {}                                   # (crosspoint, wire) -> the flow leaving that wire through it
        for (i, n), shut in closed.items():
            if n == net:
                wa, wb = crosspoints[i][3:]
                flow[i, wa] = m.NewIntVar(0, need, "")
                flow[i, wb] = m.NewIntVar(0, need, "")
                m.Add(flow[i, wa] + flow[i, wb] <= need * shut)
        for w in wires:
            if may(w, net):
                out = sum(flow[i, w] for i, _ in at[w] if (i, w) in flow)
                into = sum(flow[i, o] for i, o in at[w] if (i, o) in flow)
                m.Add(out - into == (need if w == root else -1 if w in group else 0))

    m.Minimize(sum(closed.values()))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_workers = 8
    if not fewest:
        solver.parameters.stop_after_first_solution = True
    started = time.time()
    status = solver.Solve(m)
    routable = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
    return {"verdict": "routable" if routable else "not_routable" if status == cp_model.INFEASIBLE else "unknown",
            "fewest_proved": fewest and status == cp_model.OPTIMAL,
            "closed": [[*crosspoints[i][:3], net] for (i, net), shut in closed.items() if solver.Value(shut)] if routable else [],
            "seconds": round(time.time() - started, 3)}


def main():
    try:
        problem = read(sys.stdin.read())
        answer = solve(*problem)
    except (ValueError, KeyError, TypeError) as e:
        print("solve.py: malformed problem: %s" % e, file=sys.stderr)
        return 2
    json.dump(answer, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
