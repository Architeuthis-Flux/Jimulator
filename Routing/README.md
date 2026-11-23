# Routing lab

The how-to with pictures is the repository's README. This is what the lab is and how to run it; each folder's
README has the rest.

Builds the firmware's own V5 router for the host, routes a battery of
netlists with it, and judges every result against the schematic with
`JumperlOS/test/hil/routing_check.py`. No board needed. Design:
`Routing/docs/DESIGN_ROUTING_LAB.md`; what it has found: `Routing/docs/FINDINGS.md`.

All four pieces of the design are built: the harness, battery, judge and
command line; the page that draws a result on the fabric and on the board's
KiCad sheet; the ceilings (the path a failed bridge had, the copies the free
copper still allows, and an exact solver that says whether a netlist can be
routed at all); and, for V6, crossbar arrangements other than V5's and a
ranking of the wires a board could do without.

Two engines answer, and everything the lab prints or draws says which one,
on which arrangement, and whether the probe feed is on the fabric:

- **The firmware's router**, the real code. It has V5 written into it, so it
  routes V5, and V5 with pins taken away.
- **The exact solver.** It takes any copper. What it says of a changed
  arrangement is a ceiling: what a router that keeps the firmware's path
  shape could reach there, not what a V6 router will do.

## Where things are

| Folder | What is in it | Read |
|---|---|---|
| `web/` | the page: `index.html`, `lab.js`, `lab.css` | `web/README.md`: views, marks, hands, panels, a board's own output |
| `cases/` | the case files, one folder per class; `example/` is what the page lists first | `cases/README.md`: classes, how to add an example |
| `solver/` | the exact solver (`solve.py`) and its web service (`service/`) | `solver/README.md`: ceilings; `solver/service/README.md` |
| `arrangements/` | crossbar copper other than V5's, as files of what differs | `arrangements/README.md`: the files, scoring, the lane ranking |
| `fidelity/` | captures from a real board that the harness is checked against | `fidelity/README.md` |
| `harness/` | the firmware's router built for the host | "How it is built" below. No README there: every file in that folder is part of the hash that names a router build, and every ranking on file is kept under that hash |
| `docs/` | findings, the design, the plans as executed, handoffs, the README's pictures | `docs/README.md` |
| `tests/` | the suite | "Tests" below |
| `build/` | made here, never committed: router builds, cached results, rankings, the solver's venv, the KiCad sheet | |
| `../JumperlOS/` | the firmware, a git submodule: the lab reads its `src/` (the router) and `test/hil/` (the fabric and the judge) | "The firmware checkout" below |

## The firmware checkout

```bash
git submodule update --init          # once, after cloning
```

That fetches JumperlOS at the commit this repository pins, which is the router every finding so far was made on.
To use another checkout instead (your own, with a router you are changing), name it:

```bash
JUMPERLOS=~/Documents/GitHub/JumperlOS python3 Routing/lab.py serve
```

`--variant worktree` is then that checkout as it is on disk, uncommitted changes and all, and a git ref
(`--variant main`, `--baseline v5.6.0`) is a ref of that checkout. A shallow clone of the submodule is enough to
run everything but old routers by ref; the lab says so when a ref is missing for that reason
(`git -C JumperlOS fetch --unshallow`).

Needs Python 3.12 or later and a C++17 compiler (`g++` or Apple's clang under that name). Optional: OR-tools for the
exact solver (`python3 Routing/lab.py solver-setup` makes a venv for it under `build/`), and KiCad's `kicad-cli`
for the sheet view (`python3 Routing/lab.py sheet`).

## Use from the command line

```bash
python3 Routing/lab.py run
```

Routes the `dense` and `real` classes on the firmware checkout's router and
prints a table. Useful forms:

```bash
python3 Routing/lab.py run --classes dense,real,typical,fuzz,stress,beyond,edge
python3 Routing/lab.py run --variant ~/Documents/GitHub/JumperlOS --baseline main
python3 Routing/lab.py run --classes fuzz --case fuzz_1_1
python3 Routing/lab.py import-state my_slot.yaml --name my_slot
```

- `--variant` is `worktree` (the firmware checkout as it is on disk: this
  repository's `JumperlOS` submodule, or the checkout `JUMPERLOS` names), a
  directory that holds `src/` (any other JumperlOS checkout), or a git ref of
  the firmware checkout (`HEAD`, a tag, a commit).
- `--baseline` routes the same cases on a second variant and lists what got
  worse: a case that no longer routes fully, a new kind of problem, a crash,
  or more bridges left unrouted where the copper had a path.
- `--case` prints that case's problems, notes and `b` report.
- `--json FILE` writes every result.
- `--arrangement NAME` routes on another arrangement than V5 (`run`,
  `ceiling` and `rank` all take it). The table's first line says which, who
  routed, and where the probe feed is. The router refuses an arrangement that
  is not V5 with pins taken away, names the first pin that is the reason, and
  exits 2.

Exit status: 0 clean; 1 on a short, a stray, a bridge listed as routed whose
copper does not join its nodes, a crash or hang, a must-route case with
problems, or a regression against the baseline; 2 on a usage error; 3 when
the variant does not build (the compiler's output is printed).

The whole battery (about 2,260 cases) takes five to ten seconds. Results are
cached under `build/` by variant, case and judging code. The table's `missed`
column is the class's total of failed bridges the copper had a path for; it
does not change the exit status on its own.

## What a result says

Per case: primaries routed of total (the probe feed counts as one), routed
duplicates, crosspoints, the judge's problems (`SHORT`, `STRAY`,
`NOT CONNECTED`, `UNCLAIMED ...`, `WRONG CLAIM`, `CLAIM WITHOUT COPPER`),
sense-tap reachability from the firmware's own tap planner, and whether the
case routes the same when it is routed twice in one process.

A bridge the path table lists as routed is also traced through the closed
crosspoints. If its copper does not join its two nodes it is `NOT CONNECTED`
on any class, scored ones included, and the case does not count as fully
routed. Resistance is that same trace: every closed crosspoint of the net as
one resistor, duplicates in parallel. The worst and median are over signal
bridges; bridges to GND or a rail are reported apart, since stacking makes
them the best of a case.

Three things are the firmware saying no, not the router failing, and are
reported apart from routing misses:

- **rejected**: a bridge the firmware's rules refuse outright (a forbidden
  pair, a node that is not connectable, equal ends).
- **left out of every net**: a bridge that would join two nodes a special net
  keeps apart through a shared node, or that arrived when the net tables
  were full.
- **refused**: a path the router found and the safety check
  (`validateAllPaths`) vetoed. It counts in the `refused` column, not against
  "fully routed".

A pair given twice is one bridge, merged as the firmware's loader merges it.

## What it does not check

- **Only the dense suite, on one board, under default settings.** The
  comparison covers the 21 dense cases, with the top OLED unlocked, the
  serial lock off and DAC0 at 0 V. Other settings were not compared. In
  particular the suite zeroes DAC0, so every compared case has its probe
  feed on a GPIO; the 1,992 battery cases that feed the probe from DAC0
  (DAC0 at 3.33 V) have no board run behind them.
- **A slot's own OLED lock.** A state whose config says `oled:
  {lockConnection: true}` gets two more bridges on a board (D2 to GPIO 7, D3
  to GPIO 8). The lab reads bridges, stacking and power from a state and
  does not add them. Neither `real` case has the flag set.
- **Sense taps against a board.** The taps column comes from the firmware's
  own planner, but a board capture holds no tap routes, so the fidelity
  comparison does not cover it. The list of scanned nodes is a hand copy of
  one firmware rule.
- **Crossbar sends.** `CH446Q.cpp` is not linked; the "sent" view is filled
  from the path table, so "sent equals planned" cannot fail here. The HIL
  suite keeps that check.
- **Router debug traces.** `--trace` on the harness prints only the runtime
  flags' output; the macro traces are compiled out by default.
- **The sheet view's reading of KiCad.** It follows wires, junctions, labels
  and buses on the root sheet, as r7 uses them. A board drawn another way
  (crossbars on a sub-sheet, for instance) may light less than it should;
  the fabric tab does not depend on it.
- **A live board between its rebuilds.** The page reads a board's routing
  when its counter has moved and the board is idle, not during a rebuild. A
  crosspoint closed and opened again between two polls is not seen.
- **FakeGPIO's writes in the dump.** Whether the firmware's writes to the chips
  through FakeGPIO are kept out of a live board's crossbar dump is not known.
- **Net voltages.** A live board's nets are shown without voltages.
- **The firmware's router on a changed fabric.** It is never run on one. It
  has V5's chips and pins written into it, so an arrangement that moves a
  pin is answered by the solver alone, and a pin taken away is the only
  change the router ever sees.
- **What a V6 router will do.** The solver's answer for a changed
  arrangement is a ceiling for routers that keep the path shape. A real V6
  router may do worse than it, and one with other rules may do better.
- **Special nodes in the ranking.** Only lanes, bounce rows and hub lanes
  are ranked. Whether a board could lose AREF or ADC4 depends on how often
  people use them, which a routing battery does not know.
- **A board with the feed off, or with a wire cut.** The board check is of
  V5 as built. Runs with the feed off the fabric or with pins blocked have
  no board behind them. What is checked is that the router keeps off a
  blocked pin: a case in which it closes a crosspoint on one fails, saying
  which. In the 94 rankings (256 cases each) it never did.

## How it is built

`harness/build.sh <src> <out>` compiles `NetsToChipConnections.cpp`,
`MatrixState.cpp`, `NetManager.cpp`, `RouteSafety.cpp`, `InfraPaths.cpp` and
the board files from one `src/` tree against the headers in `harness/stubs/`,
with `harness/lab_harness.cpp` (protocol and printing) and
`harness/firmware_stubs.cpp` (every stubbed firmware symbol, one line each).
Nothing under `src/` is modified. The netlist is built and routed by firmware
code only; a test fails if the harness defines any of those functions.

The lab's Python imports only the standard library. `ceiling.py` holds the
copper as a graph and the two searches over a painted result; the exact
search is `solver/solve.py`, a CP-SAT model that knows nothing of the lab or
of V5, run as a separate process with the Python of `build/solver-venv`.
`edge.py` grows the edge cases. `board.py` turns a board's own `b` report
into a result the page can show.

`arrangement.py` reads an arrangement file into the same tables
`fabric_v5.py` has, says what differs from V5, and says whether the router
can run it (then with which pins blocked). The copper searches, the solver's
problem and the drawing (`fabric_view.py`) all take those tables, so none of
them knows V5 from any other arrangement. `score.py` asks two arrangements
the same netlists; `rank.py` is the ranking. The router's side of an
arrangement is two lines of the harness's own protocol: `probe 0 x` (the
feed off) and `block` (a pin claimed for a net that is in no netlist, so
the router sees it as taken).

Sanitizers are on (ASan and UBSan, without the enum and bool checks, which
the router's `memset(-1)` idiom trips on every case).

## Tests

```bash
python3 -m unittest discover -s Routing/tests -t Routing
```
