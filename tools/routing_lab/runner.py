# SPDX-License-Identifier: MIT
"""Run cases on a built harness and judge them.

One case per process (the router keeps state between rebuilds, and a crash or
a hang then costs one case). The judge is test/hil/routing_check.py, the same
copper model the HIL suite runs against a board.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import copper
import variants

LAB = Path(__file__).resolve().parent
HIL = LAB.parent.parent / "test" / "hil"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

import routing_check as rc      # noqa: E402
from fabric_v5 import NODE_NAME  # noqa: E402

RESULTS_DIR = variants.BUILD_DIR / "results"
STDERR_TAIL = 4000
BLOCK_NET = 59          # the phantom net a blocked pin is claimed for: kBlockNet (MAX_NETS - 1) in lab_harness.cpp


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
            "worst_r": None, "median_r": None, "rail_worst_r": None}
    base.update(metrics or {})
    return {"case": case.name, "cls": case.cls, "status": status, "problems": list(problems),
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


def judge(case, sections, stderr="", block=()):
    """A result from one case's harness sections."""
    b, xbar = sections.get("b", ""), sections.get("xbar", "")
    if block:
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
    result["metrics"].update(copper.resistance_metrics(result))
    return result


def run_case(binary, case, *, repeat=2, block=(), timeout=20.0):
    """Route one case in its own process and judge it."""
    stdout, stderr, code = run_harness(binary, case, repeat=repeat, block=block, timeout=timeout)
    if code is None:
        return _result(case, "timeout", problems=["no answer in %g s" % timeout], stderr=stderr)
    if code != 0:
        return _result(case, "crash", problems=["the harness exited with %d" % code], stderr=stderr)
    sections = parse_sections(stdout).get(case.name)
    if sections is None:
        return _result(case, "crash", problems=["the harness printed nothing for this case"], stderr=stderr)
    return judge(case, sections, stderr, block)


def _judge_stamp():
    """Changes when the judging code does, so cached results are not reused."""
    h = hashlib.sha256()
    for path in (Path(__file__), Path(copper.__file__), HIL / "routing_check.py", HIL / "fabric_v5.py"):
        h.update(path.read_bytes())
    return h.hexdigest()


def _cache_path(v, case, repeat, block, stamp):
    key = json.dumps([case.to_protocol(block), case.cls, case.must_route, case.taps_required, repeat, stamp])
    return RESULTS_DIR / v.hash / (hashlib.sha256(key.encode()).hexdigest() + ".json")


def run_battery(v, cases, *, jobs=None, block=(), use_cache=True):
    """Results for every case, in order. Raises variants.BuildError."""
    binary = variants.build(v)
    stamp = _judge_stamp()
    repeat = 2

    def one(case):
        path = _cache_path(v, case, repeat, block, stamp)
        if use_cache and path.exists():
            with open(path) as f:
                return json.load(f)
        result = run_case(binary, case, repeat=repeat, block=block)
        if result["status"] != "timeout":           # a timeout may be the machine, not the case
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp%d" % os.getpid())
            with open(tmp, "w") as f:
                json.dump(result, f)
            os.replace(tmp, path)
        return result

    with ThreadPoolExecutor(jobs or os.cpu_count() or 4) as pool:
        return list(pool.map(one, cases))
