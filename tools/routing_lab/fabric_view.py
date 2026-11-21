# SPDX-License-Identifier: MIT
"""The generated fabric diagram's geometry, worked out from fabric_v5.

Laid out like the sheet's two crossbar blocks: A to H in a row, I J K L in a
row above, every lane on a track of its own between them. A chip is a 16 by 8
grid of cells. An X pin's wire runs down its column, a Y pin's wire along its
row, so the crosspoint (x, y) is the centre of cell (x, y) and sits on both.

Every wire is one SVG path of horizontal and vertical segments. No two wires
share a track: X columns and their risers sit on x = 5 mod 10, every other
vertical run on an even x, and every horizontal run has a level of its own.
"""
import sys
from pathlib import Path

HIL = Path(__file__).resolve().parent.parent.parent / "test" / "hil"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

from fabric_v5 import CHIPS, NODE_NAME, NODE_NET, X_NET, Y_NET      # noqa: E402

CELL = 10
GRID_W, GRID_H = 16 * CELL, 8 * CELL
BB, SF = "ABCDEFGH", "IJKL"
BB_X0, BB_PITCH = 60, 230               # breadboard chips: left edge of A, spacing
SF_X0, SF_PITCH = 170, 460              # special-function chips sit over the gaps A|B, C|D, E|F, G|H
PAD_Y = 90                              # pads of the nodes on I J K L (their labels slant up from here)
GND_Y = 110                             # GND's level: it has a pin on K and a pin on L
HUB_Y0, HUB_STEP = 124, 6               # six hub lanes
SF_Y = 180
APPROACH_Y0, APPROACH_STEP = 280, 4     # 32 lanes from a breadboard chip up to an SF chip's row
LANE_Y0, LANE_STEP = 420, 4             # 48 lanes between breadboard chips
BB_Y = 630
ROW_RUN_Y0, ROW_RUN_STEP = 718, 5       # the seven rows of a chip fan out under it
ROW_PAD_Y = 770
SIZE = (1920, 800)


def _chip_origin(chip):
    if chip in BB:
        return BB_X0 + BB_PITCH * BB.index(chip), BB_Y
    return SF_X0 + SF_PITCH * SF.index(chip), SF_Y


def _col(chip, x):
    return _chip_origin(chip)[0] + CELL // 2 + CELL * x


def _row(chip, y):
    return _chip_origin(chip)[1] + CELL // 2 + CELL * y


def _path(*runs):
    return " ".join("M " + " L ".join("%d,%d" % p for p in run) for run in runs)


def _column(chip, x, up_to):
    """An X pin's wire: down its column of the grid and up to a level."""
    top = _chip_origin(chip)[1]
    return [(_col(chip, x), top + GRID_H), (_col(chip, x), up_to)]


def _row_exit(chip, y, left_to):
    """A Y pin's wire: along its row of the grid and out to the left."""
    left = _chip_origin(chip)[0]
    return [(left + GRID_W, _row(chip, y)), (left_to, _row(chip, y))]


def layout():
    pins = {}                                   # wire name -> [(chip, axis, pin)]
    for chip in CHIPS:
        for axis, nets in (("X", X_NET[chip]), ("Y", Y_NET[chip])):
            for pin, name in enumerate(nets):
                pins.setdefault(name, []).append((chip, axis, pin))

    node_of = {}                                # wire name -> the firmware's name for the node on it
    for node, name in NODE_NET.items():
        node_of.setdefault(name, NODE_NAME.get(node, str(node)))

    wires, pads = {}, {}
    lane_level, approach_level, hub_level = LANE_Y0, APPROACH_Y0, HUB_Y0

    def pad(name, x, y):
        label = node_of.get(name, name)
        group = "row" if name.isdigit() else ("nano" if label[:1] in "DA" and label[1:].isdigit() or label == "AREF"
                                              else "special")
        pads[name] = {"x": x, "y": y, "label": label, "group": group}

    for name in sorted(pins):
        ps = pins[name]
        chips = [p[0] for p in ps]
        axes = [p[1] for p in ps]
        if len(ps) == 1 and chips[0] in BB and axes[0] == "Y":
            chip, _, y = ps[0]
            left = _chip_origin(chip)[0]
            if y == 0:                          # the bounce row: no hole, just a capped stub
                d, kind = _path(_row_exit(chip, 0, left - 4)), "bounce"
            else:                               # a breadboard row: out, down, across under the chip, down to its pad
                track = left - 6 * (8 - y)
                level = ROW_RUN_Y0 + ROW_RUN_STEP * (7 - y)
                pad_x = left + 10 + 20 * (y - 1)
                d = _path(_row_exit(chip, y, track) + [(track, level), (pad_x, level), (pad_x, ROW_PAD_Y)])
                kind = "row"
                pad(name, pad_x, ROW_PAD_Y)
        elif len(ps) == 2 and all(c in BB for c in chips) and axes == ["X", "X"]:
            (c1, _, x1), (c2, _, x2) = ps       # a lane between two breadboard chips, on its own level
            d = _path(_column(c1, x1, lane_level) + [(_col(c2, x2), lane_level), (_col(c2, x2), BB_Y + GRID_H)])
            kind = "lane"
            lane_level += LANE_STEP
        elif len(ps) == 2 and sorted(axes) == ["X", "Y"] and {chips[0] in BB, chips[1] in BB} == {True, False}:
            bb = next(p for p in ps if p[0] in BB)      # a lane from a breadboard chip's X pin to an SF chip's row
            sf = next(p for p in ps if p[0] in SF)
            track = _chip_origin(sf[0])[0] - 2 - 4 * (7 - sf[2])
            d = _path(_column(bb[0], bb[2], approach_level)
                      + [(track, approach_level), (track, _row(sf[0], sf[2]))]
                      + [(_chip_origin(sf[0])[0] + GRID_W, _row(sf[0], sf[2]))])
            kind = "lane"
            approach_level += APPROACH_STEP
        elif len(ps) == 2 and all(c in SF for c in chips) and axes == ["X", "X"] and name not in NODE_NET.values():
            (c1, _, x1), (c2, _, x2) = ps       # a hub lane between two SF chips
            d = _path(_column(c1, x1, hub_level) + [(_col(c2, x2), hub_level), (_col(c2, x2), SF_Y + GRID_H)])
            kind = "hub"
            hub_level += HUB_STEP
        elif all(c in SF for c in chips) and all(a == "X" for a in axes):
            (c1, _, x1) = ps[0]                 # a node on an SF chip: up to its pad (GND has a pin on K and on L)
            runs = [_column(c1, x1, PAD_Y)]
            for c2, _, x2 in ps[1:]:
                runs.append([(_col(c1, x1), GND_Y), (_col(c2, x2), GND_Y), (_col(c2, x2), SF_Y + GRID_H)])
            d, kind = _path(*runs), ("row" if name.isdigit() else "special")
            pad(name, _col(c1, x1), PAD_Y)
        else:
            raise ValueError("fabric wire %r has a shape this layout does not know: %r" % (name, ps))
        wires[name] = {"kind": kind, "d": d, "label": None}

    chips = {c: {"x": _chip_origin(c)[0], "y": _chip_origin(c)[1], "role": "bb" if c in BB else "sf"} for c in CHIPS}
    return {"size": list(SIZE), "cell": CELL, "chips": chips, "wires": wires, "pads": pads}


def pin_point(view, chip, axis, pin):
    """Where a pin's wire leaves the grid: the top of its column (X) or the left end of its row (Y)."""
    c, cell = view["chips"][chip], view["cell"]
    if axis == "X":
        return (c["x"] + cell // 2 + cell * pin, c["y"])
    return (c["x"], c["y"] + cell // 2 + cell * pin)


def segments(d):
    """The straight segments of a path made of M and L commands."""
    out, last = [], None
    tokens = d.split()
    for i, tok in enumerate(tokens):
        if tok in ("M", "L"):
            x, y = (int(v) for v in tokens[i + 1].split(","))
            if tok == "L":
                out.append((last, (x, y)))
            last = (x, y)
    return out


def _on(segment, point):
    (x1, y1), (x2, y2) = segment
    x, y = point
    if x1 == x2:
        return x == x1 and min(y1, y2) <= y <= max(y1, y2)
    return y == y1 and min(x1, x2) <= x <= max(x1, x2)


def touches(d, point):
    return any(_on(s, point) for s in segments(d))


def overlaps(view):
    """Pairs of different wires that run along the same line for some length."""
    runs = {}                                   # ("v", x) or ("h", y) -> [(low, high, wire)]
    for name, w in view["wires"].items():
        for (x1, y1), (x2, y2) in segments(w["d"]):
            if x1 == x2:
                runs.setdefault(("v", x1), []).append((min(y1, y2), max(y1, y2), name))
            else:
                runs.setdefault(("h", y1), []).append((min(x1, x2), max(x1, x2), name))
    found = []
    for line, spans in runs.items():
        spans.sort()
        for i, (lo, hi, name) in enumerate(spans):
            for lo2, hi2, other in spans[i + 1:]:
                if lo2 >= hi:
                    break
                if other != name and min(hi, hi2) > lo2:
                    found.append((name, other, line))
    return found
