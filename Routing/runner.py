# SPDX-License-Identifier: MIT
"""Run cases on a built harness and judge them.

One case per process (the router keeps state between rebuilds, and a crash or
a hang then costs one case). The judge is test/hil/routing_check.py, the same
copper model the HIL suite runs against a board.
"""
import dataclasses
import functools
import hashlib
import json
import os
import re
import subprocess
import sys
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import arrangement as arrangement_module             # run_case and run_battery take an `arrangement`
import ceiling
import copper
import variants

LAB = Path(__file__).resolve().parent
HIL = LAB.parent.parent / "test" / "hil"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

import fabric_v5                # noqa: E402
import routing_check as rc      # noqa: E402
from fabric_v5 import NODE_NAME  # noqa: E402

RESULTS_DIR = variants.BUILD_DIR / "results"
STDERR_TAIL = 4000
BLOCK_NET = 59          # the phantom net a blocked pin is claimed for: kBlockNet (MAX_NETS - 1) in lab_harness.cpp
TAKEN = "taken away here"       # in the problem of a case whose router closed a crosspoint on a blocked pin


def parse_sections(stdout):
    """{case name: {section: text}} from the harness's stdout."""
    out = {}
    for m in re.finditer(r"^=== case (\S+)\n(.*?)^=== end$", stdout, re.S | re.M):
        parts = re.split(r"^--- (\w+)\n", m.group(2), flags=re.M)
        out[m.group(1)] = {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}
    return out


def run_harness(binary, case, *, repeat=2, block=(), timeout=20.0):
    """(stdout, stderr, returncode); returncode None when the timeout expired."""
    args = [str(binary)] + (["--repeat", str(repeat)] if repeat > 1 else [])
    try:
        p = subprocess.run(args, input=case.to_protocol(block), capture_output=True, text=True,
                           errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired as e:
        err = e.stderr.decode(errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        return "", err, None
    return p.stdout, p.stderr, p.returncode


def _result(case, status, problems=(), notes=(), rejected=(), metrics=None, b="", xbar="", stderr=""):
    base = {"primaries": 0, "routed_primaries": 0, "refused": 0, "bounced": 0, "routed_duplicates": 0,
            "crosspoints": 0, "taps": None, "taps_dead": [], "repeat_same": None,
            "worst_r": None, "median_r": None, "rail_worst_r": None, "broken": 0, "missed": 0}
    base.update(metrics or {})
    return {"case": case.name, "cls": case.cls, "must_route": bool(case.must_route), "about": case.notes,
            "status": status, "problems": list(problems),
            "notes": list(notes), "rejected": [list(r) for r in rejected], "left_out": [], "refused": [],
            "metrics": base, "b": b, "xbar": xbar, "stderr": stderr[-STDERR_TAIL:]}


def _without_block_claims(b):
    """The b report with the phantom net's claims shown as free. A blocked
    pin is a claim with no copper by design; it is the experiment, not a
    bookkeeping fault of the router's."""
    head, sep, status = b.partition("Chip Status")
    lines = [re.sub(r"(?<!\d)%d(?!\d)" % BLOCK_NET, ".", line) if re.match(r"[A-L]\t", line) else line
             for line in status.split("\n")]
    return head + sep + "\n".join(lines)


@functools.lru_cache(maxsize=None)
def _copper_without(block):
    """V5's copper without the blocked pins: where the judge looks for the
    path a failed bridge could have had."""
    if not block:
        return ceiling.graph()
    x, y = ({chip: list(pins) for chip, pins in table.items()} for table in (fabric_v5.X_NET, fabric_v5.Y_NET))
    for axis, chip, pin in block:
        (x if axis == "X" else y)[fabric_v5.CHIPS[chip]][pin] = None
    return ceiling.graph(types.SimpleNamespace(CHIPS=fabric_v5.CHIPS, X_NET=x, Y_NET=y, NODE_NET=fabric_v5.NODE_NET))


def taken_pins(arrangement):
    """The pins the harness must block to run an arrangement. Raises
    RouterCannot when it is not V5 with pins taken away."""
    taken = arrangement_module.blocks(arrangement)
    if taken is None:
        raise arrangement_module.RouterCannot(
            "the firmware's router cannot route %s: %s; ask the solver: python3 tools/routing_lab/lab.py arrangement score %s"
            % (arrangement.name, arrangement_module.why_not_router(arrangement), arrangement.name))
    return taken


def on(case, block=(), arrangement=None):
    """How a case is run on an arrangement: (the case with the feed as the
    arrangement has it, every pin to block, the names of the nodes the case
    uses and the arrangement has dropped). With no arrangement the case and
    the block are as given. Raises RouterCannot when the firmware's router
    cannot run the arrangement at all."""
    block = [tuple(b) for b in block]
    if arrangement is None:
        return case, block, []
    taken = taken_pins(arrangement)
    if not arrangement.feed and case.probe[0]:
        case = dataclasses.replace(case, probe=(0, case.probe[1]))
    lacking = sorted({n for bridge in case.bridges for n in bridge[:2]} & set(arrangement.dropped))
    return case, block + [b for b in taken if b not in block], [str(NODE_NAME.get(n, n)) for n in lacking]


def _named(result, case, arrangement):
    """The result saying who routed it and on what: the arrangement's name
    ("v5" when none was given), whether the probe feed was on the fabric, and
    the engine. Given afresh to a result read from the cache, which is kept
    by what was run (the feed, the blocked pins) and not by a name."""
    result.update(arrangement=arrangement.name if arrangement is not None else "v5", feed=bool(case.probe[0]),
                  engine="router")
    return result


def judge(case, sections, stderr="", block=()):
    """A result from one case's harness sections. With pins blocked, the path
    a failed bridge could have had is looked for on the copper without them."""
    b, xbar = sections.get("b", ""), sections.get("xbar", "")
    if block:
        # A blocked pin is claimed for net 59, so a netlist that has a net 59 of its own cannot be told from one.
        if any(int(n) >= BLOCK_NET for n in re.findall(r"Net (\d+)\]", b)):
            return _result(case, "crash", b=b, xbar=xbar, stderr=stderr, problems=[
                "this netlist reaches net %d, the number blocked pins are marked with: it cannot be run with pins taken away"
                % BLOCK_NET])
        b = _without_block_claims(b)
    rejected = [[int(v) for v in line.split()] for line in sections.get("rejected", "").splitlines() if line.strip()]
    notes = ["rejected by the firmware: %s-%s" % (NODE_NAME.get(a, a), NODE_NAME.get(c, c)) for a, c in rejected]
    if len(case.bridges) - len(rejected) <= 0:
        return _result(case, "empty", notes=notes, rejected=rejected, b=b, xbar=xbar, stderr=stderr)

    # Strict claims only with no stacking at all: -1 is "default", which
    # stacks, and a culled duplicate keeps its claims (the HIL suite's rule).
    strict = case.must_route and all(dup == 0 for _, _, dup in case.bridges)
    try:
        verdict, metrics = rc.full_check(b, xbar, expect_all_routed=case.must_route, strict_claims=strict)
    except (ValueError, KeyError, IndexError) as e:
        return _result(case, "crash", problems=["cannot read the harness output: %s" % e], notes=notes,
                       rejected=rejected, b=b, xbar=xbar, stderr=stderr)
    problems = list(verdict.problems)
    notes += verdict.notes
    # A bridge the firmware keeps out of every net ("Net ?") is never routed:
    # it would join two nodes a special net keeps apart, or the net tables
    # were already full.
    left_out = copper.left_out_pairs(b)
    for a, c in left_out:
        notes.append("left out of every net by the firmware: %s-%s" % (NODE_NAME.get(a, a), NODE_NAME.get(c, c)))

    # A primary path the firmware's safety check vetoed is not a routing
    # miss: the router found a path and RouteSafety refused to close it.
    refused = [[int(v) for v in line.split()] for line in sections.get("refused", "").splitlines() if line.strip()]
    metrics["refused"] = sum(1 for r in refused if r[2] == 0)
    for n1, n2, duplicate, a, c in refused:
        if not duplicate:
            notes.append("refused by the firmware's safety check (RouteSafety: short %d/%d): %s-%s" % (
                a, c, NODE_NAME.get(n1, n1), NODE_NAME.get(n2, n2)))

    taps_text = sections.get("taps", "")
    routes = dict(re.findall(r"\[nvscan\] route (\d+):\s*(.*)", taps_text))
    if routes:
        dead = sorted(int(n) for n, route in routes.items() if route.startswith("(none"))
        metrics["taps"], metrics["taps_dead"] = len(routes), dead
        if dead:
            line = "no sense-tap route for " + " ".join(NODE_NAME.get(n, str(n)) for n in dead)
            (problems if case.taps_required else notes).append(line)
    elif case.taps_required:
        # the HIL suite's rule: a taps proof with no routes listed has failed
        problems.append("no sense-tap routes were listed, and this case requires them (%s)" % (
            taps_text.strip() or "no taps section"))

    repeat = sections.get("repeat", "").strip()
    if repeat:
        metrics["repeat_same"] = repeat == "same"
        if repeat != "same":
            problems.append("the same case routed twice gives different routes")

    result = _result(case, "problems" if problems else "ok", problems, notes, rejected, metrics, b, xbar, stderr)
    # The two other ways the firmware says no, as data for the paint (the notes say the same in words).
    result["left_out"] = left_out
    result["refused"] = [[r[0], r[1]] for r in refused if r[2] == 0]
    measured = copper.resistance_metrics(result)
    # A primary the path table lists as routed whose copper does not join its
    # nodes is wrong on any class, must-route or scored: the firmware would
    # report the bridge made. (The checker says so itself only when told every
    # bridge must route; the line is the same, so it is not said twice.)
    broken = measured.pop("broken")
    for n1, n2, net in broken:
        line = "NOT CONNECTED: %s-%s (net %d)" % (rc.node_label(n1), rc.node_label(n2), net)
        if line not in result["problems"]:
            result["problems"].append(line)
    if broken:
        result["status"] = "problems"
    result["metrics"].update(measured, broken=len(broken))
    # Failed bridges the copper could have carried with everything else where
    # it is: a worse score, and against a baseline a regression. Not a status.
    paint = copper.paint(result)
    # A pin taken away is no copper. The firmware still knows V5, though: where it has a node on such a pin (GND's
    # second pin, an end of the probe feed) it closes it, blocked or not. That is no result for this arrangement.
    # (arrangement.why_not_router and check() keep those arrangements from the router; this says so if one gets by.)
    gone = {tuple(p) for p in block}
    on_gone = sorted({(c["chip"], axis, c[axis.lower()]) for c in paint["crosspoints"] for axis in "XY"
                      if (axis, fabric_v5.CHIPS.index(c["chip"]), c[axis.lower()]) in gone})
    if on_gone:
        where = ", ".join("chip %s %s%d" % (chip, axis.lower(), pin) for chip, axis, pin in on_gone)
        return _result(case, "crash", notes=notes, rejected=rejected, b=b, xbar=xbar, stderr=stderr, problems=[
            "the router closed a crosspoint on %s, %s: the firmware still has a node or the probe feed there, so its router "
            "cannot run this netlist on this copper" % (where, TAKEN)])
    g = _copper_without(tuple(sorted(gone)))
    result["metrics"]["missed"] = sum(1 for m in ceiling.missed(paint, g) if m["path"] is not None)
    return result


def run_case(binary, case, *, repeat=2, block=(), timeout=20.0, arrangement=None):
    """Route one case in its own process and judge it. On an arrangement: with
    its feed and without its pins. A case on a node the arrangement dropped
    is not routed at all: its result is "unplaced", which is neither a miss
    nor a fault."""
    case, block, lacking = on(case, block, arrangement)
    if lacking:
        result = _result(case, "unplaced", notes=["cannot be placed on %s: it has no %s" % (arrangement.name, ", ".join(lacking))])
        result["lacks"] = lacking
        return _named(result, case, arrangement)
    stdout, stderr, code = run_harness(binary, case, repeat=repeat, block=block, timeout=timeout)
    if code is None:
        result = _result(case, "timeout", problems=["no answer in %g s" % timeout], stderr=stderr)
    elif code != 0:
        result = _result(case, "crash", problems=["the harness exited with %d" % code], stderr=stderr)
    else:
        sections = parse_sections(stdout).get(case.name)
        result = (judge(case, sections, stderr, block) if sections is not None else
                  _result(case, "crash", problems=["the harness printed nothing for this case"], stderr=stderr))
    return _named(result, case, arrangement)


def _judge_stamp():
    """Changes when the judging code does, so cached results are not reused."""
    h = hashlib.sha256()
    for path in (Path(__file__), Path(copper.__file__), Path(ceiling.__file__), HIL / "routing_check.py",
                 HIL / "fabric_v5.py"):
        h.update(path.read_bytes())
    return h.hexdigest()


def _cache_path(v, case, repeat, block, stamp):
    key = json.dumps([case.to_protocol(block), case.cls, case.must_route, case.taps_required, repeat, stamp])
    return RESULTS_DIR / v.hash / (hashlib.sha256(key.encode()).hexdigest() + ".json")


def run_battery(v, cases, *, jobs=None, block=(), use_cache=True, arrangement=None):
    """Results for every case, in order, each saying its "arrangement", "feed"
    and "engine". On an arrangement every case runs with the feed as the
    arrangement has it and without its pins (besides any in `block`). Raises
    variants.BuildError, and RouterCannot for an arrangement that is not V5
    with pins taken away."""
    if arrangement is not None:
        taken_pins(arrangement)                     # RouterCannot before anything is built
    binary = variants.build(v)
    stamp = _judge_stamp()
    repeat = 2

    def one(case):
        run_as, blocked, lacking = on(case, block, arrangement)
        path = _cache_path(v, run_as, repeat, blocked, stamp)
        if use_cache and not lacking and path.exists():
            with open(path) as f:
                return _named(json.load(f), run_as, arrangement)
        result = run_case(binary, case, repeat=repeat, block=block, arrangement=arrangement)
        if result["status"] not in ("timeout", "unplaced"):     # a timeout may be the machine, not the case
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp%d" % os.getpid())
            with open(tmp, "w") as f:
                json.dump(result, f)
            os.replace(tmp, path)
        return result

    with ThreadPoolExecutor(jobs or os.cpu_count() or 4) as pool:
        return list(pool.map(one, cases))
