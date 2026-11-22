# SPDX-License-Identifier: MIT
"""Edge cases: netlists grown to the longest prefix a solver proves routable.
The search is tested with a pretend harness and a pretend solver; the cases
that are committed are checked against the real harness, by the routing each
carries, with no solver at all."""
import contextlib
import dataclasses
import io
import json
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import arrangement
import cases
import ceiling
import edge
import generators
import lab
import runner
import variants


def pretend(verdict_of, takes=10 ** 6):
    """No harness, no solver. A 'result' holds the number of bridges; the firmware leaves one out of any prefix
    longer than `takes`; the verdict is verdict_of(the number)."""
    result = lambda binary, case, **kw: {"n": len(case.bridges), "rejected": [], "refused": [],
                                         "left_out": [[1, 2]] if len(case.bridges) > takes else []}
    answer = lambda r, *a, **kw: {"verdict": verdict_of(r["n"]), "closed": [["A", 0, 0, 6]], "error": None}
    return (mock.patch.object(runner, "run_case", side_effect=result), mock.patch.object(ceiling, "verdict", side_effect=answer))


def run(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = lab.main(argv)
    return code, out.getvalue()


class Edge(unittest.TestCase):
    def grown(self, verdict_of, longest=20, takes=10 ** 6):
        run, ask = pretend(verdict_of, takes)
        with run, ask:
            return edge.grow(None, random.Random(1), "edge_t", longest=longest)

    def test_bisection_keeps_the_longest_prefix_proved_routable(self):
        case, info = self.grown(lambda n: "routable" if n <= 7 else "not_routable")
        self.assertEqual((len(case.bridges), info["bridges"], info["next_is"], info["closed"]),
                         (7, 7, "not_routable", [["A", 0, 0, 6]]))
        self.assertEqual(case.notes, "proved routable with firmware-shaped paths (7 bridges); one more bridge: not routable, proved")

    def test_a_prefix_the_firmware_drops_a_bridge_of_is_not_an_edge_case(self):
        case, info = self.grown(lambda n: "routable", takes=9)
        self.assertEqual((len(case.bridges), info["next_is"]), (9, "dropped"))
        self.assertEqual((case.name, case.cls, case.must_route), ("edge_t", "edge", False))
        self.assertTrue(all(dup == -1 for _, _, dup in case.bridges))
        self.assertIn("the firmware drops a bridge", case.notes)

    def test_unknown_is_not_proof(self):
        case, info = self.grown(lambda n: "routable" if n <= 5 else "unknown")
        self.assertEqual((len(case.bridges), info["next_is"]), (5, "unknown"))
        self.assertIn("not known after 20 s", case.notes)
        case, info = self.grown(lambda n: "routable" if n <= 5 else "nothing")
        self.assertEqual((len(case.bridges), info["next_is"]), (5, "unknown"))

    def test_all_of_it_proved(self):
        case, info = self.grown(lambda n: "routable")
        self.assertEqual((len(case.bridges), info["next_is"]), (20, "end"))

    def test_nothing_proved_gives_nothing(self):
        self.assertIsNone(self.grown(lambda n: "unknown"))

    def test_it_asks_few_times(self):                                 # bisection, not one probe per bridge
        run, ask = pretend(lambda n: "routable" if n <= 33 else "unknown")
        with run, ask as asked:
            case, _ = edge.grow(None, random.Random(1), "edge_t", longest=80)
        self.assertEqual(len(case.bridges), 33)
        self.assertLessEqual(asked.call_count, 9)
        self.assertTrue(all(call.kwargs.get("fewest") is False for call in asked.call_args_list))    # only "is there one"

    def test_on_an_arrangement_the_netlist_has_its_feed_and_the_solver_its_copper(self):
        rails = arrangement.load("v6_rails_on_chips")
        run, ask = pretend(lambda n: "routable" if n <= 7 else "unknown")
        with run as ran, ask as asked:
            case, info = edge.grow(None, random.Random(1), "edge_t", longest=20, arrangement=rails)
            self.assertEqual({call.args[1].probe[0] for call in ran.call_args_list}, {0})          # no probe feed in any probe
            self.assertTrue(all(call.kwargs["arrangement"] is rails for call in asked.call_args_list))
            self.assertEqual((len(case.bridges), case.probe[0], info["bridges"]), (7, 0, 7))
            edge.grow(None, random.Random(1), "edge_t", longest=20)                               # and without one, as before
            self.assertEqual((ran.call_args.args[1].probe[0], asked.call_args.kwargs["arrangement"]), (1, None))
        self.assertEqual([(a, b) for a, b, _ in case.bridges], edge.draw(random.Random(1), longest=20)[:7])     # the same list

    def test_the_case_is_a_prefix_of_the_list_the_seed_draws(self):
        case, _ = self.grown(lambda n: "routable" if n <= 7 else "unknown")
        self.assertEqual([(a, b) for a, b, _ in case.bridges], edge.draw(random.Random(1), longest=20)[:7])

    def test_the_bridges_are_legal_and_every_prefix_is(self):
        pairs = edge.draw(random.Random(3), longest=80)
        self.assertEqual(len({frozenset(p) for p in pairs}), 80)                  # 80 bridges, none twice
        self.assertTrue(all(a != b for a, b in pairs))
        self.assertTrue(all(generators.legal(pairs[:k]) for k in range(1, 81)))
        self.assertEqual(pairs, edge.draw(random.Random(3), longest=80))          # the seed decides the list

    def test_the_command_writes_a_case_and_its_proof_and_skips_what_is_there(self):
        made = cases.Case("x", "edge", [(1, 8, -1)], notes="proved routable with firmware-shaped paths (1 bridges)")
        grow = lambda binary, rng, name, *a, **kw: (dataclasses.replace(made, name=name),
                                                    {"bridges": 1, "closed": [["A", 2, 1, 6]], "next_is": "unknown"})
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(lab, "CASES_DIR", Path(tmp)), \
                mock.patch.object(ceiling, "solver_installed", return_value=True), \
                mock.patch.object(edge, "grow", side_effect=grow) as grown:
            code, out = run(["edge", "--seed", "5", "--count", "2", "--seconds", "3"])
            self.assertEqual(code, 0, out)
            self.assertEqual(sorted(p.name for p in (Path(tmp) / "edge").glob("*.json")), ["edge_5_0.json", "edge_5_1.json"])
            self.assertEqual(cases.load_json(Path(tmp) / "edge" / "edge_5_1.json").name, "edge_5_1")
            self.assertEqual(json.loads((Path(tmp) / "edge" / "proof" / "edge_5_0.json").read_text()),
                             {"rule": "firmware", "closed": [["A", 2, 1, 6]]})
            self.assertEqual(grown.call_args.args[3], 3.0)                          # the limit asked for
            self.assertEqual(run(["edge", "--seed", "5", "--count", "2"])[0], 0)
            self.assertEqual(grown.call_count, 2)                                   # both were there: nothing grown again
            grown.side_effect = lambda *a, **kw: None                               # a list of which nothing is proved
            code, out = run(["edge", "--seed", "6", "--count", "1"])
            self.assertEqual(code, 0, out)
            self.assertEqual(len(list((Path(tmp) / "edge").glob("*.json"))), 2)

    def test_a_solver_that_fails_is_not_a_netlist_that_is_not_known(self):        # Review Focus 1 and 2
        harness, _ = pretend(lambda n: "routable")
        failing = lambda r, *a, **kw: ({"verdict": "routable", "closed": [["A", 0, 0, 6]], "error": None} if r["n"] <= 5 else
                                       {"verdict": "unknown", "closed": [], "error": "the solver exited with 3: boom"})
        with harness, mock.patch.object(ceiling, "verdict", side_effect=failing):
            with self.assertRaises(edge.SolverFailed) as cm:
                edge.grow(None, random.Random(1), "edge_t", longest=20)
        self.assertIn("the solver exited with 3: boom", str(cm.exception))

    def test_the_command_stops_with_exit_1_when_the_solver_fails(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(lab, "CASES_DIR", Path(tmp)), \
                mock.patch.object(ceiling, "solver_installed", return_value=True), \
                mock.patch.object(edge, "grow", side_effect=edge.SolverFailed("the solver exited with 3: boom")) as grown:
            code, out = run(["edge", "--seed", "5", "--count", "2"])
            self.assertEqual(code, 1, out)
            self.assertIn("the solver exited with 3: boom", out)
            self.assertEqual(grown.call_count, 1)                                   # it does not go on to the next case
            self.assertEqual(list((Path(tmp) / "edge").glob("*.json")), [])

    def test_the_command_without_the_solver_says_how_to_get_it(self):
        with mock.patch.object(ceiling, "SOLVER_PYTHON", Path("/nonexistent/python")):
            code, out = run(["edge", "--seed", "5", "--count", "1"])
        self.assertEqual(code, 1, out)
        self.assertIn("python3 tools/routing_lab/lab.py solver-setup", out)

    def test_committed_edge_cases_load_and_are_in_the_battery(self):
        found = lab.battery(["edge"])
        self.assertEqual(len(found), 12)
        self.assertTrue(all(c.cls == "edge" and "proved routable" in c.notes for c in found))
        self.assertEqual(lab.CLASSES[-1], "edge")

    def test_every_committed_edge_case_carries_a_routing_that_holds(self):        # no solver needed
        binary = variants.build(variants.resolve("worktree"))
        for c in lab.battery(["edge"]):
            result = runner.run_case(binary, c)
            self.assertEqual((result["rejected"], result["left_out"], result["refused"]), ([], [], []), c.name)
            proof = json.loads((lab.CASES_DIR / "edge" / "proof" / (c.name + ".json")).read_text())
            given = ceiling.problem(ceiling.painted(result))
            self.assertEqual(len(given["bridges"]), len(c.bridges) + 1, c.name)   # every bridge, and the probe feed
            self.assertEqual(ceiling.faults(given, proof["closed"], proof["rule"]), [], c.name)


if __name__ == "__main__":
    unittest.main()
