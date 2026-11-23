# Routing lab

Builds the firmware's own V5 router for the host, routes a battery of
netlists with it, and judges every result against the schematic with
`test/hil/routing_check.py`. No board needed. Design:
`CodeDocs/DESIGN_ROUTING_LAB.md`.

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

## The page

```bash
python3 tools/routing_lab/lab.py serve
```

Opens `http://127.0.0.1:8765/`. Pick a router and the classes, press Run,
click a case.

- **What is run, and what is shown.** Each class has its number of cases
  beside it and says what it is when the pointer rests on it. While a run is
  going the page names the classes and the router. Over the table a line
  beginning "Shown:" says what the table holds: which router ran which
  classes, or that it is a board's own output and no run of the router. Rest
  the pointer on it for what every case is judged on. The case panel says
  what kind of case is open: one that must route, one that is scored, or a
  board's routing.
- **Router / Baseline** take `worktree`, a git ref (`main`, `a1accf5^`), or a
  directory given with `--tree DIR` when the server was started. With a
  baseline the table tints each number better or worse, lists regressions,
  and "compare with baseline" draws both routings of the selected case.
- **Trying a change.** Edit the router in this checkout and tick **re-run on
  save**: the battery re-runs when a file under `src/` changes. Or drop
  `NetsToChipConnections.cpp`, `MatrixState.cpp` or any other source file on
  the left column: it is built as "worktree + 1 file" without touching the
  checkout. A router that does not compile shows the compiler's output and
  keeps the last table.
- **Arrangement** is the crossbar copper: V5's, or one of the files under
  `arrangements/` (see "Arrangements"). It is what the Fabric tab draws and
  what Run routes. Run is greyed, with the reason beside it, for an
  arrangement the firmware's router cannot route. A run is drawn only while
  the arrangement it was routed on is the one picked.
- **Click two nodes to connect them.** A click on a node (its dot or its
  label) picks it up and a click on a second makes a bridge. It is added to
  what is on screen: to the bridges of the case shown, or to nothing when no
  case is. The netlist is routed at once with the Router named, on the
  arrangement picked, and shown as a case called "drawn". The box under the
  controls lists its bridges; each can be taken out, and "clear" empties it.
  "start from the case shown" copies a case without adding a bridge. A case
  of the battery is carried with its settings (its stacking, power and
  probe), so the case with nothing added routes as the run routed it; a
  board's output has its bridges only, and they are routed with the
  defaults. A new Run, or a board's output put on screen, starts afresh.
  Pick another arrangement and the same netlist is routed there.
  On an arrangement only the solver can route, the firmware still makes the
  netlist and the solver's routing is what is drawn. Esc, or a second click
  on the same node, lets go. (A click on a node no longer lights its net
  alone; a click on its wire or on a crosspoint still does.)
- **Fabric tab.** The crossbars as grids with every piece of copper between
  them, generated from the arrangement's tables (V5's are
  `test/hil/fabric_v5.py`). A lit wire carries the net of its colour; a dot
  is a closed crosspoint. On another arrangement than V5 a grey cross is a
  pin taken away and a thin ring a pin on another wire than V5 has it on; a
  wire of no shape V5 has (a rail on a pin of every chip) is drawn as a bus
  on a level of its own.
- **Ranking tab.** The fabric tinted by what the router loses without each
  wire, or by how many netlists are proved to need it, with the table beside
  it. See "The lane ranking".
- **KiCad sheet tab.** The board's own schematic with the same result drawn
  over it: lit wires, lanes followed along their bus from chip to chip, a
  dot at each label and pin of a live net, and each closed crosspoint as a
  curve inside its chip from the X pin to the Y pin. Build it once with
  `python3 tools/routing_lab/lab.py sheet [board.kicad_sch] [--theme NAME]`
  (needs KiCad's `kicad-cli`; the default is the V5 r7 sheet in
  `~/Documents/GitHub/JumperlessV5`).
- **Marks, both tabs.** Red is a problem and nothing else is red: a wire
  carrying two nets (a short), a net on a node that is in no net (a stray),
  or a ring where the chip status and the copper disagree (a closed pin
  nobody claims, a claim for another net, or, in the cases judged strictly,
  a claim with no copper). Lighting one net alone never dims what is red. A
  hollow dot or dashed curve is a duplicate path's crosspoint. A small
  square is a pin claimed while no net rides its wire, where that is
  allowed. A dashed ring marks the ends of a bridge that is not there: in
  the net's colour when the router failed it (not routed, or listed as
  routed while its copper does not connect), grey when the firmware refused
  or dropped it by rule. Net colours repeat after sixteen nets.
- Click a net, a lit wire or a crosspoint to light that net alone; it holds
  across the tabs. The wheel (or a pinch) zooms about the pointer, by as
  much as you scroll, so a trackpad and a wheel feel the same; drag pans;
  double-click fits. Hover a wire for its pins and claims.
- **A board's own output.** Drop a file holding what a Jumperless prints for
  `b`, or copy it out of a terminal and paste it anywhere on the page. It is
  judged by the same checker and shown as a run of its own, class `board`,
  on both tabs, with the case panel, the missed paths and the Ceiling
  section as for any case. Press Run to go back to the battery. Details
  under "A board's own output" below.
- **ohm** is the worst signal bridge's resistance and **rail** the worst
  bridge to GND or a rail, counted in crosspoints and multiplied by the
  "ohms per crosspoint" box (42 by default, as measured on a board; duplicates in parallel lower
  it).
- **miss** counts the bridges the router failed although the free copper
  had a path for them. Select the case: each such path is drawn dashed in
  its net's colour (hollow dashed dots where crosspoints would close), and
  the bridge's row says how many crosspoints it needed. A failed bridge with
  no such path says so.
- **spare**, in the case's bridge table, is the copies the free copper still
  allows for a routed bridge and the ohms with them ("+3 → 40"). Click the
  cell to draw them dashed; click again for the missed paths.
- **Ceiling**, under the bridges, asks the exact solver whether the case's
  netlist can be routed at all, with firmware-shaped paths or with any
  copper, and can draw the solver's routing against the router's. It is
  asked on the arrangement picked. When that is not the one the run was
  routed on, the solver's routing is drawn as the picture itself and the
  panel's head says whose it is; the run and the arrangement must have the
  probe feed in the same place.

"Ceilings" below says what these three mean and what they do not.

The server listens on 127.0.0.1 only, answers only its own page (a token and
an origin check), and builds only this checkout, git refs of it, and the
`--tree` directories it was started with.

```bash
python3 tools/routing_lab/lab.py export run.html --baseline main
python3 tools/routing_lab/lab.py clean
```

`export` writes one battery run as a single HTML file that opens without the
server (table, case panel, fabric view, missed paths and spare copies; not
the KiCad backdrop, and it cannot ask the solver). `clean` deletes the caches
under `build/` (results, variant trees, binaries, solver answers), which grow
with every variant tried; the built sheet, the solver's environment and the
rankings are kept.

## A board's own output

The page shows what a board really routed from the text of its `b` report
(terminal port: the bridge array, the path table, the chip status). V5 only.

- **Getting it in.** Drop a file, or select the report in a terminal, copy,
  and paste on the page. Several files can be dropped at once; each becomes
  a case named after its file, and they stay in the table until the server
  stops. The last whole report in a text is the one used.
- **What is tolerated.** A raw serial log with the firmware's colour codes;
  a copy out of a terminal, where every tab has become spaces; whatever a
  log holds before and after the report. A path table or bridge array that
  was wrapped at the window's edge or cut short is refused with a message
  that quotes the line: read as it stands, a cut row is a shorter path, and
  the board would be shown with a fault it does not have. Widen the window
  or save a log, and try again.
- **The crossbar dump.** The chips' own view is `:crossbar` on port 7
  (`xbar{12x8:...}`). With it in the same text, or in a second file named
  alike (`x.b.txt` and `x.xbar.txt`, as `JL_ROUTING_SNAP_DIR` writes them),
  what was sent to the chips is checked against the path table. Without it,
  sent is taken to be planned, and the case's notes say that this was not
  checked.
- **What it is judged as.** A scored case: shorts, strays, a bridge listed as
  routed whose copper does not join, and claims that disagree with the
  copper are problems; a bridge the board did not route is drawn as not
  routed. Sense taps and the second-rebuild check need the harness and are
  not there.

Tested against the 21 captures of the 2026-11-21 board run, each as captured,
with colour codes, and with tabs turned to spaces. On 2026-11-22 a report
copied out of a real terminal window and pasted on the page read correctly
(10 of 10 bridges, 8 duplicates, 52 crosspoints);
`tests/fixtures/terminal_copy_2026-11-22.txt` is that report rebuilt from its
text, not the clipboard's own bytes. Another terminal may copy differently;
if a report does not read, the message says which part did not come through.

## Use from the command line

```bash
python3 tools/routing_lab/lab.py run
```

Routes the `dense` and `real` classes on this checkout's router and prints a
table. Useful forms:

```bash
python3 tools/routing_lab/lab.py run --classes dense,real,typical,fuzz,stress,beyond,edge
python3 tools/routing_lab/lab.py run --variant ~/Documents/GitHub/JumperlOS --baseline main
python3 tools/routing_lab/lab.py run --classes fuzz --case fuzz_1_1
python3 tools/routing_lab/lab.py import-state my_slot.yaml --name my_slot
```

- `--variant` is `worktree` (the checkout `lab.py` is in), a directory that
  holds `src/` (another checkout, for example your main one while the lab
  lives on a branch), or a git ref.
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

## Classes

| class | what |
|---|---|
| dense | the 21 cases of `test/hil/test_routing_dense.py` (shared through `test/hil/routing_cases.py`) |
| real | saved board states, imported with `import-state` into `cases/real/` |
| typical | 200 seeded circuits shaped like everyday use: an IC or two across the gap, power, ground, a few signals |
| fuzz | 2,000 seeded random netlists |
| stress | 21 cases each aimed at one scarce resource (one-chip floods, hub lanes, a 40-node net, maximum duplicates) |
| beyond | 3 cases over the fabric on purpose; scored, and must stay short-free |
| edge | 12 random netlists, each the longest prefix of its list that the solver proves routable with firmware-shaped paths (`cases/edge/`, grown by `lab.py edge`) |

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

## Ceilings

How far a routing is from what the copper allows. The model is the judge's:
a wire carries one net, and a node outside the net (in another net, or in no
net) may not be touched. A bridge the firmware rejected, left out or refused
is never searched for and never counts as a miss.

**miss: the path a failed bridge had.** For each bridge the router failed,
the cheapest path through copper that is free or already carries its net,
with everything else where the router put it: fewest new crosspoints, then
fewest in all. Each failed bridge is taken alone and shown its cheapest path,
so two paths may use the same free copper. That does not by itself mean only
one of those bridges could be made: there may be other paths (finding 10
below is such a case). A miss is a statement about copper, not about the
firmware's path shape: the path may be longer than the four crosspoints one
firmware path holds, or ride copper the net already has.

**spare: copies the free copper still allows.** For each routed bridge, up
to eight more paths of at most four new crosspoints each, through wires that
carry nothing and are no node's copper, sharing no wire with each other; then
the bridge's resistance with all of them closed. Each bridge is taken alone,
as if all the free copper were its own, and the firmware holds some copper
back so sense taps stay reachable. So this is "available in copper", an upper
bound, not what the firmware would give. The firmware's tap planner is not
yet asked which of them it would allow.

**The exact solver** answers what the two searches cannot: with everything
free to move, can this netlist be routed at all, and with how few
crosspoints?

```bash
python3 tools/routing_lab/lab.py solver-setup      # once; needs the network
python3 tools/routing_lab/lab.py ceiling --classes dense,real,beyond
python3 tools/routing_lab/lab.py ceiling --case nano_dense_metric --rule copper --seconds 60
```

`solver-setup` installs OR-tools 9.15 into `build/solver-venv`. Without it
everything else works, the solver's tests skip, and the page says how to get
it. An environment a failed setup left behind, with no OR-tools in it,
counts as not installed.

The netlist asked about is the case's as the firmware built it: the bridges
it allowed, its nets, and its probe feed where the firmware put it. Two
rules:

- **firmware-shaped paths**: every bridge is its own path of at most four
  crosspoints, as `pathStruct` holds one; paths of one net may share copper.
- **any copper**: the nodes a net's bridges tie together are joined by any
  tree through the copper, of any length. (Where the firmware dropped the
  bridge between two parts of one net, the parts need not be joined.)

A verdict is one of:

- **routable**, with the fewest crosspoints (`= 16`, proved) or the fewest
  found before the time ran out (`<= 18`). The lab checks the solver's
  routing with its own copper model before saying so (`ceiling.faults`: only
  offered crosspoints, no piece of copper holding two nets, every bridge
  joined, and under the firmware rule within four crosspoints). An answer
  that fails is shown as an error, not a verdict. The routing drawn is one
  of many with that count.
- **not routable**, proved. This rests on the solver and on the model, which
  the tests exercise on fabrics small enough to check on paper. If the
  solver says it of a case whose copper, as the router left it, is a routing
  the lab's own check accepts, the lab reports that the model is wrong
  instead of the verdict.
- **unknown** after the time limit (20 s by default). An answer near the
  limit is not the same from run to run; nothing committed rests on one.

What a verdict does not say. The model does not hold the copper the firmware
reserves for sense taps, nor its duplicates: "routable" is a ceiling for any
router that keeps the rule's path shape, not a promise that this router's
method could reach it. And fewer crosspoints is not better by itself: the
fewest shares as much copper inside a net as it can.

**Edge cases** (`lab.py edge --seed 1 --count 12`, about two minutes a case)
are where the router and the ceiling are compared. A random legal list of 80
bridges is drawn as `fuzz` draws its ends, and bisection finds the longest
prefix the solver proves routable with firmware-shaped paths. A prefix of
which the firmware itself drops a bridge is never asked about. Each case is
saved with the routing that proves it (`cases/edge/proof/`), and a test
checks every one of those routings against the harness's netlist with no
solver, so "provably routable" does not depend on the solver being installed
or on its luck with the clock. If the solver fails while a case is grown,
the command stops with exit 1 and writes nothing for that case. A proof
routes the probe feed too, from where today's firmware puts it: a firmware
change that moves the feed fails that test although the case's own bridges
still fit, and the cases are then grown again.

How near the true edge a case sits depends on why it stopped. Where the next
bridge is proved not to fit, it is at the edge of its list, save that
bisection assumes a longer prefix never fits where a shorter one does not.
Where the next bridge is only "not known" after the time limit, the true
edge may be several bridges further on: the case is the longest the solver
could prove, not the longest that fits. `lab.py run --classes edge` is the
headline score: how many of these the router routes in full.

`lab.py ceiling --classes edge` can answer "unknown" for an edge case (two
of the twelve, on 2026-11-21). It looks for the fewest crosspoints inside
its limit, which is a harder search than the one that grew the case, and
these cases sit at what the solver can do in 20 s. The saved proof is what
stands.

The headline on 2026-11-21, router at 5374d38: **1 of 12**. The twelve cases
hold 49 to 60 bridges each; for five the next bridge is proved not to fit,
for seven it is not known after 20 s. Of their 655 primaries (each case's
probe feed is one) the router routes 603. "Findings so far" has the detail.

## Arrangements

An arrangement is the crossbar copper: which wire is on each chip pin, and
which node is which wire. V5's is `test/hil/fabric_v5.py`. Any other is a
small JSON file under `arrangements/` that says what it changes from V5:

| key | what it says |
|---|---|
| `"about"` | one line of text |
| `"base"` | `"v5"`, the only base there is |
| `"feed"` | `false` when the probe feed is not routed through the fabric (V6 takes it off); `true` when not given, and then every end the feed can have must keep a pin: BUF_IN, DAC0 and GPIO_1 to GPIO_8 |
| `"remove"` | wire names: every pin on such a wire is taken away |
| `"pins"` | `{"A.X7": "TOP_RAIL", "K.X2": null}`: a pin put on a wire (and so joined to every other pin of that name), or taken away |
| `"chips"` | `{"M": {"role": "sf", "x": [16 names or null], "y": [8 names or null]}}`: a chip added; role `"bb"` or `"sf"` |
| `"nodes"` | `{"150": {"wire": "PORT_0", "name": "PORT_0"}, "139": null}`: a node added or moved, or removed |

A pin taken away is no copper at all: nothing routes over it and no search
passes it. A node whose last pin is taken away drops out, and a netlist that
uses it "cannot be placed" there, which is neither routable nor not.

Mistakes `check` lists besides the obvious ones, all at once: a key given
twice in one object (JSON would keep only the last); a pin written another
way than `A.X7` (no `A.X07`); a key a chip or a node does not have; a name
with spaces at its ends; and a new wire name on a single X pin with no node
on it, under `"pins"` or in a new chip's own list, which is nearly always a
misspelt name (`TOP_RIAL`). A spare pin left as a no-connect is named as V5
names one, `unconnected-...` (as V5's bounce rows are), and is no slip. A
one-pin wire on a Y pin is a bounce row, a shape V5 has eight of, so it is
taken for a slip only when it is a near copy of a name V5 has. A misspelling
repeated on two pins or more is not caught, nor is one unlike any name (`3O`
for `30`).

Two ship. `v6_feed_off` is V5's copper with the probe feed off the fabric.
`v6_rails_on_chips` is the worked example, P1 + P2 of
`CodeDocs/V6_CROSSBAR_MATRIX.md`: the feed off, and on every breadboard chip
the second lane of three doubled pairs given to TOP_RAIL, BOTTOM_RAIL and
GND. Its file is the feed line and 24 pins:

```json
{"about": "...", "base": "v5", "feed": false,
 "pins": {"A.X7": "TOP_RAIL", "A.X11": "BOTTOM_RAIL", "A.X15": "GND", "B.X5": "TOP_RAIL", "...": "..."}}
```

```bash
python3 tools/routing_lab/lab.py arrangement list                       # each one: feed, who can answer for it
python3 tools/routing_lab/lab.py arrangement show v6_rails_on_chips     # pin by pin; changed pins starred
python3 tools/routing_lab/lab.py arrangement check my_idea.json         # every mistake, each with its pin or name
python3 tools/routing_lab/lab.py arrangement score v6_rails_on_chips    # the solver, against V5, on the same netlists
```

To try an idea: write the file, `check` it, pick it on the page. A file with
a mistake is listed greyed with its problems; nothing runs on it, and
nothing else stops.

**Who can answer for it.** The firmware's router can route an arrangement
only when that is V5 with pins taken away (`"remove"`, or pins set to
`null`): the harness blocks those pins and the real router routes around
them. `lab.py run --arrangement`, the page's Run and the ranking do that.
Any arrangement that moves a pin, adds a chip or adds a node is the solver's
alone, because the router has V5's chips and pins as literals in its code.
So is one that takes away one pin of a node that keeps another (GND has a
pin on K and one on L): the firmware still has the node there and closes the
pin, blocked or not. With the feed on the fabric, the file must keep every
end the feed can have: BUF_IN, and DAC0, or, when DAC0 is not free for it (a
bridge on DAC0, DAC0 out of the probe's window as in the dense cases, or the
probe's power set to come from a GPIO first), the highest free GPIO from 8
down to 1. (The harness keeps the top OLED on, so it never feeds from GPIO 7
or 8; a board with the OLED off can, and the rule keeps them.)
Should the router still close a crosspoint on a blocked pin, that case fails
and says which.

**`arrangement score NAME [--against v5]`** asks the solver the same netlists
on both. The netlists are the firmware's own: each case is run once by the
harness on V5's copper with NAME's feed, for the bridges the firmware allows
and the nets it makes of them, and then both arrangements are asked. It
prints both verdicts and both fewest-crosspoint counts for every case, then
what fits on only one, and the crosspoints each needs over the cases proved
on both. `--grow N` also grows N of the edge class's random lists on each
(the longest prefix proved routable; about a minute and a half a list an
arrangement). On the page, pick the arrangement, open a case of a run with
the same feed, and ask under "ceiling": the solver's routing is drawn as the
picture, and the case panel says whose routing it is.

**What the solver's answer is worth for V6.** It says a routing exists on
that copper with each bridge on its own path of at most four crosspoints, or
proves there is none. A V6 router may find less than that, and one with
longer paths or other rules may find more. It knows nothing of sense taps,
of what the firmware reserves, or of resistance beyond counting crosspoints.
So read a score as: this copper can carry these netlists, and for this many
crosspoints at best.

## The lane ranking

Which wires could a board do without? The wires ranked are the ones that are
only copper between chips: the 48 lanes between breadboard chips, the 32
lanes from a breadboard chip to an SF chip, the 8 bounce rows and the 6 hub
lanes. That is 94 on V5. A node's own wire is not ranked.

```bash
python3 tools/routing_lab/lab.py rank                    # the router's part, about three minutes
python3 tools/routing_lab/lab.py rank --needed           # and the solver's; see below for how long
python3 tools/routing_lab/lab.py rank --wires KL,AK --classes dense
```

It routes the battery on the arrangement (`v6_feed_off` unless
`--arrangement` says otherwise: V6 takes the probe feed off the fabric),
then again without each wire in turn, and prints one line a wire. The
ranking is kept under `build/rank/`, one file a router and arrangement. A
ranking of some wires (`--wires`) or of one case (`--case`) is printed and
not kept, so it cannot take the place of the whole one; `--json FILE` writes
it.

There are two answers, and they are different questions:

- **loss**: what the firmware's router loses without the wire, in primaries
  routed and in cases fully routed. **It is signed.** With a wire gone the
  router sometimes routes more, because its search takes another turn, and
  that is printed as a negative loss, not as zero. A loss is about this
  router. It is not the answer to "is the wire needed".
- **needed by / not needed / unknown** (`--needed`): for every netlist the
  solver is asked whether it can be routed without the wire at all. "Needed"
  is said only on a proof that it cannot. "Not needed" is said only on a
  routing that does without it. Anything else, a solver out of time
  included, is "unknown" and counts as neither.

**Usage is no guide.** The table has how many cases use each wire, because
people ask, but it follows the router's search order. With the feed off the
least used wire, IJ, is in 10 of 256 cases and costs the router nine
primaries.

**One wire at a time.** Every line is about taking that one wire away. Two
wires that are each not needed may be needed together. To ask about a set,
take them all away and run: on the page's Ranking tab, click the wires (in
the drawing or the table), then "Run without these". The run is on the
arrangement "NAME without A, B"; the text of a file for it is shown under
the Arrangement picker, to save under `arrangements/` if it is worth
keeping, and then `arrangement score` can ask the solver about it.

`--needed` asks only where it has to (a wire no known routing of the case
touches is settled without a question), about a second a question. Over its
default classes (dense, real, typical and stress, 244 netlists) it took 40
minutes on top of the router's three; with `--needed-classes
dense,real,stress` (44 netlists), six. Run nothing else heavy beside it: an
answer that runs out of its 5 s is "unknown". A ranking made again without
`--needed` keeps what the solver proved before, as long as the arrangement's
copper is what it was. The solver's work is never thrown away: whenever a
file holding it would be written over (the copper changed, or a new
`--needed` over other classes), the old file is first copied aside beside it
as `<name>.set-aside.json` (then `-2`, `-3`: one never replaces another), and
the command and the Ranking tab say so. The tab also says when a ranking is
of copper the arrangement's file no longer has.

**The Ranking tab** shows the file for the Router named and the arrangement
picked: the fabric tinted by the router's loss or by how many netlists need
each wire (dim through teal to yellow; a wire the router routes more without
is blue; nothing there is red), and the table, sorted by a click on a
heading. "Rank now" makes the router's part from the
page, with its progress; the solver's part is started from the command line.

## Checked against a board

On 2026-11-21 a V5 was flashed with this tree's firmware (commit 0621e4f,
whose `src/` is main's 5374d38) and ran the HIL dense suite with captures on
(`fidelity/board_0621e4f44e23/`; the suite passed, 78 checks). The harness
routes all 21 cases as the board did: every path row, every chip-status
claim, every closed crosspoint.

The first comparison failed, on one thing. A board that has booted has run
`oled.init()` (`top_oled.connect_on_boot` defaults to 1), and that sets
`top_oled.enabled` in RAM whether or not a panel answers, while
`config.txt` can still say 0. From then on the probe feed's GPIO scan skips
the OLED's GPIO 7 and 8, so with DAC0 outside the probe window the feed sits
on GPIO 6. The harness had booted with the OLED off and put it on GPIO 8.
It now boots as the board does. No routed count and no finding below
changed with it.

A second, smaller check came from a report pasted on 2026-11-22 (ten bridges
made by hand, eight duplicates). Routing the same bridges, the lab closes the
same crosspoints as that board in 51 of 52 places. The one that differs is
the probe feed's end: GPIO 8 on that board, GPIO 6 in the lab. So that board
had the top OLED off when it routed, and the harness always assumes it on.
Where a board's feed sits on GPIO 7 or 8, expect that one difference.

The pass is recorded for the harness as it is (`verified.json` holds its
hash). Change anything under `harness/` and `lab.py run` says "not verified
against a board" again until `lab.py fidelity <capture>` is re-run, which
needs no board while the capture's commit still describes the router.
`fidelity/README.md` has the bench procedure for a new capture.

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

## Findings so far (router at 5374d38, from the host harness)

Full battery, 2,259 cases: no short, stray, crash or hang. Every primary of
every `typical`, `fuzz` and `stress` case routes, and outside the `edge`
class no failed bridge had a free path left in the copper (`missed` is 0).

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

From the ceilings (2026-11-21; see "Ceilings" for what each number is worth):

5. **On long random netlists the router stops well short of what fits.**
   The twelve `edge` cases (49 to 60 bridges) are each proved routable with
   firmware-shaped paths, by a routing saved beside the case. The router
   routes one of them in full and leaves 52 bridges unrouted across the
   other eleven (603 of 655 primaries). At the `fuzz` class's sizes, up to
   twelve bridges, it routes everything. See one: `lab.py run --classes edge
   --case edge_1_1`, or the page with the `edge` class ticked.
6. **Most of those 52 need other bridges' paths moved, not a better last
   search.** With everything else where the router put it (other paths and
   their duplicate copies), 12 of the 52 still had a path through free or
   same-net copper, and only 2 of those 12 are within the four crosspoints
   one firmware path holds. Copies are not what is in the way: routed with
   no stacking, so with no copy in the copper, 49 bridges fail and 15 of
   them have such a path, 4 within four crosspoints. One bridge
   (`GPIO_7`-`D11` in `edge_1_3`) needs no new crosspoint at all: its two
   nodes are already joined through the net's other bridges, eight
   crosspoints apart, and the path table still lists it as not routed.
7. **Stacking can cost primaries.** `edge_1_5` routes 55 of 61 primaries
   with the default stacking and 58 of 61 with none. The other eleven edge
   cases route the same number either way.
8. **On the dense and real cases the router is at the ceiling for routing,
   not for crosspoints.** `lab.py ceiling --classes dense,real`: 22 of the 23
   are provably routable with firmware-shaped paths and the router routes
   all 22; the 23rd is `k_rows_overflow_metric`, below. Over the 19 of them
   whose fewest is proved, its primary paths use 31 crosspoints more than
   the fewest (`corner_rows` 20 against 16, `slot3_snapshot_2026-08-26` 30
   against 25). Fewer is not better by itself.
9. **Three netlists are proved too big for the fabric as a whole; one
   "beyond" case is not beyond.** `k_rows_overflow_metric` (with its probe
   feed on GPIO 6, as the firmware builds it), `every_nano_pin` and
   `nine_k_nets` are proved not routable under both rules. That is about
   each netlist as a whole. For `k_rows_overflow_metric` it makes the
   router's 12 of 13 the most there can be. For the other two it does not
   say the router's 16 of 23 or 8 of 10 is the most that fits; that was not
   asked. `max_bridges_random` (64 bridges; the router routes 61 of the 63
   the firmware allowed) can be routed: with any copper in 94 crosspoints
   or fewer, and with firmware-shaped paths in 117 or fewer. The solver
   found the firmware-shaped routing in one 20 s run and not in another, so
   `lab.py ceiling` may still print "unknown" for it.
10. **The September router, for comparison** (`--variant "a1accf5^"`,
    before the hub rescue tier): five misses in the dense class. Two are the
    `nano_dense_metric` bridges that tier was written for (`A4`-`19`,
    `A5`-`20`, four crosspoints each). Three are in `h2_through_sf_chips`
    (`16`-`46`, `17`-`47`, `18`-`48`). The cheapest path of each crosses
    chip I by the same pin, but all three could have been made at once, four
    crosspoints each, one through each of the chips I, J and K.

For V6 (2026-11-22, router at 5374d38; each says its arrangement, its engine
and where the probe feed is):

11. **The probe feed costs the router one case, and the copper some room.**
    The firmware's router, V5's copper, 256 cases of dense, real, typical,
    stress and edge: 244 fully routed with the feed on the fabric, 245 with
    it off (`v6_feed_off`); the one is `k_rows_overflow_metric`, which is
    proved not routable with the feed and routes without it. The exact
    solver on V5's copper, growing the edge class's first two random lists:
    the first reaches 54 bridges with the feed (`edge_1_0`) and 54 without,
    the 55th proved not to fit either way; the second reaches 54 with the
    feed (`edge_1_1`, the 55th proved not to fit) and 62 without (the 63rd
    not known in 20 s).
12. **Rails and GND on every breadboard chip save crosspoints and lose no
    netlist.** The exact solver, firmware-shaped paths, feed off,
    `v6_rails_on_chips` against V5's copper, the 44 netlists of dense, real
    and stress (`lab.py arrangement score v6_rails_on_chips --grow 2`): all
    44 are routable on both; over the 38 whose fewest is proved on both, 861
    crosspoints against 955 (`rail_stacking_light` 6 against 10,
    `k_rows_overflow_metric` 18 against 26, `gnd_spread` 8 against at most
    16). The twelve lanes given up cost nothing here. Two random lists grown
    on each: 54 bridges on both for the first (the 55th proved not to fit on
    either), 65 against 62 for the second (the next not known in 20 s on
    either).
13. **The router is not monotone in the copper.** The firmware's router,
    `v6_feed_off`, 256 cases, one wire taken away at a time (`lab.py rank`):
    it routes more primaries without 13 of the 94 wires, the same without
    24, fewer without 57. Without `/DG0` it routes four more. So a loss, and
    a gain, is this router's search taking another turn.
14. **For this router the lanes between breadboard chips are nearly free,
    one at a time, and the lanes to the SF chips are not.** Same run.
    Primaries lost, summed over taking one wire away at a time: the 48 lanes
    between breadboard chips -1 in all (each between -4 and +4); the 32
    lanes to SF chips +151; the 8 bounce rows +22; the 6 hub lanes +32. The
    most costly: `CI` +10, `IJ` +9, then six at +8 (`BI`, `BL`, `CL`, `FJ`,
    `HI`, `JL`).
15. **Hardly any single wire is needed by the copper.** The exact solver,
    firmware-shaped paths, 5 s a question, `v6_feed_off`, the 244 netlists
    of dense, real, typical and stress, one wire taken away at a time
    (`lab.py rank --needed`, 43 minutes): 86 of the 94 wires are needed by
    no netlist, each of the 244 having a routing without the wire. The eight
    lanes into K (`AK` to `HK`) are each proved needed by one netlist,
    `k_rows_overflow_metric`, which puts twelve rows on K. No answer was
    left unknown. (A first run, over the 44 netlists of dense, real and
    stress, left one: `max_duplicates` without `AK`. Answers near the limit
    vary from run to run.) `IJ`, the hub lane the router loses nine
    primaries without, is needed by none: the netlists the router loses
    there have routings that do without it.
16. **With the feed off the router leaves one more unclaimed pin.** The
    firmware's router, `v6_feed_off`: `stress/six_hub_lanes` closes chip D's
    x7 for net 6 while the chip status shows it free (the kind finding 2
    describes; `edge_1_8` shows one on V5 as built). See it: `lab.py run
    --arrangement v6_feed_off --classes stress --case six_hub_lanes`.

What 13 to 15 say together: a wire's loss in the router's column is about
the router, and most of it would come back with a router that searched
differently. What the copper needs, one wire at a time, is the lanes into K
when K is full. Which sets of wires can go together is not answered by
either column: take a set away and run it, or score it.

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
python3 -m unittest discover -s tools/routing_lab/tests -t tools/routing_lab
```
