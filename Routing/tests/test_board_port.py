# SPDX-License-Identifier: MIT
"""A board's port 7 replies, read by the page's own code (web/board_port.js), and the
fake port that replays a trace. The code runs under node."""
import json
import subprocess
import unittest
from pathlib import Path

import lab
import server

HERE = Path(__file__).resolve().parent
CAPTURES = lab.FIDELITY_DIR / "board_0621e4f44e23"          # the dense suite as a V5 printed it, 2026-11-21
TRACE = HERE / "fixtures" / "port7_built.jsonl"
WATCH = HERE / "fixtures" / "port7_watch_built.jsonl"
NAMES = ["same_chip_pairs", "sf_to_sf", "k_rows_overflow_metric", "same_chip_pairs"]
SENDS = ["N", ":ver\n", ":gen\n", ":paths\n", ":crossbar\n", ":watch:routing:on\n", ":watch:routing:off\n"]
NETS = '{\r\n  "nets": [\r\n    {\r\n      "index": 6,\r\n      "name": "Net 6",\r\n      "nodes": ["1", "2"],\r\n' \
       '      "special": "",\r\n      "voltage": 1.203\r\n    }\r\n  ]\r\n}\r\n'
ABOUT = ("Built, not recorded: the exchanges a link makes with a board that goes through four routings at generations "
         "3, 5, 7 and 9. The :crossbar answers are the 2026-11-21 captures' .xbar.txt as they are; the :paths answers are "
         "what :paths prints, the captures' .b.txt from Bridge Array on. The N answer and every :gen answer are made up, "
         "because none was ever captured.")


def raw(name, ext):
    """A capture as bytes, so the board's own line ends stay."""
    return (CAPTURES / (name + ext)).read_bytes().decode("utf-8", errors="replace")


WATCH_ABOUT = (" The :watch:routing:on and :watch:routing:off answers and the changed{routing,G} lines are made up too: "
               "the board's watch was not built when this was written.")
REFUSED = ':watch:routing:on\r\n{"error":"unknown_verb","verb":"watch:routing:on"}\r\n'


def built_trace(names, watch=False):
    """The trace text of a link connecting to a board that goes through these captures, one routing each. Without
    watch the board refuses :watch and is polled; with it the board says when its routing changed."""
    gen = lambda n, idle: ":gen\r\ngen{%d,%d}\r\n" % (n, idle)
    state = lambda on, n: ':watch:routing:%s\r\n{"watch":"routing","state":"%s","gen":%d}\r\n' % (on, on, n)
    replies = [("N", NETS), (":ver\n", ":ver\r\nJumperless firmware version: 0.0.0.0\r\n"), (":gen\n", gen(3, 1)),
               (":watch:routing:on\n", state("on", 3) if watch else REFUSED)]
    for k, name in enumerate(names):
        g = 3 + 2 * k
        b = raw(name, ".b.txt")
        report = [(":paths\n", ":paths\r\n\n\r" + b[b.index("Bridge Array"):]), (":crossbar\n", raw(name, ".xbar.txt"))]
        if watch:
            replies += ([(":gen\n", gen(g, 1))] if not k else [(None, "changed{routing,%d}\r\n" % g)]) + report + [(":gen\n", gen(g, 1))]
        else:
            replies += ([(":gen\n", gen(g - 1, 0))] if k else []) + [(":gen\n", gen(g, 1))] + report + [(":gen\n", gen(g, 1))] * 4
    if watch:
        replies.append((":watch:routing:off\n", state("off", 3 + 2 * (len(names) - 1))))
    lines = [{"h": 1, "what": "routing lab port 7 trace", "source": "built", "fw": None, "about": ABOUT + (WATCH_ABOUT if watch else "")}]
    for i, (sent, got) in enumerate(replies):
        if len(lines) > 1 and (lines[-1]["sent"], lines[-1]["got"]) == (sent, got):
            lines[-1]["times"] = lines[-1].get("times", 1) + 1
        else:
            lines.append({"t": round(i * 0.1, 1), "sent": sent, "got": got})
    return "".join(json.dumps(line) + "\n" for line in lines)


class Port(unittest.TestCase):
    def test_the_built_trace_is_what_the_captures_give(self):
        self.assertEqual(TRACE.read_text(), built_trace(NAMES))
        self.assertEqual(WATCH.read_text(), built_trace(NAMES, watch=True))
        for trace, sends in ((TRACE, set(SENDS[:6])), (WATCH, set(SENDS) | {None})):
            lines = [json.loads(line) for line in trace.read_text().splitlines()]
            self.assertEqual((lines[0]["h"], lines[0]["source"]), (1, "built"))
            self.assertEqual({e["sent"] for e in lines[1:]}, sends, trace.name)

    def test_a_connect_that_fails_leaves_the_page_not_linked(self):
        p = subprocess.run(["node", str(HERE / "link_page_test.js"), str(server.WEB_DIR)], capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_the_port_code_under_node(self):
        p = subprocess.run(["node", str(HERE / "board_port_test.js"), str(CAPTURES), str(TRACE), str(WATCH)], capture_output=True, text=True,
                           timeout=120)                   # a link that waits for ever is a failed test, not a hung suite
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(subprocess.run(["node", "--check", str(server.WEB_DIR / "board_port.js")]).returncode, 0)
