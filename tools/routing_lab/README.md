# Routing lab

Builds the firmware's own V5 router for the host, routes a battery of
netlists with it, and judges every result against the schematic with
`test/hil/routing_check.py`. No board needed. Design:
`CodeDocs/DESIGN_ROUTING_LAB.md`.

This is piece 1 of 4 (harness, battery, judge, command line). The page, the
ceiling search and the V6 lane ranking are not built yet.

## Use

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

## What a result says

Per case: primaries routed of total (the probe feed counts as one), routed
duplicates, crosspoints, the judge's problems (`SHORT`, `STRAY`,
`NOT CONNECTED`, `UNCLAIMED ...`, `WRONG CLAIM`, `CLAIM WITHOUT COPPER`),
sense-tap reachability from the firmware's own tap planner, and whether the
case routes the same when it is routed twice in one process.

## What it does not check

- **Not verified against a board yet.** The harness matches the sweep
  ledger's numbers, but the crosspoint-for-crosspoint comparison against a
  board capture has not been run.
- **Crossbar sends.** `CH446Q.cpp` is not linked; the "sent" view is filled
  from the path table, so "sent equals planned" cannot fail here. The HIL
  suite keeps that check.
- **Router debug traces.** `--trace` on the harness prints only the runtime
  flags' output; the macro traces are compiled out by default.

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
