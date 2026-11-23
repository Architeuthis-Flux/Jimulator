# Firmware notes, 2026-11-23: what the routing report costs on a board, and the scan's taps

Read for the live-board piece (piece 7 of `DESIGN_ROUTING_LAB.md`, `PLAN_ROUTING_LAB_7_LIVE_BOARD.md`), after Kevin
answered two of its questions with "look at the firmware". By reading `JumperlOS/src` at `5374d38` only: no board
was touched, nothing was built, and what could not be established says so. File paths are under `JumperlOS/src/`
unless they begin with `Routing/`.

All findings are by reading `JumperlOS/src` at 5374d38; no board was touched and nothing was edited. Line numbers are this checkout's; two differ from the plan (`config.h:175` not 177, probe loop `Probing.cpp:4390-4399` not 4397-4416).

## Summary
1. `b` re-runs no routing. It calls `couldntFindPath(1)`, which prints one line per failed primary to port 1 only (never port 7) and re-marks those paths; `b`'s colour codes also go to port 1. `n` costs the same.
2. The probe feed has alternatives only by claim (DAC0 or GPIO 8 to 1, order from `probe.power_source`). A feed the router cannot place gets no fallback and no message of its own, so the "alt route with the dac" Kevin describes is missing.
3. Port 7 gives nets, user bridges and the crossbar cleanly today. The path table, chip status, infra bridges, failures and the generation counter are only reachable through `b` or `i?`.
4. Scan taps are planned per tap on copper free in both the chip shadow and the router's ledger, closed about 1 ms, one at a time, never held. A user bridge is never refused for a tap; only stacked duplicates give way. Kevin's memory holds for primaries.
5. The dump check is not possible today. Smallest set: `:gen`, `:paths`, and a tap-free `:crossbar`.

## A1. What `b` runs
- **Dispatch.** `b` is registered untagged (`SingleCharCommands.cpp:480-482`), so it is `SER3_ALLOWED` (`SingleCharCommands.h:95-99`, `:146`). Bare `b` on port 7 runs at `Ser3Backchannel.cpp:1264-1274` with no echo; `:b` reaches the same handler (`:841-868`) and is echoed (`:1186`, `:1093`, `:1105`).
- **Handler** (`SingleCharCommands.cpp:2096-2130`). Five config lines, `couldntFindPath( 1 )` (`:2121`), then `printBridgeArray`, `printPathsCompact`, `printChipStatus` to the asking port (`:2122-2127`). No routing, refresh or send is called.
- **The line** (`NetsToChipConnections.cpp:5484-5488`). The prefix is `Serial.print("\n\rCouldn't find a path for ")`, raw port 1. The two names use `printNodeOrName(node)`, whose default stream is `&Jerial` (`NetManager.h:45`), and Jerial's only output is port 1 (`main.cpp:296`). No part reaches port 7, so a page must read failures from the Paths table (x/y of -1).
- **When.** At the end of every routing pass (`NetsToChipConnections.cpp:2626`; rebuilds at `Commands.cpp:268`, `449`, `551`, `685`), on every `b`, on every `n` (`SingleCharCommands.cpp:1851`, also allowed on port 7), and from two debug-menu actions (`selfreflection/Debugs.cpp:1064`, `1071`).
- **It repeats.** A failed primary has all coordinates wiped to -1 (`:5504-5507`) and the test is "any x or y below 0" (`:5447-5457`). There is no rate limit.

## A2. Side effects of `b`
- **Print on port 1**, as above.
- **Re-marking.** `numberOfUnconnectablePaths = 0` (`:5435`), the list refilled (`:5493-5497`), `paths[i].skip = true` (`:5498`), coordinates wiped (`:5504-5507`); for a failed duplicate, coordinates wiped and `altPathNeeded = false` (`:5516-5520`). These writes sit outside the print gate, so `couldntFindPath(0)` is not a silent variant.
- **Not always a rewrite.** `checkForOverlappingPaths()` and `validateAllPaths()` run after the pass's own call (`:2626-2629`) and wipe what they skip (`RouteSafety.cpp:494-496`, `534-541`). The next `b` prints a first failure line for such a path and adds an overlap-skipped one to `unconnectablePaths`, which `guiding/GuideChecks.cpp:472-482` reads.
- **Colour codes on port 1** (not seen on a board). The print functions call `changeTerminalColor(x, false, target)` (`NetsToChipConnections.cpp:6751`, `6811`, `6836-6838`, `6851-6853`), and that function ignores its stream: `Jerial.printf("\033[38;5;%dm", termColor)` (`Graphics.cpp:447-470`). Port 7's text is colour-free; port 1 gets a set and reset per path row and per occupied chip cell.
- **One cosmetic write.** `assignTermColor()` (`:6709`) rewrites `nets[i].termColor`, as each refresh does (`Commands.cpp:334`, `510`).
- **Nothing else.** No LEDs, crosspoints, bridges or generation change. `Ser3Backchannel.h:19-28` says the port "can NEVER change system state"; `b` and `n` break that.

## A3. The probe feed
- **Chosen by claim.** `infraEvaluate()` runs at the head of each rebuild (`Commands.cpp:241`, `426`, `643`). Candidate 0 is `BUFFER_IN-DAC0` (`InfraPaths.cpp:288`), candidate 1 a free GPIO scanned 8 to 1 (`:296-315`); order comes from `probe.power_source`, default DAC0 first (`:356-362`, `config.h:112`). Viability asks only about claims (`:199-209`, `:289`, `:300-308`), never whether the pair routed.
- **In the router** the feed moves to path 0 (`NetsToChipConnections.cpp:1944-1953`, `1997-2007`) and is never duplicated (`:2753-2758`). Whether path 0 always claims copper first: not established (the plan's capture has the feed failing).
- **What is printed, all on port 1:**
  - User sets DAC0 outside 2.80 to 3.90 V: "DAC 0 was powering the probe - relocating the buffer feed" (`Peripherals.cpp:1040-1044`), then a rebuild moves it to a GPIO.
  - User bridge on BUFFER_IN: `[infra] probe_power yielded to a user connection on its node` (`InfraPaths.cpp:526-532`).
  - Every candidate claimed: `[infra] probe_power: no viable candidate (all resources claimed)`, at most every 5 s (`:564-575`).
  - Candidate chosen but unroutable: only the generic "Couldn't find a path" line; `couldntFindPath` has no infra exemption (`NetsToChipConnections.cpp:5460-5481`).
- **No fallback on a route failure.** `infraProbePowerSource()` reads the chosen candidate, not the path (`InfraPaths.cpp:632-634`), so the retries keyed on it (`Probing.cpp:7396`, `main.cpp:950-953`) and the tick (`InfraPaths.cpp:697-737`) do not fire. `i@` would show `xp:0` (`:892-908`).
- **The old DAC0 swap is gone** (`Probing.cpp:6441-6446`, `InfraPaths.cpp:326-330`); stale comments at `Probing.cpp:6409` and `7004` still name it.
- What the probe does with an unrouted feed: not established.

## A4. A user bridge with no path
- The router tries commit, alt paths and uncommitted hops under the K-row budget, a rescue pass with the budget off (`NetsToChipConnections.cpp:2517-2567`) and a hub rescue (`:2572`), then prints and marks (`:2626`). The bridge stays in the bridge array.
- It is printed again on every later routing pass and on every `b` or `n`, never on a timer.
- Rebuilds also start without a user edit: the infra tick (pending nudge, claim pin taken by MicroPython or PWM, first-choice feed viable again; `InfraPaths.cpp:697-735`), DAC writes crossing the probe window (`Peripherals.cpp:1040-1058`), and probe zero calibration (`Probing.cpp:6978-6985`). Each reprints every failure line and bumps the generation.

## A5. What port 7 returns cleanly today
- **Clean, by reading the senders:** `N`/`:nets` (`Ser3Backchannel.cpp:254-262`), `:crossbar` (`:378-394`), `K`/`:yaml` (`:187-197`; user bridges only, infra bridges are not serialized, `States.cpp:1758-1762`), `:ver` (`SingleCharCommands.cpp:3044-3051`). `A`/`:all` also reads ADCs and INAs (`:129-185`). Not checked: `:json`, `:slot`, `:history`, `X`.
- **Only in `b`:** the Bridge Array with infra bridges and net numbers, the Paths table, Chip Status (the router's ledger).
- **`routingGeneration`** is printed only by the audit (`RouteSafety.cpp:1288-1291`) behind `i?` (`SingleCharCommands.cpp:3223-3225`). That self-check zeroes `lastChipXY` for a moment (`RouteSafety.cpp:1323-1334`), `i` is `SER3_MODIFIES_STATE` (`:651-655`), and port 7 passes one character, so `i?`, `i!` and `i@` cannot be asked there.

## A6. Recommendation
- **`:gen`** prints `gen{<routingGeneration>,<idle>}`. It reads the counter and `core1req::allIdle()` (`coredination/CoreMailbox.cpp:95-97`).
  - The counter goes up at each rebuild head (`NetsToChipConnections.cpp:1748`) and again when core 2 starts the send (`CH446Q.cpp:757`); it restarts at 1 on boot (`RouteSafety.cpp:34`).
  - The idle bit is needed because `refreshLocalConnections` returns before the send (`Commands.cpp:491-497`). The page re-reads on any change and takes the dump only when idle.
  - Not established: that every table change bumps it (the virtual current-sense path, `Graphics.cpp:720-728`).
- **`:paths`** prints what `b` prints without `couldntFindPath`: the same three headings (`SingleCharCommands.cpp:2122-2126`, so `Routing/board.py` parses it unchanged) and the same three print calls, with `disableTerminalColors` set true around them and restored. The three functions only read `globalState.connections` and write to `out`; the one write is `assignTermColor()`. Old firmware answers `unknown_verb`, so the page can tell.
- **Probe mode.** `serviceUSBSer3()` is called only from `Jerial.service()` (`Jerial.cpp:1167-1168`), which runs at `main.cpp:1206` and `Menus.cpp:908`. The probe loop is `probeTick(s); jOS.serviceInner();` (`Probing.cpp:4390-4399`) and Jerial is not a service (`JumperlOS.h:427-431`). It would take:
  - an inner-set service (as `JumperlOS.h:490` does) whose `service()` calls `singleCharCommands.serviceUSBSer3()`, with the call removed from `Jerial.service()`;
  - a re-entrancy guard (static `lastInquiry` and a static buffer, `Ser3Backchannel.cpp:1146`, `:381`);
  - refusing `:every`, `:bench`, `A` and `V` while `probeActive`. A half-sent `:` line stalls probe ticks up to 2 s (`:1085-1111`), as does a host that stops reading.

## B1. How the scan plans and closes taps
- **Planned at tap time, never stored.** "Sense routes are computed FRESH on every poll … No persistent channel state exists" (`sensing/NetVoltageScan.cpp:7-10`).
- **Copper.** Every route ends on chip K, where ADC0-3 sit (`:12-20`). The planner needs each lane and row free in the chip shadow and in the router's ledger (`RouteSafety.cpp:625-654`); a second pass may share a K row wholly owned by the node's own net (`:707-718`, `:1045-1050`).
- **Close and open.** `fastConnectPath` claims the ledger as net 59 and sends each hop (`RouteSafety.cpp:1158-1166`), which sets the `lastChipXY` bit (`CH446Q.cpp:1619-1625`). After 80 µs settle and 500 µs dwell (`NetVoltageScan.cpp:302`, `315`), `fastDisconnectPath` opens it (`RouteSafety.cpp:1188-1196`). Probing calls it "the tap's ~1ms" (`Probing.cpp:3026-3027`).
- **Cadence.** On core 2, one tap per pass, at least 5 ms apart (`NetVoltageScan.cpp:81`, `1473-1486`), with `core2busy` raised around it. The default mode is one route at a time (`:174-181`, `:1352`); the help text at `config.h:232` says the opposite of the code.
- **Nodes tapped.** The scan list (`:815-866`), in-use rails and DACs (`:1501-1511`), GND when unused (`:1495-1500`), and path ends including GND, rails and DACs (`:763-770`, `:1327-1390`).
- **Paused** when the scan is off (`:1398`; on by default, `config.h:175`), in menus (`:1419`), during a rebuild or pending send (`:1429-1431`), within 100 ms of input (`:1448-1451`), and in probe mode or wavegen (`:1484-1485`).

## B2. Priority
- **The router ignores taps.** It never reads `lastChipXY`, and each rebuild resets the ledger, tap claims included (`NetsToChipConnections.cpp:1814-1820`). A rebuild waits out core 2 first (`Commands.cpp:231`, `:400`), and the scan will not start a tap during one (`RouteSafety.cpp:1129`).
- **Primaries are never refused for taps.** Every reservation test starts with `routingDuplicatePathNow` (`NetsToChipConnections.cpp:583-587`, `879-881`, `916-918`): "Primary paths keep unconditional access (connectivity first)" (`:554-555`).
- **Duplicates do route worse.** A stacked copy is denied the last virgin K row, the last tap-capable bounce chip, the last lane into I/J/K/L and the last hub lane into K (`:575-587`, `:870-931`), then "silently dropped" (`:5509-5515`). The comments record this as Kevin's ruling (`:577-580`, `:601-607`). The reserve applies even with the scan off.
- **With no room** the tap fails `noroute` (`NetVoltageScan.cpp:294-299`) or shares a same-net K row.
- So what Kevin remembers is there for primaries. If "user routing" should include stacked copies, that part is missing.
- Not established: what the next send does if a rebuild overtakes an open tap by timeout (`RouteSafety.cpp:1183-1187` drops the handle without opening).

## B3. Telling taps from user paths
- `b` prints no taps. A `b` taken mid-tap would show net 59 in Chip Status.
- Planned taps are printed only by `i!` (`NetVoltageScan.cpp:1064-1077`, `1119-1130`) and once a second under `debug.net_voltage_scan` (`:1566-1573`), both on port 1. That loop covers the scan list plus unused GND on the lowest free ADC, so it under-lists the rail, DAC and in-use GND taps.
- The harness calls the same `planFastPath(node, ADC0 + adc, &r)` (`Routing/harness/lab_harness.cpp:275`, ADC from `infraFreeAdcMask` at `:263`) and prints the same line format.
- Not derivable from the path table alone: the planner also needs the ledger, `nodeToNetIndex`, the free ADC channel and the scan list.

## B4. The dump check
- Not possible today. Equality is also the wrong form while taps run: the dump is a core-0 `memcpy` (`Ser3Backchannel.cpp:379-380`) while core 2 opens and closes taps. With a tap list the check is "table within dump within table plus taps".
- FakeGPIO also writes the shadow (`sensing/FakeGpio.cpp:83-87`); the MicroPython writer was not re-checked.
- **Smaller and exact: a tap-free dump.** In `usbSer3_sendCrossbar`, call `waitCore2()` before the `memcpy` and re-check `core2busy` after, the idiom `Probing.cpp:3025-3030` uses. The page then checks dump equals table whenever `:gen` reports idle. Not established: that `core2busy` brackets FakeGPIO's writes.
- **`:taps`, for drawing only.** A public function in `NetVoltageScan.cpp` running `printSenseRoute` over the scan list, in-use sources and GND. `planFastPath` claims and sends nothing (`RouteSafety.cpp:1107-1124`).

## Firmware additions to propose
| # | Command | Prints | Calls | Risk |
|---|---|---|---|---|
| 1 | `:gen` | `gen{<n>,<idle>}` | `routingGeneration`, `core1req::allIdle()` | None; two reads |
| 2 | `:paths` | `b`'s three blocks, same headings | `printBridgeArray`, `printPathsCompact(1)`, `printChipStatus`, colours off around them | Low; one cosmetic write |
| 3 | `:crossbar`, made tap-free | Same `xbar{12x8:…}` | `waitCore2()`, `memcpy`, re-check `core2busy` | Low; core 0 waits up to about 1 ms per tap; FakeGPIO not covered |
| 4 | `:taps` (optional) | `[nvscan] route …` lines | New wrapper around `printSenseRoute` / `planFastPath` | Low; a planned list is not proof for the check |
| 5 | Guard in `b` and `n` (optional) | Unchanged on port 1 | Skip `couldntFindPath` unless the target is port 1 | Low; restores the header's promise |
| 6 | Port 7 in probe mode (optional) | n/a | Inner-set service around `serviceUSBSer3()`, with a guard and a probe-mode whitelist | Medium; blocking paths inside probe ticks |
| 7 | Not port 7, Kevin's call | n/a | Feed falls back when its pair did not route; `Graphics.cpp:447` honours its stream; tap reserve only when the scan is on | Behaviour changes; the feed fallback needs an oscillation guard |
