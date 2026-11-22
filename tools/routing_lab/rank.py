# SPDX-License-Identifier: MIT
"""Which wires of the fabric could a next board do without.

The wires ranked are the ones that are only copper between chips: the lanes
between breadboard chips, the lanes from a breadboard chip to an SF chip, the
bounce rows and the hub lanes. A node's wire is not ranked.

Two different questions, kept apart:

- What does the firmware's router lose without the wire? `removal` routes
  the battery again with the wire taken away. The loss is signed: this router
  sometimes routes more without a wire.
- Does the copper need the wire? `needed` asks the exact solver whether each
  netlist can be routed without it at all. "Needed" is said only on a proof,
  "not needed" only on a routing that does without it; anything else is
  "unknown".

How often a wire is used answers neither: it follows the router's search
order.
"""
import json
import re

import arrangement
import ceiling
import copper
import lab
import runner
import variants

DIR = variants.BUILD_DIR / "rank"                   # a ranking is kept here, one file a variant and arrangement
KINDS = ("lane", "sf lane", "bounce", "hub")
SHAPES = {(("bb", "X"), ("bb", "X")): "lane", (("bb", "X"), ("sf", "Y")): "sf lane", (("bb", "Y"),): "bounce",
          (("sf", "X"), ("sf", "X")): "hub"}


def wires(a):
    """The wires of an arrangement that can be ranked: [{"wire", "kind",
    "pins": [(chip, axis, pin)]}], by kind (as KINDS has them), then name.
    "lane": two X pins on breadboard chips. "sf lane": a breadboard chip's X
    pin and an SF chip's Y pin. "bounce": one Y pin of a breadboard chip.
    "hub": two X pins on SF chips. None of them a node's wire."""
    nodes = set(a.NODE_NET.values())
    out = []
    for name, pins in a.pins().items():
        kind = SHAPES.get(tuple(sorted((a.ROLE[chip], axis) for chip, axis, _ in pins)))
        if kind and name not in nodes:
            out.append({"wire": name, "kind": kind, "pins": pins})
    return sorted(out, key=lambda w: (KINDS.index(w["kind"]), w["wire"]))


def without(a, *names):
    """`a` with those wires taken away, named "<a.name> without <wire>, <wire>".
    Its `data` is the JSON a file of it would hold. Raises ValueError for a
    wire `a` does not have."""
    pins = a.pins()
    missing = [n for n in names if n not in pins]
    if missing:
        raise ValueError("%s has no wire %s" % (a.name, ", ".join(missing)))
    gone = dict(a.data.get("pins") or {})
    gone.update(("%s.%s%d" % pin, None) for n in names for pin in pins[n])
    return arrangement.parse("%s without %s" % (a.name, ", ".join(names)), dict(a.data, pins=gone))


def usage(results):
    """{wire: {"cases": n, "primary": n, "duplicate": n}}: the cases in which
    the wire carries a net, and the crosspoints closed on it by primary paths
    and by duplicates, summed over the results."""
    out = {}
    for r in results:
        paint = copper.paint(r)
        for name, w in paint["wires"].items():
            out.setdefault(name, {"cases": 0, "primary": 0, "duplicate": 0})["cases"] += bool(w["nets"])
        for c in paint["crosspoints"]:
            for axis in "XY":
                out[copper.wire(c["chip"], axis, c[axis.lower()])]["duplicate" if c["dup"] else "primary"] += 1
    return out


def _totals(results):
    worst = [r["metrics"]["worst_r"] for r in results if r["metrics"].get("worst_r") is not None]
    return {"primaries": sum(r["metrics"]["routed_primaries"] for r in results),
            "fully_routed": sum(1 for r in results if lab.fully_routed(r)),
            "crosspoints": sum(r["metrics"]["crosspoints"] for r in results),
            "worst_r": max(worst) if worst else None}


def _loss(base, after):
    """The baseline against the run without the wire, signed so that more is worse for the router in every column."""
    r = None if base["worst_r"] is None or after["worst_r"] is None else after["worst_r"] - base["worst_r"]
    return {"primaries": base["primaries"] - after["primaries"], "fully_routed": base["fully_routed"] - after["fully_routed"],
            "crosspoints": after["crosspoints"] - base["crosspoints"], "worst_r": r}


def removal(v, cases, a, wires=None, progress=None):
    """What the firmware's router loses without each wire: the battery on `a`
    (the baseline), then on `a` without each of `wires` (names; every wire
    `rank.wires(a)` lists when None).

    {"arrangement", "feed", "engine": "router", "variant": {"name", "hash"},
    "cases": n, "baseline": totals, "wires": [entry]}, totals being
    {"primaries": routed, "fully_routed": n, "crosspoints": n, "worst_r"} and
    an entry {"wire", "kind", "pins", "usage" (in the baseline), "loss",
    "by_class": {class: loss}, "worse": [cases], "better": [cases],
    "used_after"}.

    A loss is the baseline minus the run without the wire for primaries and
    for cases fully routed, and the other way round for crosspoints and
    worst_r: positive is the router doing worse without the wire, negative
    doing better. "worse" and "better" are the cases with fewer and with more
    primaries routed. "used_after" counts the crosspoints closed on the wire's
    pins in the run without it, and must be 0. progress(done, of, wire) is
    called after each wire. Raises RouterCannot, BuildError, ValueError."""
    ranked = {w["wire"]: w for w in globals()["wires"](a)}
    names = list(ranked) if wires is None else list(wires)
    unknown = [n for n in names if n not in ranked]
    if unknown:
        raise ValueError("not a wire that can be ranked on %s: %s (a lane, a bounce row or a hub lane is)" % (
            a.name, ", ".join(unknown)))
    base = runner.run_battery(v, cases, arrangement=a)
    used = usage(base)
    classes = list(dict.fromkeys(r["cls"] for r in base))
    of = lambda results, cls: [r for r in results if r["cls"] == cls]
    entries = []
    for done, name in enumerate(names, 1):
        after = runner.run_battery(v, cases, arrangement=without(a, name))
        pins = set(ranked[name]["pins"])
        moved = [(b["case"], r["metrics"]["routed_primaries"] - b["metrics"]["routed_primaries"]) for b, r in zip(base, after)]
        entries.append(dict(
            ranked[name], usage=used.get(name, {"cases": 0, "primary": 0, "duplicate": 0}),
            loss=_loss(_totals(base), _totals(after)),
            by_class={cls: _loss(_totals(of(base, cls)), _totals(of(after, cls))) for cls in classes},
            worse=[case for case, d in moved if d < 0], better=[case for case, d in moved if d > 0],
            used_after=sum(1 for r in after for c in copper.paint(r)["crosspoints"]
                           if (c["chip"], "X", c["x"]) in pins or (c["chip"], "Y", c["y"]) in pins)))
        if progress:
            progress(done, len(names), name)
    return {"arrangement": a.name, "feed": a.feed, "engine": "router", "variant": {"name": v.name, "hash": v.hash},
            "cases": len(cases), "baseline": _totals(base), "wires": entries}


def _on(pins):
    """A test for crosspoints [chip, x, y, ...]: is it on one of these pins."""
    pins = {tuple(p) for p in pins}
    return lambda c: (c[0], "X", c[1]) in pins or (c[0], "Y", c[2]) in pins


def need(given, kept, wire_pins, rule="firmware", seconds=5.0):
    """Does a netlist need a wire: ("no", a routing without it), ("yes",
    None) or ("unknown", None). `given` is the problem (ceiling.problem),
    `kept` a routing known to satisfy it ([[chip, x, y, net]]), `wire_pins`
    the wire's pins.

    A kept routing with no crosspoint on the pins settles it, and nothing is
    asked. Else the solver is asked the problem without the crosspoints on
    those pins: a routing that passes the lab's own check is "no"; a proof
    that there is none is "yes"; out of time, an error, or an answer the
    check does not pass is "unknown", never either."""
    on = _on(wire_pins)
    if not any(on(c) for c in kept):
        return "no", kept
    less = dict(given, crosspoints=[c for c in given["crosspoints"] if not on(c)])
    said = ceiling.ask(less, rule, seconds, fewest=False)
    if said.get("error"):
        return "unknown", None
    if said["verdict"] == "routable" and not ceiling.faults(less, said["closed"], rule):
        return "no", said["closed"]
    return ("yes", None) if said["verdict"] == "not_routable" else ("unknown", None)


def needed(v, cases, a, ranking, rule="firmware", seconds=5.0, progress=None):
    """`ranking` (from `removal`) with the solver's word on every wire:
    "needed_by" (the cases proved not routable without it), "not_needed" (how
    many have a routing without it) and "unknown" (the cases with neither).
    Adds "rule", "seconds" and "needed_cases" (the cases with a netlist), and
    the engine becomes "router and solver".

    For each case the routing to start from is the router's own primary paths
    on `a` when they pass the lab's check (its duplicates are not what the
    netlist asks for), else one the solver finds; a case with neither is
    unknown for every wire. The solver is asked of a wire only when every
    routing known for the case touches it, and what it finds is kept for the
    wires after. progress(done, of, case) is called after each case."""
    g = ceiling.graph(a)
    entries = [dict(w, needed_by=[], not_needed=0, unknown=[]) for w in ranking["wires"]]
    results = runner.run_battery(v, cases, arrangement=a)
    counted = 0
    for done, result in enumerate(results, 1):
        paint = copper.paint(result)
        given = ceiling.problem(paint, g)
        if given is not None and not given["unplaced"]:
            counted += 1
            known = [[[c["chip"], c["x"], c["y"], c["net"]] for c in paint["crosspoints"] if not c["dup"]]]
            if ceiling.faults(given, known[0], rule):               # the router left a bridge: has the netlist a routing at all?
                said = ceiling.ask(given, rule, seconds, fewest=False)
                good = said["verdict"] == "routable" and not said.get("error") and not ceiling.faults(given, said["closed"], rule)
                known = [said["closed"]] if good else []
            for w in entries:
                on = _on(w["pins"])
                if not known:
                    verdict = "unknown"
                elif any(not any(on(c) for c in routing) for routing in known):
                    verdict = "no"
                else:
                    verdict, found = need(given, known[0], w["pins"], rule, seconds)
                    if found is not None:
                        known.insert(0, found)
                if verdict == "no":
                    w["not_needed"] += 1
                else:
                    w["needed_by" if verdict == "yes" else "unknown"].append(result["case"])
        if progress:
            progress(done, len(results), result["case"])
    return dict(ranking, wires=entries, engine="router and solver", rule=rule, seconds=seconds, needed_cases=counted)


def path(variant_hash, name):
    """Where the ranking of a variant on an arrangement is kept (the name made safe for a file)."""
    return DIR / ("%s_%s.json" % (variant_hash, re.sub(r"[^A-Za-z0-9_.-]+", "_", name)))


def save(ranking):
    """Write a ranking to its place under DIR; returns the path."""
    where = path(ranking["variant"]["hash"], ranking["arrangement"])
    where.parent.mkdir(parents=True, exist_ok=True)
    where.write_text(json.dumps(ranking) + "\n")
    return where
