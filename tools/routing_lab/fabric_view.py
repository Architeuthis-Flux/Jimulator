# SPDX-License-Identifier: MIT
"""The generated fabric diagram's geometry, worked out from an arrangement's
tables (V5's own, or any other: see arrangement.py).

Laid out like the sheet's two crossbar blocks: A to H in a row, I J K L in a
row above, every lane on a track of its own between them. A chip is a 16 by 8
grid of cells. An X pin's wire runs down its column, a Y pin's wire along its
row, so the crosspoint (x, y) is the centre of cell (x, y) and sits on both.

Every wire is one SVG path of horizontal and vertical segments. No two wires
share a track: X columns and their risers sit on x = 5 mod 10, every other
vertical run on an even x, and every horizontal run has a level of its own.
"""
import arrangement

CELL = 10
GRID_W, GRID_H = 16 * CELL, 8 * CELL
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


BUS_STEP = 4                            # a wire of no shape V5 has: a level of its own, with a riser to each pin
TRUNK_X, TRUNK_STEP = 40, 4             # right of the last chip: where a bus on both rows comes down from one to the other


def _path(*runs):
    return " ".join("M " + " L ".join("%d,%d" % p for p in run) for run in runs)


def _shape(name, ps, bb, is_node):
    """Which of V5's shapes a wire has, or "bus" for any other."""
    axes = [p[1] for p in ps]
    on_bb = [p[0] in bb for p in ps]
    if len(ps) == 1 and on_bb[0] and axes[0] == "Y":
        return "bounce" if ps[0][2] == 0 else "row"
    if len(ps) == 2 and not is_node and axes == ["X", "X"] and (all(on_bb) or not any(on_bb)):
        return "lane" if on_bb[0] else "hub"
    if len(ps) == 2 and not is_node and sorted((on, axis) for on, axis in zip(on_bb, axes)) == [(False, "Y"), (True, "X")]:
        return "approach"
    if not any(on_bb) and all(axis == "X" for axis in axes) and (len(ps) == 1 or name == "GND"):
        return "node"                           # GND_Y is GND's level; any other wire on several SF chips is a bus
    return "bus"


def layout(a=None):
    """The drawing of an arrangement's copper (V5's when None): {"size",
    "cell", "chips", "wires", "pads", "taken", "changed"}.

    Chips are placed by role, in CHIPS order: breadboard chips in the lower
    row, the others above. A wire of a shape V5 has is drawn as V5 draws it.
    Any other is a bus: a level of its own, 4 apart, in a band between the SF
    chips' lanes and the breadboard lanes, with a riser to each of its pins;
    its pins on an SF chip's X side join on a level of their own above that
    row, brought down beside the last chip. The drawing grows by what the
    buses, more lanes or more chips need, so for V5 every number is what it
    always was. A pin taken away has no wire."""
    a = a or arrangement.V5
    bb = [c for c in a.CHIPS if a.ROLE[c] == "bb"]
    sf = [c for c in a.CHIPS if a.ROLE[c] != "bb"]
    pins = {}                                   # wire name -> [(chip, axis, pin)]
    for chip in a.CHIPS:
        for axis, nets in (("X", a.X_NET[chip]), ("Y", a.Y_NET[chip])):
            for pin, name in enumerate(nets):
                if name is not None:
                    pins.setdefault(name, []).append((chip, axis, pin))

    node_of = {}                                # wire name -> the firmware's name for the node on it
    for node, name in a.NODE_NET.items():
        node_of.setdefault(name, a.NODE_NAME.get(node, str(node)))

    shape = {name: _shape(name, ps, bb, name in node_of) for name, ps in pins.items()}
    count = {s: sum(1 for v in shape.values() if v == s) for s in ("hub", "approach", "lane")}
    buses = sorted(name for name in pins if shape[name] == "bus")
    upper = [n for n in buses if any(c in sf and axis == "X" for c, axis, _ in pins[n])]     # joins SF X pins
    lower = [n for n in buses if any(c in bb or axis == "Y" for c, axis, _ in pins[n])]      # joins anything else
    trunks = [n for n in upper if n in lower]

    # Levels, top to bottom. With V5's 6 hub lanes, 32 lanes up to the SF row, 48 between breadboard chips and
    # no bus, these are the module's own numbers.
    upper_y0 = HUB_Y0 + HUB_STEP * max(count["hub"], 6)
    sf_y = SF_Y + HUB_STEP * max(0, count["hub"] - 6) + BUS_STEP * len(upper)
    approach_y0 = sf_y + APPROACH_Y0 - SF_Y
    band_y0 = approach_y0 + APPROACH_STEP * max(count["approach"], 32) + 4
    lane_y0 = band_y0 + BUS_STEP * len(lower) + LANE_Y0 - APPROACH_Y0 - APPROACH_STEP * 32 - 4
    bb_y = lane_y0 + LANE_STEP * max(count["lane"], 48) + BB_Y - LANE_Y0 - LANE_STEP * 48
    row_run_y0, row_pad_y = bb_y + ROW_RUN_Y0 - BB_Y, bb_y + ROW_PAD_Y - BB_Y

    origin = {c: (BB_X0 + BB_PITCH * i, bb_y) for i, c in enumerate(bb)}
    origin.update((c, (SF_X0 + SF_PITCH * i, sf_y)) for i, c in enumerate(sf))
    right = max(x for x, _ in origin.values()) + GRID_W
    end_pad_x = right + 20                      # a bus that is a node's and has no SF X pin: its pad, at its right end
    trunk_x = {n: right + TRUNK_X + TRUNK_STEP * i for i, n in enumerate(trunks)}
    width = max([SIZE[0]] + [x + GRID_W + (90 if c in bb else 210) for c, (x, _) in origin.items()]
                + [x + 50 for x in trunk_x.values()]
                + ([end_pad_x + 110] if (set(lower) - set(upper)) & set(node_of) else []))

    def col(chip, x):
        return origin[chip][0] + CELL // 2 + CELL * x

    def row(chip, y):
        return origin[chip][1] + CELL // 2 + CELL * y

    def column(chip, x, up_to):
        """An X pin's wire: down its column of the grid and up to a level."""
        return [(col(chip, x), origin[chip][1] + GRID_H), (col(chip, x), up_to)]

    def row_exit(chip, y, left_to):
        """A Y pin's wire: along its row of the grid and out to the left."""
        return [(origin[chip][0] + GRID_W, row(chip, y)), (left_to, row(chip, y))]

    def track(chip, y):
        """The vertical track of a Y pin, left of its chip: one for every pin."""
        return origin[chip][0] - (6 * (8 - y) if chip in bb else 2 + 4 * (7 - y))

    wires, pads = {}, {}
    lane_level, approach_level, hub_level = lane_y0, approach_y0, HUB_Y0

    def pad(name, x, y, **more):
        label = node_of.get(name, name)
        group = "row" if name.isdigit() else ("nano" if label[:1] in "DA" and label[1:].isdigit() or label == "AREF"
                                              else "special")
        pads[name] = dict({"x": x, "y": y, "label": label, "group": group}, **more)

    for name in sorted(pins):
        ps = pins[name]
        if shape[name] == "bounce":             # the bounce row: no hole, just a capped stub
            chip = ps[0][0]
            d, kind = _path(row_exit(chip, 0, origin[chip][0] - 4)), "bounce"
        elif shape[name] == "row":              # a breadboard row: out, down, across under the chip, down to its pad
            chip, _, y = ps[0]
            level = row_run_y0 + ROW_RUN_STEP * (7 - y)
            pad_x = origin[chip][0] + 10 + 20 * (y - 1)
            d = _path(row_exit(chip, y, track(chip, y)) + [(track(chip, y), level), (pad_x, level), (pad_x, row_pad_y)])
            kind = "row"
            pad(name, pad_x, row_pad_y)
        elif shape[name] == "lane":
            (c1, _, x1), (c2, _, x2) = ps       # a lane between two breadboard chips, on its own level
            d = _path(column(c1, x1, lane_level) + [(col(c2, x2), lane_level), (col(c2, x2), bb_y + GRID_H)])
            kind = "lane"
            lane_level += LANE_STEP
        elif shape[name] == "approach":
            low = next(p for p in ps if p[0] in bb)     # a lane from a breadboard chip's X pin to an SF chip's row
            high = next(p for p in ps if p[0] in sf)
            d = _path(column(low[0], low[2], approach_level)
                      + [(track(high[0], high[2]), approach_level), (track(high[0], high[2]), row(high[0], high[2]))]
                      + [(origin[high[0]][0] + GRID_W, row(high[0], high[2]))])
            kind = "lane"
            approach_level += APPROACH_STEP
        elif shape[name] == "hub":
            (c1, _, x1), (c2, _, x2) = ps       # a hub lane between two SF chips
            d = _path(column(c1, x1, hub_level) + [(col(c2, x2), hub_level), (col(c2, x2), sf_y + GRID_H)])
            kind = "hub"
            hub_level += HUB_STEP
        elif shape[name] == "node":
            (c1, _, x1) = ps[0]                 # a node on an SF chip: up to its pad (GND has a pin on K and on L)
            runs = [column(c1, x1, PAD_Y)]
            for c2, _, x2 in ps[1:]:
                runs.append([(col(c1, x1), GND_Y), (col(c2, x2), GND_Y), (col(c2, x2), sf_y + GRID_H)])
            d, kind = _path(*runs), ("row" if name.isdigit() else "special")
            pad(name, col(c1, x1), PAD_Y)
        else:                                   # a bus: every pin rises (or falls) to the wire's own level
            high = upper_y0 + BUS_STEP * upper.index(name) if name in upper else None
            low = band_y0 + BUS_STEP * lower.index(name) if name in lower else None
            runs, high_x, low_x = [], [], []
            for chip, axis, pin in ps:
                if chip in sf and axis == "X":              # up its column; the first, for a node, on up to its pad
                    first = name in node_of and not high_x
                    runs.append(column(chip, pin, PAD_Y if first else high))
                    high_x.append(col(chip, pin))
                    if first:
                        pad(name, col(chip, pin), PAD_Y)
                elif axis == "X":                           # straight up its column to the band
                    runs.append(column(chip, pin, low))
                    low_x.append(col(chip, pin))
                else:                                       # out to the left on its own track, and to the band there
                    runs.append(row_exit(chip, pin, track(chip, pin)) + [(track(chip, pin), low)])
                    low_x.append(track(chip, pin))
            if name in trunk_x:
                runs.append([(trunk_x[name], high), (trunk_x[name], low)])
                high_x.append(trunk_x[name])
                low_x.append(trunk_x[name])
            elif name in node_of and not high_x:
                pad(name, end_pad_x, low, side="right")     # ponytail: two such pads sit 4 apart and their labels overlap
                low_x.append(end_pad_x)
            for xs, level in ((high_x, high), (low_x, low)):
                if len(set(xs)) > 1:
                    runs.append([(min(xs), level), (max(xs), level)])
            d, kind = _path(*runs), "bus"
        wires[name] = {"kind": kind, "d": d, "label": None}

    chips = {c: {"x": origin[c][0], "y": origin[c][1], "role": "bb" if c in bb else "sf"} for c in a.CHIPS}
    return {"size": [width, bb_y + SIZE[1] - BB_Y], "cell": CELL, "chips": chips, "wires": wires, "pads": pads,
            "taken": [{"chip": c, "axis": axis, "pin": pin} for c, axis, pin in a.taken],
            "changed": [{"chip": c, "axis": axis, "pin": pin} for c, axis, pin in a.changed]}


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
