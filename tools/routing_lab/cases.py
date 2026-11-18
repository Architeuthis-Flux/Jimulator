# SPDX-License-Identifier: MIT
"""Cases: one netlist plus the settings it is routed under.

A case is what the harness reads on stdin (Case.to_protocol). Cases come from
the HIL dense suite (dense_cases), from firmware state documents
(import_state), from JSON files under cases/, and from generators.py.
"""
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

LAB = Path(__file__).resolve().parent
HIL = LAB.parent.parent / "test" / "hil"
if str(HIL) not in sys.path:
    sys.path.insert(0, str(HIL))

import fabric_v5          # noqa: E402  (test/hil: the schematic-derived fabric)
import routing_cases      # noqa: E402  (test/hil: the dense cases)


@dataclass
class Case:
    name: str
    cls: str
    bridges: list                                   # [(node1, node2, dup)]; dup -1 = default
    stack: tuple = (2, 3, 0, 0, 0)                  # paths rails dacs gpio adcs (config.h defaults)
    power: tuple = (0.0, 0.0, 3.33, 0.0)            # top bottom dac0 dac1 (PowerState defaults)
    probe: tuple = (1, 0)                           # auto_connect, power_source
    must_route: bool = False
    taps_required: bool = False
    notes: str = ""

    def __post_init__(self):
        if not self.name or len(self.name.split()) != 1:
            raise ValueError("a case name is one word: %r" % (self.name,))
        self.bridges = [tuple(int(v) for v in b) for b in self.bridges]
        self.stack = tuple(int(v) for v in self.stack)
        self.power = tuple(float(v) for v in self.power)
        self.probe = tuple(int(v) for v in self.probe)

    def to_protocol(self, block=()):
        """The harness's stdin text. block: [("X" | "Y", chip, pin), ...]."""
        lines = ["case " + self.name,
                 "stack " + " ".join(str(v) for v in self.stack),
                 "power " + " ".join("%g" % v for v in self.power),
                 "probe %d %d" % self.probe]
        lines += ["block %s %d %d" % tuple(b) for b in block]
        lines += ["bridge %d %d %d" % b for b in self.bridges]
        return "\n".join(lines + ["end"]) + "\n"

    def digest(self):
        return hashlib.sha256(self.to_protocol().encode()).hexdigest()


def load_json(path):
    with open(path) as f:
        return Case(**json.load(f))


def save_json(case, path):
    with open(path, "w") as f:
        json.dump(asdict(case), f, indent=1)
        f.write("\n")


def dense_cases():
    """The HIL dense suite's cases. Each bridge carries the explicit count the
    suite pastes for it; the power section is the suite's (everything at 0 V)."""
    out = []
    for name, bridges, all_routed, stacking, electrical in routing_cases.CASES:
        out.append(Case(name, "dense",
                        [(a, b, routing_cases.bridge_dup(a, b, stacking)) for a, b in bridges],
                        power=(0, 0, 0, 0), must_route=bool(all_routed),
                        taps_required=electrical == ("taps",)))
    return out


# Node names, compared without case: the fabric's names, the short names the
# firmware prints, and the long forms a state document uses.
_NAMES = {}
for _id, _name in fabric_v5.NODE_NAME.items():
    _NAMES[_name.upper()] = _id
for _name, _id in fabric_v5.SHORT_TO_NODE.items():
    _NAMES[_name.upper()] = _id
for _i in range(8):
    _NAMES["RP_GPIO_%d" % (_i + 1)] = 131 + _i
    _NAMES["NANO_A%d" % _i] = 86 + _i
for _i in range(14):
    _NAMES["NANO_D%d" % _i] = 70 + _i
_NAMES["RP_UART_TX"] = 116
_NAMES["RP_UART_RX"] = 117


def node_id(token):
    """A node id from an integer or a firmware node name."""
    if isinstance(token, int):
        return token
    text = str(token).strip()
    if text.lstrip("-").isdigit():
        return int(text)
    if text.upper() in _NAMES:
        return _NAMES[text.upper()]
    raise ValueError("unknown node name %r" % text)


_BRIDGE_LINE = re.compile(r"^\s*-\s*\{\s*n1:\s*([^,}]+?)\s*,\s*n2:\s*([^,}]+?)\s*(?:,\s*dup:\s*(-?\d+)\s*)?(?:,[^}]*)?\}")


def import_state(path, name, cls="real"):
    """A Case from a firmware state document: its bridges, power and
    [routing] stacking.

    Read line by line, as the firmware's own loader does, and not as strict
    YAML: a document captured from a terminal carries stray output after it.
    """
    section, raw, power, routing, sections = None, [], {}, {}, set()
    with open(path, errors="replace") as f:
        for line in f:
            top = re.match(r"^([A-Za-z_]\w*):", line)
            if top:
                section = top.group(1)
                sections.add(section)
            elif section == "bridges":
                m = _BRIDGE_LINE.match(line)
                if m:
                    raw.append(m.groups())
            elif section == "power":
                m = re.match(r"^\s+(\w+):\s*(-?\d+(?:\.\d+)?)", line)
                if m:
                    power[m.group(1)] = float(m.group(2))
            elif section == "config" and "routing:" in line:
                routing.update((k, int(v)) for k, v in re.findall(r"(\w+):\s*(-?\d+)", line))
    if "bridges" not in sections:
        raise ValueError("no bridges section in %s" % path)
    stack_paths = routing.get("stackPaths", 2)
    bridges = []
    for n1, n2, dup in raw:
        try:
            a, b = node_id(n1), node_id(n2)
        except ValueError as e:
            raise ValueError("%s in %s" % (e, path)) from None
        dup = -1 if dup is None else int(dup)
        # The slot loader's rule (States.cpp, "the exact value that was
        # stamped"): a count equal to the document's stackPaths was never a
        # user request, so it goes back to default.
        if dup == stack_paths:
            dup = -1
        bridges.append((a, b, dup))
    return Case(name, cls, bridges,
                stack=(stack_paths, routing.get("stackRails", 3), routing.get("stackDacs", 0), 0, 0),
                power=(power.get("topRail", 0.0), power.get("bottomRail", 0.0),
                       power.get("dac0", 3.33), power.get("dac1", 0.0)),
                notes="imported from " + Path(path).name)
