# Routing lab, plan 8: a watch command on port 7, and the firmware's fixes

> **Written 2026-11-23, by reading the firmware and the lab and by running the lab on scratch variants. No board was
> touched.** Nothing in it has run on a board. The firmware lines cited are of the worktree `JumperlOS-port7` at
> `44b1ba9`; the router files there are the pinned submodule's (`5374d38`). The page's files are cited by function name.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The board says on port 7 when its routing has changed, so the lab's page stops asking twice a second; and the five firmware fixes piece 7 listed are built: `:paths` free of sense taps (F1), `b` and `n` on port 7 silent on the main terminal (F2), port 7 answered in probe mode and the menus (F3), the probe's feed falling back when its pair does not route (F4), and the tap reserve applying only while the net scan is on (F5). Everything is proved as far as a host can prove it. The bench comes later.

**Architecture:** The firmware gains one verb, `:watch`, with one topic, `routing`. While it is on, the port's own service writes `changed{routing,<n>}` at the end of a pass when the generation moved and the board is idle. The rules that have no hardware in them (what a `:watch` line asks, when a line is due, what a modal context answers) live in one header checked by a host program. The fixes are six firmware commits, one a fix, ordered so the two that change behaviour inside the router and the probe loop (F4, F3) come last and each can be dropped alone. F4 and F5 are proved by the lab itself on the changed router. The page's link (`web/board_port.js`) asks for the watch after connecting, waits for `changed{}` lines, and keeps a slow `:gen`.

**Tech Stack:** C++ (arduino-pico, PlatformIO 6.1.19 in a throwaway venv), a host `c++` for the rules check; Python 3 standard library and `node` for the lab; MkDocs Markdown for the documentation site (edited, not built). No package is added.

**Spec:** `Routing/docs/DESIGN_ROUTING_LAB.md`, the section "Piece 8: told, not asked, and the firmware's fixes". It is binding: where this plan and it disagree, this plan is wrong. Also read: "Piece 7: a live board" and "Piece 7 as built" there, `PLAN_ROUTING_LAB_7_LIVE_BOARD.md` (its Global Constraints hold here too), and `NOTES_2026-11-23_FIRMWARE_PORT7_AND_TAPS.md` ("the notes").

Decided here, where Kevin's brief was silent, and his to overrule: the reply shapes of `:watch` (JSON, as `:padgate` and `:oled:stream` answer); `:watch:<topic>` with no state is a question; a watch ends at a fall of DTR; `:stop` does not end one; the slow poll is 3 s, two readings are 100 ms apart, the `off` at Disconnect waits 300 ms; F2 produces no failure lines for a port 7 asker; F3 answers a short list and refuses the rest with `busy`, only on a V5, and leaves the main loop's call where it is; F4's bar lasts until a user bridge is removed; F5 leaves the bounce-chip ranking alone and asks for a rebuild when the setting changes; the documentation site is edited in a worktree of its own.

## Global Constraints

- **Three repositories, nothing pushed in any.**
  - Firmware: the worktree `~/Documents/GitHub/JumperlOS-port7`, branch `port7-routing-reads`. It has no upstream on purpose: a push to JumperlOS `main` publishes a release. Never `~/Documents/GitHub/JumperlOS` itself. `.pio/**/firmware.uf2` is tracked, is rewritten by every build, and is never staged. `.github/workflows/release.yml` is never touched.
  - Lab: `~/Documents/GitHub/Jimulator`, branch `main`.
  - Documentation site: a new worktree `~/Documents/GitHub/Jumperless-docs-port7` on a new branch `port7-watch` off `origin/main`. Never the checkout `~/Documents/GitHub/Jumperless-docs` itself: it has 40 uncommitted changes, both target pages among them.
- Files staged by name. One commit a task in each repository the task touches. No attribution lines in commit messages.
- **No board is flashed and no serial port is opened.** The bench checks are written and compiled (`python3 -m py_compile`), not run.
- **Nothing under `Routing/harness/` is edited or added to**, and nothing under Jimulator's `JumperlOS/` submodule.
- **The firmware build.** `pio` under the system Python is broken on this Mac: `python3.13 -m venv <scratch>/pio313`, `<scratch>/pio313/bin/pip -q install platformio==6.1.19`, then `<scratch>/pio313/bin/pio run -e jumperless_v5 -e jumperless_og` in the worktree. After every firmware task: both environments build, `test/test_routing_og/run.sh` exits 0, and `git status --short` names only that task's files and the `firmware.uf2`.
- **The lab pointed at the worktree.** `JUMPERLOS=$HOME/Documents/GitHub/JumperlOS-port7` makes the worktree the lab's firmware (`variants.py`, `REPO`). Without it the lab reads its pinned submodule, which has none of the fixes. Lab tests in this plan pass both ways: on the pinned router they hold today's behaviour, on the worktree the fix.
- **The page.** Seven things, and no other byte: `N`, `:ver\n`, `:gen\n`, `:paths\n`, `:crossbar\n`, `:watch:routing:on\n`, `:watch:routing:off\n`. One query unanswered at a time. A `changed{}` line is not a reply. Every other constraint of plan 7 on the page holds (nothing sent before Connect, no `:` before `N` is answered, 115200 only, names use `link`, `board`, `moved`).
- Tests: `python3 -m unittest discover -s Routing/tests -t Routing` passes (385 tests on 2026-11-23, 51 s) with `JUMPERLOS` unset, as it is run today. The two classes this plan adds (`Reserve`, `Feed`) pass with it set and unset. Not established: that the rest of the suite passes with it set; a failure there is reported, not mended here.
- Style of every document touched: plain sentences, no em dashes, say what a thing does and what it does not.

## Measured before writing this plan (2026-11-23; no board was touched)

Firmware paths are under `~/Documents/GitHub/JumperlOS-port7/`. Lab paths are under `Routing/`.

**The port**

- **One entry, one caller.** `SingleCharCommands::serviceUSBSer3()` (`src/tubes/Ser3Backchannel.cpp:1174-1305`) is called only from `JerialClass::service()` (`src/Jerial.cpp:1168`), which runs at `src/main.cpp:1206` and at `src/Menus.cpp:908` (a click menu shown on the terminal with line buffering on). Its loop has no `return`: every branch ends in `continue`.
- **The probe loop** is `probeTick(s); jOS.serviceInner();` (`src/Probing.cpp:4390-4399`). `serviceInner` runs the services whose `inInnerSet()` is true (`src/JumperlOS.cpp:310-354`); the click menus, pad menus, apps and MicroPython's delay call it too (`servicePython`, `:371`). `LedDumpService` is the model of an inner-set service with a period (`src/JumperlOS.h:554-568`, `src/JumperlOS.cpp:693-720`, registered at `src/main.cpp:593`).
- **The modal flags.** `probeActive` is set at a session's first tick and cleared at its end (`src/Probing.cpp:3025`, `:4216`; `src/main.cpp:742`). `inClickMenu` and `inPadMenu` are `src/Menus.h:38` and `src/Probing.h:400`.
- **The scan does not tap in those modes.** It returns while `inClickMenu` or `inPadMenu` is set (`src/sensing/NetVoltageScan.cpp:1419`) and taps only when `probeActive == 0` (`:1484`). A guide's one-shot tap is held off by probe mode (`:610`) but not by a menu (`:1393-1395`).
- **`core2busy` is not only taps.** LED shows and path sends raise it too (`src/LEDs.cpp:3785`, `src/CH446Q.cpp:722`). `waitCore2()` gives up after 25 ms (`src/Commands.cpp:116-150`), so `:crossbar`'s four tries can take 100 ms.
- **A tap's claims are inside its `core2busy` window.** `fastConnectPath` claims the ledger as net 59 and `fastDisconnectPath` releases it (`src/routing/RouteSafety.cpp:1158`, `:1196`); both run between `core2busy = true` and `false` (`NetVoltageScan.cpp:1486-1546`, `:614-711`).
- **What pushes today.** `:oled:stream:on` sets a flag and frames are written from `oled::streamFrameToSer3()` when `USBSer3.availableForWrite() > 0` (`Ser3Backchannel.cpp:801-817`, `src/oled.cpp:4035-4049`). `:padgate:on` sets `debugProbing = 2` (`:844-849`). Neither is turned off by anything but its `off` verb, a config load, or a reboot. `:stop` only prints `{"stop":1}` (`:1231-1235`).
- **A write to a closed port is dropped.** `Adafruit_USBD_CDC::write()` loops while `tud_cdc_n_connected()`; that call is wrapped, and under `usb_cdc.ignore_dtr` it answers "connected" while the buffer drains and for 100 ms after (`src/tubes/usb_descriptors.cpp:604-650`). `USBSer3.dtr()` is the same wrapped call (framework `Adafruit_USBD_CDC.cpp:165-171`), so it is not the DTR line. `tud_cdc_n_get_line_state(itf)` is (framework `cdc_device.h:111`; include `tusb.h` if the build asks). USBSer3 is CDC interface 3 (`src/tubes/ArduinoStuff.cpp:210-212`).
- **`:help` and `:cmds` are made from `usbSer3_verbs[]`** (`Ser3Backchannel.cpp:79-112`, `:485-517`, `:594-595`). A row there documents a verb on the port itself.
- **`b` and `n`.** `cmd_showBridgeArray` and `cmd_showNetlist` take their stream from `Jerial.getResponseTarget()` and call `couldntFindPath( 1 )` (`src/SingleCharCommands.cpp:2096-2130`, `:1845-1856`). That function prints on `Serial` and marks in one loop (`src/routing/NetsToChipConnections.cpp:5431-5527`); the OG's copy prints but marks less (`src/routing/NetsToChipConnections_OG.cpp:4588-4650`). `changeTerminalColor` writes to `Jerial` whatever stream it is given, unless `disableTerminalColors` (`src/Graphics.cpp:447-470`).
- **`printChipStatus(Stream*)`** reads `chipStates[i].xStatus` and `yStatus` (`NetsToChipConnections.cpp:6823-6871`; the OG's at `NetsToChipConnections_OG.cpp:5806`). Its declaration is shared (`src/routing/NetsToChipConnections.h:89`). `chipStatus` is 84 bytes; the two status arrays are 24 (`src/routing/MatrixState.h:101-116`). The OG cannot spare a kilobyte of static RAM (`Ser3Backchannel.cpp:359-361`).
- **Host tests the firmware has:** `test/test_routing_og/run.sh` (the OG router and `RouteSafety.cpp`, `g++ -DOG_JUMPERLESS`; it does not link `InfraPaths.cpp`), `test/test_boards`, `test/test_detent_anchor`, `test/test_sip_anchor`, `tools/test_selftest_host.py`. None compiles the port or the command handlers.

**The feed (F4)**

- `infraEvaluate()` has three callers, all in `Commands.cpp` (`:241`, `:426`, `:643`), each followed by `bridgesToPaths` (`:268`, `:449`, `:685`). It picks the first candidate free of claims (`src/routing/InfraPaths.cpp:506-611`): DAC 0, then a GPIO scanned 8 to 1, or the other way round with `probe.power_source = 1` (`:288-362`). It never asks whether the pair routed.
- It runs before `clearAllNTCC()` in `refreshConnections` (`src/Commands.cpp:241`, `:246`) but after it in `refreshLocalConnections` (`:422`, `:426`). So the last rebuild's path table is not there to read at the head of the common rebuild: whether the pair routed must be noted when routing ends.
- `bridgesToPaths()` ends with `couldntFindPath(1); checkForOverlappingPaths(); validateAllPaths();` (`NetsToChipConnections.cpp:2626-2629`). It is also called with no evaluation before it: `Commands.cpp:551`, `src/LEDs.cpp:1060`, `:1124`, `src/sensing/FakeGpio.cpp:1350`.
- `pairPathStats` counts a pair's paths and crosspoints (`InfraPaths.cpp:892-908`, declared at `:648`). `infraServiceTick()` runs a pending nudge, and asks for a rebuild whenever the walk's first candidate is viable and not the active one (`:697-737`). It runs from the ProbeSwitch service, which is not in the inner set (`src/main.cpp:581`).
- **In the lab.** `InfraPaths.cpp` is compiled into the harness, and `routeCase` is `infraEvaluate(); clearAllNTCC(); blocks; loadBridgesFromState(); getNodesToConnect(); bridgesToPaths();` (`harness/lab_harness.cpp:138-179`). One process routes every case on its stdin, and the feed's state lives on between them (`:428-430`). `refreshLocalConnections` is a stub, so a nudge does nothing there. The runner routes each case twice and judges the first; a second that differs is the problem "the same case routed twice gives different routes" (`runner.py:185-189`, `:273`).
- **Run on the pinned router, all eight classes, 2273 cases:** the feed is unrouted in three, `k_rows_overflow_metric` (dense), `edge_1_10` (edge) and `nine_k_nets` (beyond). In all three the case bridges DAC 0, so the feed is on GPIO 6 and has no other candidate.
- **With the feed GPIO-first** (`probe (1, 1)`) on dense, stress, edge and typical: four cases leave the feed unrouted. In two of them, `gnd_two_rows_every_chip` (stress) and `edge_1_7` (edge), the same bridges route the feed when it is DAC-first.
- **Every router-side edit of Tasks 2, 4 and 5 together, as one scratch variant** (the pinned router with `printChipStatus`'s parameter in the V5 router and the header, `tapReserveOn()`, the hook's new name in `config.h` and `configManager.h`, and the fallback with its arming flag): 2273 cases, routed twice each, 0 differ from the pinned router in status, problems, report, crosspoints or metrics. The OG's router file and `configManager.cpp` are not compiled by the harness, so their edits are first compiled in the tasks' own builds. `gnd_two_rows_every_chip` GPIO-first, three times in one process: 16 primaries with `BUFFER_IN-GPIO_6` unrouted; then 17 with `[BUF_IN,DAC_0,…]` in the Bridge Array; then the second's report again. On the pinned router: 16, 16, 16.

**The reserve (F5)**

- Three tests begin with `routingDuplicatePathNow`: `reservedKRowForSenseTaps`, `reservedTapEscapeX`, `reservedTapEscapeY` (`NetsToChipConnections.cpp:583-587`, `:879-882`, `:916-918`). A fourth use only ranks bounce chips (`:5675`). None reads a setting. The OG router has none of it.
- The scan's switch is `measurement.net_currents`, default 1, with `HOOK_NONE`: a change runs nothing (`src/config.h:175`). `HOOK_PROBE_POWER_SOURCE` is the model of a setting that asks for a rebuild (`src/configManager.cpp:883-891`, `src/configManager.h:66`). Not established: that every way of changing the setting goes through the hook.
- Guide one-shot taps run with the scan off (`NetVoltageScan.cpp:1393-1395`).
- The harness has no knob for the scan (`lab_harness.cpp:80-133`); it runs with `config.h`'s default. `variants.resolve(spec, overrides={"src/config.h": bytes})` builds a variant with another default (`variants.py:132-168`).
- **The three tests changed, tried as a scratch variant:** scan on, all 2273 cases routed twice give the pinned router's report and crosspoints. Stacked copies, on the pinned router, the pinned router with the default at 0, the changed router, and the changed router with the default at 0: `kevin_fixture_2026_09_02` 0, 0, 0, 2; `rail_stacking_light` 3, 3, 3, 5, and only the last has the problem `no sense-tap route for 8 31 45 BUFFER_IN`. Over all classes with the scan off: stacked copies go up in example 3, dense 4, real 2, stress 8, edge 5, beyond 2, typical 160, fuzz 410 (594 cases) and down in typical 6 and fuzz 16; no case routes fewer primaries; three of the five taps proofs, `stacked_taps_reachable`, `stacked_taps_gpio_dups` and `rail_stacking_light`, fail; dead taps rise widely (`a_saved_board` 0 to 14).

**The page**

- `BoardLink.ask()` empties `this.text` when a reply is found (`web/board_port.js`, `ask`), so a `changed{}` line that arrives in the same chunk after a reply would be thrown away if only `ask` looked for it. The line must be found where bytes arrive (`pump`).
- `FakePort` skips trace lines with `"sent": null` (`FakePort` constructor) and answers a write only from an exchange with that `sent` (`answer`). A write with no such exchange is never answered, so every trace a test runs needs an answer to `:watch:routing:on\n`.
- Firmware at `44b1ba9` answers `:watch:routing:on` with `{"error":"unknown_verb","verb":"watch:routing:on"}` (`Ser3Backchannel.cpp:898-900`): the verb is the whole line.
- `BOARD_PORT.SENDS` and the word "five" are pinned by `tests/board_port_test.js`, `tests/test_board_port.py`, `tests/test_server.py`, `tests/link_page_test.js`, `web/index.html` (`#link-sends`), `web/lab.js` and `web/README.md`. `grep -rn "five\|SENDS" Routing/web Routing/tests` lists them.

**The documents**

- In the firmware repository the verbs are documented in three places only (checked by `grep` for `backchannel`, `USBSer3`, `:gen`, `:crossbar` and `port7` in the files the brief names): the table `usbSer3_verbs[]` (`:help`, `:cmds`), the VERBS comment in `src/tubes/Ser3Backchannel.h:75-94`, and `test/hil/README.md:41` (one row a test file). `:gen`, `:paths` and the waiting `:crossbar` are in all three already (`f963e4c`).
- `jumperless_skill/jumperless_skill.md` has no word on the backchannel (its port text is "Port discovery helper", lines 149-169). `jumperless_skill/jumperless_ports.json` maps ports to hardware ids and lists no verbs. `CodeDocs/JSERIAL_GUIDE.md` and `JSERIAL_QUICKREF.md` are about the jSerial routing library; USBSer3 is one endpoint name in each and no verb appears. No edit is planned in those three.
- `Ser3Backchannel.h:22` says the port "can NEVER change system state or block", and `:75` heads the verbs "all read-only".
- **The documentation site**, `~/Documents/GitHub/Jumperless-docs`: MkDocs (`mkdocs.yml`, source `docs/`, `site_url` `https://docs.jumperless.org`), hosted by Read the Docs (`.readthedocs.yaml`); no GitHub workflow. Branch `main`, one commit behind `origin/main`, 40 uncommitted changes. `site/` is committed build output and is not edited. Whether a push to `main` publishes is not established (it is a Read the Docs setting, not in the repository); treat it as publishing.
- The pages, at `origin/main`: `docs/07.5-automation.md` ("Which tool do I use?" row at line 21; "### 5. USBSer3 backchannel (4th port) — read-only telemetry" at 123, "never blocks and never changes state" at 125, the verbs bullet at 130, the `| Command | Returns |` table ending at 167, "### Implementation status" at 739) and `docs/jumperless-agent-skill.md` ("## Communication methods", the port 7 bullet at line 44). Neither names `:gen`, `:paths`, `:oled:stream`, `:padgate`, `:repeat` or `:stop`.

**Not established:** that Chrome raises DTR when it opens the port and drops it on close; what `n` (`listNets`) writes to port 1 for a port 7 asker besides the `couldntFindPath` lines; how long a `:paths` reply holds the probe loop; what the probe does while its feed is unrouted; that the OG's port 7 is used by anything. The bench checklist looks at each.

## File structure

| File | Responsibility |
|---|---|
| Firmware `src/tubes/Ser3Rules.h` (new) | The port's rules with no Arduino in them: `ser3WatchParse`, `ser3WatchDue`, `ser3ModalAnswers` |
| Firmware `test/test_ser3_rules/ser3_rules_check.cpp`, `run.sh` (new) | Their host check |
| Firmware `src/tubes/Ser3Backchannel.cpp`, `.h` (modify) | `:watch`, the `changed{}` line, the tap-free `:paths`, the modal entry and its refusals; the VERBS and ACCESS MODEL comments |
| Firmware `src/SingleCharCommands.cpp`, `.h` (modify) | F2 in `b` and `n`; `serviceUSBSer3(bool modal = false)` |
| Firmware `src/routing/NetsToChipConnections.h`, `.cpp`, `_OG.cpp` (modify) | `ChipLedger`, `printChipStatus(Stream*, const ChipLedger*)`; F5's `tapReserveOn()`; F4's one call |
| Firmware `src/routing/InfraPaths.cpp`, `.h` (modify) | F4: the note, the bar, the nudge |
| Firmware `src/config.h`, `src/configManager.h`, `.cpp` (modify) | F5: a rebuild when `net_currents` changes |
| Firmware `src/JumperlOS.h`, `.cpp`, `src/main.cpp` (modify) | F3: `Ser3ModalService`, registered on a V5 |
| Firmware `test/hil/test_port7_reads.py`, `test/hil/README.md` (modify) | Bench checks, written and not run |
| Firmware `jumperless_skill/jumperless_skill.md` (modify) | A section on port 7 and its verbs |
| Lab `tests/test_firmware_fixes.py` (new) | F5 and F4 on the router under test |
| Lab `web/board_port.js`, `web/lab.js`, `web/index.html` (modify) | The watch in the link; the seven; the words |
| Lab `tests/board_port_test.js`, `test_board_port.py`, `test_server.py`, `link_page_test.js`, `tests/fixtures/port7_built.jsonl` (modify), `tests/fixtures/port7_watch_built.jsonl` (new) | Tests |
| Lab `web/README.md`, `README.md`, `docs/DESIGN_ROUTING_LAB.md` (modify) | Documents |
| Docs site `docs/07.5-automation.md`, `docs/jumperless-agent-skill.md` (modify, in the docs worktree) | The port's verbs for the public |

## Review Focus

The failure modes the tests do not exercise and the bench is most likely to show. Each names its task.

1. **A reply written inside a reply.** The modal service and the main loop's call are two ways into one function with static state (`lastInquiry`, the static buffers of `:crossbar` and `:leds`). A handler that pumps `serviceInner` while it prints would let the other entry in. One flag, set for the whole of either pass, must be the first thing both test (Task 6).
2. **A host that holds the port and stops reading.** A reply larger than the buffer waits in `write()`. In the main loop that hangs the terminal today; after Task 6 it would hang the probe. The `changed{}` line is gated on room and cannot wait. Replies are not gated. Seen only at the bench (Tasks 3, 6).
3. **The probe loop's time.** A `:paths` reply between two ticks is about 4 kB. The service runs at most every 5 ms and a line is waited for 25 ms at most. `X` prints the tick gap; compare it with and without the page (Task 6, bench).
4. **A rebuild every half second.** `infraServiceTick` asks for a rebuild while the walk's first candidate is viable and not active. After a fallback that is the barred candidate, for ever, unless the tick leaves the barred one alone. The lab cannot see it: `refreshLocalConnections` is a stub there (Task 5).
5. **A note taken from a preview.** `bridgesToPaths` runs for slot previews and FakeGPIO with other bridges in the array. The note is taken only in a pass that `infraEvaluate` armed (Task 5).
6. **A watch nobody turned off.** A tab closed without Disconnect leaves it on. DTR's fall ends it only if the host raised DTR. Until then the lines go nowhere and cost one gated write a change (Task 3, bench).
7. **A `changed{}` line beside a reply.** In one chunk after a reply; split across two chunks; before the echo of the next query; while a query is out. The page finds it where bytes arrive, by a whole line, and no reader of a reply matches it (Task 7).
8. **The page meeting `busy`.** Every one of the seven must be on the modal list, or a board in probe mode answers a query with a refusal the page does not read (Tasks 3, 6, 7).
9. **The scan turned on after a rebuild made with it off.** Copies then sit on the copper the taps need until the next rebuild. The setting's hook asks for one; a way of changing the setting that skips the hook leaves taps dead until something else rebuilds (Task 4, bench).
10. **A removal that is not a removal.** F4's bar lifts when the count of user bridges drops. A swap of one bridge for another in one rebuild keeps the count, so the barred candidate waits for the next real removal (Task 5; said in a `ponytail:` comment).
11. **`:crossbar` in the OG's probe mode.** The OG's probe closes crosspoints of its own. Task 6 registers the service on a V5 only, so the OG is as it was.

---

### Task 1: F2, `b` and `n` on port 7 leave the main terminal alone

**Files** (firmware worktree): Modify `src/SingleCharCommands.cpp`, `test/hil/test_port7_reads.py`.

**Interfaces:**
- Consumes: `Jerial.getResponseTarget()`, `USBSer3` (declared in `src/tubes/ArduinoStuff.h:47`), `disableTerminalColors` (`src/Graphics.h:13`).
- Produces: in `cmd_showBridgeArray` and `cmd_showNetlist`, `bool port7 = ( target == (Stream*)&USBSer3 );` after `target` is settled. `couldntFindPath( 1 )` is called only when `!port7`. In `cmd_showBridgeArray`, when `port7`, `disableTerminalColors` is set true before the first `print` and put back to its old value after the last, as `usbSer3_sendPaths` does. Nothing else in either handler changes. For any other asker (port 1, a relayed command) both handlers do exactly what they did. **Why not send the lines to the asker:** `couldntFindPath` prints and marks in one loop, and the OG has its own copy; a port 7 reader has the failures in the Paths table.

- [ ] **Step 1: Write the bench check.** In `test_port7_reads.py`, after check 6, check 7 in the file's own style: port 1 is opened and read for the whole of ten rounds of `port7_command("b")`, `port7_command(":b\n")`, `port7_command("n")`; it receives 0 bytes. And `rc.parse_paths` of `:paths` gives the same before and after those rounds (nothing was marked).
- [ ] **Step 2: No run here shows it fail.** It needs a board. `python3 -m py_compile test/hil/test_port7_reads.py` passes. Its failing run is the bench checklist's item 2, on the board's firmware before the flash.
- [ ] **Step 3: Implement** as under Interfaces.
- [ ] **Step 4: Build both targets, run `test/test_routing_og/run.sh`.** Expected: both build, exit 0.
- [ ] **Step 5: Commit** `b and n asked on port 7 print nothing on port 1 and mark nothing`.

---

### Task 2: F1, `:paths` waits out a sense tap

**Files** (firmware worktree): Modify `src/routing/NetsToChipConnections.h`, `src/routing/NetsToChipConnections.cpp`, `src/routing/NetsToChipConnections_OG.cpp`, `src/tubes/Ser3Backchannel.cpp`, `src/tubes/Ser3Backchannel.h`, `test/hil/test_port7_reads.py`.

**Interfaces:**
- Produces, in `NetsToChipConnections.h`: `struct ChipLedger { int8_t x[12][16]; int8_t y[12][8]; };` and `void printChipStatus(Stream* target = &Serial, const ChipLedger* from = nullptr);`. In both router files the function reads each status through `from` when it is given (`from->x[i][j]`, `from->y[i][j]`) and from `globalState.connections.chipStates` when it is not. Its text is unchanged.
- Produces, in `usbSer3_sendPaths`:

```cpp
    ChipLedger led;
    for (int i = 0; i < 4; i++) {          // as :crossbar: a tap claims lanes as net 59 for about 1 ms, core2busy up
        waitCore2();
        for (int c = 0; c < 12; c++) {
            memcpy(led.x[c], globalState.connections.chipStates[c].xStatus, sizeof(led.x[c]));
            memcpy(led.y[c], globalState.connections.chipStates[c].yStatus, sizeof(led.y[c]));
        }
        if (!core2busy) break;
    }
```

  before the first print, and `printChipStatus(out, &led);` in place of `printChipStatus(out);`. The copy is on the stack: 288 bytes. The header's VERBS line for `:paths` gains "(Chip Status waits out a sense tap)".
- **Why a copy and not a hidden 59:** after the wait, a 59 still in Chip Status is a claim that outlived its tap. The lab notes it; a print that hid every 59 would hide that too.

- [ ] **Step 1: Write the bench check.** Check 8: with the net scan on (skipped, saying so, when it is off, as check 5 is), 100 `:paths` replies; `rc.parse_chip_status` finds net 59 in none.
- [ ] **Step 2: The lab shows the print unchanged, before the change.** `JUMPERLOS=$HOME/Documents/GitHub/JumperlOS-port7 python3 Routing/lab.py run --variant worktree --baseline 5374d38 --classes dense,real,stress,edge` in Jimulator. Expected now and after Step 3: `against 5374d38: no regressions` and the same table (the harness prints Chip Status with `printChipStatus(...)` and one argument). `5374d38` is an ancestor of the worktree's branch, so the ref resolves there.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Build both targets, run `run.sh`, run Step 2's command again.** Expected: as Step 2.
- [ ] **Step 5: Commit** `:paths prints Chip Status from a copy taken between sense taps`.

---

### Task 3: W, the watch command

**Files** (firmware worktree): Create `src/tubes/Ser3Rules.h`, `test/test_ser3_rules/ser3_rules_check.cpp`, `test/test_ser3_rules/run.sh`. Modify `src/tubes/Ser3Backchannel.cpp`, `src/tubes/Ser3Backchannel.h`, `test/hil/test_port7_reads.py`, `test/hil/README.md`.

**Interfaces:**
- `Ser3Rules.h` includes `<stdint.h>` and `<string.h>` and nothing of Arduino. All `static inline`.
  - `enum Ser3WatchAsk { SER3_WATCH_LIST, SER3_WATCH_STATE, SER3_WATCH_ON, SER3_WATCH_OFF, SER3_WATCH_UNKNOWN_TOPIC, SER3_WATCH_USAGE };`
  - `static const char* const SER3_WATCH_TOPICS[] = { "routing" };`, `#define SER3_WATCH_NTOPICS 1`, `#define SER3_WATCH_LINE_ROOM 40` (a line is 30 bytes at most: `changed{routing,4294967295}\r\n`).
  - `Ser3WatchAsk ser3WatchParse(const char* rest, int* topic)`: `rest` is what follows `watch` in the verb line, lower case, no leading colon. `""` is LIST. `"<topic>"` is STATE, `"<topic>:on"` ON, `"<topic>:off"` OFF, for a topic in the table, with `*topic` its index. A first word not in the table is UNKNOWN_TOPIC whatever follows. A known topic followed by any other word is USAGE. `*topic` is -1 unless a topic was found.
  - `bool ser3WatchDue(bool on, uint32_t gen, uint32_t told, bool idle, int room)`: true when `on`, `idle`, `gen != told` and `room >= SER3_WATCH_LINE_ROOM`. "Not equal", never "greater": the counter restarts at 1 on boot.
  - `bool ser3ModalAnswers(const char* inquiry)`: what the port answers in probe mode and the menus. True for `"N"` exactly, and for a string that begins with `:` whose head (the text up to the next `:` or space or the end, compared without case) is one of `nets`, `ver`, `gen`, `paths`, `crossbar`, `xbar`, `watch`, `stop`. False for everything else, the empty string, `"."`, `":every:…"`, `":bench"`, `":n"`, `":repeat"`, `"A"`, `"V"`, `"b"` among it. (Used by Task 6; written and checked here so the list and the seven are held together by one test.)
- `Ser3Backchannel.cpp`:
  - `usbSer3_verbs[]` gains, after `padgate`: `{ "watch", "Lines when a topic changes (topic: routing)", "[<topic>[:on|off]]", "{watch:..} then changed{routing,<n>} lines", ":watch:routing:on", 0 }`.
  - `usbSer3_dispatchVerb` gains `} else if (head == "watch") { usbSer3_watch(out, rest); }` before the single-character passthrough.
  - The reply formats are the design's table, each ended `\r\n`.

```cpp
#include "Ser3Rules.h"

static bool     usbSer3_watchOn[SER3_WATCH_NTOPICS] = { false };   // off at boot
static uint32_t usbSer3_watchTold = 0;       // the routing generation last acknowledged or sent
static bool     usbSer3_dtrWas = false;

static void usbSer3_watch(Stream* out, const String& rest) {
    String r = rest; r.trim(); r.toLowerCase();
    int topic = -1;
    switch (ser3WatchParse(r.c_str(), &topic)) {
        case SER3_WATCH_LIST:
            out->printf("{\"watches\":{\"routing\":\"%s\"}}\r\n", usbSer3_watchOn[0] ? "on" : "off");
            return;
        case SER3_WATCH_UNKNOWN_TOPIC: {
            int c = r.indexOf(':');
            out->print("{\"error\":\"unknown_topic\",\"topic\":");
            usbSer3_jsonStr(out, (c < 0 ? r : r.substring(0, c)).c_str());
            out->print(",\"topics\":[\"routing\"]}\r\n");
            return;
        }
        case SER3_WATCH_USAGE:
            out->print("{\"error\":\"watch_usage\",\"fmt\":\":watch:<topic>:on|off\",\"topics\":[\"routing\"]}\r\n");
            return;
        case SER3_WATCH_ON:
            usbSer3_watchOn[topic] = true;
            usbSer3_watchTold = routingGeneration;   // told from here on, also when it was on already
            break;
        case SER3_WATCH_OFF:
            usbSer3_watchOn[topic] = false;
            break;
        case SER3_WATCH_STATE:
            break;
    }
    out->printf("{\"watch\":\"%s\",\"state\":\"%s\",\"gen\":%lu}\r\n", SER3_WATCH_TOPICS[topic],
                usbSer3_watchOn[topic] ? "on" : "off", (unsigned long)routingGeneration);
}

// The end of every pass of the port's service: after the inquiries, so never inside a reply
// and never between an echo and its reply.
static void usbSer3_watchTick(void) {
    bool dtr = (tud_cdc_n_get_line_state(3) & 0x01) != 0;   // the line itself; USBSer3.dtr() is faked under ignore_dtr
    if (usbSer3_dtrWas && !dtr) usbSer3_watchOn[0] = false; // the host closed the port
    usbSer3_dtrWas = dtr;
    if (!usbSer3_watchOn[0]) return;                        // off: two reads a pass and no more
    uint32_t gen = routingGeneration;
    if (!ser3WatchDue(usbSer3_watchOn[0], gen, usbSer3_watchTold, core1req::allIdle(), USBSer3.availableForWrite())) return;
    USBSer3.printf("changed{routing,%lu}\r\n", (unsigned long)gen);
    USBSer3.flush();
    usbSer3_watchTold = gen;
}
```

  - `serviceUSBSer3()` calls `usbSer3_watchTick();` once, after its `while` loop. The loop has no `return`, so every pass reaches it.
  - `Ser3Backchannel.h`: the VERBS comment gains `:watch[:<topic>[:on|off]]   lines when a topic changes; topic: routing   changed{routing,<n>}` and two lines saying when the line is written and what ends a watch. The ACCESS MODEL sentence at line 22 becomes: the backchannel never makes, removes or reroutes a connection, never changes a setting and never blocks; three verbs switch a stream of lines to this port on and off (`:oled:stream`, `:padgate`, `:watch`). The VERBS heading's "all read-only" becomes "none changes a connection or a setting".

- [ ] **Step 1: Write the failing host check.** `run.sh`: `c++ -std=c++17 -Wall -I src/tubes -o "${TMPDIR:-/tmp}/ser3_rules_check" test/test_ser3_rules/ser3_rules_check.cpp && "${TMPDIR:-/tmp}/ser3_rules_check"`, run from the repository root as `test/test_routing_og/run.sh` is. The program is `assert`s and one `printf("ser3 rules: ok\n")`:
  - parse: `""` LIST; `"routing"` STATE, topic 0; `"routing:on"` ON; `"routing:off"` OFF; `"routing:maybe"`, `"routing:"`, `"routing:on:x"` USAGE; `"taps"`, `"taps:on"`, `"rout"`, `":on"` UNKNOWN_TOPIC with topic -1.
  - due: `(true, 7, 6, true, 64)` true; false when off, when `gen == told`, when not idle, when `room` is 39; true for `(true, 1, 4000000000u, true, 40)` (a reboot).
  - modal: true for each of `"N"`, `":nets"`, `":ver"`, `":gen"`, `":paths"`, `":crossbar"`, `":xbar"`, `":watch"`, `":watch:routing:on"`, `":watch:routing:off"`, `":stop"`, `":GEN"`; false for `""`, `"."`, `"A"`, `"V"`, `"K"`, `"b"`, `"n"`, `":n"`, `":every:1ms:10:gen"`, `":bench"`, `":repeat"`, `":r"`, `":leds"`, `":oled:stream:on"`, `":yaml"`, `":genx"`, `":"`.
  - the seven: for each of `"N"`, `":ver"`, `":gen"`, `":paths"`, `":crossbar"`, `":watch:routing:on"`, `":watch:routing:off"`, modal is true. A comment says these are `BOARD_PORT.SENDS` of the lab's `web/board_port.js` without their line ends.
- [ ] **Step 2: Run** `test/test_ser3_rules/run.sh`. Expected: `Ser3Rules.h` not found.
- [ ] **Step 3: Write `Ser3Rules.h`.** Run again. Expected: `ser3 rules: ok`.
- [ ] **Step 4: Write the bench checks.** A helper in `test_port7_reads.py` that holds one connection (`port7_command` opens and closes the port at every call, and a close ends a watch): `session()` returning `serial.Serial(port7_path(), 115200, timeout=0.2)`, and `ask(ser, cmd, seconds)` returning what came. Checks, all on one held session unless said:
  9. `:watch` answers `{"watches":{"routing":"off"}}`. `:watch:taps:on` answers `unknown_topic` with `"topics":["routing"]`. `:watch:routing:maybe` answers `watch_usage`.
  10. `:watch:routing:on` answers `{"watch":"routing","state":"on","gen":N}` with N the number `:gen` gives. Twenty seconds of a still board bring no `changed{` line.
  11. After `jl_exec("connect(1, 2)")` on port 1, exactly one `changed{routing,M}` arrives within 2 s, M is not N, and `:gen` asked right after answers `gen{M,1}`. Three connects in one `jl_exec` bring one line, not three.
  12. During `:every:100ms:10:gen` with a connect made halfway, no `changed{` line stands before `cap_end`; one follows it.
  13. `:watch:routing:off` answers state off, and a connect then brings no line. `:stop` with the watch on leaves `:watch` saying on.
  14. With the watch on, the session is closed and a new one opened: `:watch` says off (DTR fell). Skipped, saying so, when `usb_cdc.ignore_dtr` is set in `/config.txt`.
  Add `:watch` to the row for `test_port7_reads.py` in `test/hil/README.md`.
- [ ] **Step 5: Implement** the port's part as under Interfaces.
- [ ] **Step 6: Build both targets, run both host scripts, `py_compile` the bench file.**
- [ ] **Step 7: Commit** `Port 7: :watch:routing:on, and a changed{routing,n} line when the routing has moved and the board is idle`.

---

### Task 4: F5, the tap reserve only while the scan is on

**Files:** Lab: create `Routing/tests/test_firmware_fixes.py`. Firmware worktree: modify `src/routing/NetsToChipConnections.cpp`, `src/config.h`, `src/configManager.h`, `src/configManager.cpp`.

**Interfaces:**
- Firmware, after the definition of `routingDuplicatePathNow`:

```cpp
// The reserve keeps copper for the net scan's taps. With the scan off there are none to keep it for.
static bool tapReserveOn(void) {
  return routingDuplicatePathNow && jumperlessConfig.measurement.net_currents != 0;
}
```

  and `tapReserveOn()` in place of `routingDuplicatePathNow` in `reservedKRowForSenseTaps`, `reservedTapEscapeX` and `reservedTapEscapeY`, and nowhere else (not the K-row budget at `:994`, not the ranking at `:5675`, which denies nothing).
- Firmware, the setting: `HOOK_NET_CURRENTS` added to `ConfigApplyHook` after `HOOK_PROBE_POWER_SOURCE`, used in `config.h`'s `net_currents` row in place of `HOOK_NONE`, and in `configManager.cpp` beside the other cases: `case HOOK_NET_CURRENTS:` whose body, `if (cfgGetInt(opt) != prevInt) infraNudge();`, is inside `#if !defined(OG_JUMPERLESS)`, then `break;`, with a comment: the tap reserve follows the setting, so the routing is rebuilt when it changes; the OG has no reserve and does nothing here.
- Lab, `tests/test_firmware_fixes.py`: `ROUTER = variants.resolve("worktree")`; `POINTED = bool(os.environ.get("JUMPERLOS"))`; `has(path, word)` reads `ROUTER.src_root / path`; `scan_off()` returns the variant `variants.resolve("worktree", overrides={"src/config.h": text})` where `text` is `config.h` with `X(measurement, net_currents, INT, 1, 0, 1, 1,` replaced once by `X(measurement, net_currents, INT, 0, 0, 1, 1,` (it raises when the line is not found). `binary(v)` is `variants.build(v)`. `copies(v, name)` is `runner.run_case(binary(v), case, repeat=1)["metrics"]["routed_duplicates"]` for the dense case of that name. Both tests of a pair are skipped with a reason, never left out, so a run always says which router it judged.

- [ ] **Step 1: Write the tests** (class `Reserve`). `GATED = has("routing/NetsToChipConnections.cpp", "tapReserveOn")`.
  - `test_today_the_reserve_holds_with_the_scan_off` (skipped when `GATED or POINTED`, saying "the router under test is not the pinned one"): for `kevin_fixture_2026_09_02` and `rail_stacking_light`, copies with `scan_off()` equal copies with `ROUTER` (measured: 0 and 0, 3 and 3).
  - `test_with_the_scan_off_copies_take_the_reserve` (skipped unless `GATED or POINTED`, saying "the pinned router has no gate; set JUMPERLOS to a firmware that has"): for both cases, copies with `scan_off()` are two more than with `ROUTER` (measured); `routed_primaries` is the same; and `rail_stacking_light` with `scan_off()` has the problem `no sense-tap route for …`, which it has not with `ROUTER`.
- [ ] **Step 2: Run** `python3 -m unittest discover -s Routing/tests -t Routing -k Reserve`. Expected: the first test passes, the second is skipped. Then the same with `JUMPERLOS=$HOME/Documents/GitHub/JumperlOS-port7`. Expected, before the firmware change: the first is skipped and the second fails, copies 0 where 2 are wanted. That is the red run.
- [ ] **Step 3: Implement the firmware change.**
- [ ] **Step 4: Run with `JUMPERLOS` set.** Expected: the first test is skipped, the second passes. Then, in Jimulator, `JUMPERLOS=… python3 Routing/lab.py run --variant worktree --baseline 5374d38 --classes example,dense,real,stress,edge,beyond,typical,fuzz`. Expected: `against 5374d38: no regressions`, and every row of the table equal to the baseline's own (`--variant 5374d38`): with the scan on, nothing moves.
- [ ] **Step 5: Build both targets, run `run.sh`.** The OG router is not touched.
- [ ] **Step 6: Commit twice.** Jimulator: `Routing lab: the tap reserve with the scan off, on the router under test`. Firmware: `The tap reserve applies only while the net scan is on, and changing the setting rebuilds`. In the firmware commit's body: the measured counts (594 cases gain copies, 22 lose one, none loses a primary, the three taps proofs fail with the scan off).

---

### Task 5: F4, the probe's feed falls back

**Files:** Lab: modify `Routing/tests/test_firmware_fixes.py` (create it, with Task 4's `ROUTER`, `POINTED`, `has` and `binary`, if Task 4 was dropped). Firmware worktree: modify `src/routing/InfraPaths.cpp`, `src/routing/InfraPaths.h`, `src/routing/NetsToChipConnections.cpp`. Not `NetsToChipConnections_OG.cpp`: the OG has no feed, and `run.sh` does not link `InfraPaths.cpp`.

**Interfaces:**
- `InfraPaths.h`: `void infraNoteRouting(void);` after `infraEvaluate`, with a comment: called by `bridgesToPaths()` when routing ends; notes whether the probe feed's pair was left with no crosspoint.
- `NetsToChipConnections.cpp`: `infraNoteRouting();` on the line after `validateAllPaths();` at the end of `bridgesToPaths`.
- `InfraPaths.cpp`. State, after `s_nudgePending`:

```cpp
// --- probe feed fallback ---------------------------------------------------
// Candidates are judged by claims, never by whether the pair routed. When a
// rebuild leaves the feed's pair with no crosspoint, the next evaluation
// leaves that candidate out and the walk takes the next viable one. It stays
// out until a user bridge is removed (only that frees copper) or a reboot, so
// the feed cannot flip back and forth: one extra rebuild a removal at most.
// ponytail: a removal is "fewer user bridges than at the last evaluation"; a
// swap that keeps the count waits for the next real removal. Compare the
// bridges themselves if that ever matters.
static void pairPathStats(int a, int b, int* paths, int* dups, int* xp);
static bool s_feedNoteArmed = false;  // set by infraEvaluate: only a rebuild it began is noted
static bool s_feedUnrouted = false;   // that rebuild left the active feed pair with no crosspoint
static int8_t s_feedBarred = -1;      // candidate the walk leaves out while another is viable
static int s_feedUsers = 0;           // user bridges at the last evaluation

static int userBridgeCount(void) {
    ConnectionState& c = globalState.connections;
    int n = 0;
    for (int i = 0; i < c.numBridges; i++) {
        if (!infraIsBridge(c.bridges[i][0], c.bridges[i][1])) n++;
    }
    return n;
}
```

  In `infraEvaluate`: `s_feedNoteArmed = true;` beside `s_nudgePending = false;`. Before the candidate walk (after the `enabled` and user-override tests):

```cpp
#if !defined(OG_JUMPERLESS)
        if (f == 0) {
            int users = userBridgeCount();
            if (users < s_feedUsers) {   // a bridge was removed: copper may have freed
                s_feedBarred = -1;
                s_feedUnrouted = false;
            }
            s_feedUsers = users;
            if (s_feedUnrouted && s_feedBarred < 0 && s_forced[0] < 0 && fn.activeCandidate >= 0) {
                s_feedBarred = (int8_t)fn.activeCandidate;
            }
            s_feedUnrouted = false;
        }
#endif
```

  The walk becomes two passes: `for (int pass = 0; pass < 2 && chosen < 0; pass++) { if (pass == 1 && (f != 0 || s_feedBarred < 0)) break; for (int walk …) { … } }`, and inside it, after the `s_forced` test: `if (pass == 0 && f == 0 && s_forced[f] < 0 && cIdx == s_feedBarred) continue;`. So the barred candidate is left out only while another is viable, and a forced one never. In the relocate branch, before `teardownFunction(fn)`: when `f == 0 && s_feedBarred >= 0 && fn.activeCandidate == s_feedBarred && chosen != s_feedBarred`, print `[infra] probe_power: <barred's name> did not route, using <chosen's name>` on `Serial`, once.

```cpp
void infraNoteRouting(void) {
#if !defined(OG_JUMPERLESS)
    if (!s_feedNoteArmed) return;        // a preview, refreshBlind, FakeGPIO: not a rebuild infraEvaluate began
    s_feedNoteArmed = false;
    InfraFunction& fn = s_functions[0];
    s_feedUnrouted = false;
    if (fn.activeCandidate < 0 || fn.activePairCount <= 0) return;
    int paths, dups, xp;
    pairPathStats(fn.activePairs[0].a, fn.activePairs[0].b, &paths, &dups, &xp);
    if (paths == 0 || xp > 0) return;
    s_feedUnrouted = true;
    if (s_feedBarred >= 0 || s_forced[0] >= 0) return;   // fell back once already, or pinned: no rebuild
    for (int c = 0; c < fn.numCandidates; c++) {
        if (c == fn.activeCandidate) continue;
        InfraPair probe[2];
        if (fn.candidates[c].resolvePairs(probe) > 0 && fn.candidates[c].viable()) {
            s_nudgePending = true;       // infraServiceTick() runs the one extra rebuild
            return;
        }
    }
#endif
}
```

  In `infraServiceTick`'s switch-back test: `first != fn.activeCandidate && first != s_feedBarred && first >= 0 && …`. Without it a board that fell back rebuilds every half second for ever (Review Focus 4).
- Lab test: `feed_three_times(v)` builds `binary(v)`, takes the stress case `gnd_two_rows_every_chip`, makes three copies with `dataclasses.replace(case, name=n, probe=(1, 1))` for `feed_one`, `feed_two`, `feed_three`, runs `subprocess.run([str(binary(v))], input="".join(c.to_protocol() for c in copies), capture_output=True, text=True)` (no `--repeat`: one process, three rebuilds), and returns `[runner.judge(c, runner.parse_sections(out)[c.name], err, ()) for c in copies]`.

- [ ] **Step 1: Write the tests** (class `Feed`). `FALLS = has("routing/InfraPaths.h", "infraNoteRouting")`.
  - `test_today_a_gpio_feed_that_cannot_route_stays_unrouted` (skipped when `FALLS or POINTED`): all three results have 16 routed primaries and the note `unrouted primary path 0: BUFFER_IN-GPIO_6 (net 6)`.
  - `test_the_feed_falls_back_and_stays` (skipped unless `FALLS or POINTED`): the first result is as today (16, the note). The second has status `ok`, no problem, 17 routed primaries, no note with "unrouted", and its report's Bridge Array holds `[BUF_IN,DAC_0,`. The third's report (`b`) equals the second's.
  - `test_the_batteries_do_not_see_it` (always): for `k_rows_overflow_metric` (dense), `edge_1_10` (edge) and `nine_k_nets` (beyond), `runner.run_case(binary(ROUTER), case)` (routed twice) has `metrics["repeat_same"]` true and a note that begins `unrouted primary path 0: BUFFER_IN-GPIO_6`. In these DAC 0 is the case's own, so there is nothing to fall back to.
- [ ] **Step 2: Run** `-k Feed` without `JUMPERLOS`. Expected: the first and third pass, the second is skipped. Then with it set, before the change: the first is skipped, the third passes, and the second fails at its second result, 16 primaries where 17 are wanted. That is the red run.
- [ ] **Step 3: Implement.** Before it, read the three callers from their `infraEvaluate()` to their `bridgesToPaths()` for a `return` between the two: one would leave the note armed for the next preview. None was seen by `grep`; the bodies were not read line by line.
- [ ] **Step 4: Run with `JUMPERLOS` set.** Expected: the first skipped, the other two pass. Then `JUMPERLOS=… python3 Routing/lab.py run --variant worktree --baseline 5374d38 --classes example,dense,real,stress,edge,beyond,typical,fuzz`. Expected: `no regressions`; no case gains the problem "the same case routed twice gives different routes".
- [ ] **Step 5: Build both targets, run `run.sh`.**
- [ ] **Step 6: Commit twice.** Jimulator: `Routing lab: a GPIO feed that cannot route, three rebuilds in one process`. Firmware: `The probe's feed falls back to its next candidate when its pair did not route`. In the firmware commit's body: what it does not do (nothing when DAC 0 is the user's; nothing for the board capture `k_rows_overflow_metric`; the GPIO candidate does not try another pin), and that the extra rebuild and the tick's guard have been seen on no board.

---

### Task 6: F3, port 7 answered in probe mode and the menus

**Files** (firmware worktree): Modify `src/tubes/Ser3Backchannel.cpp`, `src/tubes/Ser3Backchannel.h`, `src/SingleCharCommands.h`, `src/JumperlOS.h`, `src/JumperlOS.cpp`, `src/main.cpp`, `test/test_ser3_rules/ser3_rules_check.cpp`.

**Interfaces:**
- `SingleCharCommands.h`: `void serviceUSBSer3(bool modal = false);`. The call in `Jerial.cpp:1168` is not edited.
- `Ser3Backchannel.cpp`, the entry. `ser3ModalAnswers` and `usbSer3_watchTick` are Task 3's: this task needs Task 3 and no other.

```cpp
static bool     usbSer3_inService = false;    // either entry is in a pass: the other returns at once
static bool     usbSer3_modal = false;        // this pass came from probe mode or a menu
static uint32_t usbSer3_lastNormalMs = 0;     // when the main loop's entry last ran

static void usbSer3_sendBusy(const char* inq) {
    USBSer3.print("{\"error\":\"busy\",\"reason\":\"modal\",\"inq\":");
    usbSer3_jsonStr(&USBSer3, inq);
    USBSer3.print(",\"ok\":[\"N\",\":nets\",\":ver\",\":gen\",\":paths\",\":crossbar\",\":xbar\",\":watch\",\":stop\"]}\r\n");
    USBSer3.flush();
}

void SingleCharCommands::serviceUSBSer3(bool modal) {
    static String lastInquiry;
    if (usbSer3_inService) return;                             // never one pass inside another
    if (modal) {
        if (millis() - usbSer3_lastNormalMs < 50) return;      // the main loop's entry is alive here: the port is its
    } else {
        usbSer3_lastNormalMs = millis();
    }
    usbSer3_inService = true;
    usbSer3_modal = modal;
    while (USBSer3.available() > 0) {
        // ... the loop as it is, with the four changes below ...
    }
    usbSer3_watchTick();
    usbSer3_modal = false;
    usbSer3_inService = false;
}
```

  The four changes inside the loop, each a no-op when `modal` is false:
  1. After `if (c < 32 || c >= 127) continue;`: `if (modal && c != ':') { char one[2] = { c, 0 }; if (!ser3ModalAnswers(one)) { usbSer3_sendBusy(one); continue; } }`.
  2. `String line = usbSer3_readLine(modal ? 25 : 2000);`.
  3. An empty line in a modal pass is dropped: `if (line.length() == 0) { if (modal) continue; … the help, as it is … }`.
  4. After `String low = line; low.toLowerCase();`: `if (modal && !ser3ModalAnswers((String(":") + low).c_str())) { usbSer3_sendBusy((String(":") + line).c_str()); continue; }`.
  In `usbSer3_sendCrossbar`, and in `usbSer3_sendPaths` where Task 2 gave it one, the wait is skipped in a modal pass, because the scan does not tap there (`NetVoltageScan.cpp:1419`, `:1484`) and `core2busy` is mostly LED shows, so four waits could hold a probe tick 100 ms. A guide's one-shot tap can run during a menu; one caught by a dump there would show as one reading with a crosspoint the table does not plan. Not seen, and not guarded: `if (!usbSer3_modal) waitCore2();` and `if (usbSer3_modal || !core2busy) break;`.
- `JumperlOS.h`, after `LedDumpService` and in its form: `class Ser3ModalService : public Service` with `getName()` `"Ser3Modal"`, `getPriority()` `ServicePriority::NORMAL`, `inInnerSet()` true, `periodUs()` 5000; `extern Ser3ModalService& ser3ModalService;` beside `ledDumpService`'s at `:897`. `JumperlOS.cpp`: the instance beside `ledDumpService`'s at `:49`, `getInstance()`, and

```cpp
ServiceStatus Ser3ModalService::service() {
    lastStatus = ServiceStatus::IDLE;
    if ( probeActive == 0 && inClickMenu == 0 && inPadMenu == 0 ) return lastStatus;   // elsewhere the main loop answers, or nobody does, as before
    singleCharCommands.serviceUSBSer3( true );
    return lastStatus;
}
```

- `main.cpp`: `jOS.registerService( &ser3ModalService ); // NORMAL, 5 ms, inner set - port 7 in probe mode and the menus (a short list of reads; see Ser3Backchannel.h)` inside the `if ( board::currentBoard( ).caps.hasProbePads )` block at `:579`, so only a V5 has it.
- `Ser3Backchannel.h`: a paragraph under ACCESS MODEL: in probe mode and the menus the port answers `N`, `:nets`, `:ver`, `:gen`, `:paths`, `:crossbar`, `:xbar`, `:watch…`, `:stop` and refuses the rest with `{"error":"busy","reason":"modal","inq":…,"ok":[…]}`; a `:` line is waited for 25 ms there; in an app or a running script the port is silent as before; on the OG nothing changed.
- **What is not changed:** a click menu shown on the terminal with line buffering on calls the main loop's entry itself (`Menus.cpp:908`), so there every verb is answered as today and the modal service stands down (the 50 ms rule).

- [ ] **Step 1: Add to the host check** a block that holds the `ok` list of `usbSer3_sendBusy` and `ser3ModalAnswers` together: for each of `"N"`, `":nets"`, `":ver"`, `":gen"`, `":paths"`, `":crossbar"`, `":xbar"`, `":watch"`, `":stop"` the function is true, and a comment names `usbSer3_sendBusy`. Run `run.sh`: it passes already (Task 3 wrote the function). This task has no failing host run: its behaviour is the loop's, which no host builds.
- [ ] **Step 2: Write the bench checks that a script can make.** In `test_port7_reads.py`, check 15: with `jl.port1_command` used to open the click menu on the terminal (`K`), `:gen` on port 7 is answered within 100 ms. `:every:100ms:3:gen` is answered with a capture when the menu's loop runs the main loop's entry (line buffering on, `Menus.cpp:908`) and with `busy` when it does not; the check accepts either and prints which. Probe mode needs a hand on the probe: it is in the checklist, not in the file.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Build both targets, run both host scripts, `py_compile`.** Then read the diff of `serviceUSBSer3` once against Review Focus 1: no path leaves the function with `usbSer3_inService` true.
- [ ] **Step 5: Commit** `Port 7 is answered in probe mode and the menus: a short list of reads, the rest refused as busy`.

---

### Task 7: The page listens

**Files** (Jimulator): Modify `Routing/web/board_port.js`, `web/lab.js`, `web/index.html`, `Routing/tests/board_port_test.js`, `tests/test_board_port.py`, `tests/test_server.py`, `tests/link_page_test.js`, `tests/fixtures/port7_built.jsonl`. Create `tests/fixtures/port7_watch_built.jsonl`.

**Interfaces** (`board_port.js`):
- `BOARD_PORT.SENDS` is `["N", ":ver\n", ":gen\n", ":paths\n", ":crossbar\n", ":watch:routing:on\n", ":watch:routing:off\n"]`. New timings: `WATCH_POLL_MS: 3000`, `GAP_MS: 100`, `OFF_MS: 300`.
- `watchOf(text) -> {topic, on, gen} | {error} | null`: the last whole line of the text that is `{"watch":"<topic>","state":"on"|"off","gen":<digits>}`, as `{topic, on: boolean, gen: number}`; or, when the last whole line that is a JSON object has an `"error"` key, `{error: its value}`; `null` before either. `{"watches":…}` is neither.
- `changedOf(line) -> number | null`: the number of a line that is exactly `changed{routing,<digits>}` (line end stripped); `null` for anything else, `changed{routing,<n>}` and `xchanged{routing,5}` among it.
- `FakePort`: a trace line with `"sent": null` is kept. When the place reaches one (at `open`, and after an answer moved the place onto it), its `got` is sent by itself `gapMs` later and the place moves past it; `times` sends it that often. A write still looks only at exchanges with its own `sent`. `add(text)` is unchanged.
- `BoardLink`:
  - `pump()` also feeds a second buffer of its own, split at line ends. For each whole line with `changedOf(line) != null` it sets `this.told = {n}` and calls `this.wake()`. A line cut by a chunk's end waits in that buffer for its rest. `this.text` and `ask()` are not changed by this: the bytes stay where the trace expects them.
  - When such a line is found while no query is out, everything in `this.text` becomes one trace line `{t, sent: null, got}` and `this.text` is emptied. While a query is out the bytes stay in that exchange's `got`.
  - `run()` begins by asking `:watch:routing:on\n` with `watchOf`. `{on: true}`: `this.watching = true`. `{error}` or `{on: false}`: `this.watching = false`. The state words say which: "the board says when its routing changes" or "asking every half second: this firmware has no :watch".
  - The loop is piece 7's with three changes. (1) A round begins `const t = this.told; this.told = null; let g = t ? {n: t.n, idle: true} : await this.askGen();` (`told` is taken and cleared before the question, so a line that arrives while that `:gen` is out is kept for the next round) so a `changed{}` line stands in for the leading `:gen`, and the `:gen` after the dump still decides. (2) After a round the link waits `GAP_MS` whatever arrives. Then, unless `this.told` is set, it goes on waiting until a `changed{}` line, `again()` or a close wakes it: `WATCH_POLL_MS` in all when watching and the last `:gen` said idle at the generation shown, `POLL_MS` in all otherwise. As in piece 7, no other byte the board sends cuts the wait. (3) The loop also ends when `this.stopping`.
  - `close()`: sets `this.stopping` and wakes. Then, when watching, proven, not ended and no query is out, it asks `:watch:routing:off\n` with `watchOf` and the limit `OFF_MS`, and goes on whatever came. Then it closes as before.
  - `connect()` is not changed: a port that is not port 7 still gets one `N`, and firmware too old for `:gen` gets `N`, `:ver\n`, `:gen\n` and no more.
- The built traces. `built_trace(names, watch=False)` is the old trace with one exchange added after the connecting `:gen`: `:watch:routing:on\n` answered `:watch:routing:on\r\n{"error":"unknown_verb","verb":"watch:routing:on"}\r\n`. `tests/fixtures/port7_built.jsonl` is that. `built_trace(names, watch=True)` is `tests/fixtures/port7_watch_built.jsonl`: the same connecting; the watch answered `{"watch":"routing","state":"on","gen":3}`; `:gen` `gen{3,1}`, `:paths`, `:crossbar`, `:gen` `gen{3,1}` for the first routing; then for each later routing at generation G a line `{"sent": null, "got": "changed{routing,G}\r\n"}` followed by `:paths`, `:crossbar`, `:gen` answered `gen{G,1}`; last, `:watch:routing:off\n` answered state off. Its header says `"source": "built"` and that the watch's lines are made up.
- `index.html`, `#link-sends` (binding): "To the board's fourth port only, and only after you press Connect. N once: its net list, which proves the port is the right one. :ver once: its firmware version. :watch:routing:on once: it asks the board to say when its routing has changed. :gen: a counter that moves when the board rebuilds its routing, and whether it has finished sending it; every three seconds while a watching board is still, twice a second while its routing is changing and on firmware that cannot watch. :paths and :crossbar when the routing has changed: its routing report, and which crosspoints are closed. :watch:routing:off when you disconnect. Five are questions and the two :watch lines switch the board's own line on and off; none makes, removes or reroutes a connection, and none prints on the board's own terminal. Nothing is sent to any other port." Then the picker's sentences as they are.
- `lab.js`: the trace's and the status line's words follow the link's; nothing else. It still never takes the port's writer.

- [ ] **Step 1: Write the failing tests** in `board_port_test.js`. Existing inline traces that reach `run()` gain `NOWATCH = { sent: ":watch:routing:on\n", got: ':watch:routing:on\r\n{"error":"unknown_verb","verb":"watch:routing:on"}\r\n' }` after their connecting `:gen`, and their expected `written` lists gain `":watch:routing:on\n"` in fourth place. The test of `SENDS` holds the seven. "a still board is asked its generation and nothing else" now holds that every write is one of the seven and that `:watch:routing:off\n` was not written (the watch was refused). New tests, with `WATCH = "port7_watch_built.jsonl"` given as a third argument by `test_board_port.py`:

```js
const FASTW = Object.assign({}, FAST, { WATCH_POLL_MS: 400, GAP_MS: 2, OFF_MS: 40 });
const ACK = { sent: ":watch:routing:on\n", got: ':watch:routing:on\r\n{"watch":"routing","state":"on","gen":3}\r\n' };
const OFF = { sent: ":watch:routing:off\n", got: ':watch:routing:off\r\n{"watch":"routing","state":"off","gen":9}\r\n' };
const told = (n) => ({ sent: null, got: "changed{routing," + n + "}\r\n" });

test("the watch's lines and its answers are read by their whole shape", () => {
  assert.equal(P.changedOf("changed{routing,12}"), 12);
  for (const no of ["changed{routing,<n>}", "xchanged{routing,5}", "changed{routing,5} ", "gen{5,1}", ":gen", ""])
    assert.equal(P.changedOf(no), null, no);
  assert.equal(P.genOf("changed{routing,7}\r\n"), null);                       // not a reply to :gen
  assert.deepEqual(P.watchOf(ACK.got), { topic: "routing", on: true, gen: 3 });
  assert.deepEqual(P.watchOf(NOWATCH.got), { error: "unknown_verb" });
  assert.equal(P.watchOf(":watch:routing:on\r\n"), null);                      // the echo alone
  assert.equal(P.watchOf('{"watches":{"routing":"on"}}\r\n'), null);
});

test("a watching board is read when it says so, and asked little else", async () => {   // Review Focus 7
  const port = new P.FakePort(fs.readFileSync(WATCH, "utf8"));
  const [link, seen] = linked(port, FASTW);
  await link.connect();
  link.run();
  while (seen.readings.length < 4) await sleep(5);
  await link.close();
  assert.deepEqual(seen.readings.map((r) => r.gen), [3, 5, 7, 9]);
  assert.equal(port.written.filter((w) => w === ":paths\n").length, 4);
  assert.ok(port.written.filter((w) => w === ":gen\n").length <= 8);          // connect, the first round, one confirm a reading
  assert.equal(port.written.at(-1), ":watch:routing:off\n");
  assert.ok(port.written.every((w) => P.BOARD_PORT.SENDS.includes(w)));
  assert.equal(port.most, 1);
});

test("a line in the chunk of a reply, split in two, and during a query", async () => {  // Review Focus 7
  const port = made([N, VER, gen(3, 1), ACK, gen(3, 1), paths("same_chip_pairs"), dump("same_chip_pairs"),
    { sent: ":gen\n", got: ":gen\r\ngen{3,1}\r\nchanged{routing,5}\r\n" },    // the line rides behind a reply
    paths("sf_to_sf"), dump("sf_to_sf"), gen(5, 1), paths("sf_to_sf"), dump("sf_to_sf"), gen(7, 1, 9), OFF]);
  const [link, seen] = linked(port, FASTW);
  await link.connect();
  link.run();
  while (seen.readings.length < 2) await sleep(5);
  assert.deepEqual(seen.readings.map((r) => r.gen), [3, 5]);                   // not lost with the reply's text
  port.add("changed{rou"); await sleep(20); port.add("ting,7}\r\n");           // one line, two chunks
  while (seen.readings.length < 3) await sleep(5);
  assert.equal(seen.readings[2].gen, 7);
  await link.close();
  const trace = link.trace().trim().split("\n").map((l) => JSON.parse(l));
  assert.ok(trace.some((e) => e.sent === null && /changed\{routing,7\}/.test(e.got)));
});

test("a line that never comes is caught by the slow poll, and a board that cannot watch is polled", async () => {
  const quiet = made([N, VER, gen(3, 1), ACK, gen(3, 1), paths("same_chip_pairs"), dump("same_chip_pairs"), gen(3, 1),
    gen(5, 1), paths("sf_to_sf"), dump("sf_to_sf"), gen(5, 1, 9), OFF]);
  const [link, seen] = linked(quiet, Object.assign({}, FASTW, { WATCH_POLL_MS: 30 }));
  await link.connect();
  link.run();
  while (seen.readings.length < 2) await sleep(5);
  await link.close();
  assert.deepEqual(seen.readings.map((r) => r.gen), [3, 5]);
  const old = built();                                                         // its watch is refused
  const [link2, seen2] = linked(old, FASTW);
  await link2.connect();
  link2.run();
  while (seen2.readings.length < 4) await sleep(5);                            // far sooner than WATCH_POLL_MS allows
  await link2.close();
  assert.ok(!old.written.includes(":watch:routing:off\n"));
});

test("disconnect says off once, within its limit, and not over a query that is out", async () => {
  const port = new P.FakePort(fs.readFileSync(WATCH, "utf8"));
  const [link, seen] = linked(port, FASTW);
  await link.connect();
  link.run();
  while (seen.readings.length < 1) await sleep(5);
  port.hush();                                                                 // the board goes silent
  const t = Date.now();
  await link.close();
  assert.ok(Date.now() - t < 400 && port.most === 1);
  assert.ok(port.written.filter((w) => w === ":watch:routing:off\n").length <= 1);
});
```

  In `test_board_port.py`: the two fixtures equal `built_trace(names)` and `built_trace(names, watch=True)`; the `sent` values of the first are the old five and `:watch:routing:on\n`, of the second the seven and `None`. In `test_server.py`: `index.html` holds "Nothing is sent to any other port" and `:watch:routing:on`, and no longer "All five are questions"; `lab.js` still holds no `getWriter`. `link_page_test.js`: its fake answers the watch.
- [ ] **Step 2: Run** `python3 -m unittest discover -s Routing/tests -t Routing -k test_board_port`. Expected: `P.changedOf is not a function`, and the fixtures differ.
- [ ] **Step 3: Implement.** The readers; `FakePort`'s unasked lines; `pump`'s second buffer; `run` and `close`; `built_trace` and the two fixtures it writes.
- [ ] **Step 4: Run all tests** three times over, as plan 7 asks of the link's tests. Expected: pass each time.
- [ ] **Step 5: Check it in the browser**, in Chrome, with `python3 Routing/lab.py serve --replay Routing/tests/fixtures/port7_watch_built.jsonl`: Connect; the four routings arrive by themselves; the status line says the board says when its routing changes; "save trace" holds the seven and nothing else, with a `"sent": null` line before each later reading; Disconnect ends with `:watch:routing:off`. Then the same with `port7_built.jsonl`: the page says it is asking every half second, and behaves as piece 7 did.
- [ ] **Step 6: Commit** `Routing lab page: the board says when its routing changed, and the page asks only then`.

---

### Task 8: Documents

**Files:** Firmware worktree: modify `jumperless_skill/jumperless_skill.md`. Docs worktree: modify `docs/07.5-automation.md`, `docs/jumperless-agent-skill.md`. Jimulator: modify `Routing/web/README.md`, `Routing/README.md`, `Routing/docs/DESIGN_ROUTING_LAB.md`.

- [ ] **Step 1: The firmware's skill.** In `jumperless_skill/jumperless_skill.md`, a new section "## The machine port (port 7)" after "Port discovery helper": which port it is and how to find it (`/dev/cu.usbmodemJLV5port7`, the fourth CDC interface, 115200); that a single character is answered at once and a `:` line is echoed and then answered; that `:help` and `:cmds` list every verb from the firmware's own table; a table of the routing reads with their reply shapes (`:gen`, `:paths`, `:crossbar`, `N`, `:ver`); the watch (the design's table, when a `changed{routing,<n>}` line is sent, what ends a watch); the worked exchange `:watch:routing:on`, a change, `changed{routing,n}`, `:paths`, `:crossbar`, `:gen`; what the port answers in probe mode and the menus and the `busy` refusal; and that `b` and `n` are answered there too but `:paths` is the read to use. Only what the tasks that were built provide: a task that was dropped is left out. Commit on the firmware branch: `The skill: port 7, its routing reads and :watch`.
- [ ] **Step 2: The documentation site.** `git -C ~/Documents/GitHub/Jumperless-docs fetch origin`, then `git -C ~/Documents/GitHub/Jumperless-docs worktree add ~/Documents/GitHub/Jumperless-docs-port7 -b port7-watch origin/main`. Neither changes a file in the main checkout's working tree. In the worktree:
  - `docs/07.5-automation.md`, found by its headings (the line numbers under "Measured" are `origin/main`'s): the heading "### 5. USBSer3 backchannel (4th port) — read-only telemetry" stays; its first sentence no longer says "never changes state": the port makes, removes and reroutes no connection and changes no setting, and three verbs switch a stream of lines to it on and off. The verbs bullet gains `:gen`, `:paths` and `:watch:routing:on`. The `| Command | Returns |` table gains rows for `:gen`, `:paths`, `:crossbar` and `:watch[:<topic>[:on|off]]`. After the table, a new "#### Routing reads and `:watch`" with the same content as Step 1's tables and exchange, and one sentence that the verbs need firmware newer than 5.7.11.5 and what older firmware answers (`unknown_verb`). The "Which tool do I use?" row and the "Implementation status" row say the same in a clause each.
  - `docs/jumperless-agent-skill.md`, "## Communication methods": the port 7 bullet names `:gen`, `:paths`, `:crossbar` and `:watch:routing:on` with one line on the `changed{routing,<n>}` line.
  - `site/` is not edited. The site is not built here: whether its hooks write into the tree is not established. Read both pages' Markdown once for a broken table.
  - Commit on `port7-watch`: `Port 7: the routing reads and :watch`. Not pushed: a push to `main` may publish (Read the Docs), and Kevin's checkout has uncommitted edits to both pages that this branch will meet at merge. Tell him the branch and both facts.
- [ ] **Step 3: The lab's documents.** `Routing/web/README.md`, "A live board": the paragraph "What the page sends" word for word as Task 7 has it; what the page does on firmware with and without `:watch`; the three new timings and why three seconds; that a board in probe mode or a menu now answers (when Task 6 was built) and that an app or a running script is still silence; the trace's `"sent": null` lines. `Routing/README.md`, "What it does not check": a change made and undone between two idle moments gives one line and one reading; the feed's fallback is not modelled by the lab's own rebuild (the harness does not retry); the lab always routes with the scan on. `DESIGN_ROUTING_LAB.md`: a "### Piece 8 as built" under piece 8 with the status, the heads of the three branches, which tasks were built and which dropped, and what the build did differently.
- [ ] **Step 4: Run all tests.** Commit on Jimulator `main`: `Routing lab: the watch and the firmware's fixes documented`.

---

## Not in this plan

- **A `:taps` list of planned taps.** A feature, not a fix.
- **Topics other than `routing`.** The verb takes a name; one is built.
- **The bench.** Nothing is flashed and no port is opened. The checklist below is for the sitting plan 7's Task 6 already waits for.
- **Any change under `Routing/harness/`.** So the lab's rebuild does not ask for the extra rebuild a board does after a feed fails, and has no knob for the scan; both are shown through tests that drive the harness as it is. When the submodule moves to this firmware, a harness that retries is a new router build and Kevin's call.
- **The GPIO candidate trying its next pin**, and a retry inside one rebuild. The feed falls back between candidates, one rebuild later.
- **The viewer's verbs in probe mode** (`:leds`, `:oled`, `:gpio`). They are refused there as busy; today they are held until the mode ends.
- **The OG.** It gets F2, the `printChipStatus` parameter and `:watch` because the files are shared. It gets no modal service, no reserve change and no feed change. Nothing is checked on an OG.
- **A push, a release, the submodule's move, `BOARD_PORT.NEEDS`, and publishing the documentation site.** Each waits for Kevin.

## When a board is on the bench

For the sitting plan 7's Task 6 describes, after its own steps. Port 1 free unless said. Write down each as seen.

1. **Before the flash:** `python3 test/hil/test_port7_reads.py` on firmware `44b1ba9` or older. Checks 7 onward fail (`b` prints on port 1; `:watch` is `unknown_verb`). These are the failing runs Tasks 1 to 3 could not make.
2. **After the flash:** the same file passes, then `python3 test/hil/run_all.py`. A failure is run again on `origin/main`'s firmware before the branch is blamed.
3. **W.** From Chrome: does `:watch` say off after the tab is closed without Disconnect (DTR)? From the page: a change by probe, by terminal and by slot each shows within a second with no `:gen` asked in between (the trace says); a still board is asked `:gen` every 3 s and nothing else.
4. **F1.** With the scan on, "read again" pressed fifty times: no note about net 59 in any reading.
5. **F2.** Kevin's terminal open on port 1, a bridge on the board that cannot route: `b` and `n` asked on port 7 twenty times add no line to his terminal. `b` typed on his terminal still prints its line.
6. **F3.** `X` before connecting the page: the probe's tick gap (max, average). Then with the page connected, in probe mode, making five connections: each shows on the page while probe mode is still on; `X` after: the gap again. Kevin says whether the probe feels as it did. Then each menu: click menu from the wheel, click menu on the terminal, a pad menu. Then an app and a running script: the page says "waiting", as before. Then a terminal program on port 7 that stops reading while the board is in probe mode, with the page closed: does the probe stall? (Review Focus 2.)
7. **F4.** `probe.power_source = 1`, then the bridges of `gnd_two_rows_every_chip` (the lab's stress case) loaded as a slot. Kevin's terminal shows one "Couldn't find a path for BUF_IN to GP_6", then `[infra] probe_power: GPIO did not route, using DAC0`, and no further rebuild: `:gen` stands still for a minute. `i@` shows the feed on DAC 0 with `xp:2`. The probe works. Remove one bridge: one more try of the GPIO, at most one more extra rebuild. Set `probe.power_source = 0` again.
8. **F5.** `measurement.net_currents = 0` with stacking on and a slot that has rails: `b` shows more copies than with it on. Set it to 1 by each way the board offers (terminal config, the menu): does the generation move by itself, and do the net currents come back? A way that does not rebuild is written down (Review Focus 9). With the scan off, run one guide check that taps: what it says.
9. **The page on a real trace.** Save the sitting's trace as `tests/fixtures/port7_<date>.jsonl` and add plan 7's two tests for it; its `changed{}` lines replace the made-up ones as evidence.
