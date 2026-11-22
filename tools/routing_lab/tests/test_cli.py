# SPDX-License-Identifier: MIT
import contextlib
import io
import json
import os
import re
import tempfile
import unittest
from unittest import mock

import arrangement
import ceiling
import lab
import rank
import variants

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIL = os.path.join(os.path.dirname(os.path.dirname(LAB)), "test", "hil")


def run(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = lab.main(argv)
    return code, out.getvalue()


def row(name, **metrics):
    """The smallest result lab.regressions reads."""
    return {"case": name, "status": "ok", "problems": [], "metrics": {"primaries": 1, "routed_primaries": 1, **metrics}}


class Cli(unittest.TestCase):
    def test_run_dense_at_worktree_exits_zero(self):
        code, out = run(["run", "--classes", "dense"])
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"dense\s+21\s+20\s")           # 21 cases, 20 fully routed (the K overflow is not)
        self.assertIn("k_rows_overflow_metric", out)

    def test_run_prints_what_separates_routers(self):
        code, out = run(["run", "--classes", "dense"])
        header = [l for l in out.splitlines() if l.startswith("class")][0]
        for word in ("copies", "xpoints", "worst ohm", "missed"):
            self.assertIn(word, header)
        dense = [l for l in out.splitlines() if l.startswith("dense")][0].split()
        self.assertEqual(dense[header.split().index("missed") - 1], "0")     # "fully routed" is two words up there

        def worst(text):
            row = [l for l in text.splitlines() if l.startswith("dense")][0]
            return int(row.split()[-1])

        self.assertGreater(worst(out), 0)
        self.assertEqual(worst(run(["run", "--classes", "dense", "--ohms", "21"])[1]) * 2, worst(out))   # 42 by default
        self.assertIn("42 ohm per crosspoint", out)

    def test_battery_classes(self):
        self.assertEqual(len(lab.battery(["dense"])), 21)
        self.assertEqual({c.cls for c in lab.battery(["dense", "real", "stress"])}, {"dense", "real", "stress"})
        with self.assertRaises(ValueError):
            lab.battery(["nope"])

    def test_regressions(self):
        ok = {"case": "a", "status": "ok", "problems": [], "metrics": {"primaries": 2, "routed_primaries": 2}}
        worse = {**ok, "metrics": {"primaries": 2, "routed_primaries": 1}}
        self.assertEqual(lab.regressions([ok], [ok]), [])
        self.assertEqual(len(lab.regressions([ok], [worse])), 1)
        self.assertEqual(len(lab.regressions([ok], [{**ok, "status": "problems", "problems": ["SHORT x"]}])), 1)
        self.assertEqual(len(lab.regressions([ok], [{**ok, "status": "crash"}])), 1)
        # the same kind of problem as the baseline had is not a regression; a case only in one list is ignored
        short = {**ok, "status": "problems", "problems": ["SHORT: nets 6 7 share copper via AB0"]}
        self.assertEqual(lab.regressions([short], [{**short, "problems": ["SHORT: nets 6 9 share copper via AC0"]}]), [])
        self.assertEqual(lab.regressions([ok], [{**ok, "case": "b"}]), [])

    def test_fewer_routed_primaries_is_a_regression_even_when_the_baseline_was_not_complete(self):
        base = {"case": "a", "status": "ok", "problems": [], "metrics": {"primaries": 10, "routed_primaries": 8}}
        fewer = {**base, "metrics": {"primaries": 10, "routed_primaries": 7}}
        more = {**base, "metrics": {"primaries": 10, "routed_primaries": 9}}
        self.assertEqual(len(lab.regressions([base], [fewer])), 1)
        self.assertEqual(lab.regressions([base], [more]), [])

    def test_a_new_miss_is_a_regression(self):
        lines = lab.regressions([row("c", missed=0)], [row("c", missed=1)])
        self.assertTrue(any("where the copper had a path" in line for line in lines))
        self.assertEqual(lines, ["c: 1 unrouted where the copper had a path (baseline 0)"])
        self.assertEqual(lab.regressions([row("c", missed=1)], [row("c", missed=1)]), [])
        self.assertEqual(lab.regressions([row("c", missed=2)], [row("c", missed=1)]), [])

    def test_file_errors_are_usage_errors_not_routing_failures(self):
        code, out = run(["import-state", "/nonexistent/state.yaml", "--name", "x"])
        self.assertEqual(code, 2, out)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(lab, "CASES_DIR", lab.Path(tmp)):
            os.makedirs(os.path.join(tmp, "real"))
            with open(os.path.join(tmp, "real", "broken.json"), "w") as f:
                f.write('{"name": "broken"')
            code, out = run(["run", "--classes", "real"])
            self.assertEqual(code, 2, out)
            self.assertIn("broken.json", out)

    def test_a_baseline_that_does_not_build_is_named(self):
        real_build = variants.build

        def build(v, sanitize=True):
            if v.name.startswith("HEAD"):
                raise variants.BuildError("old.cpp:1: error: no")
            return real_build(v, sanitize)

        with mock.patch.object(variants, "build", side_effect=build):
            code, out = run(["run", "--classes", "dense", "--case", "chain_all_chips", "--baseline", "HEAD"])
        self.assertEqual(code, 3)
        self.assertIn("baseline", out)
        self.assertIn("old.cpp:1: error: no", out)

    def test_exit_1_on_a_short_or_a_crash(self):
        short = {"case": "a", "cls": "fuzz", "status": "problems", "problems": ["SHORT: x"], "notes": [],
                 "metrics": {"primaries": 1, "routed_primaries": 1, "taps_dead": []}}
        self.assertEqual(lab.exit_code([short], [lab.cases.Case("a", "fuzz", [(1, 2, -1)])], []), 1)
        crash = {**short, "status": "crash", "problems": []}
        self.assertEqual(lab.exit_code([crash], [lab.cases.Case("a", "fuzz", [(1, 2, -1)])], []), 1)
        unrouted = {**short, "problems": ["unrouted primary path 0: 1-2 (net 6)"]}
        self.assertEqual(lab.exit_code([unrouted], [lab.cases.Case("a", "fuzz", [(1, 2, -1)])], []), 0)
        self.assertEqual(lab.exit_code([unrouted], [lab.cases.Case("a", "fuzz", [(1, 2, -1)], must_route=True)], []), 1)
        self.assertEqual(lab.exit_code([], [], ["a: routed 1/2, baseline 2/2"]), 1)

    def test_broken_variant_exits_3(self):
        with mock.patch.object(variants, "build", side_effect=variants.BuildError("x.cpp:1: error: no")):
            code, out = run(["run", "--classes", "dense"])
        self.assertEqual(code, 3)
        self.assertIn("x.cpp:1: error: no", out)

    def test_baseline_run_and_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "r.json")
            code, out = run(["run", "--classes", "dense", "--baseline", "HEAD", "--json", path])
            self.assertEqual(code, 0, out)
            self.assertIn("no regressions", out)
            with open(path) as f:
                doc = json.load(f)
        self.assertEqual(len(doc["results"]), 21)
        self.assertEqual(doc["regressions"], [])
        self.assertEqual(doc["variant"]["name"], "worktree")

    def test_single_case_prints_its_report(self):
        code, out = run(["run", "--classes", "dense", "--case", "chain_all_chips"])
        self.assertEqual(code, 0, out)
        self.assertIn("Bridge Array", out)
        self.assertEqual(run(["run", "--classes", "dense", "--case", "no_such_case"])[0], 2)

    def test_import_state_writes_a_case(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(lab, "CASES_DIR", lab.Path(tmp)):
            code, out = run(["import-state", os.path.join(HIL, "slot3_snapshot_2026-08-26.yaml"), "--name", "s3"])
            self.assertEqual(code, 0, out)
            self.assertEqual(lab.cases.load_json(os.path.join(tmp, "real", "s3.json")).name, "s3")

    @unittest.skipUnless(ceiling.solver_installed(), "the solver is not installed: python3 tools/routing_lab/lab.py solver-setup")
    def test_ceiling_prints_the_verdict_and_the_fewest(self):
        code, out = run(["ceiling", "--case", "same_chip_pairs"])
        self.assertEqual(code, 0, out)
        line = [l for l in out.splitlines() if l.startswith("same_chip_pairs")][0]
        self.assertIn("routable", line)
        self.assertIn("= 16", line)
        self.assertIn("provably routable: 1 of 1; the router routes 1 of those in full", out)
        self.assertIn("the router uses 0 more crosspoints than the fewest over the 1 cases where both are known", out)

    def test_ceiling_without_the_solver_says_how_to_get_it(self):
        with mock.patch.object(ceiling, "SOLVER_PYTHON", lab.Path("/nonexistent/python")):
            code, out = run(["ceiling", "--case", "same_chip_pairs"])
        self.assertEqual(code, 1, out)
        self.assertIn("python3 tools/routing_lab/lab.py solver-setup", out)

    def test_ceiling_exits_1_on_an_answer_the_lab_does_not_stand_behind(self):
        wrong = {"verdict": "unknown", "fewest_proved": False, "crosspoints": None, "router_crosspoints": 16, "closed": [],
                 "seconds": 0.1, "error": "the solver says this cannot be routed, yet the router routed it: the model is wrong"}
        with mock.patch.object(ceiling, "solver_installed", return_value=True), \
                mock.patch.object(ceiling, "verdict", return_value=wrong) as asked:
            code, out = run(["ceiling", "--case", "same_chip_pairs", "--rule", "copper", "--seconds", "3"])
        self.assertEqual(code, 1, out)
        self.assertIn("the model is wrong", out)
        self.assertEqual(asked.call_args.args[1:], ("copper", 3.0))
        self.assertEqual(run(["ceiling", "--case", "no_such_case"])[0], 2)

    def test_arrangement_list_show_and_check(self):
        code, out = run(["arrangement", "list"])
        self.assertEqual(code, 0, out)
        line = {l.split()[0]: l for l in out.splitlines() if l.strip()}
        self.assertIn("router and solver", line["v5"])
        self.assertIn("feed on", line["v5"])
        self.assertIn("router and solver", line["v6_feed_off"])
        self.assertIn("feed off", line["v6_feed_off"])
        self.assertIn("solver only", line["v6_rails_on_chips"])
        code, out = run(["arrangement", "show", "v6_rails_on_chips"])
        self.assertEqual((code, out.count("*")), (0, 24), out)            # every changed pin is marked, and nothing else
        self.assertTrue(out.rstrip().endswith(arrangement.why_not_router(arrangement.load("v6_rails_on_chips"))), out)
        self.assertIn("TOP_RAIL*", out)
        code, out = run(["arrangement", "show", "v6_feed_off"])
        self.assertEqual((code, out.count("*")), (0, 0), out)
        self.assertIn("the firmware's router and the exact solver", out)
        self.assertEqual(run(["arrangement", "check", "v6_feed_off"]), (0, "v6_feed_off: good\n"))
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "mine.json")
            with open(path, "w") as f:
                json.dump({"base": "v5", "feed": False, "pins": {"A.X16": "x", "K.X2": None}, "remove": ["KL"]}, f)
            code, out = run(["arrangement", "check", path])
            self.assertEqual(code, 1, out)
            self.assertIn("A.X16", out)
            with open(path, "w") as f:
                json.dump({"base": "v5", "feed": False, "pins": {"K.X2": None}, "remove": ["KL"]}, f)
            code, out = run(["arrangement", "show", path])
            self.assertEqual(code, 0, out)
            self.assertIn("dropped: BUFFER_IN", out)                      # the node whose one pin was freed
            self.assertEqual(out.count(" - "), 3, out)                    # K.X2 and both ends of KL shown as taken
        code, out = run(["arrangement", "check", "no_such_arrangement"])
        self.assertEqual(code, 1, out)
        self.assertIn("no_such_arrangement", out)

    def test_run_on_an_arrangement_says_which_and_who_routed(self):
        code, out = run(["run", "--classes", "dense", "--arrangement", "v6_feed_off"])
        self.assertEqual(code, 0, out)
        first = out.splitlines()[0]
        for words in ("arrangement: v6_feed_off", "probe feed off", "the firmware's router"):
            self.assertIn(words, first)
        self.assertRegex(out, r"dense\s+21\s+21\s")            # with the feed off the K overflow routes too
        self.assertIn("arrangement: v5 (V5, no pin taken away, probe feed on)", run(["run", "--classes", "dense"])[1].splitlines()[0])
        code, out = run(["run", "--classes", "dense", "--arrangement", "v6_rails_on_chips"])
        self.assertEqual(code, 2, out)
        self.assertIn("arrangement score v6_rails_on_chips", out)
        self.assertEqual(run(["run", "--classes", "dense", "--arrangement", "no_such_arrangement"])[0], 2)

    @unittest.skipUnless(ceiling.solver_installed(), "the solver is not installed: python3 tools/routing_lab/lab.py solver-setup")
    def test_ceiling_on_an_arrangement_the_router_cannot_route(self):
        code, out = run(["ceiling", "--case", "rail_stacking_light", "--arrangement", "v6_rails_on_chips"])
        self.assertEqual(code, 0, out)
        first = out.splitlines()[0]
        for words in ("arrangement: v6_rails_on_chips", "probe feed off", "the exact solver, firmware-shaped paths"):
            self.assertIn(words, first)
        line = [l for l in out.splitlines() if l.startswith("rail_stacking_light")][0].split()
        self.assertEqual(line[1:3], ["-", "-"])                 # the router routed another fabric: its columns say nothing
        self.assertEqual(line[-2:], ["=", "6"])
        code, out = run(["ceiling", "--case", "rail_stacking_light", "--arrangement", "v6_feed_off"])
        line = [l for l in out.splitlines() if l.startswith("rail_stacking_light")][0].split()
        self.assertEqual((code, line[-2:]), (0, ["=", "10"]), out)
        self.assertNotEqual(line[1], "-")                       # here the router ran on the arrangement itself

    @unittest.skipUnless(ceiling.solver_installed(), "the solver is not installed: python3 tools/routing_lab/lab.py solver-setup")
    def test_arrangement_score_asks_the_solver_on_both(self):
        code, out = run(["arrangement", "score", "v6_rails_on_chips", "--case", "rail_stacking_light"])
        self.assertEqual(code, 0, out)
        first = out.splitlines()[0]
        for words in ("v6_rails_on_chips", "v5", "the exact solver", "firmware-shaped paths", "probe feed off"):
            self.assertIn(words, first)
        line = [l for l in out.splitlines() if l.startswith("rail_stacking_light")][0]
        self.assertRegex(line, r"routable\s+= 6\s+routable\s+= 10")
        self.assertIn("fewest crosspoints over the 1 cases proved on both: 6 on v6_rails_on_chips, 10 on v5", out)
        self.assertIn("fits only on v6_rails_on_chips: none", out)
        self.assertEqual(run(["arrangement", "score", "v6_rails_on_chips", "--case", "no_such_case"])[0], 2)
        self.assertEqual(run(["arrangement", "score", "v6_rails_on_chips", "--against", "no_such"])[0], 1)

    def test_arrangement_score_prints_the_lengths_and_exits_1_on_an_error(self):
        table = {"a": {"verdict": "routable", "crosspoints": 6, "fewest_proved": True, "error": None},
                 "b": {"verdict": "unknown", "crosspoints": None, "fewest_proved": False, "error": "the solver died"}}
        summary = {"cases": 1, "a": {"routable": 1, "not_routable": 0, "unknown": 0, "unplaced": 0},
                   "b": {"routable": 0, "not_routable": 0, "unknown": 1, "unplaced": 0}, "only_a": [], "only_b": [],
                   "proved_on_both": 0, "fewest": {"a": 0, "b": 0}, "errors": ["c"]}
        said = {"a": "v6_feed_off", "b": "v5", "feed": False, "rule": "firmware", "seconds": 3.0, "engine": "solver",
                "rows": [dict(table, case="c", cls="x")], "summary": summary}
        grown = [{"list": 0, "a": {"bridges": 67, "next_is": "unknown"}, "b": {"bridges": 0, "next_is": None}},
                 {"list": 1, "a": {"bridges": 18, "next_is": "unplaced"}, "b": {"bridges": 54, "next_is": "not_routable"}},
                 {"list": 2, "a": {"bridges": 0, "next_is": "unplaced"}, "b": {"bridges": 0, "next_is": "not_routable"}}]
        with mock.patch.object(ceiling, "solver_installed", return_value=True), \
                mock.patch.object(lab.score, "compare", return_value=said) as compared, \
                mock.patch.object(lab.score, "lengths", return_value=grown) as lengths:
            code, out = run(["arrangement", "score", "v6_feed_off", "--seconds", "3", "--rule", "copper", "--grow", "1"])
        self.assertEqual(code, 1, out)                                  # an answer that does not stand
        self.assertIn("not answered  c", out)
        self.assertIn("random list 0: 67 bridges proved on v6_feed_off (one more: not known after 3 s), "
                      "not one on v5", out)
        self.assertEqual((compared.call_args.args[2].name, compared.call_args.args[3].name), ("v6_feed_off", "v5"))
        self.assertEqual((compared.call_args.kwargs["rule"], compared.call_args.kwargs["seconds"]), ("copper", 3.0))
        self.assertEqual((lengths.call_args.kwargs["lists"], lengths.call_args.kwargs["seconds"]), (1, 3.0))
        self.assertEqual(lengths.call_args.kwargs["rule"], "copper")    # the lists grow under the rule the heading names
        self.assertIn("random list 1: 18 bridges proved on v6_feed_off (one more: it uses a node the arrangement does not have), "
                      "54 bridges proved on v5 (one more: not routable, proved)", out)
        self.assertIn("random list 2: not one on v6_feed_off (the first: it uses a node the arrangement does not have), "
                      "not one on v5 (the first: not routable, proved)", out)
        with mock.patch.object(ceiling, "solver_installed", return_value=True), \
                mock.patch.object(lab.score, "compare", return_value=dict(said, seconds=10.0)) as compared, \
                mock.patch.object(lab.score, "lengths", return_value=grown) as lengths:
            code, out = run(["arrangement", "score", "v6_feed_off", "--grow", "1"])
        # with no limit named: 10 s a case, and 20 s a probe for the lists, as `lab.py edge` grows them
        self.assertEqual((compared.call_args.kwargs["seconds"], lengths.call_args.kwargs["seconds"]), (10.0, 20.0))
        self.assertIn("(one more: not known after 20 s)", out)
        with mock.patch.object(ceiling, "SOLVER_PYTHON", lab.Path("/nonexistent/python")):
            code, out = run(["arrangement", "score", "v6_feed_off"])
        self.assertEqual(code, 1, out)
        self.assertIn("python3 tools/routing_lab/lab.py solver-setup", out)
        # the other side is asked with the first's feed: copper with no end for the feed is refused, not scored (verification)
        with tempfile.TemporaryDirectory() as tmp:
            no_dac0 = os.path.join(tmp, "no_dac0.json")
            with open(no_dac0, "w") as f:
                json.dump({"base": "v5", "feed": False, "pins": {"K.X7": None}}, f)
            with mock.patch.object(ceiling, "solver_installed", return_value=True), \
                    mock.patch.object(lab.runner, "run_battery", side_effect=AssertionError("ran")):
                code, out = run(["arrangement", "score", "v5", "--against", no_dac0])
        self.assertEqual(code, 1, out)
        self.assertIn("DAC0", out)

    def test_rank_prints_what_the_router_loses_and_writes_it(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(rank, "DIR", lab.Path(tmp) / "rank"):
            copy = os.path.join(tmp, "copy.json")
            code, out = run(["rank", "--classes", "dense", "--wires", "KL,AK", "--json", copy])
            self.assertEqual(code, 0, out)
            heading = [l for l in out.splitlines() if l.startswith("arrangement:")][0]
            for words in ("v6_feed_off", "probe feed off", "the firmware's router", "21 cases"):
                self.assertIn(words, heading)
            lines = [l for l in out.splitlines() if l.startswith(("hub ", "sf lane "))]
            self.assertEqual(sorted(l.split()[-7] for l in lines), ["AK", "KL"], out)         # two wire lines
            self.assertTrue(all(re.search(r"\s(0|[+-]\d+)\s", l) for l in lines), lines)   # the loss carries its sign
            self.assertIn("usage counts follow the router's search order and say nothing of need; "
                          "a negative loss is the router doing better without the wire", out)
            self.assertIn("1/2 KL", out)                                # progress, a line a wire
            # some wires only: printed, and written where --json says, but not kept as the ranking (final review, 2)
            self.assertEqual(list((lab.Path(tmp) / "rank").glob("*.json")), [])
            self.assertIn("not kept", out)
            with open(copy) as g:
                doc = json.load(g)
            self.assertEqual((doc["arrangement"], doc["feed"], doc["engine"], [w["wire"] for w in doc["wires"]]),
                             ("v6_feed_off", False, "router", ["KL", "AK"]))
            self.assertEqual(run(["rank", "--classes", "dense", "--wires", "GND"])[0], 2)       # a node's wire is not ranked
            code, out = run(["rank", "--classes", "dense", "--wires", "KL", "--arrangement", "v6_rails_on_chips"])
            self.assertEqual(code, 2, out)
            self.assertIn("arrangement score v6_rails_on_chips", out)   # the router cannot route it; the solver's command is named

    def test_a_narrowed_ranking_leaves_the_kept_one_alone(self):            # final review, 2
        def removal(v, case_list, a, wires=None, progress=None):
            names = wires or ["KL", "AK", "IJ"]
            entry = lambda n: {"wire": n, "kind": "hub", "pins": [], "usage": {"cases": 1, "primary": 1, "duplicate": 0},
                               "loss": {"primaries": 1, "fully_routed": 0, "crosspoints": 0, "worst_r": None}, "by_class": {},
                               "worse": [], "better": [], "used_after": 0}
            return {"arrangement": a.name, "feed": a.feed, "engine": "router", "variant": {"name": v.name, "hash": v.hash},
                    "fabric": rank.fabric_of(a), "cases": len(case_list), "wires": [entry(n) for n in names],
                    "baseline": {"primaries": 9, "fully_routed": 3, "crosspoints": 30, "worst_r": None}}

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(rank, "DIR", lab.Path(tmp) / "rank"), \
                mock.patch.object(rank, "removal", side_effect=removal):
            v = variants.resolve("worktree")                            # solver columns of other copper already there
            rank.save({"arrangement": "v6_feed_off", "variant": {"name": "w", "hash": v.hash}, "fabric": "other",
                       "engine": "router and solver", "rule": "firmware", "seconds": 5.0, "needed_cases": 9, "wires": []})
            code, out = run(["rank"])                                   # every wire, the default classes: this one is kept
            self.assertEqual(code, 0, out)
            self.assertIn("set aside", out)                             # and the old proof is not lost: it is set aside, and said so
            files = [p for p in (lab.Path(tmp) / "rank").glob("*.json") if "set-aside" not in p.name]
            self.assertEqual(len(files), 1)
            self.assertRegex(files[0].name, r"^[0-9a-f]{64}_v6_feed_off\.json$")
            kept = files[0].read_text()
            self.assertEqual((json.loads(kept)["cases"], len(json.loads(kept)["wires"])), (256, 3))
            self.assertIn("written to", out)
            for narrowed in (["--wires", "KL"], ["--case", "same_chip_pairs"], ["--wires", "KL", "--classes", "dense"]):
                code, out = run(["rank"] + narrowed)
                self.assertEqual(code, 0, out)
                self.assertEqual(files[0].read_text(), kept, narrowed)
                self.assertIn("not kept", out)
                self.assertNotIn("written to", out)

    def test_rank_needed_puts_the_proof_beside_the_loss(self):
        def needed(v, case_list, a, ranking, rule="firmware", seconds=5.0, progress=None):
            progress(1, 1, case_list[0].name)
            by = {"KL": ([], 21, []), "AK": (["k_rows_overflow_metric", "k_rows_all_eight"], 19, []), "IJ": ([], 20, ["nano_dense_metric"])}
            return dict(ranking, engine="router and solver", rule=rule, seconds=seconds, needed_cases=len(case_list), wires=[
                dict(w, needed_by=by[w["wire"]][0], not_needed=by[w["wire"]][1], unknown=by[w["wire"]][2]) for w in ranking["wires"]])

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(rank, "DIR", lab.Path(tmp) / "rank"), \
                mock.patch.object(ceiling, "solver_installed", return_value=True), \
                mock.patch.object(rank, "needed", side_effect=needed) as asked:
            copy = os.path.join(tmp, "copy.json")
            code, out = run(["rank", "--classes", "dense", "--wires", "AK,IJ,KL", "--needed", "--needed-classes", "dense,real",
                             "--seconds", "7", "--json", copy])
            self.assertEqual(code, 0, out)
            self.assertEqual((len(asked.call_args.args[1]), asked.call_args.kwargs["seconds"]), (23, 7.0))     # dense and real
            self.assertEqual(asked.call_args.args[2].name, "v6_feed_off")
            header = [l for l in out.splitlines() if l.startswith("kind")][0]
            for column in ("needed by", "not needed", "unknown"):
                self.assertIn(column, header)
            order = [l.split()[1 if l.startswith("hub") else 2] for l in out.splitlines() if l.startswith(("hub ", "sf lane "))]
            self.assertEqual(order, ["KL", "IJ", "AK"])                 # nothing needs it first, then an unknown, then needed
            self.assertIn("needed: the exact solver proves the netlist cannot be routed without the wire (firmware-shaped paths). "
                          "not needed: a routing without it exists. The router's loss is beside these, not instead of them.", out)
            self.assertIn("1/1 same_chip_pairs", out)
            with open(copy) as f:
                doc = json.load(f)
            self.assertEqual((doc["engine"], doc["needed_cases"], doc["wires"][0]["needed_by"]),
                             ("router and solver", 23, ["k_rows_overflow_metric", "k_rows_all_eight"]))
        with mock.patch.object(ceiling, "SOLVER_PYTHON", lab.Path("/nonexistent/python")), \
                mock.patch.object(rank, "removal", side_effect=AssertionError("ranked before saying the solver is missing")):
            code, out = run(["rank", "--classes", "dense", "--wires", "KL", "--needed"])
        self.assertEqual(code, 1, out)
        self.assertIn("python3 tools/routing_lab/lab.py solver-setup", out)

    def test_build_prints_the_binary(self):
        code, out = run(["build"])
        self.assertEqual(code, 0)
        self.assertTrue(os.access(out.strip().splitlines()[-1], os.X_OK), out)


if __name__ == "__main__":
    unittest.main()
