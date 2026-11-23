# Routing Lab, Plan 1: Harness, Battery, Judge, CLI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `python3 tools/routing_lab/lab.py run` builds the real V5 router for the host, routes a battery of netlists with it, judges every result with the existing copper checker, and prints a table.

**Architecture:** A native C++ harness links the firmware's own routing sources against host stubs and speaks a line protocol on stdin/stdout, printing the same text the board prints for `b` and `:crossbar`. Python modules materialise a variant's `src/` tree, build it, run one case per process, and hand the text to `test/hil/routing_check.py`. No page, solver or ranking in this plan.

**Tech Stack:** `g++ -std=c++17` (Apple clang) with ASan/UBSan, Python 3.13 stdlib plus PyYAML (installed), `unittest`, git.

**Spec:** `CodeDocs/DESIGN_ROUTING_LAB.md` (Piece 1). Plans 2 to 4 (page, ceilings, lane ranking) follow.

## Global Constraints

- Work on branch `routing-lab` off `main`, in a git worktree (Task 0). Never push. Never touch `.github/workflows/release.yml` (Kevin's uncommitted change in the main checkout).
- **Nothing under `src/` is edited.**
- The harness sources must not define `initNets`, `clearAllNTCC`, `infraEvaluate`, `loadBridgesFromState`, `getNodesToConnect`, `bridgesToPaths`, `connectionAllowed` or `planFastPath`. Those come from the firmware.
- Everything else the firmware references and the harness does not link is defined in `harness/firmware_stubs.cpp`, one definition per symbol with a one-line comment saying what it stands in for. Hardware is a no-op. Policy inputs are variables set from the case.
- Harness output for a case is the text `b` prints (the block in `src/SingleCharCommands.cpp` that prints `pathDuplicates:` through `printChipStatus`) and one `xbar{12x8:<384 hex>}` line in the format of `usbSer3_sendCrossbar`. The only additions are the section markers and `[nvscan] route` lines.
- Battery runs use one process per case. Only the fidelity replay runs several cases in one process.
- Sanitizers on by default: `-fsanitize=address,undefined -fno-sanitize-recover=undefined -fno-omit-frame-pointer`, so either sanitizer ends the process with a report and the case is a `crash`.
- A sanitizer report or a crash in unmodified firmware code is a finding for Kevin, never something to fix under `src/` or hide in a stub. Record the case and the report in the task's commit message, then carry on with `SANITIZE=0` for the tests it blocks.
- Variant overrides are accepted only for paths that normalise to somewhere under `src/`.
- `test/test_routing_og/run.sh` still passes. `test/hil/test_routing_dense.py` behaves as before.
- Python: stdlib and PyYAML only.
- Run all tests with `python3 -m unittest discover -s tools/routing_lab/tests -t tools/routing_lab -v`.

## Review Focus

Inputs the spec implies and a person will hit, each pinned by a test in the task named:

1. **A variant that does not compile.** The lab reports the compiler's error text as that variant's result and keeps going. (Task 4)
2. **A bridge the firmware forbids or cannot place** (GND to TOP_RAIL, a node that is not connectable, both ends the same). The harness asks the firmware's own rule, lists it as rejected, and routes the rest. (Task 1)
3. **An empty netlist.** A valid result with status `empty`, not a judge failure. (Task 6)
4. **A state document with a node name the importer does not know** (a part-pin name such as `IC41_P1`). The error names the token and the file. (Task 5)
5. **An edit to the harness or its stubs.** Cached binaries and results are not reused. (Task 4)

## File Structure

```
tools/routing_lab/
  README.md              how to run; the bench capture procedure
  .gitignore             build/
  lab.py                 CLI: build, run, fidelity, import-state
  variants.py            variant trees, hashing, building
  cases.py               Case model, JSON, dense import, state-document import
  generators.py          typical, fuzz, stress, beyond
  runner.py              run one case, judge, battery, cache
  fidelity.py            ordered replay against a board capture
  harness/
    build.sh             compile one variant
    lab_harness.cpp      protocol, b report, sent view, taps, block
    firmware_stubs.cpp   every stubbed firmware symbol
    stubs/*.h            host headers
  cases/real/*.json      imported state documents
  tests/test_*.py
test/hil/routing_cases.py        new: the dense cases, hardware-free
test/hil/test_routing_dense.py   modified: imports them
```

---

### Task 0: Worktree

- [ ] **Step 1:** From `~/Documents/GitHub/JumperlOS`, create the worktree with the superpowers:using-git-worktrees skill: branch `routing-lab` from `main`.
- [ ] **Step 2:** Move the two untracked documents from the main checkout into the worktree, same paths: `CodeDocs/DESIGN_ROUTING_LAB.md` and `CodeDocs/PLAN_ROUTING_LAB_1_HARNESS.md`. They are committed with Task 1.
- [ ] **Step 3:** Run `test/test_routing_og/run.sh` in the worktree. Expected: `regress: 0 failing`. This is the baseline before anything is added.

All later paths are relative to the worktree.

---

### Task 1: The harness builds and routes one case

**Files:**
- Create: `tools/routing_lab/harness/build.sh`, `harness/lab_harness.cpp`, `harness/firmware_stubs.cpp`, `harness/stubs/*.h`, `tools/routing_lab/.gitignore`
- Test: `tools/routing_lab/tests/test_harness.py`

**Interfaces:**
- Produces: `harness/build.sh <src_root> <out_binary>` (env `SANITIZE=0` drops the sanitizers; exit non-zero with the compiler's stderr on failure).
- Produces: the harness protocol.

  stdin, one or more cases:
  ```
  case <name>
  stack <paths> <rails> <dacs> <gpio> <adcs>
  power <top> <bottom> <dac0> <dac1>
  probe <auto_connect> <power_source>
  bridge <node1> <node2> <dup>        # node ids as integers; dup -1 = default
  end
  ```
  stdout, per case:
  ```
  === case <name>
  --- rejected
  <node1> <node2>                     # one line per bridge the firmware refused
  --- b
  <exactly the b report>
  --- xbar
  xbar{12x8:<384 hex>}
  === end
  ```
  Exit 0 after the last case; exit 2 with a message on stderr for a malformed line.

Starting point: copy `test/test_routing_og/stubs/` to `harness/stubs/`, delete its `NetManager.h` and `InfraPaths.h` (the real headers are used), and extend. `build.sh` follows `test/test_routing_og/run.sh`: the firmware sources are compiled through symlinks in the output directory so the stub headers win the include order. Sources linked from `<src_root>`: `routing/NetsToChipConnections.cpp`, `routing/MatrixState.cpp`, `routing/NetManager.cpp`, `routing/RouteSafety.cpp`, `routing/InfraPaths.cpp`, `boards/board.cpp`, `boards/og/board_og.cpp`, `boards/v5/board_v5.cpp`. No `-DOG_JUMPERLESS`.

What the compiler asks for today (spike, 2026-11-17), all to be answered in `stubs/` and `firmware_stubs.cpp`:
- Router: `infraProbePowerSource`, `currentSenseOverlayState` (4 uses).
- `MatrixState.cpp`: `tolower`.
- `NetManager.cpp`, 24 names: members `power` and `display` on the state stub; `itoa`; `Stream::availableForWrite`; two `print` overloads; `hsvColor`; and display or probe names (`gpioAnimationBaseHues`, `adcReadings`, `gpioState`, `measurementToColor`, `colorToAnsi`, `brightenedNode`, `probing`, `packRgb`, `netColors`, `highlightedRow`, `highlightedNet`, `encoderNetHighlight`, `colorToVT100`, `colorToName`, `blockProbeButtonTimer`, `blockProbeButton`, `USBSer3`, `RgbToHsv`).
- `InfraPaths.cpp`, 14 names: members `config` and `power`; `syncNetsFromBridges`, `isEphemeralConnection`, `adjustEphemeralIndicesAfterBridgeRemoval`; `dacUserClaimed`, `getDacVoltage`, `setDac0voltage`, `setDac1voltage`, `MCP4728`, `probePowerDAC`, `probeGpioPowerHwClaim`, `probeGpioPowerHwRelease`, `gpio_set_dir`.
- Empty headers for `ArduinoStuff.h`, `SafeString.h`, `Highlighting.h`, `FileParsing.h`, `MCP4728.h`.

The link will ask for more. Same rule for each. If the list passes about 100 symbols, stop and report instead of pressing on.

Per case the harness does, in this order: set `jumperlessConfig.routing.stack_*`, `jumperlessConfig.probe.auto_connect` and `.power_source`, and the state's rail and DAC voltages (`getDacVoltage` returns them); for each bridge call `isConnectable` on both ends and `connectionAllowed`, printing refused ones under `--- rejected` and skipping them, as it does a bridge with equal ends; write the rest to `globalState.connections.bridges[i] = {node1, node2, dup}` and `numBridges`; then `infraEvaluate()`, `clearAllNTCC()`, `loadBridgesFromState()`, `getNodesToConnect()`, `bridgesToPaths()` (the order in `src/Commands.cpp` around line 241). `initNets()` runs once at start. `jumperlessConfig.hardware.revision` is 5. `currentSenseOverlayState`'s two nodes are -1 (no overlay). Firmware prints during routing are suppressed (`g_quiet`); the b report is printed with it off.

The sent view: after routing, a loop named `fillSentViewFromPaths()` sets `lastChipXY[chip].connected[y] |= 1 << x` for every hop of every non-skipped path with `chip`, `x`, `y` all in range, having cleared `lastChipXY` first. Comment it with the design's note that sends are not exercised.

- [ ] **Step 1: Write the failing tests**

```python
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
        src = "".join(open(os.path.join(LAB, "harness", f)).read() for f in ("lab_harness.cpp", "firmware_stubs.cpp"))
        for name in ("initNets", "clearAllNTCC", "infraEvaluate", "loadBridgesFromState",
                     "getNodesToConnect", "bridgesToPaths", "connectionAllowed", "planFastPath"):
            self.assertNotRegex(src, r"\b(void|int|bool)\s+%s\s*\([^;]*\)\s*\{" % name, name)
```

The `(2, 2)` assertion assumes a fresh board's defaults add the probe feed `BUF_IN`-`DAC0` as a second primary. If the b report shows otherwise, read why in `InfraPaths.cpp` and correct the test to what the firmware does; do not make the harness match the guess.

- [ ] **Step 2: Run to see them fail**

Run: the test command in Global Constraints. Expected: `setUpModule` fails, `build.sh` not found.

- [ ] **Step 3: Write `build.sh`, the stubs and `lab_harness.cpp`** as specified above.

- [ ] **Step 4: Run the tests, then the OG harness**

Run: the test command; then `test/test_routing_og/run.sh`. Expected: 4 tests OK; `regress: 0 failing`.

- [ ] **Step 5: Commit**

```bash
git add tools/routing_lab CodeDocs/DESIGN_ROUTING_LAB.md CodeDocs/PLAN_ROUTING_LAB_1_HARNESS.md
git commit -m "Routing lab: host harness links the real V5 router and prints the b report"
```

---

### Task 2: Replay, repeat, block, alternator

**Files:**
- Modify: `tools/routing_lab/harness/lab_harness.cpp`
- Test: `tools/routing_lab/tests/test_harness.py`

**Interfaces:**
- Produces: several `case ... end` blocks on one stdin are routed in order in one process, without resetting anything the firmware does not reset.
- Produces: `--repeat N` feeds each case block through the same per-case sequence N times, exactly as N identical blocks on stdin would be, prints the sections for the first pass only, and adds `--- repeat` with `same` or `different` (comparing each later pass's b report with the first, after the header lines). The probe-feed code keeps file-static state, so no shortcut that skips `infraEvaluate` is allowed.
- Produces: `--gnd-alternator N` sets `gndChipAlternator` before the first case.
- Produces: case lines `block X <chip> <x>` and `block Y <chip> <y>`: after `clearAllNTCC()` and before `loadBridgesFromState()` the pin's status is set to net `MAX_NETS - 1` (59). `clearAllNTCC` is the only place the router resets chip status.
- Produces: `--trace` turns the router's debug prints on and puts them under `--- trace`.

- [ ] **Step 1: Write the failing tests**

```python
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

    def test_alternator_flag_is_accepted(self):
        self.assertEqual(run(CASE % "bridge 100 1 -1\n", "--gnd-alternator", "1").returncode, 0)
```

- [ ] **Step 2: Run to see them fail.** Expected: 4 failures (one case in the output, no `repeat` section, blocked lanes used, unknown flag).
- [ ] **Step 3: Implement the four features.**
- [ ] **Step 4: Run the tests.** Expected: all pass.
- [ ] **Step 5: Commit** `Routing lab harness: ordered replay, repeat check, blocked pins`.

---

### Task 3: Sense-tap reachability

**Files:**
- Modify: `tools/routing_lab/harness/lab_harness.cpp`, `harness/firmware_stubs.cpp`
- Test: `tools/routing_lab/tests/test_harness.py`

**Interfaces:**
- Produces: a `--- taps` section after `--- xbar`. One line per scanned node in the board's own format, `[nvscan] route <node>: A(x9,y1) K(x8,y0) -> ADC0` or `[nvscan] route <node>: (none)`. When no ADC is free the section is the single line `skipped: no free ADC`.

The node list is a named copy of one firmware rule, `harnessScanList()`, with a comment citing `src/sensing/NetVoltageScan.cpp` (`isScannable` and `rebuildScanList`): every node of every net that is in use, not the empty net and not virtual, where the node is not a source (rails, DACs), not ADC0 to ADC4 and not the probe ADC; no duplicates; plus GND when no net holds GND. The ADC is the lowest bit of the firmware's `infraFreeAdcMask(0x0F)`. Each route is the firmware's `planFastPath(node, ADC0 + adc, &route)`, printed as `printSenseRoute` prints it.

- [ ] **Step 1: Write the failing tests**

```python
    def test_taps_listed_for_every_scanned_node(self):
        p = run(CASE % "bridge 1 8 -1\n")
        routes = dict(re.findall(r"\[nvscan\] route (\d+):(.*)", section(p.stdout, "taps")))
        self.assertLessEqual({"1", "8", "100"}, set(routes))         # the two rows and the GND auto-zero
        self.assertTrue(all("->" in routes[n] for n in ("1", "8", "100")), routes)

    def test_taps_skipped_when_every_adc_is_a_user_net(self):
        p = run(CASE % "bridge 110 1 -1\nbridge 111 2 -1\nbridge 112 3 -1\nbridge 113 4 -1\n")
        self.assertEqual(section(p.stdout, "taps").strip(), "skipped: no free ADC")
```

- [ ] **Step 2: Run to see them fail.** Expected: `section(...)` is `None`.
- [ ] **Step 3: Implement.** If `planFastPath` cannot be made to link, stop and report: the design's fallback (columns labelled "taps not checked") is Kevin's to accept.
- [ ] **Step 4: Run the tests.** Expected: pass.
- [ ] **Step 5: Commit** `Routing lab harness: sense-tap dry run through the firmware's planner`.

---

### Task 4: Variants

**Files:**
- Create: `tools/routing_lab/variants.py`
- Test: `tools/routing_lab/tests/test_variants.py`

**Interfaces:**
- Produces:
  ```python
  class BuildError(Exception):            # .stderr: str, the compiler's output
  @dataclass(frozen=True)
  class Variant: name: str; src_root: Path; hash: str
  def safe_override_path(rel: str) -> str                 # normalised "src/..." or ValueError
  def resolve(spec: str, overrides: dict[str, bytes] | None = None) -> Variant
  def build(v: Variant, sanitize: bool = True) -> Path    # cached binary; raises BuildError
  HARNESS_DIR: Path                                       # tools/routing_lab/harness, hashed into every variant
  ```
  `spec` is `"worktree"` (the `src/` of the checkout `lab.py` lives in, never copied), a path to a directory that contains `src/` (also never copied; this is how Kevin points the lab at his main checkout while the lab lives on its branch), or a git ref (`git archive <ref> src` unpacked under `build/variants/`). A spec is tried as a directory first, then as a ref. `overrides` maps a path to file contents; the base tree is copied (plain copy) and the files replaced. `hash` is the SHA-256 of every `*.h`, `*.hpp` and `*.cpp` under the variant's `src/` (sorted relative path and bytes), every file under `harness/`, and the compiler flags. Binaries live at `build/bin/<hash>/lab_harness`.

- [ ] **Step 1: Write the failing tests**

```python
class Variants(unittest.TestCase):
    def test_override_paths_must_stay_under_src(self):
        self.assertEqual(variants.safe_override_path("src/routing/./NetsToChipConnections.cpp"),
                         "src/routing/NetsToChipConnections.cpp")
        for bad in ("../etc/passwd", "/etc/passwd", "src/../../x.cpp", "src/routing/../../../x",
                    "tools/x.cpp", "src", ""):
            with self.assertRaises(ValueError, msg=bad):
                variants.safe_override_path(bad)

    def test_worktree_builds_and_is_cached(self):
        v = variants.resolve("worktree")
        b1 = variants.build(v); t = os.path.getmtime(b1)
        self.assertEqual(variants.build(v), b1); self.assertEqual(os.path.getmtime(b1), t)

    def test_git_ref_variant_builds(self):
        self.assertTrue(os.access(variants.build(variants.resolve("HEAD")), os.X_OK))

    def test_directory_spec_is_that_checkout(self):
        self.assertEqual(variants.resolve(REPO).hash, variants.resolve("worktree").hash)
        with self.assertRaises(ValueError):
            variants.resolve("/nonexistent/place")

    def test_override_changes_hash_and_broken_code_reports_the_compiler(self):
        base = variants.resolve("worktree")
        bad = variants.resolve("worktree", {"src/routing/NetsToChipConnections.cpp": b"this is not C++\n"})
        self.assertNotEqual(base.hash, bad.hash)
        with self.assertRaises(variants.BuildError) as cm:
            variants.build(bad)
        self.assertIn("error", cm.exception.stderr)

    def test_harness_edit_changes_hash(self):
        changed = self.copy_harness_and_append("// touched\n", to="lab_harness.cpp")   # a temp copy of harness/
        with mock.patch.object(variants, "HARNESS_DIR", changed):
            self.assertNotEqual(variants.resolve("worktree").hash, variants_hash_before)
```

- [ ] **Step 2: Run to see them fail.** Expected: `ModuleNotFoundError: variants`.
- [ ] **Step 3: Implement `variants.py`.**
- [ ] **Step 4: Run the tests.** Expected: 6 pass.
- [ ] **Step 5: Commit** `Routing lab: variant trees, content hashing, cached builds`.

---

### Task 5: Cases

**Files:**
- Create: `test/hil/routing_cases.py`, `tools/routing_lab/cases.py`, `tools/routing_lab/cases/real/kevin_state_2026-09-07.json`, `cases/real/slot3_snapshot_2026-08-26.json`
- Modify: `test/hil/test_routing_dense.py` (imports only)
- Test: `tools/routing_lab/tests/test_cases.py`

**Interfaces:**
- Produces: `test/hil/routing_cases.py` holding, moved verbatim from `test_routing_dense.py`, the node ids (`GND` ... `A`), `ALL_PAIRS_28`, `CASES`, `case_yaml`, and one new function split out of `case_yaml`: `bridge_dup(n1: int, n2: int, stacking: tuple) -> int`. It imports nothing but the standard library. `test_routing_dense.py` imports those names from it and is otherwise unchanged.
- Produces:
  ```python
  @dataclass
  class Case:
      name: str; cls: str
      bridges: list[tuple[int, int, int]]                  # node1, node2, dup (-1 default)
      stack: tuple[int, int, int, int, int] = (2, 3, 0, 0, 0)   # paths rails dacs gpio adcs (config.h defaults)
      power: tuple[float, float, float, float] = (0.0, 0.0, 3.33, 0.0)   # top bottom dac0 dac1 (PowerState defaults)
      probe: tuple[int, int] = (1, 0)                      # auto_connect, power_source
      must_route: bool = False
      taps_required: bool = False
      notes: str = ""
      def to_protocol(self, block: list[tuple[str, int, int]] = ()) -> str
      def digest(self) -> str                              # SHA-256 of to_protocol()
  def load_json(path) -> Case
  def save_json(case: Case, path) -> None
  def dense_cases() -> list[Case]
  def import_state(path, name: str, cls: str = "real") -> Case
  def node_id(token) -> int                                # int, or a long or short firmware name
  ```
  `dense_cases()`: one `Case` per entry of `CASES`, class `dense`, `power=(0, 0, 0, 0)`, each bridge's dup from `bridge_dup`, `must_route` from the entry's third field, `taps_required` when its fifth is `("taps",)`. `stack` stays at the defaults; the fidelity replay overrides it from the capture.
  `import_state()`: reads `bridges` (`n1`, `n2`, optional `dup`), `power` and `config.routing` with PyYAML. A dup equal to the document's `stackPaths` becomes -1, the rule in `States.cpp` at the comment "the exact value that was stamped". `node_id` accepts integers and, compared without case, the names in `fabric_v5.NODE_NAME` and `SHORT_TO_NODE` and the firmware's long forms `RP_GPIO_n`, `NANO_Dn`, `NANO_An`, `RP_UART_TX`, `RP_UART_RX`; anything else raises `ValueError` naming the token, and `import_state` adds the file.

- [ ] **Step 1: Write the failing tests**

```python
class Cases(unittest.TestCase):
    def test_dense_cases_match_the_hil_suite(self):
        d = cases.dense_cases()
        self.assertEqual(len(d), 21)
        by = {c.name: c for c in d}
        self.assertTrue(by["all_28_chip_pairs"].must_route); self.assertFalse(by["nano_dense_metric"].must_route)
        self.assertEqual(sorted(c.name for c in d if c.taps_required),
                         sorted(n for n, _, _, _, e in routing_cases.CASES if e == ("taps",)))
        self.assertEqual(len([c for c in d if c.taps_required]), 5)
        k = by["kevin_fixture_2026_09_02"]                       # stacking (2, 3, 0)
        self.assertIn((1, 101, 3), k.bridges); self.assertIn((6, 131, 0), k.bridges)

    def test_protocol_text(self):
        c = cases.Case("t", "x", [(1, 8, -1)])
        self.assertEqual(c.to_protocol([("X", 0, 2)]),
            "case t\nstack 2 3 0 0 0\npower 0 0 3.33 0\nprobe 1 0\nblock X 0 2\nbridge 1 8 -1\nend\n")

    def test_json_round_trip(self): ...                          # save_json then load_json equals the Case

    def test_state_import_resets_the_stamped_count(self):
        c = cases.import_state(HIL + "/slot3_snapshot_2026-08-26.yaml", "slot3")
        gp = [b for b in c.bridges if 131 <= b[0] <= 138 or 131 <= b[1] <= 138]
        self.assertTrue(gp); self.assertTrue(all(b[2] == -1 for b in gp))

    def test_state_import_reads_names_and_settings(self):
        c = cases.import_state(HIL + "/kevin_state_2026-09-07_2303.yaml", "kevin")
        self.assertEqual(len(c.bridges), 13); self.assertIn((6, 131, -1), c.bridges)
        self.assertEqual(c.stack[:3], (2, 3, 0)); self.assertEqual(c.power, (4.40, 7.40, 2.50, 0.60))

    def test_unknown_node_name_is_named(self):
        bad = self.tmp_yaml("bridges:\n  - {n1: IC41_P1, n2: 3}\n")
        with self.assertRaisesRegex(ValueError, r"IC41_P1.*%s" % re.escape(os.path.basename(bad))):
            cases.import_state(bad, "bad")
        self.assertEqual(cases.node_id("rp_uart_tx"), 116); self.assertEqual(cases.node_id("ISENSE_MINUS"), 109)

    def test_hil_suite_still_parses(self):
        py_compile.compile(HIL + "/test_routing_dense.py", doraise=True)
```

- [ ] **Step 2: Run to see them fail.** Expected: `ModuleNotFoundError: cases`.
- [ ] **Step 3: Move the dense cases, write `cases.py`, import the two state documents** with `import_state` and `save_json`.
- [ ] **Step 4: Run the tests.** Expected: 7 pass.
- [ ] **Step 5: Commit** `Routing lab: case model; dense cases shared with the HIL suite; state-document import`.

---

### Task 6: Runner and judge

**Files:**
- Create: `tools/routing_lab/runner.py`
- Test: `tools/routing_lab/tests/test_runner.py`

**Interfaces:**
- Consumes: `Case.to_protocol`, `Case.digest`, `variants.build`, the harness sections.
- Produces:
  ```python
  def parse_sections(stdout: str) -> dict[str, dict[str, str]]        # {case name: {section: text}}
  def run_case(binary: Path, case: Case, *, repeat: int = 2, block=(), timeout: float = 20.0) -> dict
  def run_battery(v: Variant, cases: list[Case], *, jobs: int | None = None, block=(), use_cache: bool = True) -> list[dict]
  ```
  A result:
  ```python
  {"case": str, "cls": str, "status": "ok" | "problems" | "empty" | "crash" | "timeout",
   "problems": [str], "notes": [str], "rejected": [[int, int]],
   "metrics": {"primaries", "routed_primaries", "bounced", "routed_duplicates", "crosspoints",
               "taps": int | None, "taps_dead": [int], "repeat_same": bool | None},
   "b": str, "xbar": str, "stderr": str}                            # stderr: last 4000 characters
  ```
  Judging: `rc.full_check(b, xbar, expect_all_routed=case.must_route, strict_claims=case.must_route and all(d == 0 for _, _, d in case.bridges))`. A dup of -1 means "default", which stacks, so only an explicit 0 on every bridge is strict; that is the HIL suite's rule (no stacking and must route). A dead tap is a problem when `case.taps_required`, otherwise a note. `repeat_same == False` is a problem. A case whose bridges were all rejected or that has none is `empty`. A non-zero exit is `crash` with the sanitizer report in `stderr`; an expired timeout kills the process and is `timeout`. The cache is one JSON file per `(variant hash, case digest, repeat, block)` under `build/results/`. `run_battery` uses a thread pool over subprocesses, `jobs` defaulting to the CPU count.

- [ ] **Step 1: Write the failing tests**

```python
class Runner(unittest.TestCase):
    def test_ok_case(self):
        r = runner.run_case(BIN, cases.Case("t", "x", [(1, 8, -1)], must_route=True))
        self.assertEqual((r["status"], r["problems"]), ("ok", []))
        self.assertEqual(r["metrics"]["taps_dead"], []); self.assertTrue(r["metrics"]["repeat_same"])

    def test_empty_case(self):
        self.assertEqual(runner.run_case(BIN, cases.Case("e", "x", []))["status"], "empty")
        self.assertEqual(runner.run_case(BIN, cases.Case("e", "x", [(100, 101, -1)]))["status"], "empty")

    def test_timeout_and_crash(self):
        self.assertEqual(runner.run_case(self.script("sleep 30"), CASE18, timeout=0.5)["status"], "timeout")
        r = runner.run_case(self.script("echo boom >&2; exit 134"), CASE18)
        self.assertEqual(r["status"], "crash"); self.assertIn("boom", r["stderr"])

    def test_unrouted_bridge_is_a_problem_only_when_it_must_route(self):
        over = [c for c in cases.dense_cases() if c.name == "k_rows_overflow_metric"][0]
        self.assertNotEqual(runner.run_case(BIN, over)["status"], "crash")
        must = dataclasses.replace(over, must_route=True)
        self.assertEqual(runner.run_case(BIN, must)["status"], "problems")

    def test_battery_is_cached(self):
        v = variants.resolve("worktree"); cs = [CASE18]
        runner.run_battery(v, cs)
        with mock.patch.object(runner, "run_case", side_effect=AssertionError("ran again")):
            self.assertEqual(runner.run_battery(v, cs)[0]["status"], "ok")
```

- [ ] **Step 2: Run to see them fail.** Expected: `ModuleNotFoundError: runner`.
- [ ] **Step 3: Implement `runner.py`.**
- [ ] **Step 4: Run the tests.** Expected: 5 pass.
- [ ] **Step 5: Commit** `Routing lab: run a case in its own process, judge it with routing_check, cache`.

---

### Task 7: Generated classes

**Files:**
- Create: `tools/routing_lab/generators.py`
- Test: `tools/routing_lab/tests/test_generators.py`

**Interfaces:**
- Produces:
  ```python
  USER_NODES: list[int]        # fabric_v5.NODE_NAME keys without BUFFER_IN (139) and BUFFER_OUT (140)
  def legal(bridges) -> bool   # no net holds two of GND, TOP_RAIL, BOTTOM_RAIL, DAC0, DAC1; no bridge with equal ends
  def fuzz(seed: int = 1, n: int = 2000, max_bridges: int = 12, row_bias: int = 60) -> list[Case]
  def typical(seed: int = 1, n: int = 200) -> list[Case]
  def stress() -> list[Case]
  def beyond() -> list[Case]
  ```
  All use `random.Random(seed)`, never the global generator. All have `must_route=False`.
  - `fuzz`: 1 to `max_bridges` bridges; each end is a row 1 to 60 with probability `row_bias` percent, else a draw from the other `USER_NODES`; illegal netlists are redrawn. Names `fuzz_<seed>_<index>`.
  - `typical`: 4 to 20 bridges. One or two ICs, each 4, 7 or 8 pins wide straddling the gap (rows `r..r+w-1` and `r+30..r+30+w-1`); one pin to TOP_RAIL or BOTTOM_RAIL, one to GND, two to five others to a GPIO, an ADC, a DAC, a Nano pin, UART or another row; then up to three row-to-row jumpers and up to two more rail or GND drops. Names `typical_<seed>_<index>`.
  - `stress`: `flood_<A..H>_gpio` (the chip's seven rows to GPIO_1..7), `flood_<A..H>_k` (its seven rows to TOP_RAIL, BOTTOM_RAIL, DAC0, DAC1, ADC0, ADC1, ADC2), `gnd_two_rows_every_chip`, `corner_rows_to_specials` (29, 30, 59, 60 to TOP_RAIL, GPIO_1, DAC0, ADC0), `six_hub_lanes` (D1-D0, D3-DAC1, D5-GPIO_1, D2-ADC1, D4-GPIO_2, ADC2-GPIO_3: one net per hub lane IJ, IK, IL, JK, JL, KL; DAC0 is left alone so the probe feed stays off KL), `one_net_forty_nodes` (39 bridges chaining rows spread over all eight chips), `max_duplicates` (the 28 chip pairs with dup 7, plus TOP_RAIL and GND to four rows each with dup 7).
  - `beyond`: `every_nano_pin` (D0..D13 and A0..A7 each to its own row), `nine_k_nets` (TOP_RAIL, BOTTOM_RAIL, DAC0, DAC1, ADC0, ADC1, ADC2, ADC3, AREF to rows 1, 8, 15, 22, 31, 38, 45, 52, 2: nine nets for eight K rows), `max_bridges_random` (seed 7, as many legal random bridges as `MAX_BRIDGES` for V5 in `src/JumperlessDefines.h`).

- [ ] **Step 1: Write the failing tests**

```python
class Generators(unittest.TestCase):
    def test_seeded_and_deterministic(self):
        self.assertEqual([c.digest() for c in generators.fuzz(3, 50)], [c.digest() for c in generators.fuzz(3, 50)])
        self.assertNotEqual(generators.fuzz(3, 50)[0].digest(), generators.fuzz(4, 50)[0].digest())
        self.assertEqual([c.digest() for c in generators.typical(1, 20)], [c.digest() for c in generators.typical(1, 20)])

    def test_everything_generated_is_legal_and_in_range(self):
        for c in generators.fuzz(1, 300) + generators.typical(1, 100) + generators.stress() + generators.beyond():
            self.assertTrue(generators.legal([(a, b) for a, b, _ in c.bridges]), c.name)
            self.assertTrue(all(n in generators.USER_NODES for a, b, _ in c.bridges for n in (a, b)), c.name)
        self.assertTrue(all(4 <= len(c.bridges) <= 20 for c in generators.typical(1, 100)))
        self.assertFalse(generators.legal([(100, 1), (101, 1)])); self.assertFalse(generators.legal([(5, 5)]))

    def test_stress_names(self):
        names = {c.name for c in generators.stress()}
        self.assertEqual(len([n for n in names if n.startswith("flood_")]), 16)
        self.assertLessEqual({"six_hub_lanes", "one_net_forty_nodes", "max_duplicates"}, names)

    def test_no_generated_case_crashes_the_router(self):
        rs = runner.run_battery(variants.resolve("worktree"),
                                generators.stress() + generators.beyond() + generators.fuzz(1, 200))
        self.assertEqual([r["case"] for r in rs if r["status"] in ("crash", "timeout")], [])
```

The last test is a finding if it fails, not a harness bug to paper over: report the case and the sanitizer output to Kevin.

- [ ] **Step 2: Run to see them fail.** Expected: `ModuleNotFoundError: generators`.
- [ ] **Step 3: Implement `generators.py`.**
- [ ] **Step 4: Run the tests.** Expected: 4 pass, or the fourth fails with a named case.
- [ ] **Step 5: Commit** `Routing lab: typical, fuzz, stress and beyond-fabric case generators`.

---

### Task 8: Command line and the checks at `main`

**Files:**
- Create: `tools/routing_lab/lab.py`, `tools/routing_lab/README.md`
- Test: `tools/routing_lab/tests/test_cli.py`, `tools/routing_lab/tests/test_acceptance.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  ```
  lab.py build [--variant worktree|<git ref>]
  lab.py run   [--variant V] [--baseline V0] [--classes dense,real,typical,fuzz,stress,beyond]
               [--case NAME] [--jobs N] [--json FILE]
  lab.py import-state FILE.yaml --name NAME
  ```
  `serve` and `export` are Plan 2. Defaults: `--variant worktree`, `--classes dense,real`. `run` prints one row per class: cases, fully routed, primaries routed of total, cases with problems, crashes and timeouts, dead taps; then one line per case that is not `ok`/`empty`. Exit 1 when any result is `crash` or `timeout`, any problem starts with `SHORT` or `STRAY`, a must-route case has problems, or, with `--baseline`, a case the baseline fully routed is not fully routed, or a case has a problem the baseline did not. A variant that fails to build prints the compiler output and exits 3. `--json` writes the full result list.
  ```python
  def battery(classes: list[str]) -> list[Case]
  def regressions(base: list[dict], new: list[dict]) -> list[str]
  def main(argv: list[str]) -> int
  ```

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli.py
class Cli(unittest.TestCase):
    def test_run_dense_at_worktree_exits_zero(self):
        self.assertEqual(lab.main(["run", "--classes", "dense"]), 0)

    def test_regressions(self):
        ok = {"case": "a", "status": "ok", "problems": [], "metrics": {"primaries": 2, "routed_primaries": 2}}
        worse = {**ok, "metrics": {"primaries": 2, "routed_primaries": 1}}
        self.assertEqual(lab.regressions([ok], [ok]), [])
        self.assertEqual(len(lab.regressions([ok], [worse])), 1)
        self.assertEqual(len(lab.regressions([ok], [{**ok, "status": "problems", "problems": ["SHORT x"]}])), 1)

    def test_broken_variant_exits_3(self):
        with mock.patch.object(variants, "build", side_effect=variants.BuildError("x.cpp:1: error: no")):
            self.assertEqual(lab.main(["run", "--classes", "dense"]), 3)

# tests/test_acceptance.py
class AtMain(unittest.TestCase):
    def test_every_must_route_dense_case_is_clean(self):
        rs = {r["case"]: r for r in runner.run_battery(variants.resolve("worktree"), cases.dense_cases())}
        for c in cases.dense_cases():
            if c.must_route:
                self.assertEqual(rs[c.name]["status"], "ok", (c.name, rs[c.name]["problems"]))
                self.assertEqual(rs[c.name]["metrics"]["routed_primaries"], rs[c.name]["metrics"]["primaries"])
            if c.taps_required:
                self.assertEqual(rs[c.name]["metrics"]["taps_dead"], [], c.name)
        m = rs["nano_dense_metric"]["metrics"]                  # 12 bridges plus the probe feed
        self.assertEqual((m["primaries"], m["routed_primaries"]), (13, 13))

class History(unittest.TestCase):                 # never skipped: see run_at below
    def test_before_the_hub_tier_two_nano_bridges_fail(self):
        r = self.run_at("a1accf5^", "nano_dense_metric")
        self.assertEqual((r["metrics"]["primaries"], r["metrics"]["routed_primaries"]), (13, 11))

    def test_before_the_bounce_pin_fix_claims_are_wrong(self):
        r = self.run_at("f41e755^", "kevin_fixture_2026_09_02")
        self.assertTrue(any("UNCLAIMED" in p or "CLAIM WITHOUT COPPER" in p or "WRONG CLAIM" in p
                            for p in r["problems"]), r["problems"])
```

`run_at(ref, name)` builds `variants.resolve(ref)` and returns the result for that dense case. Both refs carry every file the harness links (checked 2026-11-17). If a ref still fails to build against today's stubs, the test falls back to an override of the current router that puts the old behaviour back, so the lab is always shown catching a known regression:
- for `a1accf5^`: the one call `rescueViaHubs(startIndex);` in `bridgesToPaths` removed;
- for `f41e755^`: in `resolveAltPaths`, the line `int xMapBB = xMapForChipLane0(bb, sfChip);` put back to `int xMapBB = xMapForChipLane0(globalState.connections.paths[i].chip[0], bb);`.

Print which form ran. With the fallback the exact counts may differ from the ledger; assert then that `nano_dense_metric` routes fewer than 13 primaries, and that the claim problems appear. The counts 13 and 11 are the sweep ledger's (`CodeDocs/ROUTING_SWEEP_2026-09-03.md` section 3.2): twelve bridges plus the probe feed.

- [ ] **Step 2: Run to see them fail.** Expected: `ModuleNotFoundError: lab`.
- [ ] **Step 3: Implement `lab.py` and write `README.md`** (the three commands, the test command, what each class is).
- [ ] **Step 4: Run all tests.** Expected: pass, with each `History` test printing whether it ran the ref or the override. If `AtMain` fails, the harness disagrees with the board's known behaviour: investigate the harness first (stack values, feed, case conversion), and report what was found before changing any expectation.
- [ ] **Step 5: Run `python3 tools/routing_lab/lab.py run --classes dense,real,typical,fuzz,stress,beyond` and paste the table into the commit body.**
- [ ] **Step 6: Commit** `Routing lab: lab.py run/build/import-state; the dense suite is clean at main`.

---

### Task 9: Fidelity replay

**Files:**
- Create: `tools/routing_lab/fidelity.py`, `tools/routing_lab/fidelity/README.md`
- Modify: `tools/routing_lab/lab.py` (`fidelity` subcommand), `tools/routing_lab/README.md`
- Test: `tools/routing_lab/tests/test_fidelity.py`

**Interfaces:**
- Consumes: a capture directory as `test_routing_dense.py` writes it with `JL_ROUTING_SNAP_DIR` (`<case>.b.txt`, `<case>.xbar.txt`, `<case>.paste.txt`), named `fidelity/board_<commit hash>/`.
- Produces:
  ```python
  def stack_from_b(b_text: str) -> tuple[int, int, int, int, int]     # the five "...Duplicates: N" header lines
  def replay(binary: Path, capture_dir: Path, alternator: int) -> dict[str, dict[str, str]]   # one process, CASES order
  def compare(capture_dir: Path, replayed: dict) -> list[str]          # one line per difference; [] is a pass
  def check(capture_dir: Path, variant_spec: str | None = None) -> tuple[bool, list[str]]
  ```
  `lab.py fidelity <capture_dir> [--variant REF]`: the variant defaults to the commit hash in the directory name. `check` replays with alternator 0 and then 1 and passes if either compares clean; on failure it returns the shorter difference list. Each case's `stack` comes from its own capture's header. `compare` checks, per case: the path rows through `routing_snapshot_diff.rows_by_key`, the chip status through `rc.parse_chip_status`, and the crosspoint sets through `rc.crosspoints_from_xbar`. A case in the suite with no capture file is a difference.
- Produces: `fidelity/README.md`, the bench procedure from the design: build and flash a clean recorded commit, power-cycle, `JL_ROUTING_SNAP_DIR=tools/routing_lab/fidelity/board_<hash> python3 test/hil/test_routing_dense.py`, then `lab.py fidelity`.

- [ ] **Step 1: Write the failing tests**

```python
class Fidelity(unittest.TestCase):
    def setUp(self):                                # a capture made by the harness itself, alternator 1
        self.dir = Path(tempfile.mkdtemp()) / "board_selftest"
        out = fidelity.replay(BIN, None, alternator=1)          # None: default stacks, all dense cases
        self.dir.mkdir()
        for name, s in out.items():
            (self.dir / f"{name}.b.txt").write_text(s["b"]); (self.dir / f"{name}.xbar.txt").write_text(s["xbar"])

    def test_stack_from_b(self):
        self.assertEqual(fidelity.stack_from_b("pathDuplicates: 9\ndacDuplicates: 9\nrailsDuplicates: 9\n"
                                               "gpioDuplicates: 0\nadcDuplicates: 0\n"), (9, 9, 9, 0, 0))

    def test_own_capture_passes_under_one_parity(self):
        ok, diffs = fidelity.check(self.dir, "worktree")
        self.assertTrue(ok, diffs[:5])

    def test_a_moved_row_fails_and_names_the_case(self):
        p = self.dir / "chain_all_chips.b.txt"
        rows = p.read_text().split("\n")
        i = next(i for i, l in enumerate(rows) if re.match(r"\d+\t", l))
        cols = rows[i].split("\t"); cols[4] = str((int(cols[4]) + 1) % 16); rows[i] = "\t".join(cols)
        p.write_text("\n".join(rows))
        ok, diffs = fidelity.check(self.dir, "worktree")
        self.assertFalse(ok); self.assertTrue(any("chain_all_chips" in d for d in diffs))

    def test_missing_capture_is_a_difference(self):
        (self.dir / "gnd_spread.b.txt").unlink()
        self.assertTrue(any("gnd_spread" in d for d in fidelity.check(self.dir, "worktree")[1]))
```

- [ ] **Step 2: Run to see them fail.** Expected: `ModuleNotFoundError: fidelity`.
- [ ] **Step 3: Implement `fidelity.py`, the subcommand and the README.**
- [ ] **Step 4: Run all tests.** Expected: pass.
- [ ] **Step 5: Commit** `Routing lab: fidelity replay against a board capture`.

The real gate needs a board capture. Until one is committed under `fidelity/`, `lab.py run` ends its table with the line `not verified against a board`.

---

## After this plan

Kevin's bench run (or his go-ahead to flash a plugged-in V5), then `lab.py fidelity`. Plan 2 is the server and page.
