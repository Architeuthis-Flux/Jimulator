# The page

What `python3 Routing/lab.py serve` opens, and what an exported page (`lab.py export`) is: one file, `index.html`
with `lab.css` and `lab.js` inlined and the run's data beside them. The picture guide for a first visit is the
repository's README; this is the reference.

```bash
python3 Routing/lab.py serve
```

Opens `http://127.0.0.1:8765/`. Pick a router and the classes, press Run,
click a case.

- **Examples first, tests behind a box.** When a run holds the `example`
  class, the left panel lists those cases alone: a title, a line about what
  the case shows, and how many of its jumpers routed (a mark and red when
  not all did). Tick **tests** for the battery's table, every class with its
  numbers, the examples at its head. A run with no examples shows the table
  as it always did. The first example is open when a page is first seen.
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
- **Trying a change.** Edit the router in the firmware checkout (see
  `Routing/README.md`, "The firmware checkout") and tick **re-run on
  save**: the battery re-runs when a file under `src/` changes. Or drop
  `NetsToChipConnections.cpp`, `MatrixState.cpp` or any other source file on
  the left column: it is built as "worktree + 1 file" without touching the
  checkout. A router that does not compile shows the compiler's output and
  keeps the last table.
- **Arrangement** is the crossbar copper: V5's, or one of the files under
  `arrangements/` (see "Arrangements" (`Routing/arrangements/README.md`)). It is what the Fabric tab draws and
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
  `JumperlOS/test/hil/fabric_v5.py`). A lit wire carries the net of its colour; a dot
  is a closed crosspoint. On another arrangement than V5 a grey cross is a
  pin taken away and a thin ring a pin on another wire than V5 has it on; a
  wire of no shape V5 has (a rail on a pin of every chip) is drawn as a bus
  on a level of its own.
- **Crossbars tab.** The twelve chips as the board itself prints them (its
  `C` command): a row for each X pin, a column for each Y pin, a block
  where the two are joined, lines along the pins that carry something in
  their net's colour, and the wire on each pin named at the row's end and
  under the column. A block lights its net and a name picks its wire, as in
  the fabric. Selecting the text copies the board's own characters.
- **Ranking**, the second face of the case panel (the small "ranking" on
  its bar). The table is there and the fabric wears its tint: what the
  router loses without each wire, or how many netlists are proved to need
  it. See "The lane ranking" (`Routing/arrangements/README.md`).
- **KiCad sheet tab.** The board's own schematic with the same result drawn
  over it: lit wires, lanes followed along their bus from chip to chip, a
  dot at each label and pin of a live net, and each closed crosspoint as a
  curve inside its chip from the X pin to the Y pin. A lit wire is followed
  past the crossbar too: across a closed jumper, the 0R or the 2 ohm shunt
  it is drawn as the wire is, and on the far side of its op-amp it is
  **striped**: the net's colour, whole, with thin white stripes across it,
  since a buffer or a scaling stage has changed the signal by then (the
  ADCs' followers and dividers, the DACs' gain stages, the routable
  buffer). The tip says the part and what it does, and the legend's "after
  an op-amp" shows these alone. A rail is not followed so: it is drawn in
  the rail's own colour up to its supply's op-amp, and not into the DAC
  behind that. The table is `BEYOND` in `sheet.py`, read from the r7
  schematic on 2026-11-23: eleven wires have a stage, nine are followed
  through theirs, and R88 (the probe's feed onto `ROUTABLE_BUFFER_IN`) is
  taken as fitted, as the schematic has it. Build the sheet once with
  `python3 Routing/lab.py sheet [board.kicad_sch] [--theme NAME]`
  (needs KiCad's `kicad-cli`; the default is the V5 r7 sheet in
  `~/Documents/GitHub/JumperlessV5`), and again after a change to `BEYOND`.
  The plot is some 160,000 paths and takes about an eighth of a second to
  draw again at each step of a zoom or a drag, so the build also draws it
  once as a bitmap (with a headless Chrome, Chromium or Edge, when one is
  installed): the page shows the bitmap while its view moves and the plot
  once it rests. An export carries both beside the page.
- **Colours.** Ground and the two power rails wear the firmware's own
  colours, as the board's LEDs show them: ground green, a rail red, and
  blue while that rail is set negative. Every other net has one of sixteen
  colours, none of them red, and they repeat after sixteen nets.
- **Marks, fabric and sheet.** A problem is red with a white edge (a rail's
  red has none): a wire
  carrying two nets (a short), a net on a node that is in no net (a stray),
  or a ring where the chip status and the copper disagree (a closed pin
  nobody claims, a claim for another net, or, in the cases judged strictly,
  a claim with no copper). Lighting one net alone never dims a problem. A
  hollow dot, or on the sheet a dashed curve inside a chip, is a duplicate
  path's crosspoint: one of the extra copies of a jumper. A small
  square is a pin claimed while no net rides its wire, where that is
  allowed. A dashed ring marks the ends of a bridge that is not there: in
  the net's colour when the router failed it (not routed, or listed as
  routed while its copper does not connect), grey when the firmware refused
  or dropped it by rule.
- Click a net, a lit wire or a crosspoint to light that net alone; it holds
  across the tabs. The wheel (or a pinch) zooms about the pointer, by as
  much as you scroll, so a trackpad and a wheel feel the same; drag pans;
  double-click fits. Hover a wire for its pins and claims.
- **Hands.** A click answers. On a wire it says what the wire is and
  carries, in a readout over the drawing's corner, and lights its net, or
  the wire itself when it carries none. On a crosspoint, a chip, a bridge's
  row (its two ends are ringed), a net, or a problem or note that names a
  net, a pin, a wire or nodes, it shows that in the drawing. A key of the
  legend, or a count in the case panel, shows that kind of mark alone. The
  same click again, a click on the empty drawing, or Escape lets go. The
  arrow keys move through the tests; Right goes to the case's bridges and
  nets and Left back; with the ranking open they move through the lanes. A
  column head sorts the cases of each class by it. The three buttons in the
  drawing's corner zoom out, fit and zoom in (on the sheet a second **fit**
  shows the whole sheet; on the crossbars they size the text), and the
  corner says how far in the drawing is.
- **Panels.** The page is three panels: the tests, the view and the case.
  Drag a panel by its name plate onto a side of another and it goes there;
  drag the line between two to size them; the button on a panel's bar folds
  it to the bar. A double-click on a plate puts all of it back. The view's
  tabs pick a view and nothing else, and a view can have a panel of its
  own, so that the fabric, the sheet and the crossbars show at once: drag
  its tab onto a side of a panel, or press **dock** for the view shown (it
  goes under the tests). Such a panel has its own zoom buttons, and
  **tabs** on its bar puts the view back. One view always stays among the
  tabs. The browser keeps the arrangement, the sizes, what is folded and
  which views have panels, and for each page the tab, the case and the
  table's order it was left on. On a narrow screen the panels are one
  column, the view on top, and only fold.
- **The look.** Jumperless's greys, rainbow and magenta, on panels cut like
  a ship's console: name plates, cut corners, narrow capital labels. Red
  still means a problem and nothing else. The fonts (Archivo Narrow, IBM
  Plex Mono, Michroma) are used where a site has them; the lab's own page
  falls back to the system's.
- **A board's own output.** Drop a file holding what a Jumperless prints for
  `b`, or copy it out of a terminal and paste it anywhere on the page. It is
  judged by the same checker and shown as a run of its own, class `board`,
  on both tabs, with the case panel, the missed paths and the Ceiling
  section as for any case. Press Run to go back to the battery. Details
  under "A board's own output" below.
- **A live board.** **Connect a board** reads a Jumperless V5's routing over
  Web Serial and redraws it when it changes, as the case `live_board`. It
  only reads. Details under "A live board" below.
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

"Ceilings" (`Routing/solver/README.md`) below says what these three mean and what they do not.

The server listens on 127.0.0.1 only, answers only its own page (a token and
an origin check), and builds only the firmware checkout, git refs of it, and the
`--tree` directories it was started with.

```bash
python3 Routing/lab.py export run.html --baseline main
python3 Routing/lab.py clean
```

`export` writes one battery run as a single HTML file that opens without the
server (table, case panel, fabric view, missed paths and spare copies; not
the KiCad backdrop, and it cannot ask the solver). With `--arrangement NAME`
the run is on that arrangement, one the firmware's router can route, and the
page is drawn on its copper. The ranking kept for the router on it travels
too and shows as the page's ranking; the page cannot make one or run without
wires. On a narrow screen the page is one column, the drawing on top; one
finger pans it and two zoom. `clean` deletes the caches
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

## A live board

**Connect a board** (Chrome, Edge, Opera or Brave, on `https` or on
`127.0.0.1`) reads a Jumperless V5's routing from the board itself and shows it
as the case `live_board`, in every view, judged as a pasted report is. When the
board's routing changes the page reads it again and redraws it. The page only
reads: it never routes, clears or loads anything on the board, and it never
sends `b`, which prints on the board's own terminal. Built and tested on
a trace built from the board captures of 2026-11-21, with made-up `N` and
`:gen` answers, on the local server. No port 7 exchange has been recorded from
a board yet, and it has not been tried on one.

- **The port.** The board shows four USB serial ports, and they look alike.
  The page reads the fourth, the machine backchannel ("port 7"). Pick the
  one whose name ends `port7` (macOS), or the last of the four. The picker is
  filtered to the board's USB id, which all four share, so the page proves
  the port first: it sends one `N` and wants a net list back. A port that
  does not answer is closed and forgotten, and nothing else was sent to it.
  Once the browser has let the page open one port, the button reads "Connect
  the board again" and uses it without the picker. The port is opened at
  115200 and at no other speed.
- **What the page sends**, as the page says it beside the button:

  > To the board's fourth port only, and only after you press Connect. N once: its net list, which proves the port is the right one. :ver once: its firmware version. :gen twice a second: a counter that moves when the board rebuilds its routing, and whether it has finished sending it. :paths and :crossbar when that counter has moved: its routing report, and which crosspoints are closed. All five are questions. None makes, removes or reroutes a connection, and none prints on the board's own terminal. Nothing is sent to any other port. The picker lists the board's four ports and they look alike: pick the one whose name ends port7 (macOS), or the last of the four. A wrong port gets the one N and is closed. Opening the second one by mistake can reset an Arduino plugged into the board.

  Only the timings can be overridden (in the tests); the speed, the buffer
  and the five things sent are fixed, and the code refuses to send anything
  else.
- **The firmware it needs.** `:gen`, `:paths` and a `:crossbar` that waits for
  the second core. They are three read-only calls added to JumperlOS on the
  branch `port7-routing-reads` (commit `f963e4c`, in a worktree), which is not
  on GitHub and not in a release: no released firmware answers them yet, and
  the submodule here is not moved to it. A board without them answers
  `unknown_verb`; the page then says the firmware is too old for a live view
  and which release has them (`BOARD_PORT.NEEDS`, still a placeholder
  naming a release that is not out), and does not ask `b` in their place.
- **What the board does not answer.** Port 7 is answered from the board's
  main loop only: not in probe mode, in a menu or in an app. The page then
  says "waiting", with how long and when it last read, dims the view's title
  and keeps the last reading on screen. It is not an error and it is not red.
  A board that does not answer is waited for, with no limit, and only
  **Disconnect** ends that. A reply counts as begun only once the board has
  echoed the query; a stray line is neither an answer nor a reason to ask
  again. A reply that begins and then stops for three seconds is thrown away
  and asked once more. The pause between polls is not cut short by anything
  the board sends.
- **What a reading is.** `:gen` gives the routing's counter and whether the
  board has finished sending it. When it has moved and the board is idle, the
  page asks `:paths` and `:crossbar`, one query at a time, then asks `:gen`
  once more. A reading counts only when both answers say idle with the same
  number; otherwise the page tries again. **read again** reads the report and
  the dump whatever the counter says, when the board is idle.
- **Sent equals planned is checked on every reading.** The dump is the chips'
  own state and goes to the judge with the report, so what was sent is
  compared with the path table each time, which a pasted `b` report cannot do
  without a dump.
- **What changed.** From the second reading on, the crosspoints closed since
  the reading before are marked in the fabric, on the KiCad sheet and in the
  crossbars. A closed one is ringed in the colour of a change (cyan), never
  red. An opened one is grey: a small hollow ring in the fabric, a dashed
  curve on the sheet, an outline in the crossbars. The case panel counts them ("at the board's last
  change: 3 closed, 1 opened, 2 bridges changed") and a count shows them
  alone; a bridge whose state changed is marked in the table. A net that only
  got another number is no change. A redraw keeps the zoom, a docked view and
  the lit net, by its number: a board that renumbers its nets has another net
  lit.
- **Running the battery while linked.** The battery stays on screen. The
  status line then says "the board changed at HH:MM:SS", and a click on that
  brings the board's case back. A board with nothing connected is shown as
  such, with a note, where a pasted report with no bridge is refused.
- **When it fails.** A port held by another program or tab (a Jumperlessim
  viewer, a script), a port that is not the fourth, and firmware too old each
  say so under the button and leave the page not linked. **Disconnect** stops
  every query. A cable pulled says "lost". Nothing reconnects by itself, and a
  reload does not.
- **Save trace** is a button. It downloads every byte sent and received since
  Connect as JSON Lines, one exchange a line (`port7_DATE_TIME.jsonl`).
- **`serve --replay TRACE`.** `python3 Routing/lab.py serve --replay FILE`
  makes Connect read a trace through a fake port in place of a
  board, with no port opened and no Web Serial needed. It is for the tests and
  the browser check, not for visitors. `tests/fixtures/port7_built.jsonl` is
  a trace built, not recorded, from four captures (its `N` and `:gen` answers
  are made up).
- **What it is not.** V5 only: an OG's report is refused with the lab's usual
  message. One board at a time, since every V5 has the same serial identity.
  It reads routing: no LEDs, OLED or voltages (that is Jumperlessim's
  viewer). An exported page hides the Connect row, since it has no judge.
  Safari and Firefox have no Web Serial: the button is disabled, with the
  reason, and paste and drop stay.
