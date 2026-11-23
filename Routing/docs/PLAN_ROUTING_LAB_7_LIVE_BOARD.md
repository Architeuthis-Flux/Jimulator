# Routing lab, plan 7: a live board in the browser

> **Revised 2026-11-23 to the design.** Written by reading the firmware and the lab, on no board. Nothing in it has
> been checked against a board, and the firmware calls it rests on do not exist yet (Task 1 makes them). The page's
> files changed several times that day, so they are cited by function name, not by line.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A button on the lab's page connects to a Jumperless V5 over Web Serial, and the page shows that board's routing as a case that redraws by itself when the routing changes, with what changed lit. The page only asks. It never makes, removes or reroutes a connection, and nothing it asks prints on the board's main terminal.

**Architecture:** The firmware gains three reads on its fourth serial port, the machine backchannel (USBSer3, "port 7"): `:gen` (the routing's change counter and whether the second core is idle), `:paths` (what `b` prints, with none of `b`'s side effects) and a `:crossbar` that waits out a sense tap. The page opens that port and nothing else, proves it with one byte, then asks `:gen` twice a second. When the number has moved and the board is idle it reads `:paths` and `:crossbar` and posts both to `POST /api/board`, which the lab already has, so the judge, the copper searches and the drawing are the ones a pasted report gets. A new `board.changed` says what differs between two readings. The port code is a new file with no DOM in it, `web/board_port.js`, tested under `node` with a fake port that replays a trace. It ships on the local lab server. Everything it asks of the lab goes through the page's one `api(path, body)`, so the engine in the tab answers it when piece 6 is built.

**Tech Stack:** Python 3 standard library; the existing page (plain JS, SVG); Web Serial in the browser (Chrome, Edge, Opera, Brave); `node` for the port code's tests (the suite already needs it); PlatformIO for Task 1's two firmware builds. No package is added.

**Spec:** `Routing/docs/DESIGN_ROUTING_LAB.md`, the section "Piece 7: a live board". It is binding: where this plan and it disagree, this plan is wrong. The firmware reading it rests on is `Routing/docs/NOTES_2026-11-23_FIRMWARE_PORT7_AND_TAPS.md` ("the notes" below: sections A1 to A6, B1 to B4). What the design decided:

- **Local server now.** The published page waits for piece 6.
- **Port 7 only**, at 115200, proved by the single byte `N` before any `:`.
- **Five things sent:** `N`, `:ver`, `:gen`, `:paths`, `:crossbar`. Never `b`, never `n`.
- **The page polls.** `:gen` every half second; `:paths` and `:crossbar` only when the number moved and the board is idle.
- **Three firmware calls first.** Firmware without them is told it is too old. There is no fallback.
- **"Sent equals planned" is checked,** exactly, on every reading.
- **One board, one case** named `live_board`, read-only. A silent board is "waiting", never red.
- **A fake port and traces** test it without a board. One bench sitting, with one flash, asked for at the time.
- **V5 only.** The OG is out.

Decided here, where the design is silent, and Kevin's to overrule: the idle flag is `1` or `0`; `:gen` is asked once more right after the dump, so a rebuild between the two reads cannot show as a fault; `:crossbar` copies up to four times; a "read again" button reads the pair while the number stands, because the notes do not establish that every change moves it; what changed is lit in all three views; the page does not stop asking while its tab is hidden; a run of identical exchanges is one line of the trace; the version the page names as needed is set when the firmware is released (Task 7).

Also read: `Routing/web/README.md`, "A board's own output", for what exists; `JumperlOS/src/tubes/Ser3Backchannel.h` for the port's protocol.

## Global Constraints

- **Two repositories.** The lab is the Jimulator repository: `~/Documents/GitHub/Jimulator`, the lab in `Routing/`, branch `main`, public on GitHub. Tasks 2 to 7 commit there, one commit a task, and push only when Kevin asks. Task 1 is the firmware's and is done in a JumperlOS worktree of its own (below).
- **Nothing under `Routing/harness/` is edited or added to:** its files are part of the hash that names a router build. Nothing under Jimulator's `JumperlOS/` is edited: it is a submodule the lab reads, and it moves only as Task 7 says.
- **The firmware is edited in one place only:** a git worktree of JumperlOS on a new branch off `origin/main`. Never in `~/Documents/GitHub/JumperlOS` itself, which holds someone else's uncommitted work. It is built for both targets. It is never pushed without Kevin's word: a push to `main` there publishes a release. `.pio/**/firmware.uf2` is tracked and is never committed; `.github/workflows/release.yml` is never touched. Stage files by name. Until that commit is on GitHub the page's side is built and tested against traces, and the submodule stays where it is.
- **No step talks to a board except Task 6,** and Task 6 does not start without Kevin's go-ahead. Flashing is asked for again at the moment it is done.
- No attribution lines in commit messages.
- The lab itself imports only the standard library. So the server never opens a serial port (that would need `pyserial`): the page does, and sends the text.
- **The page never sends anything to a board the user has not connected by a click, and says what it sends.** A reload does not reconnect by itself. What it sends is written on the page beside the button, and every byte sent and received is kept in a trace the user can save.
- **Five things, and no other byte:** `N`, `:ver\n`, `:gen\n`, `:paths\n`, `:crossbar\n`. Never `b` and never `n`: each prints a "Couldn't find a path" line for every failed primary on the main terminal and marks paths again (notes A1, A2). Never a `:` before the port has answered `N` with a net list: on the main port `:` is "set DAC voltage" (`JumperlOS/src/SingleCharCommands.cpp:563`). The port is opened at 115200 and at no other speed: 1200 on the REPL port reboots the board into BOOTSEL (`JumperlOS/src/tubes/ArduinoStuff.cpp:386-402`).
- **One query unanswered at a time.** The page sends the next only when the last is answered. A board that is silent is waited for, not asked again.
- **Say who answered.** A live case says it is a board's own routing and not the lab's router, the firmware version the board gave, that it came over port 7, and when it was read.
- On the page a problem is red with a white edge, and a power rail is red too (the firmware's colour for it, since 2026-11-23). What changed is lit in a colour that is not red. A board that does not answer, or whose firmware is too old, is not a problem of the routing and is not red.
- In `lab.js` two words are taken. "live" means "re-run on save" (`installLive`, `#live`, `state.liveTried`). "changed" means "changed from the baseline" or "pin not as V5" (`changedFromBase`, `td.changed`, `#filter-changed`, `#key-changed`). This plan's names in the page use `link`, `board` and `moved`. `lab.js` moves fast: find a function by its name, and before a task that modifies a page file, `git status` must be clean.
- Tests: `python3 -m unittest discover -s Routing/tests -t Routing` passes with the solver installed and without it (371 tests on 2026-11-23).

## Measured before writing this plan (2026-11-23, by reading; no board was touched)

The firmware was read twice. The draft of this plan read Kevin's main checkout at `0b8d06c`, which had uncommitted edits to `Probing.cpp`, `config.h` and `JumperlessMicroPythonAPI.cpp`. The notes then read the submodule at `5374d38`. Bullets that cite the notes, and everything in Task 1, are of `5374d38`. The other firmware lines below are the draft's and may be a few lines off. JumperIDE was read at `7e37427`, Jumperlessim at `5ea97c11`. Paths starting `JumperlOS/src/`, `include/`, `boards/` and `test/` are the firmware's; paths starting `Routing/`, and bare lab file names, are the lab's.

**How a browser reaches the board**

- **Four serial ports, one identity.** The board is USB `1D50:ACAB` (`JumperlOS/src/tubes/usb_descriptors.cpp:71-72`) with four CDC interfaces named "Jumperless Main", "JL UART Passthrough", "JL Micropython REPL" and "JL TUI" (`include/usb_interface_config.h:63-69`). On macOS they are `/dev/cu.usbmodemJLV5port1`, `3`, `5` and `7` (`JumperlOS/test/hil/jl.py:454`, `:671`; `JumperlOS/test/hil/port7.py:17`). The serial string is the constant `JLV5port` (`usb_descriptors.cpp:511`), so two V5s cannot be told apart.
- **JumperIDE opens what the user picks.** `navigator.serial.requestPort()` with no filter (`JumperIDE/src/jumperless_serial_terminal.js:322`, `transports.js:224`), at 115200 (`transports.js:238`). It says the four ports "all share one VID/PID" and finds the REPL by probing each (`app.js:4339-4349`, `:4392-4397`). It never uses the backchannel.
- **Jumperlessim already talks to port 7 from Chrome.** Filter `{usbVendorId: 0x1d50, usbProductId: 0xacab}` (`Jumperlessim/packages/app/src/ports.ts:1-8`), 115200 with a 65,536 byte read buffer (`packages/engine-webserial/src/lineChannel.ts:21`), one query in flight (`engine.ts:73-80`). Kevin ran it against a real V5 in Chrome from its dev server on localhost (`docs/HANDOFF-2026-09-10.md:88-89`). Its read loop first died on Web Serial read errors; taking the reader again and the larger buffer fixed it (`HANDOFF:90`, `lineChannel.ts:29-46`). Its probe byte is stale: it sends `K` as "harmless on every CDC port" (`engine.ts:27-35`), and on the main port `K` now opens the click menu (`JumperlOS/src/SingleCharCommands.cpp:529-533`).
- **Web Serial's limits, as JumperIDE meets them.** It needs a secure context and a Chromium browser (`app.js:215-222`), a click for the picker (`app.js:4137-4138`), and the OS gives a port to one program: Chrome reports another holder as `NetworkError` (`transports.js:177-196`).

**What the firmware offers, and on which port**

- **Port 7 is the machine port.** USBSer3 is CDC interface 3, begun at 115200 (`JumperlOS/src/tubes/ArduinoStuff.cpp:209-212`). Only commands tagged `SER3_ALLOWED` run there; the rest are refused with a JSON error (`Ser3Backchannel.h:19-28`, `Ser3Backchannel.cpp:1242-1261`). Bytes under 32 are dropped. A `:` line is echoed back before its reply (`Ser3Backchannel.cpp:1085-1107`, `:1186`). A verb it does not know is answered `{"error":"unknown_verb","verb":"<verb>"}` (`:869-871`); `gen` and `paths` are answered so today.
- **What it gives cleanly today** (notes A5): `N` (the net list), `:crossbar` and `:ver`. The path table, the chip status, the infra bridges and the change counter are reachable only through `b` or `i?`.
- **`b` and `n` are not reads** (notes A1, A2). Each calls `couldntFindPath(1)`: one line a failed primary on port 1, at every ask, and those paths marked again. The draft said a `b` "writes what is already there"; the notes show that is not always so. `b` also puts colour codes on port 1. The page sends neither.
- **The crossbar dump.** `:crossbar` answers `xbar{12x8:` and 384 hex digits and `}`, a copy of `lastChipXY`, the crosspoints last sent (`Ser3Backchannel.cpp:378-394`). As captured, a reply is 406 bytes with its echo (`Routing/fidelity/board_0621e4f44e23/*.xbar.txt`).
- **The net list.** `N` on port 7 answers `{ "nets": [ ... ] }` (`Ser3Backchannel.cpp:254-262`, `:1066-1078`). `N` is no command on the main port; an unknown key there shows the menu (`SingleCharCommands.cpp:168-172`). The page uses it once, as the proof of the port.
- **Nothing is pushed when the routing changes,** and `:every` is not a push: it holds the port's service call for the whole capture (`Ser3Backchannel.cpp:1010-1034`). So the page asks.
- **The change counter** (notes A6). `routingGeneration` goes up at each rebuild's head and again when the second core starts the send, and restarts at 1 on boot. The draft said "every rebuild and clear". Not established: that every change to the path table moves it.
- **Port 7 is answered from the main loop only** (notes A6): `Jerial.cpp:1167-1168`, called at `main.cpp:1206` and `Menus.cpp:908`. The probe loop is `Probing.cpp:4390-4399` and `Jerial` is no jOS service (`JumperlOS.h:427-431`). So by reading, port 7 is silent in probe mode and in an app. **Not verified on a board.**
- **Sense taps** (notes B1, B2). The net scan closes one tap at a time for about a millisecond, at least 5 ms apart, on copper that is free, and each sets its bits in `lastChipXY` (`CH446Q.cpp:1619-1625`). It is on by default (`config.h:175`). The router never sees taps and a primary is never refused for one. FakeGPIO writes the same shadow and is not known to raise `core2busy`; MicroPython's direct crosspoint call was not read again (notes B4).
- **A board's write does not time out.** `Adafruit_USBD_CDC::write()` waits while the host holds the port open and does not read (`usb_descriptors.cpp:609-612`). The page must read whenever the port is open.
- **The version.** `:ver` on port 7 prints `Jumperless firmware version: X` (`Ser3Backchannel.cpp:835-838`, `SingleCharCommands.cpp:3044-3051`).
- **What the wrong port does.** A rising DTR on the UART passthrough port is taken as the start of a flash: it can reset a plugged-in Arduino and has the UART routed to it (`JumperlOS/src/tubes/AsyncPassthrough.cpp:2325-2337`, `:2343-2377`). On the main port the first byte of a new connection brings the greeting, `:` is "set DAC voltage" and `A` connects the UART to D0 and D1 (`SingleCharCommands.cpp:563-565`, `:553-555`). Whether Web Serial raises DTR on `open()` was **not verified**; Jumperlessim says it does (`engine.ts:111`).
- **Who else holds a port.** The desktop app sits on port 1. Port 7 can be used while port 1 is held (`JumperlOS/test/hil/port7.py:3-6`).

**What the lab needs from the board**

- **The report, and nothing else, draws the picture.** `board.result(name, text)` wants the last whole report in the text: "Bridge Array", "Paths" and "Chip Status" with all twelve chips. `:paths` prints those three under the same headings and leaves out the five settings lines `b` prints before them; no parser reads those lines. Tried on 2026-11-23: a capture cut to start at "Bridge Array", behind the echo `:paths`, is read by `board.result` with its dump, with no problem and no note about the dump.
- **The dump is the check.** With `xbar{12x8:...}` in the text, `runner.judge` hands it to the checker's "sent equals planned" (`JumperlOS/test/hil/routing_check.py`, `check_sent_matches_planned`). Tried the same day: one routing's table with another's dump gives 48 problems, the first "PLANNED but not SENT: chip A x2 y1".
- **A report with no bridge is refused.** `board.result` raises "its Bridge Array lists no bridge", which `/api/board` answers as 400. All 21 captures list the probe feed's bridge. Whether a cleared board always lists one was **not verified**.
- **Never there for a board:** sense taps and the second-rebuild check (`Routing/web/README.md`, "A board's own output").
- **The same name again replaces the case.** `api_post_board` keeps results by case name under the run `board` (`server.py`, `api_post_board` and `keep`).
- **`showBoards` is not a redraw.** It empties `state.cases` and ends in `selectCase`, which lets go of the lit net, the picked bridge and the picked wire.
- **An exported page cannot judge.** `staticApi` answers four paths and refuses the rest.
- **Report sizes.** The 21 captures of 2026-11-21 are 2,517 to 4,046 bytes, taken on port 1 with the colour codes stripped. Port 7's text carries no colour code (notes A2), so a `:paths` reply should be that long less the five lines. **Not verified.**
- **Two readings compared**, with the lab's own code on those captures, again on 2026-11-23: `same_chip_pairs` (7 bridges, 16 crosspoints) and `sf_to_sf` (9 bridges, 32 crosspoints) share no crosspoint and one bridge, the probe feed. `k_rows_overflow_metric` routes 12 of 13; the one that fails is the feed, BUFFER_IN to GPIO_6.
- **`node` is here and already needed.** v20.18.3 on this Mac; `tests/test_server.py` runs `node --check` with no skip.
- **JumperlOS has no host build of the backchannel.** Its host tests compile the router alone against stubs (`test/test_routing_og/run.sh`); `Ser3Backchannel.cpp` includes most of the firmware, and those stubs have no `waitCore2`, `core1req::allIdle` or `disableTerminalColors`. So Task 1's checks are bench checks.

**Not verified at all:** what Chrome's port picker shows for each of the four ports; that `http://127.0.0.1:8765/` gets Web Serial (Jumperlessim's page on localhost did); how long `:paths` holds the board's main loop; anything about the three calls on a board. Task 6 looks at each.

## File structure

| File | Responsibility |
|---|---|
| JumperlOS worktree: `src/tubes/Ser3Backchannel.cpp`, `.h` (modify) | The three calls: `:gen`, `:paths`, a `:crossbar` that waits out a tap |
| JumperlOS worktree: `test/hil/test_port7_reads.py` (new), `run_all.py`, `README.md` (modify) | Their bench checks |
| `Routing/board.py` (modify) | `changed`: what differs between two readings. `about` and `live` on a result |
| `Routing/server.py` (modify) | `/api/board` takes `about` and `live` and answers `changed`. `serve --replay FILE`: `/api/replay`, and `replay` in `/api/info` |
| `Routing/lab.py` (modify) | The `--replay` flag of `serve` |
| `Routing/web/board_port.js` (new) | The board's port, no DOM: the replies read, `BoardLink` (open, prove, ask, one query at a time), `FakePort`, the trace |
| `Routing/web/lab.js`, `index.html`, `lab.css` (modify) | The Connect button, what the page sends, the link's state, the live case's redraw, what changed lit |
| `Routing/export.py` (modify) | An exported page carries `board_port.js` inlined, as it carries `lab.js` |
| `Routing/tests/board_port_test.js`, `tests/test_board_port.py` (new) | The port code under `node` |
| `Routing/tests/fixtures/port7_built.jsonl` (new) | A trace built from four captures, for the tests and the replay |
| `Routing/tests/fixtures/port7_<date>.jsonl` (new, Task 6) | A trace from a real board |
| `Routing/tests/test_board.py`, `test_server.py`, `test_export.py`, `test_cli.py` (modify) | Tests |
| `Routing/web/README.md`, `Routing/README.md`, `Routing/fidelity/README.md`, `Routing/docs/DESIGN_ROUTING_LAB.md` (modify) | Documents |

## Review Focus

The inputs most likely to bite. Each has its test in the task named.

1. **A wrong port picked.** The four ports look alike to the page. A port that does not answer `N` with a net list gets that one byte and no more, is closed, and its grant is given back (`port.forget()`), so the page never opens it again without the picker. The page says which port to pick before the picker opens, and what opening the wrong one can do (Task 4, Task 5).
2. **A board that does not answer.** In probe mode, a menu or an app the main loop does not run. The page waits, says so in words, keeps the last picture with the time it was read, and sends nothing more. It is not red. When the board answers, the loop goes on (Task 4, Task 5).
3. **The report and the dump are two questions.** A rebuild between them would read as "planned but not sent", in red, on a board with no fault. So `:gen` is asked again after the dump, and a pair is a reading only when both answers say idle with the same number. In the firmware a sense tap must not be in the dump: `:crossbar` waits for the second core and copies again while `core2busy` is up. FakeGPIO's writes are not covered (notes B4) (Task 1, Task 4, Task 6).
4. **Firmware that is too old.** `:gen` or `:paths` answered `unknown_verb`. The page says the version it found and what is needed, closes the port, and sends nothing in their place. It is not red (Task 4, Task 5; seen on the board before the flash in Task 6).
5. **A reply cut short.** A read error, or a board that stopped mid-line. A reply that began and then stood still for `STALL_MS` is thrown away and asked once more. This is the only time a query is sent twice (Task 4).
6. **Bytes nobody asked for.** The echo of every `:` line; an OLED stream another tool left on. Each reader finds its own reply by its shape and ignores the rest: `gen{` is not in the echo `:gen`. The page never switches the stream off: that is another tool's state (Task 3, Task 4).
7. **A page that stops reading.** The board's write has no timeout. One query at a time and a read buffer of 65,536 bytes mean the board never waits on the page, even with the tab's script stopped: the largest report captured is 4,046 bytes (Task 4).
8. **A redraw under the user's hands.** A new reading must not move a view, undock one, drop the lit net, or pull the user off another case they are looking at. A reading that arrives during a Run is kept and shown after (Task 5).
9. **The port held elsewhere, pulled out, plugged back.** Another tab or tool on port 7 is said in words. A pulled cable ends the link cleanly; connecting again is a click (Task 4, Task 5).
10. **No byte but the five.** The link refuses to write anything not in `BOARD_PORT.SENDS`, a test holds every write of a whole session to those five, and `lab.js` never takes the port's writer. In the firmware `:paths` must not reach `couldntFindPath`, and must put no colour code on port 1 (Task 1, Task 4, Task 5, Task 6).
11. **A board with nothing on it.** A cleared board may print a report with no bridge, which a pasted report is refused for. For a linked board that is a case with nothing on it, and "what changed" lists everything opened (Task 2, Task 6).
12. **A port remembered from last time.** A grant kept by the browser is opened before it can be proved, and opening is itself what resets an Arduino on the wrong port. JumperIDE finds several ports of one board among its grants, and not always the same object after a replug (`JumperIDE/src/app.js:4374-4377`, `:4402-4406`). The page uses a remembered port only when it holds exactly one; with more it opens the picker (Task 5, Task 6).
13. **A change the counter did not count.** The notes do not establish that every change to the table moves `routingGeneration`. "read again" asks for the pair whatever the number says (Task 4, Task 5).

---

### Task 1: The firmware's three calls

Done in a JumperlOS worktree, not in Jimulator and not in `~/Documents/GitHub/JumperlOS`. The reading behind it is notes A6 and B4 and their table of proposed additions (rows 1 to 3).

**Files** (in the worktree `~/Documents/GitHub/JumperlOS-port7`, branch `port7-routing-reads`):
- Modify: `src/tubes/Ser3Backchannel.cpp`, `src/tubes/Ser3Backchannel.h` (the VERBS comment), `test/hil/run_all.py`, `test/hil/README.md`
- Create: `test/hil/test_port7_reads.py`

**Interfaces:**
- Consumes: `routingGeneration` (`routing/RouteSafety.h`), `core1req::allIdle()` (`coredination/CoreMailbox.h`), `printBridgeArray(Stream*)` (`routing/NetManager.h`), `printPathsCompact(int, Stream*)` and `printChipStatus(Stream*)` (`routing/NetsToChipConnections.h`), `disableTerminalColors` (`Graphics.h`), `waitCore2()` (`Commands.h`), `core2busy` (`coredination/externVars.h`), `lastChipXY` (`CH446Q.h`).
- Produces, on port 7. Each reply follows the echo of its line. All three land in one commit, because the page takes an answer to `:gen` as proof of all three.
  - `:gen` prints `gen{<n>,<i>}\r\n`: `<n>` is `routingGeneration` in decimal, `<i>` is `1` when `core1req::allIdle()` and `0` when not. **Why it changes nothing:** two reads.
  - `:paths` prints `b`'s three blocks under `b`'s headings and nothing before them: `\n\rBridge Array\n\r`, `printBridgeArray(out)`, `\n\n\n\rPaths\n\r`, `printPathsCompact(1, out)`, `\n\n\rChip Status\n\r`, `printChipStatus(out)`, `\n\n\r`. `disableTerminalColors` is set true around the three and put back. **Why it changes nothing:** the three functions read `globalState.connections` and write to `out`. It does not call `couldntFindPath`, so no line goes to port 1 and no path is marked. Colours are off because `changeTerminalColor` ignores its stream and writes its codes to port 1 (`Graphics.cpp:447-470`). One write remains: `assignTermColor()` inside `printPathsCompact` rewrites each net's terminal colour, as every refresh does (notes A2).
  - `:crossbar` prints what it prints today. Before the copy it calls `waitCore2()`; after it, it reads `core2busy`, and when that is up it waits and copies again, four times at most, then sends the last copy. **Why the dump is free of taps:** a tap raises `core2busy` before its first crosspoint and lowers it after its last is opened (`sensing/NetVoltageScan.cpp:1476-1486`), and holds it about a millisecond (notes B1). **Why it changes nothing:** `waitCore2()` only waits (25 ms at most, pumping USB: `Commands.cpp:116-150`), then a `memcpy` and one read.
  - `usbSer3_verbs[]` gains `{ "gen", "Routing generation, and whether core 2 is idle", "", "gen{<n>,<0|1>}", ":gen", 50 }` and `{ "paths", "Bridge array, path table, chip status (b's three blocks, no side effects)", "", "text", ":paths", 6000 }`. The floors are `ver`'s and `yaml`'s, not measured.
  - `usbSer3_dispatchVerb` gains `head == "gen"` and `head == "paths"`, before the single-character passthrough.

```cpp
static void usbSer3_sendGen(Stream* out) {
    out->printf("gen{%lu,%d}\r\n", (unsigned long)routingGeneration, core1req::allIdle() ? 1 : 0);
}

static void usbSer3_sendPaths(Stream* out) {
    bool was = disableTerminalColors;
    disableTerminalColors = true;      // changeTerminalColor ignores its stream and writes to port 1
    out->print("\n\rBridge Array\n\r");
    printBridgeArray(out);
    out->print("\n\n\n\rPaths\n\r");
    printPathsCompact(1, out);
    out->print("\n\n\rChip Status\n\r");
    printChipStatus(out);
    out->print("\n\n\r");
    disableTerminalColors = was;
}

// in usbSer3_sendCrossbar, in place of its one memcpy:
    for (int i = 0; i < 4; i++) {      // a sense tap is in the shadow for about 1 ms and raises core2busy
        waitCore2();
        memcpy(snap, lastChipXY, sizeof(snap));
        if (!core2busy) break;
    }
```

- [ ] **Step 1: Make the worktree.** `git -C ~/Documents/GitHub/JumperlOS fetch origin`, then `git -C ~/Documents/GitHub/JumperlOS worktree add ~/Documents/GitHub/JumperlOS-port7 -b port7-routing-reads origin/main`, then `git -C ~/Documents/GitHub/JumperlOS-port7 submodule update --init`. None of the three changes a file in the main checkout's working tree. Every later step of this task runs in the worktree.
- [ ] **Step 2: Write the bench checks,** `test/hil/test_port7_reads.py`, in the suite's own way (`check`, `finish`, `jl_exec`, `port1_command` from `jl`; `port7_command` from `port7`; `routing_check as rc`; the board left as found with `jl.board_state_capture` and `jl.board_state_restore`). List it in `run_all.py` after `test_routing_dense.py`, with a row in the README's table. Its checks:
  1. `:gen` twice on a still board: both match `gen\{(\d+),1\}` with the same number.
  2. `:paths` holds "Bridge Array", "Paths" and "Chip Status" in that order, twelve chip rows, no `\x1b`, no "Duplicates:" and no "Couldn't find". `rc.parse_bridge_array`, `rc.parse_paths` and `rc.parse_chip_status` read it.
  3. It is `b`'s report: `rc.parse_bridge_array` and `rc.parse_paths` give the same for `:paths` as for `port1_command("b", ...)` taken right after.
  4. After `jl_exec("connect(1, 2)")` the number of `:gen` is another, and within a second it reads idle. `:paths` then lists the bridge 1 to 2.
  5. With the net scan left on (skipped, saying so, when `/config.txt` has it off): 100 rounds of `:gen`, `:paths`, `:crossbar`, `:gen`. In every round whose two `:gen` agree and say idle, `rc.check_sent_matches_planned(rc.crosspoints_from_paths(rows), rc.crosspoints_from_xbar(dump), verdict)` finds nothing. At least 90 rounds count.
  6. Port 1, opened and read for the whole of 20 rounds of the three calls, receives no byte.
- [ ] **Step 3: No run here shows it fail.** The file needs a board. Its failing run is Task 6 Step 1, on the board's firmware as it is before the flash: `unknown_verb` at check 1. Here, `python3 -m py_compile test/hil/test_port7_reads.py` passes.
- [ ] **Step 4: Implement** the three as written under Interfaces, with the verb table's two rows, the two branches, and the three lines in the header's VERBS comment.
- [ ] **Step 5: Build both targets:** `pio run -e jumperless_v5 -e jumperless_og`. On Kevin's Mac `pio` under the system Python is broken: make a throwaway venv first (`python3.13 -m venv <scratch>/pio313`, `<scratch>/pio313/bin/pip -q install platformio==6.1.19`) and run its `pio`. Expected: both succeed. Then `test/test_routing_og/run.sh` passes, and `git diff --stat origin/main` names only this task's files and the tracked `.pio/build/jumperless_v5/firmware.uf2`, which the build rewrote.
- [ ] **Step 6: Commit** on the branch, this task's files staged by name: `Port 7: :gen, :paths, and a :crossbar that waits out a sense tap`. The `firmware.uf2` is not staged. Not pushed. Tell Kevin the branch and the commit.

---

### Task 2: What changed between two readings

**Files:**
- Modify: `Routing/board.py`, `Routing/server.py`, `Routing/tests/test_board.py`, `Routing/tests/test_server.py`

**Interfaces:**
- Consumes: `board.result`, `copper.paint`, `Handler.keep`, `api_post_board`.
- Produces:
  - `board.result(name, text, about="", live=False)`: `about` is the result's `about` (the case's notes). With `live`, a whole report (all twelve chips) whose Bridge Array lists no bridge is a result of status `"empty"` with the note "nothing is connected on the board"; without `live` it is refused as before. The dump in the text is used as it is today: a live reading always carries one, so its "sent equals planned" is the judge's.
  - `board.changed(before, after) -> dict | None`: `None` when `before` is `None`. Else `{"closed": [[chip, x, y, net], ...], "opened": [[chip, x, y, net], ...], "bridges": [{"n1", "n2", "was", "now"}, ...]}`, each list sorted. A crosspoint is told by its place (chip, x, y), not its net: a net that only got another number is no change. `closed` carries the net of `after`, `opened` the net of `before`. A bridge is told by its two nodes in either order; it is listed when its state differs, `was` or `now` being `None` when it is not there.
  - `POST /api/board {"name", "text", "about": str (optional), "live": bool (optional)}`: the answer is as before, with `"changed"`: `board.changed(the case of that name as it was kept, the new result)`. A wrong type for `about` or `live` is 400 with the reason.

- [ ] **Step 1: Write the failing tests**

```python
class Changed(unittest.TestCase):                                      # test_board.py
    def test_what_two_readings_of_a_board_differ_by(self):
        a, b = board.result("live_board", capture("same_chip_pairs")), board.result("live_board", capture("sf_to_sf"))
        c = board.changed(a, b)
        self.assertEqual((len(c["closed"]), len(c["opened"]), len(c["bridges"])), (32, 16, 14))    # measured 2026-11-23
        self.assertIn({"n1": 1, "n2": 2, "was": "routed", "now": None}, c["bridges"])
        self.assertNotIn(139, [n for x in c["bridges"] for n in (x["n1"], x["n2"])])    # the feed: in both, routed in both
        self.assertEqual(board.changed(a, a), {"closed": [], "opened": [], "bridges": []})
        self.assertIsNone(board.changed(None, a))

    def test_a_bridge_that_stopped_routing_is_a_change(self):
        a, b = board.result("x", capture("same_chip_pairs")), board.result("x", capture("k_rows_overflow_metric"))
        self.assertIn({"n1": 139, "n2": 136, "was": "routed", "now": "unrouted"}, board.changed(a, b)["bridges"])

    def test_a_net_that_only_got_another_number_is_no_change(self):
        one = {"crosspoints": [{"chip": "A", "x": 3, "y": 1, "net": 6}], "bridges": [{"n1": 1, "n2": 2, "state": "routed"}]}
        two = {"crosspoints": [{"chip": "A", "x": 3, "y": 1, "net": 7}], "bridges": [{"n1": 2, "n2": 1, "state": "routed"}]}
        with mock.patch.object(copper, "paint", side_effect=[one, two]):
            self.assertEqual(board.changed({}, {}), {"closed": [], "opened": [], "bridges": []})

    def test_what_port_7_prints_is_read_and_its_dump_checked(self):
        text = capture("same_chip_pairs", crossbar=False)
        reply = ":paths\r\n\n\r" + text[text.index("Bridge Array"):]              # :paths: no settings lines, an echo first
        r = board.result("live_board", reply + xbar("same_chip_pairs"), about="a V5 on port 7")
        self.assertEqual((r["about"], r["status"], r["problems"]), ("a V5 on port 7", "ok", []))
        self.assertFalse([n for n in r["notes"] if "sent equals planned" in n])
        other = board.result("live_board", reply + xbar("sf_to_sf"))             # another routing's dump: a fault, said
        self.assertTrue(any("PLANNED but not SENT" in p for p in other["problems"]))

    def test_a_linked_board_with_nothing_on_it_is_an_empty_case(self):     # Review Focus 11
        bare = cleared(capture("same_chip_pairs", crossbar=False))
        with self.assertRaisesRegex(ValueError, "lists no bridge"):
            board.result("pasted", bare)                                  # a pasted report: as before
        r = board.result("live_board", bare, live=True)
        self.assertEqual((r["status"], r["problems"], copper.paint(r)["crosspoints"]), ("empty", [], []))
        c = board.changed(board.result("live_board", capture("same_chip_pairs")), r)
        self.assertEqual((len(c["closed"]), len(c["opened"]), len(c["bridges"])), (0, 16, 7))
        with self.assertRaises(ValueError):
            board.result("live_board", bare.split("Chip Status")[0], live=True)     # half a report is still refused
```

`cleared` and `xbar` are new in `test_board.py` (which also needs `from unittest import mock`). `cleared` was tried on the captures on 2026-11-23: it leaves no bridge, no path row and twelve chip rows.

```python
def xbar(name):
    return (CAPTURES / (name + ".xbar.txt")).read_text()


def cleared(text):
    """A capture made to read as a board with nothing connected: no bridge, no path row, every pin free."""
    text = re.sub(r"\d+ *\[[^\]]*\],?", "", text)
    text = re.sub(r"(?m)^\d+\t.*\n", "", text)
    text = re.sub(r"numberOfPaths: \d+", "numberOfPaths: 0", text)
    return re.sub(r"(?m)^([A-L])\t.*$", lambda m: m.group(1) + "\t" + ". " * 16 + "\t" + ". " * 8, text)
```

In `test_server.py`, beside `test_board_output_is_judged_kept_and_served_like_a_run`:

```python
    def test_a_board_read_again_says_what_changed(self):
        captures = server.lab.FIDELITY_DIR / "board_0621e4f44e23"
        text = lambda n: (captures / (n + ".b.txt")).read_text(errors="replace") + (captures / (n + ".xbar.txt")).read_text()
        first = self.c.post("/api/board", {"name": "live_board", "text": text("same_chip_pairs"), "about": "a V5 on port 7"}).json
        self.assertIsNone(first["changed"])
        again = self.c.post("/api/board", {"name": "live_board", "text": text("sf_to_sf"), "live": True}).json
        self.assertEqual((len(again["changed"]["closed"]), len(again["changed"]["opened"])), (32, 16))
        self.assertEqual(len([x for x in again["rows"] if x["case"] == "live_board"]), 1)      # the same case, read again
        same = self.c.post("/api/board", {"name": "live_board", "text": text("sf_to_sf")}).json
        self.assertEqual(same["changed"], {"closed": [], "opened": [], "bridges": []})
        for bad in ({"about": 5}, {"live": 1}):
            r = self.c.post("/api/board", dict({"name": "x", "text": text("sf_to_sf")}, **bad))
            self.assertEqual(r.status, 400, bad)
```

- [ ] **Step 2: Run** `python3 -m unittest discover -s Routing/tests -t Routing -k Changed -k read_again`. Expected: `board` has no `changed`; `result` takes no `about`.
- [ ] **Step 3: Implement.** `changed` is two calls of `copper.paint` and three set differences. In `api_post_board`, read the kept case before `keep` replaces it.
- [ ] **Step 4: Run all tests.** Expected: pass.
- [ ] **Step 5: Commit** `Routing lab: what changed between two readings of a board, and a linked board with nothing on it`.

---

### Task 3: The board's replies, read, and a fake port

**Files:**
- Create: `Routing/web/board_port.js`, `Routing/tests/board_port_test.js`, `Routing/tests/test_board_port.py`, `Routing/tests/fixtures/port7_built.jsonl`

**Interfaces:**
- Consumes: the reply shapes of Task 1 and of "Measured"; the 21 captures.
- Produces, in `board_port.js`. It is a plain script with no DOM and no import. In the page it defines globals. Under `node` its last line exports them: `if (typeof module !== "undefined") module.exports = {...}`.
  - `BOARD_PORT`: `{FILTER: {usbVendorId: 0x1D50, usbProductId: 0xACAB}, BAUD: 115200, BUFFER: 65536, SENDS: ["N", ":ver\n", ":gen\n", ":paths\n", ":crossbar\n"], POLL_MS: 500, PROBE_MS: 1500, STALL_MS: 3000, WAIT_SAY_MS: 1500, NEEDS: "a JumperlOS release after 5.7.11.5 (not out when this was written)"}`. The ids are `usb_descriptors.cpp:71-72`; the speed, `ArduinoStuff.cpp:212`; the buffer, `lineChannel.ts:21`; `POLL_MS` is the design's; `PROBE_MS` is Jumperlessim's probe (`engine.ts:31`). `STALL_MS` and `WAIT_SAY_MS` are first guesses and Task 6 may set them. `NEEDS` is set in Task 7.
  - `serialWhyNot(nav, secure) -> string | null`: `null` when Web Serial can be used. Without `nav.serial`: "This browser has no Web Serial. Chrome, Edge, Opera and Brave have it. Paste or drop the board's b output here." When `secure` is false: "Web Serial needs a page served over https, or from 127.0.0.1."
  - `netListIn(text) -> boolean`: true when the text holds a whole JSON object with a `"nets"` list. The proof of port 7.
  - `versionOf(text) -> string | null`: the X of `firmware version: X`, once its line has ended.
  - `genOf(text) -> {n: number, idle: boolean} | null`: the last `gen{<digits>,<0|1>}` in the text.
  - `refusedVerb(text) -> string | null`: the verb of `{"error":"unknown_verb","verb":"..."}`; `null` when there is none.
  - `xbarOf(text) -> string | null`: the last `xbar{12x8:` with its 384 hex digits and `}`, as it stands; `null` when not all of it is there.
  - `reportOf(text) -> string | null`: the text up to the end of chip L's status row, when the text holds "Bridge Array", "Chip Status" after it and twelve chip rows after that, the twelfth ended by a line end. `null` before.
  - **The trace**, JSON Lines. Line 1: `{"h": 1, "what": "routing lab port 7 trace", "source": "board" | "built", "fw": text or null, "about": text}`. Then one line an exchange, in order: `{"t": seconds since the first, "sent": one of SENDS, "got": every byte received from when the reply before it was whole until this one was, or null when none came}`. So bytes nobody asked for are in the `got` of the exchange after them. A run of exchanges with the same `sent` and `got`, one after another, is one line with `"times": how many` and the `t` of the first, so a still board's polls cost one line. Bytes left after the last whole reply (at a close, or a pulled cable) are a last line with `"sent": null`, which `FakePort` does not replay. So no byte is left out.
  - `class FakePort`: `new FakePort(traceText, {gapMs: 1})`. It has what a `SerialPort` has that the link uses: `readable`, `writable`, `open(options)`, `close()`, `getInfo()` (the ids of `FILTER`), `forget()`. A write is answered by the next exchange at or after its place in the trace whose `sent` is what was written, and the place moves past it; a line with `times` answers that many writes. When there is none ahead, the last one behind answers. A `got` of `null` is no answer. For the tests: `written` (every write, in order), `opened` (the options `open` got), `closed`, `forgotten`, `most` (the most writes ever unanswered at once), `hush()` and `speak()` (stop answering; start again, and answer a write that was left waiting), `cut(n)` (the next answer stops after `n` characters and its exchange is not used up), `add(text)` (bytes nobody asked for), `pull()` (the cable out: `readable` ends).
- `tests/fixtures/port7_built.jsonl`: the exchanges a link makes with a board that goes through four routings (`same_chip_pairs`, `sf_to_sf`, `k_rows_overflow_metric`, `same_chip_pairs` again) at generations 3, 5, 7 and 9. Connecting: `N`, `:ver\n` answered `:ver\r\nJumperless firmware version: 0.0.0.0\r\n`, `:gen\n` answered `:gen\r\ngen{3,1}\r\n`. Then for each routing at generation G: for all but the first, `:gen\n` answered `gen{G-1,0}` (the rebuild begun, the send still to come); `:gen\n` answered `gen{G,1}`; `:paths\n`; `:crossbar\n`; `:gen\n` answered `gen{G,1}` four times. The `:crossbar` answers are the captures' `.xbar.txt` as they are. The `:paths` answers are what Task 1's `:paths` would print: `:paths\r\n\n\r`, then the capture's `.b.txt` from "Bridge Array" on. The captures are read as bytes, so the board's own line ends stay (`Path.read_text` turns `\r\n` and `\r` into `\n`, and the node tests read them raw). The `N` answer and every `:gen` answer are made up, because none was ever captured. Its header says `"source": "built"` and says all of that in `about`.
- `tests/test_board_port.py`: `built_trace(names) -> str` makes that file's text; one test holds the file to it; one runs `node tests/board_port_test.js CAPTURES TRACE` and wants exit 0, showing the output when it is not.

- [ ] **Step 1: Write the failing tests.** `tests/board_port_test.js`:

```js
"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const P = require("../web/board_port.js");
const [CAPTURES, TRACE] = process.argv.slice(2);
const cap = (name, ext) => fs.readFileSync(path.join(CAPTURES, name + ext), "utf8");
const tests = [];
const test = (name, fn) => tests.push([name, fn]);
const NETS = '{\r\n  "nets": [\r\n    {\r\n      "index": 6,\r\n      "name": "Net 6",\r\n      "nodes": ["1", "2"],\r\n'
  + '      "special": "",\r\n      "voltage": 1.203\r\n    }\r\n  ]\r\n}\r\n';
const refused = (verb) => ":" + verb + '\r\n{"error":"unknown_verb","verb":"' + verb + '"}\r\n';
const pathsReply = (name) => ":paths\r\n\n\r" + cap(name, ".b.txt").slice(cap(name, ".b.txt").indexOf("Bridge Array"));

test("the crossbar dump is found whatever stands around it", () => {            // Review Focus 6
  const reply = cap("same_chip_pairs", ".xbar.txt");                            // the echoed ":crossbar", then the dump
  assert.match(P.xbarOf(reply), /^xbar\{12x8:[0-9a-f]{384}\}$/);
  assert.equal(P.xbarOf(reply.slice(0, 200)), null);
  assert.equal(P.xbarOf("oled_b64{128x32:AAAA}\r\n" + reply), P.xbarOf(reply));
});

test("a report is whole when chip L's row has ended, and not before", () => {
  const files = fs.readdirSync(CAPTURES).filter((f) => f.endsWith(".b.txt"));
  assert.equal(files.length, 21);
  for (const file of files) {
    const text = pathsReply(file.slice(0, -6));
    const whole = P.reportOf(text);
    assert.ok(whole && whole.includes("Bridge Array") && whole.includes("Chip Status"), file);
    assert.equal(P.reportOf(text.slice(0, text.lastIndexOf("\nL") + 20)), null, file);      // inside the last row
    assert.equal(P.reportOf(text.slice(0, text.indexOf("Chip Status"))), null, file);
  }
});

test("the generation, and a board too old to give it", () => {                  // Review Focus 4, 6
  assert.deepEqual(P.genOf(":gen\r\ngen{12,1}\r\n"), { n: 12, idle: true });
  assert.deepEqual(P.genOf("gen{4294967295,0}\r\n"), { n: 4294967295, idle: false });
  assert.equal(P.genOf(":gen\r\n"), null);                                      // the echo alone
  assert.equal(P.genOf(":gen\r\ngen{12,"), null);
  assert.deepEqual(P.genOf("oled_b64{128x32:AAAA}\r\n:gen\r\ngen{4,0}\r\n"), { n: 4, idle: false });
  assert.equal(P.refusedVerb(refused("gen")), "gen");
  assert.equal(P.refusedVerb(":gen\r\ngen{12,1}\r\n"), null);
  assert.equal(P.refusedVerb('{"error":"blocked","cmd":"!","reason":"not_a_command"}\r\n'), null);
});

test("a net list proves port 7, and the main port's menu does not", () => {     // Review Focus 1
  assert.equal(P.netListIn(NETS), true);
  assert.equal(P.netListIn(NETS.slice(0, 60)), false);                          // not all of it yet
  assert.equal(P.netListIn('{"nets":[]}\r\n'), true);
  assert.equal(P.netListIn("\r\n\tMenu\r\n\tm = show this menu\r\n"), false);   // the main port's answer to N
  assert.equal(P.netListIn("oled_b64{128x32:AAAA}\r\n" + NETS), true);
  assert.equal(P.versionOf(":ver\r\nJumperless firmware version: 5.7.11.5\r\n"), "5.7.11.5");
  assert.equal(P.versionOf(":ver\r\nJumperless firmware ver"), null);
  assert.deepEqual(P.BOARD_PORT.SENDS, ["N", ":ver\n", ":gen\n", ":paths\n", ":crossbar\n"]);
});

test("why this browser cannot connect, in words", () => {
  assert.equal(P.serialWhyNot({ serial: {} }, true), null);
  assert.match(P.serialWhyNot({}, true), /Chrome/);
  assert.match(P.serialWhyNot({ serial: {} }, false), /127\.0\.0\.1/);
});

test("the fake port answers from the trace, in order, and then repeats", async () => {
  const port = new P.FakePort(fs.readFileSync(TRACE, "utf8"));
  await port.open({ baudRate: 115200, bufferSize: 65536 });
  const ask = async (text, done) => {
    const w = port.writable.getWriter(), r = port.readable.getReader();
    await w.write(new TextEncoder().encode(text));
    let got = "";
    while (done(got) == null) got += new TextDecoder().decode((await r.read()).value);
    w.releaseLock(); r.releaseLock();
    return done(got);
  };
  const gen = () => ask(":gen\n", P.genOf);
  assert.equal(await ask("N", (t) => P.netListIn(t) || null), true);
  assert.equal(await ask(":ver\n", P.versionOf), "0.0.0.0");
  assert.deepEqual([(await gen()).n, (await gen()).n], [3, 3]);                 // connecting, then the first round
  assert.equal(await ask(":paths\n", P.reportOf), P.reportOf(pathsReply("same_chip_pairs")));
  assert.equal(await ask(":crossbar\n", P.xbarOf), P.xbarOf(cap("same_chip_pairs", ".xbar.txt")));
  for (let i = 0; i < 4; i++) assert.deepEqual(await gen(), { n: 3, idle: true });      // one line, four times
  assert.deepEqual(await gen(), { n: 4, idle: false });                         // the second routing, on its way
  for (let i = 0; i < 60; i++) await gen();                                     // past the end: the last answer again
  assert.deepEqual(await gen(), { n: 9, idle: true });
  assert.equal(await ask(":crossbar\n", P.xbarOf), P.xbarOf(cap("same_chip_pairs", ".xbar.txt")));
  assert.deepEqual([port.most, port.opened.baudRate], [1, 115200]);
});

(async () => {
  for (const [name, fn] of tests) {
    try { await fn(); } catch (e) { console.log("FAIL " + name + "\n" + (e.stack || e)); process.exitCode = 1; }
  }
  console.log(tests.length + " tests");
})();
```

`tests/test_board_port.py`:

```python
class Port(unittest.TestCase):
    def test_the_built_trace_is_what_the_captures_give(self):
        self.assertEqual(TRACE.read_text(), built_trace(["same_chip_pairs", "sf_to_sf", "k_rows_overflow_metric", "same_chip_pairs"]))
        lines = [json.loads(line) for line in TRACE.read_text().splitlines()]
        self.assertEqual((lines[0]["h"], lines[0]["source"]), (1, "built"))
        self.assertEqual({e["sent"] for e in lines[1:]}, {"N", ":ver\n", ":gen\n", ":paths\n", ":crossbar\n"})

    def test_the_port_code_under_node(self):
        p = subprocess.run(["node", str(HERE / "board_port_test.js"), str(CAPTURES), str(TRACE)], capture_output=True, text=True,
                           timeout=120)                   # a link that waits for ever is a failed test, not a hung suite
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(subprocess.run(["node", "--check", str(server.WEB_DIR / "board_port.js")]).returncode, 0)
```

- [ ] **Step 2: Run** `python3 -m unittest discover -s Routing/tests -t Routing -k test_board_port`. Expected: no `board_port.js`, no fixture.
- [ ] **Step 3: Implement.** The readers first, then `FakePort`, then `built_trace` and the fixture it writes.
- [ ] **Step 4: Run all tests.** Expected: pass.
- [ ] **Step 5: Commit** `Routing lab: a board's port 7 replies read in the page's own code, and a fake port that replays a trace`.

---

### Task 4: The link: prove the port, then ask, one query at a time

**Files:**
- Modify: `Routing/web/board_port.js`, `Routing/tests/board_port_test.js`

**Interfaces:**
- Consumes: Task 3's readers, `FakePort`, the trace.
- Produces:
  - `new BoardLink(port, on, opts)`. `on` is `{reading(r), state(name, words)}`. `opts` may override any timing of `BOARD_PORT` (the tests run with a few milliseconds each).
  - `await link.connect() -> {fw}`: opens the port (`{baudRate: BAUD, bufferSize: BUFFER}`), starts the one reader, sends `N`. With a net list back inside `PROBE_MS` it asks `:ver\n` and reads `fw` (`null` when the board answers that verb with its JSON error), then asks `:gen\n`. It throws `LinkError` with `.kind`:
    - `"busy"`: `open` failed with `NetworkError`. Nothing was sent.
    - `"not_port_7"`: no net list came. Exactly one byte was sent. The port is closed before the throw.
    - `"too_old"`: `:gen` was answered `unknown_verb`. `.fw` is the version. The port is closed before the throw. Nothing was sent but `N`, `:ver\n` and `:gen\n`.
    - `"gone"`: the port ended.
  - `await link.run()`: the loop below, until `close()`, the port ends, or `:paths` is answered `unknown_verb` (state `"too_old"`, the port closed). It never throws.
  - `link.again()`: the next round reads the report and the dump whatever the number says.
  - `await link.close()`: stops the loop, lets go of the reader and the writer, closes the port.
  - `link.trace() -> string`: the header and every exchange since `connect`, as Task 3's format, `"source": "board"`.
  - A reading: `{n: count from 1, gen: the generation it was read at, b: the report's text, xbar: "xbar{12x8:...}", fw, at: ms since 1970}`.
  - States, each with words for the page: `"probing"`, `"live"`, `"waiting"`, `"too_old"`, `"lost"` ("the board is gone: unplugged, or the port was closed"). `"live"` is given with every reading, and when an answer comes after `"waiting"` was said. `"waiting"` has two sentences. A board that does not answer: "the board has not answered for N s. It answers port 7 from its main loop only: not in probe mode, a menu or an app. Last read HH:MM:SS." A number that moved on a board not idle for `WAIT_SAY_MS`: "the board's routing changed and it has not finished sending it. Last read HH:MM:SS."

**The loop (binding).** It keeps `shown`: the generation of the last reading given, or `null`.

1. Ask `:gen\n` for `g`.
2. If `g.idle`, and `g.n` is not `shown` or `again()` was called: ask `:paths\n` for the report, `:crossbar\n` for the dump, and `:gen\n` for `h`. If `h.idle` and `h.n` is `g.n`: give a reading of the two with `gen: g.n`, and set `shown`. Else give nothing, take `h` as `g`, and do this step again.
3. Wait `POLL_MS`. Go to 1.

"Not `shown`" is "not equal", never "greater": the counter goes up twice a rebuild and restarts at 1 on boot.

**Asking (binding).** One query is out at a time, and the link refuses to write anything not in `BOARD_PORT.SENDS`. Its reply is whatever the reader for it (`netListIn`, `versionOf`, `genOf`, `reportOf`, `xbarOf`) first finds in the text received since it was sent, or, for `:gen\n` and `:paths\n`, a `refusedVerb` naming that verb. Bytes that come while nothing is out are no part of any reply; the trace keeps them. The probe is the one query with a limit, and it is never sent twice: no net list in `PROBE_MS` means it is not port 7. Every other query is waited for without end: while one is out and no byte has come for `WAIT_SAY_MS`, the state is `"waiting"`, and nothing is sent. A reply that began and then got no byte for `STALL_MS` is thrown away and the same query sent once more; if that one stops short too, it is waited for as a silent board is. A read error is not the end: the reader is taken again from `port.readable` (as `lineChannel.ts:29-46` does); only a `readable` that is gone is `"lost"`.

- [ ] **Step 1: Write the failing tests** in `board_port_test.js`. A helper makes a link on a `FakePort` with fast clocks and collects what it gives:

```js
const FAST = { POLL_MS: 4, PROBE_MS: 80, STALL_MS: 60, WAIT_SAY_MS: 30 };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function linked(port, opts) {
  const seen = { readings: [], states: [] };
  const link = new P.BoardLink(port, { reading: (r) => seen.readings.push(r), state: (name, words) => seen.states.push([name, words]) },
    Object.assign({}, FAST, opts));
  return [link, seen];
}
const built = () => new P.FakePort(fs.readFileSync(TRACE, "utf8"));
const HEAD = '{"h":1,"what":"routing lab port 7 trace","source":"built","fw":null,"about":"made in a test"}\n';
const made = (steps) => new P.FakePort(HEAD + steps.map((s, i) => JSON.stringify(Object.assign({ t: i }, s))).join("\n") + "\n");
const N = { sent: "N", got: NETS };
const VER = { sent: ":ver\n", got: ":ver\r\nJumperless firmware version: 0.0.0.0\r\n" };
const gen = (n, idle, times) => ({ sent: ":gen\n", got: ":gen\r\ngen{" + n + "," + idle + "}\r\n", times: times || 1 });
const paths = (name) => ({ sent: ":paths\n", got: pathsReply(name) });
const dump = (name) => ({ sent: ":crossbar\n", got: cap(name, ".xbar.txt") });
const xbarOfCase = (name) => P.xbarOf(cap(name, ".xbar.txt"));

test("a port that is not port 7 gets one byte and is closed", async () => {     // Review Focus 1
  const port = made([{ sent: "N", got: "\r\n\tMenu\r\n\tm = show this menu\r\n" }]);
  await assert.rejects(linked(port)[0].connect(), (e) => e.kind === "not_port_7");
  assert.deepEqual([port.written, port.closed], [["N"], true]);
  const held = made([N]);
  held.open = async () => { throw Object.assign(new Error("Failed to open serial port."), { name: "NetworkError" }); };
  await assert.rejects(linked(held)[0].connect(), (e) => e.kind === "busy");
  assert.deepEqual(held.written, []);
});

test("firmware without :gen or :paths is too old, and nothing is sent in their place", async () => {   // Review Focus 4
  const old = made([N, VER, { sent: ":gen\n", got: refused("gen") }]);
  await assert.rejects(linked(old)[0].connect(), (e) => e.kind === "too_old" && e.fw === "0.0.0.0");
  assert.deepEqual([old.written, old.closed], [["N", ":ver\n", ":gen\n"], true]);
  const half = made([N, VER, gen(3, 1, 2), { sent: ":paths\n", got: refused("paths") }]);
  const [link, seen] = linked(half);
  await link.connect();
  await link.run();                                                             // it ends by itself
  assert.equal(seen.states.at(-1)[0], "too_old");
  assert.deepEqual([half.written, seen.readings, half.closed], [["N", ":ver\n", ":gen\n", ":gen\n", ":paths\n"], [], true]);
});

test("a still board is asked its generation and nothing else", async () => {    // Review Focus 7, 10
  const port = built();
  const [link, seen] = linked(port);
  assert.deepEqual(await link.connect(), { fw: "0.0.0.0" });
  assert.deepEqual(port.written, ["N", ":ver\n", ":gen\n"]);
  link.run();
  while (seen.readings.length < 4) await sleep(5);
  await sleep(60);                                                              // many polls of a board that stands
  await link.close();
  assert.deepEqual(seen.readings.map((r) => r.gen), [3, 5, 7, 9]);
  assert.deepEqual(seen.readings.map((r) => r.xbar),
    ["same_chip_pairs", "sf_to_sf", "k_rows_overflow_metric", "same_chip_pairs"].map(xbarOfCase));
  assert.ok(seen.readings.every((r) => P.reportOf(r.b)));
  assert.equal(port.written.filter((w) => w === ":paths\n").length, 4);         // one report a routing, not one a tick
  assert.deepEqual([...new Set(port.written)].sort(), P.BOARD_PORT.SENDS.slice().sort());      // the five, and no other byte
  assert.equal(port.most, 1);                                                   // never two queries out
});

test("a routing that moved between the report and the dump is read again", async () => {   // Review Focus 3
  const port = made([N, VER, gen(3, 1, 2), paths("same_chip_pairs"), dump("sf_to_sf"), gen(5, 1),
    paths("sf_to_sf"), dump("sf_to_sf"), gen(5, 1, 3)]);
  const [link, seen] = linked(port);
  await link.connect();
  link.run();
  while (seen.readings.length < 1) await sleep(5);
  await sleep(40);
  await link.close();
  assert.deepEqual(seen.readings.map((r) => [r.gen, r.xbar]), [[5, xbarOfCase("sf_to_sf")]]);
  assert.equal(port.written.filter((w) => w === ":paths\n").length, 2);
});

test("a silent board is waited for, not asked again", async () => {             // Review Focus 2
  const port = built();
  const [link, seen] = linked(port);
  await link.connect();
  link.run();
  while (seen.readings.length < 1) await sleep(5);
  port.hush();
  await sleep(40);
  const sent = port.written.length;
  await sleep(200);
  assert.ok(port.written.length <= sent + 1);                                   // at most the one that was on its way
  assert.equal(seen.states.at(-1)[0], "waiting");
  assert.match(seen.states.at(-1)[1], /probe mode/);
  port.speak();
  while (seen.states.at(-1)[0] !== "live") await sleep(5);
  await link.close();
});

test("a reply cut short is asked once more", async () => {                      // Review Focus 5
  const port = built();
  const [link, seen] = linked(port);
  await link.connect();
  port.cut(8);                                                                  // the loop's first :gen stops at ":gen\r\nge"
  link.run();
  while (seen.readings.length < 1) await sleep(5);
  await link.close();
  assert.deepEqual(port.written.slice(3, 6), [":gen\n", ":gen\n", ":paths\n"]);
  assert.deepEqual([seen.readings[0].gen, seen.readings[0].xbar], [3, xbarOfCase("same_chip_pairs")]);
});

test("bytes nobody asked for, read again, a pulled cable", async () => {        // Review Focus 6, 9, 13
  const port = built();
  const [link, seen] = linked(port);
  await link.connect();
  port.add("oled_b64{128x32:AAAA}\r\n");
  link.run();
  while (seen.readings.length < 4) await sleep(5);
  link.again();                                                                 // the number stands: read all the same
  while (seen.readings.length < 5) await sleep(5);
  assert.equal(seen.readings[4].gen, 9);
  port.pull();
  while (seen.states.at(-1)[0] !== "lost") await sleep(5);
  const trace = link.trace().trim().split("\n").map((line) => JSON.parse(line));
  assert.equal(trace[0].source, "board");
  assert.deepEqual(trace.slice(1, 5).map((e) => e.sent), ["N", ":ver\n", ":gen\n", ":gen\n"]);
  assert.ok(trace[4].got.includes("oled_b64{128x32:AAAA}") && P.genOf(trace[4].got).n === 3);   // kept, with the reply after them
  assert.ok(trace.length < 40 && trace.some((e) => e.times > 2));              // the polls of a still board are one line
});
```

- [ ] **Step 2: Run** `python3 -m unittest discover -s Routing/tests -t Routing -k test_board_port`. Expected: `BoardLink` is not a constructor.
- [ ] **Step 3: Implement.** One read loop that appends to a text and wakes whoever waits; `ask(text, reader)` on top of it; `connect`; the loop as written above, no more.
- [ ] **Step 4: Run all tests** three times over. Expected: pass each time (the tests run on real clocks of a few milliseconds; one that fails one time in three is a bug in the link, not in the test).
- [ ] **Step 5: Commit** `Routing lab: a link to a board's port 7 that proves the port, asks one thing at a time and waits for a silent board`.

---

### Task 5: The page: connect, show, redraw, light what changed

**Files:**
- Modify: `Routing/web/lab.js`, `web/index.html`, `web/lab.css`, `Routing/server.py`, `Routing/lab.py`, `Routing/export.py`, `Routing/tests/test_server.py`, `tests/test_export.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `BoardLink`, `FakePort`, `serialWhyNot`, `BOARD_PORT`; Task 2's `/api/board`; `api`, `caseOf`, `selectCase`, `renderCase`, `redraw`, `renderBattery`, `onlyKind`, `showProblem`, `sheetCurve`, `cellCentre`.
- Produces:
  - `index.html`: `<script src="board_port.js"></script>` before `lab.js`. Under the drop hint, `<div class="row" id="link-row">` with `<button id="connect" type="button">Connect a board</button>`, `<button id="link-again" type="button" class="quiet" hidden>read again</button>`, `<a id="link-trace" hidden>save trace</a>`; `<p id="link-status" class="hint">`; and `<details id="link-sends" class="hint">` whose text is the paragraph "What the page sends" below.
  - `export.py`: the `board_port.js` tag is replaced by the file's text, as the `lab.js` tag is, so that `lab.js` never names a thing that is not there; `index.html` without that tag raises as the others do. The page hides the row (an exported page has no judge).
  - `lab.py serve --replay FILE`: the server holds the file's text. `/api/info` gains `"replay": true | false`. `GET /api/replay` answers `{"trace": text}`, or 404 when the server was started without it. A file that is not a trace (its first line is not the header of Task 3) stops `serve` with the reason.
  - `lab.js`:
    - `LINK_CASE = "live_board"`.
    - `state.link = {link: BoardLink | null, name: "idle" | "probing" | "live" | "waiting" | "too_old" | "lost", words: "", fw: null, moved: null, held: null, granted: []}`. `moved` is the last `changed` the server gave that held anything. `granted` is what `navigator.serial.getPorts()` gave when the page loaded, so that a click need not wait to know.
    - `async function connectBoard()`: the button's click. With `state.info.replay`, the port is `new FakePort((await api("/api/replay")).trace, {gapMs: 300})` and no picker opens. Else, with exactly one port in `granted`, that port. Else `navigator.serial.requestPort({ filters: [BOARD_PORT.FILTER] })`, the first thing the click does (the picker needs the click). Then `connect()`, then `run()`. A second click on the button, now "Disconnect", closes the link. What it says for each `LinkError`:
      - `"not_port_7"`: `port.forget()` where the browser has it, and "That port is not the board's fourth. Nothing but one N was sent to it. Pick the one whose name ends port7 (macOS), or the last of the four."
      - `"busy"`: "Port 7 is open in another program or tab (a Jumperlessim viewer, a script). Close it there, then connect again."
      - `"too_old"`, and the state of that name: "This board's firmware (X) is too old for a live view: it has no :gen and :paths on port 7. They come with " + `BOARD_PORT.NEEDS` + ": https://github.com/Architeuthis-Flux/JumperlOS/releases. The page does not ask b in their place, because b prints on the board's terminal."
    - `async function showReading(r)`: posts `{name: LINK_CASE, text: r.b + "\n" + r.xbar, about, live: true}` to `/api/board`. `about` is "a V5's own routing, read over port 7 at HH:MM:SS, firmware X, generation N; not a run of the lab's router".
    - `function renderLink()`: the button's label, `#link-status`, and whether "read again" and "save trace" show.
    - `function drawMoved()`: the marks of `state.link.moved`. `redraw()` calls it last, when the case shown is `LINK_CASE` of the board's run, so every view on screen gets them, docked or not.
- **What the page sends** (the text of `#link-sends`, binding): "To the board's fourth port only, and only after you press Connect. N once: its net list, which proves the port is the right one. :ver once: its firmware version. :gen twice a second: a counter that moves when the board rebuilds its routing, and whether it has finished sending it. :paths and :crossbar when that counter has moved: its routing report, and which crosspoints are closed. All five are questions. None makes, removes or reroutes a connection, and none prints on the board's own terminal. Nothing is sent to any other port. The picker lists the board's four ports and they look alike: pick the one whose name ends port7 (macOS), or the last of the four. A wrong port gets the one N and is closed. Opening the second one by mistake can reset an Arduino plugged into the board."

**How a reading is shown (binding):**
1. The first reading does what a pasted report does (`showBoards`): the run shown becomes the board's, class `board`, and the case `live_board` is selected.
2. A later reading replaces that case's row and nothing else of the table. When `live_board` is the case selected, its entry in `state.cases` (the key `caseOf` makes: hash, arrangement, name) is dropped, its result and paint are fetched again, and `renderCase()` and `redraw()` run. These stay as they were: each view's zoom and place, the layout and which views are docked, `state.tab`, `state.side`, `state.tests`, `state.only`, the net lit alone and the bridge picked. `selectCase` and `openCase` are not called.
3. When another case is selected, or the run shown is not the board's (the user pressed Run), the reading is still posted, the row is updated when it is on screen, and the views are not touched. The status line says "the board changed at HH:MM:SS".
4. While `state.busy`, the newest reading is held in `state.link.held` and shown when the run is done. Older held ones are dropped.
5. `state.link.moved` is set from an answer whose `changed` holds anything, and stays until the next one that does: "read again" on a board that stands does not clear it.
6. **What changed, lit,** in the fabric, the KiCad sheet and the crossbars. A crosspoint in `closed` gets a ring in `--changed`, which the page already has and which is not `--problem`. A crosspoint in `opened` is drawn hollow and grey where it was (`cellCentre`; on the sheet, `sheetCurve`). A bridge in `bridges` has its row marked in the case panel, with "was routed, now unrouted" in words. The case panel's head says how many of each, and a click on that count shows them alone, as a legend key does (`onlyKind`). The style rules are named `link-closed` and `link-opened`.
7. The link's state is said in `#link-status` and never by colour alone. `"waiting"`, `"lost"` and `"too_old"` dim the view's title and add "last read HH:MM:SS" when there was a reading; they add no red.
8. Without Web Serial, the button is disabled and `#link-status` holds `serialWhyNot`'s sentence. On an exported page (`STATIC`) the whole row is hidden, as the drop hint is.
9. A reload does not connect. When `navigator.serial.getPorts()` holds exactly one port, the button says "Connect the board again" and its click uses that port with no picker; the port is proved again with `N`. With none, or more than one, the click opens the picker.
10. "save trace" downloads `link.trace()` as `port7_<date>_<time>.jsonl`.

- [ ] **Step 1: Write the failing tests.** In `test_server.py`: a server made with a replay file answers `/api/info` with `replay` true and `/api/replay` with the file's text; without one, `replay` is false and `/api/replay` is 404. `/board_port.js` is served. `lab.js` holds `"/api/replay"`, `function connectBoard`, `async function showReading`, `function drawMoved`, `requestPort({ filters: [BOARD_PORT.FILTER] })`, `"live_board"`, `"too_old"` and `.forget(`; it does not hold `getWriter`, `setSignals`, `baudRate: 1200` or `:oled`; it passes `node --check`. `index.html` has `id="connect"`, `id="link-sends"` and the words "Nothing is sent to any other port", and has neither "b (its routing report)" nor "Couldn't find a path". `lab.css` gives no rule naming `link-closed` or `link-opened` the colour `--problem`. In `test_export.py`: an exported page has no `<script src=` left in it and holds `class BoardLink`, and `lab.js` holds `$("link-row").hidden = Boolean(STATIC)`. In `test_cli.py`: `serve --replay` with a file that is no trace exits 1 naming the file.
- [ ] **Step 2: Run to see them fail.**
- [ ] **Step 3: Implement.** `showReading` shares the posting with `showBoards` and nothing of its state handling.
- [ ] **Step 4: Run all tests.**
- [ ] **Step 5: Check it in the browser**, in Chrome, with `python3 Routing/lab.py serve --replay Routing/tests/fixtures/port7_built.jsonl`:
  1. In the console, `window.isSecureContext && "serial" in navigator` is true on `http://127.0.0.1:8765/`. If it is false, stop and report: the plan's first call is wrong.
  2. Press Connect. The case `live_board` appears, class `board`, with 7 bridges, status ok, and no note about "sent equals planned".
  3. The fake board moves to `sf_to_sf`: the drawing changes by itself, 32 crosspoints are ringed as new, 16 are hollow grey, and nothing is red. The case panel names 14 bridges changed.
  4. Zoom in on chip K, light one net alone, and dock the crossbars beside the fabric. At the next change the zoom, the lit net and the docked view are as they were, and both views show the rings.
  5. The third routing has one bridge that did not route: it is drawn as any unrouted bridge is, and its row says "was routed, now unrouted".
  6. Press Run on `dense` while the board is linked. The battery shows; the status line says the board changed; the view is the battery's. Click `live_board`'s row: it is the newest reading.
  7. Open `#link-sends`: the paragraph is there. "save trace" gives a file whose first line is the header, whose `sent` values are only the five, and whose polls of a still board are one line.
  8. Start the server without `--replay`, in Firefox: the button is disabled and names Chrome. Paste a `b` report: it still works.
  9. `lab.py export` a page and open it: there is no Connect button.
  Screenshot the third for Kevin.
- [ ] **Step 6: Commit** `Routing lab page: connect a board, see its routing redraw when it changes, with what changed lit`.

---

### Task 6: The bench check (needs Kevin's go-ahead, and his again for the flash)

One sitting with a V5 plugged into the Mac, as the design's "How we know piece 7 works" has it. The board is flashed once, with Task 1's build. No file on the board is written by the page. **Do not start it until Kevin says the board is plugged in and he is ready**: he makes connections with the probe, and he reads his own terminal.

**Files:**
- Create: `Routing/tests/fixtures/port7_<date>.jsonl`
- Modify: `Routing/web/board_port.js` (`STALL_MS`, `WAIT_SAY_MS`, `PROBE_MS`, if the board says otherwise), `Routing/tests/board_port_test.js`, `Routing/tests/test_board_port.py`, `Routing/fidelity/README.md` (one paragraph under "Checked against a board": what was checked, on which firmware)

- [ ] **Step 1: Before the flash, on the board's firmware as it is.** Port 1 is free (Kevin's terminal closed).
  1. In the worktree, `python3 test/hil/test_port7_reads.py`. Expected: it fails at its first check with `unknown_verb`. This is Task 1's failing run.
  2. The lab runs with no `--replay`. Before Connect, write down what Chrome's picker shows for each of the four ports. Press Connect and pick the fourth. Expected: the page says the firmware is too old, with its version, in no red; "save trace" shows `N`, `:ver\n` and `:gen\n` and nothing else.
- [ ] **Step 2: The flash.** Ask Kevin now, and wait for his word. Build `jumperless_v5` in the worktree and put it on the board the way he names. Write down what `:ver` says after.
- [ ] **Step 3: The firmware's checks.** `python3 test/hil/test_port7_reads.py` passes. Then `python3 test/hil/run_all.py`, the bench suite, as its README asks (nothing in the breadboard, port 1 free). A suite that fails is run again on the firmware of `origin/main` before the branch is blamed.
- [ ] **Step 4: Kevin's terminal on port 1, the page on port 7.** Write down, each as seen:
  1. The page connects: `N` answered with a net list, the version shown, `live_board` appears and matches what is on the breadboard.
  2. **Silent while still.** With the page connected and the board still for two minutes, Kevin's terminal shows nothing.
  3. **A change by probe.** Kevin connects two rows with the probe. The page goes to "waiting" while probe mode is on, and shows the new bridge within a second of the board going idle after it is left.
  4. **A change by terminal, and by slot.** Kevin adds a bridge from his terminal, then loads another slot. Each shows on the page within a second.
  5. **A bridge that cannot route.** Kevin makes one, or loads a slot that has one. The page shows it as not routed. His terminal shows one "Couldn't find a path" line, when it fails, and none after, however long the page stays connected.
  6. **"Sent equals planned", with the net scan on.** The board still for one minute, "read again" pressed twenty times: no reading shows a "sent equals planned" problem, and nothing is red that is not a fault. With FakeGPIO in use, if Kevin has a slot that uses it: write down what is seen.
  7. Kevin clears the board (`x` on his terminal). Does `:paths` still list a bridge? The page shows a case with nothing on it, or with the feed alone, and everything else as opened.
  8. Whether the board's own LEDs, probe and menus feel as they do unlinked. Kevin says.
  9. Open the same port in a second tab: the second says the port is busy. Pull the cable: the page says the board is gone. Plug it back: how many ports does `navigator.serial.getPorts()` hold, and is the one port 7? Press Connect.
  10. Whether opening port 7 raises DTR, and whether a wrong port picked on purpose (the main port, with nothing on the UART) gets one `N` and is closed.
- [ ] **Step 5: Save the trace** of that sitting as `tests/fixtures/port7_<date>.jsonl`, and add two tests. In `board_port_test.js`: replayed through `FakePort` and a link, it gives one reading for each generation the sitting read (a `:paths` and a `:crossbar` followed by a `:gen` idle at the number they were asked under), and nothing is written but the five. In `test_board_port.py`: each of those pairs is read by `board.result` with no "not a V5 b report" and no "sent equals planned" problem, and the bridges Kevin made are there, by their nodes.
- [ ] **Step 6: Set the three timings from what was seen.** `POLL_MS` stays 500: it is the design's. If a still board ever showed a "sent equals planned" problem in item 6, stop and report: the `:crossbar` of Task 1 is not free of taps, and that is the firmware's to mend, not the page's to hide.
- [ ] **Step 7: Run all tests.**
- [ ] **Step 8: Commit** `Routing lab: the live board checked against a V5, its trace kept`. In the body: the two things of Step 1, the suite's result, and the ten of Step 4, each with what was seen.

---

### Task 7: Documents

**Files:**
- Modify: `Routing/web/README.md`, `Routing/README.md`, `Routing/docs/DESIGN_ROUTING_LAB.md` (status), `Routing/web/board_port.js` (`NEEDS`); the `JumperlOS` submodule, only as Step 3 says

- [ ] **Step 1: READMEs.** In `Routing/web/README.md`, one bullet "A live board" and a section "A live board" after "A board's own output": what Connect does; which port and how to pick it; the paragraph "What the page sends", word for word; the firmware it needs and what it says without it; what the board does not answer during (probe mode, a menu, an app) and what the page shows then; that "sent equals planned" is checked on every reading; what "changed" lights; the browsers; `serve --replay` and the trace file; that it is V5 only, one board at a time, and reads only. In `Routing/README.md`, "What it does not check" gains: a live board is read between its rebuilds, not during them; a crosspoint closed and opened between two polls is not seen; FakeGPIO's writes to the chips are not known to be kept out of the dump; net voltages are not shown.
- [ ] **Step 2: Design.** The status line (piece 7 built, on the local server), and under piece 7 what was built differently, with Task 6's findings.
- [ ] **Step 3: The submodule and `NEEDS`, each only when GitHub has what it needs.** Kevin pushes or merges Task 1's commit; this plan does not. When `git -C JumperlOS fetch origin` then `git -C JumperlOS branch -r --contains <commit>` names any branch: check the submodule out at that commit and stage `JumperlOS`. The commit touches no router file and nothing under `Routing/harness/`, so the lab's routing and its "verified against a board" stand. When the branch named is `origin/main`, a release was made: set `BOARD_PORT.NEEDS` to that release's version. Until each, the submodule stays where it is, `NEEDS` stays as Task 3 wrote it, and the README says the firmware is on a branch.
- [ ] **Step 4: Run all tests.**
- [ ] **Step 5: Commit** `Routing lab: the live board documented`.

---

## Not in this plan

The design's "Not in piece 7":

- **Writing to the board.** The page does not send the netlist made by clicking nodes to the board, clear it, load a slot or pause its net scan. It asks, and that is all.
- **Two boards at once.** Every V5 has the same serial string, so the page cannot tell them apart. One link, one case named `live_board`.
- **The OG Jumperless.** Running JumperlOS it has the same USB ids (`boards/jumperless_og.json:5-6`), so the picker lists it. The lab reads V5 reports only; an OG's report is refused with the lab's usual message.
- **A stand-in for Web Serial.** No WebUSB (JumperIDE carries one, `app.js:26`), no helper program, no phone. Paste and drop stay as they are.
- **The board's LEDs, OLED and voltages.** That is Jumperlessim's viewer. This page shows routing.
- **The published page, until piece 6.** `slopswap.org/routing-lab/` has no judge until then.

Also not here: a recording to play back for visitors (`--replay` is for the tests and the browser check).

## After this plan

**Asked of the firmware, and not in this piece.** The design lists five, and the notes' table (rows 4 to 7) says what each touches. They go to Kevin as that list:

- Port 7 answered in probe mode and the menus (a service of its own with a guard against re-entry; medium risk).
- `b` and `n` printing "Couldn't find a path" only to the port that asked.
- The probe's connection falling back to its next candidate when the chosen pair does not route.
- The tap reserve applying to stacked copies only while the scan is on.
- A list of the planned taps (`:taps`), for drawing them.

**Piece 6.** When it is built, the live board comes with it and needs no new code in the page: `showReading` asks `/api/board` through `api()`, and the engine in the tab answers that path with the same JSON. What piece 6's plan must add: `board_port.js` in the bundle, `board.changed` reached by the engine's `/api/board`, and one check on `https://slopswap.org/routing-lab/` with a board, which again needs Kevin.
