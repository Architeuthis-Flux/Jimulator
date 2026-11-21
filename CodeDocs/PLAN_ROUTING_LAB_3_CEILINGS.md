# Routing lab, plan 3: ceilings

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Say how far a routing is from what the copper allows: draw the path the hardware had for a bridge the router left unrouted, count the parallel copies the free copper still allows, and, with an exact solver, prove whether a netlist can be routed at all and with how few crosspoints.

**Architecture:** One new Python module, `ceiling.py`, holds the copper as a graph (wires joined by crosspoints, from `fabric_v5`) and two searches over a painted result: `missed` (shortest free path for a failed bridge) and `spare` (extra copies for a routed one). Both are plain Python; `missed` runs for every case in a battery, `spare` when a case is painted. The exact search is a separate script, `solver/solve.py`, run with OR-tools CP-SAT from a virtual environment under `build/`; the lab talks to it with JSON over a pipe, checks every "routable" answer against its own copper model, and works without it. Edge cases are netlists grown until the solver proves one more bridge cannot fit; they are saved as ordinary case files.

**Tech Stack:** Python 3 standard library for the lab; OR-tools 9.15 (CP-SAT) only inside `tools/routing_lab/build/solver-venv`; the existing page (plain JS, SVG).

**Spec:** `CodeDocs/DESIGN_ROUTING_LAB.md`, "Piece 3: ceilings", "How we know it works", "Learned building piece 1". Read `tools/routing_lab/README.md` for what exists.

## Global Constraints

- Nothing under `src/` is edited. `test/hil/` is read, not edited.
- Do not edit anything under `tools/routing_lab/harness/`. The board check is recorded for the harness's hash; a change there makes `lab.py run` say "not verified against a board" until `lab.py fidelity tools/routing_lab/fidelity/board_0621e4f44e23` is re-run.
- Work on branch `worktree-routing-lab`, one commit per task, never pushed. No attribution lines in commit messages. Never touch `.github/workflows/release.yml`. Stage files by name; `.pio/**/firmware.uf2` is tracked and must not be committed.
- The lab itself imports only the standard library. `ortools` is imported in `solver/solve.py` and nowhere else.
- The model is the checker's: a wire carries one net; a crosspoint joins an X wire and a Y wire on one chip; a real node outside the net may not be touched (a node in another net, or in no net).
- A bridge the firmware rejected, left out of every net, or refused in its safety check is never a miss and is never given to a search. In a paint these are the bridge states `rejected`, `left_out`, `refused`. The searches act on `unrouted` and `broken` (failed) and on `routed`.
- "Firmware-shaped" means: each bridge is its own path of at most four crosspoints (what `pathStruct` holds); paths of one net may share copper.
- Copies found by the residual search are "available in copper". The firmware holds some copper back for sense taps, so every place that shows them says so.
- Resistance stays in units of one crosspoint; the page multiplies by its ohms box.
- On the page red means a problem and nothing else is red; the page loads nothing from the network.
- Tests: `python3 -m unittest discover -s tools/routing_lab/tests -t tools/routing_lab` passes with the solver installed and without it (solver tests skip, saying why).

## Measured before writing this plan (2026-11-21, router at 5374d38)

- A prototype of the missed-path search finds, on the router before the hub rescue tier (`a1accf5^`), exactly the two unrouted bridges of `nano_dense_metric`, `A4-19` and `A5-20`, each with a path of four new crosspoints. On today's router no failed bridge in the 2,247-case battery has a path (the ten failed bridges of `beyond` and the two failed probe feeds have none).
- It costs 1.5 s for the whole battery. The spare-copy search costs about 9 ms a case, so it is done when a case is painted, not for every case in a run.
- OR-tools 9.15.6755 installs with `pip` into a virtual environment under Python 3.13 here. With the model of Tasks 5 and 6 and a 20 s limit, over the 21 dense and 3 beyond cases:
  - 17 dense cases are proved routable with the fewest crosspoints proved, in 0.2 to 9 s, under both rules. Three more (`chain_all_chips`, `gnd_spread`, `big_net_thirteen_nodes`) are proved routable but their fewest is not proved in 20 s.
  - `k_rows_overflow_metric` is proved not routable in 1.2 s under both rules, the probe feed counted: its overflow is the fabric's, as the suite has always assumed.
  - `every_nano_pin` and `nine_k_nets` are proved not routable in 1 to 2.4 s. `max_bridges_random` (64 bridges, the router routes 61) can be routed as any-copper trees (90 crosspoints or fewer); for firmware-shaped paths nothing is known after 20 s.
  - Where the fewest is proved it is never above the router's count, and on some cases it is below (`corner_rows`: 16 against the router's 20). The router's count here includes its duplicates; Task 7 compares against its primaries alone.
- So 20 s is the default limit, and a verdict of "unknown" is a real outcome the page and the commands must show.
- Random netlists longer than the `fuzz` class's twelve bridges are where the router and the ceiling part. For two seeds, prefixes of one legal random list: at 20 bridges the router routes all and the fewest is proved; at 30 it leaves one bridge unrouted, at 40 two or three, at 50 five or six, and each of those netlists is proved routable with firmware-shaped paths. At 60 one seed is still proved routable (the router routes 54 of 61) and the other is not known after 20 s. At 80 the firmware itself keeps fewer bridges in nets than at 60 for one seed (53: the rest it leaves out), so "more bridges" is not always "harder". The edge the solver can prove lies around 50 to 60 bridges, and "one more bridge" will usually read "not known", seldom "proved not routable".
- In the 40-bridge netlist of seed 1 one failed bridge (`ISENSE_PLUS-UART_TX`) needs a single new crosspoint through copper its net already has: a miss of the kind Task 1 draws, on today's router. In the 30-bridge one the failed bridge has no free path with the rest where the router put it; only moving other paths frees one, which is what the solver's routing shows.
- These came from throwaway prototypes. The numbers are for sizing; the tasks' tests are what must hold.

## File structure

| File | Responsibility |
|---|---|
| `tools/routing_lab/ceiling.py` (new) | The copper graph; `missed`, `spare`, `painted`; the problem a solver is given; asking the solver and checking its answer |
| `tools/routing_lab/solver/solve.py` (new) | CP-SAT model for both rule sets. Reads one JSON problem on stdin, writes one JSON answer. Knows nothing of the lab or of V5 |
| `tools/routing_lab/edge.py` (new) | Growing a netlist to the edge of what provably fits |
| `tools/routing_lab/cases/edge/*.json` (new) | The edge cases found, as ordinary case files |
| `tools/routing_lab/runner.py`, `lab.py`, `server.py`, `export.py` (modify) | The `missed` metric and column; `solver-setup`, `ceiling`, `edge` commands; `/api/ceiling`; exports carry missed paths and spare copies |
| `tools/routing_lab/web/lab.js`, `lab.css`, `index.html` (modify) | Dashed missed paths, the spare column, the solver's verdict and overlay |
| `tools/routing_lab/tests/test_ceiling.py`, `test_solver.py`, `test_edge.py` (new) | Tests, on small made-up fabrics and on real results |

## Review Focus

The inputs the design is silent on that are most likely to bite. Each has its test in the task named.

1. **A solver that is missing, crashes, times out or prints rubbish** must read as "not installed" or "unknown", never as "not routable" and never as a stack trace on the page (Task 5, Task 7).
2. **A "not routable" verdict for a case the router routed in full** means the model is wrong, not the router. The lab must say so loudly and must not show it as a verdict (Task 7).
3. **A result with nothing to search**: a crash or timeout (no report), a case whose every bridge was refused, or one with no failed bridge. The searches return empty answers and the page shows nothing extra (Task 1, Task 2, Task 5).
4. **A bridge whose two nodes are one piece of copper, or a node the fabric model does not hold.** Zero crosspoints needed in the first case, no search in the second, no exception in either (Task 1).
5. **A path that is free in copper but passes a node in no net** would be a stray on a board. The searches must never offer one, and a solver answer that does is rejected (Task 1, Task 7).

---

### Task 1: The copper graph and the missed path

**Files:**
- Create: `tools/routing_lab/ceiling.py`, `tools/routing_lab/tests/test_ceiling.py`

**Interfaces:**
- Consumes: `copper.paint(result)` (keys `nets`, `crosspoints`, `wires`, `bridges`), `fabric_v5` (`CHIPS`, `X_NET`, `Y_NET`, `NODE_NET`).
- Produces:
  - `ceiling.Graph`: a named tuple `(edges, owners)`. `edges[wire]` is a list of `(other_wire, (chip, x, y))`, one for every crosspoint on the wire; `owners[wire]` is the list of node ids whose copper the wire is.
  - `ceiling.graph(fabric=fabric_v5) -> Graph`. `fabric` is anything with `CHIPS`, `X_NET`, `Y_NET`, `NODE_NET`; the default's graph is built once.
  - `ceiling.missed(paint, g=None) -> list[dict]`: one entry for every bridge in `paint["bridges"]` whose state is `unrouted` or `broken`, the probe feed included, in the paint's order: `{"n1", "n2", "net", "infra", "path", "new", "hops"}`. `path` is the cheapest way through the copper as a list of `{"chip", "x", "y", "new"}` from `n1`'s wire to `n2`'s, or `None` when the copper has none with everything else where it is. `new` counts the crosspoints that would have to be closed; `hops` is `len(path)`.

**The rule (binding):** a path may pass a wire only if no net rides it and it is no node's copper, or it carries this bridge's net and nothing else, or its node is in this net. A crosspoint already closed for this net costs nothing; any other costs one. Fewest new crosspoints wins; among those, fewest hops.

- [ ] **Step 1: Write the failing tests** in `tests/test_ceiling.py`. A made-up fabric and a paint built by hand keep the expected answers checkable on paper:

```python
TINY = types.SimpleNamespace(                        # two chips, two lanes between them, one bounce row each
    CHIPS="AB", X_NET={"A": ["L0", "L1"], "B": ["L0", "L1"]},
    Y_NET={"A": ["1", "2", "bA"], "B": ["3", "4", "bB"]}, NODE_NET={1: "1", 2: "2", 3: "3", 4: "4"})

def tiny_paint(bridges, closed=(), riding=None, fabric=TINY):
    """A paint by hand, with the keys the searches read. bridges: [(n1, n2, net, state)]; closed: [(chip, x, y,
    net)], which also puts the net on both wires; riding: {wire: [nets]} for copper held without a crosspoint."""

class Missed(unittest.TestCase):
    def test_graph_of_the_tiny_fabric(self):
        g = ceiling.graph(TINY)
        self.assertEqual(sorted(w for w, _ in g.edges["1"]), ["L0", "L1"])
        self.assertEqual(len(g.edges["L0"]), 6)                      # three Y wires on each of two chips
        self.assertEqual(g.owners["1"], [1]); self.assertEqual(g.owners.get("L0", []), [])

    def test_an_unrouted_bridge_gets_the_shortest_free_path(self):
        m = ceiling.missed(tiny_paint([(1, 3, 6, "unrouted")]), ceiling.graph(TINY))
        self.assertEqual((m[0]["new"], m[0]["hops"]), (2, 2))
        self.assertEqual({(h["chip"], h["y"]) for h in m[0]["path"]}, {("A", 0), ("B", 0)})

    def test_copper_another_net_rides_is_not_free(self):
        taken = [("A", 0, 1, 7), ("B", 0, 1, 7)]                      # net 7 (2-4) on lane L0; net 8 holds lane L1
        p = tiny_paint([(1, 3, 6, "unrouted"), (2, 4, 7, "routed")], taken, riding={"L1": [8]})
        m = ceiling.missed(p, ceiling.graph(TINY))
        self.assertIsNone(m[0]["path"]); self.assertEqual((m[0]["new"], m[0]["hops"]), (0, 0))

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

    def test_states_the_firmware_refused_are_not_searched(self):
        p = tiny_paint([(1, 3, 6, "refused"), (2, 4, None, "left_out"), (1, 2, None, "rejected"), (2, 4, 7, "routed")])
        self.assertEqual(ceiling.missed(p, ceiling.graph(TINY)), [])

    def test_one_piece_of_copper_and_a_node_off_the_model(self):      # Review Focus 4
        same = types.SimpleNamespace(**{**vars(TINY), "NODE_NET": {1: "1", 9: "1", 3: "3"}})
        m = ceiling.missed(tiny_paint([(1, 9, 6, "unrouted"), (1, 77, 6, "unrouted")]), ceiling.graph(same))
        self.assertEqual((m[0]["path"], m[0]["new"]), ([], 0)); self.assertIsNone(m[1]["path"])

    def test_empty_and_crashed_paints(self):                          # Review Focus 3
        self.assertEqual(ceiling.missed(copper.paint({"status": "crash", "problems": [], "notes": [], "b": ""})), [])

class OnTheRouter(unittest.TestCase):                                 # setUpModule builds "worktree" and "a1accf5^"
    def test_the_router_before_the_hub_tier_missed_two_paths_of_four(self):
        found = ceiling.missed(copper.paint(runner.run_case(OLD, dense("nano_dense_metric"))))
        self.assertEqual(sorted((name(m["n1"]), name(m["n2"]), m["new"]) for m in found if m["path"]),
                         [("A4", "19", 4), ("A5", "20", 4)])

    def test_todays_router_misses_nothing_in_dense_real_and_stress(self):
        for r in runner.run_battery(variants.resolve("worktree"), lab.battery(["dense", "real", "stress"])):
            self.assertEqual([m for m in ceiling.missed(copper.paint(r)) if m["path"]], [], r["case"])
        over = ceiling.missed(copper.paint(runner.run_case(NEW, dense("k_rows_overflow_metric"))))
        self.assertEqual([(m["infra"], m["path"]) for m in over], [(True, None)])     # the feed, and the copper has no way
```

`name(n)` is `str(copper.NODE_NAME.get(n, n))`; `dense(case_name)` picks from `cases.dense_cases()`.

- [ ] **Step 2: Run** `python3 -m unittest discover -s tools/routing_lab/tests -t tools/routing_lab -k test_ceiling`. Expected: import error, no `ceiling`.
- [ ] **Step 3: Implement** `Graph`, `graph`, `missed`. Dijkstra over wires with cost `(new crosspoints, hops)`; which net a node is in comes from `paint["nets"][str(net)]["nodes"]`, what rides a wire from `paint["wires"][name]["nets"]`, what is closed from `paint["crosspoints"]`.
- [ ] **Step 4: Run** the same command. Expected: pass.
- [ ] **Step 5: Commit** `Routing lab: the copper graph and the path a failed bridge had`.

---

### Task 2: Spare copies, and a paint that carries both searches

**Files:**
- Modify: `tools/routing_lab/ceiling.py`, `tools/routing_lab/server.py` (`api_get_case`), `tools/routing_lab/export.py` (`write`), `tools/routing_lab/tests/test_ceiling.py`, `tests/test_server.py`, `tests/test_export.py`

**Interfaces:**
- Consumes: Task 1's `Graph`, `graph`, `missed`; `copper.effective_resistance(edges, a, b)`.
- Produces:
  - `ceiling.spare(paint, g=None, limit=8) -> list[dict]`: one entry per bridge whose state is `routed` and that is not the probe feed: `{"n1", "n2", "net", "copies", "r", "paths"}`. `paths` is a list of copies, each a list of `{"chip", "x", "y"}`; `copies == len(paths)`; `r` is the bridge's resistance with all of them closed, `None` when `copies` is 0.
  - `ceiling.painted(result) -> dict`: `copper.paint(result)` plus `paint["missed"]` (Task 1's list) and, on every bridge, `"spare"` (the count, 0 when none or not routed), `"r_spare"` and `"spare_paths"`.
  - `server.api_get_case` and `export.write` use `ceiling.painted` where they used `copper.paint`.

**The rule (binding):** a copy is a path from `n1`'s wire to `n2`'s of at most four crosspoints, all new, through wires that carry no net and are no node's copper. Copies of one bridge share no wire with each other. They are found shortest first until none is left or `limit` is reached. Each bridge is looked at alone, as if it could take all the free copper: two bridges' copies may want the same lane. This is "available in copper", not "what the firmware would give".

- [ ] **Step 1: Write the failing tests**

```python
class Spare(unittest.TestCase):
    def test_a_free_lane_is_one_more_copy_and_halves_the_resistance(self):
        closed = [("A", 0, 0, 6), ("B", 0, 0, 6)]                     # 1-3 on lane L0; L1 is free
        s = ceiling.spare(tiny_paint([(1, 3, 6, "routed")], closed), ceiling.graph(TINY))
        self.assertEqual((s[0]["copies"], s[0]["r"]), (1, 1.0))
        self.assertEqual({(h["chip"], h["x"]) for h in s[0]["paths"][0]}, {("A", 1), ("B", 1)})

    def test_no_free_copper_no_copies(self):
        closed = [("A", 0, 0, 6), ("B", 0, 0, 6), ("A", 1, 1, 7), ("B", 1, 1, 7)]
        s = ceiling.spare(tiny_paint([(1, 3, 6, "routed"), (2, 4, 7, "routed")], closed), ceiling.graph(TINY))
        self.assertEqual([(x["copies"], x["r"]) for x in s], [(0, None), (0, None)])

    def test_the_limit_and_the_four_crosspoint_rule(self):
        wide = types.SimpleNamespace(**{**vars(TINY), "X_NET": {c: ["L%d" % i for i in range(5)] for c in "AB"}})
        p = tiny_paint([(1, 3, 6, "routed")], [("A", 0, 0, 6), ("B", 0, 0, 6)], fabric=wide)    # on L0; four lanes free
        s = ceiling.spare(p, ceiling.graph(wide))
        self.assertEqual((s[0]["copies"], s[0]["r"]), (4, 0.4))        # five two-crosspoint paths side by side
        self.assertEqual(ceiling.spare(p, ceiling.graph(wide), limit=2)[0]["copies"], 2)
        # two chains side by side, each six crosspoints end to end: the free one is too long to be a copy
        twin = types.SimpleNamespace(CHIPS="ABCD", NODE_NET={1: "1", 4: "4"},
                                     X_NET={"A": ["AB", "ab"], "B": ["AB", "BC", "ab", "bc"],
                                            "C": ["BC", "CD", "bc", "cd"], "D": ["CD", "cd"]},
                                     Y_NET={"A": ["1"], "B": ["bB", "bb"], "C": ["bC", "bc2"], "D": ["4"]})
        first = [("A", 0, 0, 6), ("B", 0, 0, 6), ("B", 1, 0, 6), ("C", 0, 0, 6), ("C", 1, 0, 6), ("D", 0, 0, 6)]
        s = ceiling.spare(tiny_paint([(1, 4, 6, "routed")], first, fabric=twin), ceiling.graph(twin))
        self.assertEqual(s[0]["copies"], 0)

    def test_a_crashed_result_paints_with_nothing_extra(self):        # Review Focus 3
        p = ceiling.painted({"case": "c", "cls": "x", "status": "crash", "problems": [], "notes": [], "b": ""})
        self.assertEqual((p["missed"], p["bridges"]), ([], []))

    def test_on_real_results(self):
        p = ceiling.painted(runner.run_case(NEW, dense("chain_all_chips")))
        for b in p["bridges"]:
            self.assertEqual(b["spare"], len(b["spare_paths"]))
            if b["spare"]:
                self.assertLess(b["r_spare"], b["r"])
                for path in b["spare_paths"]:
                    self.assertLessEqual(len(path), 4)
                    for h in path:                                   # every wire a copy uses is free in the paint
                        for axis, pin in (("X", h["x"]), ("Y", h["y"])):
                            w = copper.wire(h["chip"], axis, pin)
                            self.assertTrue(w in (copper.NODE_NET[b["n1"]], copper.NODE_NET[b["n2"]])
                                            or p["wires"][w]["nets"] == [], w)
        self.assertEqual(p["missed"], [])
        self.assertEqual([b["spare"] for b in p["bridges"] if b["infra"]], [0])
```

In `test_server.py`: `/api/case` answers a paint with `missed` and a `spare` on every bridge. In `test_export.py`: the exported `chain_all_chips` paint has them too.

- [ ] **Step 2: Run to see them fail.**
- [ ] **Step 3: Implement.** Reuse Task 1's search with "free wires only, nothing already closed, at most four hops"; after each copy mark its inner wires used.
- [ ] **Step 4: Run all tests.** Expected: pass.
- [ ] **Step 5: Commit** `Routing lab: copies the free copper still allows, carried in the paint`.

---

### Task 3: "missed" as a number: judge, table, regressions

**Files:**
- Modify: `tools/routing_lab/runner.py` (`judge`, `_result`, `_judge_stamp`), `tools/routing_lab/lab.py` (`print_table`, `regressions`), `tools/routing_lab/tests/test_runner.py`, `tests/test_cli.py`, `tests/test_acceptance.py`

**Interfaces:**
- Consumes: `ceiling.missed`.
- Produces: `result["metrics"]["missed"]`: the number of failed bridges for which the copper had a path (entries of `ceiling.missed` whose `path` is not `None`). 0 in `_result`'s defaults. `_judge_stamp()` also hashes `ceiling.py`. `print_table` gains a `missed` column after `problems`, the class total. `regressions(base, new)` adds a line `"<case>: <n> unrouted where the copper had a path (baseline <m>)"` when `n > m`.

`missed` does not change a case's status or `lab.py run`'s exit code on its own: a scored case with a miss is a worse score, and against a baseline it is a regression, which already exits 1.

- [ ] **Step 1: Write the failing tests**

```python
    def test_missed_counts_bridges_the_copper_could_carry(self):          # test_acceptance.py, beside the history tests
        self.assertEqual(old["nano_dense_metric"]["metrics"]["missed"], 2)        # a1accf5^
        self.assertEqual(new["nano_dense_metric"]["metrics"]["missed"], 0)
        self.assertEqual(sum(r["metrics"]["missed"] for r in new.values()), 0)    # every dense case today

    def test_a_new_miss_is_a_regression(self):                             # test_cli.py
        lines = lab.regressions([row("c", missed=0)], [row("c", missed=1)])
        self.assertTrue(any("where the copper had a path" in line for line in lines))
        self.assertEqual(lab.regressions([row("c", missed=1)], [row("c", missed=1)]), [])
```

`row(name, **metrics)` builds the smallest result `regressions` reads: status `ok`, no problems, one primary routed, and the metrics given. `lab.py run --classes dense` must print a header with `missed`.

- [ ] **Step 2: Run to see them fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run all tests, then** `python3 tools/routing_lab/lab.py run --variant "a1accf5^" --classes dense`. Expected: the dense row shows `missed 2`.
- [ ] **Step 5: Commit** `Routing lab: missed paths counted in the judge, the table and regressions`.

---

### Task 4: The page draws missed paths and lists spare copies

**Files:**
- Modify: `tools/routing_lab/web/lab.js`, `web/lab.css`, `web/index.html`, `tools/routing_lab/tests/test_server.py`

**Interfaces:**
- Consumes: the paint from Task 2 (`paint.missed`, `bridge.spare`, `bridge.r_spare`, `bridge.spare_paths`); `row.metrics.missed` from Task 3.
- Produces: `state.ghost`, the list of paths drawn dashed (`[{net, hops: [{chip, x, y}]}]`); `drawGhost()`, called at the end of `drawFabric` and `drawSheet`.

**What it does:**
- The battery table gains a column `miss` between `taps` and `prob` (tip: "unrouted bridges the free copper could have carried"; less is better; a non-zero cell is red). The left column widens from 450 px to 490 px.
- In the case panel a failed bridge whose missed entry has a path reads `NOT ROUTED - the copper had a path: N crosspoints` (or `... K new, N in all` when they differ); one without reads `NOT ROUTED - no free path in the copper as routed`.
- Selecting a case sets `state.ghost` to its missed paths. Each is drawn dashed in the net's colour, on the fabric view as hollow dashed dots at the crosspoints with the wires between them dashed, on the sheet view as dashed curves in the chips. A dashed path is not red: the bridge's own row carries the red.
- The bridges table gains a column `spare`: `+3 → 40` (copies the copper allows, and the ohms with them), blank at 0. Its header tip: "available in copper, taking this bridge alone; the firmware holds some copper back for sense taps". Clicking a cell shows that bridge's copies as the dashed paths; clicking it again goes back to the missed paths.
- An exported page shows all of this (the data is in its paints).

- [ ] **Step 1: Write the failing test**: `lab.js` holds `drawGhost` and `spare_paths`, still passes `node --check`, and the page has no `http` reference.
- [ ] **Step 2: Run to see it fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Check it in the browser** (`python3 tools/routing_lab/lab.py serve --no-open`, the built-in browser at `http://127.0.0.1:8765/`):
  1. Router `a1accf5^`, class dense: the table shows `miss 2` on `nano_dense_metric`; selecting it draws two dashed paths of four crosspoints each and the two rows read "the copper had a path: 4 crosspoints".
  2. Router `worktree`, `chain_all_chips`: the spare column has numbers; clicking one draws that many dashed paths, none on a lit wire.
  3. `k_rows_overflow_metric`: the probe feed's row reads "no free path in the copper as routed"; nothing dashed.
  4. Both tabs draw the dashed paths; lighting one net alone dims the other nets' dashed paths.
  Screenshot the first for Kevin.
- [ ] **Step 5: Commit** `Routing lab page: the path a failed bridge had, and the copies still free`.

---

### Task 5: The solver, and "can this netlist be routed at all" for any copper

**Files:**
- Create: `tools/routing_lab/solver/solve.py`, `tools/routing_lab/tests/test_solver.py`
- Modify: `tools/routing_lab/ceiling.py`, `tools/routing_lab/lab.py` (`solver-setup`; `clean` keeps `build/solver-venv`)

**Interfaces:**
- Produces, lab side:
  - `ceiling.SOLVER_PYTHON = variants.BUILD_DIR / "solver-venv" / "bin" / "python"`; `ceiling.solver_installed() -> bool`.
  - `ceiling.problem(paint, g=None) -> dict | None`: what a solver is given, or `None` when the paint has no bridge in a state of `routed`, `unrouted` or `broken`:
    `{"bridges": [[wire_a, wire_b, net], ...], "terminals": {wire: net}, "crosspoints": [[chip, x, y, x_wire, y_wire], ...]}`.
    A wire is offered when it is a terminal or no node's copper; a crosspoint is offered when both its wires are, and it does not join the terminals of two nets. The probe feed is a bridge like any other.
  - `ceiling.ask(problem, rule, seconds=20.0, fewest=True) -> dict`: runs `solve.py` under `SOLVER_PYTHON` and returns its answer. Raises `ceiling.SolverMissing` (a `ValueError` whose text ends with `python3 tools/routing_lab/lab.py solver-setup`) when the environment is not there. Anything else that goes wrong (non-zero exit, no JSON, the process outliving `seconds + 30`) returns `{"verdict": "unknown", "error": "<what happened>"}`.
  - `lab.py solver-setup`: `python3 -m venv build/solver-venv`, then `pip install ortools==9.15.6755` in it; prints the version it can import. Needs the network once.
- Produces, `solve.py` (run as `python solve.py`, problem on stdin, answer on stdout, exit 0; a malformed problem is exit 2 with a line on stderr):
  - in: the problem's three keys plus `"rule": "copper" | "firmware"`, `"seconds": float`, and `"fewest": bool` (default true). With `fewest` false it stops at the first routing it finds (`stop_after_first_solution`): a routable netlist whose fewest cannot be proved otherwise runs to the limit, and the edge search of Task 9 only needs "routable".
  - out: `{"verdict": "routable" | "not_routable" | "unknown", "fewest_proved": bool, "closed": [[chip, x, y, net], ...], "seconds": float}`. `closed` is empty unless routable.

**The model (binding; this formulation was timed in the spike):**
- A boolean per offered non-terminal wire and net, "this wire is that net's"; a wire is at most one net's. A terminal is its net's and no other's.
- A boolean per offered crosspoint and net, "closed for that net", which implies both its wires are that net's.
- Rule `copper`: for each net, one terminal is the source of `T - 1` units of flow and every other terminal takes one; flow runs only through that net's closed crosspoints (at most `T - 1` through each); other wires pass on what they get.
- The objective is the fewest closed crosspoints. `OPTIMAL` is `routable` with `fewest_proved`; `FEASIBLE` is `routable` without; `INFEASIBLE` is `not_routable`; anything else is `unknown`. `max_time_in_seconds = seconds`, 8 workers.

- [ ] **Step 1: Write the failing tests** in `tests/test_solver.py`. The class is skipped with "the solver is not installed: python3 tools/routing_lab/lab.py solver-setup" when `ceiling.solver_installed()` is false; the tests of `problem` and of `ask`'s failures run regardless.

```python
ONE_LANE = types.SimpleNamespace(**{**vars(TINY), "X_NET": {"A": ["L0"], "B": ["L0"]}})
CHAIN = types.SimpleNamespace(CHIPS="ABCD", X_NET={"A": ["AB"], "B": ["AB", "BC"], "C": ["BC", "CD"], "D": ["CD"]},
                              Y_NET={"A": ["1"], "B": ["bB"], "C": ["bC"], "D": ["4"]}, NODE_NET={1: "1", 4: "4"})

class Problem(unittest.TestCase):
    def test_problem_of_a_paint(self):
        p = ceiling.problem(tiny_paint([(1, 3, 6, "unrouted"), (2, 4, 7, "routed"), (1, 2, 8, "refused")]), ceiling.graph(TINY))
        self.assertEqual(p["bridges"], [["1", "3", 6], ["2", "4", 7]])
        self.assertEqual(p["terminals"], {"1": 6, "3": 6, "2": 7, "4": 7})
        self.assertEqual(len(p["crosspoints"]), 12)                  # 2 lanes x 3 Y wires x 2 chips: all offered
    def test_a_node_in_no_net_is_not_offered(self):                  # Review Focus 5
        p = ceiling.problem(tiny_paint([(1, 3, 6, "unrouted")]), ceiling.graph(TINY))
        self.assertFalse([c for c in p["crosspoints"] if "2" in c or "4" in c])
    def test_nothing_to_route(self):                                 # Review Focus 3
        self.assertIsNone(ceiling.problem(tiny_paint([(1, 3, 6, "refused")]), ceiling.graph(TINY)))

class Asking(unittest.TestCase):                                     # Review Focus 1
    def test_no_environment_says_how_to_get_one(self):
        with mock.patch.object(ceiling, "SOLVER_PYTHON", Path("/nonexistent/python")), self.assertRaises(ceiling.SolverMissing) as cm:
            ceiling.ask(PROBLEM, "copper")
        self.assertIn("lab.py solver-setup", str(cm.exception))
    def test_a_solver_that_dies_or_prints_rubbish_is_unknown(self):
        for script in ("import sys; sys.exit(3)", "print('not json')", "import time; time.sleep(60)"):
            with fake_solver(script):                                # SOLVER_PYTHON -> a python that runs this instead
                a = ceiling.ask(PROBLEM, "copper", seconds=0.2)
            self.assertEqual(a["verdict"], "unknown"); self.assertTrue(a["error"])

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
        self.assertEqual(p.returncode, 2); self.assertTrue(p.stderr.strip())
    def test_stopping_at_the_first_routing(self):
        a = ceiling.ask(ceiling.problem(unrouted(TINY, [(1, 3, 6), (2, 4, 7)]), ceiling.graph(TINY)), "copper", fewest=False)
        self.assertEqual((a["verdict"], a["fewest_proved"]), ("routable", False))
```

`NEEDS_SOLVER` is that skip message, used by every solver test class. `ceiling.SOLVE_PY` is the path of `solver/solve.py`.

In the test file, `unrouted(fabric, bridges)` is `tiny_paint` with every bridge `unrouted`, and `solve(fabric, bridges, rule)` is `ceiling.ask(ceiling.problem(unrouted(fabric, bridges), ceiling.graph(fabric)), rule, seconds=10)`. `PROBLEM` is the problem of `TINY` with bridges 1-3 and 2-4. `fake_solver(script)` points `ceiling.SOLVER_PYTHON` at a small executable that runs `python3 -c script` whatever its arguments.

- [ ] **Step 2: Run to see them fail** (import errors; with no environment the solver class reports skipped).
- [ ] **Step 3: Run** `python3 tools/routing_lab/lab.py solver-setup` once it exists, so the solver tests run here.
- [ ] **Step 4: Implement** `problem`, `ask`, `solver-setup`, and `solve.py` with rule `copper` (rule `firmware` answers exit 2 "not built yet" until Task 6).
- [ ] **Step 5: Run all tests.** Expected: pass, none skipped on this machine.
- [ ] **Step 6: Commit** `Routing lab: exact search for any copper (CP-SAT in its own environment)`.

---

### Task 6: The firmware-shaped rule

**Files:**
- Modify: `tools/routing_lab/solver/solve.py`, `tools/routing_lab/tests/test_solver.py`

**Interfaces:**
- Consumes: Task 5's `solve.py` contract. Produces: the same contract for `"rule": "firmware"`.

**The model (binding):** the wire and crosspoint booleans of Task 5. For each bridge, one unit of flow from its first wire to its second through its net's closed crosspoints, using at most four crosspoints, with at most one unit into any wire on the way. Paths of one net may use the same crosspoint; it is counted once in the objective.

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run to see them fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run all tests.** Expected: pass.
- [ ] **Step 5: Commit** `Routing lab: exact search for firmware-shaped paths`.

---

### Task 7: Verdicts the lab stands behind, and `lab.py ceiling`

**Files:**
- Modify: `tools/routing_lab/ceiling.py`, `tools/routing_lab/lab.py` (`ceiling` command; `clean` also removes `build/ceiling`), `tools/routing_lab/tests/test_solver.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `ceiling.problem`, `ceiling.ask`, `copper.paint`, `lab.fully_routed`.
- Produces:
  - `ceiling.faults(problem, closed, rule) -> list[str]`: what is wrong with an answer by the lab's own model, empty when it holds: a crosspoint that was not offered; a wire closed for two nets; a bridge whose wires the closed crosspoints of its net do not join; under `firmware`, a bridge whose shortest way through its net's closed crosspoints is more than four.
  - `ceiling.verdict(result, rule="firmware", seconds=20.0, use_cache=True, fewest=True) -> dict`:
    `{"verdict": "routable" | "not_routable" | "unknown" | "nothing", "fewest_proved": bool, "crosspoints": int | None, "router_crosspoints": int, "closed": [...], "seconds": float, "error": str | None}`.
    - `nothing`: `problem` is `None`.
    - A `routable` answer with faults becomes `unknown` with `error` = "the solver's answer fails the lab's own check: <first fault>".
    - A `not_routable` answer for a result with `lab.fully_routed(result)` and no problems becomes `unknown` with `error` = "the solver says this cannot be routed, yet the router routed it: the model is wrong" (Review Focus 2).
    - `router_crosspoints` counts the closed crosspoints of primary paths in the paint (`dup` false).
    - Cached in `build/ceiling/<sha256 of problem, rule, seconds, fewest and solve.py>.json`; an answer with an `error` is not cached.
  - `lab.py ceiling [--variant V] [--classes dense,real] [--case NAME] [--rule firmware|copper] [--seconds 20]`: one line per case (router routed/primaries, the router's primary crosspoints, the verdict, the fewest when routable, `=` when proved and `<=` when not), then: `provably routable: N of M; the router routes K of those in full`, `the router uses X more crosspoints than the fewest over the P cases where both are known`, and any case with an `error`. Exit 1 if any verdict has an `error` or the solver is missing (with the setup line), else 0.

- [ ] **Step 1: Write the failing tests**

```python
class Standing(unittest.TestCase):
    def test_faults_of_made_up_answers(self):
        p = ceiling.problem(tiny_paint([(1, 3, 6, "unrouted"), (2, 4, 7, "unrouted")]), ceiling.graph(TINY))
        good = [["A", 0, 0, 6], ["B", 0, 0, 6], ["A", 1, 1, 7], ["B", 1, 1, 7]]
        self.assertEqual(ceiling.faults(p, good, "firmware"), [])
        self.assertTrue(ceiling.faults(p, good[:3], "copper"))                              # 2-4 not joined
        self.assertTrue(ceiling.faults(p, good[:2] + [["A", 0, 1, 7], ["B", 0, 1, 7]], "copper"))   # L0 in two nets
        self.assertTrue(ceiling.faults(p, good + [["Z", 0, 0, 6]], "copper"))               # not offered
    def test_a_wrong_answer_is_unknown_with_the_reason(self):
        with mock.patch.object(ceiling, "ask", return_value={"verdict": "routable", "fewest_proved": True, "closed": [], "seconds": 0.1}):
            v = ceiling.verdict(ROUTED_RESULT, use_cache=False)
        self.assertEqual(v["verdict"], "unknown"); self.assertIn("lab's own check", v["error"])
    def test_not_routable_against_a_full_routing_is_the_models_fault(self):               # Review Focus 2
        with mock.patch.object(ceiling, "ask", return_value={"verdict": "not_routable", "fewest_proved": False, "closed": [], "seconds": 0.1}):
            v = ceiling.verdict(ROUTED_RESULT, use_cache=False)
        self.assertEqual(v["verdict"], "unknown"); self.assertIn("the model is wrong", v["error"])
    def test_a_crashed_result_has_nothing_to_ask(self):
        self.assertEqual(ceiling.verdict(CRASHED_RESULT)["verdict"], "nothing")

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
        self.assertEqual(ceiling.verdict(by["max_bridges_random"], "copper")["verdict"], "routable")
    def test_a_case_with_a_proved_fewest(self):
        v = ceiling.verdict(runner.run_case(NEW, dense("same_chip_pairs")), "firmware")
        self.assertEqual((v["verdict"], v["fewest_proved"], v["crosspoints"], v["router_crosspoints"]), ("routable", True, 16, 16))
```

The first run of this class takes about two minutes (the dense suite twice at up to 5 s a case, and `max_bridges_random` runs its full 20 s); after that the answers come from `build/ceiling`.

`ROUTED_RESULT` is `runner.run_case(NEW, dense("same_chip_pairs"))` and `CRASHED_RESULT` the crashed result of Task 2's test. In `test_cli.py`: `lab.py ceiling --case same_chip_pairs` prints `routable` and `= 16`, exit 0; with `ceiling.SOLVER_PYTHON` patched away it prints the setup line and exits 1. In `test_export.py` the clean test also makes `ceiling` and `solver-venv` directories: `clean` removes the first and keeps the second.

- [ ] **Step 2: Run to see them fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run all tests, then** `python3 tools/routing_lab/lab.py ceiling --classes dense,real,beyond`. Read the table: put the three summary lines in the commit message body.
- [ ] **Step 5: Commit** `Routing lab: solver verdicts checked by the lab's own model; lab.py ceiling`.

---

### Task 8: The solver on the page

**Files:**
- Modify: `tools/routing_lab/server.py`, `tools/routing_lab/web/lab.js`, `web/lab.css`, `web/index.html`, `tools/routing_lab/tests/test_server.py`

**Interfaces:**
- Consumes: `ceiling.verdict`, `ceiling.solver_installed`.
- Produces:
  - `/api/info` gains `"solver": bool`.
  - `POST /api/ceiling` with `{"variant": <hash>, "case": <name>, "rule": "firmware" | "copper", "seconds": number}` answers `ceiling.verdict(...)` plus `"paint": {"crosspoints": [{"chip", "x", "y", "net"}], "wires": {name: {"nets": [net]}}}` built from `closed` (empty when not routable). `seconds` is clamped to 1..120. 404 for an unknown run or case, 400 for an unknown rule, 409 with the setup line in `hint` when the solver is not installed.

**What the page does:** the case panel gains a section "Ceiling" under the bridges: two buttons, `firmware-shaped paths` and `any copper`, and a seconds box (20). Pressing one shows "asking the solver..." and disables both until the answer:
- `routable`: "Can be routed, proved. Fewest crosspoints: 22 (proved)" or "... at most 24 (not proved in 20 s)", then "the router's primaries use 26", and a checkbox `draw the solver's routing`, which draws it against the router's exactly as "compare with baseline" draws a baseline (copper only the router closes outlined, copper only the solver closes dashed grey). It and "compare with baseline" turn each other off.
- `not_routable`: "Cannot be routed, proved (firmware-shaped paths)". Under `firmware` it adds "try any copper to see whether the limit is the path shape or the fabric".
- `unknown`: "Not known after 20 s", or the `error` in red when there is one.
- `nothing`: "No bridge the firmware allowed".
- With `info.solver` false the section shows the setup line and no buttons. An exported page has no section.

- [ ] **Step 1: Write the failing tests** in `test_server.py`: `info.solver` is a boolean; `/api/ceiling` with `ceiling.verdict` patched to a fixed routable answer returns it with a `paint` whose `wires` name every wire the closed crosspoints touch; an unknown rule is 400; an unknown case is 404; with the solver patched away it is 409 with `lab.py solver-setup` in `hint`; `seconds: 100000` reaches `ceiling.verdict` as 120.
- [ ] **Step 2: Run to see them fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Check it in the browser:**
  1. `same_chip_pairs`, firmware-shaped: "Fewest crosspoints: 16 (proved)" and "the router's primaries use 16"; drawing the solver's routing shows at most a few outlined or dashed crosspoints.
  2. Class beyond, `every_nano_pin`: "Cannot be routed, proved" under both buttons. `max_bridges_random`, any copper: "Can be routed, proved ... at most N (not proved in 20 s)"; firmware-shaped: "Not known after 20 s".
  3. Stop the server, move `build/solver-venv` aside, start it: the section shows the setup line. Put it back.
  4. While the solver is asked, the buttons are disabled and the rest of the page still answers.
- [ ] **Step 5: Commit** `Routing lab page: ask the solver, see its verdict and its routing`.

---

### Task 9: Edge cases, the headline score, documents

**Files:**
- Create: `tools/routing_lab/edge.py`, `tools/routing_lab/tests/test_edge.py`, `tools/routing_lab/cases/edge/*.json`
- Modify: `tools/routing_lab/lab.py` (`edge` command, `CLASSES`), `tools/routing_lab/README.md`, `CodeDocs/DESIGN_ROUTING_LAB.md` (status), `tools/routing_lab/web/lab.js` (the `edge` class ticked by default)

**Interfaces:**
- Consumes: `generators.legal`, `generators.fuzz`'s way of drawing ends, `runner.run_case`, `ceiling.verdict`, `cases.Case`, `cases.save_json`.
- Produces:
  - `edge.draw(rng, longest=80) -> list[(int, int)]`: `longest` random bridges, ends drawn as `generators.fuzz` draws them (a row 60 times in 100, else a special node), a pair kept only if the list stays `generators.legal`. Every prefix is then legal too.
  - `edge.grow(binary, rng, name, seconds=20.0, longest=80, rule="firmware") -> (cases.Case, dict) | None`: draws one list, then finds by bisection the longest prefix the solver proves routable. Each probe routes the prefix with the harness (so the netlist is the firmware's: its nets, its probe feed, its refusals) and asks `ceiling.verdict(result, rule, seconds, fewest=False)`. `unknown` and `nothing` count as "not proved" and the search goes shorter. Returns the case for that prefix (class `edge`, `must_route` false, bridges with `dup` -1) and `{"bridges": k, "next_is": "not_routable" | "unknown" | "end"}` (`end`: all `longest` were proved), or `None` when not even one bridge is proved routable.
  - `lab.py edge --seed 1 --count 12 [--seconds 20] [--longest 80]`: writes `cases/edge/edge_<seed>_<i>.json`, with notes "proved routable with firmware-shaped paths (K bridges); one more bridge: not routable, proved" or "...; one more bridge: not known after 20 s". Skips a file that exists. Exits 1 with the setup line when the solver is not installed. By the measurements above this takes about two minutes a case.
  - `"edge"` joins `lab.CLASSES` (cases from files only, no generator). `lab.py run --classes edge` is the headline: the share of provably routable netlists at the edge that the router routes in full.

A kept case is proved routable in its own right; bisection only decides where to look, so the edge may sit a bridge short of the true one where routability is not monotone (a refused bridge, a probe feed that moves). "Provably routable with firmware-shaped paths" is a ceiling for any router that keeps the firmware's path shape, not a claim that this router's method could reach it: the model does not hold the copper the firmware reserves for sense taps.

- [ ] **Step 1: Write the failing tests** in `tests/test_edge.py`:

```python
def pretend(verdict_of):
    """No harness, no solver: a 'result' is the number of bridges, and the verdict is verdict_of(that number)."""
    return (mock.patch.object(runner, "run_case", side_effect=lambda binary, case, **kw: len(case.bridges)),
            mock.patch.object(ceiling, "verdict", side_effect=lambda n, *a, **kw: {"verdict": verdict_of(n), "error": None}))

class Edge(unittest.TestCase):
    def grown(self, verdict_of, longest=20):
        run, ask = pretend(verdict_of)
        with run, ask:
            return edge.grow(None, random.Random(1), "edge_t", longest=longest)

    def test_bisection_keeps_the_longest_prefix_proved_routable(self):
        case, info = self.grown(lambda n: "routable" if n <= 7 else "not_routable")
        self.assertEqual((len(case.bridges), info), (7, {"bridges": 7, "next_is": "not_routable"}))
        self.assertEqual((case.name, case.cls, case.must_route), ("edge_t", "edge", False))
        self.assertTrue(all(dup == -1 for _, _, dup in case.bridges))
    def test_unknown_is_not_proof(self):
        case, info = self.grown(lambda n: "routable" if n <= 5 else "unknown")
        self.assertEqual((len(case.bridges), info["next_is"]), (5, "unknown"))
    def test_all_of_it_proved(self):
        case, info = self.grown(lambda n: "routable")
        self.assertEqual((len(case.bridges), info["next_is"]), (20, "end"))
    def test_nothing_proved_gives_nothing(self):
        self.assertIsNone(self.grown(lambda n: "unknown"))
    def test_it_asks_few_times(self):                                 # bisection, not one probe per bridge
        run, ask = pretend(lambda n: "routable" if n <= 33 else "unknown")
        with run, ask as asked:
            edge.grow(None, random.Random(1), "edge_t", longest=80)
        self.assertLessEqual(asked.call_count, 9)
    def test_the_bridges_are_legal_and_every_prefix_is(self):
        pairs = edge.draw(random.Random(3), longest=80)
        self.assertEqual(len(pairs), 80)
        self.assertTrue(all(a != b for a, b in pairs))
        self.assertTrue(all(generators.legal(pairs[:k]) for k in range(1, 81)))
        self.assertEqual(pairs, edge.draw(random.Random(3), longest=80))          # the seed decides the list
    def test_committed_edge_cases_load_and_are_in_the_battery(self):
        found = lab.battery(["edge"])
        self.assertEqual(len(found), 12)
        self.assertTrue(all(c.cls == "edge" and "proved routable" in c.notes for c in found))

    @unittest.skipUnless(ceiling.solver_installed(), NEEDS_SOLVER)
    def test_a_committed_edge_case_is_still_proved_routable(self):    # one case, so the suite stays quick
        binary = variants.build(variants.resolve("worktree"))
        v = ceiling.verdict(runner.run_case(binary, lab.battery(["edge"])[0]), "firmware", seconds=20, fewest=False)
        self.assertEqual((v["verdict"], v["error"]), ("routable", None))
```

- [ ] **Step 2: Run to see them fail.**
- [ ] **Step 3: Implement** `edge.py`, the command, the class.
- [ ] **Step 4: Generate** `python3 tools/routing_lab/lab.py edge --seed 1 --count 12` (about 25 minutes; run it in the background), then `python3 tools/routing_lab/lab.py run --classes edge`. Record the headline: cases fully routed of 12, bridges routed of all, and the `missed` total. If fewer than 12 files come out (a list of which not one bridge is proved), run further seeds until there are 12.
- [ ] **Step 5: Run all tests.**
- [ ] **Step 6: Documents.** README: a section "Ceilings" (what `miss` and `spare` mean and their limits; `solver-setup`, `ceiling`, `edge`; the two rule sets in one sentence each; what a verdict is worth: a "routable" is checked by the lab's own model, a "not routable" rests on the solver and on the tests with small fabrics; the headline number with its date), and "Findings so far" gains whatever `lab.py ceiling` and the edge run showed. Design: status line (piece 3 built), and under "Honest limit" that the firmware's tap planner is not yet used as the oracle for spare copies.
- [ ] **Step 7: Commit** `Routing lab: edge cases grown to what provably fits; the headline score; docs`.

---

## Not in this plan

- **The tap planner as oracle for spare copies** (the design's follow-on). Spare copies stay labelled "available in copper". A cheap first answer needs no new code: route the same case with every stack setting at its highest and see how many copies the firmware makes.
- **Blocked wires** in the searches. Plan 4 adds them with the lane ranking.
- **Solver verdicts in an exported page**, and running the solver over a whole battery from the page. `lab.py ceiling` does the batch.

## After this plan

Plan 4 (V6 lane ranking) blocks a wire and re-runs the battery; with this plan it can ask the same of the solver, to tell "the copper needs this lane" from "this router happens to use it".
