# SPDX-License-Identifier: MIT
"""Fidelity: does the harness route what a real board routed?

A capture directory is what test/hil/test_routing_dense.py writes with
JL_ROUTING_SNAP_DIR set: <case>.b.txt and <case>.xbar.txt for every dense
case. The harness replays the suite in the suite's order in ONE process,
because a board does not reboot between cases and the router's GND
alternator survives rebuilds. Its starting value depends on what the board
routed at boot, so both parities are tried.
"""
import re
import subprocess
import sys
from pathlib import Path

import cases
import runner
import variants

HIL_TOOLS = Path(__file__).resolve().parent.parent.parent / "test" / "hil" / "tools"
if str(HIL_TOOLS) not in sys.path:
    sys.path.insert(0, str(HIL_TOOLS))

import routing_check as rc                          # noqa: E402
from routing_snapshot_diff import rows_by_key      # noqa: E402

# the b report's header line -> its place in Case.stack (paths rails dacs gpio adcs)
_HEADER = {"pathDuplicates": 0, "railsDuplicates": 1, "dacDuplicates": 2, "gpioDuplicates": 3, "adcDuplicates": 4}


def stack_from_b(b_text):
    """The five global stacking settings a b report was printed under."""
    stack = [2, 3, 0, 0, 0]
    for key, i in _HEADER.items():
        m = re.search(key + r":\s*(-?\d+)", b_text)
        if m:
            stack[i] = int(m.group(1))
    return tuple(stack)


def replay(binary, capture_dir, alternator):
    """{case: sections} for the dense suite routed in order in one process.
    With a capture directory, each case runs under the stacking settings its
    own capture was printed under; with None, under the defaults."""
    order = cases.dense_cases()
    for c in order:
        cap = Path(capture_dir) / (c.name + ".b.txt") if capture_dir is not None else None
        if cap is not None and cap.exists():
            c.stack = stack_from_b(cap.read_text(errors="replace"))
    p = subprocess.run([str(binary), "--gnd-alternator", str(alternator)],
                       input="".join(c.to_protocol() for c in order),
                       capture_output=True, text=True, errors="replace", timeout=300)
    if p.returncode != 0:
        raise RuntimeError("the harness exited with %d: %s" % (p.returncode, p.stderr[-2000:]))
    sections = runner.parse_sections(p.stdout)
    return {c.name: sections[c.name] for c in order}


def _show(claim):
    return "free" if claim is None else str(claim)


def compare(capture_dir, replayed):
    """One line per difference between a board capture and a replay: path
    rows, chip status, closed crosspoints. An empty list is a pass."""
    capture_dir = Path(capture_dir)
    diffs = []
    for name, sections in replayed.items():
        b_path, x_path = capture_dir / (name + ".b.txt"), capture_dir / (name + ".xbar.txt")
        missing = [p.name for p in (b_path, x_path) if not p.exists()]
        if missing:
            diffs.append("%s: no capture (%s)" % (name, ", ".join(missing)))
            continue
        board_b = b_path.read_text(errors="replace")
        try:
            board_rows, lab_rows = rows_by_key(board_b), rows_by_key(sections["b"])
            for key in sorted(set(board_rows) | set(lab_rows), key=str):
                if board_rows.get(key) != lab_rows.get(key):
                    diffs.append("%s: path %s%s-%s: board %s, harness %s" % (
                        name, "dup " if key[0] else "", key[1], key[2], board_rows.get(key), lab_rows.get(key)))
            board_status, lab_status = rc.parse_chip_status(board_b), rc.parse_chip_status(sections["b"])
            for chip in rc.CHIPS:
                for axis, board_pins, lab_pins in zip("XY", board_status.get(chip, ((), ())),
                                                      lab_status.get(chip, ((), ()))):
                    for pin, (on_board, in_lab) in enumerate(zip(board_pins, lab_pins)):
                        if on_board != in_lab:
                            diffs.append("%s: chip status %s.%s%d: board %s, harness %s" % (
                                name, chip, axis, pin, _show(on_board), _show(in_lab)))
            board_xp = rc.crosspoints_from_xbar(rc.parse_xbar(x_path.read_text(errors="replace")))
            lab_xp = rc.crosspoints_from_xbar(rc.parse_xbar(sections["xbar"]))
            for chip, x, y in sorted(board_xp - lab_xp):
                diffs.append("%s: crosspoint only on the board: %s x%d y%d" % (name, chip, x, y))
            for chip, x, y in sorted(lab_xp - board_xp):
                diffs.append("%s: crosspoint only in the harness: %s x%d y%d" % (name, chip, x, y))
        except (ValueError, KeyError, IndexError) as e:
            diffs.append("%s: cannot read the capture: %s" % (name, e))
    return diffs


def check(capture_dir, variant_spec=None):
    """(passed, differences). The variant defaults to the commit named by a
    directory called board_<commit>. Passes when the replay matches the
    capture under either starting parity of the GND alternator; otherwise
    returns the shorter list of differences."""
    capture_dir = Path(capture_dir)
    if not capture_dir.is_dir():
        raise ValueError("no capture directory %s" % capture_dir)
    if variant_spec is None:
        m = re.fullmatch(r"board_(.+)", capture_dir.name)
        if not m:
            raise ValueError("name the capture directory board_<commit>, or pass --variant")
        variant_spec = m.group(1)
    binary = variants.build(variants.resolve(variant_spec))
    best = None
    for alternator in (0, 1):
        diffs = compare(capture_dir, replay(binary, capture_dir, alternator))
        if not diffs:
            return True, []
        if best is None or len(diffs) < len(best):
            best = diffs
    return False, best
