#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Routing lab: build the firmware's V5 router for the host, route a battery
of netlists with it, and judge the result against the schematic.

    lab.py run [--variant V] [--baseline V0] [--classes dense,real,...] [--case NAME] [--jobs N] [--json FILE]
    lab.py serve [--port 8765] [--tree DIR]... [--no-open]
    lab.py sheet [BOARD.kicad_sch] [--theme NAME]
    lab.py export OUT.html [--variant V] [--baseline V0] [--classes ...]
    lab.py clean
    lab.py solver-setup
    lab.py ceiling [--variant V] [--classes ...] [--case NAME] [--rule firmware|copper] [--seconds 20]
    lab.py edge [--seed 1] [--count 12] [--seconds 20] [--longest 80]
    lab.py arrangement list | show NAME | check NAME
    lab.py build [--variant V]
    lab.py fidelity CAPTURE_DIR [--variant V]
    lab.py import-state FILE.yaml --name NAME [--class real]

A variant is "worktree" (this checkout), a directory that holds src/ (another
checkout), or a git ref. See README.md.
"""
import argparse
import functools
import json
import re
import subprocess
import sys
from pathlib import Path

import arrangement
import cases
import ceiling
import generators
import runner
import score
import variants

LAB = Path(__file__).resolve().parent
CASES_DIR = LAB / "cases"
FIDELITY_DIR = LAB / "fidelity"
GENERATED = {"dense": cases.dense_cases, "typical": generators.typical, "fuzz": generators.fuzz,
             "stress": generators.stress, "beyond": generators.beyond}
# example: the small cases a visitor sees first, each showing one kind of routing (files under cases/example/);
# edge: from files only (lab.py edge)
CLASSES = ["example", "dense", "real", "typical", "fuzz", "stress", "beyond", "edge"]
OHMS = 42.0             # one closed crosspoint, as measured on a board; the page and --ohms can say otherwise
ON_WHAT = "the crossbar arrangement: v5, a name from `lab.py arrangement list`, or the path of a .json."
# What each class is, for the page to say what a run covers. The counts are worked out, not written here.
CLASS_WHAT = {
    "example": "small cases that each show one kind of routing, with a title and a line about it: what a visitor sees first",
    "dense": "the cases of the bench HIL suite; the ones that suite requires must route here too, the rest are scored",
    "real": "saved board states, imported from slot files with import-state; scored",
    "typical": "seeded circuits shaped like everyday use: an IC or two across the gap, power, ground, a few signals; scored",
    "fuzz": "seeded random netlists of up to twelve bridges; scored",
    "stress": "cases each aimed at one scarce resource (one chip flooded, hub lanes, a forty-node net); scored",
    "beyond": "cases made too big for the fabric on purpose; scored, and must stay free of shorts",
    "edge": "random netlists of about fifty bridges, each proved routable by the exact solver; scored, and how many "
            "route in full is the headline",
}


@functools.lru_cache(maxsize=None)
def _generated_count(cls):
    return len(GENERATED[cls]()) if cls in GENERATED else 0


def about():
    """{class: {"cases": how many it runs, "what": one line}}."""
    return {cls: {"cases": _generated_count(cls) + len(list((CASES_DIR / cls).glob("*.json"))), "what": CLASS_WHAT[cls]}
            for cls in CLASSES}


def battery(classes):
    """Every case of the named classes: the generated ones, then any JSON
    files under cases/<class>/."""
    out = []
    for cls in classes:
        if cls not in CLASSES:
            raise ValueError("unknown class %r (have %s)" % (cls, ", ".join(CLASSES)))
        if cls in GENERATED:
            out += GENERATED[cls]()
        for path in sorted((CASES_DIR / cls).glob("*.json")):
            try:
                out.append(cases.load_json(path))
            except (ValueError, TypeError, KeyError) as e:     # bad JSON, or not a case
                raise ValueError("cannot read the case file %s: %s" % (path, e)) from None
    return out


def fully_routed(result):
    """Every primary the firmware allowed is routed, and its copper joins its
    nodes. A path its safety check refused is the firmware saying no, not the
    router failing."""
    m = result["metrics"]
    return (result["status"] in ("ok", "problems") and m["primaries"] > 0 and not m.get("broken")
            and m["routed_primaries"] + m.get("refused", 0) == m["primaries"])


def verified_against_a_board():
    """True when lab.py fidelity has passed against a board capture with the
    harness as it is now (the pass is recorded beside the capture)."""
    for marker in FIDELITY_DIR.glob("board_*/verified.json"):
        try:
            with open(marker) as f:
                if json.load(f).get("harness") == variants.harness_hash():
                    return True
        except (OSError, ValueError):
            pass
    return False


def problem_kind(problem):
    """SHORT, STRAY, NOT CONNECTED, UNCLAIMED WIRE, ...: the capitals a
    routing_check problem starts with; the whole line for anything else."""
    m = re.match(r"[A-Z][A-Z ]*[A-Z]\b", problem)
    return m.group(0) if m else problem


def regressions(base, new):
    """One line per case that got worse than the baseline: it no longer
    routes fully, it crashes or hangs, or it has a kind of problem the
    baseline did not."""
    before = {r["case"]: r for r in base}
    out = []
    for r in new:
        b = before.get(r["case"])
        if b is None or "unplaced" in (r["status"], b["status"]):      # not routed at all: nothing to compare
            continue
        m, bm = r["metrics"], b["metrics"]
        if r["status"] in ("crash", "timeout") and b["status"] not in ("crash", "timeout"):
            out.append("%s: %s (the baseline did not)" % (r["case"], r["status"]))
            continue
        if m["routed_primaries"] < bm["routed_primaries"] or (fully_routed(b) and not fully_routed(r)):
            out.append("%s: routed %d/%d, baseline %d/%d" % (
                r["case"], m["routed_primaries"], m["primaries"], bm["routed_primaries"], bm["primaries"]))
        fresh = sorted({problem_kind(p) for p in r["problems"]} - {problem_kind(p) for p in b["problems"]})
        if fresh:
            out.append("%s: new problem: %s" % (r["case"], "; ".join(fresh)))
        if m.get("missed", 0) > bm.get("missed", 0):
            out.append("%s: %d unrouted where the copper had a path (baseline %d)" % (
                r["case"], m["missed"], bm.get("missed", 0)))
    return out


def exit_code(results, case_list, regression_lines):
    must = {c.name for c in case_list if c.must_route}
    for r in results:
        if r["status"] in ("crash", "timeout"):
            return 1
        if any(p.startswith(("SHORT", "STRAY")) for p in r["problems"]) or r["metrics"].get("broken"):
            return 1
        if r["case"] in must and r["problems"]:
            return 1
    return 1 if regression_lines else 0


def what(a):
    """An arrangement in a line: its name, how far it is from V5, and the feed."""
    if arrangement.blocks(a) is None:
        fabric = "%d pins not as V5 has them" % len(a.changed) if a.changed else "nodes not as V5 has them"
    elif a.taken:
        fabric = "V5 with %d pin%s taken away" % (len(a.taken), "" if len(a.taken) == 1 else "s")
    else:
        fabric = "V5, no pin taken away"
    return "%s (%s, probe feed %s)" % (a.name, fabric, "on" if a.feed else "off")


def print_table(v, results, ohms=OHMS, a=None):
    """One row per class, under a line saying what was routed (the
    arrangement `a`, V5 when None) and by whom. Primaries say whether
    everything routed; copies, xpoints and the worst signal bridge's ohms are
    what tell two routers apart once it has (rail and GND bridges are in the
    page's own column)."""
    print("arrangement: %s   engine: the firmware's router" % what(a or arrangement.V5))
    print("variant: %s  (%s)   %g ohm per crosspoint" % (v.name, v.hash[:12], ohms))
    print("%-9s %6s %13s %12s %8s %9s %7s %14s %10s %7s %8s %10s" % (
        "class", "cases", "fully routed", "primaries", "refused", "problems", "missed", "crash/timeout", "dead taps",
        "copies", "xpoints", "worst ohm"))
    order = []
    for r in results:
        if r["cls"] not in order:
            order.append(r["cls"])
    for cls in order:
        rs = [r for r in results if r["cls"] == cls]
        worst = [r["metrics"]["worst_r"] for r in rs if r["metrics"].get("worst_r") is not None]
        print("%-9s %6d %13d %12s %8d %9d %7d %14d %10d %7d %8d %10d" % (
            cls, len(rs), sum(fully_routed(r) for r in rs),
            "%d/%d" % (sum(r["metrics"]["routed_primaries"] for r in rs), sum(r["metrics"]["primaries"] for r in rs)),
            sum(r["metrics"].get("refused", 0) for r in rs),
            sum(1 for r in rs if r["status"] == "problems"),
            sum(r["metrics"].get("missed", 0) for r in rs),
            sum(1 for r in rs if r["status"] in ("crash", "timeout")),
            sum(len(r["metrics"]["taps_dead"]) for r in rs),
            sum(r["metrics"]["routed_duplicates"] for r in rs),
            sum(r["metrics"]["crosspoints"] for r in rs),
            round(max(worst) * ohms) if worst else 0))
    for r in results:
        m = r["metrics"]
        if r["status"] in ("crash", "timeout"):
            print("  %-8s %s/%s: %s" % (r["status"], r["cls"], r["case"], (r["problems"] or [""])[0]))
        elif r["status"] == "unplaced":
            print("  unplaced %s/%s: no %s on %s" % (r["cls"], r["case"], ", ".join(r["lacks"]), r["arrangement"]))
        elif r["status"] == "problems":
            more = " (+%d more)" % (len(r["problems"]) - 1) if len(r["problems"]) > 1 else ""
            print("  problems %s/%s: %s%s" % (r["cls"], r["case"], r["problems"][0], more))
        elif r["status"] == "ok" and not fully_routed(r):
            print("  unrouted %s/%s: %d of %d primaries routed" % (
                r["cls"], r["case"], m["routed_primaries"], m["primaries"] - m.get("refused", 0)))


def print_case(result):
    m = result["metrics"]
    print("%s/%s: %s, %d of %d primaries, %d duplicates, %d crosspoints, taps %s" % (
        result["cls"], result["case"], result["status"], m["routed_primaries"], m["primaries"],
        m["routed_duplicates"], m["crosspoints"], m["taps"]))
    for p in result["problems"]:
        print("  ! " + p)
    for n in result["notes"]:
        print("  . " + n)
    print(result["b"])
    if result["stderr"].strip():
        print(result["stderr"])


def cmd_run(args):
    case_list = _cases_of(args)
    if case_list is None:
        return 2
    v = variants.resolve(args.variant)
    a = arrangement.load(args.arrangement)
    results = runner.run_battery(v, case_list, jobs=args.jobs, arrangement=a)
    print_table(v, results, args.ohms, a)
    if args.case:
        print_case(results[0])
    lines = []
    if args.baseline:
        base_v = variants.resolve(args.baseline)
        try:
            base = runner.run_battery(base_v, case_list, jobs=args.jobs, arrangement=a)
        except variants.BuildError as e:
            print("the baseline %s does not build:\n%s" % (base_v.name, e.stderr), file=sys.stderr)
            return 3
        lines = regressions(base, results)
        print("against %s: %s" % (base_v.name, "no regressions" if not lines else "%d regressions" % len(lines)))
        for line in lines:
            print("  worse    " + line)
    if not verified_against_a_board():
        print("not verified against a board (see fidelity/README.md)")
    if args.json:
        with open(args.json, "w") as f:
            json.dump({"variant": {"name": v.name, "hash": v.hash}, "arrangement": a.name, "baseline": args.baseline,
                       "regressions": lines, "results": results}, f)
    return exit_code(results, case_list, lines)


def cmd_fidelity(args):
    import fidelity
    ok, diffs = fidelity.check(args.capture_dir, args.variant)
    if ok:
        # Recorded beside the capture: which harness passed. lab.py run stops
        # saying "not verified" only while the harness is still that one.
        with open(Path(args.capture_dir) / "verified.json", "w") as f:
            json.dump({"harness": variants.harness_hash(), "variant": args.variant or Path(args.capture_dir).name}, f)
            f.write("\n")
        print("fidelity: PASS - the harness routes the dense suite as the board capture in %s does" % args.capture_dir)
        return 0
    print("fidelity: FAIL - %d differences from the board capture in %s" % (len(diffs), args.capture_dir))
    for line in diffs[:40]:
        print("  " + line)
    if len(diffs) > 40:
        print("  ... and %d more" % (len(diffs) - 40))
    return 1


def cmd_serve(args):
    import webbrowser

    import server
    srv = server.make_server(args.port, args.tree or [])
    print("routing lab: %s   (Ctrl-C stops it)" % srv.url, flush=True)
    if not args.no_open:
        webbrowser.open(srv.url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        srv.server_close()
    return 0


def cmd_build(args):
    v = variants.resolve(args.variant)
    print("%s  (%s)" % (v.name, v.hash[:12]))
    print(variants.build(v))
    return 0


def cmd_sheet(args):
    import sheet
    try:
        where = sheet.build(args.schematic or sheet.DEFAULT_SCH, args.theme)
    except sheet.SheetUnavailable as e:
        raise ValueError("%s\n  then: %s" % (e, e.hint))
    print("%s: overlay.json, backdrop.svg  (reload the page)" % where)
    return 0


def cmd_export(args):
    import export
    size = export.write(args.out, args.variant, args.baseline, [c for c in args.classes.split(",") if c], args.arrangement,
                        args.backdrop)
    print("%s: %.1f MB, one file, opens without the server" % (args.out, size / 1e6))
    return 0


def cmd_clean(args):
    import shutil
    freed = 0
    # build/sheet stays (small, slow to remake), and so do build/solver-venv (it needs the network) and build/rank
    # (a ranking with the solver's columns is hours of work)
    for name in ("results", "variants", "bin", "ceiling"):
        path = variants.BUILD_DIR / name
        if path.is_dir():
            freed += sum(f.stat().st_size for f in path.rglob("*") if f.is_file() and not f.is_symlink())
            shutil.rmtree(path)
    print("freed %.0f MB (cached results, variant trees, harness binaries, solver answers); the next run rebuilds what"
          " it needs" % (freed / 1e6))
    return 0


def _cases_of(args):
    """The battery an invocation names with --classes and --case, or None after saying there is no such case."""
    classes = [c for c in args.classes.split(",") if c]
    case_list = battery(classes)
    if args.case:
        case_list = [c for c in case_list if c.name == args.case]
        if not case_list:
            print("no case named %r in %s" % (args.case, ", ".join(classes)), file=sys.stderr)
            return None
    return case_list


def cmd_ceiling(args):
    """Ask the solver of every case: can its netlist be routed at all on the
    arrangement, and with how few crosspoints. The netlists are the
    firmware's: each case is run by the harness on the arrangement when the
    router can run it, else on V5 with the arrangement's feed, and then the
    router's two columns say nothing (it routed another fabric). Exit 1 when
    an answer does not stand (the solver failed, or the lab's own check
    contradicts it) or there is no solver."""
    case_list = _cases_of(args)
    if case_list is None:
        return 2
    a = arrangement.load(args.arrangement)
    if not ceiling.solver_installed():
        print("the exact search needs the solver; install it once with: " + ceiling.SETUP)
        return 1
    v = variants.resolve(args.variant)
    router_too = arrangement.blocks(a) is not None
    results = runner.run_battery(v, case_list, arrangement=a if router_too else arrangement.base(a.feed))
    shape = "firmware-shaped paths" if args.rule == "firmware" else "any copper"
    print("arrangement: %s   engine: the exact solver, %s" % (what(a), shape))
    print("variant: %s  (%s)   rule: %s, %g s a case" % (v.name, v.hash[:12], shape, args.seconds))
    print("%-30s %9s %9s  %-13s %s" % ("case", "routed", "router xp", "verdict", "fewest"))
    routable = routed_too = both = extra = unplaced = 0
    errors = []
    for r in results:
        m = r["metrics"]
        d = ceiling.verdict(r, args.rule, args.seconds, arrangement=a)
        unplaced += d["verdict"] == "unplaced"
        fewest = ""
        if d["verdict"] == "routable":
            fewest = ("= %d" if d["fewest_proved"] else "<= %d") % d["crosspoints"]
            routable += 1
            routed_too += fully_routed(r)
            if d["fewest_proved"] and fully_routed(r):
                both += 1
                extra += d["router_crosspoints"] - d["crosspoints"]
        if d["error"]:
            errors.append("%s: %s" % (r["case"], d["error"]))
        routed = "%d/%d" % (m["routed_primaries"], m["primaries"] - m.get("refused", 0))
        print("%-30s %9s %9s  %-13s %s" % (r["case"][:30], routed if router_too else "-",
                                           d["router_crosspoints"] if router_too else "-", d["verdict"].replace("_", " "), fewest))
    if router_too:
        print("provably routable: %d of %d; the router routes %d of those in full" % (routable, len(results), routed_too))
        print("the router uses %d more crosspoints than the fewest over the %d cases where both are known" % (extra, both))
    else:
        print("provably routable: %d of %d (the firmware's router cannot route this arrangement: %s)" % (
            routable, len(results), arrangement.why_not_router(a)))
    if unplaced:
        print("%d cannot be placed on %s: they use a node it does not have" % (unplaced, a.name))
    for line in errors:
        print("  not answered  " + line)
    return 1 if errors else 0


def cmd_solver_setup(args):
    """OR-tools in an environment of its own under build/ (the lab itself
    imports only the standard library). Needs the network once; running it
    again changes nothing."""
    python = ceiling.SOLVER_PYTHON
    steps = ([sys.executable, "-m", "venv", str(python.parent.parent)],
             [str(python), "-m", "pip", "install", "--quiet", "--disable-pip-version-check", "ortools==" + ceiling.ORTOOLS],
             [str(python), "-c", "import ortools; print(ortools.__version__)"])
    for argv in steps:
        done = subprocess.run(argv, capture_output=True, text=True)
        if done.returncode != 0:
            raise ValueError("solver-setup: %s failed:\n%s" % (" ".join(argv[1:4]), done.stderr.strip()))
    print("OR-tools %s in %s" % (done.stdout.strip(), python.parent.parent))
    return 0


def cmd_edge(args):
    """Grow edge cases (see edge.py) and write each as cases/edge/<name>.json
    with the routing that proves it in cases/edge/proof/. About two minutes a
    case at the default limit; a case whose file is there is left alone."""
    import random

    import edge
    if not ceiling.solver_installed():
        print("growing edge cases needs the solver; install it once with: " + ceiling.SETUP)
        return 1
    binary = variants.build(variants.resolve("worktree"))
    dest = CASES_DIR / "edge"
    (dest / "proof").mkdir(parents=True, exist_ok=True)
    for i in range(args.count):
        name = "edge_%d_%d" % (args.seed, i)
        if (dest / (name + ".json")).exists():
            print("%s: already there" % name, flush=True)
            continue
        try:
            grown = edge.grow(binary, random.Random(args.seed * 100003 + i), name, args.seconds, args.longest)
        except edge.SolverFailed as e:          # no verdict at all: stop, do not write it down as "not known"
            print("%s: the solver failed, nothing written for it (%s)" % (name, e), flush=True)
            return 1
        if grown is None:
            print("%s: not one bridge of its list is proved routable; nothing written" % name, flush=True)
            continue
        case, found = grown
        with open(dest / "proof" / (name + ".json"), "w") as f:
            json.dump({"rule": "firmware", "closed": found["closed"]}, f)
            f.write("\n")
        cases.save_json(case, dest / (name + ".json"))
        print("%s: %s" % (name, case.notes), flush=True)
    return 0


def engines(a):
    """Who can answer for an arrangement, in words."""
    return "router and solver" if arrangement.blocks(a) is not None else "solver only"


NEXT_WORDS = {"not_routable": "not routable, proved", "unknown": "not known after %g s", "dropped": "the firmware drops a bridge",
              "unplaced": "it uses a node the arrangement does not have", "end": "none left in the list",
              "failed": "the firmware's harness crashed or timed out on it"}


def cmd_score(args, a):
    """Ask the exact solver the same netlists on `a` and on --against, and say
    what only one of them fits and what each needs. Exit 1 when an answer does
    not stand or there is no solver."""
    case_list = _cases_of(args)
    if case_list is None:
        return 2
    try:
        b = arrangement.load(args.against)
        arrangement.with_feed(b, a.feed)            # both are asked a's netlists, so b must have a's feed's ends
    except arrangement.Bad as e:
        print("\n".join(e.problems))
        return 1
    if not ceiling.solver_installed():
        print("scoring an arrangement needs the solver; install it once with: " + ceiling.SETUP)
        return 1
    v = variants.resolve(args.variant)
    shape = "firmware-shaped paths" if args.rule == "firmware" else "any copper"
    seconds, probe_seconds = args.seconds or 10.0, args.seconds or 20.0     # a list is grown as `lab.py edge` grows one
    print("score: %s against %s   engine: the exact solver, %s, %g s a case   probe feed %s the fabric on both"
          " (the netlists are the firmware's, as it makes them on V5's copper)"
          % (a.name, b.name, shape, seconds, "on" if a.feed else "off"))
    s = score.compare(v, case_list, a, b, rule=args.rule, seconds=seconds)
    width = max(13, len(a.name), len(b.name))
    line = "%-30s %-" + str(width) + "s %7s   %-" + str(width) + "s %7s"
    print(line % ("case", a.name, "fewest", b.name, "fewest"))
    fewest = lambda d: "" if d["verdict"] != "routable" else ("= %d" if d["fewest_proved"] else "<= %d") % d["crosspoints"]
    for r in s["rows"]:
        print(line % (r["case"][:30], r["a"]["verdict"].replace("_", " "), fewest(r["a"]),
                      r["b"]["verdict"].replace("_", " "), fewest(r["b"])))
    m = s["summary"]
    print("fits only on %s: %s" % (a.name, ", ".join(m["only_a"]) or "none"))
    print("fits only on %s: %s" % (b.name, ", ".join(m["only_b"]) or "none"))
    print("fewest crosspoints over the %d cases proved on both: %d on %s, %d on %s" % (
        m["proved_on_both"], m["fewest"]["a"], a.name, m["fewest"]["b"], b.name))
    for word, said in (("unknown", "not known in %g s" % seconds), ("unplaced", "cannot be placed (a node is missing)")):
        if m["a"][word] or m["b"][word]:
            print("%s: %d on %s, %d on %s" % (said, m["a"][word], a.name, m["b"][word], b.name))
    for r in s["rows"]:
        for side in "ab":
            if r[side].get("error"):
                print("  not answered  %s on %s: %s" % (r["case"], s[side], r[side]["error"]))
    if args.grow:
        import edge
        why = lambda d: NEXT_WORDS[d["next_is"]] % probe_seconds if d["next_is"] == "unknown" else NEXT_WORDS[d["next_is"]]
        how_far = lambda name, d: ("not one on %s" % name + (" (the first: %s)" % why(d) if d.get("next_is") else "")
                                   if not d["bridges"] else "%d bridges proved on %s (one more: %s)" % (d["bridges"], name, why(d)))
        try:
            for entry in score.lengths(v, a, b, lists=args.grow, seconds=probe_seconds, rule=args.rule):
                print("random list %d: %s, %s" % (entry["list"], how_far(a.name, entry["a"]), how_far(b.name, entry["b"])),
                      flush=True)
        except edge.SolverFailed as e:
            print("the solver failed while growing a list: %s" % e)
            return 1
    return 1 if m["errors"] else 0


def cmd_arrangement(args):
    """list: every arrangement. show NAME: its copper, pin by pin, against V5.
    check NAME: what is wrong with its file, if anything. score NAME: the
    exact solver on it and on another, over the same netlists."""
    if args.what == "list":
        for name in arrangement.names():
            try:
                a = arrangement.load(name)
                print("%-22s feed %-3s  %-17s  %s" % (name, "on" if a.feed else "off", engines(a), a.about))
            except arrangement.Bad as e:
                print("%-22s %d problems: python3 Routing/lab.py arrangement check %s" % (name, len(e.problems), name))
        return 0
    if not args.name:
        raise ValueError("arrangement %s needs a name (see: lab.py arrangement list)" % args.what)
    try:
        a = arrangement.load(args.name)
    except arrangement.Bad as e:
        print("\n".join(e.problems))
        return 1
    if args.what == "check":
        print("%s: good" % a.name)
        return 0
    if args.what == "score":
        return cmd_score(args, a)
    print("%s: %s" % (a.name, a.about))
    print("probe feed %s the fabric. A pin that is not on V5's wire is starred; a pin taken away is a dash."
          % ("on" if a.feed else "off"))
    for chip in a.CHIPS:
        for axis in "XY":
            shown = []
            for pin, wire in enumerate((a.X_NET if axis == "X" else a.Y_NET)[chip]):
                shown.append("-" if wire is None else wire + ("*" if (chip, axis, pin) in a.changed else ""))
            print("  %s.%s  %s " % (chip, axis, " ".join(shown)))
    base = arrangement.V5
    moved = sorted(n for n, w in a.NODE_NET.items() if base.NODE_NET.get(n) != w)
    gone = sorted(n for n in base.NODE_NET if n not in a.NODE_NET and n not in a.dropped)
    if moved:
        print("nodes added or moved: " + ", ".join("%s on %s" % (a.NODE_NAME.get(n, n), a.NODE_NET[n]) for n in moved))
    if gone:
        print("nodes removed: " + ", ".join(str(base.NODE_NAME.get(n, n)) for n in gone))
    if a.dropped:
        print("nodes dropped: " + ", ".join(str(base.NODE_NAME.get(n, n)) for n in a.dropped)
              + " (no pin left; a netlist that uses one cannot be placed)")
    why = arrangement.why_not_router(a)
    print("engine: the firmware's router and the exact solver" if why is None
          else "engine: the exact solver only. The firmware's router cannot route it: " + why)
    return 0


def signed(n):
    """A loss with its sign: +3, -1, 0."""
    return "%+d" % n if n else "0"


def cmd_rank(args):
    """Route the battery on an arrangement, then again without each lane,
    bounce row and hub lane, and print what the firmware's router loses
    without each, least first. The ranking is written under build/rank/."""
    import rank
    case_list = _cases_of(args)
    if case_list is None:
        return 2
    a = arrangement.load(args.arrangement)
    if args.needed and not ceiling.solver_installed():
        print("whether a wire is needed is asked of the solver; install it once with: " + ceiling.SETUP)
        return 1
    v = variants.resolve(args.variant)
    names = [w for w in (args.wires or "").split(",") if w] or None
    said = lambda done, of, item: print("%d/%d %s" % (done, of, item), file=sys.stderr, flush=True)
    # A ranking of some wires, or of one case, is printed (and written where --json says) but not kept: the file under
    # build/rank is the whole ranking of this router on this arrangement, and may hold hours of the solver's work.
    keep = (lambda r: r) if names or args.case else rank.save
    ranking = keep(rank.removal(v, case_list, a, wires=names, progress=said))        # kept even if the solver's part is stopped
    by_loss = lambda w: (w["loss"]["primaries"], w["loss"]["fully_routed"])
    order, more, columns = by_loss, lambda w: (), ()
    if args.needed:
        asked = [c for c in battery([c for c in args.needed_classes.split(",") if c]) if not args.case or c.name == args.case]
        ranking = keep(rank.needed(v, asked, a, ranking, seconds=args.seconds, progress=said))
    if "needed_cases" in ranking:                   # asked now, or kept from an earlier --needed of this variant and arrangement
        count = lambda w, key: len(w[key]) if key in w else 0
        order = lambda w: (count(w, "needed_by"), count(w, "unknown")) + by_loss(w)
        more = lambda w: (count(w, "needed_by"), w.get("not_needed", ""), count(w, "unknown")) if "needed_by" in w else ("", "", "")
        columns = ("needed by", "not needed", "unknown")
    if args.json:
        with open(args.json, "w") as f:
            json.dump(ranking, f)
    base = ranking["baseline"]
    print("arrangement: %s   engine: the firmware's router%s   variant: %s (%s)   %d cases" % (
        what(a), " for the loss, the exact solver (firmware-shaped paths, %g s a question) for what is needed, over %d cases"
        % (ranking["seconds"], ranking["needed_cases"]) if columns else "", v.name, v.hash[:12], ranking["cases"]))
    print("with every wire: %d primaries routed, %d cases fully routed, %d crosspoints" % (
        base["primaries"], base["fully_routed"], base["crosspoints"]))
    line = "%-8s %-28s %8s %10s %7s %8s %6s %7s" + " %10s" * len(columns)
    print(line % (("kind", "wire", "used in", "primaries", "cases", "xpoints", "worse", "better") + columns))
    for w in sorted(ranking["wires"], key=order):
        print(line % ((w["kind"], w["wire"], w["usage"]["cases"], signed(w["loss"]["primaries"]), signed(w["loss"]["fully_routed"]),
                       signed(w["loss"]["crosspoints"]), len(w["worse"]), len(w["better"])) + more(w)))
    print("lost without the wire: primaries routed, cases fully routed; xpoints: crosspoints more; worse, better: cases with"
          " fewer or more primaries routed")
    print("usage counts follow the router's search order and say nothing of need; a negative loss is the router doing better"
          " without the wire")
    if columns:
        print("needed: the exact solver proves the netlist cannot be routed without the wire (firmware-shaped paths). "
              "not needed: a routing without it exists. The router's loss is beside these, not instead of them.")
    print("not kept: a ranking of some wires or of one case does not take the place of the whole one (--json FILE writes it)"
          if names or args.case else "written to %s" % rank.path(v.hash, a.name))
    if ranking.get("set_aside"):
        print("the ranking that was there held the solver's columns for other copper or other netlists; it is set aside as %s"
              % ranking["set_aside"])
    return 0


def cmd_import_state(args):
    case = cases.import_state(args.file, args.name, args.cls)
    dest = CASES_DIR / args.cls
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / (args.name + ".json")
    cases.save_json(case, path)
    print("%s: %d bridges" % (path, len(case.bridges)))
    return 0


def main(argv):
    ap = argparse.ArgumentParser(prog="lab.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="route a battery and print the table")
    run.add_argument("--variant", default="worktree")
    run.add_argument("--baseline", help="a second variant; getting worse than it is an error")
    run.add_argument("--classes", default="dense,real", help="comma list of: " + ", ".join(CLASSES))
    run.add_argument("--case", help="only this case, with its b report")
    run.add_argument("--jobs", type=int)
    run.add_argument("--json", help="write every result to this file")
    run.add_argument("--ohms", type=float, default=OHMS, help="ohms per crosspoint for the worst-ohm column (%g)" % OHMS)
    run.add_argument("--arrangement", default="v5", help=ON_WHAT + " The router routes only V5 with pins taken away")
    run.set_defaults(fn=cmd_run)
    build = sub.add_parser("build", help="build the harness for a variant and print its path")
    build.add_argument("--variant", default="worktree")
    build.set_defaults(fn=cmd_build)
    srv = sub.add_parser("serve", help="open the page: run variants and look at the copper")
    srv.add_argument("--port", type=int, default=8765)
    srv.add_argument("--tree", action="append", metavar="DIR",
                     help="another checkout (a directory holding src/) the page may use as a variant; repeatable")
    srv.add_argument("--no-open", action="store_true", help="do not open a browser")
    srv.set_defaults(fn=cmd_serve)
    fid = sub.add_parser("fidelity", help="compare the harness against a board capture of the dense suite")
    fid.add_argument("capture_dir", help="a JL_ROUTING_SNAP_DIR capture, named board_<commit>")
    fid.add_argument("--variant", help="default: the commit in the directory's name")
    fid.set_defaults(fn=cmd_fidelity)
    imp = sub.add_parser("import-state", help="turn a firmware state document into a case")
    imp.add_argument("file")
    imp.add_argument("--name", required=True)
    imp.add_argument("--class", dest="cls", default="real", choices=CLASSES)
    imp.set_defaults(fn=cmd_import_state)
    sht = sub.add_parser("sheet", help="read the board's KiCad schematic for the page's KiCad sheet tab")
    sht.add_argument("schematic", nargs="?", help="a .kicad_sch (default: the V5 r7 sheet beside this repository)")
    sht.add_argument("--theme", help="a KiCad colour theme for the backdrop")
    sht.set_defaults(fn=cmd_sheet)
    exp = sub.add_parser("export", help="one battery run as a single HTML file that opens without the server")
    exp.add_argument("out", help="the .html to write")
    exp.add_argument("--variant", default="worktree")
    exp.add_argument("--baseline")
    exp.add_argument("--classes", default="example,dense,real,stress,beyond,edge", help="comma list of: " + ", ".join(CLASSES))
    exp.add_argument("--arrangement", default="v5", help="the copper to route on, one the firmware's router can route "
                     "(see `arrangement list`); the ranking kept for it travels too")
    exp.add_argument("--backdrop", metavar="NAME", help="carry the KiCad sheet too: its backdrop (10 MB) is written beside "
                     "the page under this file name and fetched when the sheet tab is opened")
    exp.set_defaults(fn=cmd_export)
    sub.add_parser("clean", help="delete the caches under build/ (results, variant trees, binaries)") \
        .set_defaults(fn=cmd_clean)
    sub.add_parser("solver-setup", help="install the exact solver (OR-tools) into build/solver-venv; needs the network once") \
        .set_defaults(fn=cmd_solver_setup)
    ceil = sub.add_parser("ceiling", help="ask the exact solver: can each netlist be routed at all, with how few crosspoints")
    ceil.add_argument("--variant", default="worktree")
    ceil.add_argument("--classes", default="dense,real", help="comma list of: " + ", ".join(CLASSES))
    ceil.add_argument("--case", help="only this case")
    ceil.add_argument("--rule", default="firmware", choices=("firmware", "copper"),
                      help="firmware: each bridge its own path of at most four crosspoints; copper: any copper")
    ceil.add_argument("--seconds", type=float, default=20.0, help="the solver's limit for one case (20)")
    ceil.add_argument("--arrangement", default="v5", help=ON_WHAT)
    ceil.set_defaults(fn=cmd_ceiling)
    edg = sub.add_parser("edge", help="grow random netlists to the longest the solver proves routable (cases/edge/)")
    edg.add_argument("--seed", type=int, default=1)
    edg.add_argument("--count", type=int, default=12, help="how many cases (12)")
    edg.add_argument("--seconds", type=float, default=20.0, help="the solver's limit for one probe (20)")
    edg.add_argument("--longest", type=int, default=80, help="bridges in the list a case is a prefix of (80)")
    edg.set_defaults(fn=cmd_edge)
    arr = sub.add_parser("arrangement", help="the crossbar arrangements under arrangements/: list, show, check, and score "
                                             "(the exact solver on one and on another, over the same netlists)")
    arr.add_argument("what", choices=("list", "show", "check", "score"))
    arr.add_argument("name", nargs="?", help="an arrangement's name, or the path of its .json")
    arr.add_argument("--against", default="v5", help="score: the other arrangement (v5)")
    arr.add_argument("--variant", default="worktree", help="score: the firmware whose netlists are asked (worktree)")
    arr.add_argument("--classes", default="dense,real,stress", help="score: comma list of: " + ", ".join(CLASSES))
    arr.add_argument("--case", help="score: only this case")
    arr.add_argument("--rule", default="firmware", choices=("firmware", "copper"),
                     help="score: firmware: each bridge its own path of at most four crosspoints; copper: any copper")
    arr.add_argument("--seconds", type=float, help="score: the solver's limit for one question (10 for a case, 20 for a "
                                                   "probe of --grow)")
    arr.add_argument("--grow", type=int, default=0, metavar="N",
                     help="score: also grow N of the edge class's random lists on both (about a minute and a half a list "
                          "an arrangement)")
    arr.set_defaults(fn=cmd_arrangement)
    rnk = sub.add_parser("rank", help="what the firmware's router loses without each lane, bounce row and hub lane")
    rnk.add_argument("--arrangement", default="v6_feed_off",
                     help=ON_WHAT + " The default has the probe feed off the fabric, as V6 will; v5 is the same ranking "
                                    "with the feed on it, as a V5 has it")
    rnk.add_argument("--variant", default="worktree")
    rnk.add_argument("--classes", default="dense,real,typical,stress,edge", help="comma list of: " + ", ".join(CLASSES))
    rnk.add_argument("--case", help="only this case")
    rnk.add_argument("--wires", help="comma list of wires to rank (every lane, bounce row and hub lane when not given)")
    rnk.add_argument("--json", help="write the ranking to this file as well")
    rnk.add_argument("--needed", action="store_true",
                     help="also ask the exact solver, case by case, whether the netlist can be routed without each wire at all")
    rnk.add_argument("--needed-classes", default="dense,real,typical,stress",
                     help="the classes whose netlists are asked (over an hour for these; a quarter of one for dense,real,stress)")
    rnk.add_argument("--seconds", type=float, default=5.0, help="the solver's limit for one question of --needed (5)")
    rnk.set_defaults(fn=cmd_rank)
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except variants.BuildError as e:
        print("the variant does not build:\n" + e.stderr, file=sys.stderr)
        return 3
    except (ValueError, OSError) as e:          # a bad argument or an unreadable file: usage, not a routing failure
        print("lab.py: %s" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
