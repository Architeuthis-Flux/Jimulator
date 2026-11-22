# Routing lab: design

Written 2026-11-17, approved the same day. All four pieces are built
(`tools/routing_lab/`; its README says how to use them): 1, 2 and 3 on
2026-11-21, and piece 4 on 2026-11-22 from `PLAN_ROUTING_LAB_4_ARRANGEMENTS.md`.
Piece 4's section below was widened that day, and "Piece 4 as built" under
it says where the build differs from the text. "Learned building piece 1" at
the end changes what the later pieces must do. Piece 3 as built leaves out one thing the text below puts in it: the
tap planner is not yet the oracle for spare copies (see "Honest limit").
Piece 2 as built differs from the text below in one way: the
r7 sheet draws its breadboard-to-breadboard lanes as buses and nearly
everything else as a label on the pin, so the sheet view follows buses and
lights labels and pin ends, not long wires.

The fidelity gate passed on 2026-11-21 against a V5 (21 of 21 dense cases
identical), after one correction: a booted board has `top_oled.enabled` set
in RAM, which moves the probe feed from GPIO 8 to GPIO 6. The tools README,
"Checked against a board", has the account.

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
  **Not built** (2026-11-21): spare copies are labelled "available in copper"
  everywhere they show, and the solver's model does not hold the taps'
  copper either, so its "routable" is a ceiling, not a promise. A cheap first
  answer needs no new code: route the case with every stack setting at its
  highest and count the copies the firmware makes.

## Piece 4: arrangements and the V6 lane ranking

Widened on 2026-11-22 by two answers from Kevin: V6 takes the probe feed off
the crossbars, and the crossbar arrangement must be easy to change while V6
is being worked out. The second is new scope; the lane ranking below is one
use of it.

- **An arrangement is the fabric as a small file**: V5, plus what differs
  (a pin given another wire, a wire taken away, a chip added, a node moved,
  the probe feed on the fabric or off it). Changing the arrangement is
  editing that file; the page redraws from it. There is no on-page editor.
- **Two engines, never mixed up.** The firmware's router has V5 literals
  (`V6_CROSSBAR_MATRIX.md` section 7), so it can route an arrangement only
  when that is V5 with wires taken away, by blocking their pins. The exact
  solver takes any arrangement, since the fabric is data to it. Every table
  and every command says which engine answered, on which arrangement, with
  the feed on or off.
- **What the solver's answer is worth for V6**: a ceiling for any router that
  keeps the path shape (each bridge its own path of at most four
  crosspoints), not what a V6 router would do.
- **Scoring an arrangement**: the battery's netlists, as the firmware builds
  them with the feed off, asked of the solver on the arrangement and on V5.
  Reported: which netlists change verdict, and the fewest crosspoints where
  both are proved. At edge sizes many answers are "unknown", so the count of
  routable netlists is not the headline by itself.

The lane ranking:

- For each of the 80 lanes (48 between breadboard chips, 32 from a
  breadboard chip to an SF chip), the 8 bounce rows and the 6 hub lanes, 94
  wires in all: block it, re-run the battery, record the loss in bridges
  routed, cases fully routed, crosspoints and resistance, per class. Rank by
  least loss. (This text first said "86 lanes", which counted the hub lanes
  twice.)
- The loss is signed. The router is not monotone: with one lane blocked it
  sometimes routes a bridge more. The router's loss is therefore shown
  beside, not as, the answer to "is this wire needed".
- The same against the global search, to separate "the copper needs this
  lane" from "this router happens to use it".
- Raw usage counts are shown beside the loss, labelled as biased by search
  order.
- Custom sets: block several wires together (for example one lane of each
  doubled pair, or three X pins per breadboard chip) and see the combined loss.
- The fabric view takes the loss as a heat overlay.
- The probe feed changes the answer for KL and the K rows. Since V6 takes
  the feed off the fabric (`V6_CROSSBAR_MATRIX.md` P2; Kevin, 2026-11-22),
  the ranking runs with the feed off. A switch runs it with the feed on, as
  a V5 has it.
- Runs as a background job with progress; results are cached by variant, case
  and blocked set.

### Piece 4 as built (2026-11-22)

Built as above, with these differences:

- **A netlist can be made by clicking nodes.** Asked for by Kevin while the
  piece was being built: click two nodes on the Fabric tab and the bridge is
  routed at once on the arrangement picked, by the router when it can route
  that copper and by the solver when it cannot. Not in the text above.
- **Only the router's part of the ranking runs from the page.** "Rank now"
  routes the battery without each wire (three minutes for 256 cases) and
  shows its progress. The solver's part ("is the wire needed") is started
  from the command line (`lab.py rank --needed`), because it runs for 40
  minutes over the 244 netlists of its default classes; the page shows its
  columns when the file has them, and a ranking made again keeps them.
- **Needed is asked one wire at a time.** For each netlist and each wire the
  solver is asked whether a routing exists without that wire. Two wires that
  are each not needed may be needed together; that is not asked.
- **A custom set is a run, not a number.** Wires picked on the Ranking tab
  are taken away together and the battery is run on what is left; the run is
  shown like any other, and the arrangement can be saved as a file and
  scored. No combined loss against the baseline is printed.
- **The drawing of a wire V5 has no shape for** (a rail on a pin of every
  chip) is a bus on a level of its own between the two rows of chips. Its
  pins on an SF chip's X side join on a second level above that row, with one
  vertical run beside the last chip, because an SF chip's columns line up
  with the columns of the breadboard chip under it.
- **Resistance is in the ranking's file, not its table.** The table prints
  primaries, cases and crosspoints; `worst_r` is in the file, for every wire
  and class.

What it measured is in the README's "Findings so far", 11 to 16.

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
  (Answered 2026-11-22: it does not.)
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
