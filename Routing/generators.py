# SPDX-License-Identifier: MIT
"""Generated cases: typical circuits, random netlists, stress and
beyond-the-fabric sets. Everything is seeded (random.Random, never the global
generator), so a name always means the same netlist. Nothing here is required
to route fully: these are scored, not asserted.
"""
import random

from cases import Case, fabric_v5, routing_cases

GND, TOP, BOT, DAC0, DAC1 = 100, 101, 102, 106, 107
ADC = [110, 111, 112, 113]
GPIO = list(range(131, 139))                    # GPIO_1..8
NANO_D = list(range(70, 84))                    # D0..D13
NANO_A = list(range(86, 94))                    # A0..A7
UART = [116, 117]
AREF = 85
MAX_BRIDGES_V5 = 128                            # src/JumperlessDefines.h, the non-OG branch

# Every node a user can wire: the fabric's nodes without the probe buffer.
USER_NODES = sorted(n for n in fabric_v5.NODE_NAME if n not in (139, 140))
ROWS = list(range(1, 61))
SPECIALS = [n for n in USER_NODES if n > 60]
# The seven breadboard rows on each chip A..H, from the schematic.
CHIP_ROWS = {chip: [int(n) for n in fabric_v5.Y_NET[chip][1:]] for chip in "ABCDEFGH"}


# Every pair of nodes the firmware keeps out of one net. Two tables in
# src/routing/MatrixState.cpp: globalDoNotIntersects, and each special net's
# own doNotIntersectNodes (which is what keeps DAC0 and DAC1 apart). A test
# compares this copy with what the harness prints (--forbidden-pairs).
FORBIDDEN_PAIRS = (
    [(GND, TOP), (GND, BOT), (GND, DAC1), (TOP, DAC1), (TOP, DAC0), (BOT, DAC1), (BOT, DAC0), (TOP, BOT),
     (DAC0, DAC1)]
    + [(node, supply) for node in GPIO + UART + [140] for supply in (TOP, BOT, DAC1, DAC0)])


def legal(bridges):
    """True when the firmware would take every bridge: none has equal ends,
    and no net would hold a pair the firmware keeps apart (directly or through
    shared nodes). The firmware refuses such a bridge or vetoes its path, and
    a refusal must never be read as the router failing to route."""
    parent = {}

    def find(n):
        parent.setdefault(n, n)
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    for a, b in bridges:
        if a == b:
            return False
        parent[find(a)] = find(b)
    return not any(a in parent and b in parent and find(a) == find(b) for a, b in FORBIDDEN_PAIRS)


def _case(name, cls, pairs, dup=-1, notes=""):
    return Case(name, cls, [(a, b, dup) for a, b in pairs], notes=notes)


def _dedupe(pairs):
    seen, out = set(), []
    for a, b in pairs:
        key = (min(a, b), max(a, b))
        if key not in seen:
            seen.add(key)
            out.append((a, b))
    return out


def fuzz(seed=1, n=2000, max_bridges=12, row_bias=60):
    """Random netlists: each end is a row with probability row_bias percent,
    else any other user node."""
    rng = random.Random(seed)

    def end():
        return rng.choice(ROWS) if rng.randrange(100) < row_bias else rng.choice(SPECIALS)

    out = []
    while len(out) < n:
        count = 1 + rng.randrange(max_bridges)
        pairs = []
        while len(pairs) < count:
            a, b = end(), end()
            if a != b:
                pairs.append((a, b))
        if legal(pairs):
            out.append(_case("fuzz_%d_%d" % (seed, len(out)), "fuzz", pairs))
    return out


def typical(seed=1, n=200):
    """Circuits shaped like everyday use: one or two ICs across the gap with
    power, ground and a few signal pins wired out, some jumpers, some extra
    rail or ground drops."""
    rng = random.Random(seed)
    signal_kinds = ("gpio", "gpio", "adc", "dac", "nano", "nano", "uart", "row")

    def signal():
        kind = rng.choice(signal_kinds)
        if kind == "gpio":
            return rng.choice(GPIO)
        if kind == "adc":
            return rng.choice(ADC)
        if kind == "dac":
            return rng.choice((DAC0, DAC1))
        if kind == "nano":
            return rng.choice(NANO_D + NANO_A)
        if kind == "uart":
            return rng.choice(UART)
        return rng.choice(ROWS)

    out = []
    while len(out) < n:
        pairs = []
        for _ in range(rng.choice((1, 1, 2))):
            width = rng.choice((4, 7, 8))
            first = rng.randint(1, 30 - width + 1)
            pins = list(range(first, first + width)) + list(range(first + 30, first + 30 + width))
            rng.shuffle(pins)
            pairs.append((pins[0], rng.choice((TOP, BOT))))
            pairs.append((pins[1], GND))
            for pin in pins[2:2 + rng.randint(2, 5)]:
                pairs.append((pin, signal()))
        for _ in range(rng.randint(0, 3)):
            pairs.append(tuple(rng.sample(ROWS, 2)))
        for _ in range(rng.randint(0, 2)):
            pairs.append((rng.choice(ROWS), rng.choice((TOP, BOT, GND))))
        pairs = _dedupe(pairs)
        if 4 <= len(pairs) <= 20 and legal(pairs):
            out.append(_case("typical_%d_%d" % (seed, len(out)), "typical", pairs))
    return out


def stress():
    """Hand-shaped hard cases, each aimed at one scarce resource."""
    out = []
    for chip, rows in CHIP_ROWS.items():
        out.append(_case("flood_%s_gpio" % chip, "stress", list(zip(rows, GPIO)),
                         notes="seven GPIO nets out of one chip: one L lane, the rest bounce"))
        out.append(_case("flood_%s_k" % chip, "stress", list(zip(rows, [TOP, BOT, DAC0, DAC1] + ADC[:3])),
                         notes="seven chip-K nets out of one chip: one K lane, the rest bounce"))
    out.append(_case("gnd_two_rows_every_chip", "stress",
                     [(GND, row) for rows in CHIP_ROWS.values() for row in rows[:2]]))
    out.append(_case("corner_rows_to_specials", "stress", [(29, TOP), (30, GPIO[0]), (59, DAC0), (60, ADC[0])],
                     notes="rows 29, 30, 59, 60 are X pins of K and L"))
    out.append(_case("six_hub_lanes", "stress",
                     [(NANO_D[1], NANO_D[0]), (NANO_D[3], DAC1), (NANO_D[5], GPIO[0]),
                      (NANO_D[2], ADC[1]), (NANO_D[4], GPIO[1]), (ADC[2], GPIO[2])],
                     notes="one net per hub lane: IJ, IK, IL, JK, JL, KL (DAC0 left to the probe feed)"))
    spread = [rows[i] for i in range(5) for rows in CHIP_ROWS.values()]      # 40 rows, chip after chip
    out.append(_case("one_net_forty_nodes", "stress", list(zip(spread, spread[1:])),
                     notes="one net at MAX_NODES, every bridge crossing chips"))
    out.append(_case("max_duplicates", "stress",
                     list(routing_cases.ALL_PAIRS_28) + [(TOP, r) for r in (1, 2, 3, 4)] + [(GND, r) for r in (5, 6, 7, 9)],
                     dup=7, notes="every chip pair plus two rails, each asking for seven copies"))
    return out


def beyond():
    """Over the fabric on purpose: scored, and must stay short-free."""
    out = [
        _case("every_nano_pin", "beyond", list(zip(NANO_D + NANO_A, range(1, 23))),
              notes="22 Nano nets; chips I and J have eight rows each"),
        _case("nine_k_nets", "beyond",
              list(zip([TOP, BOT, DAC0, DAC1] + ADC + [AREF], [1, 8, 15, 22, 31, 38, 45, 52, 2])),
              notes="nine chip-K nets for eight K rows"),
    ]
    rng = random.Random(7)
    pairs, seen = [], set()
    while len(pairs) < MAX_BRIDGES_V5:
        a = rng.choice(ROWS) if rng.randrange(100) < 60 else rng.choice(SPECIALS)
        b = rng.choice(ROWS) if rng.randrange(100) < 60 else rng.choice(SPECIALS)
        key = (min(a, b), max(a, b))
        if a != b and key not in seen and legal(pairs + [(a, b)]):
            seen.add(key)
            pairs.append((a, b))
    out.append(_case("max_bridges_random", "beyond", pairs, notes="MAX_BRIDGES random bridges, seed 7"))
    return out
