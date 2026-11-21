# Routing Lab, Plan 2: Server, Page, Both Views, Resistance

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `python3 tools/routing_lab/lab.py serve` opens a page that runs a router variant against the battery, shows a table that separates routers (copies, crosspoints, ohms, taps), and draws any case on a generated fabric diagram and on the r7 KiCad sheet with every net's copper lit and every problem marked.

**Architecture:** Python does all the reckoning and the page only draws. `copper.py` turns one result into a "paint" (which net is on which wire and crosspoint, ohms per bridge). `fabric_view.py` lays out the generated diagram from the fabric data. `sheet.py` reads the r7 `.kicad_sch` for wire, label and pin positions and has `kicad-cli` plot the backdrop. `server.py` is a small local HTTP server over those and the plan 1 modules. `web/` is one page of plain JavaScript and SVG with no build step and no dependencies.

**Tech Stack:** Python 3.13 standard library (`http.server`), plain JS/SVG/CSS, `kicad-cli` (KiCad 10, already installed) for the sheet backdrop, Node 20 only for `node --check`.

**Spec:** `CodeDocs/DESIGN_ROUTING_LAB.md`, "Piece 2: the page" and "Learned building piece 1". Builds on plan 1 (`tools/routing_lab/`, branch `worktree-routing-lab`).

## Global Constraints

- Same worktree and branch as plan 1. Never push. Nothing under `src/` is edited.
- The server binds `127.0.0.1` only.
- Every `/api/` request must carry the header `X-Lab-Token` with the token the server made at start (the page gets it inlined in `index.html`). A missing or wrong token is 403.
- A request whose `Host` is not `127.0.0.1:<port>` or `localhost:<port>`, or whose `Origin`, when present, is not `http://` plus one of those, is 403.
- From the page a variant is `worktree`, a git ref, a directory named with `--tree` when the server started, or one of those with uploaded files. Any other directory is 400. Uploaded paths go through `variants.safe_override_path`. An upload over 5 MB is 413.
- No page dependencies, no build step, no network requests except to the server itself.
- Resistance is stored in units of one crosspoint (a two-crosspoint path is 2.0). The page and the CLI multiply by the ohms-per-crosspoint setting, default 60.
- A bridge the firmware rejected, left out of every net, or refused in its safety check is never shown or counted as a routing miss.
- Colours: one fixed palette indexed by net number, the same in both views and the table. Problems are red. Nothing else is red.
- All tests: `python3 -m unittest discover -s tools/routing_lab/tests -t tools/routing_lab`.

## Review Focus

Inputs the spec implies and a person will hit, each pinned by a test or a named browser check in the task shown:

1. **The variant does not build** (a typo saved mid-edit). The page shows the compiler's first error and keeps the last good results on screen; live mode keeps watching. (Tasks 3, 5)
2. **A request from another web page.** Any page in a browser on this Mac can reach a localhost port; without the token and origin checks it could have code compiled and run. 403, and nothing is built. (Task 3)
3. **A case that crashed or timed out.** The case panel shows the status and the sanitizer report instead of an empty diagram. (Tasks 1, 4)
4. **The KiCad sheet cannot be made** (no `kicad-cli`, or the schematic is not where expected). The sheet tab says what is missing and how to point at the file; everything else works. (Tasks 6, 7)
5. **A file saved while the build runs.** `variants.build` raises "the sources changed"; the server resolves again and retries once. (Task 3)

## File Structure

```
tools/routing_lab/
  copper.py        one result -> paint: nets on wires and crosspoints, claims, ohms
  fabric_view.py   the generated diagram's geometry, from fabric_v5
  sheet.py         r7 .kicad_sch -> overlay (wire, label, pin positions); kicad-cli backdrop
  server.py        local HTTP server and API
  export.py        one-file read-only HTML of a run
  lab.py           + serve, sheet, export, clean; run prints copies / crosspoints / ohms
  web/index.html, web/lab.js, web/lab.css
  tests/test_copper.py, test_fabric_view.py, test_sheet.py, test_server.py, test_export.py
  build/sheet/     git-ignored: overlay.json, backdrop.svg
```

---

### Task 1: Paint and resistance

**Files:**
- Create: `tools/routing_lab/copper.py`, `tests/test_copper.py`
- Modify: `tools/routing_lab/runner.py` (metrics), `tools/routing_lab/lab.py` (`run` columns), `tests/test_cli.py`

**Interfaces:**
- Produces:
  ```python
  def wire(chip: str, axis: str, pin: int) -> str            # the fabric net name on that pin (fabric_v5.X_NET / Y_NET)
  def wire_kind(name: str) -> str                            # "row" | "lane" | "bounce" | "hub" | "special"
  def effective_resistance(edges: list[tuple[str, str]], a: str, b: str) -> float | None
      # every edge is one crosspoint (1.0) between two wires; None when a and b are not connected
  def paint(result: dict) -> dict
  NET_COLOURS: list[str]                                     # 16 hex colours; a net's colour is NET_COLOURS[net % 16]
  ```
  `paint(result)` reads `result["b"]`, `result["xbar"]` and `result["notes"]` through `routing_check`'s parsers and returns:
  ```python
  {"nets": {"6": {"label": "6", "colour": "#...", "nodes": [1, 8]}},     # label is the b report's token: Gn, T, B, d0, d1 or the number
   "crosspoints": [{"chip": "A", "x": 2, "y": 1, "net": 6, "path": 1, "dup": 0}],
   "wires": {"/AB0": {"kind": "lane", "nets": [6], "pins": [{"chip": "A", "axis": "X", "pin": 2, "claim": 6}, ...]}},
   "bridges": [{"n1": 1, "n2": 8, "net": 6, "state": "routed" | "unrouted" | "refused" | "left_out" | "rejected",
                "copies": 3, "hops": 2, "r": 0.667}],             # r in crosspoint units, None unless routed
   "problems": [...], "notes": [...], "status": "ok"}
  ```
  A wire lists every pin it has, each with the chip status's claim (`None` = free). `nets` on a wire with two entries is a short. `copies` counts routed path rows for that bridge (primary plus duplicates); `hops` is the primary's crosspoints. `state` comes from the result's `rejected`, `notes` ("left out of every net", "refused by the firmware's safety check") and the path table. For a result whose status is `crash`, `timeout` or `empty`, `paint` returns empty `nets`, `crosspoints`, `wires`, `bridges` and carries `problems`, `notes`, `status` and `stderr`.
- Produces in every result's `metrics` (computed in `runner.judge`): `worst_r`, `median_r` (over routed user bridges), `rail_worst_r` (bridges with GND, TOP_RAIL or BOTTOM_RAIL at one end); each `None` when there is no such bridge. The probe feed's bridge is left out of all three.
- `lab.py run` gains columns `copies` (routed duplicates), `xpoints` and `worst ohm` (class maximum of `worst_r` times 60, with `--ohms N` to change 60).

- [ ] **Step 1: Write the failing tests**

```python
class Copper(unittest.TestCase):
    def test_series_and_parallel(self):
        self.assertEqual(copper.effective_resistance([("a", "m"), ("m", "b")], "a", "b"), 2.0)
        two = [("a", "m"), ("m", "b"), ("a", "n"), ("n", "b")]
        self.assertAlmostEqual(copper.effective_resistance(two, "a", "b"), 1.0)
        self.assertIsNone(copper.effective_resistance([("a", "m")], "a", "b"))
        self.assertEqual(copper.effective_resistance([], "a", "a"), 0.0)

    def test_wire_names_and_kinds(self):
        self.assertEqual(copper.wire("A", "X", 2), "/AB0"); self.assertEqual(copper.wire("B", "X", 0), "/AB0")
        self.assertEqual(copper.wire("A", "Y", 1), "1");    self.assertEqual(copper.wire("K", "Y", 0), "AK")
        self.assertEqual([copper.wire_kind(n) for n in ("1", "/AB0", "AK", "IJ", "TOP_RAIL")],
                         ["row", "lane", "lane", "hub", "special"])
        self.assertEqual(copper.wire_kind(copper.wire("A", "Y", 0)), "bounce")

    def test_paint_of_one_direct_bridge(self):
        p = copper.paint(runner.run_case(BIN, cases.Case("t", "x", [(1, 8, 0)])))      # dup 0: one path
        b = [x for x in p["bridges"] if (x["n1"], x["n2"]) == (1, 8)][0]
        self.assertEqual((b["state"], b["copies"], b["hops"], b["r"]), ("routed", 1, 2, 2.0))
        net = str(b["net"])
        self.assertEqual(p["wires"]["1"]["nets"], [b["net"]]); self.assertEqual(p["wires"]["8"]["nets"], [b["net"]])
        self.assertEqual(len([c for c in p["crosspoints"] if c["net"] == b["net"]]), 2)
        self.assertRegex(p["nets"][net]["colour"], r"^#[0-9a-f]{6}$")
        lane = [w for w in p["wires"].values() if w["kind"] == "lane" and w["nets"] == [b["net"]]][0]
        self.assertTrue(all(pin["claim"] == b["net"] for pin in lane["pins"]))          # claimed at both ends

    def test_copies_lower_the_resistance(self):
        one = copper.paint(runner.run_case(BIN, cases.Case("t", "x", [(1, 8, 0)])))
        three = copper.paint(runner.run_case(BIN, cases.Case("t", "x", [(1, 8, 2)])))
        r = lambda p: [x for x in p["bridges"] if (x["n1"], x["n2"]) == (1, 8)][0]
        self.assertGreater(r(three)["copies"], 1); self.assertLess(r(three)["r"], r(one)["r"])

    def test_states_that_are_not_routing_misses(self):
        p = copper.paint(runner.run_case(BIN, cases.Case("t", "x", [(100, 101, -1), (5, 101, -1), (5, 131, -1),
                                                                    (100, 1, -1), (102, 1, -1)])))
        state = {(b["n1"], b["n2"]): b["state"] for b in p["bridges"]}
        self.assertEqual(state[(100, 101)], "rejected"); self.assertEqual(state[(102, 1)], "left_out")
        self.assertIn("refused", (state[(5, 101)], state[(5, 131)]))
        self.assertNotIn("unrouted", state.values())

    def test_a_crashed_result_paints_empty_with_its_report(self):
        p = copper.paint({"case": "c", "cls": "x", "status": "crash", "problems": ["the harness exited with 134"],
                          "notes": [], "rejected": [], "metrics": {}, "b": "", "xbar": "", "stderr": "ASAN boom"})
        self.assertEqual((p["crosspoints"], p["bridges"], p["status"]), ([], [], "crash")); self.assertIn("boom", p["stderr"])

    def test_metrics_carry_resistance(self):
        m = runner.run_case(BIN, cases.Case("t", "x", [(1, 8, 0), (100, 3, 0)]))["metrics"]
        self.assertEqual(m["worst_r"], 2.0); self.assertEqual(m["rail_worst_r"], 2.0)
        self.assertIsNone(runner.run_case(BIN, cases.Case("t", "x", [(1, 8, 0)]))["metrics"]["rail_worst_r"])
```
In `tests/test_cli.py`: `run --classes dense` output has the header words `copies`, `xpoints` and `worst ohm`, and `--ohms 30` halves the printed worst ohms.

- [ ] **Step 2: Run to see them fail.** Expected: `ModuleNotFoundError: copper`.
- [ ] **Step 3: Implement.** `effective_resistance`: build the Laplacian over the component holding `a`, ground `b`, solve by Gaussian elimination with partial pivoting (pure Python; the systems have a few dozen unknowns).
- [ ] **Step 4: Run all tests.** Expected: pass. Then `lab.py run --classes dense,stress` and read the new columns for sense (a direct bridge is 120 ohm at 60 per crosspoint).
- [ ] **Step 5: Commit** `Routing lab: paint a result (nets on copper, claims, ohms); run prints copies, crosspoints, ohms`.

---

### Task 2: The generated fabric diagram's geometry

**Files:**
- Create: `tools/routing_lab/fabric_view.py`, `tests/test_fabric_view.py`

**Interfaces:**
- Produces `layout() -> dict`, computed once from `fabric_v5`:
  ```python
  {"size": [w, h], "cell": 10,
   "chips": {"A": {"x": .., "y": .., "role": "bb"}, ..., "L": {.. "role": "sf"}},   # top-left of a 16 x 8 grid of cells
   "wires": {"/AB0": {"kind": "lane", "d": "M.. L..", "label": [x, y] | None}},     # one SVG path per wire, touching all its pins
   "pads": {"1": {"x": .., "y": .., "label": "1", "group": "row"}, "TOP_RAIL": {...}}}  # one pad per node wire
  ```
  Layout rules, in the manner of the sheet's two crossbar blocks:
  - A to H in one row, I J K L in a row above, the lane tracks between. X pins are columns (X0 left), Y pins are rows (Y0 top). The crosspoint (x, y) of a chip is the centre of cell (x, y).
  - Each column's wire leaves the top of a breadboard chip; each of the 48 breadboard-to-breadboard lanes has its own horizontal track. Each of the 32 lanes into I/J/K/L runs up to that chip's row for it. The 6 hub lanes run above the SF chips.
  - Y1..Y7 of a breadboard chip run down to its seven row pads; Y0 ends in a short capped stub (the bounce row).
  - Each special node on an SF chip's X pin runs up to a labelled pad. GND, on K.X15 and L.X15, is one wire with one pad.
  - Rows are drawn as a strip of pads: 1 to 30 under A to D, 31 to 60 under E to H. Rows 29, 30, 59 and 60 are pads at K and L like the other specials.

- [ ] **Step 1: Write the failing tests**

```python
class FabricView(unittest.TestCase):
    def setUp(self): self.v = fabric_view.layout()

    def test_every_wire_and_chip_is_drawn(self):
        names = {n for c in fabric_v5.CHIPS for n in fabric_v5.X_NET[c] + fabric_v5.Y_NET[c]}
        self.assertEqual(set(self.v["wires"]), names); self.assertEqual(set(self.v["chips"]), set(fabric_v5.CHIPS))

    def test_a_wire_touches_every_pin_it_has(self):
        for chip in fabric_v5.CHIPS:
            for axis, nets in (("X", fabric_v5.X_NET[chip]), ("Y", fabric_v5.Y_NET[chip])):
                for pin, name in enumerate(nets):
                    self.assertTrue(fabric_view.touches(self.v["wires"][name]["d"], fabric_view.pin_point(self.v, chip, axis, pin)),
                                    (chip, axis, pin, name))

    def test_no_two_wires_share_a_track(self):
        self.assertEqual(fabric_view.overlaps(self.v), [])      # collinear overlapping segments of different wires

    def test_chips_do_not_overlap_and_fit(self):
        boxes = [(c["x"], c["y"], c["x"] + 160, c["y"] + 80) for c in self.v["chips"].values()]
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                self.assertTrue(a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])
        self.assertTrue(all(0 <= x0 and x1 <= self.v["size"][0] and 0 <= y0 and y1 <= self.v["size"][1] for x0, y0, x1, y1 in boxes))

    def test_every_node_has_a_pad(self):
        self.assertEqual(set(self.v["pads"]), set(fabric_v5.NODE_NET.values()))
        self.assertEqual(len([p for p in self.v["pads"].values() if p["group"] == "row"]), 60)
```
`touches(d, point)`, `pin_point(view, chip, axis, pin)` and `overlaps(view)` are public helpers of `fabric_view` (the page needs `pin_point`'s rule too, so the layout also stores each chip's origin and the cell size).

- [ ] **Step 2: Run to see them fail.** Expected: `ModuleNotFoundError: fabric_view`.
- [ ] **Step 3: Implement `layout()`** with orthogonal paths only (horizontal and vertical segments).
- [ ] **Step 4: Run the tests.** Expected: pass.
- [ ] **Step 5: Commit** `Routing lab: geometry of the generated fabric diagram`.

---

### Task 3: The server

**Files:**
- Create: `tools/routing_lab/server.py`, `tests/test_server.py`, `tools/routing_lab/web/index.html` (a placeholder with the token slot; Task 4 fills it)
- Modify: `tools/routing_lab/lab.py` (`serve`)

**Interfaces:**
- Produces:
  ```python
  def make_server(port: int = 0, trees: list[str] = ()) -> http.server.ThreadingHTTPServer   # 127.0.0.1; has .token and .url
  ```
  `lab.py serve [--port 8765] [--tree DIR]... [--no-open]` prints the URL and opens it in the default browser.
- The API (JSON; every request needs the token):
  | request | answer |
  |---|---|
  | `GET /api/info` | `{"classes", "variants": [{"spec", "name"}], "verified": bool, "ohms": 60, "fabric": layout(), "sheet": bool}` |
  | `POST /api/run` `{"variant": V, "baseline": V or null, "classes": [..]}` | `{"variant": {"name", "hash"}, "baseline": {...} or null, "rows": [row], "regressions": [str]}` |
  | `GET /api/case?variant=<hash>&case=<name>` | `{"result": result, "paint": paint}`; 404 for an unknown hash or case |
  | `GET /api/watch?spec=S` | `{"hash": h}`: the tree's hash now |
  | `GET /api/sheet` | the overlay (Task 6), or 404 with `{"error", "hint"}` |
  `V` is a spec string or `{"base": spec, "files": {"src/...": "text"}}`. A `row` is a result without `b`, `xbar` and `stderr`, plus `fully_routed` and, with a baseline, `"base": {the same metrics}`. A variant that does not build answers 200 with `{"build_error": "<compiler output>", "variant": {"name"}}`. When `variants.build` raises "the sources changed", the server resolves and builds once more before answering.
- `GET /` serves `web/index.html` with `__LAB_TOKEN__` replaced by the token; other files only from `web/` and `build/sheet/backdrop.svg`.

- [ ] **Step 1: Write the failing tests** (each starts `make_server(0)` on a thread and uses `http.client`)

```python
class Server(unittest.TestCase):
    def test_binds_loopback_and_inlines_the_token(self):
        self.assertEqual(self.srv.server_address[0], "127.0.0.1")
        self.assertIn(self.srv.token, self.get("/", token=None).body)

    def test_api_needs_the_token_and_a_local_origin(self):
        self.assertEqual(self.get("/api/info", token=None).status, 403)
        self.assertEqual(self.get("/api/info", token="wrong").status, 403)
        self.assertEqual(self.get("/api/info", headers={"Origin": "http://evil.example"}).status, 403)
        self.assertEqual(self.get("/api/info", headers={"Host": "evil.example"}).status, 403)
        self.assertEqual(self.get("/api/info").status, 200)
        with mock.patch.object(variants, "build", side_effect=AssertionError("built for a stranger")):
            self.assertEqual(self.post("/api/run", {"variant": "worktree", "classes": ["dense"]}, token=None).status, 403)

    def test_static_files_stay_inside_web(self):
        for path in ("/../lab.py", "/%2e%2e/lab.py", "/web/../../lab.py", "/build/bin"):
            self.assertIn(self.get(path, token=None).status, (403, 404), path)

    def test_run_and_case(self):
        r = self.post("/api/run", {"variant": "worktree", "baseline": None, "classes": ["dense"]}).json
        self.assertEqual(len(r["rows"]), 21); self.assertNotIn("b", r["rows"][0]); self.assertIn("worst_r", r["rows"][0]["metrics"])
        c = self.get("/api/case?variant=%s&case=chain_all_chips" % r["variant"]["hash"]).json
        self.assertIn("Bridge Array", c["result"]["b"]); self.assertTrue(c["paint"]["crosspoints"])
        self.assertEqual(self.get("/api/case?variant=%s&case=nope" % r["variant"]["hash"]).status, 404)

    def test_baseline_rows_and_regressions(self):
        r = self.post("/api/run", {"variant": "worktree", "baseline": "HEAD", "classes": ["dense"]}).json
        self.assertEqual(r["regressions"], []); self.assertIn("base", r["rows"][0])

    def test_uploaded_file_makes_a_variant_and_a_broken_one_reports_the_compiler(self):
        bad = {"base": "worktree", "files": {"src/routing/NetsToChipConnections.cpp": "this is not C++\n"}}
        r = self.post("/api/run", {"variant": bad, "classes": ["dense"]})
        self.assertEqual(r.status, 200); self.assertIn("error", r.json["build_error"])
        self.assertEqual(self.post("/api/run", {"variant": {"base": "worktree", "files": {"../x": "y"}}, "classes": ["dense"]}).status, 400)
        self.assertEqual(self.post("/api/run", {"variant": {"base": "worktree", "files": {"src/a.h": "x" * 6_000_000}}, "classes": ["dense"]}).status, 413)

    def test_only_named_directories_are_variants(self):
        self.assertEqual(self.post("/api/run", {"variant": "/tmp", "classes": ["dense"]}).status, 400)
        with self.server(trees=[REPO]) as s:
            self.assertEqual(s.post("/api/run", {"variant": REPO, "classes": ["dense"]}).status, 200)

    def test_a_save_during_the_build_is_retried_once(self):
        real, calls = variants.build, []
        def flaky(v, sanitize=True):
            calls.append(v)
            if len(calls) == 1: raise variants.BuildError("the sources changed while the harness was building; run again")
            return real(v, sanitize)
        with mock.patch.object(variants, "build", side_effect=flaky):
            self.assertNotIn("build_error", self.post("/api/run", {"variant": "worktree", "classes": ["dense"]}).json)
        self.assertEqual(len(calls), 2)

    def test_watch_reports_the_tree_hash(self):
        self.assertEqual(self.get("/api/watch?spec=worktree").json["hash"], variants.resolve("worktree").hash)
```

- [ ] **Step 2: Run to see them fail.** Expected: `ModuleNotFoundError: server`.
- [ ] **Step 3: Implement `server.py` and `lab.py serve`.** Results are kept per variant hash in memory for `/api/case`; the runner's disk cache makes a restart cheap.
- [ ] **Step 4: Run all tests.** Expected: pass.
- [ ] **Step 5: Commit** `Routing lab: local server (token and origin checked) over the battery`.

---

### Task 4: The page: table, fabric view, case panel

**Files:**
- Create: `tools/routing_lab/web/lab.js`, `web/lab.css`; replace `web/index.html`
- Modify: `tests/test_server.py`

**What the page does** (one screen, three columns, as the design's sketch):
- **Left, top:** variant A (a text box with a list: `worktree`, each `--tree`, recent refs), optional baseline B, class checkboxes (default dense, real, stress), Run, ohms-per-crosspoint box (60). When `info.verified` is false, a plain line under it: "not verified against a board".
- **Left, below:** the battery table. One collapsible group per class with totals; one line per case: routed of primaries (refused shown apart), copies, crosspoints, worst ohms (signals) and worst rail ohms (rails and GND) in separate columns, dead taps, problem count. With a baseline, each number that differs is tinted better or worse and shows the baseline value on hover. Two filters: "not clean" and "changed". Clicking a case selects it.
- **Centre:** tabs Fabric and KiCad sheet (the second is Task 7). The fabric view draws `info.fabric`: chips as faint 16 by 8 grids, wires thin and dim, pads with labels. For the selected case, from its paint: a wire carrying a net takes the net's colour and its pad is filled with it; a closed crosspoint is a dot in its net's colour, hollow when the path is a duplicate; a wire carrying two nets is red and thick; a pin whose claim does not match the copper (claimed with no copper on a wire some net rides, or copper with no claim) gets a small red ring; an unrouted bridge's two pads get a dashed outline in its net's colour; a rejected, left-out or refused bridge's pads get a grey dashed outline. Wheel zooms, drag pans, double-click fits.
- **Hover** on a wire, pad or crosspoint: its name, kind, nets, and each pin's claim. **Click** a net anywhere (or in the list): that net stays lit and the rest dims; click again to release.
- **Right:** the case panel: name, class, status, the counts; the net list (colour swatch, label, nodes); the bridges (state, copies, hops, ohms); problems; notes; a "b report" disclosure with the raw text. For `crash` and `timeout`: the status and the stderr text in place of the lists.
- A build error replaces nothing: it shows in a bar above the table with the compiler's first error line and a disclosure for the rest.

**Interfaces:**
- Consumes: the Task 3 API. `window.LAB_TOKEN` from `index.html`; `window.LAB_STATIC` when present (Task 8) replaces every fetch.
- Produces in `lab.js`, for Tasks 5 and 7: `state` (info, runs by variant hash, selected case, isolated net), `api(path, body)`, `selectCase(name)`, `netColour(net)`, `drawFabric(paint)`, and one function per panel named `render<Panel>()`.

- [ ] **Step 1: Write the failing tests** in `tests/test_server.py`

```python
    def test_page_files_are_served_and_parse(self):
        for path, kind in (("/lab.js", "javascript"), ("/lab.css", "css")):
            r = self.get(path, token=None); self.assertEqual(r.status, 200); self.assertIn(kind, r.headers["Content-Type"])
        self.assertEqual(subprocess.run(["node", "--check", str(server.WEB_DIR / "lab.js")]).returncode, 0)
        page = self.get("/", token=None).body
        self.assertNotRegex(page, r'(src|href)="https?://')          # nothing from the network
        for anchor in ('id="battery"', 'id="fabric"', 'id="case"', 'id="build-error"'):
            self.assertIn(anchor, page)
```

- [ ] **Step 2: Run to see it fail.** Expected: 404 for `/lab.js`.
- [ ] **Step 3: Write the page.**
- [ ] **Step 4: Run the tests.** Expected: pass.
- [ ] **Step 5: Check it in the browser.** `lab.py serve --no-open`, open the URL in the built-in browser, run dense + real + stress on `worktree`, and confirm each of these, with a screenshot of the first four:
  1. `chain_all_chips`: one net across all eight chips, every lane it rides and its eight row pads in one colour, dots at its 14 crosspoints, and the probe feed's two in another colour.
  2. `stacked_taps_reachable`: hollow dots on duplicate paths; the bridges list shows copies above 1 and ohms below 120.
  3. `k_rows_overflow_metric`: the unrouted bridge's pads dashed in its net's colour.
  4. `fuzz_1_1` (run fuzz): a red ring on chip A's X0.
  5. A scratch case file under `cases/real/` with `GND-1, BOTTOM_RAIL-1` (deleted after the check): the left-out bridge's pads dashed grey, nothing red.
  6. Hover names the wire; clicking a net isolates it; wheel and drag work; the b report opens.
  7. Console shows no errors.
- [ ] **Step 6: Send Kevin the screenshots** (SendUserFile) with one line each, and carry on.
- [ ] **Step 7: Commit** `Routing lab: the page - battery table, fabric view, case panel`.

---

### Task 5: Variants in the page, live re-run, compare

**Files:**
- Modify: `tools/routing_lab/web/lab.js`, `web/lab.css`, `web/index.html`, `tools/routing_lab/server.py`, `tests/test_server.py`

**What it adds:**
- **Dropped files.** Dropping `.cpp`/`.h` files on the page asks, per file, which `src/` path it replaces (pre-filled from `GET /api/paths?name=<basename>`, which lists the tracked files under `src/` with that name), then runs the variant `{"base": A's spec, "files": {...}}`. The variant shows in the pickers as "worktree + 1 file".
- **Live.** A toggle beside A (only for `worktree` and `--tree` variants): the page asks `/api/watch` every 1.5 s and re-runs when the hash changes. A build error leaves the last good table on screen with the error bar above it; the next good build clears the bar.
- **Compare.** With a baseline run, a toggle in the fabric view draws the selected case three ways: copper both variants close in the net's colour, copper only A closes with a bright outline, copper only the baseline closes in dashed grey. The case panel's bridges list shows both variants' copies and ohms side by side.
- **Regressions list** above the table when a baseline is set: the server's `regressions` lines, each selecting its case.

**Interfaces:**
- Produces: `GET /api/paths?name=N` -> `{"paths": ["src/routing/N", ...]}` (from `git ls-files src`, exact basename match).

- [ ] **Step 1: Write the failing test**

```python
    def test_paths_lists_tracked_files_by_basename(self):
        self.assertEqual(self.get("/api/paths?name=NetsToChipConnections.cpp").json["paths"], ["src/routing/NetsToChipConnections.cpp"])
        self.assertEqual(self.get("/api/paths?name=nope.cpp").json["paths"], [])
        self.assertEqual(self.get("/api/paths?name=../../etc/passwd").json["paths"], [])
```
- [ ] **Step 2: Run to see it fail.** Expected: 404.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run all tests.** Expected: pass.
- [ ] **Step 5: Check it in the browser:**
  1. Live on, then save a harmless edit (a comment) to `src/routing/NetsToChipConnections.cpp` in the WORKTREE: the table re-runs within about five seconds and nothing changes. Undo the edit.
  2. Save a syntax error there: the error bar shows the compiler's line, the table stays. Undo: the bar clears. (`git diff --stat -- src` must be empty afterwards.)
  3. Baseline `a1accf5^`, variant `worktree`, class dense: `nano_dense_metric` is tinted better; compare mode shows the two hub-tier paths as A-only copper.
  4. Drop a copy of the router with `rescueViaHubs(startIndex);` commented out: the variant appears as "worktree + 1 file" and `nano_dense_metric` shows 11 of 13.
- [ ] **Step 6: Commit** `Routing lab page: dropped files, live re-run, compare against a baseline`.

---

### Task 6: The KiCad sheet's overlay and backdrop

**Files:**
- Create: `tools/routing_lab/sheet.py`, `tests/test_sheet.py`
- Modify: `tools/routing_lab/lab.py` (`sheet`), `tools/routing_lab/server.py` (`/api/sheet`, the backdrop file)

**Interfaces:**
- Produces:
  ```python
  DEFAULT_SCH: Path      # ~/Documents/GitHub/JumperlessV5/Jumperless23V50/MainBoard/JumperlessV5r7/JumperlessV5r7.kicad_sch
  def parse_sexpr(text: str) -> list                       # nested lists of str
  def pin_point(at: tuple[float, float, int], mirror: str | None, pin_at: tuple[float, float]) -> tuple[float, float]
  def overlay(sch_path: Path) -> dict
  def build(sch_path: Path = DEFAULT_SCH, theme: str | None = None) -> Path     # writes build/sheet/overlay.json and backdrop.svg
  class SheetUnavailable(Exception)                        # .hint: what is missing and what to run
  ```
  `overlay` returns, in sheet millimetres (the units of the `.kicad_sch` and of `kicad-cli`'s SVG):
  ```python
  {"size": [841.0, 594.0],
   "nets": {"/AB0": {"segments": [[x1, y1, x2, y2], ...], "labels": [[x, y], ...]}},   # keyed by fabric net name
   "pins": {"A.X2": [x, y], ...},          # all 288 crossbar pins, at the pin's wire end
   "bodies": {"A": [x0, y0, x1, y1]}}      # each crossbar symbol's rectangle
  ```
  How: a crossbar is a symbol whose `lib_id` ends in `CH446Q`; its chip letter is the first letter of its Reference (A2, B1, ... L1) and its pins are named X0..X15, Y0..Y7 in `lib_symbols`. A pin's sheet position is the symbol's `at` plus the pin's `at` rotated by the symbol's angle and mirrored, with the library's y axis pointing up. Wires that share an end point, or meet at a junction, are one group. A group's net is the fabric's name for any crossbar pin on it, else the text of a label on it (a local label `AB0` is the net `/AB0`). A label sits on a group when its point is on one of the group's segments. Only nets in `fabric_v5` are kept.
  `build` runs `kicad-cli sch export svg --exclude-drawing-sheet --pages 1 [--theme T]` and writes both files; it raises `SheetUnavailable` when `kicad-cli` or the schematic is missing. `lab.py sheet [SCH] [--theme T]` calls it and prints the paths. `GET /api/sheet` answers the overlay when built, else 404 with the hint `python3 tools/routing_lab/lab.py sheet`.

- [ ] **Step 1: Write the failing tests**

```python
MINI = '''(kicad_sch (paper "A4")
  (lib_symbols (symbol "X:CH446Q" (symbol "CH446Q_1_1"
    (rectangle (start -10 10) (end 10 -10))
    (pin bidirectional line (at 15 5 180) (length 5) (name "X0") (number "1"))
    (pin bidirectional line (at 15 -5 180) (length 5) (name "Y1") (number "2")))))
  (symbol (lib_id "X:CH446Q") (at 100 100 0) (property "Reference" "A2" (at 0 0 0)))
  (symbol (lib_id "X:CH446Q") (at 200 100 0) (mirror y) (property "Reference" "B1" (at 0 0 0)))
  (wire (pts (xy 115 95) (xy 150 95)))
  (wire (pts (xy 150 95) (xy 150 60)))
  (wire (pts (xy 185 95) (xy 150 95)))
  (junction (at 150 95))
  (label "AB0" (at 150 70 0))
  (wire (pts (xy 115 105) (xy 130 105)))
  (global_label "1" (at 130 105 0)))'''

class Sheet(unittest.TestCase):
    def test_sexpr(self):
        self.assertEqual(sheet.parse_sexpr('(a "b c" (d 1.5) e)'), ["a", "b c", ["d", "1.5"], "e"])

    def test_pin_point_rotations_and_mirror(self):
        self.assertEqual(sheet.pin_point((100, 100, 0), None, (15, 5)), (115, 95))       # library y is up
        self.assertEqual(sheet.pin_point((100, 100, 180), None, (15, 5)), (85, 105))
        self.assertEqual(sheet.pin_point((100, 100, 90), None, (15, 5)), (95, 85))
        self.assertEqual(sheet.pin_point((200, 100, 0), "y", (15, 5)), (185, 95))

    def test_overlay_of_a_small_sheet(self):
        with mock.patch.object(sheet.fabric_v5, "X_NET", {"A": ["/AB0"], "B": ["/AB0"]}), \
             mock.patch.object(sheet.fabric_v5, "Y_NET", {"A": ["x", "1"], "B": ["x", "8"]}), \
             mock.patch.object(sheet.fabric_v5, "CHIPS", "AB"):
            o = sheet.overlay(self.write(MINI))
        self.assertEqual(o["pins"]["A.X0"], [115, 95]); self.assertEqual(o["pins"]["B.X0"], [185, 95])
        self.assertEqual(len(o["nets"]["/AB0"]["segments"]), 3); self.assertEqual(o["nets"]["/AB0"]["labels"], [[150, 70]])
        self.assertEqual(o["nets"]["1"]["segments"], [[115, 105, 130, 105]])
        self.assertEqual(o["bodies"]["A"], [90, 90, 110, 110])

    @unittest.skipUnless(sheet.DEFAULT_SCH.exists(), "the r7 schematic is not on this machine")
    def test_the_real_sheet(self):
        o = sheet.overlay(sheet.DEFAULT_SCH)
        self.assertEqual(len(o["pins"]), 288); self.assertEqual(len(o["bodies"]), 12)
        lanes = [n for n in fabric_v5.LANES]
        self.assertEqual([n for n in lanes if n not in o["nets"]], [])                    # every lane has copper or a label on the sheet
        self.assertEqual([str(r) for r in range(1, 61) if str(r) not in o["nets"]], [])
        self.assertGreater(sum(len(n["segments"]) for n in o["nets"].values()), 300)
        # the pin transform is right on real data: nearly every crossbar pin ends on a wire end or a label
        ends = {(round(x, 2), round(y, 2)) for n in o["nets"].values()
                for s in n["segments"] for x, y in ((s[0], s[1]), (s[2], s[3]))}
        ends |= {(round(x, 2), round(y, 2)) for n in o["nets"].values() for x, y in n["labels"]}
        on_copper = sum(1 for x, y in o["pins"].values() if (round(x, 2), round(y, 2)) in ends)
        self.assertGreaterEqual(on_copper, 270)                 # 288 less the eight unconnected Y0 pins and a margin

    def test_missing_schematic_says_what_to_do(self):
        with self.assertRaises(sheet.SheetUnavailable) as cm: sheet.build(Path("/nonexistent.kicad_sch"))
        self.assertIn("lab.py sheet", cm.exception.hint)
```
In `tests/test_server.py`: `/api/sheet` is 404 with a `hint` when `build/sheet/overlay.json` is absent (patch the directory), and 200 with `pins` when present.

- [ ] **Step 2: Run to see them fail.** Expected: `ModuleNotFoundError: sheet`.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the tests, then `lab.py sheet`.** Expected: pass; `overlay.json` and `backdrop.svg` under `build/sheet/`. If `test_the_real_sheet` shows lanes with no copper and no label, read how that lane is drawn on the sheet before changing the rule.
- [ ] **Step 5: Commit** `Routing lab: KiCad sheet overlay (wires, labels, pins) and backdrop`.

---

### Task 7: The KiCad sheet tab

**Files:**
- Modify: `tools/routing_lab/web/lab.js`, `web/lab.css`, `web/index.html`

**What it does:** the sheet tab shows `backdrop.svg` as an image with an SVG overlay in the same millimetre coordinates. For the selected case's paint: each wire that carries a net has its sheet segments drawn over in the net's colour (thicker than KiCad's wire) and a small filled tag at each of its labels; a wire carrying two nets is red; each closed crosspoint is a curve inside the chip's body from its X pin to its Y pin in the net's colour (dashed for a duplicate); a mismatched claim is a red ring at the pin. Hover and net isolation behave as in the fabric view, and the isolated net is shared between the tabs. Wheel zooms, drag pans, double-click fits the two crossbar blocks. When `/api/sheet` is 404 the tab shows the hint and a note that the fabric view needs nothing.

- [ ] **Step 1: Write the failing test**: the page has `id="sheet"` and `lab.js` still passes `node --check`.
- [ ] **Step 2: Run to see it fail.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Check it in the browser:** `chain_all_chips` lights one drawn lane between each pair of neighbouring chips on the sheet's lower block and curves inside eight chip bodies; a case with a GPIO (`gpio_seven_from_chip_a`) lights label tags at the chip's L lane and on chip L; isolating a net in one tab holds in the other; with `build/sheet` moved aside the tab shows the hint. Screenshot the first two for Kevin.
- [ ] **Step 5: Commit** `Routing lab page: the KiCad sheet view`.

---

### Task 8: Export, clean, documents

**Files:**
- Create: `tools/routing_lab/export.py`, `tests/test_export.py`
- Modify: `tools/routing_lab/lab.py` (`export`, `clean`), `tools/routing_lab/README.md`, `CodeDocs/DESIGN_ROUTING_LAB.md` (status line)

**Interfaces:**
- Produces `export.write(path, variant_spec, baseline_spec=None, classes=("dense", "real", "stress", "beyond")) -> int` (bytes written): one HTML file holding `index.html` with `lab.css` and `lab.js` inlined and `window.LAB_STATIC = {"info", "run", "cases": {name: {"result", "paint"}}}`. The page, finding `LAB_STATIC`, reads from it, hides Run, Live, the pickers and the drop target, and says "exported <date> from <variant name>". The sheet backdrop is not included; the sheet tab says so.
- `lab.py export OUT.html [--variant V] [--baseline B] [--classes ...]`; `lab.py clean` removes `build/results`, `build/variants` and `build/bin` and prints what it freed.

- [ ] **Step 1: Write the failing tests**

```python
class Export(unittest.TestCase):
    def test_one_file_with_everything_inlined(self):
        out = self.tmp / "run.html"
        export.write(out, "worktree", classes=("dense",))
        html = out.read_text()
        self.assertNotRegex(html, r'<script[^>]+src=|<link[^>]+href=|https?://(?!www\.w3\.org)')
        data = json.loads(re.search(r"window\.LAB_STATIC = (\{.*?\});\n", html, re.S).group(1))
        self.assertEqual(len(data["run"]["rows"]), 21); self.assertIn("chain_all_chips", data["cases"])
        self.assertTrue(data["cases"]["chain_all_chips"]["paint"]["crosspoints"])
        self.assertNotIn("__LAB_TOKEN__", html); self.assertNotIn(str(Path.home()), html)     # no token, no home path

    def test_clean_empties_the_caches(self): ...        # patch BUILD_DIR to a temp tree; the three directories go, build/sheet stays
```
- [ ] **Step 2: Run to see them fail.**
- [ ] **Step 3: Implement.** A variant named by a directory is exported by its last path component only, so the file carries no home path.
- [ ] **Step 4: Run all tests; open an export from `file://` in the browser** and check the table, a case in the fabric view, and that no request leaves the page.
- [ ] **Step 5: Update the README** (the page, `serve`, `sheet`, `export`, `clean`; what the colours and marks mean) and the design's status line.
- [ ] **Step 6: Commit** `Routing lab: one-file export, cache clean-up, docs for the page`.

---

## After this plan

Kevin looks at the page with his own netlists and says what the views should show differently. Plan 3 (ceilings: missed paths, the global search, edge cases) draws its paths on these views.
