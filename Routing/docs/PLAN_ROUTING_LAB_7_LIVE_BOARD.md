# Routing lab, plan 7: a live board in the browser

> **Draft, 2026-11-23.** Written by reading the firmware and the lab, on no board, while the lab still lived in the
> JumperlOS repository; the lab moved here the same day and this plan's paths were brought up to date (firmware
> files are `JumperlOS/src/...`). It has not been reviewed against a board, and its design section ("Piece 7" of
> `Routing/docs/DESIGN_ROUTING_LAB.md`) is still to be written and approved before Task 1. Line numbers for the
> page's files are of the commit "routing lab sheet view: a lit wire is followed through its op-amp".

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A button on the lab's page connects to a Jumperless V5 over Web Serial, and the page shows that board's routing as a case that redraws by itself when the routing changes, with what changed lit. The page only asks. It never makes, removes or reroutes a connection.

**Architecture:** The page opens the board's fourth serial port, the machine backchannel (USBSer3, "port 7"), and nothing else. The firmware pushes nothing when its routing changes, so the page asks: twice a second it reads the net list (`N`) and the crossbar dump (`:crossbar`), and it asks for the `b` report only when one of those changed. The report and the dump go to `POST /api/board`, which the lab already has, so the judge, the copper searches and the drawing are the ones a pasted report gets. A new `board.changed` says what differs between two readings. The port code is a new file with no DOM in it, `web/board_port.js`, tested under `node` with a fake port that replays a trace. It ships on the local lab server first. It does not wait for piece 6: everything it asks goes through the page's one `api(path, body)`, so the engine in the tab answers it when that is built.

**Tech Stack:** Python 3 standard library; the existing page (plain JS, SVG); Web Serial in the browser (Chrome, Edge, Opera, Brave); `node` for the port code's tests (the suite already needs it). No package is added.

**Spec:** The design section **"Piece 7: a live board" does not exist yet.** It must be written into `Routing/docs/DESIGN_ROUTING_LAB.md` and approved by Kevin before Task 1 starts. Kevin's ask, 2026-11-23: "write a plan to connect to a jumperless from the browser and show a live updating view of the routing on a real jumperless". This plan is written against the calls below; where the design decides otherwise, the task named changes. The design must decide:

1. **Where it ships first.** The local lab server now (this plan), or only with piece 6's engine in the tab. (All tasks.)
2. **Which port, and how the page knows it has it.** Port 7 only, proved by one byte (`N`) before anything else is sent. What a wrong pick costs, and what the page tells the user before the picker opens. (Task 3, Task 4.)
3. **Asking against being told.** The page polls. How often, and what makes it ask for the report. (Task 3.)
4. **When the crossbar dump counts.** A dump read the same three times in a row. What is said when it never holds still. (Task 1, Task 3.)
5. **What the page may send.** Four things: `N`, `:ver`, `:crossbar`, `b`. Whether it stops asking while its tab is hidden. (Task 3.)
6. **The live case.** Its name, where it sits in the table, what happens to a run on screen, what a redraw may not disturb, what "changed" means and how long it stays lit. (Task 1, Task 4.)
7. **A board that does not answer.** By reading, port 7 is silent while the board is in probe mode, a menu or an app. What the page shows then. (Task 3, Task 4, Task 5.)
8. **Browsers without Web Serial**, a page not in a secure context, and exported pages. (Task 2, Task 4.)
9. **Testing without a board.** The trace format, and the replay. (Task 2, Task 4.)
10. **The bench check**, and that it needs Kevin's go-ahead. (Task 5.)
11. **What is asked of the firmware later**, and not done here. ("After this plan".)

Also read: `Routing/README.md`, "A board's own output", for what exists; `JumperlOS/src/tubes/Ser3Backchannel.h` for the port's protocol.

## Global Constraints

- Nothing under `JumperlOS/src/` is edited. `JumperlOS/test/hil/` is read, not edited. Nothing under `Routing/harness/` is edited.
- One commit per task, never pushed. No attribution lines in commit messages. Never touch `.github/workflows/release.yml`. Stage files by name; `.pio/**/firmware.uf2` is tracked and must not be committed.
- The lab itself imports only the standard library. So the server never opens a serial port (that would need `pyserial`): the page does, and sends the text.
- **The page never sends anything to a board the user has not connected by a click, and says what it sends.** A reload does not reconnect by itself. The four things it sends are written on the page beside the button, and every byte sent is kept in a trace the user can save.
- **Four things, and no other byte:** `N`, `:ver\n`, `:crossbar\n`, `b`. Never a `:` before the port has answered `N` with a net list: on the main port `:` is "set DAC voltage" (`JumperlOS/src/SingleCharCommands.cpp:563`). The port is opened at 115200 and at no other speed: 1200 on the REPL port reboots the board into BOOTSEL (`JumperlOS/src/tubes/ArduinoStuff.cpp:386-402`).
- **One query unanswered at a time.** The page sends the next only when the last is answered. A board that is silent is waited for, not asked again.
- **Say who answered.** A live case says it is a board's own routing and not the lab's router, the firmware version the board gave, that it came over port 7, when it was read, and whether what was sent to the chips was checked against the path table.
- On the page red means a problem and nothing else is red. What changed is lit in a colour that is not red. A board that does not answer is not a problem of the routing and is not red.
- No step talks to a board except Task 5, and Task 5 does not start without Kevin's go-ahead. Nothing is flashed.
- Another session is at work in this worktree on the page: `web/lab.js`, `web/index.html`, `web/lab.css`, `server.py`, `export.py` and the README changed twice while this plan was written (`48c08ad`, `17b72f2`). The line numbers below for those files are of `17b72f2` and will have moved: find the function by its name. Before a task that modifies one of them, `git status` must be clean.
- In `lab.js`, "live" already means "re-run on save" (`installLive`, `#live`, `state.liveTried`). This plan's names use `link` and `board`.
- Tests: `python3 -m unittest discover -s Routing/tests -t Routing` passes with the solver installed and without it.

## Measured before writing this plan (2026-11-23, by reading; no board was touched)

Read in: the JumperlOS main checkout at `0b8d06c` (it has uncommitted edits to `JumperlOS/src/Probing.cpp`, `JumperlOS/src/config.h` and `JumperlOS/src/JumperlessMicroPythonAPI.cpp` among others; what is cited from them is marked), JumperIDE at `7e37427`, Jumperlessim at `5ea97c11`, and this worktree at `17b72f2`. Paths starting `JumperlOS/src/`, `include/`, `boards/`, `modules/` and `test/` are that checkout's. Paths starting `Routing/`, and bare lab file names, are this worktree's.

**How a browser reaches the board**

- **Four serial ports, one identity.** The board is USB `1D50:ACAB` (`JumperlOS/src/tubes/usb_descriptors.cpp:71-72`) with four CDC interfaces named "Jumperless Main", "JL UART Passthrough", "JL Micropython REPL" and "JL TUI" (`include/usb_interface_config.h:63-69`). On macOS they are `/dev/cu.usbmodemJLV5port1`, `3`, `5` and `7` (`JumperlOS/test/hil/jl.py:454`, `:671`; `JumperlOS/test/hil/port7.py:17`). The serial string is the constant `JLV5port` (`usb_descriptors.cpp:511`), so two V5s cannot be told apart.
- **JumperIDE opens what the user picks.** `navigator.serial.requestPort()` with no filter (`JumperIDE/src/jumperless_serial_terminal.js:322`, `transports.js:224`), at 115200 (`transports.js:238`). It never calls `setSignals` (no hit in `JumperIDE/src/*.js`). Its REPL is on CDC 2 (`app.js:4129-4131`). It says the four ports "all share one VID/PID" and finds the REPL by probing each (`app.js:4339-4349`, `:4392-4397`). On the main port it sends `B1 \n` on connect (`jumperless_serial_terminal.js:21`, `:170`). It never uses the backchannel (no hit for `USBSer3`, `backchannel` or `xbar{` in `JumperIDE/src`).
- **Jumperlessim already talks to port 7 from Chrome.** Filter `{usbVendorId: 0x1d50, usbProductId: 0xacab}` (`Jumperlessim/packages/app/src/ports.ts:1-8`), 115200 with a 65,536 byte read buffer (`packages/engine-webserial/src/lineChannel.ts:21`), one query in flight (`engine.ts:73-80`), `:crossbar` every 250 ms (`engine.ts:22`). Kevin ran it against a real V5 in Chrome from its dev server on localhost (`docs/HANDOFF-2026-09-10.md:88-89`). Its read loop first died on Web Serial read errors; taking the reader again and the larger buffer fixed it (`HANDOFF:90`, `lineChannel.ts:29-46`).
- **Its probe is stale.** It sends `K` as "harmless on every CDC port" (`engine.ts:27-35`). On the main port `K` now opens the click menu (`JumperlOS/src/SingleCharCommands.cpp:529-533`).
- **Web Serial's limits, as JumperIDE meets them.** It needs a secure context and a Chromium browser (`app.js:215-222`), a click for the picker (`app.js:4137-4138`), and the OS gives a port to one program: Chrome reports another holder as `NetworkError` (`transports.js:177-196`). A page cannot be asked to let go, as the desktop app can (`jumperless_serial_terminal.js:207-212`).

**What the firmware offers, and on which port**

- **Port 7 is the machine port.** USBSer3 is CDC interface 3, begun at 115200 (`JumperlOS/src/tubes/ArduinoStuff.cpp:209-212`), "without competing with the human-facing menu on the primary serial port" (`JumperlOS/src/tubes/Ser3Backchannel.h:5-8`). Only commands tagged `SER3_ALLOWED` run there; the rest are refused with a JSON error (`Ser3Backchannel.h:19-28`, `Ser3Backchannel.cpp:1242-1261`). Bytes under 32 are dropped (`:1179-1180`).
- **The `b` report can be asked for on port 7.** `b` is registered with no tag (`JumperlOS/src/SingleCharCommands.cpp:480-482`), and the default tag is `SER3_ALLOWED` (`SingleCharCommands.h:95-99`, `:146`). Its handler prints to the port that asked (`SingleCharCommands.cpp:2096-2130`; the backchannel sets that at `Ser3Backchannel.cpp:1264-1273`). **Not verified on a board:** the bench suite takes `b` on port 1 (`JumperlOS/test/hil/test_routing_dense.py:66-69`). No capture of `b` from port 7 exists.
- **`b` is not silent on port 1.** The handler calls `couldntFindPath(1)` (`SingleCharCommands.cpp:2121`), which prints "Couldn't find a path for X to Y" to `Serial`, the main port, for each primary path that did not route (`JumperlOS/src/routing/NetsToChipConnections.cpp:5484-5488`). So each `b` the page asks puts one line a failed bridge on the user's terminal.
- **`b` is not only a print.** `couldntFindPath` also writes: it marks each failed primary path skipped, sets its crosspoints to none, and fills the list of paths that could not be made (`NetsToChipConnections.cpp:5490-5521`). The router runs the same call at the end of every routing pass (`:2626`), so by reading a `b` writes what is already there. **Not verified on a board.**
- **The crossbar dump.** `:crossbar` (or `:xbar`) answers `xbar{12x8:` and 384 hex digits and `}`, a copy of `lastChipXY`, the crosspoints last sent (`Ser3Backchannel.cpp:378-394`, `:798-799`). A `:` line is echoed back first (`:1085-1107`, `:1186`). As captured, a reply is 406 bytes with its echo (`Routing/fidelity/board_0621e4f44e23/*.xbar.txt`).
- **The net list.** `N` on port 7 answers `{ "nets": [ {"index", "name", "nodes", "special", ...} ] }` (`Ser3Backchannel.cpp:254-262`, `:1066-1078`; `JumperlOS/src/routing/JsonState.cpp:128-195`, `:345-355`). A net's entry also carries a measured `"voltage"` or `"logic"` (`JsonState.cpp:210`, `:278-280`), so the text changes when nothing was rewired. `N` is no command on the main port (the registrations, `SingleCharCommands.cpp:435-785`, have none); an unknown key there shows the menu (`:168-172`). Its length was **not verified**; the code reserves 8,192 bytes for the whole state (`JsonState.cpp:109-113`).
- **Nothing is pushed when the routing changes.** The only thing port 7 sends unasked is the OLED stream, once switched on (`Ser3Backchannel.cpp:87`, `:776-792`). The "live crossbar" (`c!`) is a drawing on the main terminal (`JumperlOS/src/CH446Q.cpp:1298-1325`).
- **`:every` is not a push.** A streamed capture runs inside the port's service call and waits out each interval in a loop, up to 60 s; it stops on any byte received (`Ser3Backchannel.cpp:1010-1034`). The main loop does not run meanwhile.
- **There is a change counter, and port 7 cannot read it.** `routingGeneration` goes up on every rebuild and clear (`JumperlOS/src/routing/RouteSafety.cpp:34`, `JumperlOS/src/CH446Q.cpp:757`, `NetsToChipConnections.cpp:1748`). It is printed only by the audit behind `i?` (`RouteSafety.cpp:1288-1291`, `SingleCharCommands.cpp:3223-3225`), and `i` is tagged `SER3_MODIFIES_STATE` (`:651-655`).
- **Port 7 is answered from the main loop only.** `serviceUSBSer3()` is called from `Jerial.service()` (`JumperlOS/src/Jerial.cpp:1167-1168`), which is called at `JumperlOS/src/main.cpp:1206` and `JumperlOS/src/Menus.cpp:908` and nowhere else. Probe mode is a loop of its own that calls `jOS.serviceInner()` (`JumperlOS/src/Probing.cpp:4397-4416`, a file with uncommitted edits), and `Jerial` is no jOS service (`JumperlOS/src/JumperlOS.h:429`). Jumperlessim's capture tool found the same: with the main terminal in a full-screen app "the backchannel does not answer" (`Jumperlessim/tools/capture/jlcap.py:18-19`). **Not verified on a board** for probe mode.
- **The dump holds more than the path table.** The net scan's sense taps are written into `lastChipXY` (`JumperlOS/src/sensing/NetVoltageScan.cpp:365`). The scan "closes ephemeral sense taps to ADC0 that a crossbar snapshot can catch mid-flight", so the bench suite switches it off (`JumperlOS/test/hil/test_routing_dense.py:49-52`). It is on by default (`JumperlOS/src/config.h:177`, a file with uncommitted edits). FakeGpio and MicroPython's direct crosspoint call write there too (`JumperlOS/src/sensing/FakeGpio.cpp:83-87`; `JumperlOS/src/JumperlessMicroPythonAPI.cpp:1739-1743`, a file with uncommitted edits). How long a tap stays closed was **not verified**.
- **A board's write does not time out.** `Adafruit_USBD_CDC::write()` waits while the host holds the port open and does not read (`usb_descriptors.cpp:609-612`). The page must read whenever the port is open.
- **The version.** `:ver` on port 7 prints `Jumperless firmware version: X` (`Ser3Backchannel.cpp:835-838`, `SingleCharCommands.cpp:3044-3051`).
- **The REPL can print the same blocks** (`print_bridges`, `print_paths`, `print_chip_status`: `modules/jumperless/modjumperless.c:105-109`, a file with uncommitted edits), but that is the port JumperIDE holds and a session of the user's. Not used.
- **What the wrong port does.** A rising DTR on the UART passthrough port is taken as the start of a flash: it can reset a plugged-in Arduino and has the UART routed to it (`JumperlOS/src/tubes/AsyncPassthrough.cpp:2325-2337`, `:2343-2377`; `ArduinoStuff.cpp:380-384`, `:407-409`). On the main port the first byte of a new connection brings the greeting and a flush of what follows (`JumperlOS/test/hil/jl.py:1387-1391`), `:` is "set DAC voltage" (`SingleCharCommands.cpp:563-565`) and `A` connects the UART to D0 and D1 (`:553-555`). Whether Web Serial raises DTR on `open()` was **not verified**; Jumperlessim says it does (`engine.ts:111`).
- **Who else holds a port.** The desktop app sits on port 1 and lets go for a lease file a browser cannot write (`JumperlOS/test/hil/jl.py:75-85`; `Jumperless-App/JumperlessWokwiBridge.py:449-465`). When it looks for its ports it opens each one and sends ENQ (`JumperlessWokwiBridge.py:1833-1848`), which port 7 drops. Port 7 can be used while port 1 is held (`JumperlOS/test/hil/port7.py:3-6`).

**What the lab needs from the board**

- **The `b` report, and nothing else, draws the picture.** `board.result(name, text)` wants the last whole report in the text: "Bridge Array", "Paths" and "Chip Status" with all twelve chips (`Routing/board.py:57-88`, `:108-143`). `copper.paint` reads the crosspoints, the claims and the bridges from that text alone (`copper.py:118-201`).
- **The dump adds one check.** With `xbar{12x8:...}` in the text, `runner.judge` hands it to the checker's "sent equals planned" (`runner.py:151`; `JumperlOS/test/hil/routing_check.py:430-433`). Without it the lab makes a dump from the path table and notes that this was not checked (`board.py:30-31`, `:91-98`, `:135-139`). So without `:crossbar` the page cannot see a crosspoint the chips hold that the table does not list, or one listed that was never sent.
- **A report with no bridge is refused.** `board.result` raises "its Bridge Array lists no bridge" (`board.py:118-119`), which `/api/board` answers as 400. All 21 captures list the probe feed's bridge. The firmware adds that bridge by its settings (`JumperlOS/src/routing/InfraPaths.cpp:288`, `:310`); whether a cleared board always lists one was **not verified**.
- **Never there for a board:** sense taps and the second-rebuild check (`Routing/README.md:226-227`).
- **The same name again replaces the case.** `api_post_board` keeps results by case name under the run `board` (`server.py`, `api_post_board` at 353 and `keep` at 248; `tests/test_server.py`, `test_board_output_is_judged_kept_and_served_like_a_run`).
- **`showBoards` is not a redraw.** It empties `state.cases` and ends in `selectCase`, which lets go of the lit net, the picked bridge and the picked wire (`web/lab.js`, `showBoards` at 634, `selectCase` at 694).
- **An exported page cannot judge.** `staticApi` answers four paths and refuses the rest (`web/lab.js`, at 111).
- **Report sizes.** The 21 captures of 2026-11-21 are 2,517 to 4,046 bytes (`wc -c Routing/fidelity/board_0621e4f44e23/*.b.txt`). They were taken on port 1 with the colour codes already stripped (`JumperlOS/test/hil/jl.py:1436`), so the length on the wire is **not verified**.
- **Two readings compared**, with the lab's own code on those captures: `same_chip_pairs` (7 bridges, 16 crosspoints) and `sf_to_sf` (9 bridges, 32 crosspoints) share no crosspoint and one bridge, the probe feed. `k_rows_overflow_metric` routes 12 of 13; the one that fails is the feed, BUFFER_IN to GPIO_6.
- **`node` is here and already needed.** v20.18.3 on this Mac; `tests/test_server.py:145` runs `node --check` with no skip.

**Not verified at all:** what Chrome's port picker shows for each of the four ports; that `http://127.0.0.1:8765/` gets Web Serial (Jumperlessim's page on localhost did); how long `N` and `b` hold the board's main loop; whether `b` on port 7 begins with an echo. Task 5 measures each.

## File structure

| File | Responsibility |
|---|---|
| `Routing/board.py` (modify) | `changed`: what differs between two readings. A note for a dump that did not hold still. `about` on a result |
| `Routing/server.py` (modify) | `/api/board` takes `about` and `unsteady` and answers `changed`. `serve --replay FILE`: `/api/replay`, and `replay` in `/api/info` |
| `Routing/lab.py` (modify) | The `--replay` flag of `serve` |
| `Routing/web/board_port.js` (new) | The board's port, no DOM: the three replies read, `BoardLink` (open, prove, ask, one query at a time), `FakePort`, the trace |
| `Routing/web/lab.js`, `index.html`, `lab.css` (modify) | The Connect button, what the page sends, the link's state, the live case's redraw, what changed lit |
| `Routing/export.py` (modify) | An exported page carries `board_port.js` inlined, as it carries `lab.js` |
| `Routing/tests/board_port_test.js`, `tests/test_board_port.py` (new) | The port code under `node` |
| `Routing/tests/fixtures/port7_built.jsonl` (new) | A trace built from four captures, for the tests and the replay |
| `Routing/tests/fixtures/port7_<date>.jsonl` (new, Task 5) | A trace from a real board |
| `Routing/tests/test_board.py`, `test_server.py`, `test_export.py` (modify) | Tests |
| `Routing/README.md`, `Routing/docs/DESIGN_ROUTING_LAB.md` (modify) | Documents |

## Review Focus

The inputs most likely to bite. Each has its test in the task named.

1. **A wrong port picked.** The four ports look alike to the page. A port that does not answer `N` with a net list gets that one byte and no more, is closed, and its grant is given back (`port.forget()`), so the page never opens it again without the picker. The page says which port to pick before the picker opens, and what opening the wrong one can do (Task 3, Task 4).
2. **A board that does not answer.** In probe mode, a menu or an app the main loop does not run. The page waits, says so in words, keeps the last picture with the time it was read, and sends nothing more. It is not red. When the board answers, the loop goes on (Task 3, Task 4).
3. **A dump that does not hold still.** The net scan's taps come and go in `lastChipXY`. One reading that differs from the path table is not a fault. A dump goes to the judge only when three readings in a row are the same; until then the case's notes say "sent equals planned" was not checked, and nothing is red for it (Task 1, Task 3).
4. **The report and the dump are two questions.** A rebuild between them reads as a fault. The dump used is the one read right after the report, and only if it is the steady one (Task 3).
5. **A reply cut short.** A read error, or a board that stopped mid-line. A reply that began and then stood still for `STALL_MS` is thrown away and asked once more. This is the only time a query is sent twice (Task 3).
6. **Bytes nobody asked for.** The echo of `:crossbar`; an OLED stream another tool left on. Each reader finds its own reply by its shape and ignores the rest. The page never switches the stream off: that is another tool's state (Task 2, Task 3).
7. **A page that stops reading.** The board's write has no timeout. One query at a time and a read buffer of 65,536 bytes mean the board never waits on the page, even with the tab's script stopped: the largest report captured is 4,046 bytes, and the firmware's own guess for a full state is "10-20KB" (`JsonState.cpp:112`) (Task 3).
8. **A redraw under the user's hands.** A new reading must not move the view, drop the lit net, or pull the user off another case they are looking at. A reading that arrives during a Run is kept and shown after (Task 4).
9. **The port held elsewhere, pulled out, plugged back.** Another tab or tool on port 7 is said in words. A pulled cable ends the link cleanly; connecting again is a click (Task 3, Task 4).
10. **What `b` prints on the user's terminal.** One "Couldn't find a path" line a failed bridge, each time the report is asked. So the report is asked only when something changed, and the page says this beside the button (Task 3, Task 4, Task 5).
11. **A board with nothing on it.** A cleared board may print a report with no bridge, which a pasted report is refused for. For a linked board that is a case with nothing on it, and "what changed" lists everything opened (Task 1, Task 5).
12. **A port remembered from last time.** A grant kept by the browser is opened before it can be proved, and opening is itself what resets an Arduino on the wrong port. JumperIDE finds several ports of one board among its grants, and not always the same object after a replug (`JumperIDE/src/app.js:4374-4377`, `:4402-4406`). The page uses a remembered port only when it holds exactly one; with more it opens the picker (Task 4, Task 5).

---

### Task 1: What changed between two readings

**Files:**
- Modify: `Routing/board.py`, `Routing/server.py`, `Routing/tests/test_board.py`, `Routing/tests/test_server.py`

**Interfaces:**
- Consumes: `board.result`, `copper.paint`, `Handler.keep`, `api_post_board`.
- Produces:
  - `board.result(name, text, about="", unsteady=False, live=False)`: `about` is the result's `about` (the case's notes). With no dump in the text and `unsteady` true, the note is `board.NO_STEADY_DUMP` in place of `board.NO_DUMP`. A dump in the text is used whatever `unsteady` says. With `live`, a whole report (all twelve chips) whose Bridge Array lists no bridge is a result of status `"empty"` with the note "nothing is connected on the board"; without `live` it is refused as before.
  - `board.NO_STEADY_DUMP`: `"the crossbar dump was not the same in three readings in a row (the net scan closes sense taps for a moment; i on the board's terminal pauses it): what was sent to the chips is taken to be what the path table lists, so \"sent equals planned\" was not checked"`.
  - `board.changed(before, after) -> dict | None`: `None` when `before` is `None`. Else `{"closed": [[chip, x, y, net], ...], "opened": [[chip, x, y, net], ...], "bridges": [{"n1", "n2", "was", "now"}, ...]}`, each list sorted. A crosspoint is told by its place (chip, x, y), not its net: a net that only got another number is no change. `closed` carries the net of `after`, `opened` the net of `before`. A bridge is told by its two nodes in either order; it is listed when its state differs, `was` or `now` being `None` when it is not there.
  - `POST /api/board {"name", "text", "about": str (optional), "unsteady": bool (optional), "live": bool (optional)}`: the answer is as before, with `"changed"`: `board.changed(the case of that name as it was kept, the new result)`. A wrong type for `about`, `unsteady` or `live` is 400 with the reason.

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

    def test_a_dump_that_did_not_hold_still_is_said_so(self):          # Review Focus 3
        text = capture("same_chip_pairs", crossbar=False)
        r = board.result("live_board", text, about="a V5 on port 7", unsteady=True)
        self.assertEqual((r["about"], r["status"], r["problems"]), ("a V5 on port 7", "ok", []))
        self.assertEqual([n for n in r["notes"] if "sent equals planned" in n], [board.NO_STEADY_DUMP])
        self.assertIn(board.NO_DUMP, board.result("pasted", text)["notes"])
        with_dump = board.result("live_board", capture("same_chip_pairs"), unsteady=True)
        self.assertFalse([n for n in with_dump["notes"] if "sent equals planned" in n])

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

`cleared` is new in `test_board.py` (which also needs `from unittest import mock`). It was tried on the captures on 2026-11-23: it leaves no bridge, no path row and twelve chip rows.

```python
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
        again = self.c.post("/api/board", {"name": "live_board", "text": text("sf_to_sf")}).json
        self.assertEqual((len(again["changed"]["closed"]), len(again["changed"]["opened"])), (32, 16))
        self.assertEqual(len([x for x in again["rows"] if x["case"] == "live_board"]), 1)      # the same case, read again
        same = self.c.post("/api/board", {"name": "live_board", "text": text("sf_to_sf")}).json
        self.assertEqual(same["changed"], {"closed": [], "opened": [], "bridges": []})
        no_dump = (captures / "sf_to_sf.b.txt").read_text(errors="replace")
        self.assertEqual(self.c.post("/api/board", {"name": "live_board", "text": no_dump, "unsteady": True}).status, 200)
        notes = self.c.get("/api/case?variant=board&case=live_board").json["result"]["notes"]
        self.assertTrue(any("three readings" in n for n in notes))
        for bad in ({"about": 5}, {"unsteady": "yes"}, {"live": 1}):
            r = self.c.post("/api/board", dict({"name": "x", "text": text("sf_to_sf")}, **bad))
            self.assertEqual(r.status, 400, bad)
```

- [ ] **Step 2: Run** `python3 -m unittest discover -s Routing/tests -t Routing -k Changed -k read_again`. Expected: `board` has no `changed`; `result` takes no `about`.
- [ ] **Step 3: Implement.** `changed` is two calls of `copper.paint` and three set differences. In `api_post_board`, read the kept case before `keep` replaces it.
- [ ] **Step 4: Run all tests.** Expected: pass.
- [ ] **Step 5: Commit** `Routing lab: what changed between two readings of a board, and a dump that did not hold still`.

---

### Task 2: The board's replies, read, and a fake port

**Files:**
- Create: `Routing/web/board_port.js`, `Routing/tests/board_port_test.js`, `Routing/tests/test_board_port.py`, `Routing/tests/fixtures/port7_built.jsonl`

**Interfaces:**
- Consumes: the reply shapes under "Measured"; the 21 captures.
- Produces, in `board_port.js`. It is a plain script with no DOM and no import. In the page it defines globals. Under `node` its last line exports them: `if (typeof module !== "undefined") module.exports = {...}`.
  - `BOARD_PORT`: `{FILTER: {usbVendorId: 0x1D50, usbProductId: 0xACAB}, BAUD: 115200, BUFFER: 65536, POLL_MS: 500, STEADY_READS: 3, PROBE_MS: 1500, STALL_MS: 3000, WAIT_SAY_MS: 1500, TRACE_MAX: 400}`. Where each is from: the ids, `usb_descriptors.cpp:71-72`; the speed, `ArduinoStuff.cpp:212`; the buffer, `lineChannel.ts:21`; `PROBE_MS`, Jumperlessim's probe (`engine.ts:31`). `POLL_MS`, `STEADY_READS`, `STALL_MS`, `WAIT_SAY_MS` and `TRACE_MAX` are first guesses of this plan; Task 5 sets them from the board.
  - `serialWhyNot(nav, secure) -> string | null`: `null` when Web Serial can be used. Without `nav.serial`: "This browser has no Web Serial. Chrome, Edge, Opera and Brave have it. Paste or drop the board's b output here." When `secure` is false: "Web Serial needs a page served over https, or from 127.0.0.1."
  - `netsKey(text) -> string | null`: the first text from `{ "nets":` that parses as JSON, as `"index:node,node;index:node,..."`. `null` when there is none yet. `""` for a board with no nets. `"voltage"`, `"logic"`, `"name"` and `"special"` are not in the key.
  - `xbarOf(text) -> string | null`: the last `xbar{12x8:` with its 384 hex digits and `}`, as it stands; `null` when not all of it is there.
  - `reportOf(text) -> string | null`: the text up to the end of chip L's status row, when the text holds "Bridge Array", "Chip Status" after it and twelve chip rows after that, the twelfth ended by a line end. `null` before. Colour codes do not stop it.
  - **The trace**, JSON Lines. Line 1: `{"h": 1, "what": "routing lab port 7 trace", "source": "board" | "built", "fw": text or null, "about": text}`. Then one line an exchange, in order: `{"t": seconds since the first, "sent": "N" | ":ver\n" | ":crossbar\n" | "b", "got": the reply as received, or null when none came}`.
  - `class FakePort`: `new FakePort(traceText, {gapMs: 1})`. It has what a `SerialPort` has that the link uses: `readable`, `writable`, `open(options)`, `close()`, `getInfo()` (the ids of `FILTER`), `forget()`. A write is answered by the next exchange at or after its place in the trace whose `sent` is what was written; when there is none ahead, by the last one behind. A `got` of `null` is no answer. For the tests: `written` (every write, in order), `opened` (the options `open` got), `closed`, `forgotten`, `most` (the most writes ever unanswered at once), `hush()` and `speak()` (stop answering; start again, and answer a write that was left waiting), `cut(n)` (the next answer stops after `n` characters), `add(text)` (bytes nobody asked for), `pull()` (the cable out: `readable` ends).
- `tests/fixtures/port7_built.jsonl`: four routings in turn (`same_chip_pairs`, `sf_to_sf`, `k_rows_overflow_metric`, `same_chip_pairs` again). For each, the exchanges a link makes on a still board: `N`, `:crossbar\n`, `b`, `:crossbar\n`, then three more of `N`, `:crossbar\n`. Before the first come the two of connecting: `N`, and `:ver\n` answered `:ver\r\nJumperless firmware version: 0.0.0.0\r\n`. The `b` and `:crossbar` answers are the captures' files as they are (taken on port 1 and port 7, colour codes stripped). The `N` answers are made up in the shape `JsonState.cpp` prints, from each report's Bridge Array, because no `N` reply was ever captured. Its header says `"source": "built"` and says all of that in `about`.
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
const nets = (volts, nodes) => '{\r\n  "nets": [\r\n    {\r\n      "index": 6,\r\n      "name": "Net 6",\r\n      "nodes": '
  + JSON.stringify(nodes) + ',\r\n      "special": "adc",\r\n      "voltage": ' + volts + "\r\n    }\r\n  ]\r\n}\r\n";

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
    const text = fs.readFileSync(path.join(CAPTURES, file), "utf8");
    const whole = P.reportOf(text);
    assert.ok(whole && whole.includes("Bridge Array") && whole.includes("Chip Status"), file);
    assert.equal(P.reportOf(text.slice(0, text.lastIndexOf("\nL") + 20)), null, file);      // inside the last row
    assert.equal(P.reportOf(text.slice(0, text.indexOf("Chip Status"))), null, file);
  }
  assert.ok(P.reportOf(cap("sf_to_sf", ".b.txt").replace(/^(\d+\t)/gm, "\x1b[38;5;196m$1")));   // colour codes
});

test("the nets key ignores what is measured and changes when a node does", () => {
  assert.equal(P.netsKey(nets("1.203", ["1", "ADC0"])), "6:1,ADC0");
  assert.equal(P.netsKey(nets("3.300", ["1", "ADC0"])), "6:1,ADC0");
  assert.notEqual(P.netsKey(nets("1.203", ["1", "2", "ADC0"])), "6:1,ADC0");
  assert.equal(P.netsKey(nets("1.203", ["1"]).slice(0, 60)), null);             // not all of it yet
  assert.equal(P.netsKey('{"nets":[]}\r\n'), "");
  assert.equal(P.netsKey('{"error":"blocked","cmd":"!","reason":"not_a_command"}\r\n'), null);
  assert.equal(P.netsKey("\r\n\tMenu\r\n\tm = show this menu\r\n"), null);      // the main port's answer to N
  assert.equal(P.netsKey("oled_b64{128x32:AAAA}\r\n" + nets("0.000", ["1", "2"])), "6:1,2");
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
  const first = await ask("N", P.netsKey);
  assert.equal(await ask(":crossbar\n", P.xbarOf), P.xbarOf(cap("same_chip_pairs", ".xbar.txt")));
  for (let i = 0; i < 4; i++) { await ask("N", P.netsKey); await ask(":crossbar\n", P.xbarOf); }
  assert.notEqual(await ask("N", P.netsKey), first);                            // the second routing
  for (let i = 0; i < 40; i++) await ask("N", P.netsKey);                       // past the end: the last answer again
  assert.equal(await ask("N", P.netsKey), first);                               // the fourth routing is the first again
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
        head = json.loads(TRACE.read_text().split("\n")[0])
        self.assertEqual((head["h"], head["source"]), (1, "built"))

    def test_the_port_code_under_node(self):
        p = subprocess.run(["node", str(HERE / "board_port_test.js"), str(CAPTURES), str(TRACE)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(subprocess.run(["node", "--check", str(server.WEB_DIR / "board_port.js")]).returncode, 0)
```

- [ ] **Step 2: Run** `python3 -m unittest discover -s Routing/tests -t Routing -k test_board_port`. Expected: no `board_port.js`, no fixture.
- [ ] **Step 3: Implement.** The three readers first, then `FakePort`, then `built_trace` and the fixture it writes.
- [ ] **Step 4: Run all tests.** Expected: pass.
- [ ] **Step 5: Commit** `Routing lab: a board's port 7 replies read in the page's own code, and a fake port that replays a trace`.

---

### Task 3: The link: prove the port, then ask, one query at a time

**Files:**
- Modify: `Routing/web/board_port.js`, `Routing/tests/board_port_test.js`

**Interfaces:**
- Consumes: Task 2's readers, `FakePort`, the trace.
- Produces:
  - `new BoardLink(port, on, opts)`. `on` is `{reading(r), state(name, words)}`. `opts` may override any timing of `BOARD_PORT` (the tests run with a few milliseconds each) and gives `hidden()`, which answers whether the page is out of sight (default: never).
  - `await link.connect() -> {fw}`: opens the port (`{baudRate: BAUD, bufferSize: BUFFER}`), starts the one reader, sends `N`. With a net list back inside `PROBE_MS` it asks `:ver\n`, as any query is asked, and reads `firmware version: X`; `fw` is `null` when the board answers that verb with its JSON error. It throws `LinkError` with `.kind`:
    - `"busy"`: `open` failed with `NetworkError`. Nothing was sent.
    - `"not_port_7"`: no net list came. Exactly one byte was sent. The port is closed before the throw.
    - `"gone"`: the port ended.
  - `await link.run()`: the loop below, until `close()` or the port ends. It never throws.
  - `link.again()`: the next round asks for the report whatever changed.
  - `await link.close()`: stops the loop, lets go of the reader and the writer, closes the port.
  - `link.trace() -> string`: the header and the last `TRACE_MAX` exchanges, as Task 2's format, `"source": "board"`.
  - A reading: `{n: count from 1, b: the report's text, xbar: "xbar{12x8:...}" or null, fw, at: ms since 1970}`.
  - States, each with words for the page: `"probing"`, `"live"`, `"waiting"` ("the board has not answered for N s. It answers port 7 from its main loop only: not in probe mode, a menu or an app. Last read HH:MM:SS."), `"lost"` ("the board is gone: unplugged, or the port was closed").

**The loop (binding).** It keeps: `key` (the nets key the last report was asked under), `B` (the last report), `afterB` (the dump read right after it), `shown` (the dump of the last reading given, or `null`), and the last `STEADY_READS` dumps. The steady dump is the dump when those are all the same, else none.

1. While `hidden()`, wait and send nothing.
2. Ask `N` for the nets key `k`. Ask `:crossbar\n` for a dump.
3. If `k` is not `key`, or there is a steady dump and it is not `afterB`, or `again()` was called: ask `b` for `B`, then `:crossbar\n` for `afterB`; set `key`. Give a reading with `B`, and with `afterB` as its `xbar` when `afterB` is the steady dump, else `null`.
4. Else, if there is a steady dump, it is `afterB`, and it is not `shown`: give a reading with the same `B` and that dump. The report is not asked again.
5. Wait `POLL_MS`. Go to 1.

**Asking (binding).** One query is out at a time. Its reply is whatever the reader for it (`netsKey`, `xbarOf`, `reportOf`, the version line) first finds in the text received since it was sent; the rest of that text is dropped. The probe is the one query with a limit: no net list in `PROBE_MS` means it is not port 7. Bytes that come while nothing is out are dropped. A reply that has not begun is waited for without end: after `WAIT_SAY_MS` the state is `"waiting"`, and nothing is sent. A reply that began and then got no byte for `STALL_MS` is thrown away and the same query sent once more. A read error is not the end: the reader is taken again from `port.readable` (as `lineChannel.ts:29-46` does); only a `readable` that is gone is `"lost"`.

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
const VER = { sent: ":ver\n", got: ":ver\r\nJumperless firmware version: 0.0.0.0\r\n" };

test("a port that is not port 7 gets one byte and is closed", async () => {     // Review Focus 1
  const menu = HEAD + JSON.stringify({ t: 0, sent: "N", got: "\r\n\tMenu\r\n\tm = show this menu\r\n" }) + "\n";
  const port = new P.FakePort(menu);
  const [link] = linked(port);
  await assert.rejects(link.connect(), (e) => e.kind === "not_port_7");
  assert.deepEqual([port.written, port.closed], [["N"], true]);
  const held = new P.FakePort(menu);
  held.open = async () => { throw Object.assign(new Error("Failed to open serial port."), { name: "NetworkError" }); };
  await assert.rejects(linked(held)[0].connect(), (e) => e.kind === "busy");
  assert.deepEqual(held.written, []);
});

test("a still board is read once, and its dump is believed at the third reading", async () => {   // Review Focus 3, 4
  const port = built();
  const [link, seen] = linked(port);
  assert.deepEqual(await link.connect(), { fw: "0.0.0.0" });
  assert.deepEqual(port.written, ["N", ":ver\n"]);
  link.run();
  while (seen.readings.length < 8) await sleep(5);
  await link.close();
  assert.deepEqual(seen.readings.map((r) => r.xbar === null), [true, false, true, false, true, false, true, false]);
  assert.equal(seen.readings[1].b, seen.readings[0].b);                         // the same report, now with its dump
  assert.equal(seen.readings[1].xbar, P.xbarOf(cap("same_chip_pairs", ".xbar.txt")));
  assert.ok(seen.readings[4].b.includes("numberOfPaths"));
  assert.equal(port.written.filter((w) => w === "b").length, 4);                // one report a routing, not one a tick
  assert.equal(port.most, 1);                                                   // never two queries out (Review Focus 7)
});

test("a silent board is waited for, not asked again", async () => {             // Review Focus 2
  const port = built();
  const [link, seen] = linked(port);
  await link.connect();
  link.run();
  while (seen.readings.length < 2) await sleep(5);
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
  port.cut(20);                                                                 // the first N of the loop stops after 20 characters
  link.run();
  while (seen.readings.length < 1) await sleep(5);
  await link.close();
  assert.deepEqual(port.written.slice(2, 4), ["N", "N"]);
  assert.ok(P.reportOf(seen.readings[0].b));
});

test("a dump that will not hold still never reaches the judge", async () => {   // Review Focus 3
  const x = [P.xbarOf(cap("same_chip_pairs", ".xbar.txt")), P.xbarOf(cap("sf_to_sf", ".xbar.txt"))];
  const n = { sent: "N", got: nets("0", ["1", "2"]) };
  const steps = [n, VER, n, { sent: ":crossbar\n", got: x[0] }, { sent: "b", got: cap("same_chip_pairs", ".b.txt") }];
  for (let i = 0; i < 200; i++) steps.push({ sent: ":crossbar\n", got: x[i % 2] }, n);     // the dump differs at every reading
  const port = new P.FakePort(HEAD + steps.map((s, i) => JSON.stringify(Object.assign({ t: i }, s))).join("\n") + "\n");
  const [link, seen] = linked(port);
  await link.connect();
  link.run();
  await sleep(150);
  await link.close();
  assert.deepEqual(seen.readings.map((r) => r.xbar), [null]);
  assert.equal(port.written.filter((w) => w === "b").length, 1);
});

test("bytes nobody asked for, a hidden page, a pulled cable", async () => {     // Review Focus 6, 9
  const port = built();
  let hidden = false;
  const [link, seen] = linked(port, { hidden: () => hidden });
  await link.connect();
  port.add("oled_b64{128x32:AAAA}\r\n");
  link.run();
  while (seen.readings.length < 2) await sleep(5);
  hidden = true;
  await sleep(40);
  const sent = port.written.length;
  await sleep(80);
  assert.equal(port.written.length, sent);                                      // out of sight: nothing is asked
  hidden = false;
  link.again();
  while (seen.readings.length < 3) await sleep(5);
  port.pull();
  while (seen.states.at(-1)[0] !== "lost") await sleep(5);
  const trace = link.trace().trim().split("\n").map((line) => JSON.parse(line));
  assert.equal(trace[0].source, "board");
  assert.deepEqual(trace.slice(1, 3).map((e) => e.sent), ["N", ":ver\n"]);
});
```

- [ ] **Step 2: Run** `python3 -m unittest discover -s Routing/tests -t Routing -k test_board_port`. Expected: `BoardLink` is not a constructor.
- [ ] **Step 3: Implement.** One read loop that appends to a text and wakes whoever waits; `ask(text, reader)` on top of it; `connect`; the loop as written above, no more.
- [ ] **Step 4: Run all tests** three times over. Expected: pass each time (the tests run on real clocks of a few milliseconds; one that fails one time in three is a bug in the link, not in the test).
- [ ] **Step 5: Commit** `Routing lab: a link to a board's port 7 that proves the port, asks one thing at a time and waits for a silent board`.

---

### Task 4: The page: connect, show, redraw, light what changed

**Files:**
- Modify: `Routing/web/lab.js`, `web/index.html`, `web/lab.css`, `Routing/server.py`, `Routing/lab.py`, `Routing/export.py`, `Routing/tests/test_server.py`, `tests/test_export.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `BoardLink`, `FakePort`, `serialWhyNot`, `BOARD_PORT`; Task 1's `/api/board`; `api`, `selectCase`, `redraw`, `renderBattery`, `showProblem`.
- Produces:
  - `index.html`: `<script src="board_port.js"></script>` before `lab.js`. Under the drop hint, `<div class="row" id="link-row">` with `<button id="connect" type="button">Connect a board</button>`, `<button id="link-again" type="button" class="quiet" hidden>read again</button>`, `<a id="link-trace" hidden>save trace</a>`; `<p id="link-status" class="hint">`; and `<details id="link-sends" class="hint">` whose text is the paragraph "What the page sends" below.
  - `export.py`: the `board_port.js` tag is replaced by the file's text, as the `lab.js` tag is, so that `lab.js` never names a thing that is not there; `index.html` without that tag raises as the others do. The page hides the row (an exported page has no judge).
  - `lab.py serve --replay FILE`: the server holds the file's text. `/api/info` gains `"replay": true | false`. `GET /api/replay` answers `{"trace": text}`, or 404 when the server was started without it. A file that is not a trace (its first line is not the header of Task 2) stops `serve` with the reason.
  - `lab.js`:
    - `LINK_CASE = "live_board"`.
    - `state.link = {link: BoardLink | null, name: "idle" | "probing" | "live" | "waiting" | "lost", words: "", fw: null, changed: null, held: null, granted: []}`. `granted` is what `navigator.serial.getPorts()` gave when the page loaded, so that a click need not wait to know.
    - `async function connectBoard()`: the button's click. With `state.info.replay`, the port is `new FakePort((await api("/api/replay")).trace, {gapMs: 300})` and no picker opens. Else, with exactly one port in `granted`, that port. Else `navigator.serial.requestPort({ filters: [BOARD_PORT.FILTER] })`, the first thing the click does (the picker needs the click). Then `connect()`, then `run()`. On `"not_port_7"`: `port.forget()` where the browser has it, and the words "That port is not the board's fourth. Nothing but one N was sent to it. Pick the one whose name ends port7 (macOS), or the last of the four." On `"busy"`: "Port 7 is open in another program or tab (a Jumperlessim viewer, a script). Close it there, then connect again." A second click on the button, now "Disconnect", closes the link.
    - `async function showReading(r)`: posts `{name: LINK_CASE, text: r.b + "\n" + (r.xbar || ""), about, unsteady: r.xbar === null, live: true}` to `/api/board`. `about` is "a V5's own routing, read over port 7 at HH:MM:SS, firmware X; not a run of the lab's router".
    - `function renderLink()`: the button's label, `#link-status`, and whether "read again" and "save trace" show.
    - `function drawChanged()`: the marks of `state.link.changed` on the fabric view and the crossbars view.
- **What the page sends** (the text of `#link-sends`, binding): "To the board's fourth port only: N (its net list) and :crossbar (which crosspoints are closed) twice a second, :ver once, and b (its routing report) when one of the first two changed. All four are questions: none makes, removes or reroutes a connection. Two things b does besides answering: it prints "Couldn't find a path" on the board's main terminal for every bridge that did not route, and it marks those paths as failed again, as the router did when it routed. Nothing is sent to any other port, and nothing before you press Connect. The picker lists the board's four ports and they look alike: pick the one whose name ends port7 (macOS), or the last of the four. Opening the second one by mistake can reset an Arduino plugged into the board."

**How a reading is shown (binding):**
1. The first reading does what a pasted report does (`showBoards`): the run shown becomes the board's, class `board`, and the case `live_board` is selected.
2. A later reading replaces that case's row and nothing else of the table. When `live_board` is the case selected, its entry in `state.cases` is dropped, its result and paint are fetched again, and `renderCase()` and `redraw()` run. The view's zoom and place, which views are open, the net lit alone, the bridge picked and the legend's choice stay as they were. `selectCase` is not called.
3. When another case is selected, or the run shown is not the board's (the user pressed Run), the reading is still posted, the row is updated when it is on screen, and the view is not touched. The status line says "the board changed at HH:MM:SS".
4. While `state.busy`, the newest reading is held in `state.link.held` and shown when the run is done. Older held ones are dropped.
5. `state.link.changed` is set from an answer whose `changed` holds anything, and stays until the next one that does: a reading that only brought the dump does not clear it.
6. **What changed, lit.** A crosspoint in `closed` gets a ring in `--changed` (a colour of the page that is not `--problem`). A crosspoint in `opened` is drawn hollow and grey where it was. A bridge in `bridges` has its row marked in the case panel, with "was routed, now unrouted" in words. The case panel's head says how many of each, and a click on that count shows them alone, as a legend key does.
7. The link's state is said in `#link-status` and never by colour alone. `"waiting"` and `"lost"` dim the view's title and add "last read HH:MM:SS"; they add no red.
8. Without Web Serial, the button is disabled and `#link-status` holds `serialWhyNot`'s sentence. On an exported page (`STATIC`) the whole row is hidden, as the drop hint is.
9. A reload does not connect. When `navigator.serial.getPorts()` holds exactly one port, the button says "Connect the board again" and its click uses that port with no picker; the port is proved again with `N`. With none, or more than one, the click opens the picker.
10. "save trace" downloads `link.trace()` as `port7_<date>_<time>.jsonl`.

- [ ] **Step 1: Write the failing tests.** In `test_server.py`: a server made with a replay file answers `/api/info` with `replay` true and `/api/replay` with the file's text; without one, `replay` is false and `/api/replay` is 404. `/board_port.js` is served. `lab.js` holds `"/api/replay"`, `function connectBoard`, `async function showReading`, `function drawChanged`, `requestPort({ filters: [BOARD_PORT.FILTER] })`, `"live_board"` and `.forget(`; it does not hold `setSignals`, `baudRate: 1200` or `:oled`; it passes `node --check`. `index.html` has `id="connect"`, `id="link-sends"` and the words "Nothing is sent to any other port". `lab.css` gives no rule that names `changed` the colour `--problem`. In `test_export.py`: an exported page has no `<script src=` left in it and holds `class BoardLink`, and `lab.js` holds `$("link-row").hidden = Boolean(STATIC)`. In `test_cli.py`: `serve --replay` with a file that is no trace exits 1 naming the file.
- [ ] **Step 2: Run to see them fail.**
- [ ] **Step 3: Implement.** `showReading` shares the posting with `showBoards` and nothing of its state handling.
- [ ] **Step 4: Run all tests.**
- [ ] **Step 5: Check it in the browser**, in Chrome, with `python3 Routing/lab.py serve --replay Routing/tests/fixtures/port7_built.jsonl`:
  1. In the console, `window.isSecureContext && "serial" in navigator` is true on `http://127.0.0.1:8765/`. If it is false, stop and report: the plan's first call is wrong.
  2. Press Connect. The case `live_board` appears, class `board`, with 7 bridges; its notes first say the dump was not read three times, and within about a second that note goes.
  3. The fake board moves to `sf_to_sf`: the drawing changes by itself, 32 crosspoints are ringed as new, 16 are hollow grey, and nothing is red. The case panel names 14 bridges changed.
  4. Zoom in on chip K and light one net alone. At the next change the zoom and the lit net are as they were.
  5. The third routing has one bridge that did not route: it is drawn as any unrouted bridge is, and its row says "was routed, now unrouted".
  6. Press Run on `dense` while the board is linked. The battery shows; the status line says the board changed; the view is the battery's. Click `live_board`'s row: it is the newest reading.
  7. Open `#link-sends`: the paragraph is there. "save trace" gives a file whose first line is the header and whose `sent` values are only the four.
  8. Start the server without `--replay`, in Firefox: the button is disabled and names Chrome. Paste a `b` report: it still works.
  9. `lab.py export` a page and open it: there is no Connect button.
  Screenshot the third for Kevin.
- [ ] **Step 6: Commit** `Routing lab page: connect a board, see its routing redraw when it changes, with what changed lit`.

---

### Task 5: The bench check (needs Kevin's go-ahead)

One sitting with a V5 plugged into the Mac. Nothing is flashed and no file on the board is written. The page sends its four things. One more question is typed by hand in a terminal on port 7, with the page disconnected: `:bench:nets` and `:bench:crossbar`. `:bench` times a verb on the board and prints `bench{verb,min_us,avg_us,max_us,bytes}`; it also sets that verb's floor for `:every` in RAM, until the next boot (`Ser3Backchannel.cpp:896-928`). **Do not start it until Kevin says the board is plugged in and he is ready**: he makes connections with the probe, and he reads his own terminal.

**Files:**
- Create: `Routing/tests/fixtures/port7_<date>.jsonl`
- Modify: `Routing/web/board_port.js` (the timings, if the board says otherwise), `Routing/tests/board_port_test.js`, `Routing/tests/test_board_port.py`, `Routing/fidelity/README.md` (one paragraph: what was checked, on which firmware)

- [ ] **Step 1: Kevin's terminal on port 1, the page on port 7.** Kevin has his usual terminal (or the desktop app) on the main port. The lab runs with no `--replay`. Before Connect, write down what Chrome's picker shows for each of the four ports. Press Connect and pick the fourth.
- [ ] **Step 2: Write down, each as seen:**
  1. The probe: `N` answered with a net list. The firmware version shown.
  2. `b` on port 7 gives a report the lab reads: `live_board` appears and matches what is on the breadboard. Whether the reply begins with an echo.
  3. Kevin's terminal shows nothing while the board is still.
  4. Kevin connects two rows with the probe. Does the page go to "waiting" while probe mode is on, and show the new bridge when it is left? How long after?
  5. Kevin makes a bridge that cannot route (or loads a slot that has one). Each report puts one "Couldn't find a path" line on his terminal and no more than one a change.
  6. With the net scan on (the default) and the board still for one minute: how many of the dumps read differ from the one before. Does "sent equals planned" get checked, or does the note stay. Is anything ever red that is not a fault.
  7. `:bench:nets` and `:bench:crossbar` on port 7: the average microseconds and the bytes of each. A stopwatch on the trace: from `b` sent to its reply whole.
  8. Whether the board's own LEDs, probe and menus feel as they do unlinked. Kevin says.
  9. Open the same port in a second tab: the second says the port is busy. Pull the cable: the page says the board is gone. Plug it back: how many ports does `navigator.serial.getPorts()` hold, and is the one port 7? Press Connect.
  10. Two `b` in a row on a still board: the same report and the same dump, and Kevin's board behaves as before.
  11. Kevin clears the board (`x` on his terminal). Does the report still list a bridge? The page shows a case with nothing on it, or with the feed alone, and everything else as opened.
- [ ] **Step 3: Save the trace** of that sitting as `tests/fixtures/port7_<date>.jsonl`. Add a test that replays it through `FakePort` and wants: every reading's report read by `board.result` with no "not a V5 b report", and the bridges Kevin made, by their nodes. Add its numbers to "Measured" in the README.
- [ ] **Step 4: Set the timings from what was seen.** `POLL_MS` so that `N` and `:crossbar` together take under one part in fifty of the board's time, by `:bench` (one in fifty is this plan's call; Kevin may want another). `STEADY_READS` so that a still board with the scan on is checked. If no number does that, leave 3 and say so in the README: with the scan on, "sent equals planned" is not checked for a live board. If `b` cannot be asked on port 7 at all, stop: the plan needs the firmware, and that is Kevin's call.
- [ ] **Step 5: Run all tests.**
- [ ] **Step 6: Commit** `Routing lab: the live board checked against a V5, its trace kept, its timings set from the board`. In the body: the eleven things of Step 2, each with what was seen.

---

### Task 6: Documents

**Files:**
- Modify: `Routing/README.md`, `Routing/docs/DESIGN_ROUTING_LAB.md` (status)

- [ ] **Step 1: README.** Under "The page", one bullet "A live board". A section "A live board" after "A board's own output": what Connect does; which port and how to pick it; the paragraph "What the page sends", word for word; what the board does not answer during (probe mode, a menu, an app) and what the page shows then; when "sent equals planned" is checked and when it is not; what "changed" lights; the browsers; `serve --replay` and the trace file; that it is V5 only, one board at a time, and reads only. "What it does not check" gains: a live board is read between its rebuilds, not during them; a crosspoint closed for less than three readings is not seen; net voltages are not shown.
- [ ] **Step 2: Design.** The status line (piece 7 built, on the local server), and under piece 7 what was built differently, with Task 5's numbers.
- [ ] **Step 3: Run all tests.**
- [ ] **Step 4: Commit** `Routing lab: the live board documented`.

---

## Not in this plan

- **The published page.** `slopswap.org/routing-lab/` has no judge until piece 6 is built. Until then a live board is the local lab's. See "After this plan".
- **Writing to the board.** The page does not send the netlist made by clicking nodes to the board, clear it, load a slot or pause its net scan. It asks, and that is all.
- **Anything in the firmware.** Four things would make this better and all are under `JumperlOS/src/`: a line pushed on port 7 when the routing changes, or a verb for `routingGeneration`; `couldntFindPath` printing to the port that asked; port 7 answered in probe mode and the menus; the report and the dump in one reply.
- **Two boards at once.** Every V5 has the same serial string, so the page cannot tell them apart. One link, one case named `live_board`.
- **The OG Jumperless.** Running JumperlOS it has the same USB ids (`boards/jumperless_og.json:5-6`), so the picker lists it. The lab reads V5 reports only (`Routing/README.md:204`); an OG's report is refused with the lab's usual message.
- **Browsers without Web Serial.** No WebUSB stand-in (JumperIDE carries one, `app.js:26`), no helper program, no phone. Paste and drop stay as they are.
- **The board's LEDs, OLED and voltages.** That is Jumperlessim's viewer. This page shows routing.
- **A recording to play back for visitors.** `--replay` is for the tests and the browser check.

## After this plan

When piece 6 is built, the live board comes with it and needs no new code in the page: `showReading` asks `/api/board` through `api()`, and the engine in the tab answers that path with the same JSON ("a board's `b` output pasted or dropped" is already on piece 6's list of what runs live). What piece 6's plan must add: `board_port.js` in the bundle, `board.changed` reached by the engine's `/api/board`, and one check on `https://slopswap.org/routing-lab/` with a board, which again needs Kevin. The docs page for the curious then has a Connect button too.

The firmware asks above go to Kevin as a list with the lines they touch. With a change counter on port 7 the page asks one short question a round and the report only when the number moved; the steady-dump rule and the nets key go away.
