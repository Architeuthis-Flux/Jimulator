#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Routing lab: build the firmware's V5 router for the host, route a battery
of netlists with it, and judge the result against the schematic.

    lab.py run [--variant V] [--baseline V0] [--classes dense,real,...] [--case NAME] [--jobs N] [--json FILE]
    lab.py serve [--port 8765] [--tree DIR]... [--no-open]
    lab.py build [--variant V]
    lab.py fidelity CAPTURE_DIR [--variant V]
    lab.py import-state FILE.yaml --name NAME [--class real]

A variant is "worktree" (this checkout), a directory that holds src/ (another
checkout), or a git ref. See README.md.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import cases
import generators
import runner
import variants

LAB = Path(__file__).resolve().parent
CASES_DIR = LAB / "cases"
FIDELITY_DIR = LAB / "fidelity"
GENERATED = {"dense": cases.dense_cases, "typical": generators.typical, "fuzz": generators.fuzz,
             "stress": generators.stress, "beyond": generators.beyond}
CLASSES = ["dense", "real", "typical", "fuzz", "stress", "beyond"]


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
    """Every primary the firmware allowed is routed. A path its safety check
    refused is the firmware saying no, not the router failing."""
    m = result["metrics"]
    return (result["status"] in ("ok", "problems") and m["primaries"] > 0
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
        if b is None:
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
    return out


def exit_code(results, case_list, regression_lines):
    must = {c.name for c in case_list if c.must_route}
    for r in results:
        if r["status"] in ("crash", "timeout"):
            return 1
        if any(p.startswith(("SHORT", "STRAY")) for p in r["problems"]):
            return 1
        if r["case"] in must and r["problems"]:
            return 1
    return 1 if regression_lines else 0


def print_table(v, results, ohms=60.0):
    """One row per class. Primaries say whether everything routed; copies,
    xpoints and worst ohm are what tell two routers apart once it has."""
    print("variant: %s  (%s)   %g ohm per crosspoint" % (v.name, v.hash[:12], ohms))
    print("%-9s %6s %13s %12s %8s %9s %14s %10s %7s %8s %10s" % (
        "class", "cases", "fully routed", "primaries", "refused", "problems", "crash/timeout", "dead taps",
        "copies", "xpoints", "worst ohm"))
    order = []
    for r in results:
        if r["cls"] not in order:
            order.append(r["cls"])
    for cls in order:
        rs = [r for r in results if r["cls"] == cls]
        worst = [r["metrics"]["worst_r"] for r in rs if r["metrics"].get("worst_r") is not None]
        print("%-9s %6d %13d %12s %8d %9d %14d %10d %7d %8d %10d" % (
            cls, len(rs), sum(fully_routed(r) for r in rs),
            "%d/%d" % (sum(r["metrics"]["routed_primaries"] for r in rs), sum(r["metrics"]["primaries"] for r in rs)),
            sum(r["metrics"].get("refused", 0) for r in rs),
            sum(1 for r in rs if r["status"] == "problems"),
            sum(1 for r in rs if r["status"] in ("crash", "timeout")),
            sum(len(r["metrics"]["taps_dead"]) for r in rs),
            sum(r["metrics"]["routed_duplicates"] for r in rs),
            sum(r["metrics"]["crosspoints"] for r in rs),
            round(max(worst) * ohms) if worst else 0))
    for r in results:
        m = r["metrics"]
        if r["status"] in ("crash", "timeout"):
            print("  %-8s %s/%s: %s" % (r["status"], r["cls"], r["case"], (r["problems"] or [""])[0]))
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
    classes = [c for c in args.classes.split(",") if c]
    case_list = battery(classes)
    if args.case:
        case_list = [c for c in case_list if c.name == args.case]
        if not case_list:
            print("no case named %r in %s" % (args.case, ", ".join(classes)), file=sys.stderr)
            return 2
    v = variants.resolve(args.variant)
    results = runner.run_battery(v, case_list, jobs=args.jobs)
    print_table(v, results, args.ohms)
    if args.case:
        print_case(results[0])
    lines = []
    if args.baseline:
        base_v = variants.resolve(args.baseline)
        try:
            base = runner.run_battery(base_v, case_list, jobs=args.jobs)
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
            json.dump({"variant": {"name": v.name, "hash": v.hash}, "baseline": args.baseline,
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
    run.add_argument("--ohms", type=float, default=60.0, help="ohms per crosspoint for the worst-ohm column (60)")
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
