# Routing lab

Builds the firmware's own V5 router for the host, routes a battery of
netlists with it, and judges every result against the schematic with
`test/hil/routing_check.py`. No board needed. Design:
`CodeDocs/DESIGN_ROUTING_LAB.md`.

Pieces 1 and 2 of 4 are built: the harness, battery, judge and command line,
and the page that draws a result on the fabric and on the board's KiCad
sheet. The ceiling search and the V6 lane ranking are not built yet.

## The page

```bash
python3 tools/routing_lab/lab.py serve
```

Opens `http://127.0.0.1:8765/`. Pick a router and the classes, press Run,
click a case.

- **Router / Baseline** take `worktree`, a git ref (`main`, `a1accf5^`), or a
  directory given with `--tree DIR` when the server was started. With a
  baseline the table tints each number better or worse, lists regressions,
  and "compare with baseline" draws both routings of the selected case.
- **Trying a change.** Edit the router in this checkout and tick **live**:
  the battery re-runs when a file under `src/` changes. Or drop
  `NetsToChipConnections.cpp`, `MatrixState.cpp` or any other source file on
  the left column: it is built as "worktree + 1 file" without touching the
  checkout. A router that does not compile shows the compiler's output and
  keeps the last table.
- **Fabric tab.** The twelve crossbars as grids with every piece of copper
  between them, generated from `test/hil/fabric_v5.py`. A lit wire carries
  the net of its colour; a dot is a closed crosspoint.
- **KiCad sheet tab.** The board's own schematic with the same result drawn
  over it: lit wires, lanes followed along their bus from chip to chip, a
  dot at each label and pin of a live net, and each closed crosspoint as a
  curve inside its chip from the X pin to the Y pin. Build it once with
  `python3 tools/routing_lab/lab.py sheet [board.kicad_sch] [--theme NAME]`
  (needs KiCad's `kicad-cli`; the default is the V5 r7 sheet in
  `~/Documents/GitHub/JumperlessV5`).
- **Marks, both tabs.** Red is a problem and nothing else is red: a wire
  carrying two nets, or a ring where the chip status and the copper disagree
  (a closed pin nobody claims, or a claim for another net). A hollow dot or
  dashed curve is a duplicate path's crosspoint. A small square is a pin
  claimed while no net rides its wire. A dashed ring marks the ends of a
  bridge that is not there: in the net's colour when the router failed it,
  grey when the firmware refused or dropped it by rule.
- Click a net, a lit wire or a crosspoint to light that net alone; it holds
  across the tabs. Wheel zooms, drag pans, double-click fits. Hover a wire
  for its pins and claims.
- The **ohm** columns are the worst bridge's resistance, counted in
  crosspoints and multiplied by the "ohms per crosspoint" box (60 by
  default; duplicates in parallel lower it).

The server listens on 127.0.0.1 only, answers only its own page (a token and
an origin check), and builds only this checkout, git refs of it, and the
`--tree` directories it was started with.

```bash
python3 tools/routing_lab/lab.py export run.html --baseline main
python3 tools/routing_lab/lab.py clean
```

`export` writes one battery run as a single HTML file that opens without the
server (table, case panel, fabric view; not the KiCad backdrop). `clean`
deletes the caches under `build/` (results, variant trees, binaries), which
grow with every variant tried; the built sheet is kept.

## Use from the command line

```bash
python3 tools/routing_lab/lab.py run
```

Routes the `dense` and `real` classes on this checkout's router and prints a
table. Useful forms:

```bash
python3 tools/routing_lab/lab.py run --classes dense,real,typical,fuzz,stress,beyond
python3 tools/routing_lab/lab.py run --variant ~/Documents/GitHub/JumperlOS --baseline main
python3 tools/routing_lab/lab.py run --classes fuzz --case fuzz_1_1
python3 tools/routing_lab/lab.py import-state my_slot.yaml --name my_slot
```

- `--variant` is `worktree` (the checkout `lab.py` is in), a directory that
  holds `src/` (another checkout, for example your main one while the lab
  lives on a branch), or a git ref.
- `--baseline` routes the same cases on a second variant and lists what got
  worse: a case that no longer routes fully, a new kind of problem, a crash.
- `--case` prints that case's problems, notes and `b` report.
- `--json FILE` writes every result.

Exit status: 0 clean; 1 on a short, a stray, a crash or hang, a must-route
case with problems, or a regression against the baseline; 2 on a usage error;
3 when the variant does not build (the compiler's output is printed).

The whole battery (about 2,250 cases) takes about five seconds. Results are
cached under `build/` by variant, case and judging code.

## Classes

| class | what |
|---|---|
| dense | the 21 cases of `test/hil/test_routing_dense.py` (shared through `test/hil/routing_cases.py`) |
| real | saved board states, imported with `import-state` into `cases/real/` |
| typical | 200 seeded circuits shaped like everyday use: an IC or two across the gap, power, ground, a few signals |
| fuzz | 2,000 seeded random netlists |
| stress | 21 cases each aimed at one scarce resource (one-chip floods, hub lanes, a 40-node net, maximum duplicates) |
| beyond | 3 cases over the fabric on purpose; scored, and must stay short-free |

Only the dense cases that the HIL suite requires to route are required to
route here. Everything else is scored. A JSON file dropped in `cases/<class>/`
joins that class.

Generated netlists are legal: no net holds a pair of nodes the firmware keeps
apart (a rail and a GPIO, DAC0 and DAC1, and so on; the table is checked
against the firmware's own). So an unrouted primary in `typical`, `fuzz` or
`stress` is the router's doing. `beyond` overflows on purpose.

## What a result says

Per case: primaries routed of total (the probe feed counts as one), routed
duplicates, crosspoints, the judge's problems (`SHORT`, `STRAY`,
`NOT CONNECTED`, `UNCLAIMED ...`, `WRONG CLAIM`, `CLAIM WITHOUT COPPER`),
sense-tap reachability from the firmware's own tap planner, and whether the
case routes the same when it is routed twice in one process.

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

- **Not verified against a board yet.** The harness matches the sweep
  ledger's numbers, but the crosspoint-for-crosspoint comparison against a
  board capture has not been run. `fidelity/README.md` has the one bench run
  it needs; `lab.py fidelity <capture>` then does the comparison and records
  the pass. `lab.py run` says "not verified against a board" until a pass is
  recorded for the harness as it is now.
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

## Findings so far (router at 5374d38, host only)

Full battery, 2,247 cases: no short, stray, crash or hang. Every primary of
every `typical`, `fuzz` and `stress` case routes.

1. **A netlist with GND can route differently on the next rebuild.** 18 cases
   do, including `slot3_snapshot_2026-08-26`. All flip with the starting
   parity of `gndChipAlternator`, which `clearAllNTCC()` never resets (the
   sweep ledger's F5).
2. **A duplicate can close a pin it does not claim.** In 44 fuzz cases a
   duplicate of a special-to-special path, bounced through a breadboard chip,
   closes that chip's second SF-lane X pin while the chip status shows it
   free. `setChipXStatus` refuses the claim when the tap-escape reservation
   says it is the chip's last virgin SF lane; the bounce code ignores that and
   writes the crosspoint anyway, so the reserved lane is used after all.
   See it: `lab.py run --classes fuzz --case fuzz_1_1`. One more case,
   `fuzz_1_288`, has an unclaimed lane of a different shape that has not been
   traced.
3. **An enum is read before it is set.** `NetsToChipConnections.cpp:2597`
   reads `pathType` of a duplicate still holding `clearAllNTCC()`'s
   `memset(-1)`. Harmless today (-1 is not `VIRTUAL`).
4. **The scan's GND auto-zero tap looks unreachable.** In
   `NetVoltageScan.cpp`, `gndInUse` is true whenever any net lists GND, and
   the GND special net always does. Worth a check on a board.

## How it is built

`harness/build.sh <src> <out>` compiles `NetsToChipConnections.cpp`,
`MatrixState.cpp`, `NetManager.cpp`, `RouteSafety.cpp`, `InfraPaths.cpp` and
the board files from one `src/` tree against the headers in `harness/stubs/`,
with `harness/lab_harness.cpp` (protocol and printing) and
`harness/firmware_stubs.cpp` (every stubbed firmware symbol, one line each).
Nothing under `src/` is modified. The netlist is built and routed by firmware
code only; a test fails if the harness defines any of those functions.

Sanitizers are on (ASan and UBSan, without the enum and bool checks, which
the router's `memset(-1)` idiom trips on every case).

## Tests

```bash
python3 -m unittest discover -s tools/routing_lab/tests -t tools/routing_lab
```
