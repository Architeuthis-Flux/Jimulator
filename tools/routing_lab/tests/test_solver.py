# SPDX-License-Identifier: MIT
"""The exact search: what the solver is given, what the lab does when it is
missing or misbehaves, and, where OR-tools is installed, its answers on
fabrics small enough to check on paper."""
import contextlib
import io
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import ceiling
import lab
import runner
import variants
from tests.test_ceiling import TINY, dense, tiny_paint

NEEDS_SOLVER = "the solver is not installed: python3 tools/routing_lab/lab.py solver-setup"
NEW = ROUTED_RESULT = None                          # today's harness, and a case it routes in full
CRASHED_RESULT = {"case": "c", "cls": "x", "status": "crash", "problems": [], "notes": [], "b": ""}


def setUpModule():
    global NEW, ROUTED_RESULT
    NEW = variants.build(variants.resolve("worktree"))
    ROUTED_RESULT = runner.run_case(NEW, dense("same_chip_pairs"))


ONE_LANE = types.SimpleNamespace(**{**vars(TINY), "X_NET": {"A": ["L0"], "B": ["L0"]}})
CHAIN = types.SimpleNamespace(CHIPS="ABCD", X_NET={"A": ["AB"], "B": ["AB", "BC"], "C": ["BC", "CD"], "D": ["CD"]},
                              Y_NET={"A": ["1"], "B": ["bB"], "C": ["bC"], "D": ["4"]}, NODE_NET={1: "1", 4: "4"})


def unrouted(fabric, bridges):
    return tiny_paint([(a, b, net, "unrouted") for a, b, net in bridges], fabric=fabric)


def solve(fabric, bridges, rule):
    return ceiling.ask(ceiling.problem(unrouted(fabric, bridges), ceiling.graph(fabric)), rule, seconds=10)


PROBLEM = ceiling.problem(unrouted(TINY, [(1, 3, 6), (2, 4, 7)]), ceiling.graph(TINY))


@contextlib.contextmanager
def fake_solver(script, with_ortools=True):
    """ceiling.SOLVER_PYTHON as an executable that runs `script` whatever its arguments, in something
    laid out as the solver's environment is: bin/python, and (unless told not to) a package named ortools."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "bin" / "python"
        path.parent.mkdir()
        path.write_text("#!%s\n%s\n" % (sys.executable, script))
        path.chmod(0o755)
        if with_ortools:
            (Path(tmp) / "lib" / "python3.13" / "site-packages" / "ortools").mkdir(parents=True)
        with mock.patch.object(ceiling, "SOLVER_PYTHON", path):
            yield


class Problem(unittest.TestCase):
    def test_problem_of_a_paint(self):
        p = ceiling.problem(tiny_paint([(1, 3, 6, "unrouted"), (2, 4, 7, "routed"), (1, 2, 8, "refused")]), ceiling.graph(TINY))
        self.assertEqual(p["bridges"], [["1", "3", 6], ["2", "4", 7]])
        self.assertEqual(p["terminals"], {"1": 6, "3": 6, "2": 7, "4": 7})
        self.assertEqual(len(p["crosspoints"]), 12)                  # 2 lanes x 3 Y wires x 2 chips: all offered
        self.assertIn(["A", 1, 2, "L1", "bA"], p["crosspoints"])     # chip, x, y, the X wire, the Y wire

    def test_a_node_in_no_net_is_not_offered(self):                  # Review Focus 5
        p = ceiling.problem(tiny_paint([(1, 3, 6, "unrouted")]), ceiling.graph(TINY))
        self.assertFalse([c for c in p["crosspoints"] if "2" in c or "4" in c])
        self.assertEqual(len(p["crosspoints"]), 8)

    def test_a_crosspoint_that_would_join_two_nets_terminals_is_not_offered(self):
        direct = types.SimpleNamespace(CHIPS="A", X_NET={"A": ["5", "6"]}, Y_NET={"A": ["1", "2"]},
                                       NODE_NET={1: "1", 2: "2", 5: "5", 6: "6"})       # every wire is a node
        p = ceiling.problem(unrouted(direct, [(1, 5, 6), (2, 6, 7)]), ceiling.graph(direct))
        self.assertEqual(p["crosspoints"], [["A", 0, 0, "5", "1"], ["A", 1, 1, "6", "2"]])   # not 5-2, not 6-1

    def test_nothing_to_route(self):                                 # Review Focus 3
        self.assertIsNone(ceiling.problem(tiny_paint([(1, 3, 6, "refused")]), ceiling.graph(TINY)))
        self.assertIsNone(ceiling.problem(tiny_paint([]), ceiling.graph(TINY)))

    def test_two_nodes_on_one_wire_are_not_a_bridge_to_route(self):  # Review Focus 4
        same = types.SimpleNamespace(**{**vars(TINY), "NODE_NET": {1: "1", 9: "1", 3: "3"}})
        p = ceiling.problem(tiny_paint([(1, 9, 6, "unrouted"), (1, 3, 6, "unrouted")], fabric=same), ceiling.graph(same))
        self.assertEqual(p["bridges"], [["1", "3", 6]])
        self.assertIsNone(ceiling.problem(tiny_paint([(1, 9, 6, "unrouted")], fabric=same), ceiling.graph(same)))


class Asking(unittest.TestCase):                                     # Review Focus 1
    def test_no_environment_says_how_to_get_one(self):
        with mock.patch.object(ceiling, "SOLVER_PYTHON", Path("/nonexistent/python")):
            self.assertFalse(ceiling.solver_installed())
            with self.assertRaises(ceiling.SolverMissing) as cm:
                ceiling.ask(PROBLEM, "copper")
        self.assertTrue(str(cm.exception).endswith("python3 tools/routing_lab/lab.py solver-setup"))
        self.assertIsInstance(cm.exception, ValueError)

    def test_an_environment_without_the_solver_in_it_is_not_installed(self):
        # what a solver-setup that could not reach the network leaves behind: a python, and nothing to import
        with fake_solver("import sys; sys.exit(1)", with_ortools=False):
            self.assertFalse(ceiling.solver_installed())
            with self.assertRaises(ceiling.SolverMissing):
                ceiling.ask(PROBLEM, "copper")
        with fake_solver("import sys; sys.exit(1)"):
            self.assertTrue(ceiling.solver_installed())

    def test_a_routing_that_is_not_a_routing_is_unknown(self):       # rubbish that parses is still rubbish
        for closed in ([[1]], [["A", 0]], "everything", [["A", 0, 0, 6], None], [["A", "0", 0, 6]], None):
            script = "import json; print(json.dumps({'verdict': 'routable', 'fewest_proved': True, 'closed': %r}))" % (closed,)
            with fake_solver(script):
                a = ceiling.ask(PROBLEM, "copper")
            self.assertEqual((a["verdict"], a["closed"]), ("unknown", []), closed)
            self.assertIn("cannot be read", a["error"], closed)

    def test_a_solver_that_dies_or_prints_rubbish_is_unknown(self):
        for script in ("import sys; sys.exit(3)", "print('not json')", "print('{\"verdict\": \"maybe\"}')",
                       "import time; time.sleep(60)"):
            with fake_solver(script), mock.patch.object(ceiling, "GRACE", 0.5):     # the sleeper is given up on in 0.7 s
                a = ceiling.ask(PROBLEM, "copper", seconds=0.2)
            self.assertEqual(a["verdict"], "unknown", script)
            self.assertTrue(a["error"], script)

    def test_the_solver_gets_the_problem_with_the_rule_and_the_limits(self):
        echo = "import json, sys; p = json.load(sys.stdin); print(json.dumps({'verdict': 'unknown', 'got': p}))"
        with fake_solver(echo):
            got = ceiling.ask(PROBLEM, "firmware", seconds=3, fewest=False)["got"]
        self.assertEqual((got["rule"], got["seconds"], got["fewest"]), ("firmware", 3, False))
        self.assertEqual(got["bridges"], PROBLEM["bridges"])

    def test_setup_makes_the_environment_and_installs_the_pinned_solver(self):
        ran = []

        def run(argv, **kw):
            ran.append([str(a) for a in argv])
            return types.SimpleNamespace(returncode=0, stdout="9.15.6755\n", stderr="")

        out = io.StringIO()
        with mock.patch.object(lab.subprocess, "run", side_effect=run), contextlib.redirect_stdout(out):
            self.assertEqual(lab.main(["solver-setup"]), 0)
        venv = str(ceiling.SOLVER_PYTHON.parent.parent)
        self.assertEqual(ran[0][1:], ["-m", "venv", venv])
        self.assertEqual(ran[1][:1] + ran[1][-1:], [str(ceiling.SOLVER_PYTHON), "ortools==9.15.6755"])
        self.assertIn("9.15.6755", out.getvalue())


@unittest.skipUnless(ceiling.solver_installed(), NEEDS_SOLVER)
class Copper(unittest.TestCase):
    def test_two_bridges_two_lanes(self):
        a = solve(TINY, [(1, 3, 6), (2, 4, 7)], "copper")
        self.assertEqual((a["verdict"], a["fewest_proved"], len(a["closed"])), ("routable", True, 4))

    def test_two_bridges_one_lane_cannot_be_routed(self):
        self.assertEqual(solve(ONE_LANE, [(1, 3, 6), (2, 4, 7)], "copper")["verdict"], "not_routable")

    def test_a_net_is_a_tree_of_any_length(self):
        a = solve(CHAIN, [(1, 4, 6)], "copper")
        self.assertEqual((a["verdict"], len(a["closed"])), ("routable", 6))

    def test_three_nodes_share_copper(self):                         # 1-3 and 1-4 in one net: lane L0 reaches both
        a = solve(TINY, [(1, 3, 6), (1, 4, 6)], "copper")
        self.assertEqual(len(a["closed"]), 3)

    def test_a_malformed_problem_is_exit_2(self):
        p = subprocess.run([str(ceiling.SOLVER_PYTHON), str(ceiling.SOLVE_PY)], input="{}", capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertTrue(p.stderr.strip())

    def test_stopping_at_the_first_routing(self):
        a = ceiling.ask(ceiling.problem(unrouted(TINY, [(1, 3, 6), (2, 4, 7)]), ceiling.graph(TINY)), "copper", fewest=False)
        self.assertEqual((a["verdict"], a["fewest_proved"]), ("routable", False))

    def test_the_solver_writes_nothing_but_its_answer(self):
        import json
        p = subprocess.run([str(ceiling.SOLVER_PYTHON), str(ceiling.SOLVE_PY)], capture_output=True, text=True,
                           input=json.dumps(dict(PROBLEM, rule="copper", seconds=5)))
        self.assertEqual((p.returncode, p.stderr), (0, ""))          # no warnings on the way
        self.assertEqual(json.loads(p.stdout)["verdict"], "routable")


@unittest.skipUnless(ceiling.solver_installed(), NEEDS_SOLVER)
class FirmwareShaped(unittest.TestCase):
    def test_a_direct_path_is_two_crosspoints(self):
        a = solve(TINY, [(1, 3, 6), (2, 4, 7)], "firmware")
        self.assertEqual((a["verdict"], a["fewest_proved"], len(a["closed"])), ("routable", True, 4))

    def test_six_crosspoints_is_copper_but_not_a_firmware_path(self):
        self.assertEqual(solve(CHAIN, [(1, 4, 6)], "firmware")["verdict"], "not_routable")
        self.assertEqual(solve(CHAIN, [(1, 4, 6)], "copper")["verdict"], "routable")

    def test_paths_of_one_net_share_copper(self):
        a = solve(TINY, [(1, 3, 6), (1, 4, 6)], "firmware")           # both leave row 1 by the same crosspoint
        self.assertEqual(len(a["closed"]), 3)

    def test_every_bridge_needs_its_own_path(self):
        mid = types.SimpleNamespace(**{**vars(CHAIN), "Y_NET": {**CHAIN.Y_NET, "B": ["2"]}, "NODE_NET": {1: "1", 2: "2", 4: "4"}})
        self.assertEqual(solve(mid, [(1, 2, 6), (1, 4, 6)], "firmware")["verdict"], "not_routable")   # 1-4 alone is six
        self.assertEqual(solve(mid, [(1, 2, 6), (2, 4, 6)], "firmware")["verdict"], "routable")       # 2-4 is four
        self.assertEqual(len(solve(mid, [(1, 2, 6), (1, 4, 6)], "copper")["closed"]), 6)              # the same tree

    def test_one_lane_two_nets(self):
        self.assertEqual(solve(ONE_LANE, [(1, 3, 6), (2, 4, 7)], "firmware")["verdict"], "not_routable")

    def test_a_bridge_on_one_wire_does_not_make_a_netlist_unroutable(self):          # Review Focus 4
        same = types.SimpleNamespace(**{**vars(TINY), "NODE_NET": {1: "1", 9: "1", 3: "3"}})
        for rule in ("firmware", "copper"):
            self.assertEqual(solve(same, [(1, 9, 6), (1, 3, 6)], rule)["verdict"], "routable", rule)

    def test_stopping_at_the_first_routing(self):
        a = ceiling.ask(PROBLEM, "firmware", fewest=False)
        self.assertEqual((a["verdict"], a["fewest_proved"]), ("routable", False))


class Standing(unittest.TestCase):
    """What the lab stands behind: a solver's answer checked by the lab's own copper model."""

    def test_faults_of_made_up_answers(self):
        p = ceiling.problem(tiny_paint([(1, 3, 6, "unrouted"), (2, 4, 7, "unrouted")]), ceiling.graph(TINY))
        good = [["A", 0, 0, 6], ["B", 0, 0, 6], ["A", 1, 1, 7], ["B", 1, 1, 7]]
        self.assertEqual(ceiling.faults(p, good, "firmware"), [])
        self.assertTrue(ceiling.faults(p, good[:3], "copper"))                              # 2-4 not joined
        self.assertTrue(ceiling.faults(p, good[:2] + [["A", 0, 1, 7], ["B", 0, 1, 7]], "copper"))   # L0 joins two nets
        self.assertTrue(ceiling.faults(p, good + [["Z", 0, 0, 6]], "copper"))               # not offered
        relabelled = [[c, x, y, 99] for c, x, y, _ in good]                                 # the tags are not trusted
        self.assertEqual(ceiling.faults(p, relabelled, "firmware"), [])

    def test_a_node_in_no_net_may_not_be_touched(self):                                     # Review Focus 5
        p = ceiling.problem(tiny_paint([(1, 3, 6, "unrouted")]), ceiling.graph(TINY))
        through_row_2 = [["A", 0, 0, 6], ["B", 0, 0, 6], ["A", 0, 1, 6]]                    # row 2 is in no net
        self.assertTrue(ceiling.faults(p, through_row_2, "copper"))

    def test_four_crosspoints_at_most_under_the_firmware_rule(self):
        p = ceiling.problem(unrouted(CHAIN, [(1, 4, 6)]), ceiling.graph(CHAIN))
        six = [["A", 0, 0, 6], ["B", 0, 0, 6], ["B", 1, 0, 6], ["C", 0, 0, 6], ["C", 1, 0, 6], ["D", 0, 0, 6]]
        self.assertEqual(ceiling.faults(p, six, "copper"), [])
        self.assertTrue(ceiling.faults(p, six, "firmware"))

    def test_a_wrong_answer_is_unknown_with_the_reason(self):
        with mock.patch.object(ceiling, "ask", return_value={"verdict": "routable", "fewest_proved": True, "closed": [], "seconds": 0.1}):
            v = ceiling.verdict(ROUTED_RESULT, use_cache=False)
        self.assertEqual(v["verdict"], "unknown")
        self.assertIn("lab's own check", v["error"])
        self.assertEqual((v["closed"], v["crosspoints"], v["fewest_proved"]), ([], None, False))

    def test_not_routable_against_a_full_routing_is_the_models_fault(self):               # Review Focus 2
        with mock.patch.object(ceiling, "ask", return_value={"verdict": "not_routable", "fewest_proved": False, "closed": [], "seconds": 0.1}):
            v = ceiling.verdict(ROUTED_RESULT, use_cache=False)
            self.assertEqual(v["verdict"], "unknown")
            self.assertIn("the model is wrong", v["error"])
            over = ceiling.verdict(runner.run_case(NEW, dense("k_rows_overflow_metric")), use_cache=False)
        self.assertEqual((over["verdict"], over["error"]), ("not_routable", None))          # the router did not route it all

    def test_not_routable_is_the_models_fault_whenever_the_routers_own_routing_holds(self):
        # routed in full, but judged "problems" for something that is not the copper (62 battery cases are)
        flagged = dict(ROUTED_RESULT, status="problems", problems=["the same case routed twice gives different routes"])
        with mock.patch.object(ceiling, "ask", return_value={"verdict": "not_routable", "fewest_proved": False, "closed": [], "seconds": 0.1}):
            v = ceiling.verdict(flagged, use_cache=False)
        self.assertEqual(v["verdict"], "unknown")
        self.assertIn("the model is wrong", v["error"])

    def test_an_answer_the_lab_does_not_stand_behind_is_not_kept(self):
        asked = []

        def joins_nothing(problem, rule, seconds, fewest):
            asked.append(rule)
            return {"verdict": "routable", "fewest_proved": True, "closed": [], "seconds": 0.1}

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(variants, "BUILD_DIR", Path(tmp)), \
                mock.patch.object(ceiling, "ask", side_effect=joins_nothing):
            for _ in range(2):
                self.assertIn("lab's own check", ceiling.verdict(ROUTED_RESULT)["error"])
            self.assertEqual(len(asked), 2)                          # asked again: the first answer was not kept
            self.assertEqual(list(Path(tmp).rglob("*.json")), [])

    def test_a_crashed_result_has_nothing_to_ask(self):
        with mock.patch.object(ceiling, "ask", side_effect=AssertionError("asked about nothing")):
            v = ceiling.verdict(CRASHED_RESULT)
        self.assertEqual((v["verdict"], v["error"], v["closed"], v["crosspoints"]), ("nothing", None, [], None))

    def test_the_routers_own_routing_passes_the_check_and_is_counted(self):
        import copper
        paint = copper.paint(ROUTED_RESULT)
        own = [[c["chip"], c["x"], c["y"], c["net"]] for c in paint["crosspoints"] if not c["dup"]]
        self.assertEqual(ceiling.faults(ceiling.problem(paint), own, "firmware"), [])
        with mock.patch.object(ceiling, "ask", return_value={"verdict": "routable", "fewest_proved": False, "closed": own, "seconds": 0.1}):
            v = ceiling.verdict(ROUTED_RESULT, use_cache=False)
        self.assertEqual((v["verdict"], v["error"], v["crosspoints"], v["router_crosspoints"]), ("routable", None, len(own), len(own)))

    def test_answers_are_cached_but_not_one_with_an_error(self):
        calls = []

        def answer(problem, rule, seconds, fewest):
            calls.append(rule)
            return {"verdict": "unknown", "fewest_proved": False, "closed": [], "seconds": 0.1,
                    **({"error": "the solver exited with 3"} if rule == "copper" else {})}

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(variants, "BUILD_DIR", Path(tmp)), \
                mock.patch.object(ceiling, "ask", side_effect=answer):
            for rule in ("firmware", "firmware", "copper", "copper"):
                ceiling.verdict(ROUTED_RESULT, rule)
            self.assertEqual(calls, ["firmware", "copper", "copper"])
            ceiling.verdict(ROUTED_RESULT, "firmware", seconds=7)                            # another limit: asked again
            self.assertEqual(len(calls), 4)


@unittest.skipUnless(ceiling.solver_installed(), NEEDS_SOLVER)
class OnTheBoardsFabric(unittest.TestCase):
    def test_the_router_is_never_contradicted_on_the_dense_suite(self):
        for r in runner.run_battery(variants.resolve("worktree"), lab.battery(["dense"])):
            for rule in ("firmware", "copper"):
                v = ceiling.verdict(r, rule, seconds=5)          # cached after the first run
                self.assertIsNone(v["error"], (r["case"], rule, v["error"]))
                if lab.fully_routed(r):
                    self.assertNotEqual(v["verdict"], "not_routable", r["case"])
                    if v["verdict"] == "routable" and v["fewest_proved"]:
                        self.assertLessEqual(v["crosspoints"], v["router_crosspoints"], r["case"])

    def test_what_is_beyond_the_fabric_is_proved_so(self):
        by = {r["case"]: r for r in runner.run_battery(variants.resolve("worktree"), lab.battery(["beyond"]))}
        for name in ("every_nano_pin", "nine_k_nets"):
            self.assertEqual(ceiling.verdict(by[name], "firmware")["verdict"], "not_routable", name)
        over = runner.run_case(NEW, dense("k_rows_overflow_metric"))
        for rule in ("firmware", "copper"):
            self.assertEqual(ceiling.verdict(over, rule)["verdict"], "not_routable", rule)
        # 64 bridges: any copper can carry them. Nothing is asserted of firmware-shaped paths (not known in 20 s).
        # fewest=False: the answer must not hang on how far the search for the fewest gets inside the limit.
        self.assertEqual(ceiling.verdict(by["max_bridges_random"], "copper", fewest=False)["verdict"], "routable")

    def test_a_case_with_a_proved_fewest(self):
        v = ceiling.verdict(ROUTED_RESULT, "firmware")
        self.assertEqual((v["verdict"], v["fewest_proved"], v["crosspoints"], v["router_crosspoints"]), ("routable", True, 16, 16))


if __name__ == "__main__":
    unittest.main()
