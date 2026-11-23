# Handoff 2026-11-22: routing lab, phase 5 (V6 arrangement choices)

Kevin picked the next phase on 2026-11-22, after plan 4 was merged, from four
choices put to him. He chose **"V6 arrangement choices"**, which was offered
as: "Lab only, no src/ edits. Score the V6 doc's proposals and sets of wires
taken away together. Today the lab only says what single wires cost, not
which sets V6 can give up."

Nothing of phase 5 exists: no design text, no plan, no code. This doc is
what a new chat needs to write the phase's design and plan cold. It was
written by the chat that built plan 4. Line numbers are for commit 263225a.

## What the next chat produces

1. **A design for phase 5**, approved by Kevin before any plan. Every piece
   so far is a section of `CodeDocs/DESIGN_ROUTING_LAB.md`. There is no
   precedent for a fifth: its status line says "All four pieces are built",
   its goals stop at G6, and "Build order" says four plans. A fifth piece
   amends all three. Whether Kevin wants that or a new design doc is his call.
2. **`CodeDocs/PLAN_ROUTING_LAB_5_<NAME>.md`**, once the design is approved.
   Kevin approved the design once (2026-11-17). Plans 1 and 2 followed it
   without a separate ask; for plans 3 and 4 he said "Write plan 3" and "Write
   plan 4". Before each build he chose how it is built ("Build it here" for
   plan 4: inline in one chat).

## Before touching anything

- **The main checkout is not yours.** `~/Documents/GitHub/JumperlOS` is on
  `main` (263225a, or a later commit adding only this doc) and holds
  someone else's uncommitted firmware work under `src/`, `scripts/`, `lib/`,
  `modules/`, `data/` and `test/`, plus `.github/workflows/release.yml`
  modified and `.pio/build/jumperless_v5/firmware.uf2` deleted. Never edit,
  stage, commit, stash or check out over any of it.
- **This doc may not be on `main` yet.** If your worktree lacks it, it is
  untracked at `~/Documents/GitHub/JumperlOS/CodeDocs/HANDOFF_2026-11-22_ROUTING_LAB_5.md`.
  Copy it into your worktree; do not move it.
- **Work in a new worktree off `main`.** In the main checkout the lab's
  default variant (`--variant worktree`) is that uncommitted `src/` (variant
  hash `fa617e94…`), not the router every finding is about. A clean worktree
  off `main` hashes to `9524e1cf…` while its `src/` and the lab's `harness/`
  are as at 263225a: the router behind the findings (`git diff 5374d38
  263225a -- src` is empty). The test suite also resolves
  `worktree` and writes into `build/`, so in the main checkout it would build
  and test the uncommitted `src/`.
- **A lab server may still run on port 8765**, started from the main
  checkout by the plan-4 chat. It serves the uncommitted `src/` as "worktree"
  and has no ranking. Start your own on another port.
- **The plan-4 worktree is kept for its `build/` only.**
  `.claude/worktrees/routing-lab-4`, branch `routing-lab-plan-4` at 263225a,
  already merged. Ask Kevin before removing it.

## Read in this order

1. This doc.
2. `CodeDocs/V6_CROSSBAR_MATRIX.md` (280 lines): the chokepoints (section 2),
   the proposals (P1 to P5 in section 3, A1 to A4 in section 4, R1 to R5 in
   section 5, the expansion port in section 6) and what the firmware's router
   would need to route a changed fabric (section 7). Its second paragraph,
   added 2026-11-22, sums up findings 12, 14 and 15 and points to the README
   for 11 to 16; the rest dates from 2026-09-03.
3. `tools/routing_lab/README.md`: "Arrangements" (line 382), "The lane
   ranking" (473), "What it does not check" (571), "Findings so far" (612;
   the V6 ones, 11 to 16, from 687).
4. `CodeDocs/DESIGN_ROUTING_LAB.md`: "Piece 4" and "Piece 4 as built" (273 to
   359), "Learned building piece 1" (403).
5. `CodeDocs/PLAN_ROUTING_LAB_4_ARRANGEMENTS.md`: the model for the plan's
   form, and its "Not in this plan" and "After this plan" (717 to 728).
6. Code, in `tools/routing_lab/`: `arrangement.py`, `rank.py`, `score.py`,
   then `ceiling.py` (`graph`, `problem`, `ask`, `verdict`), `runner.py`
   (`taken_pins`, `run_battery`) and `lab.py` (`cmd_arrangement`,
   `cmd_score`, `cmd_rank`).

## What Kevin has said that binds this phase

- 2026-11-17, his first message about the lab: "And I'm also designing V6 so
  let's rank paths that are rarely used so we can use them for other things".
  The design made this its third aim, "Learn which lanes V6 can give up for
  other uses", and ranks by need rather than by how rarely the router uses a
  wire, because usage follows the router's search order. He has not said
  what the freed pins are for.
- 2026-11-22: "we should make it easy to change the crossbar arrangement for
  working on V6, and no the probe won't go throught the crossbars". So V6
  has the probe feed off the fabric: the V6 arrangements say
  `"feed": false`, and `rank` defaults to `v6_feed_off`.
- 2026-11-22: "live ohms per crosspoint is 42". The page's ohms box defaults
  to 42.
- 2026-11-22: "we should also be allowed to click nodes to make connections
  in the visualizer and route them on whatever we're looking at". Built
  (plan 4, Task 10).
- 2026-11-22: he picked "V6 arrangement choices" for phase 5, the option the
  plan-4 chat marked as its recommendation; the words quoted at the top are
  that chat's, not his. He did not pick a V5 router pass (fixing findings 1,
  2, 5 to 7 and 16, which edits `src/`), a router that reads any
  arrangement from the board descriptor (V6 doc section 7, also `src/`), or
  leaving the phase open.
- From the design (2026-11-17), still binding: usage data, such as how often
  people use a special node, is out of scope; a routing battery cannot
  supply it.

## Where things stand

- **`main` at 263225a holds all four pieces.** Plan 4 is the 16 commits from
  64bca37 to 263225a after the plan's own commit (6b018cf), merged by fast
  forward on 2026-11-22. Nothing is pushed. A later commit that adds only
  this doc changes nothing below.
- **Tests:** `python3 -m unittest discover -s tools/routing_lab/tests -t
  tools/routing_lab`, 349 tests, passed on 2026-11-22 in 45 s with the
  solver installed (24 skip without it).
- **What was measured is kept only in the plan-4 worktree**, under
  `.claude/worktrees/routing-lab-4/tools/routing_lab/build/rank/`:
  - `9524e1cf…_v6_feed_off.json`: the firmware's router and the exact solver,
    on `v6_feed_off`. The router's part covers 256 cases of dense, real,
    typical, stress and edge (baseline 2,987 primaries, 245 fully routed,
    13,293 crosspoints). The solver's "needed" covers 244 netlists (firmware
    rule, 5 s a question). Findings 13 to 15 come from it.
  - `9524e1cf…_v5.json`: the router only, on the 21 dense cases. It is not a
    full V5 ranking.
  - Both predate the ranking file's `"fabric"` digest, so `rank.same_copper`
    matches them by its older rule: same feed, V5's nodes, the same wires on
    the same pins.
  - To use them in a new worktree off `main`, copy both files with `cp -p`
    into its `tools/routing_lab/build/rank/`. A file is named `<variant
    hash>_<arrangement>.json`, and the hash is the same there. (Inferred from
    `rank.path` and the variant hash; not tried.) The page dates a ranking by
    its file's time, so a plain `cp` shows the day of the copy.
  - The same worktree's `build/ceiling/` (243 files, about 1 MB) holds the
    exact solver's cached answers, finding 12's score among them. Each is
    named by the question and the bytes of `solver/solve.py`, so copying the
    folder saves asking again while `solve.py` is unchanged. It does not
    replace `solver-setup`.
- **`build/` is per checkout and ignored by git.** A new worktree needs
  `python3 tools/routing_lab/lab.py solver-setup` before any solver command
  (OR-tools 9.15.6755 into `build/solver-venv`; needs the network once).
  Without it, `ceiling`, `arrangement score` and `rank --needed` print the
  setup hint and exit 1.

## What the lab does today

### An arrangement file

`tools/routing_lab/arrangements/<name>.json` is V5 plus what differs
(`arrangement.py`). Any key not listed here is an error:

| Key | What it does |
|---|---|
| `about` | Text. |
| `base` | Must be `"v5"`. |
| `feed` | `true` (default) or `false`: the probe feed on the fabric or off it. |
| `remove` | V5 wire names. Every pin of each becomes no copper. |
| `pins` | `{"A.X7": "TOP_RAIL"}` puts a pin on a wire (joined to every pin of that name); `{"A.X7": null}` takes it away. |
| `chips` | `{"M": {"role": "bb" or "sf", "x": [16 names or null], "y": [8 names or null]}}`. A new capital letter. Every chip is 16 X by 8 Y. |
| `nodes` | `{"150": {"wire": NAME, "name": TEXT}}` adds or moves a node; `{"139": null}` removes it. |

Rules (all problems are listed at once, and nothing runs on a bad file):

- A pin is `([A-Z])\.([XY])(0|[1-9][0-9]?)`, X 0 to 15, Y 0 to 7.
- A V5 wire of two or more pins that is no node's and is left on exactly one
  pin is an error, so lanes are given up in pairs (both ends) or the other
  end is given a new wire. GND, the one node's wire on two pins, is exempt:
  left on one of K.X15 and L.X15 it passes and makes the file solver only.
- A new one-pin wire with no node is an error on an X pin unless it is named
  `unconnected-…`. On a Y pin it is a bounce row unless its name is a near
  copy of a named V5 wire (difflib ratio at or above 0.81). Spaces at a
  name's ends are an error on every wire.
- With `"feed": true`, BUF_IN (node 139), DAC0 (106) and GPIO_1 to GPIO_8
  (131 to 138) must each keep a pin.
- A node whose wire is left on no pin is dropped. A case that uses it is
  "unplaced": neither routable nor not.

### Who can answer

- **The firmware's router** runs an arrangement only when it is V5 with pins
  taken away. It is refused, with the reason (`why_not_router`), for an added
  chip, a pin given a wire, one pin taken from a node that keeps another
  (GND is on K.X15 and L.X15), or a node added, moved or removed with `null`.
  A run in which the router closes a crosspoint on a taken pin fails.
- **The exact solver** takes any arrangement. The `firmware` rule is each
  bridge its own path of at most four crosspoints (`MAX_HOPS = 4`,
  `solver/solve.py:27`); the `copper` rule is any tree. Its "routable" is a
  ceiling for a router that keeps that path shape, not what a V6 router would
  do. It knows nothing of resistance, sense taps or the firmware's
  reservations.
- **Netlists always come from the firmware's harness**, which knows only
  V5's nodes. A node new to an arrangement never appears in any netlist; a
  V5 node moved to another wire does.

Shipped arrangements:

- `v6_feed_off`: the feed off, nothing else. Router and solver.
- `v6_rails_on_chips`: the feed off, and on each of A to H three second
  lanes given to TOP_RAIL, BOTTOM_RAIL and GND (24 pins). The 12 lanes it
  gives up: `/AD1 /AF1 /AH1 /BC1 /BE1 /BG1 /CD1 /CH1 /DG1 /EF1 /EH1 /FG1`.
  Solver only.

### Commands

| Command | Does | Keeps |
|---|---|---|
| `lab.py arrangement list` | Each arrangement, its feed, "router and solver" or "solver only" | nothing |
| `lab.py arrangement show NAME` | The pin tables with changes starred, nodes changed, which engine | nothing |
| `lab.py arrangement check NAME` | `NAME: good`, or every problem (exit 1) | nothing |
| `lab.py arrangement score NAME [--against v5] [--classes dense,real,stress] [--rule firmware] [--seconds S] [--grow N]` | The solver on NAME and on `--against`, both with NAME's feed, asked the netlists the harness makes on V5's copper with that feed: verdicts, "fits only on", fewest crosspoints over the cases proved on both, unknowns, and with `--grow` how far random lists grow on each. `--seconds` defaults to 10 s a case and 20 s a grow probe. | nothing (no `--json`); solver answers cached in `build/ceiling/` |
| `lab.py ceiling --arrangement NAME` | The solver's verdicts on the arrangement (20 s a case) | `build/ceiling/` |
| `lab.py run --arrangement NAME or file.json` | The router's battery table on the arrangement | `build/results/` |
| `lab.py rank [--arrangement v6_feed_off] [--classes dense,real,typical,stress,edge] [--wires A,B] [--case C] [--json FILE]` | One wire taken away at a time, the router's signed loss | `build/rank/<hash>_<name>.json`, unless `--wires` or `--case` |
| `lab.py rank --needed [--needed-classes dense,real,typical,stress] [--seconds 5]` | Adds the solver's "needed by / not needed / unknown" for each wire | the same file; earlier solver columns are set aside, never overwritten |

`rank --wires A,B` ranks each listed wire alone; it is not a set.

### Sets of wires today

- **On the page:** on the Ranking tab, click wires, then "Run without these".
  The router routes the battery on the reduced copper, and the page shows
  the arrangement's JSON to copy. The run lives in the server's memory only.
  The button needs a ranking loaded and copper the router can run.
- **From the command line:** write a file with `"base": "v5", "feed": false,
  "remove": [...]`, then `lab.py run --arrangement x.json` (the router's
  table, compared with nothing) and `lab.py arrangement score x.json
  --against v6_feed_off` (the solver on both). Leave `feed` out and it is on
  (the default): `run` routes with the feed, and `score` asks `v6_feed_off`
  with the feed on too, which is V5's copper. Only the header's "probe feed
  on" shows it. The page's JSON already says `"feed": false`.
- **Functions that already take a set:** `rank.without(a, *names)`
  (`rank.py:54`) builds the smaller arrangement, and
  `rank.need(given, kept, wire_pins)` (`rank.py:160`) takes any pins, so the
  union of a set's pins works as it is. `need` settles a netlist without
  asking when a known routing avoids those pins, and `rank.needed` reuses
  every routing it finds for the wires after, within one run (nothing of
  that is saved).

### Not computed anywhere (the gap this phase fills)

1. **"Needed together"**: a solver proof that the netlists can, or cannot, do
   without a whole set. Only one wire at a time is asked.
2. **A combined router loss** for a set against the full arrangement. The
   design planned it (DESIGN line 314); "Piece 4 as built" says it was not
   built (line 346).
3. **Any ranking of copper only the solver can route.** `rank.removal` and
   `rank.needed` both route the battery with the firmware first
   (`rank.py:131`, `:198`), which raises `RouterCannot` (exit 2). So
   `v6_rails_on_chips`, and every proposal that moves a pin, cannot be ranked.
4. **A kept score.** `arrangement score` prints and saves nothing, and no
   server endpoint calls `score.compare`.
5. **The V6 numbers beside each proposal** in `V6_CROSSBAR_MATRIX.md`. Plan 4's
   "After this plan" asked for them; only the V6 doc's second paragraph sums
   some of them up.

## The V6 proposals against the lab

"Solver only" means the format can write it and only the exact solver can
answer. The format checks for A1, A2, A4 (as a second chip), P3 to P5, R1,
R4 and the port were run in memory by readers for this doc; none was scored.

| V6 doc item | What changes | As a file today | What the lab cannot say |
|---|---|---|---|
| P1 rails and GND on every breadboard chip (section 3) | 3 X pins per chip become TOP_RAIL, BOTTOM_RAIL, GND, from 3 of its 5 doubled lanes | `v6_rails_on_chips` is one choice of the 12 lanes. Solver only. The 12 lanes alone, as `remove`, are router and solver | A second crosspoint per row ("halves the per-row resistance"): the solver's routing has the fewest crosspoints and no copies, though `ceiling.solved` gives its bridges' ohms on the page. The router on the moved pins. Any ranking |
| P2 probe feed off the fabric | Frees a K row, an L row and KL | `v6_feed_off`. Router and solver | A board with the feed off |
| P3 rows 29, 30, 59, 60 off K and L | (a) accept 56 rows; (b) the rows onto two chips' Y0; (c) a ninth breadboard chip; (d) "pair them" | (a) pins taken away: router and solver, and cases using those rows are "unplaced". (b) one row per Y0: solver only. (c) a `role: "bb"` chip: solver only | See "Doc errors" for (b), (c) and (d) |
| P4 ADC0 to 3 on L as well as K | Needs four free L pins | Three are freed (L.X0, L.X1, L.X3); three ADCs there: solver only | Sense taps, which are the point of it; the doc's fourth pin |
| P5 a second lane for the 8 single-lane pairs (AE AG BF BH CE CG DF DH) | No breadboard X pin is free, so it trades a lane | For example `"remove": ["/AD1", "/EH1"]` and `/AE1` on A.X7 and E.X15 (D.X1 and H.X9 can become `/DH1`, another single pair's second lane): solver only | Finding 15: no netlist needs any single lane alone. Without each one the router loses between -2 and +4 primaries, +8 for the eight (plan-4 ranking); finding 14's -1 is for all 48 lanes between breadboard chips |
| A1 chip M as a mirror of K (section 4) | A new SF chip; one new X pin per breadboard chip; M's X carries the rails, GND, DAC0, DAC1, ADC0 to 3 | A `chips` entry with role `sf` passes the check. Solver only. Never scored | What M's other 7 X pins carry; the router's choice between K and M |
| A2 chip N as a bounce hub | Lanes from each breadboard chip to N's X; N's Y no-connect | Role `bb` with Y named `unconnected-…` passes. Solver only. Never scored | Any ranking (N is solver only). The role decides what `rank.wires` lists: as `bb`, N's lanes are "lane" and its Y rows "bounce", mixed in with V5's; as `sf`, neither |
| A3 A1 and A2 together | Fourteen chips; 3 of each breadboard chip's 5 second lanes | Solver only | The doc's reason for it holds only in part (see "Doc errors") |
| A4 a 16x16 or 8x32 part for K and L | A bigger chip | Not as one chip (every chip is 16 X by 8 Y). A second `sf` chip whose 16 X pins carry K's 16 X wires is the same switch matrix as a 16x16 K and passes the check. Solver only. Never scored. 8x32 is not modelled | More rows on the same lanes add no copper; only new lanes do. The hub wires KL, IK and JK would then have 3 pins, a shape the rank does not classify |
| R1 low-ohm power taps | A mux from rows 1, 8, 15, 22, 31, 38, 45, 52 to the rails, outside the crossbar | Roughly, as an SF chip: solver only | A switch with its own ohms; a mux closing one channel at a time. The lab would score R1 worse than P1 on the one thing it improves |
| R2 P1 for analog circuits | As P1 | As P1 | An audio or op-amp class (`typical` is the nearest) |
| R4 placing pins by use; a port for the Nano header | Moves UART or GPIO pins; new port nodes | Moving V5 nodes: solver only | Netlists that use new nodes |
| R5 a sense chip | An SF chip with ADC0 to 3 and 12 hub lanes on X, and 8 rows wired to A to H (one X pin per breadboard chip, as A1) | The format can write it, but all X pins of I to L are in use, and the doc does not say where the 12 come from. Its lanes from A to H come out of the pin budget below | Sense taps |
| Section 6 the expansion port | 16 port lines on today's nano pins of I and J; the freed nano pins become second hub lanes | The port lines are V5's nano nodes where they are, so netlists already use them. Taking the dropped nano pins away works with both engines; giving them a second hub lane (for example `IJ2` on I.X0 and J.X0, which drops A0 and D0) is solver only. A new node is needed only for a line not on a nano pin | Which 6 nano pins go (the V6 doc does not say); cases that use them become unplaced |
| Section 7 the router's descriptor queries | A router refactor, not copper | Out of this phase (Kevin chose lab only) | |

R3 (short paths for power, not signals) is a principle with no copper of
its own. The section 2 chokepoints are what V6 is short of, not sets to give
up. As whole sets they are controls: the K lanes are each proved needed, so
any set holding one is needed; the L lanes, bounce rows, hub lanes and
single lanes are each needed by none alone, and nobody has asked about them
together.

**The pin budget** (V6 doc, end of section 4): all 16 X pins of each
breadboard chip are in use (12 to other breadboard chips, 4 to the SF
chips), and each chip is in 5 doubled pairs, so 5 second-lane pins are what
can be traded. P1 takes 3, A1 takes 1, A2 takes 1 or 2 (R5, in section 5,
would take 1 as well; the V6 doc's budget leaves it out). P1, A1 and A2 with
one lane each use all 5; with two A2 lanes some pair loses its last direct
lane. Every X pin of I to L is named, and their 8 Y pins are one per
breadboard chip.

Those 5 are the second lanes of the 20 doubled pairs. Giving up exactly k of
them on every chip can be done in 33 ways (k = 1), 250 (k = 2), 250 (k = 3),
33 (k = 4) or 1 (k = 5). P1 is a k = 3 choice, and `v6_rails_on_chips` is one
of the 250. These count removal only: which freed pin gets which new wire
multiplies them.

## What is measured (2026-11-22, router at 5374d38)

From the README's findings 11 to 16, which give the cases and commands:

- **The feed costs the router one case.** The firmware's router, V5's copper,
  256 cases: 244 fully routed with the feed on, 245 with it off
  (`k_rows_overflow_metric`).
- **One P1 choice saves crosspoints and loses no netlist.** The exact
  solver, firmware rule, `v6_rails_on_chips` (one choice of the 12 lanes, K
  keeping its rail pins) against V5's copper, both with the feed off, 44
  netlists of dense, real and stress: all routable on both; 861 crosspoints
  against 955 over the 38 proved on both. Other choices, and P1 as its text
  has it, are not scored.
- **The router is not monotone.** `v6_feed_off`, one wire taken away at a
  time: more primaries without 13 of the 94 wires, the same without 24, fewer
  without 57.
- **The router's losses, one wire at a time.** Primaries lost, summed over
  the runs that each took one wire away: the 48 lanes between breadboard
  chips -1 in all, the 32 lanes to SF chips +151, the 8 bounce rows +22, the
  6 hub lanes +32. None is the loss of a group taken away together. Most
  costly: `CI` +10, `IJ` +9.
- **The copper needs hardly any single wire.** The exact solver, firmware
  rule, 5 s a question, `v6_feed_off`, the 244 netlists of dense, real,
  typical and stress, one wire taken away at a time: 86 of the 94 wires are
  needed by none; the eight lanes into K (`AK` to `HK`) are each needed by
  one, `k_rows_overflow_metric`. No answer was left unknown. 43 minutes,
  with the router's part already cached.
- **With the feed off the router leaves one more unclaimed pin**
  (`stress/six_hub_lanes`, chip D's x7). A router bug, not a lab one.

The README's own summary: "Which sets of wires can go together is not
answered by either column". That is this phase.

## What will make a set answer slow or wrong

- **The router is not monotone,** so a set's loss is not the sum of its
  wires' losses. Each set is measured whole.
- **The solver is monotone in copper taken away.** If the netlists can do
  without a set, they can do without any part of it; if they cannot do
  without a set, they cannot without anything containing it. A search can
  prune on both.
- **To the solver, the two lanes of a doubled pair are the same copper** (a
  chip joins any X to any Y), so a solver set can name pairs and how many of
  each pair's lanes go, and proved answers for `/XY0` and `/XY1` on the same
  netlist must agree, which makes a test. To the firmware's router they
  differ (finding 13: without `/DG0` it routes four more), so a router set
  names its lanes.
- **The number of sets is the cost.** 94 wires make 4,371 pairs and 134,044
  triples. One wire taken away cost the router 1.5 s over 256 cases (plan 4,
  "Measured"); the solver takes about a second a question, 5 s at most by
  default; one full `--needed` took 43 minutes of solver time. So the design
  must say which
  sets are asked: the V6 doc's named ones, a per-chip budget, a greedy
  search, or something else. That is the main design question.
- **"Unknown" is sticky and varies.** Answers near the time limit vary from
  run to run. `ceiling.verdict` caches a timed-out "unknown" (asking again
  at the same seconds returns it until other seconds or `lab.py clean`).
  `rank.need` calls `ceiling.ask` directly and caches nothing.
- **Crashes read as losses.** `rank.removal` counts a crash or timeout as 0
  primaries routed. With pins blocked, a netlist that reaches net 59 is a
  crash by the lab's own guard (`BLOCK_NET`, `runner.py:36`). A combined loss
  must keep these apart.
- **Unroutable on the full copper reads as "unknown".** `rank.needed` calls a
  netlist the solver cannot route on the full copper "unknown" for every
  wire. Copper that gives lanes up makes more of those, mixing "impossible
  anyway" with "out of time".
- **Names depend on order.** `rank.without` names a set `"<name> without A,
  B"` in the order given, and rank files and server runs are keyed by name.
  `rank.fabric_of(a)` is a digest of the copper that does not depend on
  order. A rank file records how many cases it covers, not which classes: a
  ranking over fewer classes (`--classes`, or the page's "Rank now") replaces
  the router's part and, on the same copper, keeps the solver's columns, so
  one file can pair a router part over some classes with solver columns over
  others.
- **The router's cache follows the lab's own files.** A cached result's key
  includes a stamp of `runner.py`, `copper.py`, `ceiling.py`,
  `test/hil/routing_check.py` and `fabric_v5.py` (`runner.py:250`). Editing
  any of them makes every cached router result unusable. Results are keyed by
  the pins blocked, not the arrangement's name, so a set and a saved file of
  the same copper share them.
- **Two sources of netlists.** `score.compare` takes them from V5's copper;
  `rank.needed` and `lab.py ceiling` take them from the arrangement when the
  router can run it. The bridges the firmware allows could differ; how often
  is not measured.
- **`score.VERDICTS` omits "nothing"**, which `ceiling.verdict` can return, so
  a score's counts may not add up to its cases.
- **Grown lengths are lower bounds** unless the next bridge was proved not
  to fit. After "unknown", "failed" or "dropped" nothing proves the next
  prefix does not fit, and the bisection never tries a longer one. Finding
  11's 62 without the feed and finding 12's 65 against 62 are such lengths.
  The bisection also assumes routability is monotone in the list's length.

## Doc errors and disagreements found while writing this

In `V6_CROSSBAR_MATRIX.md` (ask Kevin what he meant before scoring these):

- P1 says K "loses three of its twelve special pins" and names none. The
  three nodes it moves are on K.X4, K.X5 and K.X15 (C8), though section 1
  counts GND apart from K's twelve, and GND is also on L.X15. The shipped
  `v6_rails_on_chips` keeps all four, and finding 12 is for that copper.
- P3 (c) points at section 4 for a ninth breadboard chip; section 4 has none.
- P3 (d), "pair them (29 and 59 on one chip's adjacent pins)", is already V5: 29 is
  K.X0, 59 is K.X1, 30 is L.X0, 60 is L.X1.
- P3 (b) puts four rows on two Y0 pins; what that means is not clear.
- P4 counts four L pins freed by moving 30, 60 and ADC4; that is three.
- C3 says `nano_dense_metric` has two nets fail; findings 8 and 10 say it
  routes today (those were the September router's misses, fixed by the hub
  tier).
- A3's reason ("the nano-dense case needs bounces (A2), the K-overflow case
  needs specials rows (A1)") holds only in part. Its first half holds
  neither way: `nano_dense_metric` routes on V5's copper with the feed on and
  off (findings 8, 10 to 12). Its second half holds only with the feed on:
  `k_rows_overflow_metric` is proved not routable with the feed on (finding
  9) and routes with it off (findings 11, 12). Taking the feed off does what
  A1 was for.
- C1 has the feed on GP_8; a booted board with its top OLED on feeds from
  GPIO 6 (README "Checked against a board").

In the lab's own docs:

- `DESIGN_ROUTING_LAB.md` line 236 says the ohms default is 60; the page and
  plan 4 say 42.
- The time of `rank --needed` over the default classes: the timed run took
  43 minutes (42:52) with the router's part already cached, so the solver's
  part is about 43 minutes and a fresh `build/` adds about three for the
  router's. README "The lane ranking" (40 minutes on top of the router's
  three), finding 15 (43) and DESIGN "Piece 4 as built" (40) are within a
  few minutes of that. `lab.py rank --help` says "over an hour" (and "a quarter of one" for
  dense, real and stress, where the README says six minutes), the page says
  "the better part of an hour", and `server.py` says "can take hours".
- README (line 529) says a ranking file is set aside for "a new `--needed`
  over other classes"; the code sets it aside for any new `--needed` over old
  solver columns.
- README line 340's "20 s by default" holds for `ceiling` and the page; `score`
  asks 10 s and 20 s, `rank --needed` 5 s.
- `lab.py`'s usage text (lines 6 to 17) lists neither `rank` nor
  `arrangement score`.
- Plan 4's "Two engines" constraint is narrower than what was built: the
  router is also refused when one pin of a node that keeps another is taken
  away (DESIGN, "Piece 4 as built").

## Ask Kevin before starting

He leaves during long runs, so ask everything at the start.

1. **What answer he wants for a set:** the solver's proof that the netlists
   can do without it, the router's combined loss, or both (the design counts
   a ranking that follows the router's search order as a failure, so the
   router's loss is shown beside need, never as it). And what for: how many
   pins on which chips, and for what (he has said only "for other things";
   the budget above).
2. **Which proposals first,** and whether adding chips (A1 to A4) is in this
   phase. The V6 doc calls adding chips "a separate decision".
3. **P1:** pick the 3 lanes per chip by hand, or have the lab score the
   choices. 250 ways give up 3 second lanes on every chip, and the shipped
   file is one. Scoring them all needs phase-5 code (`arrangement score`
   keeps nothing; `rank` refuses copper only the solver can route). At plan
   4's rate of about 2 minutes a choice over 44 netlists that is about 8
   hours, and up to about 30 if every question runs to its 10 s (estimated,
   not measured). Also whether K keeps K.X4, K.X5 and K.X15 (and L keeps
   L.X15), and what they become if not.
4. **The V6 doc's unclear items:** P3 (b) and (d), P4's fourth pin, A1's 7
   spare X pins, A2 as written (two lanes a chip) or the cost model's
   one-lane version, R5's 12 hub lanes and whether R5 replaces A1 or joins
   it.
5. **New nodes** (R4's port for the Nano header, and any port line not on a
   nano pin): accept that no netlist can use them, or model them as V5 nodes
   moved to new wires. P4's ADCs on L and section 6's port lines on nano
   pins are not new nodes: they are V5 nodes on more pins or where they are,
   and netlists already use them.
6. **Page or command line,** and whether set results are kept as files.
7. **Where the numbers land:** beside each proposal in `V6_CROSSBAR_MATRIX.md`,
   as plan 4's "After this plan" says.
8. **The design's form:** a piece 5 in `DESIGN_ROUTING_LAB.md` (amending its
   status, goals and build order) or a new design doc.
9. **Long unattended runs:** the go-ahead for runs of an hour or more, with
   nothing heavy beside them.
10. **How the plan is built:** subagent-driven or inline, and whether to use
    workflows.
11. **The plan-4 worktree:** whether to remove it once its two ranking files
    (and its `build/ceiling/`) are copied.
12. **Which path rule the V6 numbers use:** the firmware's four crosspoints a
    path, as today; six, as V6 doc section 7 proposes; or the copper rule as
    a bound. "Not needed" under four holds for any looser rule; "needed"
    under four may not hold at six. Six is lab work, not a flag: `MAX_HOPS`
    in `solver/solve.py`, the four in `ceiling.faults` (`ceiling.py:313`),
    and `rank --needed`, which has no `--rule`.

## Rulings in force from plan 4

Still true at 263225a:

1. Taking away one pin of a node that keeps another (GND) makes an
   arrangement solver only.
2. With `"feed": true`, every feed end must keep a pin, or the arrangement
   is refused; `arrangement.with_feed` raises on the same.
3. The misspelling rule as written under "An arrangement file" above.
4. Ranking files live at `build/rank/<variant hash>_<name>.json` with a
   `"fabric"` digest and `"nodes_as_v5"`. Re-ranking the router on the same
   copper carries the solver's columns over. A file holding solver columns is
   copied aside first (`<stem>.set-aside.json`, then `-2`, `-3`) when other
   copper or new solver columns would replace it. A router-only file is
   simply overwritten.
5. Rankings narrowed by `--wires` or `--case` are printed, not kept. One
   narrowed only by `--classes`, or the page's "Rank now", replaces the
   router's part (ruling 4 says what happens to the solver's columns).
6. A set of wires taken away is a run, not a combined-loss number.
7. `edge.grow` reports a harness crash or timeout as "failed", which proves
   nothing.
8. A run in which the router closes a crosspoint on a taken pin fails.
   (`rank` counts such runs in `used_after`, which nothing prints.)
9. `lab.py arrangement score` asks 10 s a case and 20 s a grow probe unless
   `--seconds` says otherwise (one value sets both).
10. On copper only the solver can route, the table beside the solver's
    picture is a router run on other copper with the same feed: for a
    netlist made by clicking nodes, V5's copper; for a battery run, whatever
    arrangement that run used. The page names it.

## Known small gaps, not fixed

- `rank.needed` counts a netlist the solver proves unroutable on the full
  copper as "unknown" for every wire. Matters for this phase (above).
- `rank.removal` folds a router crash or timeout into the loss. Matters for
  any combined loss (above).
- A file named `arrangements/v5.json` would be listed twice and never loaded
  by name.
- Picking arrangements quickly twice on the page can draw the first one.
- `server.ran_on` is keyed by name and never cleared; editing a file and
  re-running other classes on the page mixes copper under one name.
- A node placed on a breadboard chip's Y0 gets no pad in the fabric drawing,
  and a node's wire keeps its pad when the node is removed or moved with
  `nodes`. P3 (b) hits the first; P3 (a) hits the second only when written
  as nodes removed with `null` (solver only), not as pins taken away.
- `web/lab.js` is tested only by string checks and `node --check`. Page work
  for sets would need checking in the browser by hand.
- `fabric_view.py:193`: two pads of node buses with no SF X pin overlap their
  labels (drawing only).

## House conventions for the design and the plan

- **Plan header,** as plans 3 and 4: a sentence-case title (`# Routing lab,
  plan 5: …`), the "For agentic workers" line word for word, then
  **Goal**, **Architecture**, **Tech Stack**, **Spec** (design sections by
  heading).
- **Sections in order:** Global Constraints; "Measured before writing this
  plan (date, router at …)", from throwaway prototypes ("The tasks' tests are
  what must hold"); File structure (a table, each path new or modify);
  Review Focus (opening "The inputs the design is silent on that are most
  likely to bite. Each has its test in the task named.", then numbered bold
  inputs with their tasks); the tasks; Not in this plan; After this plan.
- **Global Constraints:** plan 4's eleven carry over, with "Two engines"
  widened to the rule as built (ruling 1 above).
- **A task:** `### Task N: <plain title>`; `**Files:**` (Create, Modify);
  `**Interfaces:**` (Consumes, Produces with exact signatures, dict keys,
  flags, output text, HTTP codes); rules not open to reinterpretation marked
  "(binding)"; checkbox steps: write the failing tests, run to see them fail,
  implement, run all tests, check in the browser for page work, commit with
  the exact message. The last task is "Documents" (README, design, the V6
  doc).
- **Tests:** `tools/routing_lab/tests/test_<module>.py`, methods named as
  plain sentences, solver tests behind
  `@unittest.skipUnless(ceiling.solver_installed(), NEEDS_SOLVER)`.
- **Commits:** the exact subject the task's commit step gives (`Routing lab:
  <what now exists>` or `Routing lab page: …`), with no body unless the step
  asks for one. A measuring task's step asks for "Measured <date>: <engine>,
  <arrangement>, <feed>, <cases>:" and the numbers; a fix round lists its
  fixes.
- **The design:** a piece section of bullets that each open with a bold
  phrase; "Widened on <date> by …" when Kevin's answers change it; a "Piece N
  as built (date)" subsection opening "Built as above, with these
  differences:"; numbers in the README's findings, not the design.
- **Style:** short present-tense sentences; "must" and "never", not
  "should"; "for example", never "e.g."; no em dashes; plain words ("taken
  away", "wire", "copper", "netlist", "the firmware's router", "the exact
  solver"); every number dated with its engine, arrangement, feed and cases;
  "unknown", "not asked", "not confirmed" spelled out; on the page, red only
  for problems.

## Standing constraints

- Nothing under `src/` is edited. `test/hil/` is read only. Nothing under
  `tools/routing_lab/harness/` is edited (the board check is recorded for the
  harness's hash).
- Never push. Never touch `.github/workflows/release.yml`. Stage files by
  name; never commit `.pio/**/firmware.uf2`. No attribution lines in commit
  messages or pull request descriptions.
- The lab imports only the standard library; `ortools` only in
  `solver/solve.py`.
- Flashing a board needs Kevin's go-ahead each time.
- Never touch the main checkout's uncommitted work (above).

## Commands

From the new worktree's root:

```bash
python3 tools/routing_lab/lab.py solver-setup
```

```bash
python3 -m unittest discover -s tools/routing_lab/tests -t tools/routing_lab
```

```bash
python3 tools/routing_lab/lab.py arrangement list
```

About ten minutes the first time in a new worktree (plan 4's estimate);
`--against v5` is the default:

```bash
python3 tools/routing_lab/lab.py arrangement score v6_rails_on_chips --grow 2
```

About 45 minutes on a fresh `build/` (about three for the router's part,
about 43 for the solver's). Run it in the background, and only to measure again: the
copied plan-4 file already holds its answer, and a finished run sets that
file aside:

```bash
python3 tools/routing_lab/lab.py rank --needed
```

The page, at `http://127.0.0.1:8770/`; it runs until stopped:

```bash
python3 tools/routing_lab/lab.py serve --port 8770 --no-open
```
