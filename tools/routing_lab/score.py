# SPDX-License-Identifier: MIT
"""Two crossbar arrangements, asked the same netlists by the exact solver.

The firmware's router runs only V5's copper, so an arrangement that moves a
pin has no router to score it with. The solver takes any copper. What it says
is a ceiling: what a router that keeps the path shape could reach on that
copper, not what a V6 router would do.

The netlists are the firmware's own. Each case is run once by the harness on
V5's copper with the first arrangement's feed setting, for the bridges the
firmware allows and the nets it makes of them; the router's routing of them
is not used. Both arrangements are then asked those same netlists.
"""
import random

import arrangement
import ceiling
import edge
import runner
import variants

VERDICTS = ("routable", "not_routable", "unknown", "unplaced")


def compare(v, cases, a, b=None, rule="firmware", seconds=10.0, fewest=True, progress=None):
    """{"a", "b", "feed", "rule", "seconds", "engine": "solver", "rows":
    [{"case", "cls", "a": verdict, "b": verdict}], "summary"}: every case
    asked on arrangement `a` and on `b` (V5's copper when None), a verdict
    being ceiling.verdict's answer without its routing.

    summary: "cases"; for "a" and "b" how many are of each of VERDICTS;
    "only_a" and "only_b", the cases proved routable on one and proved not
    routable on the other (not known is not "does not fit"); "proved_on_both"
    and "fewest", the crosspoints each needs over the cases whose fewest is
    proved on both; "errors", the cases with an answer that does not stand.
    progress(done, of, case) is called after each case."""
    b = arrangement.with_feed(b or arrangement.V5, a.feed)
    results = runner.run_battery(v, cases, arrangement=arrangement.base(a.feed))
    rows = []
    for done, result in enumerate(results, 1):
        row = {"case": result["case"], "cls": result["cls"]}
        for side, on in (("a", a), ("b", b)):
            said = ceiling.verdict(result, rule, seconds, fewest=fewest, arrangement=on)
            row[side] = {k: value for k, value in said.items() if k != "closed"}
        rows.append(row)
        if progress:
            progress(done, len(results), result["case"])
    both = [r for r in rows if all(r[s]["verdict"] == "routable" and r[s]["fewest_proved"] for s in "ab")]
    only = lambda yes, no: [r["case"] for r in rows if r[yes]["verdict"] == "routable" and r[no]["verdict"] == "not_routable"]
    summary = {"cases": len(rows), "only_a": only("a", "b"), "only_b": only("b", "a"), "proved_on_both": len(both),
               "fewest": {s: sum(r[s]["crosspoints"] for r in both) for s in "ab"},
               "errors": [r["case"] for r in rows if r["a"].get("error") or r["b"].get("error")]}
    for side in "ab":
        summary[side] = {word: sum(1 for r in rows if r[side]["verdict"] == word) for word in VERDICTS}
    return {"a": a.name, "b": b.name, "feed": a.feed, "rule": rule, "seconds": seconds, "engine": "solver",
            "rows": rows, "summary": summary}


def lengths(v, a, b=None, lists=2, seed=1, seconds=20.0, longest=80, progress=None):
    """How far the edge class's random lists grow on each arrangement:
    [{"list": i, "a": {"bridges": k, "next_is": why one more is not proved},
    "b": {...}}], bridges 0 (and next_is None) when not one is proved. List i
    is drawn as `lab.py edge` draws it, so list 0 of seed 1 is edge_1_0's.
    Both grow with `a`'s feed setting. About a minute and a half a list an
    arrangement. Raises edge.SolverFailed."""
    b = arrangement.with_feed(b or arrangement.V5, a.feed)
    binary = variants.build(v)
    out = []
    for i in range(lists):
        entry = {"list": i}
        for side, on in (("a", a), ("b", b)):
            grown = edge.grow(binary, random.Random(seed * 100003 + i), "list_%d" % i, seconds, longest, arrangement=on)
            entry[side] = {"bridges": grown[1]["bridges"], "next_is": grown[1]["next_is"]} if grown else \
                {"bridges": 0, "next_is": None}
            if progress:
                progress(2 * i + (side == "b") + 1, 2 * lists, "list %d on %s" % (i, on.name))
        out.append(entry)
    return out
