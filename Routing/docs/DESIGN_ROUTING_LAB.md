# Routing lab: design

Written 2026-11-17, approved the same day. Its four pieces are built
(`Routing/`; its README says how to use them): 1, 2 and 3 on
2026-11-21, and piece 4 on 2026-11-22 from `PLAN_ROUTING_LAB_4_ARRANGEMENTS.md`.
Two more were added on 2026-11-22 and are not built: piece 5 (V6 arrangement
choices, not designed yet) and piece 6 (the lab on the web, designed below,
waiting for Kevin's approval). Piece 7 (a live board) was designed and then built on 2026-11-23, on a trace built from the board captures
of 2026-11-21 and the local server; see "Piece 7 as built" under it.
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
  (Reversed by Kevin on 2026-11-22: see piece 6.)
- The OG router. It has `test/test_routing_og`.
- Changing the router. Findings feed a later router pass. Nothing under
  `JumperlOS/src/` is edited by this project.
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

`Routing/` in JumperlOS, on a branch off `main` (`main` holds the
newest router; `dev` has nothing newer). My call: the harness compiles
firmware sources and shares the HIL fabric model and checker, so it belongs
with the firmware. The earlier split (frontend in Jumperlessim) is not
followed because the page is one file tied to this server's JSON.

```
Routing/
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
`RouteSafety.cpp`, `InfraPaths.cpp` and `JumperlOS/src/boards/*.cpp`. A syntax-only
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

**Variants.** A variant is a complete `JumperlOS/src/` tree: a base plus overrides.
Sources: the working tree (re-run on save), a git ref, or files dropped on the
page. Any file under `JumperlOS/src/` may be overridden, since the fabric tables are in
`JumperlOS/src/boards/v5/board_v5.cpp`. Each variant is cached by content hash.

**Trust boundary.** The server compiles and runs what it is given, so it binds
to 127.0.0.1 only, accepts uploads only to paths under `JumperlOS/src/`, and rejects
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
| dense | the cases in `JumperlOS/test/hil/test_routing_dense.py`, moved to a module both import |
| real | `JumperlOS/test/hil/*.yaml` snapshots, plus anything dropped in `cases/real/` |
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
  added to the case on screen (or starts a netlist when none is) and routed
  at once on the arrangement picked, by the router when it can route that
  copper and by the solver when it cannot. Not in the text above.
- **The router is refused a little more than "V5 with pins taken away".**
  Taking away one pin of a node that keeps another (GND) makes an
  arrangement the solver's alone: the firmware still closes that pin. And a
  run in which the router closes a crosspoint on any blocked pin fails.
- **Only the router's part of the ranking runs from the page.** "Rank now"
  routes the battery without each wire (three minutes for 256 cases) and
  shows its progress. The solver's part ("is the wire needed") is started
  from the command line (`lab.py rank --needed`), because it runs for 40
  minutes over the 244 netlists of its default classes; the page shows its
  columns when the file has them, and a ranking made again keeps them.
- **Needed is asked one wire at a time.** For each netlist and each wire the
  solver is asked whether a routing exists without that wire. Two wires that
  are each not needed may be needed together; that is not asked.
- **A custom set is a run, not a number.** Wires picked with the page's ranking open
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

## Piece 5: V6 arrangement choices

Not designed yet. Kevin chose it on 2026-11-22 as the phase after piece 4:
scoring the V6 proposals and sets of wires taken away together.
`HANDOFF_2026-11-22_ROUTING_LAB_5.md` is what a chat needs to design it.

## Piece 6: the lab on the web

Asked for by Kevin on 2026-11-22: "let's continue implementing this and
getting it to run on the web and publish it to slopswap and then eventually
when it's all sorted out, we can add it as a page to the jumperless docs
(which will just be more the existing V5 routing visualizer for users'
curiosity and less geared toward designing v6". Of three scopes put to him
(look only; route in the page; also compare routers) he chose "2, and put 1
up first". Stage 1 is up: `slopswap.org/routing-lab/`, two exported pages.
This piece is the second scope.

It reverses two things above: "a public hosted site" under "Not in scope",
and approach 2 under "Approaches considered". What was held against
WebAssembly in the browser, and what answers it now:

- *New C++ still needs a local compile.* Still true. The web page routes with
  routers built on the Mac and published with it. Trying an edited router
  stays in the local lab.
- *The judge is written twice.* It is not: the lab's own Python runs in the
  tab (measured below).
- *Fuzz and lane-removal runs are slow in a tab.* Measured: about 17 ms a
  case, so the 256 cases of a ranking's battery take about 5 s and the 2,000
  fuzz cases about 35 s. A whole ranking (94 batteries) would be 7 minutes;
  rankings are published, not made in the tab.

**Why.** So the lab opens from a link, on any machine and on a phone, with
nothing running on Kevin's Mac. The same bundle, cut down to V5, later
becomes a page of the Jumperless docs for the curious.

### Approaches considered for the web

1. **Published pages only** (stage 1). Nothing is live: no clicking nodes
   together, no run without some wires. It is what `export` already made.
2. **The router as WebAssembly, the lab's Python in the tab under Pyodide
   (chosen).** One judge, one copper search, one drawing: the files the local
   lab runs, unchanged. The cost is the Python runtime, about 6 MB to fetch
   compressed, once.
3. **The router as WebAssembly, the judge and the rest rewritten in
   JavaScript.** Light to load. But about 2,500 lines of Python would exist
   twice and have to be kept the same by a test over the whole battery, and
   the design's first failure is "a score that is about the harness and not
   the firmware".
4. **A server that runs the lab.** It compiles and runs what it is sent,
   which is why the local server answers only to 127.0.0.1. Not for a public
   site. A server is needed only for the exact solver on demand; see "What
   needs a server".

Kevin picked the scope and left the how to me, so 2 is my call.

### Measured before designing it (2026-11-22, router at 5374d38)

Throwaway prototypes, for sizing.

- **The router compiles to WebAssembly unchanged**, with emsdk 6.0.9 and the
  flags of `harness/build.sh` less the sanitizers: 205 KB (73 KB compressed),
  5 s to build. Its output is the native harness's, byte for byte, on all
  2,259 cases of the battery.
- **It runs as a stand-alone program with a host of eight functions**
  (arguments, read, write, seek, close, exit, and two no-ops), one fresh
  instance per case, synchronously: 1.3 ms a case, and the same output on the
  259 cases of dense, real, stress, beyond, edge and typical. The text must be
  read as `subprocess` text mode reads it: `\r\n` and `\r` become `\n` (the
  `b` report has both).
- **The lab's Python runs under Pyodide as it is** (Pyodide 314.0.8, Python
  3.14.2; the lab imports only the standard library). Those 259 cases judged
  and painted: 4.2 s against 2.4 s under the Mac's Python, 16 ms a case, and
  the JSON is identical (11.7 MB). The slowest case is 450 ms
  (`one_net_forty_nodes`).
- **Pyodide is five files**: 9.6 MB, 2.5 MB, 1.25 MB and two small ones;
  about 6.3 MB compressed. It started in a second under Node. A phone was not
  measured.
- **Stage 1's pages** are 3 MB each (56 and 59 cases, their ranking) and 0.3
  MB over the wire.

### What it is

- **One page, three places it gets its answers.** The page asks everything
  through `api(path, body)`. Today that is the local server, or the data an
  exported page carries. The third is an engine in the tab. The page's code
  stays one.
- **The engine is the lab.** A Web Worker holds Pyodide, the lab's Python
  files as they are, and the routers. It answers the paths `server.py`
  answers, with the same JSON, by running the same functions: the API's
  methods move out of the HTTP handler into a class with no HTTP in it, which
  both the handler and the engine call. Nothing that judges, searches copper
  or lays out the drawing is written a second time.
- **One fresh router instance per case**, as the one-process rule says. The
  seam is `runner.run_harness`: in the tab it starts the WebAssembly program
  with the case on its stdin where the local lab starts a process. A battery
  runs one case after another.
- **Routers are published, not built in the tab.** `lab.py web` builds each
  router it is given (a git ref, or the working tree) for the browser and
  lists it under the hash its native build has, so a ranking and a published
  run find their router. The Router and Baseline boxes pick from that list.
  Dropping source files is not offered on the web; the page says the local
  lab does that.
- **The trust gate.** A router is listed only if its WebAssembly build prints
  what its native build prints, byte for byte, for every case of the battery;
  `lab.py web` checks it and refuses otherwise. And a test asks the engine and
  the server the same things over the battery and wants the same JSON. The
  board check still stands behind the native harness alone; the page says
  which router it is and that the copy in the tab was checked against it.
- **What runs live.** Run, on any arrangement the firmware's router can
  route; a baseline; two nodes clicked together, and "start from the case
  shown"; wires taken away and "Run without these"; a board's `b` output
  pasted or dropped; compare; resistance; missed paths and spare copies.
- **What is published data.** Everything from the exact solver. The rankings
  on file travel as they are, each with when it was made. The solver's
  answers are asked for at publishing, for a set that is written down: every
  published case (the classes `lab.py web` is given; dense, real, stress,
  beyond and edge if none), as each published router routes it on each
  arrangement it can route, asked on that arrangement and on every
  arrangement of the same feed that only the solver can route, under both
  rules, at 20 s with the fewest crosspoints wanted. The tab asks with those
  same settings and cannot change the seconds, so it finds each answer under
  the key the lab keeps it by (the question, the rule, the limit, and the
  bytes of `solver/solve.py`, which travels unchanged for that reason). "Ask
  the solver" on one of those cases gives the published answer; on anything
  else, for example a netlist made by clicking, it says the solver is not on
  the web. An arrangement only the solver can route shows what was published
  for it; nodes clicked on it are not routed, and the page says why. "Rank
  now" is not offered. My calls.
- **It opens at once.** The page first shows a published run, as stage 1's
  pages do, and can be read straight away. The engine is fetched when
  something live is first asked for, and the page says how far along it is.
  After that it comes from the browser's cache.
- **A case that never comes back.** The engine is one worker (slopswap
  cannot set the headers that shared memory between workers needs). It hands
  the page each case as it finishes. If one has not come back in 20 s the
  page ends the worker, starts another and goes on with the rest; the new
  worker reports that case as a timeout, as the local lab does. What must
  outlive a worker is kept by the page and given to the next one: the results
  so far, any arrangement made here by taking wires away, and a board's
  pasted output.
- **The bundle is one flat folder** of files that name each other by relative
  path, with nothing fetched from another site (slopswap's rules, and the
  docs' later): the page, the worker's script, Pyodide's files, the lab's
  Python as one zip, a `.wasm` for each router, a list of the routers, and
  the published runs, rankings and solver answers as JSON.
- **One command makes it.** `lab.py web OUT --variant REF ... [--classes ...]
  [--theme FILE]` writes the folder: the routers, the run the page opens on
  (the first router, on V5, the classes given), the rankings on file for
  those routers, and the solver's answers for the set above. It needs emsdk,
  the pinned Pyodide (`lab.py web-setup` fetches it once, as `solver-setup`
  fetches OR-tools) and the solver; without the solver it publishes no solver
  answers and says so. The first time it asks the solver for everything
  (minutes to an hour); after that the answers are on file. The build script
  for the browser is not under `harness/`, whose hash is what the board check
  vouches for. The theme is what `slopswap/.Routing_dress.py` does
  to stage 1's pages (the site's stylesheet linked, the lab's colours pointed
  at it, a title, a description and a breadcrumb, and a refusal to write a
  page that holds the home path), given as a file so the local page keeps its
  look. Publishing is copying the folder into `slopswap/routing-lab/` and
  pushing; the live page becomes that folder's `index.html` and stage 1's two
  pages are removed. My calls.
- **On a phone** it is the one-column page of stage 1, and a tap on a node
  picks it up as a click does. Checked at 375 px before it is published.
- **The KiCad sheet** is fetched only when its tab is opened (10 MB, 1.4 MB
  compressed). The r7 project is in the public JumperlessV5 repository. It
  is published when `lab.py sheet` has been run in the checkout (it needs
  `kicad-cli`); without it the tab says the sheet was not published. My call.
- **The docs page, later.** The same bundle with a switch that leaves out the
  arrangement picker, the ranking and anything said about V6, in a flat
  folder of its own as `docs/pixelmap/` is. Not designed further here.

### Where the lab meets the machine

The Python files are one set, serving the local lab and the tab, and the
local lab behaves as before. These are the places that need a process, a
thread, git or a compiler, and what each does in the tab:

- **Starting the harness** (`runner.run_harness`): the WebAssembly program,
  one fresh instance, read as text mode reads.
- **Building a router** (`variants.build`) and **finding one**
  (`variants.resolve`, and the server's own `resolve`): the published list.
  A name not on it is refused with the list.
- **The pool of threads** in `runner.run_battery`: one case after another.
- **The timeout**: made by the page's 20 s, as above, since the tab cannot
  interrupt a running instance.
- **The solver** (`ceiling.ask`, and the checks that it is installed): a
  third state beside "installed" and "not installed", which is "published
  answers only". The page shows the ask buttons with the seconds fixed.
- **The run the page opens on**: the engine is given it when it starts, so a
  case of it can be asked about without routing it again.
- **"Checked against a board"**: published with the router's list. The tab
  does not hash `harness/`.
- **Off in the tab**: dropped source files (`/api/paths`), "re-run on save"
  (`/api/watch`), making a ranking (POST `/api/rank`), the sheet's build.
- **Files by path.** The lab finds `test/hil`, its cases, its arrangements
  and `solver/solve.py` by where they are, and stamps its cache with the
  bytes of five of its own files. So the zip is unpacked in the tab as real
  files in the same places. A ranking is put where `rank.path` looks.
- **Two Pythons.** The Mac's is 3.13 and Pyodide's 3.14. The battery's
  generated classes come from seeded `random`; the test of the engine against
  the server covers every class, fuzz too, to show they come out the same.

### What needs a server

Nothing in this piece. Two things would, if Kevin wants them on the web: the
exact solver on demand (routing nodes clicked on copper only the solver can
route, and any question not asked on the Mac first), and trying a changed
router without building it on the Mac. `HANDOFF_2026-11-22_ROUTING_LAB_HOSTING.md`
says what each would take.

### Not in this piece

- The exact solver in the tab, and compiling a router in the tab.
- Making a ranking in the tab.
- The docs page itself.
- Keeping anything between visits (a netlist drawn, a run). A reload starts
  from the published run.
- Anything under `JumperlOS/src/`, and anything under `Routing/harness/`.

### How we know it works

- The gate above: every listed router's WebAssembly build against its native
  build over the whole battery, and the engine's JSON against the server's.
- In a browser, from the published folder, with the network panel showing no
  request to another site: the page opens on the published run; two nodes
  clicked on `v5` are routed and drawn; the same on `v6_feed_off` has no feed
  bridge; a dense case's wires taken away and run; a `b` report pasted; the
  page's ranking shows the published one; `v6_rails_on_chips` shows its
  published answers and says why a click is not routed.
- The same at 375 px.
- The local lab's tests and its page behave as before.

### Left to the builder

- How the worker and the page talk, and how progress is shown.
- How the Python and the published data are packed, and whether the browser
  keeps the engine's cache of results for the tab only.
- How `lab.py web` finds emsdk and Pyodide, and what it says without them
  (the tests that need them skip, saying why, as the solver's do).
- The names of the files in the folder.

## Piece 7: a live board

*Written 2026-11-23, after Kevin answered the draft plan's six questions. The plan is
`PLAN_ROUTING_LAB_7_LIVE_BOARD.md`; the firmware reading behind this section is
`NOTES_2026-11-23_FIRMWARE_PORT7_AND_TAPS.md` (by reading, on no board). Built since, on a built trace (no port 7 exchange recorded from a board): see "Piece 7 as built" below.*

Kevin's ask (2026-11-23): "connect to a jumperless from the browser and show a live updating view of the
routing on a real jumperless".

### What it is

A button on the page connects to one Jumperless V5 over Web Serial, on the board's fourth USB serial port (the
machine backchannel, "port 7"). The page then shows that board's routing as a case named `live_board`, in every
view, judged against the schematic like any board's own output, and redraws it when the routing changes, with what
changed lit in a colour that is not a problem's. The page only reads. It never routes, clears or loads anything on
the board.

### Kevin's answers, and what each decides

1. **One bench sitting: yes.** The plan's last task is one sitting with a V5 on the Mac. With the firmware calls
   below it means flashing that board once, and flashing is asked for at the time, as always.
2. **No line on his terminal because the page looked.** Asked whether a "Couldn't find a path" line per change was
   acceptable: "in general no unless it really can't find a path", and "if it's for the probe and there's an alt
   route with the dac that's fine if it reroutes it". By the firmware (notes A1, A2): `b` re-runs no routing, but
   every `b` (and every `n`) calls `couldntFindPath(1)`, which prints one line per failed primary on the main port
   and marks those paths again. So **the page never sends `b` or `n`**. It reads the report through a new call that
   prints the same three blocks and nothing else. A line the firmware prints when a routing pass really fails is
   the firmware's own and stays.
   The probe's own connection has no reroute of the kind Kevin describes (notes A3): its candidates (DAC 0, then a
   free GPIO) are chosen by what is claimed, never by whether the pair routed, and a feed that does not route gets
   only the generic line. That is a gap in the firmware, listed below; this piece shows it as it is.
3. **The firmware may gain calls on port 7.** Three, all reads:
   - `:gen` prints `gen{<routingGeneration>,<idle>}`: the counter that moves at every rebuild and send, and
     whether the second core is idle. The page asks this, twice a second, and nothing else while the number
     stands.
   - `:paths` prints what `b` prints (the bridge array, the path table, the chip status, same headings, so
     `Routing/board.py` reads it unchanged) without `couldntFindPath` and with terminal colours off.
   - `:crossbar` waits for the second core before it copies the chips' state, so a scan tap in flight is never in
     the dump.

   Old firmware answers `unknown_verb`. The page then says the board's firmware is too old for a live view and
   which version has it. It does not fall back to `b`.
4. **"Sent equals planned" is checked.** Kevin: "if there's no room for the scan it'll use it for user routing (if
   not, it should do that)". By the firmware (notes B1, B2): a tap is planned fresh on copper that is free, held
   about a millisecond and opened; the router never sees taps, and a primary is never refused for one. So with the
   tap-free `:crossbar`, the dump equals the path table's crosspoints whenever `:gen` says idle, and the page
   checks exactly that. One thing differs from what he remembers: stacked copies (not primaries) give way to a
   reserve kept for taps, and that reserve applies even with the scan off. Listed below; his call.
5. **One board, read-only.** One link, one case. Every V5 has the same serial identity, so two could not be told
   apart anyway.
6. **OG boards are out for now.** An OG's report is refused with the lab's usual message.

### How the page talks to the board

- Nothing is sent until the user clicks Connect, and a reload does not reconnect by itself. What the page sends is
  written beside the button, and every byte sent and received is kept in a trace the user can save.
- The picker is filtered to the Jumperless's USB identity (`1D50:ACAB`). All four of the board's ports share it,
  so the page proves it has the right one before anything else: it sends the single byte `N` and wants a net list
  back. Never a `:` before that: on the main port `:` sets a DAC voltage. The port is opened at 115200 and at no
  other speed.
- Then `:ver`, then `:gen` every half second. When the number has moved and the board is idle: `:paths` and
  `:crossbar`, one query unanswered at a time. A board that is silent (by reading, port 7 is not answered in probe
  mode, the menus or an app) is "waiting", not an error and not red.
- The text goes to the lab's own judge: the local server's `/api/board` today, the engine in the tab when piece 6
  is built. Nothing new is needed in the page for that.
- Browsers without Web Serial (Safari, Firefox) get the button disabled with the reason; paste and drop stay.

### How we know piece 7 works

A fake port that replays traces drives the page's port code under `node` and the whole page in a browser
(`serve --replay`). The bench sitting records a real trace, which becomes a fixture. On the bench: Kevin's
terminal on the main port stays silent while the page is connected and the board is still; a change by probe, by
terminal and by slot shows on the page within a second of the board going idle; a bridge that cannot route is
shown as not routed with one line on his terminal, when it fails, and none after.

### The firmware's part

In JumperlOS, on a branch in a worktree of its own (never Kevin's main checkout, which holds someone else's
uncommitted work), built for both targets, the bench suite run, and not pushed without Kevin's word. This
repository's submodule moves to that commit only once it is on GitHub. Until then the page's side is built and
tested against a built trace.

### Asked of the firmware, and not in this piece

- Port 7 answered in probe mode and the menus (a service of its own with a guard against re-entry; medium risk).
- `b` and `n` printing "Couldn't find a path" only to the port that asked.
- The probe's connection falling back to its next candidate when the chosen pair does not route.
- The tap reserve applying to stacked copies only while the scan is on.
- A list of the planned taps (`:taps`), for drawing them.

### Piece 7 as built (2026-11-23)

Status: built and tested on a trace built from the board captures of 2026-11-21, with made-up `N` and `:gen`
answers, on the local server (`lab.py serve`). No port 7 exchange has been recorded from a board yet. The bench check on a real
board has not been made, so nothing here is known of a board's own behaviour, and there are no bench findings. The
firmware's three calls are on a branch of JumperlOS (`port7-routing-reads`, commit `f963e4c`, in a worktree), not
released and not on GitHub, so no released firmware answers them. The submodule is not moved to it, and
`BOARD_PORT.NEEDS` still names a release that is not out. The page's code is `web/board_port.js` (the replies read,
`FakePort`, `BoardLink`) and `connectBoard` and `showReading` in `web/lab.js`; the server gained `board.changed` and a
linked board with nothing on it (`POST /api/board` takes `about` and `live`); `serve --replay TRACE` plays a trace
through the page. "How the page talks to the board" above is built as written, except in these points, where the
build says more or says otherwise:

- `:gen` is asked once more right after the dump, and a reading counts only when both answers say idle with the same
  number.
- **read again** reads the report and the dump whatever the counter says, when the board is idle.
- A reply counts as begun only once the board has echoed the query. A stray line is neither an answer nor a reason
  to ask again. A reply that begins and stops for three seconds is thrown away and asked once more. A board that
  does not answer is waited for with no limit, and only Disconnect ends that.
- The wait between polls is not cut short by anything the board sends.
- Only the timings can be overridden. The speed, the buffer and the five things sent are fixed.
- What changed is marked in all three views: a closed crosspoint is ringed in the colour of a change (not red), and an
  opened one is grey (a small ring in the fabric, a dashed curve on the sheet, an outline in the crossbars). A redraw keeps the zoom, a docked
  view and the lit net, by its number: a board that renumbers its nets has another net lit.
- Running the battery while linked keeps the battery on screen. The status line then says the board changed, and a
  click on that brings the board's case back.
- A failed connect (busy, wrong port, firmware too old) leaves the page not linked. "Save trace" is a button.
- An exported page hides the Connect row.

Still to do: the bench sitting (Task 6 of the plan), and the submodule and `NEEDS` once the firmware's commit is on
GitHub and released.

### Not in piece 7

Writing to the board. Two boards. The OG. A stand-in for Web Serial. The board's LEDs, OLED and voltages (that is
Jumperlessim's viewer). The published page, until piece 6.

## Piece 8: told, not asked, and the firmware's fixes

*Written 2026-11-23. The plan is `PLAN_ROUTING_LAB_8_WATCH_AND_FIRMWARE.md`. Nothing here is built. The firmware was read
in the worktree `JumperlOS-port7` at `44b1ba9`; the router numbers below were measured in the lab on scratch variants of
the pinned router (`5374d38` with files replaced), on no board. Built since, and run on no board: see "Piece 8 as built" below.*

Kevin's ask (2026-11-23): "How does it poll for updates to the routing on port 7? maybe we need a command that says 'send
me a message when [thing, in this case routing] changes', if it doesn't exist, add it and make sure it's documented in
both the docs and skill. And do the firmware fixes and we can test on real hardware later".

### What it is

Today the page asks `:gen` twice a second and the board never speaks first about routing. Piece 8 adds a command that
makes the board say when its routing has changed, has the page use it, and builds the five fixes piece 7 left with the
firmware. All of it is built and proved as far as a host can prove it. The bench sitting comes after and is not part of
the build.

### The watch command

`:watch:<topic>:on` and `:watch:<topic>:off`, on port 7. One topic exists: `routing`. Every line the board can send:

| Asked | Answered (after the echo of the line, as for every verb) |
|---|---|
| `:watch` | `{"watches":{"routing":"off"}}` (or `"on"`) |
| `:watch:routing` | `{"watch":"routing","state":"off","gen":<n>}`: the state, nothing changed |
| `:watch:routing:on` | `{"watch":"routing","state":"on","gen":<n>}` |
| `:watch:routing:off` | `{"watch":"routing","state":"off","gen":<n>}` |
| `:watch:<other>`, with or without a state | `{"error":"unknown_topic","topic":"<other>","topics":["routing"]}` |
| `:watch:routing:<other word>` | `{"error":"watch_usage","fmt":":watch:<topic>:on\|off","topics":["routing"]}` |
| nothing (the watch is on) | `changed{routing,<n>}` |

- `<n>` is `routingGeneration`, the number `:gen` gives. `:on` marks that number as told, also when the watch was on.
- **When `changed{routing,<n>}` is sent.** At the end of a pass of the port's service, after every inquiry that was
  waiting has been answered: when the watch is on, the generation is not the one last told, the board is idle (the test
  `:gen` reports, `core1req::allIdle()`), and the port's buffer can take the whole line. Then the line is written and
  `<n>` is marked as told. So a reader can ask `:paths` and `:crossbar` at once; several rebuilds before the board goes
  idle give one line with the latest number; the line is never inside a reply and never between an echo and its reply.
  A line the buffer cannot take is not written and is tried again at the next pass.
- **What turns it off.** `:off`, a reboot (it is off at boot), and a fall of port 7's DTR line, which is the host closing
  the port where the host had raised DTR. `:oled:stream` and `:padgate` do not do the last: they stay on until turned
  off (`Ser3Backchannel.cpp:801-849`, `oled.cpp:4035`). The watch differs because the next program on the port did not
  ask for its lines. The line is read with `tud_cdc_n_get_line_state`, not `USBSer3.dtr()`, which the `ignore_dtr`
  setting fakes. A host that never raises DTR keeps its watch until `:off`, but hears its lines only with
  `usb_cdc.ignore_dtr` on: by default the board drops what it writes to a port whose DTR is down. Not established: that Chrome raises DTR on
  open and drops it on close. Nothing depends on it: a line nobody reads is dropped, not waited on.
- **`:stop`, `:repeat`, `:every`.** `:stop` cancels a capture and leaves a watch as it is, as it leaves the OLED stream.
  `:repeat` and `.` run the last inquiry again, so after `:watch:routing:on` they acknowledge again. `:every` holds the
  port's service for the whole capture, so no `changed{}` line is written during one; it comes after `cap_end`.
  `:every` with a watch verb runs it each sample, as it does `:oled:stream:on` today. None of the three is changed.
- **Old firmware** answers `{"error":"unknown_verb","verb":"watch:routing:on"}`.
- The mechanism takes a topic name. Only `routing` is built.

### How the page uses it

- After `N`, `:ver` and `:gen`, as today, the page sends `:watch:routing:on`. Acknowledged: it stops the half-second
  poll. An error line in answer (older firmware): it polls every half second as piece 7 does, and says so.
- While the watch is on and the last answer said idle at the generation shown, the page asks nothing but `:gen` every
  3 s. That is only to notice a board gone silent and a line that was lost. Three seconds: a still board gets 20
  questions a minute where it got 120, a lost line costs at most 3 s, and silence is said within 4.5 s (3 s, and the
  1.5 s the page already waits before saying "waiting").
- A `changed{routing,n}` line ends that wait: the page asks `:paths`, then `:crossbar`, then `:gen`, and the reading
  counts only when that `:gen` says idle at `n`, as today. If it does not, the round goes on from that answer.
- The line is found by its whole shape on a line of its own, in everything the port receives, whatever else is out.
  It is never the answer to a query, and no reply is taken for it. After a round the page waits at least 100 ms.
- On Disconnect the page sends `:watch:routing:off` and waits at most 300 ms for the answer, then closes. With a query
  still unanswered it closes without sending, so "one query unanswered at a time" holds.
- **Seven things, and no other byte:** `N`, `:ver`, `:gen`, `:paths`, `:crossbar`, `:watch:routing:on`,
  `:watch:routing:off`. The page's "what the page sends" paragraph, its tests and its README change with the list.
- In a trace, bytes that arrive unasked and end in a `changed{}` line are a line of their own with `"sent": null`,
  and the fake port sends such a line by itself. Bytes that arrive unasked while a query is out stay in its `got`.

### The firmware's fixes, and the bound on each

- **F1. `:paths` waits out a sense tap.** It copies the router's ledger (288 bytes) the way `:crossbar` copies the
  crosspoints (wait for the second core, copy, look at `core2busy`, four tries) and prints Chip Status from the copy.
  A tap's net 59 that still shows after that is a claim that outlived its tap, which is worth seeing; the lab's reading
  of 59 as free stays. Bound: `printChipStatus` gains an optional second parameter in both router copies; without it
  the function prints what it printed. The OG's copy needs the parameter because the header is shared.
- **F2. `b` and `n` asked on port 7 print nothing on port 1 and mark nothing.** The lines are not produced for a
  port 7 asker. `couldntFindPath` prints and marks in one loop and has an OG copy that differs, so sending its lines to
  the asker would mean splitting the router's function twice; and the failures are already in what `b` prints (a row
  of -1 in the Paths table). The change is in the two handlers, which both targets share: when the asker is port 7
  they skip `couldntFindPath` and print with colours off. On the main terminal `b` and `n` are untouched.
- **F3. Port 7 is answered in probe mode and the menus.** The call in the main loop stays where it is. A new service in
  the set the modal loops keep alive answers the port only while `probeActive`, `inClickMenu` or `inPadMenu` is set and
  the main loop's call has not run for 50 ms. There it answers `N`, `:nets`, `:ver`, `:gen`, `:paths`, `:crossbar`,
  `:xbar`, `:watch…` and `:stop`, and refuses everything else, `:every`, `:bench` and the long reads among it, with
  `{"error":"busy","reason":"modal",…}`. Bounds: one flag keeps either entry from running inside the other; a `:` line
  is waited for 25 ms there, not 2 s; the tap wait is skipped there, because the scan does not tap in those modes (a
  guide's one-shot tap can, during a menu, and is not guarded); the service runs at most every 5 ms; only a V5 has it. What can go wrong: a `:paths` reply is about 4 kB written between two probe ticks,
  and a host that holds the port open and stops reading stalls the probe as it stalls the main loop today.
- **F4. The probe's feed falls back.** When a rebuild leaves the feed's pair with no crosspoint and another candidate
  is free of claims, one more rebuild is asked for; its evaluation leaves the failed candidate out and takes the next.
  The failed candidate stays out until a user bridge is removed (only that frees copper) or the board reboots, so the
  feed cannot flip back and forth: at most one extra rebuild for each removal. A forced candidate is never left out,
  and when nothing else is viable the failed one is kept, as today. It helps a board set GPIO-first whose GPIO feed
  cannot route while DAC 0 can. It does not help the board capture `k_rows_overflow_metric`: there DAC 0 is the
  user's and every K row is taken, so no candidate routes. The OG has no feed and no change.
- **F5. The tap reserve only while the scan is on.** The three tests that deny a stacked copy the last K row, the last
  tap-capable bounce chip, the last lane into I, J, K or L and the last hub lane into K ask
  `measurement.net_currents` first. A change to that setting asks for a rebuild, so turning the scan on gives the
  taps their copper back. Bounds: with the scan on, which is the default, routing is unchanged. With it off, the guide
  checks' one-shot taps, which run with the scan off, can find no route and fail `noroute`; a tap never shares copper
  with another net. The OG router has no reserve and no change.

### How it is proved without a board

- Both targets build (`jumperless_v5`, `jumperless_og`), and `test/test_routing_og/run.sh` passes after each fix.
- **F5, measured:** on all 2273 cases of the eight classes, routed twice each, the changed router with the scan on gives
  the pinned router's report and crosspoints, byte for byte. With the scan off (a variant whose `config.h` default is
  0; the harness has no knob for it) 594 cases gain stacked copies, 22 lose one (typical 6, fuzz 16), none loses a
  primary, and three of the five dense cases that are proofs of taps fail their proof, which is what the setting means.
- **F4, measured** (one variant with every router-side edit of F1, F4 and F5): it gives the pinned router's results on
  all 2273 cases; the fallback fires in none, because in the three whose feed is unrouted DAC 0 is the user's. The stress case `gnd_two_rows_every_chip` with the
  feed GPIO-first, sent three times to one harness process: 16 of 17 primaries, then 17 of 17 with the feed on DAC 0,
  then the same again. On the pinned router it is 16 of 17 three times. This is a lab test and not a battery case: the
  runner judges the first rebuild and calls a different second one a problem.
- The harness is not edited. It does not run `Commands.cpp`, so the extra rebuild itself and the rebuild on a changed
  setting are seen only at the bench.
- **W and F3:** the rules (what `:watch…` asks, when a line is due, what a modal context answers) are in one header
  with no Arduino in it, checked by a host program, `test/test_ser3_rules`. The page's node tests run a fake port that
  sends `changed{}` lines: after a reply in one chunk, split across chunks, during a query, and never.
- **F1, F2:** no host test; the firmware has no host build of the port or the command handlers. They build, the lab
  shows `printChipStatus` prints what it printed, and their bench checks are written.

### What waits for the bench

Written into `test/hil/test_port7_reads.py` and the plan's checklist, and run by nobody yet: every line of the watch
on a board; that a line follows a change within a pass of the board going idle; DTR on open and close from Chrome and
from pyserial; port 1 silent while `b` and `n` are asked on port 7; Chip Status free of 59 over 100 readings with the
scan on; port 7 answered in probe mode and in each menu, and the probe's tick gap (`X`) with and without the page
connected; the feed falling back on a board set GPIO-first, with one extra rebuild and no more; copies and taps with
the scan off, and after it is turned on again.

### Piece 8 as built (2026-11-23)

Status: built, and proved only as far as a host can. Nothing has run on a board: no firmware here is flashed, no port
7 exchange of the watch has been recorded, and the bench checks are written and compiled and not run. The port's rules
(what `:watch` asks, when a line is due, what probe mode and the menus answer) are checked by a host program,
`test/test_ser3_rules`; the page is tested on traces built by its tests (`tests/fixtures/port7_watch_built.jsonl`);
F4 and F5 are shown in the lab on the host router (`tests/test_firmware_fixes.py`, classes `Feed` and `Reserve`). F1 and
F2 have no host test. The extra rebuild F4 asks for and the rebuild F5 asks for on a change of the setting are proved
nowhere: the harness does not run `Commands.cpp` or `configManager.cpp`. Both firmware targets build and
`test/test_routing_og/run.sh` passes.

The heads, none of them pushed (the firmware, documentation site and canonical skill branches have no upstream):

- Firmware: `port7-routing-reads` in the worktree `JumperlOS-port7`, at `9356cc1` (the skill's section on port 7,
  `4f4ef56`, its corrections `6892af5`, and the whole-branch review's fixes). The plan's commits on it: `67e1fe0` (F2), `bf249ce` (F1), `3f6a3c4` (the watch), `5c9a649` and its fix `0d8b866`
  (F3), `d2a11a1` (F5), `527c988` (F4). No release has them; they need firmware newer than 5.7.11.5, and a build of
  the branch still says 5.7.11.5 to `:ver`.
- Documentation site: `port7-watch` in the worktree `Jumperless-docs-port7`, off `origin/main` (`7707c2a6`), at
  `887f6b46` (`673494ee`, its corrections and the whole-branch review's fixes): `docs/07.5-automation.md` and `docs/jumperless-agent-skill.md`. It
  documents verbs no released firmware has, and the main checkout has uncommitted edits to both pages that it will meet at merge.
- Canonical skill: `port7-watch` in the worktree `Large-Breadboard-Model-port7`, off `origin/main` (`437e7c0`), at
  `7429777` (`2d1831e`, its corrections and the whole-branch review's fixes).
- Jimulator: `main`. The plan's lab commits: `f8bd936` and its fix `270acff` (the page), `fd06a38` (the plan's text
  after review), `4a10c7c` (`Reserve`), `eac0e36` (`Feed`), `8a37b2e` and `7dd4ede` (the documents and their
  corrections), `b042c36` (the whole-branch review's fixes).

Built: all eight tasks (F2, F1, the watch, F5, F4, F3, the page, these documents), and an addition to the last:
the same section went into the canonical skill, `SKILL.md` and a new `reference/port7-backchannel.md` in
Large-Breadboard-Model, on a local branch `port7-watch` in the worktree `Large-Breadboard-Model-port7`, because the
firmware repository's skill file is marked superseded. That branch is not pushed, and that repository's checkout
has uncommitted edits to `SKILL.md` that the branch will meet at merge. None was dropped. The documents had one
round of corrections after review, in all four repositories. What is above is
built as written, except in these points, where the build says more or says otherwise:

- **Which menu answers how.** Only a menu printed on the terminal without the columns view and with line buffering
  on runs the main loop's entry, from its list loops only: there a verb off the short list is answered while the
  menu's list is showing, and may be refused as busy on its option, node and yes/no screens. Every other menu
  (the columns view that `K` opens, a menu on the board alone, a terminal menu with line buffering off) gets the
  short list, as probe mode does. The spec's words, that
  a click menu on the terminal with line buffering on runs the main loop's entry, describe that rarer path. The main
  loop's entry is stamped when its pass ends as well as when it starts, so a long normal pass keeps the modal one out.
- **Refused in a modal pass:** `:repeat` and `.` too, with `b`, `n`, `:help` and `:cmds`. A `:` line there is waited
  for 25 ms from its last byte, so a host that trickles bytes can hold the probe longer; the page sends whole lines.
- **F4.** The failed candidate is not kept out for good. While the feed has fallen back, each removal of a user bridge
  lets it be tried once more: if it still does not route, the feed goes to it and back one rebuild later (two
  rebuilds and a short gap in the feed for that removal). The extra rebuild is asked by a tick that does not run in
  probe mode, so there it waits for the next rebuild or the end of probe mode.
- **F5.** The rebuild on a change of `measurement.net_currents` happens for a change made through the config's live
  set path: `i` (which writes its alias `display.net_currents`), a line typed at the `` ` `` config prompt, and the
  settings menu's edits and its reset of one option. `config reset`, the `clear_*` commands (`clear_calibration`,
  `clear_hardware`, `clear_all`) and the settings menu's full reset replace the whole config and skip it: after one of those, copies made
  with the scan off keep the taps' copper until the next rebuild. By code reading only.
- **The page.** Its paragraph on what it sends says five of the seven are questions, and that `:gen` is asked every
  three seconds while a watching board is still and twice a second while its routing is changing and on firmware
  that cannot watch. A `changed{}` line that comes while a round's first `:gen` is out is kept and starts the next
  round. The status sentence the page shows while a board is silent says words true of both firmwares: the board
  does not answer port 7 in an app or a running script, nor, on released firmware (5.7.11.5 and before), in probe
  mode or a menu.
- `:watch:` with a trailing colon answers the list of watches.

Still to do: the bench sitting (the plan's checklist "When a board is on the bench"), a
push and a release of the firmware, the submodule's move and `BOARD_PORT.NEEDS`, and the merge of the documentation
site's branch and of the canonical skill's branch. Each waits for Kevin.

Open from the whole-branch review (2026-11-23). It found no difference between the bytes the firmware writes and the
bytes the page reads, and nothing that must be fixed before a flash. These it left open, each Kevin's call:

- **A glance in the Slots picker can set F4 off.** Every detent on a slot that has a file is a rebuild that
  `infraEvaluate` begins (`previewSlotColors` in `LEDs.cpp`, then `loadSlot` in `States.cpp`), so its routing is
  noted like any other. If a slot glanced at leaves the feed's pair unrouted, the candidate can be barred, the feed
  moved, and `[infra] probe_power: ... did not route` printed for a slot that was never loaded; back on the user's
  own slot the feed can stay on its other candidate until a bridge is removed or a reboot. There is no loop and the
  probe keeps its power. Not fixed here: a fix is new state in the feed or the slot manager that nothing on a host
  can run. Two ways to do it: clear the bar where a slot's bridges are loaded (`infraScrubLoadedBridges`), or take
  no note and move no bar while a preview is up. F4 reverts alone (`527c988`).
- **The service table is full.** `MAX_SERVICES` is 24 and a V5 now registers 23, or 24 with the file cache.
  `registerService` drops a service past the limit without a word. Raise the limit before another service is added.
- **A client that polls in probe mode.** A verb off the short list is refused `busy` there, where released firmware
  says nothing. Jumperlessim's viewer asks `:leds:all` every 50 ms, so in probe mode it gets a refusal each time,
  and each one takes time from the probe's loop. Bench.
- **The page does not ask for the watch again.** If a board's watch ends without the page's doing, the page reads
  changes by its 3 s `:gen` for the rest of the link.
- **Older than this piece, seen while reviewing it.** With `serial_1.function = 0` at boot `USBSer1` is not begun,
  so the fourth port is not the backchannel and the watch's DTR test reads the wrong interface. Previewing a slot
  that has no file leaves the last slot's crosspoints closed (`enterPreviewMode` in `States.cpp`), which the page
  can now show while a menu is up. The firmware's comments say a slot preview never calls `infraEvaluate`; the
  path through `loadSlot` does.
- **For the bench, besides the plan's checklist.** Item 6 with Jumperlessim's viewer attached as well. Scroll the
  Slots picker with the page connected. In item 7, browse past the dense slot to one with as many bridges, cancel,
  and look at `i@` and the terminal. Watch the first `:paths` asked in probe mode for a crash: how deep the stack
  is there could not be told by reading.

### Not in piece 8

A `:taps` list of planned taps: a feature, not a fix. Topics other than `routing`. The GPIO candidate trying its next
pin when its pin does not route. Any change under `Routing/harness/`, so the lab's own rebuild does not yet retry as
the board's does and has no knob for the scan. The viewer's verbs (`:leds`, `:oled`, `:gpio`) in probe mode. A push,
a release, a flash, the submodule's move, and publishing the documentation site.

## How we know it works

- At `main`, every must-route dense case routes and the judge is clean.
- Pointed at the commit before the hub rescue tier (`a1accf5^`), the lab
  marks `19-A4` and `20-A5` in `nano_dense_metric` as missed and draws a path
  of four crosspoints. At `main` both are routed.
- Pointed at the commit before the bounce-pin fix (`f41e755^`), the claim
  checks fail on `kevin_fixture_2026_09_02`. At `main` they pass.
- A blocked wire never appears in any path.
- The five dense cases with a taps proof report every tap reachable at `main`.
- `JumperlOS/test/hil/slot3_snapshot_2026-08-26.yaml` imports with its GPIO bridges
  single, as the board leaves them.
- Two crosspoints in series read twice the setting; two such paths in
  parallel read once the setting.
- The solver agrees with hand-checked answers on small made-up fabrics.
- `test/test_routing_og/run.sh` and the HIL suite behave as before.

The two historical checks hold only if those commits build against the stubs.

## Build order

Four plans, each usable when it lands: (1) harness, battery, judge, CLI;
(2) server and page, both views, resistance; (3) ceilings and edge cases;
(4) lane ranking. Added on 2026-11-22: (5) V6 arrangement choices, and
(6) the lab on the web. Neither waits for the other. Added on 2026-11-23:
(7) a live board, which needs calls added to the firmware first. Also on 2026-11-23: (8) a watch command so the board
says when its routing changed, and the firmware fixes piece 7 listed; it builds on (7) and waits for the same bench
sitting.

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
- Any real netlists beyond the two YAML snapshots in `JumperlOS/test/hil/`.

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
