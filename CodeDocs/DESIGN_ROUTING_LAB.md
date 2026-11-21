# Routing lab: design

Written 2026-11-17, approved the same day. Pieces 1 and 2 are built
(2026-11-21, `tools/routing_lab/`; its README says how to use them); pieces 3
and 4 are not. "Learned building piece 1" at the end changes what the later
pieces must do. Piece 2 as built differs from the text below in one way: the
r7 sheet draws its breadboard-to-breadboard lanes as buses and nearly
everything else as a label on the pin, so the sheet view follows buses and
lights labels and pin ends, not long wires.

## Why

A change to the V5 router can only be judged today with a board on the bench
and the HIL suite: 21 dense cases, seconds each, pass or fail. Kevin wants to:

1. Put in a changed router and see what it did across many netlists, from
   everyday to beyond the fabric, drawn on the schematic.
2. Know how far the router is from the best the copper allows: bridges
   routed, crosspoints spent, resistance, parallel copies.
3. Learn which lanes V6 can give up for other uses.

## Goals

- **G1 Fast loop.** Save a router file, see the battery re-run. A single case
  in about a second, the standard battery in under a minute.
- **G2 See it.** Each net's path lit on a generated fabric diagram and on the
  r7 KiCad sheet. Shorts, strays, unrouted bridges and missed paths are marked
  and explained. Two variants can be compared on one case.
- **G3 Trust it.** The harness reproduces a real board's routes crosspoint
  for crosspoint on the dense cases.
- **G4 Ceilings.** An independent search says whether a path existed that the
  router did not find, and whether the whole netlist was routable at all.
- **G5 Resistance.** Ohms per bridge over the net's real closed crosspoints,
  and what more parallel copies would buy.
- **G6 V6 ranking.** Lanes ranked by what routing loses when each is removed.

## Not in scope

- A firmware simulator (LEDs, OLED, timing). Jumperlessim covers that.
- A public hosted site. A read-only HTML export of results is the share path.
- The OG router. It has `test/test_routing_og`.
- Changing the router. Findings feed a later router pass. Nothing under
  `src/` is edited by this project.
- Routing on a V6 fabric with the firmware router (it has V5 literals; see
  `V6_CROSSBAR_MATRIX.md` section 7). The fabric is data, so the ceiling
  search can take a V6 fabric later.
- How often people use a given special node (AREF, ADC4, UART). That is usage
  data, which a routing battery cannot supply. The ranking covers routing
  resources only: lanes, bounce rows, hub lanes.

## What would make it a failure

- A score that is about the harness and not the firmware. Hence G3 first.
- "Proved optimal" printed when a search only timed out.
- A lane ranking that reflects the router's search order instead of need.

## Approaches considered

1. **Local lab in JumperlOS (chosen).** Native harness, Python server, one
   static page. Reuses the existing fabric model and copper checker. Runs only
   where the repo and a compiler are.
2. **WebAssembly in the browser.** Hostable, but new C++ still needs a local
   compile, the judge is written twice, and fuzz and lane-removal runs are slow
   in a tab. The HTML export covers sharing.
3. **Board in the loop.** The truth, but seconds per case rules out fuzzing,
   ceilings and lane removal. Kept as the reference for G3.

Kevin described outcomes and left the tooling to me, so 1 is my call.

## Where it lives

`tools/routing_lab/` in JumperlOS, on a branch off `main` (`main` holds the
newest router; `dev` has nothing newer). My call: the harness compiles
firmware sources and shares the HIL fabric model and checker, so it belongs
with the firmware. The earlier split (frontend in Jumperlessim) is not
followed because the page is one file tied to this server's JSON.

```
tools/routing_lab/
  lab.py            CLI and server
  harness/          lab_harness.cpp, host stubs
  cases/            battery, one file per case, grouped by class
  fidelity/         board captures, per firmware version
  web/              index.html, lab.js, lab.css, generated sheet overlay
  build/            git-ignored: variant trees, binaries, result cache
```

## Piece 1: harness, battery, judge

**Harness.** One native program per variant. It links the real
`NetsToChipConnections.cpp`, `MatrixState.cpp`, `NetManager.cpp`,
`RouteSafety.cpp`, `InfraPaths.cpp` and `src/boards/*.cpp`. A syntax-only
spike against the stubs in `test/test_routing_og/stubs` (2026-11-17) left:
the router 5 errors, `MatrixState.cpp` 1, `NetManager.cpp` 51 over 24 names,
`InfraPaths.cpp` 25 over 14 names; `RouteSafety.cpp` and the board files
already build in the OG harness. So about 40 stub declarations before the
link, and the link will ask for more. Rules:

- The netlist is built by firmware code, never by a re-implementation (the
  OG harness re-implements it; this one must not). The harness writes the
  case's bridges into `globalState.connections.bridges[]` and then runs the
  sequence at the head of the rebuild in `Commands.cpp`: `infraEvaluate`,
  `clearAllNTCC`, `loadBridgesFromState`, `getNodesToConnect`,
  `bridgesToPaths`. `infraEvaluate` is real, so the probe feed is decided by
  the firmware's own rule from the case's DAC0 voltage and power source.
- Stubs fall in two kinds: hardware is a no-op; policy inputs come from the
  case (stack settings, rail and DAC voltages, probe power source,
  current-sense overlay). Anything else is listed by name in the harness with
  a comment.
- **Crossbar sends are not exercised.** `CH446Q.cpp` is PIO and DMA code and
  is not linked. A named loop of about twenty lines fills `lastChipXY` and the
  `:crossbar` line from `paths[]`. My call. The cost: "sent equals planned"
  cannot fail on the host and is not claimed, and the incremental send is not
  covered. The HIL suite keeps both.
- Output is the same text the board prints for `b` plus a `:crossbar` line,
  so `routing_check.py` and `routing_snapshot_diff.py` work on it unchanged.
  The page's JSON is derived in Python from `routing_check`'s parsers. The
  only extra line is `taps:` (below).
- One case per process. The GND alternator is never reset and failed paths
  leak claims (sweep findings F5, F7). Separate processes also isolate a crash
  or hang, which is reported as a result for that case.
- Built with address and undefined-behaviour sanitizers by default.
- `--repeat 2` routes the case twice in one process and compares, to catch
  state that survives a rebuild.
- `--block <wire,...>` claims wires for a phantom net before routing (piece 4).

**Variants.** A variant is a complete `src/` tree: a base plus overrides.
Sources: the working tree (re-run on save), a git ref, or files dropped on the
page. Any file under `src/` may be overridden, since the fabric tables are in
`src/boards/v5/board_v5.cpp`. Each variant is cached by content hash.

**Trust boundary.** The server compiles and runs what it is given, so it binds
to 127.0.0.1 only, accepts uploads only to paths under `src/`, and rejects
path traversal.

**Battery.** Each case: name, class, bridges with optional per-bridge `dup`,
the stacking settings, rail and DAC voltages, probe power source and
auto-connect, and whether it must route fully. Generated classes use a fresh
board's defaults, so the feed is DAC0-fed (two crosspoints, one K row) unless
the case uses DAC0, when the firmware moves it to a GPIO (a K row, an L row
and the KL lane). The dense cases set DAC0 to 0 V and get the GPIO feed, as on
the board.

A firmware state document (YAML) can be imported as a case. The import is
Python and repeats one loader rule by name: a per-bridge count equal to
`stackPaths` is reset to default (`States.cpp`, the stamped-count reset).

| class | source |
|---|---|
| dense | the cases in `test/hil/test_routing_dense.py`, moved to a module both import |
| real | `test/hil/*.yaml` snapshots, plus anything dropped in `cases/real/` |
| typical | seeded generator: rails and GND on several rows, an IC across the gap, GPIO, ADC, DAC, Nano pins, UART |
| fuzz | seeded random netlists, a few thousand |
| stress | one-chip floods, every chip pair, K and L exhaustion, every Nano pin, one very large net, maximum duplicates |
| edge | piece 3: netlists the solver proves routable with nothing to spare |
| beyond | over the fabric on purpose; scored, and must stay short-free |

**Judge.** `routing_check.full_check` as is: connectivity, SHORT, STRAY,
chip-local and the claim checks.

**Taps.** The tap reservations only ever refuse duplicates, so without a tap
check a variant that starves the sense taps shows more copies and fewer ohms
with a clean judge. That would run against the standing rule that a duplicate
never takes the last route a tap needs (sweep section 6). So after routing the
harness asks the firmware's own tap planner in `RouteSafety.cpp` for a route to
every node the scan would visit and prints `taps: n of m` with the nodes that
have none. The five dense cases that carry a taps proof must keep every tap;
everywhere else it is a column. The scan's node list comes from
`NetVoltageScan.cpp`, which cannot be linked, so the harness carries a named
copy of that one rule. My call. If the planner cannot be linked in the first
plan, the copies and ohms columns say "taps not checked" until it can.

**CLI.** `lab.py run`, `lab.py fidelity`, `lab.py serve`, `lab.py export`.
`run` exits non-zero on a short or a regression against the baseline, so it
works in CI without the page.

**Fidelity gate (G3).** One bench run:

1. Flash a build of a clean, recorded commit. The version string is not
   enough: six commits on `main` all report 5.7.11.5. The capture folder is
   named by commit hash.
2. Power-cycle, then run the HIL dense suite once with `JL_ROUTING_SNAP_DIR`
   set. The captures are committed under `fidelity/`.

`lab.py fidelity` builds the harness from that commit and replays the dense
cases in the suite's order in one process, because the board does not reboot
between cases and the GND alternator survives rebuilds. The alternator's
starting value depends on what the board routed at boot, so the replay tries
both parities. Pass: zero rows moved and identical chip status under one of
them. Anything else is a fidelity bug to chase, not to waive. Ordinary battery
runs stay one case per process. Until the gate passes, the page shows "not
verified against a board".

## Piece 2: the page

```
+ Variants ------------+ + [Fabric] [KiCad sheet] ----------------+ + Case ---------------+
| A main@5374d38       | |   I    J    K    L     16x8 grids,     | | nano_dense_metric   |
| B working tree  live | |   lanes drawn between chips, lit by net | | 13 bridges, 11 routed|
+ Battery -------------+ |   A  B  C  D  E  F  G  H               | | x 19-A4 unrouted    |
| class     A      B   | |   rows 1-60, rails, Nano, specials      | |   copper had a path:|
| dense   21/21  21/21 | +-----------------------------------------+ |   C > K.Y2 > IK > I |
| stress  38/40  40/40 |                                             | worst 250 ohm       |
+----------------------+                                             +---------------------+
```

- **Battery table.** Per class and per case, for each variant: bridges routed,
  shorts, strays, crosspoints, worst bridge ohms, copies, gap to the ceiling.
  Better or worse than the baseline is coloured. Filters for failures and for
  changes only.
- **Fabric view.** Drawn from the fabric data, laid out like the sheet's
  crossbar blocks. Each chip is a 16 by 8 grid; a closed crosspoint is a dot.
  Every wire and crosspoint can be hovered and clicked. A missed path is drawn
  dashed in the net's colour.
- **KiCad sheet view.** The r7 sheet exported by `kicad-cli` as the backdrop.
  A generator reads the `.kicad_sch` wires, labels and pins (same millimetre
  coordinates as the export) and writes an overlay keyed by net, committed and
  regenerated on a board revision like `fabric_v5.py`. Lanes that are labels
  light at both stubs. A closed crosspoint is a line inside the chip body from
  its X pin to its Y pin.
- **Breadboard strip.** Rows, rails, Nano header and specials as pads, lit by
  net. My addition; it shows which rows a case touches.
- **Compare.** One case, two variants: copper only in A, only in B, in both.
- **Resistance (G5).** Each closed crosspoint is a resistor between its two
  wires; wire copper is zero. A bridge's value is the effective resistance
  between its two nodes over the net's whole network, so copies count. The
  per-crosspoint value is a setting, default 60 ohm (datasheet 65 ohm maximum;
  about 130 ohm measured for a two-crosspoint loop). Rails and GND are reported
  apart from signals.

## Piece 3: ceilings

The model is the checker's: a wire carries one net; a crosspoint joins an X
wire and a Y wire on one chip; a real node outside the net may not be touched.

- **Residual search (exact, fast).** Everything else stays where the router
  put it. For an unrouted bridge: the shortest path through free or same-net
  copper, if one exists. This is "the hardware had a path and the router did
  not find it", with the path drawn. Repeated for a routed bridge it lists the
  extra parallel copies the free copper allows and the resistance they would
  give.
- **Global search (exact, time-limited).** Everything may move. Two rule sets:
  *copper* (a net is any tree, any length) and *firmware-shaped* (each bridge
  is its own path of at most four crosspoints, as `pathStruct` holds; one
  net's paths may share copper). Verdicts are "routable, proved", "not
  routable, proved" or "unknown after N seconds". When routable it also
  returns the fewest crosspoints.
- **Edge cases.** Grow a random netlist until the global search proves it
  unroutable, keep the last routable one. These are the hardest cases that
  provably fit, and the router's share of them routed is the headline score.
- **Solver.** OR-tools CP-SAT in a virtual environment under the lab folder.
  My call: nothing suitable is installed, and an exact disjoint-tree search is
  not worth hand-writing. It is optional; without it the page says so.
- **Honest limit.** Copies found by the residual search are "available in
  copper". The firmware refuses some of them to keep sense taps reachable.
  Follow-on within this piece: use the firmware's own tap planner as the
  oracle (a copy is allowed if every node that had a tap route keeps one).

## Piece 4: V6 lane ranking

- For each of the 86 lanes, 8 bounce rows and 6 hub lanes: block it, re-run
  the battery, record the loss in bridges routed, cases fully routed,
  crosspoints and resistance, per class. Rank by least loss.
- The same against the global search, to separate "the copper needs this
  lane" from "this router happens to use it".
- Raw usage counts are shown beside the loss, labelled as biased by search
  order.
- Custom sets: block several wires together (for example one lane of each
  doubled pair, or three X pins per breadboard chip) and see the combined loss.
- The fabric view takes the loss as a heat overlay.
- The probe feed changes the answer for KL and the K rows. The ranking runs
  with the feed as the firmware decides it. A switch re-runs it with the feed
  off, for a V6 that takes the feed off the fabric (`V6_CROSSBAR_MATRIX.md`
  P2). My call; the second run doubles the job, so it is on request.
- Runs as a background job with progress; results are cached by variant, case
  and blocked set.

## How we know it works

- At `main`, every must-route dense case routes and the judge is clean.
- Pointed at the commit before the hub rescue tier (`a1accf5^`), the lab
  marks `19-A4` and `20-A5` in `nano_dense_metric` as missed and draws a path
  of four crosspoints. At `main` both are routed.
- Pointed at the commit before the bounce-pin fix (`f41e755^`), the claim
  checks fail on `kevin_fixture_2026_09_02`. At `main` they pass.
- A blocked wire never appears in any path.
- The five dense cases with a taps proof report every tap reachable at `main`.
- `test/hil/slot3_snapshot_2026-08-26.yaml` imports with its GPIO bridges
  single, as the board leaves them.
- Two crosspoints in series read twice the setting; two such paths in
  parallel read once the setting.
- The solver agrees with hand-checked answers on small made-up fabrics.
- `test/test_routing_og/run.sh` and the HIL suite behave as before.

The two historical checks hold only if those commits build against the stubs.

## Build order

Four plans, each usable when it lands: (1) harness, battery, judge, CLI;
(2) server and page, both views, resistance; (3) ceilings and edge cases;
(4) lane ranking.

## Left to the builder

- Whether the stubs are shared with the OG harness or copied.
- How a variant tree is materialised (copy, symlinks or `git archive`).
- The CP-SAT formulation and the default time limit.
- Diagram layout details and colours.
- Whether the sheet backdrop is the SVG or a raster of it (the SVG is 10 MB).

## Needed from Kevin

- The bench run for the fidelity gate (above), or a V5 left plugged in and a
  go-ahead for me to flash it and run the suite, which snapshots and restores
  the bench. The lab is usable before it, with the banner.
- For the ranking: whether V6 keeps the probe feed on the crossbar.
- Any real netlists beyond the two YAML snapshots in `test/hil/`.

## Learned building piece 1

These bind the later pieces.

- **Primaries no longer separate routers.** On every legal `typical`, `fuzz`
  and `stress` netlist today's router routes every primary. Two variants can
  only be told apart by duplicates, crosspoints, resistance and taps, so the
  page's table must lead with those, and `lab.py run` should print them
  (it prints only routed primaries today).
- **Three kinds of "not routed" are the firmware saying no.** A bridge it
  rejects outright, a bridge it leaves out of every net, and a path its
  safety check vetoes are not routing misses. The ceiling search (piece 3)
  must drop them before asking whether the copper had a path, and the page
  must draw them differently from a missed path.
- **The lab models a state load.** One rebuild from a complete bridge list.
  Incremental adds (`refreshLocalConnections`, where the probe feed is at
  index 0 after boot) are not modelled.
- **The server is a wider door than "localhost only".** Any web page open in
  a browser on the same Mac can post to a localhost port. The server must
  check the request's origin (or carry a token) before it compiles anything,
  and a variant given as a directory should be limited to directories Kevin
  has named.
- **The cache grows without limit**: about 11 MB per variant tree and 28 MB
  of results per variant battery. Piece 2 needs a way to clear it.
- **Blocked pins work but are thinly tested.** One runner-level test. Piece 4
  should add its own before trusting a ranking.
- **Old routers build.** Commits back to 2026-09-03 link against today's
  stubs; `routeTrace` is a weak symbol for that reason. Keep new harness code
  from naming firmware symbols older commits lack, or make them weak too.
