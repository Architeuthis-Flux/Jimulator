# tests/test_harness.py
import os, re, subprocess, sys, unittest
LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(LAB))
sys.path.insert(0, os.path.join(REPO, "test", "hil"))
import routing_check as rc

BIN = os.path.join(LAB, "build", "test", "lab_harness")

def setUpModule():
    os.makedirs(os.path.dirname(BIN), exist_ok=True)
    subprocess.run([os.path.join(LAB, "harness", "build.sh"), os.path.join(REPO, "src"), BIN], check=True)

def run(text, *args):
    return subprocess.run([BIN, *args], input=text, capture_output=True, text=True, timeout=30)

def section(out, name):
    m = re.search(r"^--- %s\n(.*?)(?=^--- |^=== end)" % name, out, re.S | re.M)
    return m.group(1) if m else None

CASE = "case t\nstack 2 3 0 0 0\npower 0 0 3.33 0\nprobe 1 0\n%send\n"

class Harness(unittest.TestCase):
    def test_one_bridge_routes_and_judges_clean(self):
        p = run(CASE % "bridge 1 8 -1\n")
        self.assertEqual(p.returncode, 0, p.stderr)
        b, x = section(p.stdout, "b"), section(p.stdout, "xbar")
        self.assertIn("Bridge Array", b); self.assertIn("path\tnet\tnode1", b); self.assertIn("Chip Status", b)
        self.assertRegex(x, r"xbar\{12x8:[0-9a-f]{384}\}")
        v, m = rc.full_check(b, x, expect_all_routed=True)
        self.assertTrue(v.ok(), v.problems)
        self.assertEqual((m["primaries"], m["routed_primaries"]), (2, 2))  # 1-8 plus the probe feed

    def test_forbidden_and_degenerate_bridges_are_rejected_not_routed(self):
        p = run(CASE % "bridge 100 101 -1\nbridge 5 5 -1\nbridge 61 2 -1\nbridge 1 8 -1\n")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(section(p.stdout, "rejected").split("\n")[:3], ["100 101", "5 5", "61 2"])
        self.assertEqual([(a, b_) for a, b_, _ in rc.parse_bridge_array(section(p.stdout, "b")) if 139 not in (a, b_)], [(1, 8)])

    def test_malformed_input_exits_2(self):
        self.assertEqual(run("case t\nbridge 1\nend\n").returncode, 2)

    def test_netlist_is_built_by_firmware_code(self):
        src = ""
        for f in ("lab_harness.cpp", "firmware_stubs.cpp"):
            with open(os.path.join(LAB, "harness", f)) as fh:
                src += fh.read()
        for name in ("initNets", "clearAllNTCC", "infraEvaluate", "loadBridgesFromState",
                     "getNodesToConnect", "bridgesToPaths", "connectionAllowed", "planFastPath"):
            self.assertNotRegex(src, r"\b(void|int|bool)\s+%s\s*\([^;]*\)\s*\{" % name, name)

    def test_two_cases_in_one_process(self):
        p = run(CASE % "bridge 1 8 -1\n" + CASE.replace("case t", "case u") % "bridge 2 9 -1\n")
        self.assertEqual(re.findall(r"^=== case (\w+)", p.stdout, re.M), ["t", "u"])

    def test_repeat_reports_same(self):
        p = run(CASE % "bridge 1 8 -1\nbridge 100 3 -1\nbridge 100 31 -1\n", "--repeat", "2")
        self.assertEqual(section(p.stdout, "repeat").strip(), "same")

    def test_blocked_lane_is_never_used(self):
        # A.X2 and A.X3 are the two A-B lanes (fabric_v5.X_NET['A'][2:4]); B's ends are B.X0, B.X1
        blocks = "block X 0 2\nblock X 1 0\nblock X 0 3\nblock X 1 1\n"
        p = run(CASE % (blocks + "bridge 1 8 -1\n"))
        rows = [r for r in rc.parse_paths(section(p.stdout, "b")) if (r["node1"], r["node2"]) == (1, 8)]
        hops = [h for h in rows[0]["hops"] if h[1] >= 0]
        self.assertTrue(hops, "1-8 still routes, by a bounce")
        self.assertFalse({("A", 2), ("A", 3), ("B", 0), ("B", 1)} & {(c, x) for c, x, y in hops})
        xs, _ = rc.parse_chip_status(section(p.stdout, "b"))["A"]
        self.assertEqual((xs[2], xs[3]), (59, 59))

    def test_unknown_flag_exits_2(self):
        self.assertEqual(run(CASE % "bridge 1 8 -1\n", "--nope").returncode, 2)

    def test_alternator_flag_picks_the_gnd_chip(self):
        # with stack_rails 0 every GND path takes K or L by the alternator's parity
        case = CASE.replace("stack 2 3 0 0 0", "stack 0 0 0 0 0") % "bridge 100 1 -1\n"
        chips = []
        for start in ("0", "1"):
            p = run(case, "--gnd-alternator", start)
            self.assertEqual(p.returncode, 0, p.stderr)
            row = [r for r in rc.parse_paths(section(p.stdout, "b")) if 100 in (r["node1"], r["node2"])][0]
            chips.append({h[0] for h in row["hops"]} & {"K", "L"})
        self.assertEqual(chips, [{"K"}, {"L"}])

    def test_trace_section_holds_the_router_debug_prints(self):
        p = run(CASE % "bridge 1 8 -1\n", "--trace")
        self.assertTrue(section(p.stdout, "trace").strip())
        self.assertIsNone(section(run(CASE % "bridge 1 8 -1\n").stdout, "trace"))


if __name__ == "__main__":
    unittest.main()
