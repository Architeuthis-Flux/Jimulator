# SPDX-License-Identifier: MIT
"""The copper searches, on fabrics small enough to check on paper and on what
the router really did."""
import types
import unittest

import cases
import ceiling
import copper
import lab
import runner
import variants

NEW = OLD = None                        # harness binaries: today's router, and the one before the hub rescue tier

TINY = types.SimpleNamespace(                        # two chips, two lanes between them, one bounce row each
    CHIPS="AB", X_NET={"A": ["L0", "L1"], "B": ["L0", "L1"]},
    Y_NET={"A": ["1", "2", "bA"], "B": ["3", "4", "bB"]}, NODE_NET={1: "1", 2: "2", 3: "3", 4: "4"})


def setUpModule():
    global NEW, OLD
    NEW = variants.build(variants.resolve("worktree"))
    OLD = variants.build(variants.resolve("a1accf5^"))


def tiny_paint(bridges, closed=(), riding=None, fabric=TINY):
    """A paint by hand, with the keys the searches read. bridges: [(n1, n2, net, state)]; closed: [(chip, x, y,
    net)], which also puts the net on both wires; riding: {wire: [nets]} for copper held without a crosspoint."""
    on = {w: set(nets) for w, nets in (riding or {}).items()}
    for chip, x, y, net in closed:
        for w in (fabric.X_NET[chip][x], fabric.Y_NET[chip][y]):
            on.setdefault(w, set()).add(net)
    wires = {w: {"nets": sorted(on.get(w, ()))} for chip in fabric.CHIPS for w in fabric.X_NET[chip] + fabric.Y_NET[chip]}
    nets = {}                                        # as a real paint: every bridge with a net, whatever became of it
    for n1, n2, net, _ in bridges:
        if net is not None:
            nodes = nets.setdefault(str(net), {"nodes": []})["nodes"]
            nodes += [n for n in (n1, n2) if n not in nodes]
    return {"nets": nets, "wires": wires,
            "crosspoints": [{"chip": c, "x": x, "y": y, "net": net, "dup": False} for c, x, y, net in closed],
            "bridges": [{"n1": a, "n2": b, "net": net, "state": state, "infra": False, "r": None}
                        for a, b, net, state in bridges]}


def name(n):
    return str(copper.NODE_NAME.get(n, n))


def dense(case_name):
    return next(c for c in cases.dense_cases() if c.name == case_name)


class Missed(unittest.TestCase):
    def test_graph_of_the_tiny_fabric(self):
        g = ceiling.graph(TINY)
        self.assertEqual(sorted(w for w, _ in g.edges["1"]), ["L0", "L1"])
        self.assertEqual(len(g.edges["L0"]), 6)                      # three Y wires on each of two chips
        self.assertEqual(g.owners["1"], [1])
        self.assertEqual(g.owners.get("L0", []), [])

    def test_an_unrouted_bridge_gets_the_shortest_free_path(self):
        m = ceiling.missed(tiny_paint([(1, 3, 6, "unrouted")]), ceiling.graph(TINY))
        self.assertEqual((m[0]["new"], m[0]["hops"]), (2, 2))
        self.assertEqual({(h["chip"], h["y"]) for h in m[0]["path"]}, {("A", 0), ("B", 0)})
        self.assertEqual((m[0]["n1"], m[0]["n2"], m[0]["net"], m[0]["infra"]), (1, 3, 6, False))
        self.assertTrue(all(h["new"] for h in m[0]["path"]))

    def test_copper_another_net_rides_is_not_free(self):
        taken = [("A", 0, 1, 7), ("B", 0, 1, 7)]                      # net 7 (2-4) on lane L0; net 8 holds lane L1
        p = tiny_paint([(1, 3, 6, "unrouted"), (2, 4, 7, "routed")], taken, riding={"L1": [8]})
        m = ceiling.missed(p, ceiling.graph(TINY))
        self.assertIsNone(m[0]["path"])
        self.assertEqual((m[0]["new"], m[0]["hops"]), (0, 0))

    def test_a_node_in_no_net_is_never_passed(self):                  # Review Focus 5
        withx = types.SimpleNamespace(**{**vars(TINY), "X_NET": {"A": ["L0", "L1", "N9"], "B": ["L0", "L1"]},
                                         "NODE_NET": {**TINY.NODE_NET, 9: "N9"}})
        g, held = ceiling.graph(withx), {"L0": [7], "L1": [8]}        # both lanes held; N9 also joins rows 1 and 2
        m = ceiling.missed(tiny_paint([(1, 2, 6, "unrouted")], riding=held, fabric=withx), g)
        self.assertIsNone(m[0]["path"])                               # node 9 is in no net: its copper is not a way
        m = ceiling.missed(tiny_paint([(1, 2, 6, "unrouted"), (1, 9, 6, "unrouted")], riding=held, fabric=withx), g)
        self.assertEqual(m[0]["new"], 2)                              # node 9 is in net 6 now: it may be passed

    def test_same_net_copper_is_free_and_already_closed_crosspoints_cost_nothing(self):
        closed = [("A", 0, 0, 6), ("B", 0, 0, 6)]                     # 1-3 routed on L0; now row 2 wants to join row 1
        m = ceiling.missed(tiny_paint([(1, 3, 6, "routed"), (1, 2, 6, "unrouted")], closed), ceiling.graph(TINY))
        self.assertEqual((m[0]["new"], m[0]["hops"]), (1, 2))         # only A.x0/y1 is new; A.x0/y0 is there
        self.assertEqual(sorted(h["new"] for h in m[0]["path"]), [False, True])

    def test_states_the_firmware_refused_are_not_searched(self):
        p = tiny_paint([(1, 3, 6, "refused"), (2, 4, None, "left_out"), (1, 2, None, "rejected"), (2, 4, 7, "routed")])
        self.assertEqual(ceiling.missed(p, ceiling.graph(TINY)), [])

    def test_one_piece_of_copper_and_a_node_off_the_model(self):      # Review Focus 4
        same = types.SimpleNamespace(**{**vars(TINY), "NODE_NET": {1: "1", 9: "1", 3: "3"}})
        m = ceiling.missed(tiny_paint([(1, 9, 6, "unrouted"), (1, 77, 6, "unrouted")]), ceiling.graph(same))
        self.assertEqual((m[0]["path"], m[0]["new"]), ([], 0))
        self.assertIsNone(m[1]["path"])

    def test_empty_and_crashed_paints(self):                          # Review Focus 3
        self.assertEqual(ceiling.missed(copper.paint({"status": "crash", "problems": [], "notes": [], "b": ""})), [])


class OnTheRouter(unittest.TestCase):
    def test_the_router_before_the_hub_tier_missed_two_paths_of_four(self):
        found = ceiling.missed(copper.paint(runner.run_case(OLD, dense("nano_dense_metric"))))
        self.assertEqual(sorted((name(m["n1"]), name(m["n2"]), m["new"]) for m in found if m["path"]),
                         [("A4", "19", 4), ("A5", "20", 4)])

    def test_todays_router_misses_nothing_in_dense_real_and_stress(self):
        for r in runner.run_battery(variants.resolve("worktree"), lab.battery(["dense", "real", "stress"])):
            self.assertEqual([m for m in ceiling.missed(copper.paint(r)) if m["path"]], [], r["case"])
        over = ceiling.missed(copper.paint(runner.run_case(NEW, dense("k_rows_overflow_metric"))))
        self.assertEqual([(m["infra"], m["path"]) for m in over], [(True, None)])     # the feed, and the copper has no way


if __name__ == "__main__":
    unittest.main()
