# Findings so far

What the lab has measured, each with its date, the arrangement, the engine and where the probe feed was. Moved here
word for word from the lab's README of 2026-11-23. The router is JumperlOS at `5374d38`, the commit this
repository's submodule is pinned to (the hash the lab gives its source is `9524e1cf...`).

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

From the ceilings (2026-11-21; see "Ceilings" (`Routing/solver/README.md`) for what each number is worth):

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
