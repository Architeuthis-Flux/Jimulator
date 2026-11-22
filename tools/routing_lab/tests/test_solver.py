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
from tests.test_ceiling import TINY, tiny_paint

NEEDS_SOLVER = "the solver is not installed: python3 tools/routing_lab/lab.py solver-setup"
ONE_LANE = types.SimpleNamespace(**{**vars(TINY), "X_NET": {"A": ["L0"], "B": ["L0"]}})
CHAIN = types.SimpleNamespace(CHIPS="ABCD", X_NET={"A": ["AB"], "B": ["AB", "BC"], "C": ["BC", "CD"], "D": ["CD"]},
                              Y_NET={"A": ["1"], "B": ["bB"], "C": ["bC"], "D": ["4"]}, NODE_NET={1: "1", 4: "4"})


def unrouted(fabric, bridges):
    return tiny_paint([(a, b, net, "unrouted") for a, b, net in bridges], fabric=fabric)


def solve(fabric, bridges, rule):
    return ceiling.ask(ceiling.problem(unrouted(fabric, bridges), ceiling.graph(fabric)), rule, seconds=10)


PROBLEM = ceiling.problem(unrouted(TINY, [(1, 3, 6), (2, 4, 7)]), ceiling.graph(TINY))


@contextlib.contextmanager
def fake_solver(script):
    """ceiling.SOLVER_PYTHON as an executable that runs `script` whatever its arguments."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "python"
        path.write_text("#!%s\n%s\n" % (sys.executable, script))
        path.chmod(0o755)
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


if __name__ == "__main__":
    unittest.main()
