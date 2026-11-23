# SPDX-License-Identifier: MIT
"""The KiCad sheet view's data, read from the board's .kicad_sch.

overlay() finds, in sheet millimetres (the units of the file and of
kicad-cli's SVG plot): the wire segments and label positions of every net of
the crossbar fabric, where each crossbar pin ends, each crossbar symbol's
body, and the copper a wire's signal goes on to past the fabric (BEYOND: the
other side of its op-amp, jumper or shunt). build() also has kicad-cli plot
the sheet as the backdrop. Both land in build/sheet/; nothing is written next
to the schematic.

Like JumperlOS/test/hil/fabric_v5.py this is derived from the schematic, not from the
firmware's tables. Net names come from fabric_v5, so the two agree by
construction on what a net is called.
"""
import heapq
import json
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import variants

HIL = variants.HIL    # JumperlOS/test/hil, which variants puts on the path

import fabric_v5      # noqa: E402

DEFAULT_SCH = Path("~/Documents/GitHub/JumperlessV5/Jumperless23V50/MainBoard/JumperlessV5r7/"
                   "JumperlessV5r7.kicad_sch").expanduser()
SHEET_DIR = variants.BUILD_DIR / "sheet"
KICAD_CLI = ("kicad-cli", "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
PAPER = {"A0": (1189.0, 841.0), "A1": (841.0, 594.0), "A2": (594.0, 420.0), "A3": (420.0, 297.0),
         "A4": (297.0, 210.0), "A5": (210.0, 148.0)}
HINT = "python3 Routing/lab.py sheet [path/to/board.kicad_sch]"



def _past(net, by, kind, way, gain=None):
    return {"net": net, "by": by, "kind": kind, "way": way, **({"gain": gain} if gain else {})}


# What a crossbar wire's signal becomes past the fabric on the V5 r7 sheet, read from that schematic on 2026-11-23:
# for each wire, the copper beyond it in order away from the crossbar.
#   net   a label on the sheet, or a name given in ANCHOR to copper that has none
#   by    the part between
#   kind  "same": the same signal, across a closed jumper, a 0R or a 2 ohm shunt
#         "buffer": after an op-amp follower;  "scale": after a stage that scales and shifts it (gain says how)
#   way   "out": the wire feeds the stage;  "in": the stage drives the wire
# Only these eleven wires have an op-amp stage (the UART, AREF, the Nano header, the rows and the lanes have none),
# and the sheet has no level shifter. The page draws "same" as the wire is drawn and the other two striped.
_ADC_8V = "x0.182 + 1.65 V (+-8 V reads 0.19 to 3.11 V)"
_DAC = "x4.05 - 8.3 V"
BEYOND = {
    "ROUTABLE_BUFFER_IN": [_past("ROUTABLE_BUFFER_OUT", "U7A", "buffer", "out"),
                           _past("ADC_UNBUFFERED_+-8V_PROBE", "R88 (0R)", "same", "out"),
                           _past("after U7B", "U7B", "buffer", "out"),
                           _past("ADC_BUFFERED_+-8V_PROBE", "U7B's divider", "scale", "out", _ADC_8V)],
    "ROUTABLE_BUFFER_OUT": [_past("ROUTABLE_BUFFER_IN", "U7A", "buffer", "in")],
    **{"ADC_UNBUFFERED_+-8V_%d" % n: [_past("after U11" + unit, "U11" + unit, "buffer", "out"),
                                      _past("ADC_BUFFERED_+-8V_%d" % n, "U11%s's divider" % unit, "scale", "out", _ADC_8V)]
       for n, unit in enumerate("ABCD")},
    "ADC_UNBUFFERED_5V_4": [_past("after U7D", "U7D", "buffer", "out"),
                            _past("ADC_BUFFERED_5V_4", "R87 and R82", "scale", "out", "x0.667")],
    "DAC_0": [_past("R_SENSE+", "R57 (the 2 ohm shunt)", "same", "in"), _past("DAC_0_OUT", "U10A", "scale", "in", _DAC)],
    "DAC_1": [_past("after U10B", "U12", "same", "in"), _past("DAC_1_OUT", "U10B", "scale", "in", _DAC)],
    "TOP_RAIL": [_past("after U1807A", "JP3", "same", "in"), _past("DAC_2_OUT", "U1807A", "scale", "in", _DAC)],
    "BOTTOM_RAIL": [_past("after U1807B", "JP4", "same", "in"), _past("DAC_3_OUT", "U1807B", "scale", "in", _DAC)],
    "Net-(I1-X11)": [_past("CURR_SENSE+", "JP5", "same", "out")],
    "Net-(J6-X11)": [_past("CURR_SENSE-", "JP6", "same", "out")],
    **{"GPIO_%d" % n: [_past("RP_GPIO_%d" % n, "its jumper (JP23 to JP30)", "same", "out")] for n in range(20, 28)},
}
# copper with no label, named by a point on it (an op-amp's output pin)
ANCHOR = {"after U11A": (581.66, 229.87), "after U11B": (580.39, 255.27), "after U11C": (581.66, 280.67),
          "after U11D": (580.39, 308.61), "after U7D": (581.66, 193.04), "after U7B": (708.025, 193.04),
          "after U10B": (680.085, 301.625), "after U1807A": (746.76, 262.89), "after U1807B": (745.49, 303.53)}
# a second label on a wire's own copper: DAC_0's at the shunt
ALIAS = {"R_SENSE-": "DAC_0"}


class SheetUnavailable(Exception):
    """The sheet view cannot be made. .hint says what to run once the cause is fixed."""

    def __init__(self, message, hint=HINT):
        super().__init__(message)
        self.hint = hint


_TOKEN = re.compile(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()]+')


def parse_sexpr(text):
    """One s-expression as nested lists of strings."""
    stack, current = [], None
    for m in _TOKEN.finditer(text):
        tok = m.group(0)
        if tok == "(":
            stack.append(current)
            current = []
        elif tok == ")":
            done, current = current, stack.pop()
            if current is None:
                return done
            current.append(done)
        elif tok[0] == '"':
            current.append(re.sub(r"\\(.)", r"\1", tok[1:-1]))
        else:
            current.append(tok)
    raise ValueError("unbalanced s-expression")


def _all(node, head):
    return [c for c in node if isinstance(c, list) and c and c[0] == head]


def _one(node, head):
    found = _all(node, head)
    return found[0] if found else None


def _num(value):
    f = round(float(value), 4)
    return int(f) if f == int(f) else f


def pin_point(at, mirror, pin_at):
    """Where a pin ends on the sheet. at: the symbol's (x, y, angle); mirror:
    None, "x" or "y"; pin_at: the pin's (x, y) in the library symbol, whose y
    axis points up while the sheet's points down. The symbol is turned first,
    then flipped across the sheet's own axis."""
    sx, sy, angle = at
    px, py = pin_at
    turn = int(angle) % 360
    if turn == 90:
        px, py = -py, px
    elif turn == 180:
        px, py = -px, -py
    elif turn == 270:
        px, py = py, -px
    dx, dy = px, -py                                # the offset on the sheet
    if mirror == "x":
        dy = -dy
    elif mirror == "y":
        dx = -dx
    return (_num(sx + dx), _num(sy + dy))


def _on_segment(p, seg):
    (x, y), (x1, y1, x2, y2) = p, seg
    if abs((x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)) > 1e-6:
        return False
    return min(x1, x2) - 1e-6 <= x <= max(x1, x2) + 1e-6 and min(y1, y2) - 1e-6 <= y <= max(y1, y2) + 1e-6


def overlay(sch_path):
    """See the module docstring. Keys: size, nets, pins, bodies, beyond."""
    tree = parse_sexpr(Path(sch_path).read_text())
    fabric_names = {n for c in fabric_v5.CHIPS for n in fabric_v5.X_NET[c] + fabric_v5.Y_NET[c]}
    beyond = {wire: past for wire, past in BEYOND.items() if wire in fabric_names}
    keep = fabric_names | {t["net"] for past in beyond.values() for t in past}     # the nets worth their copper

    paper = _one(tree, "paper") or ["paper", "A4"]
    size = [float(paper[2]), float(paper[3])] if paper[1] == "User" else list(PAPER.get(paper[1], PAPER["A4"]))
    if "portrait" in paper:
        size.reverse()

    # the crossbar's library symbol(s): pin name -> position, and the body's rectangle
    library = {}
    for sym in _all(_one(tree, "lib_symbols") or [], "symbol"):
        if not sym[1].endswith("CH446Q"):
            continue
        pins, rect = {}, None
        for unit in _all(sym, "symbol"):
            for pin in _all(unit, "pin"):
                at, name = _one(pin, "at"), _one(pin, "name")
                if at and name and re.fullmatch(r"[XY]\d+", name[1]):
                    pins[name[1]] = (float(at[1]), float(at[2]))
            r = _one(unit, "rectangle")
            if r and rect is None:
                s, e = _one(r, "start"), _one(r, "end")
                rect = (float(s[1]), float(s[2]), float(e[1]), float(e[2]))
        library[sym[1]] = (pins, rect)

    pins, bodies, pin_wire = {}, {}, {}             # pin_wire: sheet point -> the fabric's name for that pin's copper
    for sym in _all(tree, "symbol"):
        lib_id = _one(sym, "lib_id")
        if not lib_id or lib_id[1] not in library:
            continue
        ref = next((p[2] for p in _all(sym, "property") if p[1] == "Reference"), "")
        chip = ref[:1]
        if chip not in fabric_v5.CHIPS:
            continue
        at = _one(sym, "at")
        place = (float(at[1]), float(at[2]), int(float(at[3])) if len(at) > 3 else 0)
        mirror = (_one(sym, "mirror") or [None, None])[1]
        lib_pins, rect = library[lib_id[1]]
        for name, where in lib_pins.items():
            axis, index = name[0], int(name[1:])
            table = fabric_v5.X_NET if axis == "X" else fabric_v5.Y_NET
            point = pin_point(place, mirror, where)
            pins["%s.%s%d" % (chip, axis, index)] = list(point)
            if index < len(table[chip]):
                pin_wire[point] = table[chip][index]
        if rect:
            (x1, y1), (x2, y2) = pin_point(place, mirror, rect[:2]), pin_point(place, mirror, rect[2:])
            bodies[chip] = [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]

    segments = []
    for w in _all(tree, "wire"):
        pts = _all(_one(w, "pts"), "xy")
        segments.append((_num(pts[0][1]), _num(pts[0][2]), _num(pts[1][1]), _num(pts[1][2])))

    # wires that share an end, or meet at a junction, are one piece of copper
    parent = list(range(len(segments)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    ends = {}
    for i, (x1, y1, x2, y2) in enumerate(segments):
        for p in ((x1, y1), (x2, y2)):
            if p in ends:
                parent[find(i)] = find(ends[p])
            else:
                ends[p] = i
    for j in _all(tree, "junction"):
        at = _one(j, "at")
        p = (_num(at[1]), _num(at[2]))
        touching = [i for i, s in enumerate(segments) if _on_segment(p, s)]
        for i in touching[1:]:
            parent[find(i)] = find(touching[0])

    def group_at(p):
        if p in ends:
            return find(ends[p])
        return next((find(i) for i, s in enumerate(segments) if _on_segment(p, s)), None)

    # a piece's net: the fabric's name for a crossbar pin on it, else the name on a label
    labels = []                                     # (net name by its text, point, group or None)
    for kind, prefix in (("label", "/"), ("global_label", "")):
        for lab in _all(tree, kind):
            at = _one(lab, "at")
            p = (_num(at[1]), _num(at[2]))
            labels.append((ALIAS.get(prefix + lab[1], prefix + lab[1]), p, group_at(p)))
    name_of = {}
    for name, p, g in labels:
        if g is not None and name in keep:
            name_of.setdefault(g, name)
    for name, p in ANCHOR.items():                  # copper with no label of its own
        g = group_at(p)
        if g is not None and name in keep:
            name_of.setdefault(g, name)
    for p, name in pin_wire.items():                # a pin's own name wins over a label's
        g = group_at(p)
        if g is not None:
            name_of[g] = name

    nets = {}
    for i, seg in enumerate(segments):
        name = name_of.get(find(i))
        if name in keep:
            nets.setdefault(name, {"segments": [], "labels": []})["segments"].append(list(seg))
    for text, p, g in labels:
        name = name_of.get(g) if g is not None else pin_wire.get(p, text)
        if name in keep:
            nets.setdefault(name, {"segments": [], "labels": []})["labels"].append(list(p))
    _follow_buses(tree, nets)
    beyond = {wire: [t for t in past if t["net"] in nets] for wire, past in beyond.items()}     # what this sheet has
    return {"size": size, "nets": nets, "pins": pins, "bodies": bodies,
            "beyond": {wire: past for wire, past in beyond.items() if past}}


def _follow_buses(tree, nets):
    """r7 draws its breadboard-to-breadboard lanes as stubs that enter a shared
    bus. Adds to each such net its bus entries and the stretch of bus between
    them, so the lane is drawn from chip to chip."""
    at_point = {}                                   # a point on a net's copper or label -> the net
    for name, n in nets.items():
        for s in n["segments"]:
            at_point[(s[0], s[1])] = at_point[(s[2], s[3])] = name
        for p in n["labels"]:
            at_point[tuple(p)] = name
    entries = {}                                    # net -> [(its wire's end, the bus end)]
    for e in _all(tree, "bus_entry"):
        at, size = _one(e, "at"), _one(e, "size")
        a = (_num(at[1]), _num(at[2]))
        b = (_num(float(at[1]) + float(size[1])), _num(float(at[2]) + float(size[2])))
        for wire_end, bus_end in ((a, b), (b, a)):
            if wire_end in at_point:
                entries.setdefault(at_point[wire_end], []).append((wire_end, bus_end))
                break
    buses = []
    for bus in _all(tree, "bus"):
        pts = _all(_one(bus, "pts"), "xy")
        buses.append((_num(pts[0][1]), _num(pts[0][2]), _num(pts[1][1]), _num(pts[1][2])))
    # the buses as a graph, each segment cut wherever another bus ends on it or an entry lands on it
    stops = {p for s in buses for p in ((s[0], s[1]), (s[2], s[3]))} | {b for es in entries.values() for _, b in es}
    graph = {}
    for s in buses:
        along = sorted((p for p in stops if _on_segment(p, s)),
                       key=lambda p: (p[0] - s[0]) * (s[2] - s[0]) + (p[1] - s[1]) * (s[3] - s[1]))
        for p, q in zip(along, along[1:]):
            graph.setdefault(p, []).append((q, math.dist(p, q)))
            graph.setdefault(q, []).append((p, math.dist(p, q)))
    for name, found in entries.items():
        segments = nets[name]["segments"]
        segments.extend([*wire_end, *bus_end] for wire_end, bus_end in found)
        start = found[0][1]                         # shortest way along the bus from the first entry to each other
        best, before, heap = {start: 0.0}, {}, [(0.0, start)]
        while heap:
            d, p = heapq.heappop(heap)
            if d > best[p]:
                continue
            for q, step in graph.get(p, ()):
                if d + step < best.get(q, math.inf):
                    best[q], before[q] = d + step, p
                    heapq.heappush(heap, (d + step, q))
        walked = set()
        for _, goal in found[1:]:
            while goal in before and (before[goal], goal) not in walked:
                walked.add((before[goal], goal))
                segments.append([*before[goal], *goal])
                goal = before[goal]


def kicad_cli():
    """The kicad-cli to run, or None."""
    for candidate in KICAD_CLI:
        found = shutil.which(candidate)
        if found:
            return found
    return None


def build(sch_path=DEFAULT_SCH, theme=None):
    """Writes build/sheet/overlay.json and backdrop.svg; returns the directory."""
    sch_path = Path(sch_path).expanduser()
    if not sch_path.is_file():
        raise SheetUnavailable("the schematic is not at %s" % sch_path)
    cli = kicad_cli()
    if cli is None:
        raise SheetUnavailable("kicad-cli was not found (KiCad 8 or later puts it in the application)")
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [cli, "sch", "export", "svg", "--exclude-drawing-sheet", "--pages", "1", "-o", tmp]
        if theme:
            cmd += ["--theme", theme]
        p = subprocess.run(cmd + [str(sch_path)], capture_output=True, text=True)
        plotted = Path(tmp) / (sch_path.stem + ".svg")
        if p.returncode != 0 or not plotted.is_file():
            raise SheetUnavailable("kicad-cli could not plot the sheet: %s" % (p.stderr.strip() or p.stdout.strip()))
        SHEET_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(plotted, SHEET_DIR / "backdrop.svg")
    data = overlay(sch_path)
    data["theme"] = theme           # None: KiCad's own light theme, which the page shows inverted on its dark ground
    with open(SHEET_DIR / "overlay.json", "w") as f:
        json.dump(data, f)
    return SHEET_DIR
