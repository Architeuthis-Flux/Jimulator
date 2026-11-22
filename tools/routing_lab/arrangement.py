# SPDX-License-Identifier: MIT
"""The crossbar arrangement as a file: V5 plus what differs.

An arrangement is the fabric the copper searches and the exact solver work
on: which wire is on each chip pin, and which node is which wire. V5's is
test/hil/fabric_v5.py. Another is a small JSON file under arrangements/ that
says what it changes:

    "about"   one line of text
    "base"    "v5" (the only base there is)
    "feed"    true when the probe feed is routed through the fabric (default)
    "remove"  wire names: every pin on such a wire is taken away
    "pins"    {"A.X7": "TOP_RAIL", "K.X2": null}: a pin put on a wire (joined
              to every other pin of that name), or taken away
    "chips"   {"M": {"role": "sf", "x": [16 names or null], "y": [8 ...]}}
    "nodes"   {"150": {"wire": "PORT_0", "name": "PORT_0"}, "139": null}:
              a node added or moved, or removed

A pin taken away is no copper at all. A base node whose last pin is taken
away drops out of the arrangement; a netlist that uses it cannot be placed.
With "feed" true, every end the feed can have (FEED_NODE and FEED_ENDS: BUF_IN,
DAC0, GPIO_1 to GPIO_8) must keep a pin.

The firmware's router has V5 written into it, so it can route an arrangement
only when that is V5 with pins taken away (the harness blocks them). `blocks`
says so; the solver takes any arrangement.
"""
import copy
import json
import re
from pathlib import Path

import copper                                       # puts test/hil on the path

import fabric_v5                                    # noqa: E402

DIR = Path(__file__).resolve().parent / "arrangements"
KEYS = ("about", "base", "feed", "remove", "pins", "chips", "nodes")
PINS = {"X": 16, "Y": 8}
FEED_NODE = copper.FEED_NODE
# The probe feed's other end: DAC0 while DAC0 is in the probe's window, else the highest free GPIO from 8 down to 1
# (src/routing/InfraPaths.cpp; the dense cases feed from GPIO 6). With the feed on the fabric, every one needs a pin.
FEED_ENDS = (106,) + tuple(range(131, 139))         # DAC0, GPIO_1 to GPIO_8
PIN = re.compile(r"([A-Z])\.([XY])(0|[1-9][0-9]?)")  # A.X7, written one way only (no A.X07, no other digits)
NODE = re.compile(r"0|[1-9][0-9]{0,5}")


class Bad(ValueError):
    """An arrangement that cannot be used. `.problems` lists every reason."""

    def __init__(self, name, problems):
        super().__init__("%s: %s" % (name, "; ".join(problems)))
        self.problems = list(problems)


class RouterCannot(ValueError):
    """The firmware's router was asked for an arrangement that is not V5 with pins taken away."""


def _pins(chips, x_net, y_net):
    """{wire: [(chip, axis, pin)]} for every pin that has a wire."""
    out = {}
    for chip in chips:
        for axis, table in (("X", x_net), ("Y", y_net)):
            for pin, wire in enumerate(table[chip]):
                if wire is not None:
                    out.setdefault(wire, []).append((chip, axis, pin))
    return out


class Arrangement:
    """name, about, feed; CHIPS, X_NET, Y_NET (None: the pin is taken away),
    NODE_NET, NODE_NAME, ROLE; and against V5: changed (pins not on V5's
    wire), taken (those with no wire), dropped (base nodes left on no pin).
    data is the JSON it was made from, for making another from it."""

    def __init__(self, name, about, feed, chips, x_net, y_net, node_net, node_name, role, dropped=(), data=None):
        self.name, self.about, self.feed = name, about, feed
        self.data = copy.deepcopy(data) if data is not None else {"base": "v5", "feed": feed}      # what a file of it says
        self.CHIPS, self.X_NET, self.Y_NET = chips, x_net, y_net
        self.NODE_NET, self.NODE_NAME, self.ROLE = node_net, node_name, role
        self.changed = sorted(
            (chip, axis, pin) for chip in chips for axis, table, base in (("X", x_net, fabric_v5.X_NET), ("Y", y_net, fabric_v5.Y_NET))
            for pin, wire in enumerate(table[chip]) if chip not in base or wire != base[chip][pin])
        self.taken = [(chip, axis, pin) for chip, axis, pin in self.changed if self.wire(chip, axis, pin) is None]
        self.dropped = sorted(dropped)

    def wire(self, chip, axis, pin):
        return (self.X_NET if axis == "X" else self.Y_NET)[chip][pin]

    def pins(self):
        return _pins(self.CHIPS, self.X_NET, self.Y_NET)


def _base_tables():
    role = {chip: "bb" if chip in "ABCDEFGH" else "sf" for chip in fabric_v5.CHIPS}
    return (fabric_v5.CHIPS, copy.deepcopy(fabric_v5.X_NET), copy.deepcopy(fabric_v5.Y_NET),
            dict(fabric_v5.NODE_NET), dict(fabric_v5.NODE_NAME), role)


V5 = Arrangement("v5", "the V5 board as its schematic wires it", True, *_base_tables())
_OFF = Arrangement("v5, feed off", "V5's copper with the probe feed off the fabric", False, *_base_tables())


def base(feed):
    """V5's copper with the probe feed on the fabric (that is V5) or off it."""
    return V5 if feed else _OFF


def feed_problems(node_net):
    """What keeps the probe feed off copper with these nodes: its ends that have no pin."""
    return ['"feed" is true, but %s (%d), %s, has no pin: say "feed": false'
            % (fabric_v5.NODE_NAME.get(n, n), n, "the feed's own end" if n == FEED_NODE
               else "where the firmware feeds the probe from" + ("" if n == 106 else " when DAC0 is out of the probe's window"))
            for n in (FEED_NODE,) + FEED_ENDS if n not in node_net]


def with_feed(a, feed):
    """`a`'s copper, by `a`'s name, with the probe feed on the fabric or off
    it: for asking of one arrangement the netlists another was given. Raises
    Bad when the feed is put onto copper that has no pin for one of its ends."""
    if a.feed == feed:
        return a
    if feed and feed_problems(a.NODE_NET):
        raise Bad(a.name, feed_problems(a.NODE_NET))
    other = copy.copy(a)
    other.feed, other.data = feed, dict(a.data, feed=feed)
    return other


def _pin_name(chip, axis, pin):
    return "%s.%s%d" % (chip, axis, pin)


def _build(name, data):
    """(arrangement or None, problems). One pass, so check() and parse() cannot disagree."""
    if not isinstance(data, dict):
        return None, ["an arrangement is one JSON object, with at least \"base\": \"v5\""]
    problems = ['unknown key "%s" (the keys are %s)' % (k, ", ".join(KEYS)) for k in data if k not in KEYS]
    if data.get("base") != "v5":
        problems.append('"base" must be "v5", not %s' % _shown(data.get("base")))
    if not isinstance(data.get("about", ""), str):
        problems.append('"about" is one line of text, not %s' % _shown(data["about"]))
    feed = data.get("feed", True)
    if not isinstance(feed, bool):
        problems.append('"feed" is true or false, not %s' % _shown(feed))
        feed = True
    shapes = {"remove": list, "pins": dict, "chips": dict, "nodes": dict}
    part = {}
    for key, shape in shapes.items():
        part[key] = data.get(key) if isinstance(data.get(key), shape) else shape()
        if key in data and not isinstance(data[key], shape):
            problems.append('"%s" must be %s' % (key, "a list of wire names" if shape is list else "an object"))

    chips, x_net, y_net, node_net, node_name, role = _base_tables()
    name_or_null = lambda v: v is None or (isinstance(v, str) and v != "")

    for letter, spec in part["chips"].items():
        if not re.fullmatch("[A-Z]", letter):
            problems.append('chip "%s": a chip is one capital letter' % letter)
            continue
        if letter in chips:
            problems.append("chip %s is already a chip of the base; change its pins with \"pins\"" % letter)
            continue
        spec = spec if isinstance(spec, dict) else {}
        good = True
        problems += ['chip %s: unknown key "%s" (a chip has role, x and y)' % (letter, k) for k in spec if k not in ("role", "x", "y")]
        if spec.get("role") not in ("bb", "sf"):
            problems.append('chip %s: its role is "bb" or "sf", not %s' % (letter, _shown(spec.get("role"))))
            good = False
        for axis, key in (("X", "x"), ("Y", "y")):
            listed = spec.get(key)
            if not isinstance(listed, list) or len(listed) != PINS[axis] or not all(name_or_null(w) for w in listed):
                problems.append('chip %s: "%s" must list %d pins, each a wire name or null' % (letter, key, PINS[axis]))
                good = False
        if good:
            chips += letter
            x_net[letter], y_net[letter], role[letter] = list(spec["x"]), list(spec["y"]), spec["role"]

    base_wires = {w for table in (fabric_v5.X_NET, fabric_v5.Y_NET) for row in table.values() for w in row}
    for wire in part["remove"]:
        if not isinstance(wire, str):
            problems.append('"remove": %s is not a wire name' % _shown(wire))
            continue
        if wire not in base_wires:
            problems.append('"remove": %s is not a wire of the base' % _shown(wire))
            continue
        for table in (x_net, y_net):
            for row in table.values():
                row[:] = [None if w == wire else w for w in row]

    named_x = set()                                 # new names put on X pins under "pins": where a misspelt name lands
    for spec, wire in part["pins"].items():
        m = PIN.fullmatch(spec)
        if not m or m.group(1) not in chips or int(m.group(3)) >= PINS[m.group(2)]:
            problems.append('pin "%s": a pin is CHIP.Xn (n 0 to 15) or CHIP.Yn (n 0 to 7) on a chip of the arrangement' % spec[:40])
        elif not name_or_null(wire):
            problems.append("pin %s: its wire is a name or null, not %s" % (spec, _shown(wire)))
        else:
            (x_net if m.group(2) == "X" else y_net)[m.group(1)][int(m.group(3))] = wire
            if m.group(2) == "X":
                named_x.add(wire)

    placed = {}
    for key, spec in part["nodes"].items():
        if not NODE.fullmatch(str(key)):
            problems.append('node "%s": a node is a whole number, written plainly (no leading zero)' % str(key)[:40])
            continue
        node = int(key)
        if spec is None:
            node_net.pop(node, None)
            node_name.pop(node, None)
        elif not isinstance(spec, dict) or not isinstance(spec.get("wire"), str) or not spec["wire"]:
            problems.append('node %d: give {"wire": name} (and a "name" to show), or null to remove it' % node)
        else:
            problems += ['node %d: unknown key "%s" (a node has wire and name)' % (node, k) for k in spec if k not in ("wire", "name")]
            if not isinstance(spec.get("name", ""), str):
                problems.append("node %d: its name is text, not %s" % (node, _shown(spec["name"])))
            placed[node] = node_net[node] = spec["wire"]
            node_name[node] = str(spec.get("name") or node_name.get(node, node))

    live = _pins(chips, x_net, y_net)
    for node, wire in sorted(placed.items()):
        if wire not in live:
            problems.append("node %d is placed on %s, which is on no pin" % (node, wire))
    owned = set(fabric_v5.NODE_NET.values())
    for wire, pins in sorted(V5.pins().items()):
        if len(pins) >= 2 and wire not in owned and len(live.get(wire, ())) == 1:
            problems.append('wire %s is left on one pin (%s): take the wire away with "remove", or give the pin another wire'
                            % (wire, _pin_name(*live[wire][0])))
    # A name V5 has not, put on one X pin under "pins", with no node on it, is most likely a slip of a name (TOP_RIAL).
    # A one-pin wire on a Y pin is a bounce row, a shape V5 has eight of; a new chip's own lists name its wires on purpose.
    for wire, pins in sorted(live.items()):
        if wire in named_x and wire not in base_wires and len(pins) == 1 and wire not in node_net.values():
            problems.append("wire %s is on one pin only (%s) and is no node's: a misspelt name? Join it to another pin, "
                            "put a node on it, or take the pin away with null" % (wire, _pin_name(*pins[0])))
    dropped = [n for n, wire in node_net.items() if n not in placed and wire not in live]
    for node in dropped:                            # a base node whose last pin was taken away drops out
        del node_net[node]
        node_name.pop(node, None)
    if feed:
        problems += feed_problems(node_net)
    about = data.get("about") if isinstance(data.get("about"), str) else ""
    return Arrangement(name, about, feed, chips, x_net, y_net, node_net, node_name, role, dropped, data), problems


def _shown(value):
    """A value from a file, shown in a problem, kept short."""
    try:
        text = json.dumps(value)
    except (ValueError, TypeError, RecursionError):
        text = repr(type(value))
    return text if len(text) <= 60 else text[:57] + "..."


def check(data):
    """Every problem with an arrangement's data, each naming its pin, wire, chip, node or key. Empty when it is good."""
    return _build("check", data)[1]


def parse(name, data):
    """An Arrangement from a file's data. Raises Bad, listing every problem."""
    a, problems = _build(name, data)
    if problems:
        raise Bad(name, problems)
    return a


def names():
    """"v5", then every file under DIR, by name."""
    return ["v5"] + sorted(p.stem for p in DIR.glob("*.json"))


def load(name):
    """The arrangement called `name`: "v5", a file's stem under DIR, or a path ending .json. Raises Bad."""
    name = str(name)
    if name == "v5":
        return V5
    if name == _OFF.name:
        return _OFF
    path = Path(name).expanduser() if name.endswith(".json") else DIR / (name + ".json")
    if not path.is_file():
        raise Bad(name, ["there is no arrangement %s (there are: %s)" % (name, ", ".join(names()))])
    twice = []

    def pairs(items):                               # JSON lets a key be given twice and keeps the last: say so instead
        seen = set()
        for k, _ in items:
            if k in seen:
                twice.append('the key "%s" is given twice in one object; JSON keeps only the last' % k[:40])
            seen.add(k)
        return dict(items)

    try:
        data = json.loads(path.read_text(), object_pairs_hook=pairs)
    except (OSError, ValueError, RecursionError) as e:
        raise Bad(path.stem, ["%s cannot be read as JSON: %s" % (path.name, str(e)[:200])]) from None
    if twice:
        raise Bad(path.stem, twice)
    try:
        return parse(path.stem, data)
    except Bad:
        raise
    except Exception as e:                          # a mistake no rule foresaw is still the file's, and must stop nothing else
        raise Bad(path.stem, ["%s cannot be read as an arrangement (%s: %s)" % (path.name, type(e).__name__, e)]) from None


def why_not_router(a):
    """None when the firmware's router can run `a` (it is V5 with pins taken
    away); else one sentence naming the first thing that is not V5's."""
    extra = [c for c in a.CHIPS if c not in V5.CHIPS]
    if extra:
        return "chip %s is not a chip of V5" % extra[0]
    for chip, axis, pin in a.changed:
        wire = a.wire(chip, axis, pin)
        if wire is not None:
            return "%s is on %s, not on %s as V5 has it" % (_pin_name(chip, axis, pin), wire, V5.wire(chip, axis, pin))
        was = V5.wire(chip, axis, pin)
        if was in a.NODE_NET.values():              # the node keeps another pin, so the firmware still routes it to this one
            return "%s is taken away, but %s is still a node (on its other pin), and the firmware would go on closing this one" % (
                _pin_name(chip, axis, pin), was)
    for node in sorted(set(V5.NODE_NET) | set(a.NODE_NET)):
        if node in a.dropped:
            continue
        if a.NODE_NET.get(node) != V5.NODE_NET.get(node):
            return "node %s is not where V5 has it" % (a.NODE_NAME.get(node) or V5.NODE_NAME.get(node, node))
    return None


def blocks(a):
    """The harness's block list, [("X" | "Y", chip index, pin)], when the
    firmware's router can run `a`; None when it cannot."""
    if why_not_router(a) is not None:
        return None
    return [(axis, a.CHIPS.index(chip), pin) for chip, axis, pin in a.taken]
