# Routing lab, plan 4: arrangements and the lane ranking

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the crossbar arrangement a small file that is easy to change, say what any arrangement can route, and rank V5's 94 lanes, bounce rows and hub lanes by what is lost without each, with the probe feed off the fabric as V6 will have it.

**Architecture:** An arrangement is V5 plus what differs, read by a new `arrangement.py` into the four tables the fabric model already has (`CHIPS`, `X_NET`, `Y_NET`, `NODE_NET`). The copper searches and the exact solver take those tables as they are; nothing in the solver changes. The firmware's router can route an arrangement only when it is V5 with pins taken away, which the harness already does by blocking pins. A new `rank.py` takes one wire away at a time, asks the router what is lost, then asks the solver whether the copper needed the wire. The page gets an arrangement picker, a fabric drawing generated for any arrangement, and a ranking tab.

**Tech Stack:** Python 3 standard library; the existing harness, unchanged; the existing CP-SAT solver in `build/solver-venv`; the existing page (plain JS, SVG).

**Spec:** `CodeDocs/DESIGN_ROUTING_LAB.md`, "Piece 4: arrangements and the V6 lane ranking" (widened 2026-11-22), "How we know it works". `CodeDocs/V6_CROSSBAR_MATRIX.md` for what Kevin wants to try (P1 to P5, A1 to A4) and why the firmware's router cannot route a changed fabric (section 7). `tools/routing_lab/README.md` for what exists.

## Global Constraints

- Nothing under `src/` is edited. `test/hil/` is read, not edited. Nothing under `tools/routing_lab/harness/` is edited (the board check is recorded for the harness's hash).
- One commit per task, never pushed. No attribution lines in commit messages. Never touch `.github/workflows/release.yml`. Stage files by name; `.pio/**/firmware.uf2` is tracked and must not be committed.
- The lab itself imports only the standard library. `ortools` is imported in `solver/solve.py` and nowhere else.
- **Say who answered.** Every table, command and page view that shows a routing or a score names three things: the engine (the firmware's router, or the exact solver), the arrangement, and whether the probe feed is on the fabric.
- **Two engines, never mixed up.** The firmware's router runs an arrangement only when that is V5 with pins taken away. Asked for any other, it refuses and says which pin is the reason. The solver takes any arrangement.
- **The solver's answer for a changed arrangement is a ceiling.** It says what a router that keeps the path shape (each bridge its own path of at most four crosspoints; `MAX_HOPS` in `solver/solve.py` stays 4) could reach, not what a V6 router would do. Every place that shows it says "exact solver".
- **The router's loss is signed and is not the answer to "needed".** With a wire taken away the router sometimes routes more. "Needed" is said of a wire only on a proof: the solver finds no routing without it. "Not needed" is said only on a routing that does without it. Anything else is "unknown".
- The model is the checker's: a wire carries one net; a crosspoint joins an X wire and a Y wire on one chip; a real node outside the net may not be touched. A pin taken away is no copper at all: no crosspoint on it is offered or used.
- Resistance stays in units of one crosspoint; the page multiplies by its ohms box (42 by default).
- On the page red means a problem and nothing else is red. The ranking's heat uses no red.
- Tests: `python3 -m unittest discover -s tools/routing_lab/tests -t tools/routing_lab` passes with the solver installed and without it (solver tests skip, saying why).

## Measured before writing this plan (2026-11-22, router at 5374d38)

Throwaway prototypes, for sizing. The tasks' tests are what must hold.

- **The feed turns off cleanly.** A case with `probe=(0, x)` has no feed bridge. Over dense, real, typical, stress and edge (256 cases): fully routed 245 with the feed off, 244 with it on.
- **94 wires to rank**: 48 lanes between breadboard chips, 32 from a breadboard chip to an SF chip, 8 bounce rows, 6 hub lanes.
- **Usage is no guide.** Counting the cases (of 256, feed off) in which a wire carries a net: least used are IJ (10), `/EH1` (15), JL (17), `/EG1` (18); most used are the eight lanes into K (215 to 226) and the bounce rows (211 to 220). No wire goes unused.
- **Blocking a wire costs 1.5 s** for those 256 cases, so all 94 take about two and a half minutes; with the 2,000 fuzz cases as well, about twenty. A blocked wire had no crosspoint in any result, and no case crashed, shorted or strayed.
- **The router is not monotone.** With `/AB0` blocked it routes one primary more (2,988 against 2,987). With `/AE0` blocked one more case routes in full and one primary fewer. IJ, used in only 10 cases, costs 9 primaries; AK costs 4; chip A's bounce row costs 5.
- **Net 59 is far away.** A blocked pin is claimed for net 59. The highest real net in the battery is 34 (dense); the edge class reaches 23.
- **The edge proofs survive the feed coming off**: with the feed's own crosspoints dropped, all 12 still pass `ceiling.faults` against the feed-off netlist. The router still routes 1 of the 12 in full.
- **A changed arrangement can be scored with no change to the solver.** `ceiling.problem(paint, g)` already takes the graph. Tried on V6_CROSSBAR_MATRIX's P1 + P2 (feed off; on each breadboard chip the second lane of three doubled pairs given to TOP_RAIL, BOTTOM_RAIL and GND, pairs AD AF AH BC BE BG CD CH DG EF EH FG), against V5 with the feed off, firmware-shaped paths, 10 s a case, the 23 dense and real netlists:
  - All 23 are routable on both.
  - Over the 20 whose fewest is proved on both: 505 crosspoints on V5, 459 on the arrangement.
  - `gnd_spread` at most 16 against 8, `rail_stacking_light` 10 against 6, `isense_loop_stacked` 8 against 7, `k_rows_overflow_metric` 26 against 18, `big_net_thirteen_nodes` at most 20 against 12.
  - 134 s for the lot.
- **The edge of what fits separates those two on one random list of two.** Grown with the feed off, the edge class's first list reaches 54 bridges on both (the 55th proved not to fit on both); its second reaches 61 on V5 and 67 on the arrangement (the next not known in 20 s on either). About a minute and a half a list an arrangement. So the score leads with verdict changes and fewest crosspoints, and offers the lengths as well.
- **The feed itself costs capacity.** That second list fits 54 bridges with the feed on V5's fabric and 61 with it off.
- **A wire is proved needed, or not, in about a second.** With the feed off `k_rows_overflow_metric` routes, and the solver proves it cannot without any one of the eight lanes into K; the other eight rankable wires its routing uses are proved not needed (16 questions, 24 s). `nano_dense_metric`, `gpio_seven_from_chip_a` and `k_rows_all_eight` need none of the wires their routings use (28, 19 and 7 questions; 44, 15 and 6 s). A first guess, that `k_rows_all_eight` needs every K lane, was wrong: only a measurement goes into a test.
- **The lab matches a board on a netlist made by hand.** A `b` report Kevin pasted (10 bridges, 8 duplicates) and the lab's routing of the same bridges close the same crosspoints in 51 of 52 places; the one that differs is the probe feed's GPIO (8 on his board, 6 in the lab).

## File structure

| File | Responsibility |
|---|---|
| `tools/routing_lab/arrangement.py` (new) | The arrangement file format: load, check, the V5 base, what differs from V5, whether the firmware's router can run it and with which pins blocked |
| `tools/routing_lab/arrangements/*.json` (new) | Arrangements. Ships `v6_feed_off` and `v6_rails_on_chips` |
| `tools/routing_lab/score.py` (new) | Two arrangements asked the same netlists by the solver, and how far the random lists grow on each |
| `tools/routing_lab/edge.py` (modify) | Growing a list on an arrangement |
| `tools/routing_lab/rank.py` (new) | The rankable wires, usage, removal with the router, and whether the copper needs a wire |
| `tools/routing_lab/ceiling.py` (modify) | A graph skips pins taken away; `problem` says what it could not place; `verdict`, `painted` and a new `solved` take an arrangement |
| `tools/routing_lab/runner.py` (modify) | A battery on an arrangement: the feed, the blocks, the judge's searches on the right copper, the net 59 guard |
| `tools/routing_lab/fabric_view.py` (modify) | The fabric drawing for any arrangement |
| `tools/routing_lab/lab.py`, `server.py` (modify) | `arrangement list/show/check/score`, `rank`, `--arrangement` on `run` and `ceiling`; `/api/fabric`, `/api/rank`, `/api/job`; arrangements in `/api/info`, `/api/run`, `/api/ceiling` |
| `tools/routing_lab/web/lab.js`, `lab.css`, `index.html` (modify) | The arrangement picker, the drawing of any arrangement, the solver's routing as the picture, the ranking tab |
| `tools/routing_lab/tests/test_arrangement.py`, `test_score.py`, `test_rank.py` (new), others (modify) | Tests |

## Review Focus

The inputs the design is silent on that are most likely to bite. Each has its test in the task named.

1. **An arrangement file with a mistake in it** (a pin that does not exist, a chip named twice, a lane left with one end, a node on no pin, a misspelt key, broken JSON). Every problem is listed with the pin or name it is about, nothing runs on it, and the page shows the list, not a stack trace (Task 1, Task 4).
2. **A netlist that uses a node the arrangement does not have.** It is "cannot be placed", with the bridges named: never "not routable", never a routing miss, and never quietly asked without those bridges (Task 1's rule for a node that loses its pin, Task 2 for the solver, Task 3 for the router).
3. **A netlist that reaches net 59 while pins are blocked.** The harness marks blocked pins with that number and the judge wipes it from the chip status. Such a case is refused with the reason (Task 3).
4. **The firmware's router asked for an arrangement it cannot route.** Refused, naming the first pin that is not V5's, and pointing at the solver's command (Task 3, Task 4).
5. **A wire taken away, offered again by a search.** `missed`, `spare` and `problem` must not pass a pin that is gone, or the miss column and the solver's verdicts are about V5, not the arrangement (Task 2, Task 3).
6. **A wire whose removal makes the router do better, and a solver that runs out of time.** The gain is shown as a gain, not clipped to zero; "unknown" is never counted as needed or as not needed (Task 6, Task 7).
7. **A wire of a shape the drawing has never seen** (a rail on nine pins, a lane to a thirteenth chip). It is drawn on a track of its own, crossing no other wire's track, and nothing raises (Task 4).

---

### Task 1: Arrangements as files

**Files:**
- Create: `tools/routing_lab/arrangement.py`, `tools/routing_lab/arrangements/v6_feed_off.json`, `tools/routing_lab/arrangements/v6_rails_on_chips.json`, `tools/routing_lab/tests/test_arrangement.py`
- Modify: `tools/routing_lab/lab.py` (`arrangement list|show|check`), `tools/routing_lab/tests/test_cli.py`

**Interfaces:**
- Consumes: `test/hil/fabric_v5.py` (`CHIPS`, `X_NET`, `Y_NET`, `NODE_NET`, `NODE_NAME`).
- Produces:
  - **The file**, `arrangements/<name>.json`, one JSON object. Only `base` is required; an unknown key is a problem.
    - `"about"`: one line of text.
    - `"base"`: `"v5"`, the only base there is.
    - `"feed"`: `true` (the default) when the probe feed is routed through the fabric, `false` when it is not.
    - `"remove"`: wire names. Every pin on such a wire is taken away.
    - `"pins"`: `{"A.X7": "TOP_RAIL", "K.X2": null}`. A name puts the pin on that wire, joined to every other pin of that name (a new name is new copper). `null` takes the pin away.
    - `"chips"`: `{"M": {"role": "sf", "x": [16 names or null], "y": [8 names or null]}}`. A new chip: one capital letter not in use, role `"bb"` or `"sf"`.
    - `"nodes"`: `{"150": {"wire": "PORT_0", "name": "PORT_0"}, "139": null}`. A node added or moved to a wire; `null` removes the node.
  - `arrangement.Arrangement`: a plain object with `name`, `about`, `feed`, `CHIPS` (a string), `X_NET`, `Y_NET` (lists per chip, `None` for a pin taken away), `NODE_NET`, `NODE_NAME`, `ROLE` (`{chip: "bb" | "sf"}`; A to H are `bb`, I to L `sf`), `changed` (sorted `(chip, axis, pin)` of every pin whose wire is not V5's, a new chip's pins included), `taken` (those that are `None`) and `dropped` (sorted ids of the base's nodes that the changes leave on no pin; they are not in `NODE_NET`).
  - `arrangement.V5`: the base itself (`name` "v5", `feed` true, nothing changed). `arrangement.base(feed) -> Arrangement`: V5's copper with the feed on (that is `V5`) or off (named "v5, feed off"). This is what the harness builds a netlist on when the arrangement itself is one the router cannot run.
  - `arrangement.RouterCannot` (a `ValueError`): what Task 3's runner raises when asked to route an arrangement that is not V5 with pins taken away.
  - `arrangement.check(data: dict) -> list[str]`: every problem, each naming its pin, wire, chip, node or key. Empty when the file is good.
  - `arrangement.parse(name, data) -> Arrangement`; `arrangement.load(name) -> Arrangement`, `name` being "v5", a file's stem under `arrangement.DIR`, or a path ending `.json`. Both raise `arrangement.Bad` (a `ValueError` with `.problems`, the list from `check`; a missing file or broken JSON is one problem).
  - `arrangement.names() -> list[str]`: "v5" first, then the files' stems, sorted.
  - `arrangement.blocks(a) -> list[("X" | "Y", chip index, pin)] | None`: the harness's block list when `a` is V5 with pins taken away and nothing else (same chips, same nodes, every pin that is left on V5's wire). `None` otherwise.
  - `arrangement.why_not_router(a) -> str | None`: `None` when `blocks(a)` is a list; else one sentence naming the first difference, such as `"A.X7 is on TOP_RAIL, not on /AD1 as V5 has it"`.
  - `lab.py arrangement list` (name, feed on or off, engine: "router and solver" or "solver only", about), `lab.py arrangement show NAME` (every chip's X and Y wires, a changed pin marked `*`, a taken pin shown as `-`; then nodes added, moved or dropped; then the engine line with `why_not_router`), `lab.py arrangement check NAME` (the problems, exit 1; or "NAME: good", exit 0).

**Rules `check` enforces (binding):** `base` is "v5". A pin is `CHIP.Xn` with n 0 to 15 or `CHIP.Yn` with n 0 to 7 on a chip of the arrangement, and its value is a string or `null`. A removed wire is a wire of the base. A new chip's letter is one capital not already a chip, its role is `bb` or `sf`, its `x` has 16 entries and its `y` 8. A node's key is a whole number, and a node the file itself places must be on a wire that has a pin after every change. A wire that had two or more pins in V5 and is left on exactly one is a problem ("take the wire away with `remove`, or give the pin another wire"): half a lane is a mistake, not a design. With `"feed": true`, the feed's own node (139, BUF_IN) must still have a pin.

**A node that loses its only pin (binding):** taking a base node's last pin away is allowed, and is how a pin is freed for another use (`"pins": {"K.X2": null}` once the feed is off). The node then drops out of the arrangement: it is in `dropped`, not in `NODE_NET`. For both engines a netlist with a bridge on a dropped node "cannot be placed" (Tasks 2 and 3): it is never a routing miss and never "not routable".

**The shipped arrangements:**
- `v6_feed_off.json`: `{"about": "V5's copper with the probe feed off the fabric, as V6 will have it", "base": "v5", "feed": false}`.
- `v6_rails_on_chips.json`: feed off, and V6_CROSSBAR_MATRIX's P1. For each of the pairs AD AF AH BC BE BG CD CH DG EF EH FG, both pins of the lane `/<pair>1` are given to rails: on each breadboard chip the three pins so freed become, in pin order, TOP_RAIL, BOTTOM_RAIL and GND. Its `about` says so.

- [ ] **Step 1: Write the failing tests** in `tests/test_arrangement.py`:

```python
V5 = arrangement.V5

class Files(unittest.TestCase):
    def test_v5_is_the_fabric_model_as_it_is(self):
        self.assertEqual((V5.name, V5.feed, V5.CHIPS), ("v5", True, "ABCDEFGHIJKL"))
        self.assertEqual((V5.X_NET, V5.Y_NET, V5.NODE_NET), (fabric_v5.X_NET, fabric_v5.Y_NET, fabric_v5.NODE_NET))
        self.assertEqual((V5.changed, V5.taken, arrangement.blocks(V5)), ([], [], []))
        self.assertEqual("".join(V5.ROLE[c][0] for c in V5.CHIPS), "bbbbbbbbssss")

    def test_a_pin_given_another_wire_and_a_pin_taken_away(self):
        a = arrangement.parse("t", {"base": "v5", "feed": False, "remove": ["/AD1"], "pins": {"A.X7": "TOP_RAIL", "K.X2": None}})
        self.assertEqual((a.X_NET["A"][7], a.X_NET["D"][1], a.X_NET["K"][2]), ("TOP_RAIL", None, None))
        self.assertEqual(fabric_v5.X_NET["A"][7], "/AD1")               # the base is never written to
        self.assertEqual(a.changed, [("A", "X", 7), ("D", "X", 1), ("K", "X", 2)])
        self.assertEqual(a.taken, [("D", "X", 1), ("K", "X", 2)])
        self.assertEqual((a.dropped, 139 in a.NODE_NET), ([139], False))        # BUF_IN had that one pin: the node is gone
        self.assertEqual(V5.dropped, [])
        # the same file with the feed left on the fabric is a mistake: the feed's node has no pin
        self.assertTrue(any("139" in p or "BUF_IN" in p for p in arrangement.check({"base": "v5", "pins": {"K.X2": None}})))
        # and half a lane is one too: A.X7 moved, /AD1 left on D alone
        self.assertTrue(any("/AD1" in p for p in arrangement.check({"base": "v5", "pins": {"A.X7": "TOP_RAIL"}})))

    def test_the_router_can_run_only_v5_with_pins_taken_away(self):
        gone = arrangement.parse("t", {"base": "v5", "feed": False, "remove": ["KL", "/AB1"]})
        self.assertEqual(sorted(gone.taken), [("A", "X", 3), ("B", "X", 1), ("K", "X", 12), ("L", "X", 14)])
        self.assertEqual(sorted(arrangement.blocks(gone)), [("X", 0, 3), ("X", 1, 1), ("X", 10, 12), ("X", 11, 14)])
        self.assertIsNone(arrangement.why_not_router(gone))
        self.assertIs(gone.feed, False)
        rewired = arrangement.parse("t", {"base": "v5", "remove": ["/AD1"], "pins": {"A.X7": "TOP_RAIL"}})
        self.assertIsNone(arrangement.blocks(rewired))
        self.assertIn("A.X7", arrangement.why_not_router(rewired))
        self.assertIn("TOP_RAIL", arrangement.why_not_router(rewired))

    def test_a_chip_and_a_node_added_and_a_node_removed(self):
        m = {"role": "sf", "x": ["TOP_RAIL", "BOTTOM_RAIL", "GND", "PORT_0"] + [None] * 12, "y": ["AM", "BM"] + [None] * 6}
        a = arrangement.parse("t", {"base": "v5", "chips": {"M": m}, "remove": ["/AD1", "/BD1"],
                                    "pins": {"A.X7": "AM", "B.X7": "BM"},
                                    "nodes": {"150": {"wire": "PORT_0", "name": "PORT_0"}, "139": None}})
        self.assertEqual((a.CHIPS, a.ROLE["M"], a.Y_NET["M"][:2]), ("ABCDEFGHIJKLM", "sf", ["AM", "BM"]))
        self.assertEqual((a.NODE_NET[150], a.NODE_NAME[150], 139 in a.NODE_NET), ("PORT_0", "PORT_0", False))
        self.assertEqual(len([p for p in a.changed if p[0] == "M"]), 24)        # every pin of a new chip is a change
        self.assertIsNone(arrangement.blocks(a))

    def test_what_is_wrong_with_a_file_is_listed_by_name(self):                # Review Focus 1
        bad = {"base": "v9", "feeed": True, "remove": ["NO_SUCH_WIRE"],
               "pins": {"A.X16": "x", "Q.Y1": "y", "A.Z1": "z", "A.X2": 5, "A.X3": None},
               "chips": {"A": {"role": "bb", "x": [None] * 16, "y": [None] * 8}, "mm": {}, "N": {"role": "hub", "x": [], "y": []}},
               "nodes": {"1": {"wire": "NOWHERE"}, "one": None}}
        problems = arrangement.check(bad)
        for part in ("v9", "feeed", "NO_SUCH_WIRE", "A.X16", "Q.Y1", "A.Z1", "A.X2", "/AB1", "chip A", "mm", "hub", "16", "node 1", "one"):
            self.assertTrue(any(part in p for p in problems), (part, problems))
        with self.assertRaises(arrangement.Bad) as cm:
            arrangement.parse("t", bad)
        self.assertEqual(cm.exception.problems, problems)
        self.assertEqual(arrangement.check({"base": "v5"}), [])
        self.assertEqual(arrangement.check({"base": "v5", "remove": ["/AB1"]}), [])      # both ends go: no half lane

    def test_the_shipped_arrangements(self):
        self.assertEqual(arrangement.names()[0], "v5")
        self.assertLessEqual({"v6_feed_off", "v6_rails_on_chips"}, set(arrangement.names()))
        off = arrangement.load("v6_feed_off")
        self.assertEqual((off.feed, off.changed, arrangement.blocks(off)), (False, [], []))
        rails = arrangement.load("v6_rails_on_chips")
        self.assertEqual((rails.feed, len(rails.changed), rails.taken), (False, 24, []))
        for chip in "ABCDEFGH":
            freed = [w for w, was in zip(rails.X_NET[chip], fabric_v5.X_NET[chip]) if w != was]
            self.assertEqual(freed, ["TOP_RAIL", "BOTTOM_RAIL", "GND"], chip)
        self.assertIsNone(arrangement.blocks(rails))

    def test_a_file_that_is_missing_or_not_json(self):
        for name in ("no_such_arrangement", self.write("broken.json", '{"base": ')):
            with self.assertRaises(arrangement.Bad) as cm:
                arrangement.load(name)
            self.assertEqual(len(cm.exception.problems), 1)
```

`self.write(name, text)` writes a file in a temporary directory and returns its path. In `test_cli.py`: `arrangement list` names all three with "router and solver" for the first two and "solver only" for the third; `arrangement show v6_rails_on_chips` marks 24 pins with `*` and ends with the sentence from `why_not_router`; `arrangement check` of a broken file prints its problems and exits 1; of `v6_feed_off` prints "good" and exits 0.

- [ ] **Step 2: Run** `python3 -m unittest discover -s tools/routing_lab/tests -t tools/routing_lab -k test_arrangement`. Expected: import error, no `arrangement`.
- [ ] **Step 3: Implement.** `check` first, `parse` on top of it (deep-copy the base tables, apply `chips`, `remove`, `pins`, `nodes` in that order).
- [ ] **Step 4: Run all tests.** Expected: pass.
- [ ] **Step 5: Commit** `Routing lab: the crossbar arrangement as a file (V5 plus what differs)`.

---

### Task 2: The copper tools on an arrangement

**Files:**
- Modify: `tools/routing_lab/ceiling.py`, `tools/routing_lab/tests/test_ceiling.py`, `tests/test_solver.py`

**Interfaces:**
- Consumes: Task 1's `Arrangement` (it has the four tables `ceiling.graph` reads).
- Produces:
  - `ceiling.graph(fabric)`: a pin whose wire is `None` adds no edge, no `ends` entry. Graphs are kept per fabric object for the base and for `arrangement.V5`; any other is built when asked.
  - `ceiling.problem(paint, g=None)` gains `"unplaced": [[n1, n2], ...]`: the bridges the firmware allowed whose node the graph does not have. They are not in `bridges`. `solve.py` ignores the key.
  - `ceiling.verdict(result, rule="firmware", seconds=20.0, use_cache=True, fewest=True, arrangement=None)`: asks on `arrangement`'s copper (V5's when `None`). Adds `"arrangement": name`, `"engine": "solver"`, `"unplaced": [...]`. When anything is unplaced the verdict is `"unplaced"`, nothing is asked and `error` is `None`. `router_crosspoints` is as before (it is about the result, whatever fabric is asked).
  - `ceiling.painted(result, arrangement=None)`: `missed` and `spare` searched on the arrangement's copper.
  - `ceiling.solved(result, answer, arrangement=None) -> dict`: a routable `verdict` answer as a paint of its own, on the arrangement's wires, for the page to draw as the picture: `nets` (from `copper.paint(result)`), `crosspoints` (`chip, x, y, net`, `dup` false, `path` None), `wires` (`{name: {"kind", "nets", "stray": False, "pins": [{"chip", "axis", "pin", "claim": None, "mark": None}]}}` for every wire of the arrangement), `bridges` (each bridge given: `state` "routed", `copies` 1, `hops` the crosspoints between its wires in the solver's copper, `r` its resistance there, `infra`), `problems` `[]`, `notes` (one line: "the exact solver's routing on <arrangement>: one of many, and not what the firmware's router did"), `status` "ok". `None` when the answer is not routable.
  - The cache key of `verdict` already holds the problem's crosspoints, so two arrangements never share an answer.

- [ ] **Step 1: Write the failing tests**

```python
class OnAnArrangement(unittest.TestCase):                              # test_ceiling.py
    def test_a_pin_taken_away_is_not_copper(self):                     # Review Focus 5
        gone = types.SimpleNamespace(**{**vars(TINY), "X_NET": {"A": ["L0", None], "B": ["L0", "L1"]}})
        g = ceiling.graph(gone)
        self.assertEqual(sorted(w for w, _ in g.edges["1"]), ["L0"])
        self.assertEqual([xp for xp in g.ends if xp[:2] == ("A", 1)], [])
        closed = [("A", 0, 0, 6), ("B", 0, 0, 6)]                      # 1-3 on L0; L1 has lost its end on chip A
        self.assertEqual(ceiling.spare(tiny_paint([(1, 3, 6, "routed")], closed, fabric=TINY), g)[0]["copies"], 0)
        self.assertIsNone(ceiling.missed(tiny_paint([(1, 3, 6, "unrouted")], riding={"L0": [7]}), g)[0]["path"])

    def test_a_bridge_on_a_node_the_arrangement_lacks_is_unplaced(self):     # Review Focus 2
        p = ceiling.problem(tiny_paint([(1, 3, 6, "unrouted"), (1, 77, 6, "unrouted")]), ceiling.graph(TINY))
        self.assertEqual((p["bridges"], p["unplaced"]), ([["1", "3", 6]], [[1, 77]]))
        self.assertEqual(ceiling.problem(tiny_paint([(1, 3, 6, "unrouted")]), ceiling.graph(TINY))["unplaced"], [])

class Arrangements(unittest.TestCase):                                 # test_solver.py
    def feed_off(self, name):
        return runner.run_case(NEW, dataclasses.replace(dense(name), probe=(0, 0)))

    def test_a_netlist_that_cannot_be_placed_is_not_asked(self):       # Review Focus 2
        without_row_1 = arrangement.parse("t", {"base": "v5", "nodes": {"1": None}})
        with mock.patch.object(ceiling, "ask", side_effect=AssertionError("asked")):
            v = ceiling.verdict(self.feed_off("same_chip_pairs"), arrangement=without_row_1, use_cache=False)
        self.assertEqual((v["verdict"], v["error"], v["arrangement"], v["engine"]), ("unplaced", None, "t", "solver"))
        self.assertTrue(v["unplaced"] and all(1 in pair for pair in v["unplaced"]))

    @unittest.skipUnless(ceiling.solver_installed(), NEEDS_SOLVER)
    def test_rails_on_every_chip_cost_fewer_crosspoints(self):
        r, rails = self.feed_off("rail_stacking_light"), arrangement.load("v6_rails_on_chips")
        on_v5, on_rails = ceiling.verdict(r), ceiling.verdict(r, arrangement=rails)
        self.assertEqual([(v["verdict"], v["fewest_proved"], v["crosspoints"]) for v in (on_v5, on_rails)],
                         [("routable", True, 10), ("routable", True, 6)])
        self.assertEqual((on_v5["arrangement"], on_rails["arrangement"]), ("v5", "v6_rails_on_chips"))
        p = ceiling.solved(r, on_rails, rails)
        self.assertEqual((len(p["crosspoints"]), p["status"], p["problems"]), (6, "ok", []))
        self.assertTrue(all(b["state"] == "routed" and b["r"] is not None and b["hops"] <= 4 for b in p["bridges"]))
        self.assertEqual(len(p["wires"]["TOP_RAIL"]["pins"]), 9)       # K's pin and one on each breadboard chip
        self.assertIn("exact solver", p["notes"][0])
        self.assertIsNone(ceiling.solved(r, dict(on_rails, verdict="unknown"), rails))
```

- [ ] **Step 2: Run to see them fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run all tests.** Expected: pass.
- [ ] **Step 5: Commit** `Routing lab: the copper searches and the solver take an arrangement`.

---

### Task 3: The firmware's router on an arrangement

**Files:**
- Modify: `tools/routing_lab/runner.py`, `tools/routing_lab/lab.py` (`run --arrangement`, `ceiling --arrangement`, the table's first line), `tools/routing_lab/tests/test_runner.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `arrangement.blocks`, `why_not_router`, `ceiling.graph`, `ceiling.missed`, the harness's `block` and `probe` lines (already there, see `cases.Case.to_protocol`).
- Produces:
  - `arrangement.RouterCannot` is raised with `why_not_router(a)` and "ask the solver: `python3 tools/routing_lab/lab.py arrangement score <name>`".
  - `runner.run_battery(v, cases, *, jobs=None, block=(), use_cache=True, arrangement=None)`: with an arrangement, every case runs with the feed as the arrangement has it (`probe[0]` 0 when `feed` is false) and the arrangement's pins blocked, besides any in `block`. Raises `RouterCannot` when `arrangement.blocks(a)` is `None`. Every result carries `"arrangement": name` ("v5" when none was given), `"feed": bool` and `"engine": "router"`. `run_case` takes the same `arrangement`.
  - The judge on an arrangement: `metrics["missed"]` is searched on the arrangement's copper, so a pin taken away is never part of a path it reports.
  - **A case on a node the arrangement dropped** is not given to the harness. Its result has status `"unplaced"`, no problems, the note `"cannot be placed on <arrangement>: it has no <node names>"`, and metrics all at their defaults. It is not fully routed, not a crash and not a regression, and `lab.exit_code` does not count it; `print_table` gains nothing but one line a case, `unplaced <class>/<case>: no <node names> on <arrangement>`.
  - The run cache on disk is keyed by the case's protocol text, which holds the feed and the blocked pins but not the arrangement's name: a result read from it is given the name of the arrangement asked for.
  - **The net 59 guard:** `runner.judge` with any pin blocked, on a report whose bridge array holds a net of `BLOCK_NET` or above, returns status `crash` with the one problem `"this netlist reaches net 59, the number blocked pins are marked with: it cannot be run with pins taken away"`.
  - `lab.py run --arrangement NAME` and `lab.py ceiling --arrangement NAME`. The first line of each table reads, for example, `arrangement: v6_feed_off (V5, no pin taken away, probe feed off)   engine: the firmware's router`, or `... engine: the exact solver, firmware-shaped paths`. For `run`, a `RouterCannot` is exit 2 with its text.
  - `lab.py ceiling --arrangement NAME` asks the solver on the arrangement's copper. The netlists are the firmware's: each case is run by the harness on the arrangement when the router can run it, else on `arrangement.base(a.feed)`, and in that second case the two router columns of the table show `-`, since the router routed another fabric.

- [ ] **Step 1: Write the failing tests**

```python
class OnAnArrangement(unittest.TestCase):                              # test_runner.py
    def test_the_feed_is_off_where_the_arrangement_has_none(self):
        r = runner.run_battery(V, [CASE18], arrangement=arrangement.load("v6_feed_off"))[0]
        self.assertEqual([b for b in copper.paint(r)["bridges"] if b["infra"]], [])
        self.assertEqual((r["metrics"]["primaries"], r["arrangement"], r["feed"], r["engine"]), (1, "v6_feed_off", False, "router"))
        plain = runner.run_battery(V, [CASE18])[0]
        self.assertEqual((plain["metrics"]["primaries"], plain["arrangement"], plain["feed"]), (2, "v5", True))

    def test_a_wire_taken_away_is_never_used(self):                    # the design's "a blocked wire never appears in any path"
        for wires in (["KL"], ["AK"], ["/AB0", "/AB1"], [copper.BOUNCE[0]], ["IJ", "IK", "IL"]):
            a = arrangement.parse("without", {"base": "v5", "feed": False, "remove": wires})
            for r in runner.run_battery(V, lab.battery(["dense", "stress"]), arrangement=a):
                self.assertNotIn(r["status"], ("crash", "timeout"), (wires, r["case"]))
                used = {copper.wire(c["chip"], axis, c[axis.lower()]) for c in copper.paint(r)["crosspoints"] for axis in "XY"}
                self.assertEqual(used & set(wires), set(), (wires, r["case"]))
                self.assertEqual([p for p in r["problems"] if p.startswith(("SHORT", "STRAY"))], [], (wires, r["case"]))

    def test_a_missed_path_never_passes_a_wire_taken_away(self):       # Review Focus 5
        nano = next(c for c in cases.dense_cases() if c.name == "nano_dense_metric")
        old = variants.resolve("a1accf5^")                              # leaves A4-19 and A5-20 unrouted, each with a path
        plain = runner.run_battery(old, [nano])[0]
        self.assertEqual(plain["metrics"]["missed"], 2)
        for hub in ("IK", "JK"):                                        # the two paths go by way of these hub lanes
            a = arrangement.parse("no_" + hub, {"base": "v5", "remove": [hub]})
            r = runner.run_battery(old, [nano], arrangement=a)[0]
            for m in ceiling.missed(copper.paint(r), ceiling.graph(a)):
                for h in m["path"] or ():
                    self.assertNotIn(hub, (copper.wire(h["chip"], "X", h["x"]), copper.wire(h["chip"], "Y", h["y"])))
            self.assertEqual(r["metrics"]["missed"], sum(1 for m in ceiling.missed(copper.paint(r), ceiling.graph(a)) if m["path"] is not None))

    def test_the_router_refuses_what_it_cannot_route(self):            # Review Focus 4
        with self.assertRaises(arrangement.RouterCannot) as cm:
            runner.run_battery(V, [CASE18], arrangement=arrangement.load("v6_rails_on_chips"))
        self.assertRegex(str(cm.exception), r"[A-H]\.X\d+ is on (TOP_RAIL|BOTTOM_RAIL|GND)")
        self.assertIn("arrangement score v6_rails_on_chips", str(cm.exception))

    def test_a_case_on_a_dropped_node_is_unplaced_not_a_miss(self):    # Review Focus 2
        no_rail = arrangement.parse("no_top_rail", {"base": "v5", "feed": False, "pins": {"K.X4": None}})   # TOP_RAIL's one pin
        self.assertEqual(no_rail.dropped, [101])
        uses, spares = cases.Case("uses", "x", [(1, 8, -1), (101, 3, -1)]), cases.Case("spares", "x", [(1, 8, -1)])
        with mock.patch.object(runner, "run_harness", wraps=runner.run_harness) as ran:
            a, b = runner.run_battery(V, [uses, spares], arrangement=no_rail, use_cache=False)
        self.assertEqual(ran.call_count, 1)                             # only the case that can be placed is routed
        self.assertEqual((a["status"], a["problems"], a["metrics"]["primaries"], a["arrangement"]), ("unplaced", [], 0, "no_top_rail"))
        self.assertIn("TOP_RAIL", a["notes"][0])
        self.assertEqual((b["status"], b["arrangement"]), ("ok", "no_top_rail"))
        self.assertFalse(lab.fully_routed(a))
        self.assertEqual(lab.exit_code([a, b], [uses, spares], []), 0)
        self.assertEqual(lab.regressions([b, dict(b, case="uses")], [a, b]), [])

    def test_a_cached_result_is_named_for_the_arrangement_asked(self):
        one, other = (arrangement.parse(n, {"base": "v5", "feed": False, "remove": ["KL"]}) for n in ("one", "other"))
        self.assertEqual(runner.run_battery(V, [CASE18], arrangement=one)[0]["arrangement"], "one")
        with mock.patch.object(runner, "run_case", side_effect=AssertionError("ran again")):
            self.assertEqual(runner.run_battery(V, [CASE18], arrangement=other)[0]["arrangement"], "other")

    def test_net_59_and_blocked_pins_do_not_mix(self):                 # Review Focus 3
        sections = runner.parse_sections(runner.run_harness(BIN, CASE18)[0])["t"]
        self.assertIn("Net 6]", sections["b"])
        high = dict(sections, b=sections["b"].replace("Net 6]", "Net 59]"))
        r = runner.judge(CASE18, high, block=[("X", 0, 2)])
        self.assertEqual(r["status"], "crash")
        self.assertIn("net 59", r["problems"][0])
        self.assertNotIn("net 59", " ".join(runner.judge(CASE18, sections, block=[("X", 0, 2)])["problems"]))
```

`V` is `variants.resolve("worktree")`. In `test_cli.py`: `lab.py run --classes dense --arrangement v6_feed_off` exits 0, its first line holds "arrangement: v6_feed_off", "probe feed off" and "the firmware's router", and the dense row reads 21 cases, 21 fully routed (with the feed off `k_rows_overflow_metric` routes too); `--arrangement v6_rails_on_chips` exits 2 and names `arrangement score`; `lab.py ceiling --case rail_stacking_light --arrangement v6_rails_on_chips` (solver installed) prints "the exact solver", `= 6`, and `-` in the two router columns.

- [ ] **Step 2: Run to see them fail.**
- [ ] **Step 3: Implement.** The hub lanes named in the missed-path test are what the two September paths use (`I.x14`, `K.x13`, `J.x14`, `K.x14`); if the old router's misses turn out to go another way, name in the test the hub lane each path really uses and note it in the ledger.
- [ ] **Step 4: Run all tests, then** `python3 tools/routing_lab/lab.py run --arrangement v6_feed_off --classes dense,real,typical,stress,edge`. Expected: 256 cases, 245 fully routed, no feed, no "not verified against a board" line.
- [ ] **Step 5: Commit** `Routing lab: the firmware's router on an arrangement (feed off, pins taken away), and the net 59 guard`.

---

### Task 4: The page draws any arrangement

**Files:**
- Modify: `tools/routing_lab/fabric_view.py`, `tools/routing_lab/server.py`, `tools/routing_lab/web/lab.js`, `web/lab.css`, `web/index.html`, `tools/routing_lab/tests/test_fabric_view.py`, `tests/test_server.py`

**Interfaces:**
- Consumes: `Arrangement`, `arrangement.names/load/blocks/why_not_router`, `runner.run_battery(..., arrangement=)`.
- Produces:
  - `fabric_view.layout(a=None) -> dict`: today's keys, plus `"taken": [{"chip", "axis", "pin"}]` and `"changed": [{"chip", "axis", "pin"}]`. For V5 the answer is what it is today, key for key and number for number. For another arrangement: chips are placed by role (breadboard chips in the lower row, SF chips in the upper, in `CHIPS` order, the drawing made wider when there are more than eight or four); a wire of a shape the V5 drawing knows is drawn as V5 draws it; any other wire is drawn as a bus on a level of its own in a band kept for them, with a riser to each of its pins; a pin taken away has no wire.
  - `/api/info` gains `"arrangements": [{"name", "about", "feed", "engine": "router" | "solver", "why": why_not_router or None}]`. A file that does not load is listed with `"problems": [...]` and no engine.
  - `GET /api/fabric?arrangement=NAME` answers `{"fabric": layout, "nodes": {id: {"wire", "name"}}, "arrangement": {"name", "about", "feed", "engine", "why"}}`. Unknown name: 404. A file with problems: 400 with `"problems"`.
  - `POST /api/run` takes `"arrangement": NAME` (default "v5"). Its answer gains `"arrangement": {...}` as above. A `RouterCannot` is 400 with the text in `error`. The same arrangement applies to the baseline.
  - **Runs are kept apart by arrangement.** `server.runs` is keyed by the variant's hash and the arrangement's name together, `GET /api/case` takes `arrangement=NAME` (default "v5"), and the page's own store of fetched cases is keyed the same way. Today both are keyed by the variant alone, so a run on `v5` and a run on `v6_feed_off` would overwrite each other case by case, and a drawing or a solver question could be about the wrong one.
  - On the page: an "Arrangement" picker under Baseline. Picking one redraws the Fabric tab from `/api/fabric`; taken pins show as small grey crosses on the chip's edge, changed pins as a thin ring in the ink colour (not red). The KiCad sheet tab says "the sheet is V5's own; this arrangement is drawn on the Fabric tab" for anything but V5 copper. The "Shown:" line adds the arrangement, the engine and the feed. Run is disabled, with the reason beside it, when the arrangement is solver-only.

**The bus rule (binding):** buses get levels in a band of their own between the SF row's approach lanes and the breadboard lanes, 4 apart, one level per wire, never shared. Today's geometry leaves that band three levels (approach lanes end at y 404, breadboard lanes start at 420), so for any arrangement but V5 the drawing is re-spaced: the breadboard row and everything under it move down by what the buses need, and the size grows with them. Only V5's drawing may not change. A riser to an X pin runs straight up or down that pin's column. A riser to a Y pin leaves the chip to the left on a track of its own beside the chip and turns to the level there. `fabric_view.overlaps(view)` must be empty for every arrangement the tests draw.

- [ ] **Step 1: Pin today's drawing.** Run `python3 -c "import sys,json,hashlib; sys.path.insert(0,'tools/routing_lab'); import fabric_view; print(hashlib.sha256(json.dumps(fabric_view.layout(), sort_keys=True).encode()).hexdigest())"` and put the digest in the test below as `V5_DRAWING`.
- [ ] **Step 2: Write the failing tests**

```python
class AnyArrangement(unittest.TestCase):                               # test_fabric_view.py
    def test_v5_is_drawn_exactly_as_before(self):
        for view in (fabric_view.layout(), fabric_view.layout(arrangement.V5)):
            drawn = {k: v for k, v in view.items() if k not in ("taken", "changed")}
            self.assertEqual(hashlib.sha256(json.dumps(drawn, sort_keys=True).encode()).hexdigest(), V5_DRAWING)
            self.assertEqual((view["taken"], view["changed"]), ([], []))

    def test_a_rail_on_nine_pins_is_drawn_and_crosses_no_other_track(self):     # Review Focus 7
        rails = arrangement.load("v6_rails_on_chips")
        view = fabric_view.layout(rails)
        self.assertEqual(fabric_view.overlaps(view), [])
        self.assertEqual(len(view["changed"]), 24)
        for wire in ("TOP_RAIL", "BOTTOM_RAIL", "GND"):
            pins = [(c, "X", x) for c in rails.CHIPS for x, w in enumerate(rails.X_NET[c]) if w == wire]
            self.assertGreaterEqual(len(pins), 9)
            for chip, axis, pin in pins:
                self.assertTrue(fabric_view.touches(view["wires"][wire]["d"], fabric_view.pin_point(view, chip, axis, pin)), (wire, chip, pin))
        self.assertNotIn("/AD1", view["wires"])

    def test_pins_taken_away_and_a_chip_added(self):
        gone = fabric_view.layout(arrangement.parse("t", {"base": "v5", "remove": ["KL", "/AB1"]}))
        self.assertEqual(len(gone["taken"]), 4)
        self.assertFalse({"KL", "/AB1"} & set(gone["wires"]))
        self.assertEqual(fabric_view.overlaps(gone), [])
        m = {"role": "sf", "x": ["TOP_RAIL", "BOTTOM_RAIL", "GND"] + [None] * 13, "y": [c + "M" for c in "ABCDEFGH"]}
        wider = arrangement.parse("t", {"base": "v5", "chips": {"M": m}, "remove": ["/%s1" % p for p in ("AB", "CD", "EF", "GH")],
                                        "pins": {"%s.X%d" % (c, fabric_v5.X_NET[c].index("/%s1" % p)): c + "M"
                                                 for p in ("AB", "CD", "EF", "GH") for c in p}})
        view = fabric_view.layout(wider)
        self.assertEqual((view["chips"]["M"]["role"], fabric_view.overlaps(view)), ("sf", []))
        self.assertGreater(view["size"][0], fabric_view.layout()["size"][0])
        self.assertEqual(len({(c["x"], c["y"]) for c in view["chips"].values()}), 13)
```

In `test_server.py`: `/api/info` lists the three arrangements with their engines and, with a broken file put in a patched `arrangement.DIR`, lists it with its problems while the page still loads; `/api/fabric?arrangement=v6_rails_on_chips` answers a fabric whose `changed` has 24 pins; `?arrangement=nope` is 404; the broken file is 400 with `problems`; `/api/run` with `"arrangement": "v6_feed_off"` answers rows without a feed and names the arrangement; with `"v6_rails_on_chips"` it is 400 and the error names a pin. After a run of the dense class on `v5` and one on `v6_feed_off`, `/api/case?...&arrangement=v5&case=chain_all_chips` has a probe feed bridge in its paint and `&arrangement=v6_feed_off` has none, whichever ran last. `lab.js` holds the picker's code (`/api/fabric`, `state.arrangement`), builds the key of its case store from the variant and the arrangement, and still passes `node --check`.

Add four wires of an unknown shape to the drawing tests, so the band is made to grow: an arrangement that puts one new name, `BUS_n`, on a pin of chip A, a pin of chip E and a pin of chip K for n in 0 to 3 (taking the lanes those pins were on away) must draw with `overlaps(view) == []` and a size taller than V5's.

- [ ] **Step 3: Run to see them fail.**
- [ ] **Step 4: Implement.**
- [ ] **Step 5: Check it in the browser** (`python3 tools/routing_lab/lab.py serve --no-open`):
  1. Arrangement `v6_feed_off`, class dense, Run: the "Shown:" line names it, "the firmware's router" and "probe feed off"; no case has a probe feed row; `k_rows_overflow_metric` is fully routed.
  2. Arrangement `v6_rails_on_chips`: the Fabric tab shows three long buses with a riser into every breadboard chip, 24 ringed pins, nothing red; Run is disabled and says why; the KiCad sheet tab says it is V5's.
  3. Back to `v5`: the drawing is the old one.
  4. Put a file with a mistake in `arrangements/`: the picker lists it greyed with its problems on hover, and everything else works. Remove it.
  Screenshot the second for Kevin.
- [ ] **Step 6: Commit** `Routing lab page: pick an arrangement and see its copper`.

---

### Task 5: Scoring an arrangement with the solver, and seeing its routing

**Files:**
- Create: `tools/routing_lab/score.py`, `tools/routing_lab/tests/test_score.py`
- Modify: `tools/routing_lab/lab.py` (`arrangement score`), `tools/routing_lab/server.py` (`/api/ceiling`), `tools/routing_lab/web/lab.js`, `tools/routing_lab/tests/test_server.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `ceiling.verdict(..., arrangement=)`, `ceiling.solved`, `runner.run_battery`.
- Produces:
  - `score.compare(v, cases, a, b=None, rule="firmware", seconds=10.0, fewest=True, progress=None) -> dict`. The netlists are the firmware's own: each case is run once by the harness on `arrangement.base(a.feed)`, V5's copper with `a`'s feed setting (the router's routing is not used, only the bridges it allowed and their nets), then the solver is asked on `a` and on `b`. `b` is V5's copper when `None`; whatever `b` is, both are asked the same netlists, so `b`'s own feed setting is not used. Returns `{"a", "b", "feed", "rule", "seconds", "engine": "solver", "rows": [{"case", "cls", "a": verdict, "b": verdict}], "summary": {...}}`, a verdict here being `ceiling.verdict`'s answer without `closed`. `progress(done, of, case)` is called after each case.
  - `summary`: `"cases"`; per side `"routable"`, `"not_routable"`, `"unknown"`, `"unplaced"`; `"only_a"` and `"only_b"` (cases proved routable on one and proved not routable on the other); `"proved_on_both"` (fewest proved on both) and `"fewest": {"a": total, "b": total}` over those; `"errors"` (cases whose verdict has an `error`).
  - `edge.grow(binary, rng, name, seconds=20.0, longest=80, rule="firmware", arrangement=None)`: with an arrangement, each probe's netlist is built with the arrangement's feed setting and the solver is asked on the arrangement's copper. Without one it is as before.
  - `score.lengths(v, a, b=None, lists=2, seed=1, seconds=20.0, longest=80, progress=None) -> list[dict]`: how far the edge class's random lists grow on each arrangement. List `i` is drawn from `random.Random(seed * 100003 + i)`, as `lab.py edge` draws it, so list 0 is `edge_1_0`'s. An entry is `{"list": i, "a": {"bridges": k, "next_is": ...}, "b": {...}}`, `bridges` 0 when not one is proved.
  - `lab.py arrangement score NAME [--against v5] [--classes dense,real,stress] [--case NAME] [--rule firmware|copper] [--seconds 10] [--grow N]`: the first line names both arrangements, "the exact solver", the rule and the feed; then one line a case (both verdicts, both counts, `=` or `<=`); then `fits only on NAME: ...`, `fits only on OTHER: ...`, `fewest crosspoints over the P cases proved on both: X on NAME, Y on OTHER`, and how many are unknown or unplaced on each. With `--grow N`, then N lines: `random list i: K bridges proved on NAME (one more: ...), M on OTHER (one more: ...)`, about a minute and a half a list an arrangement. Exit 1 on any error or when the solver is missing (with the setup line), else 0.
  - `POST /api/ceiling` takes `"run": NAME` (the arrangement of the run whose case is asked about, default "v5") and `"arrangement": NAME` (the copper to ask on, default the run's). Its answer gains `"arrangement"` and `"solved"` (`ceiling.solved(...)`, or null). When the run's feed setting is not the arrangement's it is 409: "this run has the probe feed on the fabric and NAME has it off (or the other way round): run the classes on an arrangement with the same feed first". A netlist with the feed in it is never asked of an arrangement without one.
  - On the page, with a solver-only arrangement picked: the Ceiling buttons ask on it, and a routable answer is drawn as the picture itself, from `solved`, with the case panel's head reading "the exact solver's routing on NAME, one of many; not the firmware's router" and the bridge table filled from it. With a router arrangement the Ceiling section is as it is today, asking on that arrangement.

- [ ] **Step 1: Write the failing tests** in `tests/test_score.py`:

```python
def fake(verdict_of):
    """ceiling.verdict replaced: verdict_of(case name, arrangement name) -> (verdict, crosspoints, proved)."""
    def answer(result, rule, seconds, use_cache=True, fewest=True, arrangement=None):
        verdict, n, proved = verdict_of(result["case"], arrangement.name if arrangement else "v5")
        return {"verdict": verdict, "crosspoints": n, "fewest_proved": proved, "closed": [], "error": None, "unplaced": [],
                "router_crosspoints": 0, "seconds": 0.0, "arrangement": arrangement.name if arrangement else "v5", "engine": "solver"}
    return mock.patch.object(ceiling, "verdict", side_effect=answer)

class Score(unittest.TestCase):
    def test_what_only_one_arrangement_fits_is_named(self):
        table = {("a_case", "v6_feed_off"): ("routable", 10, True), ("a_case", "v5"): ("not_routable", None, False),
                 ("b_case", "v6_feed_off"): ("unknown", None, False), ("b_case", "v5"): ("routable", 12, False),
                 ("c_case", "v6_feed_off"): ("routable", 8, True), ("c_case", "v5"): ("routable", 9, True)}
        three = [cases.Case(n, "x", [(1, 8, -1)]) for n in ("a_case", "b_case", "c_case")]
        with fake(lambda case, arr: table[case, arr]):
            s = score.compare(V, three, arrangement.load("v6_feed_off"))
        self.assertEqual((s["a"], s["b"], s["feed"], s["engine"]), ("v6_feed_off", "v5", False, "solver"))
        self.assertEqual((s["summary"]["only_a"], s["summary"]["only_b"]), (["a_case"], []))       # unknown is not "does not fit"
        self.assertEqual((s["summary"]["proved_on_both"], s["summary"]["fewest"]), (1, {"a": 8, "b": 9}))
        self.assertEqual((s["summary"]["a"]["unknown"], s["summary"]["b"]["not_routable"]), (1, 1))
        self.assertNotIn("closed", s["rows"][0]["a"])

    def test_both_are_asked_the_same_netlist_with_the_feed_as_the_first_has_it(self):
        seen = []
        with fake(lambda case, arr: ("routable", 2, True)), \
                mock.patch.object(runner, "run_battery", side_effect=lambda v, cs, **kw: seen.append(kw.get("arrangement")) or
                                  [dict(runner._result(c, "ok"), b="x") for c in cs]):
            score.compare(V, [cases.Case("c", "x", [(1, 8, -1)])], arrangement.load("v6_rails_on_chips"))
        self.assertEqual([(a.feed, a.changed, arrangement.blocks(a)) for a in seen], [(False, [], [])])   # V5's copper, feed off, once

    def test_the_same_random_lists_are_grown_on_both(self):
        grown = []

        def grow(binary, rng, name, seconds=20.0, longest=80, rule="firmware", arrangement=None):
            grown.append((rng.random(), arrangement.name, arrangement.feed))
            if arrangement.name == "v5" and len(grown) > 2:
                return None                                              # not one bridge proved
            return cases.Case(name, "edge", [(1, 8, -1)]), {"bridges": 67 if arrangement.name != "v5" else 61,
                                                               "closed": [], "next_is": "unknown"}

        with mock.patch.object(edge, "grow", side_effect=grow):
            out = score.lengths(V, arrangement.load("v6_rails_on_chips"), lists=2)
        self.assertEqual([(r["list"], r["a"]["bridges"], r["b"]["bridges"]) for r in out], [(0, 67, 61), (1, 67, 0)])
        self.assertEqual(grown[0][0], grown[1][0])                       # one list, grown on both
        self.assertNotEqual(grown[0][0], grown[2][0])                    # and another list after it
        self.assertEqual({g[1:] for g in grown}, {("v6_rails_on_chips", False), ("v5", False)})    # both with the first's feed

    @unittest.skipUnless(ceiling.solver_installed(), NEEDS_SOLVER)
    def test_rails_on_every_chip_against_v5(self):
        two = [dense("rail_stacking_light"), dense("isense_loop_stacked")]
        s = score.compare(V, two, arrangement.load("v6_rails_on_chips"), seconds=20)
        by = {r["case"]: r for r in s["rows"]}
        self.assertEqual((by["rail_stacking_light"]["a"]["crosspoints"], by["rail_stacking_light"]["b"]["crosspoints"]), (6, 10))
        self.assertEqual((s["summary"]["proved_on_both"], s["summary"]["fewest"]), (2, {"a": 13, "b": 18}))
```

`runner.run_battery`'s `arrangement` in the second test is `arrangement.base(a.feed)`. In `tests/test_edge.py`, with the pretend harness and solver of that file: `edge.grow(..., arrangement=arrangement.load("v6_rails_on_chips"))` runs every probe's case with `probe[0] == 0` and passes the arrangement to `ceiling.verdict`. In `test_cli.py`: `lab.py arrangement score v6_rails_on_chips --case rail_stacking_light` prints a first line with both names, "the exact solver" and "probe feed off", a case line holding `= 6` and `= 10`, and exits 0; with the solver patched away it prints the setup line and exits 1. In `test_server.py`: after a run of the dense class on `v6_feed_off`, `/api/ceiling` with `"run": "v6_feed_off", "arrangement": "v6_rails_on_chips"` and `ceiling.verdict` patched to a routable answer passes the arrangement on and answers `solved` with a `wires` entry for `TOP_RAIL`; with `"run": "v5"` (feed on) and the same arrangement it is 409 and the message names the feed; an unknown arrangement is 404.

- [ ] **Step 2: Run to see them fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run all tests, then** `python3 tools/routing_lab/lab.py arrangement score v6_rails_on_chips --classes dense,real,stress --grow 2` (about ten minutes). Put its summary lines and the two lengths in the commit message body. The prototype's lengths were 54 and 54, then 61 on V5 and 67 on the arrangement; answers near the time limit vary, so a length a bridge or two off is not a fault.
- [ ] **Step 5: Check it in the browser:** arrangement `v6_rails_on_chips`, run the dense class on `v6_feed_off` first, pick `rail_stacking_light`, switch the arrangement to `v6_rails_on_chips`, press "firmware-shaped paths": "Fewest crosspoints: 6 (proved)", and the Fabric tab shows the solver's routing using the rail buses, the head of the case panel saying whose routing it is.
- [ ] **Step 6: Commit** `Routing lab: two arrangements scored on the same netlists by the exact solver`.

---

### Task 6: Usage, and what the router loses without each wire

**Files:**
- Create: `tools/routing_lab/rank.py`, `tools/routing_lab/tests/test_rank.py`
- Modify: `tools/routing_lab/lab.py` (`rank`), `tools/routing_lab/tests/test_cli.py`

**Interfaces:**
- Consumes: `runner.run_battery(..., arrangement=)`, `arrangement.parse`, `copper.paint`, `lab.fully_routed`.
- Produces:
  - `rank.wires(a) -> list[dict]`: the wires that can be ranked, `{"wire", "kind", "pins": [(chip, axis, pin)]}`, `kind` one of `"lane"` (two X pins on breadboard chips), `"sf lane"` (a breadboard chip's X pin and an SF chip's Y pin), `"bounce"` (one Y pin of a breadboard chip that is no node's), `"hub"` (two X pins on SF chips that are no node's). Sorted by kind, then name. For V5: 48, 32, 8 and 6.
  - `rank.without(a, wire) -> Arrangement`: `a` with that wire taken away, named `"<a.name> without <wire>"`.
  - `rank.usage(results) -> {wire: {"cases": n, "primary": n, "duplicate": n}}`: the cases in which the wire carries a net, and the crosspoints closed on it by primary paths and by duplicates, summed over the results.
  - `rank.removal(v, cases, a, wires=None, progress=None) -> dict`: the baseline (the battery on `a`) and, for each wire (all of `rank.wires(a)` when `None`), the battery on `rank.without(a, wire)`. Returns `{"arrangement", "feed", "engine": "router", "variant": {"name", "hash"}, "cases": n, "baseline": totals, "wires": [entry]}`. `totals` is `{"primaries": routed, "fully_routed": n, "crosspoints": n, "worst_r": float | None}`. An entry is `{"wire", "kind", "pins", "usage": {...}, "loss": {"primaries", "fully_routed", "crosspoints", "worst_r"}, "by_class": {cls: the same four}, "worse": [case names], "better": [case names], "used_after": 0}`. `progress(done, of, wire)` is called after each wire.
  - **Loss is baseline minus without, signed**: positive means the router did worse without the wire, negative means it did better. `crosspoints` and `worst_r` are without minus baseline (more is worse). `worse` and `better` are the cases with fewer or more primaries routed. `used_after` is the crosspoints closed on the wire's pins in the runs without it, which must be 0.
  - `lab.py rank [--arrangement v6_feed_off] [--variant worktree] [--classes dense,real,typical,stress,edge] [--wires A,B] [--json FILE]`: prints the heading (arrangement, feed, "the firmware's router", cases), then one line a wire sorted by `loss.primaries` then `loss.fully_routed`, least first: kind, wire, used in N cases, primaries lost (signed, `+3`, `-1`, `0`), cases lost, crosspoints, how many cases worse and better. Under it: "usage counts follow the router's search order and say nothing of need; a negative loss is the router doing better without the wire". Progress goes to stderr, one line a wire (`12/94 /AB1`). Writes the dict to `build/rank/<variant hash>_<arrangement name>.json`. The default arrangement has the feed off, as V6 will; `--arrangement v5` is the same ranking with the feed on the fabric, as a V5 has it.

- [ ] **Step 1: Write the failing tests** in `tests/test_rank.py`:

```python
def results(routed):
    """Results by hand: {case: primaries routed}, each of 3 primaries."""
    return [dict(runner._result(cases.Case(n, "x", [(1, 8, -1)]), "ok", metrics={"primaries": 3, "routed_primaries": k, "crosspoints": 2 * k}), b="")
            for n, k in routed.items()]

class Wires(unittest.TestCase):
    def test_v5_has_ninety_four(self):
        kinds = collections.Counter(w["kind"] for w in rank.wires(arrangement.V5))
        self.assertEqual(kinds, {"lane": 48, "sf lane": 32, "bounce": 8, "hub": 6})
        self.assertEqual(len({w["wire"] for w in rank.wires(arrangement.V5)}), 94)
        self.assertEqual(len(rank.wires(arrangement.parse("t", {"base": "v5", "remove": ["KL"]}))), 93)
        self.assertEqual(sorted(rank.without(arrangement.V5, "KL").taken), [("K", "X", 12), ("L", "X", 14)])

class Removal(unittest.TestCase):
    def test_loss_is_signed(self):                                      # Review Focus 6
        runs = {"v5": {"a": 3, "b": 2}, "v5 without KL": {"a": 3, "b": 3}, "v5 without AK": {"a": 1, "b": 2}}
        with mock.patch.object(runner, "run_battery", side_effect=lambda v, cs, **kw: results(runs[kw["arrangement"].name])):
            r = rank.removal(V, [cases.Case(n, "x", [(1, 8, -1)]) for n in "ab"], arrangement.V5, wires=["KL", "AK"])
        by = {w["wire"]: w for w in r["wires"]}
        self.assertEqual((r["baseline"]["primaries"], r["baseline"]["fully_routed"]), (5, 1))
        self.assertEqual((by["KL"]["loss"]["primaries"], by["KL"]["loss"]["fully_routed"], by["KL"]["better"], by["KL"]["worse"]),
                         (-1, -1, ["b"], []))                           # the router does better without it: a gain, not zero
        self.assertEqual((by["AK"]["loss"]["primaries"], by["AK"]["loss"]["fully_routed"], by["AK"]["worse"]), (2, 1, ["a"]))
        self.assertEqual((r["engine"], r["arrangement"], r["feed"]), ("router", "v5", True))

    def test_on_the_real_router(self):
        off, battery = arrangement.load("v6_feed_off"), lab.battery(["dense", "real"])
        r = rank.removal(V, battery, off, wires=["KL", "AK", copper.BOUNCE[0]])
        base = runner.run_battery(V, battery, arrangement=off)
        self.assertEqual(r["baseline"]["primaries"], sum(x["metrics"]["routed_primaries"] for x in base))
        for w in r["wires"]:
            self.assertEqual(w["used_after"], 0, w["wire"])
            without = runner.run_battery(V, battery, arrangement=rank.without(off, w["wire"]))
            self.assertEqual(w["loss"]["primaries"], r["baseline"]["primaries"] - sum(x["metrics"]["routed_primaries"] for x in without))
            self.assertEqual(w["usage"], rank.usage(base)[w["wire"]])
        self.assertEqual(rank.usage(base)["AK"]["cases"],
                         sum(1 for x in base if copper.paint(x)["wires"]["AK"]["nets"]))
```

In `test_cli.py`: `lab.py rank --classes dense --wires KL,AK` exits 0, its heading names `v6_feed_off`, "probe feed off" and "the firmware's router", it prints two wire lines and the sentence about usage, and writes a JSON file under a patched `variants.BUILD_DIR` that loads as the dict.

- [ ] **Step 2: Run to see them fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run all tests, then** `python3 tools/routing_lab/lab.py rank` (about two and a half minutes). Put the five wires with the least loss and the five with the most in the commit message body, and how many wires the router does better without.
- [ ] **Step 5: Commit** `Routing lab: what the router loses without each lane, bounce row and hub lane`.

---

### Task 7: Does the copper need the wire, or does this router only happen to use it

**Files:**
- Modify: `tools/routing_lab/rank.py`, `tools/routing_lab/lab.py` (`rank --needed`), `tools/routing_lab/tests/test_rank.py`

**Interfaces:**
- Consumes: `ceiling.problem`, `ceiling.ask`, `ceiling.faults`, `ceiling.graph`, `rank.removal`'s dict.
- Produces:
  - `rank.need(given, kept, wire_pins, rule="firmware", seconds=5.0) -> ("no" | "yes" | "unknown", routing | None)`. `given` is a problem (`ceiling.problem`), `kept` a routing known to satisfy it (`[[chip, x, y, net]]`), `wire_pins` the pins of the wire in question.
    - If no crosspoint of `kept` is on one of the pins: `("no", kept)`, and the solver is not asked.
    - Otherwise the solver is asked the problem without the crosspoints on those pins, `fewest=False`. A routable answer that passes `ceiling.faults` is `("no", its routing)`. `not_routable` is `("yes", None)`. Anything else, an answer with an `error` included, is `("unknown", None)`.
  - `rank.needed(v, cases, a, ranking, rule="firmware", seconds=5.0, progress=None) -> dict`: `ranking` (from `removal`) with three keys added to every wire's entry: `"needed_by": [cases]` (proved), `"not_needed": n`, `"unknown": [cases]`. For each case the routing kept is the router's own closed crosspoints when they pass `ceiling.faults` for the case's problem on `a`, else the solver's routing on `a` (asked once, `fewest=False`); a case for which neither exists is `unknown` for every wire. A routing found for one wire is tried first for the next. Adds `"rule"`, `"seconds"`, `"needed_cases": n` to the ranking and sets `"engine": "router and solver"`.
  - `lab.py rank --needed [--needed-classes dense,real,typical,stress] [--seconds 5]`: runs `removal`, then `needed` over the cases of those classes. The table gains "needed by" (a count, proved), "not needed" and "unknown", and sorts by needed-by, then unknown, then the router's loss. Under it: "needed: the exact solver proves the netlist cannot be routed without the wire (firmware-shaped paths). not needed: a routing without it exists. The router's loss is beside these, not instead of them."

- [ ] **Step 1: Write the failing tests**

```python
class Need(unittest.TestCase):                                         # tiny fabrics from tests.test_ceiling
    def setUp(self):
        self.g = ceiling.graph(TINY)
        self.given = ceiling.problem(tiny_paint([(1, 3, 6, "unrouted")]), self.g)
        self.on_l0 = [["A", 0, 0, 6], ["B", 0, 0, 6]]
        self.l1 = [("A", "X", 1), ("B", "X", 1)]
        self.l0 = [("A", "X", 0), ("B", "X", 0)]

    def test_a_routing_that_never_touches_the_wire_settles_it_unasked(self):
        with mock.patch.object(ceiling, "ask", side_effect=AssertionError("asked")):
            self.assertEqual(rank.need(self.given, self.on_l0, self.l1), ("no", self.on_l0))

    def test_unknown_is_neither_yes_nor_no(self):                       # Review Focus 6
        for answer in ({"verdict": "unknown", "closed": []}, {"verdict": "unknown", "closed": [], "error": "the solver exited with 3"},
                       {"verdict": "routable", "closed": []}):          # the last fails the lab's own check
            with mock.patch.object(ceiling, "ask", return_value=answer):
                self.assertEqual(rank.need(self.given, self.on_l0, self.l0), ("unknown", None))

    def test_the_solver_is_asked_without_the_wires_crosspoints(self):
        with mock.patch.object(ceiling, "ask", return_value={"verdict": "not_routable", "closed": []}) as asked:
            self.assertEqual(rank.need(self.given, self.on_l0, self.l0), ("yes", None))
        offered = asked.call_args.args[0]["crosspoints"]
        self.assertEqual([c for c in offered if c[3] == "L0" or c[4] == "L0"], [])
        self.assertIs(asked.call_args.kwargs["fewest"], False)        # "is there a routing" is all that is asked

    @unittest.skipUnless(ceiling.solver_installed(), NEEDS_SOLVER)
    def test_with_the_real_solver(self):
        self.assertEqual(rank.need(self.given, self.on_l0, self.l0)[0], "no")           # lane L1 does as well
        one = ceiling.problem(tiny_paint([(1, 3, 6, "unrouted")], fabric=ONE_LANE), ceiling.graph(ONE_LANE))
        self.assertEqual(rank.need(one, self.on_l0, self.l0), ("yes", None))            # there is no other lane

@unittest.skipUnless(ceiling.solver_installed(), NEEDS_SOLVER)
class Needed(unittest.TestCase):
    def test_every_lane_into_k_is_needed_when_k_is_full(self):
        off, full = arrangement.load("v6_feed_off"), [dense("k_rows_overflow_metric")]
        lanes = ["%sK" % c for c in "ABCDEFGH"]
        r = rank.needed(V, full, off, rank.removal(V, full, off, wires=lanes + ["IJ"]), seconds=20)
        by = {w["wire"]: w for w in r["wires"]}
        for lane in lanes:
            self.assertEqual((by[lane]["needed_by"], by[lane]["unknown"]), (["k_rows_overflow_metric"], []), lane)
        self.assertEqual((by["IJ"]["needed_by"], by["IJ"]["not_needed"], by["IJ"]["unknown"]), ([], 1, []))
        self.assertEqual(r["engine"], "router and solver")
```

`ONE_LANE` and `NEEDS_SOLVER` come from `tests.test_solver`. `k_rows_overflow_metric` sends twelve rows to nodes on K. With the feed off it routes, and the prototype's solver proved it cannot be routed without any one of the eight lanes into K, each in about a second.

- [ ] **Step 2: Run to see them fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run all tests, then** `python3 tools/routing_lab/lab.py rank --needed` in the background. The solver is asked only where a kept routing touches the wire: by the prototype about a second a question and up to twenty-eight questions a case, so over an hour for the 244 cases of the default classes, a quarter of an hour with `--needed-classes dense,real,stress`. Do not run the test suite while it runs: solver answers near the limit come back "unknown" under load and are kept. Put in the commit message body: how many of the 94 wires no netlist is proved to need, how many some netlist is, how many have an unknown, and the ten wires nothing needs with the least router loss.
- [ ] **Step 5: Commit** `Routing lab: which wires the copper needs, proved, beside what the router loses`.

---

### Task 8: The ranking on the page

**Files:**
- Modify: `tools/routing_lab/server.py`, `tools/routing_lab/web/lab.js`, `web/lab.css`, `web/index.html`, `tools/routing_lab/tests/test_server.py`

**Interfaces:**
- Consumes: `rank.removal`, `rank.needed`, the JSON `lab.py rank` writes, `/api/run` with an arrangement.
- Produces:
  - `GET /api/rank?variant=SPEC&arrangement=NAME`: the newest ranking in `build/rank/` for that variant's hash and arrangement, or 404 with `hint` "python3 tools/routing_lab/lab.py rank --needed".
  - `POST /api/rank {"variant", "arrangement", "classes"}`: runs the router's part of the ranking (`rank.removal`, minutes) in this request, one at a time (a second is 409), writing the same file, and answers it. `GET /api/job` answers `{"what": "ranking" | null, "done", "of", "wire"}` while it runs, fed by `progress`. The solver's part can take over an hour and is not started from the page: `lab.py rank --needed` writes the file, and the page shows its "needed" columns when the file has them, and says how to get them when it has not.
  - `POST /api/run` takes, besides a named arrangement, `"without": [wire names]`: the named arrangement with those wires taken away as well. The answer's `arrangement` names it "<name> without A, B" and carries `"json"`: the file's text for that arrangement, to paste into `arrangements/`.
  - On the page: a third tab, "Ranking". The centre shows the fabric with every rankable wire tinted by the column chosen (needed by, or the router's loss), on a scale from the panel colour through teal to yellow, no red; the right column shows the ranking's table (kind, wire, used, router loss signed, needed by, not needed, unknown), sortable by a click on a heading, with the same two sentences `lab.py rank` prints under it. Above the table: which router, which arrangement, feed on or off, how many cases, and when the ranking was made; "Rank now" starts the router's part and shows `/api/job`'s progress. A click on a wire, in the drawing or the table, adds it to "take away"; "Run without these" runs the ticked classes on the arrangement without them and goes to the Fabric tab; the arrangement's JSON is shown beside the button to copy.

- [ ] **Step 1: Write the failing tests** in `test_server.py`: with a ranking file written under a patched `variants.BUILD_DIR`, `GET /api/rank` answers it and an unknown arrangement is 404 with the hint; `POST /api/rank` with `rank.removal` patched to call `progress` twice answers the dict, never calls `rank.needed`, and `/api/job` read from inside the patch sees `{"what": "ranking", "done": 1, "of": 2}`; a second `POST /api/rank` while one runs is 409; `/api/run` with `"arrangement": "v6_feed_off", "without": ["KL", "IJ"]` answers rows from an arrangement whose name ends "without KL, IJ" and a `json` that `arrangement.check` passes; `"without": ["NO_SUCH"]` is 400. `lab.js` holds the tab's code (`/api/rank`, `/api/job`, `function drawHeat`) and passes `node --check`; `lab.css` has no red in the heat scale (`--problem` is not used by any `.heat` rule).
- [ ] **Step 2: Run to see them fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Check it in the browser** with the ranking Task 7 wrote:
  1. The Ranking tab says whose ranking it is and when; the lanes into K and the bounce rows are the brightest under "router loss".
  2. Sorting by "needed by" puts the wires nothing needs first; a wire with a negative loss shows it with its sign.
  3. Click three wires nothing needs, "Run without these": the Fabric tab shows the run, the "Shown:" line names "v6_feed_off without ...", and the three wires carry nothing and are drawn as taken away.
  4. "Rank now" on dense alone shows progress wire by wire and ends with a new table.
  Screenshot the first for Kevin.
- [ ] **Step 5: Commit** `Routing lab page: the ranking as heat on the fabric, and runs without the wires picked`.

---

### Task 9: Documents

**Files:**
- Modify: `tools/routing_lab/README.md`, `CodeDocs/DESIGN_ROUTING_LAB.md` (status), `CodeDocs/V6_CROSSBAR_MATRIX.md` (one pointer)

- [ ] **Step 1: README.** A section "Arrangements" (the file, key by key, with `v6_rails_on_chips` as the worked example; `arrangement list/show/check/score`; which engine can answer for which arrangement and why; what the solver's answer is worth for V6). A section "The lane ranking" (`lab.py rank`, `--needed`; what loss, needed, not needed and unknown mean; that loss is signed; that usage is no guide; the Ranking tab; running without a set of wires). "Findings so far" gains what Tasks 5, 6 and 7 measured, each with its date, the arrangement, the engine and the feed. "What it does not check" gains: the firmware's router is never run on a changed fabric; a V6 router may do better or worse than the solver's ceiling; special nodes are not ranked (how often people use AREF or ADC4 is not something a routing battery knows).
- [ ] **Step 2: Design.** The status line (piece 4 built), and under piece 4 what was built differently, if anything.
- [ ] **Step 3: `V6_CROSSBAR_MATRIX.md`.** One paragraph at the top pointing at the arrangements and the ranking, with the measured numbers for P1 + P2.
- [ ] **Step 4: Run all tests.**
- [ ] **Step 5: Commit** `Routing lab: arrangements and the lane ranking documented`.

---

## Not in this plan

- **An editor on the page.** An arrangement is changed by editing its file; the page redraws when it is picked again. The one thing the page writes is the JSON for "V5 without these wires", to copy.
- **The firmware's router on a changed fabric.** It has V5 literals (V6_CROSSBAR_MATRIX section 7). Until the router reads its fabric from the board descriptor, a changed arrangement is answered by the solver alone.
- **Paths longer than four crosspoints.** The solver's firmware-shaped rule stays at four. V6_CROSSBAR_MATRIX section 7 thinks of six; that is one constant in `solver/solve.py` and a rule name, when it is wanted.
- **Ranking special nodes**, and usage data from real circuits.
- **A committed edge class for each arrangement.** `--grow` reports how far the random lists reach; it saves no cases and no proofs.
- **The tap planner as oracle for spare copies** (left over from piece 3), and the harness modelling a board with its top OLED off (the one crosspoint by which the lab differed from Kevin's pasted report).

## After this plan

The four pieces of the design are built. What the ranking and the scores say about V6 goes into `V6_CROSSBAR_MATRIX.md` as numbers beside its proposals.
