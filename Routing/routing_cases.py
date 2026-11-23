#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The dense / edge-case routings, as data.

The lab routes them on the host. They began as the cases of JumperlOS's bench
test (JumperlOS/test/hil/test_routing_dense.py, which pastes them onto a
board); that file carries its own copy of them, so a case changed here or
there is changed in the other by hand. Standard library only, no board needed
to import it.
"""

# node ids (src/JumperlessDefines.h)
GND, TOP, BOT = 100, 101, 102
DAC0, DAC1 = 106, 107
ADC0, ADC1, ADC2, ADC3 = 110, 111, 112, 113
ISP, ISM = 108, 109                              # ISENSE_PLUS / ISENSE_MINUS (the 2 ohm shunt)
UART_TX, UART_RX = 116, 117
GP = {i: 130 + i for i in range(1, 9)}          # GP[1] = RP_GPIO_1 = 131
D = {i: 70 + i for i in range(14)}              # D[0] = NANO_D0
A = {i: 86 + i for i in range(8)}               # A[0] = NANO_A0

ALL_PAIRS_28 = [
    (1, 8), (2, 15), (3, 22), (4, 31), (5, 38), (6, 45), (7, 52),
    (9, 16), (10, 23), (11, 32), (12, 39), (13, 46), (14, 53),
    (17, 24), (18, 33), (19, 40), (20, 47), (21, 54),
    (25, 34), (26, 41), (27, 48), (28, 55),
    (35, 42), (36, 49), (37, 56),
    (43, 50), (44, 57),
    (51, 58),
]

# name, bridges, all_routed, (stack_paths, stack_rails, stack_dacs), electrical
CASES = [
    ("same_chip_pairs",
     [(1, 2), (3, 4), (5, 6), (8, 9), (10, 11), (15, 16)],
     True, (0, 0, 0), None),
    ("chain_all_chips",
     [(1, 8), (8, 15), (15, 22), (22, 31), (31, 38), (38, 45), (45, 52)],
     True, (0, 0, 0), None),
    ("parallel_AB",
     [(1, 8), (2, 9), (3, 10), (4, 11), (5, 12),
      (GP[1], 18), (GP[2], 25), (18, 25)],
     True, (0, 0, 0), ("loopback", 1, 2)),
    # exactly eight chip-K rows: two rails on two chips each, one DAC/ADC
    # net on two chips, DAC1 on one, plus the probe feed's row
    ("k_rows_all_eight",
     [(TOP, 1), (TOP, 8), (BOT, 31), (BOT, 38), (DAC0, 18), (DAC0, 19),
      (ADC0, 18), (ADC0, 25), (DAC1, 45)],
     True, (0, 0, 0), ("dac_adc", 0, 0, 2.5)),
    ("gnd_spread",
     [(GND, 1), (GND, 8), (GND, 15), (GND, 22), (GND, 31), (GND, 38),
      (GND, 45), (GND, 52)],
     True, (0, 0, 0), None),
    ("nano_moderate",
     [(D[0], 1), (D[1], 2), (D[2], 3), (D[3], 4),
      (A[0], 15), (A[1], 16), (A[2], 17), (A[3], 18)],
     True, (0, 0, 0), None),
    ("gpio_seven_from_chip_a",
     [(GP[i], i) for i in range(1, 8)],
     True, (0, 0, 0), None),
    ("sf_to_sf",
     [(DAC0, ADC0), (GP[1], ADC2), (GP[2], D[0]), (TOP, D[13]),
      (GP[3], GP[4]), (D[2], A[0]), (GND, A[1]), (UART_TX, D[1])],
     True, (0, 0, 0), ("loopback", 3, 4)),
    ("corner_rows",
     [(29, 1), (30, 8), (59, 31), (60, 38), (29, 30), (59, 60)],
     True, (0, 0, 0), None),
    ("big_net_thirteen_nodes",
     [(1, 8), (8, 15), (15, 22), (22, 31), (31, 38), (38, 45), (45, 52),
      (52, 2), (2, 9), (9, 16), (16, 23), (23, TOP)],
     True, (0, 0, 0), None),
    ("all_28_chip_pairs",
     ALL_PAIRS_28,
     True, (0, 0, 0), None),
    # forces the hub tier's H2 shape (row to row THROUGH an SF chip): seven
    # A-E nets spend the single A-E lane and every other chip's bounce row,
    # then four C-G nets (one lane) find no lane and no bounce row left
    ("h2_through_sf_chips",
     [(i, 30 + i) for i in range(1, 8)] + [(15, 45), (16, 46), (17, 47), (18, 48)],
     True, (0, 0, 0), None),
    ("nano_gpio_realistic",
     [(D[2], 1), (D[3], 2), (A[0], 15), (GP[1], 3), (GP[2], 4),
      (UART_TX, D[0]), (UART_RX, D[1]), (TOP, 5), (GND, 6), (GND, 16),
      (DAC0, 17), (ADC0, 18)],
     True, (0, 0, 0), None),
    ("kevin_fixture_2026_09_02",
     [(1, TOP), (38, GND), (2, ADC0), (ADC1, 3), (ADC2, 4), (5, ADC3),
      (6, GP[1]), (7, GP[2]), (GP[3], 8), (TOP, 11), (47, GND), (ADC3, D[0])],
     True, (2, 3, 0), None),   # no taps proof: all four ADCs are user nets here
    # Kevin's bench 2026-09-03: with stacking on, an LED at 12 mA on 24-28
    # showed no ants - chip D had no lane left for a sense tap (its K lane
    # to a primary, its I/J lanes to net 24-28's own duplicates) and the
    # rail net's duplicates had taken every bounce row. Every scanned row
    # must keep a tap route.
    ("stacked_taps_reachable",
     [(1, TOP), (38, GND), (2, ADC0), (5, ADC3), (6, GP[1]), (7, GP[2]),
      (GP[3], 8), (ADC3, D[0]), (18, 23), (41, 45), (48, 51), (56, 58),
      (56, GND), (18, TOP), (D[7], 18), (24, 28)],
     True, (2, 3, 0), ("taps",)),
    # the same netlist with GPIO stacking on: a GPIO's tap bounces through a
    # chip whose L lane must be free too, so the reservation has to keep a
    # chip that serves EVERY tap kind, not just rows
    ("stacked_taps_gpio_dups",
     [(1, TOP), (38, GND), (2, ADC0), (5, ADC3), (6, GP[1]), (7, GP[2]),
      (GP[3], 8), (ADC3, D[0]), (18, 23), (41, 45), (48, 51), (56, 58),
      (56, GND), (18, TOP), (D[7], 18), (24, 28)],
     True, (2, 3, 0, 2, 0), ("taps",)),
    ("rail_stacking_light",
     [(TOP, 1), (TOP, 15), (BOT, 31), (GND, 45), (DAC0, 8)],
     True, (2, 3, 1), ("taps",)),
    # test_net_currents' loop (DAC0 -> shunt -> row 5 -> GND) with stacking
    # on: the release gate of 2026-09-03 found row 5 with NO sense route.
    # The two SF-to-SF hub hops (the probe feed BUF_IN->GP_8, DAC0->I_POS)
    # had been packed onto K rows y0 and y1 - chip A's and B's only direct
    # lanes to the ADCs - and the loop's six stacked copies then spent every
    # bounce lane chip A had. bestSfRow now leaves a row-holding chip's K
    # row alone; every scanned node must keep a tap route.
    ("isense_loop_stacked",
     [(DAC0, ISP), (ISM, 5), (GND, 5)],
     True, (2, 2, 0), ("taps",)),
    # the same loop with chip A's own K row spent by a rail on row 2: the
    # tap for row 5 must then join the net's copper at a bounce row one of
    # its stacked copies rides (tier 4 accepts y0 when the net owns it)
    ("isense_loop_a_k_row_taken",
     [(2, TOP), (DAC0, ISP), (ISM, 5), (GND, 5)],
     True, (2, 2, 0), ("taps",)),
    # beyond the fabric on purpose: metrics only, but never a short
    ("nano_dense_metric",
     [(D[i], i + 1) for i in range(6)] + [(A[i], i + 15) for i in range(6)],
     False, (0, 0, 0), None),
    ("k_rows_overflow_metric",
     [(TOP, 1), (TOP, 15), (BOT, 8), (BOT, 22), (DAC0, 31), (DAC1, 38),
      (ADC0, 45), (ADC1, 52), (ADC2, 3), (ADC3, 17), (GND, 2), (GND, 9)],
     False, (0, 0, 0), None),
]


def bridge_dup(n1, n2, stacking):
    """The explicit duplicate count a case's stacking tuple gives one bridge:
    rail, DAC, GPIO and ADC bridges each have their own class."""
    paths, rails, dacs = stacking[:3]
    gpio = stacking[3] if len(stacking) > 3 else 0     # [routing] stack_gpio default
    adcs = stacking[4] if len(stacking) > 4 else 0     # [routing] stack_adcs default
    gpio_nodes = set(GP.values()) | {UART_TX, UART_RX}
    adc_nodes = {ADC0, ADC1, ADC2, ADC3}
    if n1 in (TOP, BOT, GND) or n2 in (TOP, BOT, GND):
        return rails
    if n1 in (DAC0, DAC1) or n2 in (DAC0, DAC1):
        return dacs
    if n1 in gpio_nodes or n2 in gpio_nodes:
        return gpio
    if n1 in adc_nodes or n2 in adc_nodes:
        return adcs
    return paths


def case_yaml(bridges, stacking):
    """One pastable state document. Stacking is carried PER BRIDGE as an
    explicit `dup:` count: the router honours a stored count >= 0 as-is, so
    the case controls its duplicates without touching the global
    [routing] stack_* config. (The slot loader turns a count equal to the
    slot's stackPaths back into "default", so the config block pins that at
    a value no case uses.)"""
    lines = ["version: 2", "sourceOfTruth: bridges", "", "bridges:"]
    for n1, n2 in bridges:
        lines.append("  - {n1: %d, n2: %d, dup: %d}" % (n1, n2, bridge_dup(n1, n2, stacking)))
    lines += ["", "power:", "  topRail: 0.00", "  bottomRail: 0.00",
              "  dac0: 0.00", "  dac1: 0.00", "",
              "config:",
              "  routing: {stackPaths: 9, stackRails: 9, stackDacs: 9, railPriority: 1}",
              ""]
    return "\n".join(lines) + "\n"
