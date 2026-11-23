# SPDX-License-Identifier: MIT
"""A board's own output as a result.

What a Jumperless V5 prints for `b` on its terminal port (bridge array, path
table, chip status) is judged and painted exactly as a harness run is, so the
page can show what a board really routed. The text may be a raw serial log
(colour codes and all) or a copy out of a terminal window, where every tab
has become spaces; the checker's parsers want the tabs, so they are put back
here and JumperlOS/test/hil/routing_check.py is left as the bench suite uses it.

The crossbar dump (`:crossbar` on port 7, "xbar{12x8:...}") is used when it
is in the text. Without it, what was sent to the chips is taken to be what
the path table lists, and the result says so.
"""
import re

import cases
import copper
import runner

rc = runner.rc

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b[78]")
XBAR = re.compile(r"xbar\{12x8:[0-9A-Fa-f]{384}\}")
PATH_HEADER = "path\tnet\tnode1\tchip0\tx0\ty0\tnode2\tchip1\tx1\ty1\taltPath\tsameChp\tdup\tpathType\tchip2\tx2\ty2"
# What a wrapped row leaves on the next line: the rest of its path type and hops, nothing else. (The path table
# holds other lines too: "duplicates", and the firmware's own "rail dup bounce skips: ..." note.)
_PIECE = r"(?:BB|NANO|SF|to|VIRTUAL|Not|Assigned|[@A-L]|-?\d+)"
LEFTOVER = re.compile(r"%s(?:\s+%s)*" % (_PIECE, _PIECE))
NOT_READ = "this is not a V5 b report the lab can read: "
NO_DUMP = ("no crossbar dump in the upload (':crossbar' on port 7): what was sent to the chips is taken to be what "
           "the path table lists, so \"sent equals planned\" was not checked")


def _path_row(row):
    """A path row with its tabs back. The first thirteen columns are single
    words; the path type is one to three ("VIRTUAL", "Not Assigned", "BB to
    BB"); the third and fourth hops, when there are any, start at a chip
    letter ("@" for none) followed by a number."""
    if "\t" in row:
        return row                                  # as the board sent it
    words = row.split()
    if len(words) < 14:
        return row
    more = next((i for i in range(14, len(words) - 1)
                 if re.fullmatch(r"[@A-L]", words[i]) and re.fullmatch(r"-?\d+", words[i + 1])), len(words))
    return "\t".join(words[:13] + [" ".join(words[13:more])] + words[more:])


def _whole(row):
    """A path row with every column it should have: fourteen, then nothing or
    the five or six of the third and fourth hops. A row the terminal wrapped
    or cut has fewer, and must not be read as a shorter path."""
    cols = [c.strip() for c in row.split("\t")]
    return len(cols) >= 14 and cols[0].isdigit() and len([c for c in cols[14:] if c]) in (0, 5, 6)


def normalize(text):
    """The last whole `b` report in `text`, as the checker's parsers read one:
    from its "Bridge Array" to its twelfth chip-status row, colour codes gone,
    and the tabs a terminal copy turns into spaces put back. ValueError when
    there is no report, or its path table has a row that is not whole or the
    leftover of one (a table wrapped at the window's edge would otherwise
    read as shorter paths, and the board be shown with faults it has not)."""
    text = ANSI.sub("", text).replace("\r\n", "\n").replace("\r", "\n")
    start = text.rfind("Bridge Array")              # the debug menu prints these two words as well,
    while start >= 0 and "Chip Status" not in text[start:]:     # and a second report may be cut short
        start = text.rfind("Bridge Array", 0, start)
    if start < 0:
        raise ValueError(NOT_READ + "it needs the \"Bridge Array\", \"Paths\" and \"Chip Status\" blocks that `b` prints")
    out, part, chips = [], "bridges", 0
    for line in text[start:].split("\n"):
        s = line.strip()
        if part == "bridges" and re.match(r"path\s+net\s+node1\b", s):
            part, line = "paths", PATH_HEADER
        elif part != "status" and s.startswith("Chip Status"):
            part, line = "status", "Chip Status"
        elif part == "paths" and (re.match(r"\d+\s", s) or LEFTOVER.fullmatch(s)):
            line = _path_row(s)
            if not _whole(line):
                raise ValueError(NOT_READ + "its path table has a line that is not a whole row (%r); was the text "
                                            "wrapped at the window's edge or cut short?" % s[:60])
        elif part == "status" and re.match(r"[A-L]\s", s):
            line = s[0] + "\t" + "    ".join(s[1:].split())
            chips += 1
        out.append(line)
        if chips == 12:
            break                                   # whatever a log holds after the report is not part of it
    return "\n".join(out) + "\n"


def xbar_of(rows):
    """The crossbar dump a board would give if it sent exactly what these path rows list."""
    masks = {chip: [0] * 8 for chip in rc.CHIPS}
    for r in rows:
        if r["net"] >= 0:
            for chip, x, y in rc.routed_hops(r):
                masks[chip][y] |= 1 << x
    return "xbar{12x8:%s}" % "".join("%04X" % m for chip in rc.CHIPS for m in masks[chip])


def _name(given):
    """A case name from a file name: its last part, without ".b.txt" or its extension, in the letters a name may have."""
    stem = re.split(r"[/\\]", given or "")[-1].lstrip(".")
    stem = re.sub(r"\.(b|xbar)\.txt$|\.[^.]*$", "", stem)
    return re.sub(r"[^A-Za-z0-9_+-]", "_", stem)[:60] or "board"


def result(name, text, about="", live=False):
    """A judged result (class "board") from what a board printed; `about` is
    the case's notes. ValueError, with what is wrong, when the text is not a
    `b` report of this fabric or its path table did not come through whole.
    A whole report read from a live board that lists no bridge is a board with
    nothing connected (status "empty"); a pasted one is refused."""
    text = ANSI.sub("", text or "")
    b = normalize(text)
    try:
        bridges, rows, status = rc.parse_bridge_array(b), rc.parse_paths(b), rc.parse_chip_status(b)
    except (ValueError, KeyError, IndexError) as e:
        raise ValueError(NOT_READ + str(e.args[0] if e.args else e)) from None
    if not bridges and not live:
        raise ValueError(NOT_READ + "its Bridge Array lists no bridge")
    array = b.split("Bridge Array", 1)[1].split("Paths", 1)[0]
    if array.count("[") != len(re.findall(r"\[[^,\]]+,[^,\]]+,Net (?:\d+|\?)\]", array)):
        raise ValueError(NOT_READ + "an entry of its Bridge Array did not come through whole; was the text wrapped "
                                    "at the window's edge?")
    if len(status) != 12:
        raise ValueError(NOT_READ + "its Chip Status has %d of the 12 chips" % len(status))
    declared = re.search(r"numberOfPaths:\s*(\d+)", b)
    if not rows and (declared is None or int(declared.group(1)) > 0):
        raise ValueError(NOT_READ + "its path table did not come through (no row could be read); was the text "
                                    "wrapped at the window's edge or cut short?")
    notes = []
    primaries = sum(1 for r in rows if not r["dup"])
    if primaries < len(bridges):
        notes.append("the path table lists %d primary paths for %d bridges: part of the report may be missing"
                     % (primaries, len(bridges)))
    dumps = XBAR.findall(text)
    if not dumps:
        notes.append(NO_DUMP)
    case = cases.Case(_name(name), "board", [(n1, n2, -1) for n1, n2, _ in bridges])
    judged = runner.judge(case, {"b": b, "xbar": dumps[-1] if dumps else xbar_of(rows)})
    if judged["status"] == "crash":
        raise ValueError(NOT_READ + (judged["problems"] or ["the checker could not read it"])[0])
    if not bridges:
        notes.append("nothing is connected on the board")
    judged["notes"] = notes + judged["notes"]
    judged["about"] = about
    return judged


def changed(before, after):
    """What two readings of one case differ by: the crosspoints closed and
    opened (told by place, so a net that only got another number is no
    change) and the bridges whose state differs (told by their two nodes).
    None when there is no earlier reading."""
    if before is None:
        return None
    old, new = copper.paint(before), copper.paint(after)
    places = lambda p: {(c["chip"], c["x"], c["y"]): c["net"] for c in p["crosspoints"]}
    states = lambda p: {frozenset((b["n1"], b["n2"])): b for b in p["bridges"]}
    (was, now), (was_b, now_b) = (places(old), places(new)), (states(old), states(new))
    state = lambda d, k: d[k]["state"] if k in d else None
    return {"closed": sorted([*k, now[k]] for k in now.keys() - was.keys()),
            "opened": sorted([*k, was[k]] for k in was.keys() - now.keys()),
            "bridges": [{"n1": b["n1"], "n2": b["n2"], "was": state(was_b, k), "now": state(now_b, k)}
                        for k, b in sorted(((k, (now_b.get(k) or was_b[k])) for k in was_b.keys() | now_b.keys()),
                                           key=lambda kb: (kb[1]["n1"], kb[1]["n2"]))
                        if state(was_b, k) != state(now_b, k)]}
