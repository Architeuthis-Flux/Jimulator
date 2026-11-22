// SPDX-License-Identifier: MIT
// Routing lab page. Python does the reckoning (server.py, copper.py,
// fabric_view.py); this file only asks and draws.
"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";
const STATIC = window.LAB_STATIC || null;   // an exported page carries its data and asks nothing
const GREY = "#8a90ad";

const state = {
  info: null,        // /api/info: classes, variants, arrangements; the fabric layout and node names of the arrangement picked
  arrangement: "v5", // the arrangement picked: the copper the Fabric tab draws and the next Run routes
  run: null,         // the last good /api/run answer; run.arrangement is what it was routed on
  cases: {},         // "variant hash/arrangement/case name" -> {result, paint}
  selected: null,    // case name
  current: null,     // {result, paint} of the selected case
  isolated: null,    // a net number lit alone, or null
  ohms: 42,          // ohms per crosspoint (the server says); resistance arrives in crosspoint units
  closed: {},        // class name -> collapsed in the table
  tab: "fabric",
  upload: {},        // dropped file name -> {path, text, choices}
  busy: false,       // a run is in flight
  liveTried: null,   // the last tree hash live mode ran, good build or not
  compare: false,    // draw the selected case against the baseline's routing of it
  base: null,        // {result, paint} of the selected case as the baseline routed it
  picking: 0,        // counts case selections, so a slow answer cannot overwrite a later click
  ghost: [],         // paths drawn dashed: [{net, hops: [{chip, x, y}]}]; the missed paths, or one bridge's spare copies
  spareOf: null,     // "n1-n2" of the bridge whose spare copies are the dashed paths, or null for the missed paths
  ceiling: newCeiling(null),   // what the exact solver said of the selected case
  ceilingSeconds: 20,          // the solver's time limit, as the box has it
  ranking: null,     // /api/rank's answer for the Router named and the arrangement picked, or null
  rankingFor: null,  // what the last ranking was asked for, so a slow answer cannot overwrite a later one
  rankNote: "",      // progress of "Rank now", or why there is no ranking
  rankBusy: false,   // a ranking is being made
  rankSort: { key: "loss", down: false },
  heat: "loss",      // what the Ranking tab tints the fabric by: "loss" (the router's) or "needed" (the solver's)
  takeAway: [],      // wires picked on the Ranking tab to run without
  v5nodes: null,     // V5's nodes, for the name of one the arrangement picked has dropped
  drawn: [],         // the netlist made by clicking nodes: [[node, node]]
  from: null,        // the node picked up by a first click, waiting for the second
};

// The solver's word on one case of one run: asked (busy) on the copper of the arrangement `on`, answered (answer,
// under rule, after `asked` seconds), drawn.
function newCeiling(run) {
  return { run: run, busy: false, rule: null, asked: 0, answer: null, draw: false, on: null };
}

const $ = (id) => document.getElementById(id);

function el(tag, attrs, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) node.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid != null) node.append(kid);
  return node;
}

function svg(tag, attrs, ...kids) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "text") node.textContent = v;
    else if (v != null) node.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid != null) node.append(kid);
  return node;
}

// ---------------------------------------------------------------- asking

async function api(path, body) {
  if (STATIC) return staticApi(path);
  const init = { headers: { "X-Lab-Token": window.LAB_TOKEN } };
  if (body !== undefined) {
    init.method = "POST";
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  let reply;
  try {
    reply = await fetch(path, init);
  } catch (e) {                                    // no answer at all: the server is not running
    throw new Error("The lab server is not answering. Start it again (lab.py serve), then reload this page.");
  }
  let data = {};
  try { data = await reply.json(); } catch (e) { /* an empty or non-JSON answer */ }
  if (!reply.ok) {
    // every start of the server makes a new token, and this page still holds the one it was served with
    const stale = reply.status === 403 && /token/.test(data.error || "");
    const err = new Error(stale ? "This page is from an earlier start of the lab server. Reload it."
      : data.error || ("the server answered " + reply.status));
    err.status = reply.status;
    err.data = data;
    throw err;
  }
  return data;
}

function staticApi(path) {
  const [pathname, query] = path.split("?");
  if (pathname === "/api/info") return STATIC.info;
  if (pathname === "/api/run") return STATIC.run;
  if (pathname === "/api/case") {
    const found = STATIC.cases[new URLSearchParams(query || "").get("case")];
    if (found) return found;
  }
  const err = new Error("not part of this exported page");
  err.status = 404;
  err.data = {};
  throw err;
}

// ---------------------------------------------------------------- small things

function netColour(net) {
  const nets = state.current && state.current.paint.nets;
  const known = nets && nets[String(net)];
  return known ? known.colour : GREY;
}

function netLabel(net) {
  const nets = state.current && state.current.paint.nets;
  const known = nets && nets[String(net)];
  return known ? known.label : String(net);
}

function nodeName(node) {                          // by the arrangement picked; a node it dropped keeps the name V5 gives it
  const known = state.info.nodes[String(node)] || (state.v5nodes || {})[String(node)];
  return known ? known.name : String(node);
}

// ---------------------------------------------------------------- arrangements
//
// An arrangement is the crossbar copper: V5's, or V5 with what a file under
// arrangements/ changes. The one picked is what the Fabric tab draws and what
// the next Run routes. A run remembers the one it was made on, and is drawn
// only while that one is picked: its copper on another's wires would be a lie.

const V5_ROW = { name: "v5", feed: true, engine: "router", why: null };

// The picked arrangement's row of the list: {name, about, feed, engine: "router" | "solver", why}.
function picked() {
  return (state.info.arrangements || []).find((a) => a.name === state.arrangement) || V5_ROW;
}

// What the shown run was routed on (an exported page from before arrangements says nothing: V5).
function ranOn() {
  return (state.run && state.run.arrangement) || V5_ROW;
}

// Who answered, on what, and whether the probe feed is on the fabric: said wherever a routing is shown.
function arrangementWords(a) {
  return "arrangement " + a.name + ", " + (a.engine === "solver" ? "the exact solver" : "the firmware's router")
    + ", probe feed " + (a.feed ? "on" : "off") + " the fabric";
}

// The picker and what hangs on it: whether Run can run, and the marks the drawing explains.
function renderArrangement() {
  const a = picked();
  const select = $("arrangement");
  select.replaceChildren();
  const broken = [];
  for (const row of state.info.arrangements || []) {
    const bad = Boolean(row.problems);
    if (bad) broken.push(row);
    select.append(el("option", { value: row.name, disabled: bad ? "" : null, title: bad ? row.problems.join("\n") : row.about,
      text: row.name + (bad ? "  (" + row.problems.length + " problems)"
        : "  (feed " + (row.feed ? "on" : "off") + (row.engine === "solver" ? ", solver only" : "")
          + (row.json ? ", not a file" : "") + ")") }));
  }
  select.value = state.arrangement;
  select.title = a.about || "";
  select.disabled = Boolean(STATIC);
  // an arrangement made here (one without some wires) is no file: the text of one, to save under arrangements/
  $("arrangement-json").hidden = !a.json;
  $("arrangement-json").querySelector("pre").textContent = a.json || "";
  $("arrangement-json").title = "save it as tools/routing_lab/arrangements/<a name>.json to keep it";
  // a file with a mistake: listed, greyed, its problems on hover; nothing else stops
  $("arrangement-bad").hidden = !broken.length;
  $("arrangement-bad").replaceChildren(...broken.map((row) => el("div", { title: row.problems.join("\n"),
    text: row.name + ".json has " + row.problems.length + (row.problems.length === 1 ? " problem" : " problems") + " (hover)" })));
  const cannot = a.engine !== "router";
  $("run").disabled = cannot || state.busy || Boolean(STATIC);
  $("run-why").hidden = !cannot;
  $("run-why").textContent = cannot ? "The firmware's router cannot route " + a.name + ": " + a.why
    + ". It routes V5 with pins taken away; the exact solver takes any arrangement." : "";
  const f = state.info.fabric;
  const taken = (f.taken || []).length;
  $("key-taken").hidden = !taken;
  $("key-changed").hidden = (f.changed || []).length === taken;
  $("sheet-note").textContent = "the sheet is V5's own; this arrangement is drawn on the Fabric tab";
  $("sheet-note").hidden = state.tab !== "sheet" || !(f.changed || []).length;
}

// Pick an arrangement: fetch its drawing and its nodes, draw it, and draw the shown case again if it is a run on it.
async function pickArrangement(name) {
  const data = await api("/api/fabric?arrangement=" + encodeURIComponent(name));
  state.arrangement = name;
  state.info.fabric = data.fabric;
  state.info.nodes = data.nodes;
  const rows = state.info.arrangements || [];                  // the file may have changed since the list was made
  const at = rows.findIndex((a) => a.name === name);
  if (at >= 0) rows[at] = data.arrangement;
  drawFabricBase();
  renderArrangement();
  if (state.ceiling.on && state.ceiling.on !== name) state.ceiling = newCeiling(state.run);    // it was asked on other copper
  state.takeAway = [];                             // wires picked on other copper
  if (state.current) {
    renderCase();
    redraw();
  } else $("view-title").textContent = name === "v5" ? "" : name + ": its copper";
  if (state.tab === "ranking") loadRanking();
}

// The solver's routing as the picture itself: when the arrangement picked is not the one the shown run was routed
// on (the firmware's router may not be able to route it at all) and the solver has routed the selected case on it.
function solvedShown() {
  const c = state.ceiling;
  return (state.run && ranOn().name !== state.arrangement && c.on === state.arrangement && c.answer && c.answer.solved) || null;
}

// The paint both views and the hover text are of: the solver's on the arrangement picked, else the run's when the
// run is on the arrangement picked, else none.
function shownPaint() {
  if (!state.current) return null;
  return solvedShown() || (ranOn().name === state.arrangement ? state.current.paint : null);
}

// a wire drawn red: two nets on it (a short), or a net on a node that is in no net (a stray)
function wrong(w) {
  return w.nets.length > 1 || Boolean(w.stray);
}

// a bridge the router owes: not routed, or listed as routed while its copper does not join
function failed(b) {
  return b.state === "unrouted" || b.state === "broken";
}

function count(n, word) {                          // "1 bridge", "2 bridges"
  return n + " " + word + (n === 1 ? "" : "s");
}

function ohmsText(r) {
  return r == null ? "" : String(Math.round(r * state.ohms));
}

function unclean(row) {
  return ["problems", "crash", "timeout"].includes(row.status) || (row.status !== "empty" && !row.fully_routed);
}

// ---------------------------------------------------------------- the battery table

// better: +1 when more is better, -1 when less is, 0 when a change is only a change
const COLUMNS = [
  { head: "routed", tip: "primaries routed, of those the firmware allowed", better: 1, get: (r) => r.metrics.routed_primaries,
    text: (r) => r.metrics.routed_primaries + "/" + (r.metrics.primaries - (r.metrics.refused || 0)) },
  { head: "copies", tip: "routed duplicate paths", better: 1, get: (r) => r.metrics.routed_duplicates },
  { head: "xp", tip: "closed crosspoints", better: 0, get: (r) => r.metrics.crosspoints },
  { head: "ohm", tip: "worst signal bridge, ohms", better: -1, get: (r) => r.metrics.worst_r, text: (r) => ohmsText(r.metrics.worst_r) },
  { head: "rail", tip: "worst bridge to GND or a rail, ohms", better: -1, get: (r) => r.metrics.rail_worst_r, text: (r) => ohmsText(r.metrics.rail_worst_r) },
  { head: "taps", tip: "scanned nodes with no sense-tap route", better: -1, get: (r) => r.metrics.taps_dead.length },
  { head: "miss", tip: "unrouted bridges the free copper could have carried", better: -1, get: (r) => r.metrics.missed || 0,
    text: (r) => (r.metrics.missed ? String(r.metrics.missed) : ""), cls: (r) => (r.metrics.missed ? "problem" : "") },
  { head: "prob", tip: "problems the judge found", better: -1, get: (r) => (["crash", "timeout"].includes(r.status) ? 1 : 0) + r.problems.length,
    text: (r) => (["crash", "timeout"].includes(r.status) ? r.status : (r.problems.length || "")),
    cls: (r) => (r.problems.length || ["crash", "timeout"].includes(r.status) ? "problem" : "") },
];

function changedFromBase(row) {
  if (!row.base) return false;
  return row.status !== row.base.status || COLUMNS.some((c) => c.get(row) !== c.get(row.base));
}

function cell(col, row) {
  const value = col.get(row);
  const td = el("td", { text: col.text ? col.text(row) : (value == null ? "" : String(value)) });
  if (col.cls && col.cls(row)) td.classList.add(col.cls(row));
  if (row.base) {
    const before = col.get(row.base);
    if (before !== value) {
      const sign = Math.sign((value == null ? Infinity : value) - (before == null ? Infinity : before)) * col.better;
      td.classList.add(sign > 0 ? "better" : sign < 0 ? "worse" : "changed");
      td.title = "baseline: " + (col.text ? col.text(row.base) : before);
    }
  }
  return td;
}

function classRow(name, rows) {
  const worst = (key) => {
    const values = rows.map((r) => r.metrics[key]).filter((v) => v != null);
    return values.length ? Math.max(...values) : null;
  };
  const sum = (f) => rows.reduce((total, r) => total + f(r), 0);
  const broken = rows.filter((r) => ["problems", "crash", "timeout"].includes(r.status)).length;
  const missed = sum((r) => r.metrics.missed || 0);
  const tr = el("tr", { class: "class" + (state.closed[name] ? " closed" : "") },
    el("td", { text: name + "  (" + rows.length + ")" }),
    el("td", { text: rows.filter((r) => r.fully_routed).length + "/" + rows.length, title: "cases fully routed" }),
    el("td", { text: String(sum((r) => r.metrics.routed_duplicates)) }),
    el("td", { text: String(sum((r) => r.metrics.crosspoints)) }),
    el("td", { text: ohmsText(worst("worst_r")) }),
    el("td", { text: ohmsText(worst("rail_worst_r")) }),
    el("td", { text: String(sum((r) => r.metrics.taps_dead.length)) }),
    el("td", { text: missed ? String(missed) : "", class: missed ? "problem" : "" }),
    el("td", { text: broken ? String(broken) : "", class: broken ? "problem" : "" }));
  tr.addEventListener("click", () => {
    state.closed[name] = !state.closed[name];
    renderBattery();
  });
  return tr;
}

const RUN_CHECKS = "Each case is a netlist. The firmware's own router, built for this computer, routes it, and the result "
  + "is judged against the schematic: no short, no stray, every bridge listed as routed really joined, chip-status "
  + "claims agreeing with the copper, sense taps reachable, and the same routes on a second rebuild. The dense cases "
  + "the bench suite requires must route; every other case is scored.";
const BOARD_CHECKS = "Read from a board's b report and judged against the schematic as a run is: shorts, strays, bridges "
  + "listed as routed that do not join, claims that disagree with the copper. Sense taps and the second-rebuild check "
  + "need the router and are not there.";

// One line over the table saying what it holds: which router ran which classes, or that it is a board's own output.
function renderShowing() {
  const box = $("showing");
  const run = state.run;
  box.hidden = !run;
  if (!run) return;
  if (run.board) {
    box.title = BOARD_CHECKS;
    box.replaceChildren(el("b", { text: "Shown: " }), "what a board printed (" + run.rows.length
      + (run.rows.length === 1 ? " report" : " reports") + "). Not a run of the router: press Run for that.");
    return;
  }
  if (run.drawn) {
    box.title = RUN_CHECKS;
    const elsewhere = ranOn().name !== state.arrangement;
    box.replaceChildren(el("b", { text: "Shown: " }), "a netlist made by hand, router " + run.variant.name + "; "
      + arrangementWords(ranOn())
      + (elsewhere ? ". That run only made the netlist: on " + state.arrangement + " it is the exact solver that routes it." : "."));
    return;
  }
  const classes = [];
  for (const row of run.rows) if (!classes.includes(row.cls)) classes.push(row.cls);
  box.title = RUN_CHECKS + classes.map((c) => "\n" + c + ": " + (((state.info.about || {})[c] || {}).what || "")).join("");
  box.replaceChildren(el("b", { text: "Shown: " }), "router " + run.variant.name + " on "
    + classes.map((c) => c + " (" + run.rows.filter((r) => r.cls === c).length + ")").join(", ") + ", "
    + run.rows.length + " cases, each routed and judged against the schematic; " + arrangementWords(ranOn())
    + (run.baseline ? "; compared with " + run.baseline.name : "") + ".");
}

function renderBattery() {
  const box = $("battery");
  box.replaceChildren();
  renderShowing();
  if (!state.run) return;
  const onlyUnclean = $("filter-unclean").checked;
  const onlyChanged = $("filter-changed").checked;
  const table = el("table", { class: "battery" },
    el("tr", {}, el("th", { text: "case" }), COLUMNS.map((c) => el("th", { text: c.head, title: c.tip }))));
  const classes = [];
  for (const row of state.run.rows) if (!classes.includes(row.cls)) classes.push(row.cls);
  for (const name of classes) {
    const rows = state.run.rows.filter((r) => r.cls === name);
    if (!(name in state.closed)) state.closed[name] = rows.length > 60;    // long classes start folded
    table.append(classRow(name, rows));
    if (state.closed[name]) continue;
    let listed = 0;
    for (const row of rows) {
      if (onlyUnclean && !unclean(row)) continue;
      if (onlyChanged && !changedFromBase(row)) continue;
      listed += 1;
      const tr = el("tr", { class: "case" + (row.case === state.selected ? " on" : ""), "data-case": row.case },
        el("td", { text: row.case, title: row.case }), COLUMNS.map((c) => cell(c, row)));
      tr.addEventListener("click", () => selectCase(row.case));
      table.append(tr);
    }
    if (!listed) {                                 // the filters hid every case: say so, an empty class reads as a fault
      const why = [onlyUnclean ? "not clean" : null, onlyChanged ? "changed from the baseline" : null].filter(Boolean);
      table.append(el("tr", { class: "note" }, el("td", { colspan: String(COLUMNS.length + 1),
        text: "none of the " + rows.length + " is " + why.join(" and ") + "; untick the filter to list them" })));
    }
  }
  box.append(table);
}

// ---------------------------------------------------------------- running

function baseSpec() {
  return $("variant").value.trim() || "worktree";
}

// What Run sends as the router: a name, or a name plus the dropped files that replace files in it.
function variantSpec() {
  const files = {};
  for (const f of Object.values(state.upload)) files[f.path] = f.text;
  return Object.keys(files).length ? { base: baseSpec(), files: files } : baseSpec();
}

// ---------------------------------------------------------------- dropped files

async function addUpload(name, text) {
  let choices = [];
  try { choices = (await api("/api/paths?name=" + encodeURIComponent(name))).paths; } catch (e) { /* offer a guess */ }
  state.upload[name] = { path: choices[0] || ("src/" + name), text: text, choices: choices };
  renderUploads();
}

function renderUploads() {
  const box = $("uploads");
  const names = Object.keys(state.upload);
  box.hidden = names.length === 0;
  box.replaceChildren();
  if (!names.length) return;
  box.append(el("div", { class: "hint", text: "Run uses these in place of the router's own files:" }));
  for (const name of names) {
    const f = state.upload[name];
    const path = el("input", { value: f.path, spellcheck: "false", title: "the file under src/ this replaces" });
    path.addEventListener("input", () => { f.path = path.value.trim(); });
    box.append(el("div", { class: "file" }, path,
      el("button", { type: "button", text: "x", title: "drop this file",
        onclick: () => { delete state.upload[name]; renderUploads(); } })));
    if (f.choices.length > 1) {
      box.append(el("div", { class: "hint", text: "also: " + f.choices.slice(1).join(", ") }));
    }
  }
}

function installDrop() {
  let depth = 0;
  window.addEventListener("dragenter", (event) => {
    event.preventDefault();
    depth += 1;
    document.body.classList.add("dropping");
  });
  window.addEventListener("dragleave", () => {
    depth -= 1;
    if (depth <= 0) document.body.classList.remove("dropping");
  });
  window.addEventListener("dragover", (event) => event.preventDefault());
  window.addEventListener("drop", async (event) => {
    event.preventDefault();
    depth = 0;
    document.body.classList.remove("dropping");
    // A file is board output (a `b` report), a crossbar dump that goes with one (same name before ".b.txt" /
    // ".xbar.txt", as a capture directory has them), or a source file to try in the router.
    const reports = {};
    const dumps = {};
    const sources = [];
    for (const file of event.dataTransfer.files) {
      const text = await file.text();
      const stem = file.name.replace(/\.(b|xbar)\.txt$|\.[^.]*$/, "");
      if (looksLikeBoard(text)) reports[stem] = text;
      else if (/xbar\{12x8:/.test(text)) dumps[stem] = text;
      else sources.push([file.name, text]);
    }
    const stems = Object.keys(reports);
    if (!stems.length) {
      for (const [name, text] of sources) await addUpload(name, text);
      return;
    }
    const only = stems.length === 1 ? Object.values(dumps)[0] : undefined;      // one report, one dump: they belong together
    await showBoards(stems.map((stem) => [stem, reports[stem] + "\n" + (dumps[stem] || only || "")]));
  });
}

// ---------------------------------------------------------------- live: re-run when the router's tree changes

function installLive() {
  setInterval(async () => {
    // a board's output on screen is not a run of the router: live leaves it alone until Run is pressed
    if (!$("live").checked || state.busy || !state.run || state.run.board || Object.keys(state.upload).length) return;
    let hash;
    try { hash = (await api("/api/watch?spec=" + encodeURIComponent(baseSpec()))).hash; } catch (e) { return; }
    if (state.busy || !state.run || state.run.board || !$("live").checked) return;      // things moved while the question was out
    if (hash === state.run.variant.hash) {
      // back at the tree the table shows (a broken edit undone): the error of the failed try is stale
      if (state.liveTried && state.liveTried !== hash) {
        $("build-error").hidden = true;
        state.liveTried = null;
      }
      return;
    }
    // one try per new hash: a tree that does not build is not rebuilt every tick
    if (hash !== state.liveTried) {
      state.liveTried = hash;
      if (state.run.drawn) await routeDrawn();      // the netlist made by hand is what is shown: route that again
      else await runBattery();
    }
  }, 1500);
}

function showBuildError(data) {
  const box = $("build-error");
  const text = String(data.build_error || "");
  // the compiler's first error, without the long build path in front of the file name
  const first = (text.split("\n").find((line) => line.includes("error")) || text.split("\n")[0] || "the build failed")
    .replace(/^\S*\/(?:fw_)?/, "");
  const what = data.which === "baseline" ? "The baseline" : data.which === "request" ? "The request" : "The router";
  box.replaceChildren(
    el("div", { text: what + (data.variant && data.variant.name ? " (" + data.variant.name + ")" : "") + " did not build: " + first }),
    el("details", {}, el("summary", { text: "compiler output" }), el("pre", { text: text })));
  box.hidden = false;
}

// Something went wrong that is not a build: the server is gone, a request was refused, an upload could not be read.
function showProblem(text) {
  $("build-error").replaceChildren(el("div", { text: text }));
  $("build-error").hidden = false;
}

function renderRegressions() {
  const box = $("regressions");
  const lines = (state.run && state.run.regressions) || [];
  box.hidden = !(state.run && state.run.baseline);
  if (box.hidden) return;
  box.replaceChildren(el("div", {
    text: lines.length ? lines.length + " worse than " + state.run.baseline.name + ":"
      : "nothing worse than " + state.run.baseline.name }));
  for (const line of lines) {
    box.append(el("a", { text: line, onclick: () => selectCase(line.split(":")[0]) }));
  }
}

// Run the ticked classes on the arrangement picked; with `without` (wire names), on that arrangement with those
// wires taken away as well, which then becomes the arrangement picked.
async function runBattery(without) {
  if (state.busy) return false;     // one run at a time: answers would otherwise land in the order they arrive
  if (picked().engine !== "router") return false;      // the firmware's router cannot route it: Run says why
  const classes = [...document.querySelectorAll("#classes input:checked")].map((box) => box.value);
  const body = { variant: variantSpec(), baseline: $("baseline").value.trim() || null, classes: classes,
    arrangement: state.arrangement, without: without || [] };
  $("busy").textContent = "running " + (classes.join(", ") || "no class") + " on " + baseSpec()
    + (Object.keys(state.upload).length ? " with the dropped files" : "") + (body.baseline ? " and on " + body.baseline : "")
    + (body.arrangement === "v5" ? "" : ", arrangement " + body.arrangement)
    + (body.without.length ? " without " + body.without.join(", ") : "") + "...";
  $("busy").hidden = false;
  state.busy = true;
  renderArrangement();
  try {
    // the arrangement's file may have been edited since it was picked: draw what is about to be routed
    if (body.arrangement !== "v5") await pickArrangement(body.arrangement);
    const data = await api("/api/run", body);
    if (data.build_error) {
      showBuildError(data);         // the last good table stays on screen
      return false;
    }
    $("build-error").hidden = true;
    state.run = data;
    state.cases = {};
    if (data.arrangement && data.arrangement.name !== state.arrangement) {
      // routed without some wires: that arrangement is no file, so it joins the list as it is, and is the one drawn
      state.current = null;
      state.takeAway = [];
      if (!state.info.arrangements.some((a) => a.name === data.arrangement.name)) state.info.arrangements.push(data.arrangement);
      await pickArrangement(data.arrangement.name);
    }
    $("compare-box").hidden = !data.baseline;
    if (!data.baseline) {
      state.compare = false;
      $("compare").checked = false;
    }
    renderRegressions();
    renderBattery();
    const names = data.rows.map((r) => r.case);
    const pick = names.includes(state.selected) ? state.selected
      : ((data.rows.find(unclean) || data.rows[0] || {}).case);
    if (pick) await selectCase(pick);
    return true;
  } catch (err) {
    showProblem(err.message + (err.data && err.data.problems ? ":\n" + err.data.problems.join("\n") : ""));
    return false;
  } finally {
    $("busy").hidden = true;
    state.busy = false;
    renderArrangement();
  }
}

// ---------------------------------------------------------------- a board's own output
//
// What a Jumperless prints for `b` (dropped as a file, or pasted) is judged by
// the server and shown as a run of its own, class "board": the table, the
// case panel and both views draw it as they draw anything the lab routed.

function looksLikeBoard(text) {
  return /Bridge Array/.test(text) && /Chip Status/.test(text);
}

// list: [[name, text]]. Every one is kept by the server; the last is the one selected.
async function showBoards(list) {
  if (!list.length) return;
  if (state.busy) {                                // the drop or paste is not kept: say so, do not swallow it
    showProblem("A run is in flight: drop or paste the board output again when it is done.");
    return;
  }
  state.busy = true;
  $("busy").textContent = "reading the board's output...";
  $("busy").hidden = false;
  renderArrangement();
  try {
    let data = null;
    for (const [name, text] of list) data = await api("/api/board", { name: name, text: text });
    if (state.arrangement !== "v5") await pickArrangement("v5");      // a board is V5: draw its output on V5's copper
    $("build-error").hidden = true;
    state.run = data;
    state.cases = {};
    state.compare = false;
    $("compare").checked = false;
    $("compare-box").hidden = true;
    state.closed.board = false;
    renderRegressions();
    renderBattery();
    await selectCase(data.shown);
  } catch (err) {
    showProblem(err.message);
  } finally {
    $("busy").hidden = true;
    state.busy = false;
    renderArrangement();
  }
}

const pastes = new Map();      // pasted text -> the name it was given, so the same paste again is the same case

function installPaste() {
  window.addEventListener("paste", (event) => {
    const text = event.clipboardData ? event.clipboardData.getData("text") : "";
    if (!looksLikeBoard(text)) return;             // anything else is pasted where it was going
    event.preventDefault();
    if (!pastes.has(text)) pastes.set(text, "pasted_" + (pastes.size + 1));
    showBoards([[pastes.get(text), text]]);
  });
}

// One case of the shown run as a variant routed it. Kept and asked for by the variant and the arrangement
// together: the same router on two arrangements is two runs.
async function caseOf(variant, name) {
  const arrangement = ranOn().name;
  const key = variant.hash + "/" + arrangement + "/" + name;
  if (!state.cases[key]) {
    state.cases[key] = await api("/api/case?variant=" + encodeURIComponent(variant.hash)
      + "&arrangement=" + encodeURIComponent(arrangement) + "&case=" + encodeURIComponent(name));
  }
  return state.cases[key];
}

async function selectCase(name) {
  if (!state.run) return;
  const run = state.run;
  const mine = ++state.picking;
  const current = await caseOf(run.variant, name);
  // with compare on, the same case as the baseline routed it
  const base = state.compare && run.baseline ? await caseOf(run.baseline, name) : null;
  if (run !== state.run || mine !== state.picking) return;     // a newer run or a newer click came first
  // the solver's answer stays while the same case of the same run is shown; its drawing gives way to a baseline's
  if (name !== state.selected || state.ceiling.run !== run) state.ceiling = newCeiling(run);
  else if (base) state.ceiling.draw = false;
  state.selected = name;
  state.current = current;
  state.base = base;
  state.isolated = null;
  showMissed();
  for (const tr of document.querySelectorAll("#battery tr.case")) {
    tr.classList.toggle("on", tr.dataset.case === name);
  }
  renderCase();
  renderDrawn();                                   // "start from the case shown" goes with what is shown
  redraw();
}

// Both views of the selected case. The fabric is drawn against a second routing of the same case when there is
// one: the solver's when that is asked for, else the baseline's.
function redraw() {
  if (state.tab === "ranking") {                   // that tab tints the copper by the ranking, with no case on it
    drawFabric(null);
    drawHeat();
    return;
  }
  const on = ranOn();
  if (on.name !== state.arrangement) {             // the run is on other copper than the drawing: draw none of it
    const solved = solvedShown();
    $("view-title").textContent = solved
      ? state.selected + "   the exact solver's routing on " + state.arrangement + ", one of many; not the firmware's router"
        + "   probe feed " + (on.feed ? "on" : "off") + " the fabric"
      : state.run.drawn         // the netlist made by hand, on copper only the solver routes, and no routing of it yet
        ? state.arrangement + ": its copper. The firmware made the netlist; routing it here is the exact solver's work"
          + (state.info.solver ? " (ask under Ceiling)." : ", and the solver is not installed: python3 tools/routing_lab/lab.py solver-setup")
        : state.arrangement + ": its copper. The run shown is on " + on.name + ": pick that arrangement to see it drawn"
          + (state.info.solver ? ", or ask the solver for this case on " + state.arrangement + " (Ceiling)." : ".");
    drawSheet(null);                               // the sheet is V5's own
    drawFabric(solved);
    return;
  }
  const solved = state.ceiling.draw && state.ceiling.answer && state.ceiling.answer.paint;
  const base = solved || (state.base && state.base.paint);
  $("view-title").textContent = state.selected + "   " + state.run.variant.name
    + (state.run.board ? "" : "   " + arrangementWords(on))
    + (solved ? "   against the solver's routing" : base ? "   against " + state.run.baseline.name : "");
  drawSheet(state.current.paint);
  drawFabric(state.current.paint, base, solved ? "the solver" : "the baseline");
}

// ---------------------------------------------------------------- the case panel

function isolate(net) {
  state.isolated = state.isolated === net ? null : net;
  applyIsolation();
}

function applyIsolation() {
  for (const view of document.querySelectorAll(".view svg")) {
    view.classList.toggle("isolating", state.isolated != null);
    for (const node of view.querySelectorAll("[data-net]")) {
      node.classList.toggle("iso", Number(node.dataset.net) === state.isolated);
    }
  }
  for (const row of document.querySelectorAll("#case .net")) {
    row.classList.toggle("on", Number(row.dataset.net) === state.isolated);
  }
}

const STATE_WORDS = { routed: "routed", unrouted: "NOT ROUTED", broken: "LISTED AS ROUTED, NOT CONNECTED",
                      refused: "refused by the safety check",
                      left_out: "left out of every net", rejected: "rejected" };
const SPARE_TIP = "available in copper, taking this bridge alone; the firmware holds some copper back for sense taps";

// What became of a bridge, in words. For one the router failed: whether the copper had a path for it.
function stateWords(b, paint) {
  if (!failed(b)) return STATE_WORDS[b.state];
  const m = (paint.missed || []).find((x) => x.n1 === b.n1 && x.n2 === b.n2 && x.net === b.net);
  if (!m || !m.path) return STATE_WORDS[b.state] + " - no free path in the copper as routed";
  return STATE_WORDS[b.state] + " - the copper had a path: "
    + (m.new === m.hops ? m.hops + " crosspoints" : m.new + " new, " + m.hops + " in all");
}

// The dashed paths are the case's missed paths, until a bridge's spare copies are asked for.
function showMissed() {
  state.spareOf = null;
  const missed = (state.current && state.current.paint.missed) || [];
  state.ghost = missed.filter((m) => m.path).map((m) => ({ net: m.net, hops: m.path }));
}

function toggleSpare(b) {
  const key = b.n1 + "-" + b.n2;
  if (state.spareOf === key) showMissed();
  else {
    state.spareOf = key;
    state.ghost = b.spare_paths.map((hops) => ({ net: b.net, hops: hops }));
  }
  for (const td of document.querySelectorAll("#case td.spare")) td.classList.toggle("on", td.dataset.bridge === state.spareOf);
  drawGhost();
  applyIsolation();
}

function renderCase() {
  const box = $("case");
  const result = state.current.result;
  const solved = solvedShown();                    // the solver's routing on the arrangement picked, when that is the picture
  const paint = solved || state.current.paint;
  const m = result.metrics;
  box.replaceChildren(el("h1", { text: result.case }));
  if (solved) {
    box.append(
      el("div", { class: "about", text: "the exact solver's routing on " + state.arrangement
        + ", one of many; not the firmware's router" }),
      el("div", { class: "counts", text: count(solved.crosspoints.length, "crosspoint") + " for "
        + count(solved.bridges.filter((b) => b.state === "routed").length, "bridge") + "; probe feed " + (ranOn().feed ? "on" : "off")
        + " the fabric. The netlist is the firmware's, from the run on " + ranOn().name + "." }));
  } else {
    box.append(el("div", {}, el("span", { class: "status " + result.status, text: result.status }),
      // what kind of case this is: a board's own routing, one the bench suite requires to route, or one that is scored
      el("span", { class: "hint", text: "  " + result.cls + " · "
        + (result.cls === "board" ? "as a board routed it" : result.must_route ? "must route" : "scored") })));
    if (result.about) box.append(el("div", { class: "about", text: result.about }));
    if (["crash", "timeout"].includes(result.status)) {
      box.append(el("h2", { text: "what the harness said" }),
        el("ul", { class: "problems" }, result.problems.map((p) => el("li", { text: p }))),
        el("pre", { class: "report", text: result.stderr || "(nothing on stderr)" }));
      return;
    }
    box.append(el("div", { class: "counts",
      text: m.routed_primaries + " of " + (m.primaries - (m.refused || 0)) + " primaries routed, "
        + m.routed_duplicates + " copies, " + m.crosspoints + " crosspoints"
        + (m.taps == null ? "" : ", " + (m.taps - m.taps_dead.length) + " of " + m.taps + " taps reachable")
        + (m.repeat_same === false ? ", ROUTES DIFFER ON A SECOND REBUILD" : "") }));
  }

  if (paint.problems.length) {
    box.append(el("h2", { text: "problems" }),
      el("ul", { class: "problems" }, paint.problems.map((p) => el("li", { text: p }))));
  }

  box.append(el("h2", { text: "bridges" }));
  const bridges = el("table", { class: "bridges" },
    el("tr", {}, ["bridge", "copies", "hops", "ohm"].map((h) => el("th", { text: h })),
      el("th", { text: "spare", title: SPARE_TIP })));
  // with compare on, the baseline's value follows in brackets where it differs
  const before = {};
  for (const b of (state.base && !solved ? state.base.paint.bridges : [])) before[b.n1 + "-" + b.n2] = b;
  const versus = (now, was) => (was === undefined || was === now || was === "" ? []
    : [el("span", { class: "was", text: " (" + (was === "" ? "-" : was) + ")" })]);
  for (const b of paint.bridges) {
    const routed = b.state === "routed";
    const old = before[b.n1 + "-" + b.n2];
    const oldRouted = old && old.state === "routed";
    const tr = el("tr", { class: routed ? "" : (failed(b) ? "unrouted" : "no") },
      el("td", {}, b.net == null ? null : el("span", { class: "swatch", style: "display:inline-block;margin-right:5px;background:" + netColour(b.net) }),
        nodeName(b.n1) + " - " + nodeName(b.n2) + (b.infra ? "  (probe feed)" : ""),
        routed ? null : el("div", { class: "state", text: stateWords(b, paint) }),
        old && old.state !== b.state ? el("div", { class: "state", text: "baseline: " + STATE_WORDS[old.state] }) : null),
      el("td", {}, routed ? String(b.copies) : "", versus(routed ? String(b.copies) : "", oldRouted ? String(old.copies) : undefined)),
      el("td", { text: routed ? String(b.hops) : "" }),
      el("td", {}, ohmsText(b.r), versus(ohmsText(b.r), oldRouted ? ohmsText(old.r) : undefined)),
      // copies the free copper still allows, and the ohms with them; a click draws them dashed
      b.spare ? el("td", { class: "spare" + (state.spareOf === b.n1 + "-" + b.n2 ? " on" : ""), "data-bridge": b.n1 + "-" + b.n2,
        title: SPARE_TIP, text: "+" + b.spare + " → " + ohmsText(b.r_spare),
        onclick: (event) => { event.stopPropagation(); toggleSpare(b); } }) : el("td", {}));
    if (b.net != null) tr.addEventListener("click", () => isolate(b.net));
    bridges.append(tr);
  }
  box.append(bridges);
  if (!STATIC) box.append(ceilingSection());       // an exported page cannot ask the solver

  box.append(el("h2", { text: "nets" }));
  for (const [net, info] of Object.entries(paint.nets)) {
    box.append(el("div", { class: "net", "data-net": net, onclick: () => isolate(Number(net)) },
      el("span", { class: "swatch", style: "background:" + info.colour }),
      el("span", { text: info.label + ":  " + info.nodes.map(nodeName).join(", ") })));
  }

  if (paint.notes.length) {
    box.append(el("h2", { text: "notes" }), el("ul", { class: "notes" }, paint.notes.map((n) => el("li", { text: n }))));
  }
  box.append(el("details", {}, el("summary", { text: solved ? "b report of the run on " + ranOn().name : "b report" }),
    el("pre", { text: result.b })));
  applyIsolation();
}

// ---------------------------------------------------------------- the ceiling: what the exact solver says of the case

const RULE_WORDS = { firmware: "firmware-shaped paths", copper: "any copper" };

async function askCeiling(rule) {
  const c = state.ceiling;
  if (c.busy || !c.run || !state.selected) return;
  const seconds = state.ceilingSeconds;
  const elsewhere = ranOn().name !== state.arrangement;      // asked on other copper than the run's: the answer is the picture
  const drawn = c.draw || Boolean(solvedShown());
  Object.assign(c, { busy: true, rule: rule, asked: seconds, answer: null, on: state.arrangement, draw: false });
  if (drawn) {                                     // the routing drawn belonged to the answer just dropped
    if (elsewhere) renderCase();
    redraw();
  }
  renderCeiling();
  let answer;
  try {
    // the netlist is the shown run's; the copper asked on is the arrangement picked
    answer = await api("/api/ceiling", { variant: c.run.variant.hash, run: ranOn().name, arrangement: state.arrangement,
      case: state.selected, rule: rule, seconds: seconds });
  } catch (err) {
    answer = { verdict: "unknown", error: err.message + (err.data && err.data.hint ? ": " + err.data.hint : "") };
  }
  c.busy = false;
  c.answer = answer;
  if (c !== state.ceiling) return;                 // another case or arrangement was picked while the solver worked
  if (elsewhere) {
    renderCase();
    redraw();
  } else renderCeiling();
}

function ceilingWords(c) {
  const a = c.answer;
  const shape = RULE_WORDS[c.rule];
  if (a.error) return [el("div", { class: "error", text: a.error })];
  if (a.verdict === "nothing") return [el("div", { text: "No bridge the firmware allowed" })];
  if (a.verdict === "unplaced") {                  // neither routable nor not: the copper has no such node
    const pairs = (a.unplaced || []).map((p) => p.map(nodeName).join("-")).join(", ");
    return [el("div", { text: "Cannot be placed on " + c.on + ": the netlist uses a node it does not have"
      + (pairs ? " (" + pairs + ")" : "") })];
  }
  if (a.verdict === "unknown") return [el("div", { text: "Not known after " + c.asked + " s (" + shape + ")" })];
  if (a.verdict === "not_routable") {
    return [el("div", { text: "Cannot be routed, proved (" + shape + ")" }),
      c.rule === "firmware" ? el("div", { class: "hint",
        text: "try any copper to see whether the limit is the path shape or the fabric" }) : null];
  }
  const fewest = el("div", { text: "Can be routed, proved (" + shape + "). Fewest crosspoints: "
    + (a.fewest_proved ? a.crosspoints + " (proved)" : "at most " + a.crosspoints + " (not proved in " + c.asked + " s)") });
  if (c.on !== ranOn().name) {                     // asked on other copper than the run's: the routing is the picture
    return [fewest, el("div", { class: "hint", text: "drawn: the exact solver's routing on " + c.on
      + ". The run's own routing is on " + ranOn().name + "." })];
  }
  const row = state.run.rows.find((r) => r.case === state.selected);
  const draw = el("input", { type: "checkbox", checked: c.draw ? "" : null });
  draw.addEventListener("change", () => {
    c.draw = draw.checked;
    if (c.draw && state.compare) {                 // one second routing at a time: the baseline's gives way
      state.compare = false;
      $("compare").checked = false;
      state.base = null;
      renderCase();
    }
    redraw();
  });
  return [
    fewest,
    el("div", { class: "hint", text: "the router's primaries use " + a.router_crosspoints
      + (row && row.fully_routed ? "" : ", for the bridges it routed") }),
    el("label", { class: "inline", title: "copper only the router closes is outlined; copper only the solver closes is dashed grey" },
      draw, " draw the solver's routing")];
}

function ceilingSection() {
  const c = state.ceiling;
  const box = el("div", { id: "ceiling" }, el("h2", { text: "ceiling" }));
  if (!state.info.solver) {
    box.append(el("div", { class: "hint", text: "Whether a netlist can be routed at all is asked of an exact solver. Install it once with:" }),
      el("pre", { text: "python3 tools/routing_lab/lab.py solver-setup" }),
      el("div", { class: "hint", text: "then reload this page." }));
    return box;
  }
  const seconds = el("input", { type: "number", min: "1", max: "120", step: "1", value: String(state.ceilingSeconds),
    title: "the solver's time limit, 1 to 120 s" });
  seconds.addEventListener("input", () => { state.ceilingSeconds = Math.min(120, Math.max(1, Number(seconds.value) || 20)); });
  const button = (rule, tip) => el("button", { type: "button", text: RULE_WORDS[rule], title: tip, disabled: c.busy ? "" : null,
    onclick: () => askCeiling(rule) });
  // who is asked, on what copper, with the feed where the run had it
  box.append(el("div", { class: "hint", text: "asked of the exact solver, on " + state.arrangement + ", probe feed "
    + (ranOn().feed ? "on" : "off") + " the fabric" + (ranOn().name === state.arrangement ? ""
      : " (the netlist is this run's, on " + ranOn().name + ")") }));
  box.append(el("div", { class: "ask" }, el("span", { class: "hint", text: "can it be routed with" }),
    button("firmware", "each bridge its own path of at most four crosspoints, as the firmware holds a path"),
    button("copper", "any way through the copper, of any length"),
    seconds, el("span", { class: "hint", text: "s" })));
  if (c.busy) box.append(el("div", { class: "hint", text: "asking the solver..." }));
  else if (c.answer) box.append(...ceilingWords(c).filter(Boolean));
  return box;
}

function renderCeiling() {
  const old = $("ceiling");
  if (old) old.replaceWith(ceilingSection());
}

// ---------------------------------------------------------------- pan, zoom, hover

const ZOOM_PER_PIXEL = 0.002;      // doublings of the zoom for one pixel of scrolling: the one number to tune the feel

// full: the box a double-click returns to; widest: how far out the wheel may go
function panZoom(view, full, widest = full[2] * 1.5) {
  let box = full.slice();
  const apply = () => view.setAttribute("viewBox", box.join(" "));
  const scale = () => {
    const r = view.getBoundingClientRect();
    return Math.max(box[2] / r.width, box[3] / r.height);       // user units per pixel ("meet")
  };
  const at = (event) => {
    const r = view.getBoundingClientRect();
    const k = scale();
    return [box[0] + box[2] / 2 + (event.clientX - r.left - r.width / 2) * k,
            box[1] + box[3] / 2 + (event.clientY - r.top - r.height / 2) * k];
  };
  // The wheel zooms about the pointer, as KiCad does, and by as much as was scrolled: a trackpad sends dozens of
  // small steps a second and a wheel a few big ones, and both must come out the same. A step is in pixels, lines
  // or pages (deltaMode); a pinch arrives as a wheel event with ctrl held, in much smaller steps.
  view.addEventListener("wheel", (event) => {
    event.preventDefault();
    const unit = event.deltaMode === 1 ? ZOOM_PER_PIXEL * 25 : event.deltaMode === 2 ? ZOOM_PER_PIXEL * 500 : ZOOM_PER_PIXEL;
    const wanted = Math.pow(2, event.deltaY * unit * (event.ctrlKey ? 10 : 1));
    const k = Math.min(widest / box[2], Math.max(full[2] / 60 / box[2], wanted));    // stop at the limits, do not stick
    const [x, y] = at(event);
    box = [x - (x - box[0]) * k, y - (y - box[1]) * k, box[2] * k, box[3] * k];
    apply();
  }, { passive: false });
  let drag = null;
  view.addEventListener("pointerdown", (event) => {
    drag = { x: event.clientX, y: event.clientY, box: box.slice(), moved: false };
  });
  window.addEventListener("pointermove", (event) => {
    if (!drag) return;
    const dx = event.clientX - drag.x;
    const dy = event.clientY - drag.y;
    if (!drag.moved && Math.hypot(dx, dy) < 4) return;
    drag.moved = true;
    view.classList.add("dragging");
    const k = scale();
    box = [drag.box[0] - dx * k, drag.box[1] - dy * k, box[2], box[3]];
    apply();
  });
  window.addEventListener("pointerup", () => {
    if (drag && drag.moved) view.dataset.dragged = "1";      // swallow the click that ends a drag
    drag = null;
    view.classList.remove("dragging");
  });
  view.addEventListener("click", (event) => {
    if (view.dataset.dragged) {
      delete view.dataset.dragged;
      event.stopPropagation();
    }
  }, true);
  view.addEventListener("dblclick", () => { box = full.slice(); apply(); });
  apply();
}

function hover(node, text) {
  node.addEventListener("pointermove", (event) => {
    const tip = $("tip");
    tip.textContent = typeof text === "function" ? text() : text;
    tip.hidden = false;
    const frame = $("centre").getBoundingClientRect();
    tip.style.left = Math.min(event.clientX - frame.left + 14, frame.width - 350) + "px";
    tip.style.top = (event.clientY - frame.top + 14) + "px";
  });
  node.addEventListener("pointerleave", () => { $("tip").hidden = true; });
}

function wireTip(name) {
  if (state.tab === "ranking") return rankTip(name);
  const paint = shownPaint();
  const w = paint && paint.wires[name];
  const kind = state.info.fabric.wires[name] ? state.info.fabric.wires[name].kind : "";
  if (!w) return name + "  (" + kind + ")";
  const riding = w.nets.length ? w.nets.map(netLabel).join(" and ") : "no net";
  const pins = w.pins.map((p) => "  " + p.chip + "." + p.axis + p.pin + "  "
    + (p.claim == null ? "free" : "claimed for " + netLabel(p.claim))
    + (p.mark === "mismatch" ? "   <- does not match the copper" : "")).join("\n");
  const fault = w.nets.length > 1 ? "   SHORT" : w.stray ? "   STRAY: this node is in no net" : "";
  return name + "  (" + w.kind + ")\ncarries: " + riding + fault + "\n" + pins;
}

// ---------------------------------------------------------------- the fabric view

const fabric = { wires: {}, pads: {}, dots: null, marks: null, ghost: null };

function pinPoint(chip, axis, pin) {
  const f = state.info.fabric;
  const c = f.chips[chip];
  return axis === "X" ? [c.x + f.cell / 2 + f.cell * pin, c.y] : [c.x, c.y + f.cell / 2 + f.cell * pin];
}

function cellCentre(chip, x, y) {
  const f = state.info.fabric;
  const c = f.chips[chip];
  return [c.x + f.cell / 2 + f.cell * x, c.y + f.cell / 2 + f.cell * y];
}

// The copper of the arrangement picked (state.info.fabric), with nothing routed on it. Drawn again whenever
// another arrangement is picked.
function drawFabricBase() {
  const f = state.info.fabric;
  fabric.wires = {};
  fabric.pads = {};
  const view = svg("svg", { id: "fabric-svg", preserveAspectRatio: "xMidYMid meet" });
  const chips = svg("g", { class: "chips" });
  for (const [name, c] of Object.entries(f.chips)) {
    chips.append(svg("g", { class: "chip" },
      svg("rect", { x: c.x, y: c.y, width: 16 * f.cell, height: 8 * f.cell }),
      svg("text", { x: c.x + 16 * f.cell + 6, y: c.y + 14, text: name })));
  }
  // What the arrangement changes, on the chip's edge where the pin is: a grey cross for a pin taken away, a thin
  // ring in the ink colour for a pin on another wire than V5 has it on. Neither is a fault, so neither is red.
  const pinMarks = svg("g", { class: "pin-marks" });
  const gone = new Set((f.taken || []).map((p) => p.chip + "." + p.axis + p.pin));
  for (const p of f.changed || []) {
    const [x, y] = pinPoint(p.chip, p.axis, p.pin);
    const pin = p.chip + "." + p.axis + p.pin;
    const mark = gone.has(pin)
      ? svg("path", { class: "pin-taken", d: "M" + (x - 3) + " " + (y - 3) + "l6 6m0 -6l-6 6" })
      : svg("circle", { class: "pin-changed", cx: x, cy: y, r: 4.2 });
    hover(mark, pin + (gone.has(pin) ? ": taken away in " : ": not on V5's wire in ") + state.arrangement);
    pinMarks.append(mark);
  }
  const wires = svg("g", { class: "wires" });
  const hits = svg("g", { class: "hits" });
  for (const [name, w] of Object.entries(f.wires)) {
    const path = svg("path", { class: "wire", d: w.d });
    const hit = svg("path", { class: "hit", d: w.d });
    hover(hit, () => wireTip(name));
    hit.addEventListener("click", () => {
      if (state.tab === "ranking") return toggleTakeAway(name);
      const paint = shownPaint();
      const live = paint && paint.wires[name];
      if (live && live.nets.length === 1) isolate(live.nets[0]);
    });
    wires.append(path);
    hits.append(hit);
    fabric.wires[name] = path;
  }
  const pads = svg("g", { class: "pads" });
  const above = Math.min(...Object.values(f.chips).map((c) => c.y));      // the upper row of chips: pads over it slant
  for (const [name, p] of Object.entries(f.pads)) {
    const text = p.side === "right" ? svg("text", { x: p.x + 8, y: p.y + 3, text: p.label })     // at a bus's end
      : p.y < above
      ? svg("text", { x: p.x + 3, y: p.y - 7, transform: "rotate(-60 " + (p.x + 3) + " " + (p.y - 7) + ")", text: p.label })
      : svg("text", { x: p.x, y: p.y + 13, "text-anchor": "middle", text: p.label });
    const g = svg("g", { class: "pad" }, svg("circle", { cx: p.x, cy: p.y, r: 3.6 }), text);
    hover(g, () => wireTip(name) + (STATIC || state.tab === "ranking" ? "" : "\nclick: connect this node to another"));
    g.addEventListener("click", () => clickNode(name));
    pads.append(g);
    fabric.pads[name] = g;
  }
  fabric.dots = svg("g", { class: "dots" });
  fabric.marks = svg("g", { class: "marks" });
  fabric.ghost = svg("g", { class: "ghosts" });
  // the pads lie over the wires' hit areas, so that a click on a node lands on the node and not on its wire
  view.append(chips, wires, fabric.ghost, fabric.dots, fabric.marks, hits, pads, pinMarks);
  $("fabric").replaceChildren(view);
  markFrom();
  panZoom(view, [0, 0, f.size[0], f.size[1]]);
}

// With a second routing of the same case (a baseline's paint, or the solver's):
// copper only this router closes is outlined, copper only the other closes is
// drawn dashed grey. `who` names the other in the hover text.
function drawCompare(paint, base, who) {
  const key = (c) => c.chip + "." + c.x + "." + c.y;
  const mine = new Set(paint.crosspoints.map(key));
  const theirs = new Set(base.crosspoints.map(key));
  for (const dot of fabric.dots.children) {
    if (!theirs.has(dot.dataset.key)) dot.classList.add("only-a");
  }
  for (const c of base.crosspoints) {
    if (mine.has(key(c))) continue;
    const [x, y] = cellCentre(c.chip, c.x, c.y);
    const ghost = svg("circle", { class: "xp only-b", cx: x, cy: y, r: 3.6 });
    hover(ghost, () => c.chip + "  x" + c.x + " y" + c.y + "\nclosed only by " + who);
    fabric.dots.append(ghost);
  }
  for (const [name, path] of Object.entries(fabric.wires)) {
    const a = paint.wires[name] && paint.wires[name].nets.length > 0;
    const b = base.wires[name] && base.wires[name].nets.length > 0;
    if (a && !b) path.classList.add("only-a");
    if (b && !a) path.classList.add("only-b");
  }
}

function drawFabric(paint, base, who) {
  for (const path of Object.values(fabric.wires)) {
    path.setAttribute("class", "wire");
    path.style.stroke = "";
    delete path.dataset.net;
  }
  for (const g of Object.values(fabric.pads)) {
    g.setAttribute("class", "pad");
    g.firstChild.style.fill = "";
    delete g.dataset.net;
    for (const ring of g.querySelectorAll(".want")) ring.remove();
  }
  fabric.dots.replaceChildren();
  fabric.marks.replaceChildren();
  markFrom();
  if (!paint) return;

  for (const [name, w] of Object.entries(paint.wires)) {
    const path = fabric.wires[name];
    if (!path) continue;
    const pad = fabric.pads[name];
    if (wrong(w)) {
      path.classList.add("live", "short");
      if (pad) pad.classList.add("live", "short");
    } else if (w.nets.length === 1) {
      path.classList.add("live");
      path.style.stroke = netColour(w.nets[0]);
      path.dataset.net = w.nets[0];
      if (pad) {
        pad.classList.add("live");
        pad.firstChild.style.fill = netColour(w.nets[0]);
        pad.dataset.net = w.nets[0];
      }
    }
    for (const pin of w.pins) {
      if (!pin.mark) continue;
      const [x, y] = pinPoint(pin.chip, pin.axis, pin.pin);
      if (pin.mark === "mismatch") {
        const ring = svg("circle", { class: "mismatch", cx: x, cy: y, r: 6 });
        hover(ring, () => wireTip(name));
        fabric.marks.append(ring);
      } else {                                   // held: claimed, but no net rides the wire
        fabric.marks.append(svg("rect", { class: "held", x: x - 2.5, y: y - 2.5, width: 5, height: 5,
          stroke: netColour(pin.claim), "data-net": pin.claim }));
      }
    }
  }

  for (const c of paint.crosspoints) {
    const [x, y] = cellCentre(c.chip, c.x, c.y);
    const colour = netColour(c.net);
    const dot = svg("circle", { class: "xp" + (c.dup ? " dup" : ""), cx: x, cy: y, r: 3.3, fill: colour,
      "data-net": c.net, "data-key": c.chip + "." + c.x + "." + c.y });
    if (c.dup) dot.style.stroke = colour;        // a duplicate path's crosspoint: a ring, not a dot
    hover(dot, () => c.chip + "  x" + c.x + " y" + c.y + "\nnet " + netLabel(c.net) + ", path " + c.path
      + (c.dup ? " (a duplicate)" : ""));
    dot.addEventListener("click", () => isolate(c.net));
    fabric.dots.append(dot);
  }

  for (const b of paint.bridges) {
    if (b.state === "routed") continue;
    for (const node of [b.n1, b.n2]) {
      const known = state.info.nodes[String(node)];
      const pad = known && fabric.pads[known.wire];
      if (!pad) continue;
      const centre = pad.firstChild;
      pad.append(svg("circle", { class: "want", cx: centre.getAttribute("cx"), cy: centre.getAttribute("cy"), r: 7,
        stroke: failed(b) ? netColour(b.net) : GREY }));
    }
  }
  if (base) drawCompare(paint, base, who);
  drawGhost();
  applyIsolation();
}

// ---------------------------------------------------------------- dashed paths: what the copper had, or still has

// state.ghost on both views, dashed in the net's colour and never red (the
// bridge's own row carries the red): hollow dots at the crosspoints that would
// be closed, the free wires between them, and on the sheet curves in the chips.
function drawGhost() {
  const paint = state.current && state.current.paint;
  fabric.ghost.replaceChildren();
  sheet.ghost.replaceChildren();
  if (sheet.live) sheet.live.append(sheet.ghost);
  if (!paint || ranOn().name !== state.arrangement) return;    // they are paths in the run's copper, not in this one's
  const wireAt = {};                                         // "A.X3" -> the name of the wire on that pin
  for (const [name, w] of Object.entries(paint.wires)) {
    for (const pin of w.pins) wireAt[pin.chip + "." + pin.axis + pin.pin] = name;
  }
  const what = state.spareOf ? "a copy the free copper still allows" : "a path the copper had for this bridge";
  for (const g of state.ghost) {
    const colour = netColour(g.net);
    const dashed = new Set();
    for (const h of g.hops) {
      if (h.new === false) continue;                         // already closed for this net: drawn as it is
      for (const pin of [h.chip + ".X" + h.x, h.chip + ".Y" + h.y]) {
        const name = wireAt[pin];
        const known = state.info.fabric.wires[name];
        if (!known || dashed.has(name) || paint.wires[name].nets.length) continue;      // lit copper is drawn already
        dashed.add(name);
        const path = svg("path", { class: "wire ghost", d: known.d, "data-net": g.net });
        path.style.stroke = colour;
        fabric.ghost.append(path);
      }
      const [x, y] = cellCentre(h.chip, h.x, h.y);
      const dot = svg("circle", { class: "xp ghost", cx: x, cy: y, r: 3.6, "data-net": g.net });
      dot.style.stroke = colour;
      hover(dot, () => h.chip + "  x" + h.x + " y" + h.y + "\nnet " + netLabel(g.net) + ": " + what);
      fabric.ghost.append(dot);
      const d = sheet.data && sheetCurve(h);
      if (d) sheet.ghost.append(svg("path", { class: "s-curve ghost", d: d, stroke: colour, "data-net": g.net }));
    }
  }
}

// ---------------------------------------------------------------- the KiCad sheet view
//
// The board's own schematic as the backdrop, and over it, in the sheet's
// millimetres: the wires and labels of each net-carrying piece of copper, and
// each closed crosspoint as a curve inside its chip from the X pin to the Y pin.

const sheet = { data: null, live: null, ghost: svg("g", {}) };

// A crosspoint on the sheet: a curve inside its chip from the X pin to the Y
// pin, bowed into the body, away from the side the pins leave it on.
function sheetCurve(c) {
  const s = sheet.data;
  const a = s.pins[c.chip + ".X" + c.x];
  const b = s.pins[c.chip + ".Y" + c.y];
  const body = s.bodies[c.chip];
  if (!a || !b || !body) return null;
  const width = body[2] - body[0];
  const deep = a[0] > (body[0] + body[2]) / 2 ? body[0] + width * 0.15 : body[2] - width * 0.15;
  return "M" + a[0] + " " + a[1] + "C" + deep + " " + a[1] + " " + deep + " " + b[1] + " " + b[0] + " " + b[1];
}

async function drawSheetBase() {
  let why = "The KiCad sheet is not part of an exported page.";
  if (!STATIC) {
    why = "The KiCad sheet has not been built. Build it once with:\n\n    python3 tools/routing_lab/lab.py sheet"
      + "\n\nand reload. The fabric view needs nothing.";
    if (state.info.sheet) {
      try { sheet.data = await api("/api/sheet"); } catch (err) { why = err.message; }
    }
  }
  if (!sheet.data) {
    $("sheet").replaceChildren(el("pre", { class: "hint", style: "padding:16px; white-space:pre-wrap", text: why }));
    return;
  }
  const s = sheet.data;
  const view = svg("svg", { id: "sheet-svg", preserveAspectRatio: "xMidYMid meet" });
  sheet.live = svg("g", {});
  view.append(svg("image", { href: "sheet/backdrop.svg", x: 0, y: 0, width: s.size[0], height: s.size[1],
    class: s.theme ? null : "light" }), sheet.live);
  $("sheet").replaceChildren(view);
  const bodies = Object.values(s.bodies);                    // a double-click fits the crossbar blocks
  const x0 = Math.min(...bodies.map((b) => b[0])) - 40;
  const y0 = Math.min(...bodies.map((b) => b[1])) - 30;
  const x1 = Math.max(...bodies.map((b) => b[2])) + 50;
  const y1 = Math.max(...bodies.map((b) => b[3])) + 20;
  panZoom(view, bodies.length ? [x0, y0, x1 - x0, y1 - y0] : [0, 0, s.size[0], s.size[1]], s.size[0] * 1.2);
}

function sheetDot(cls, [x, y], attrs) {                      // a dot that stays one size on screen
  return svg("path", Object.assign({ class: cls, d: "M" + x + " " + y + "l0.001 0" }, attrs));
}

function drawSheet(paint) {
  const s = sheet.data;
  if (!s) return;
  sheet.live.replaceChildren();
  if (!paint) return;
  const copper = svg("g", {});
  const curves = svg("g", {});
  const marks = svg("g", {});

  for (const [name, w] of Object.entries(paint.wires)) {
    const drawn = s.nets[name] || { segments: [], labels: [] };
    if (w.nets.length) {
      const short = wrong(w);
      const look = short ? {} : { stroke: netColour(w.nets[0]), "data-net": w.nets[0] };
      const parts = drawn.segments.map(([ax, ay, bx, by]) => svg("path",
        Object.assign({ class: "s-wire" + (short ? " short" : ""), d: "M" + ax + " " + ay + "L" + bx + " " + by }, look)));
      const points = new Map();                              // labels and pin ends, once each
      for (const p of drawn.labels) points.set(p.join(","), p);
      for (const pin of w.pins) {
        const p = s.pins[pin.chip + "." + pin.axis + pin.pin];
        if (p) points.set(p.join(","), p);
      }
      for (const p of points.values()) parts.push(sheetDot("s-tag" + (short ? " short" : ""), p, look));
      for (const part of parts) {
        hover(part, () => wireTip(name));
        if (!short) part.addEventListener("click", () => isolate(w.nets[0]));
        copper.append(part);
      }
    }
    for (const pin of w.pins) {
      const p = pin.mark && s.pins[pin.chip + "." + pin.axis + pin.pin];
      if (!p) continue;
      if (pin.mark === "mismatch") {
        const ring = svg("circle", { class: "s-ring", cx: p[0], cy: p[1], r: 2.2 });
        hover(ring, () => wireTip(name));
        marks.append(ring);
      } else {                                               // held: claimed, but no net rides the wire
        marks.append(svg("rect", { class: "s-held", x: p[0] - 0.9, y: p[1] - 0.9, width: 1.8, height: 1.8,
          stroke: netColour(pin.claim), "data-net": pin.claim }));
      }
    }
  }

  for (const c of paint.crosspoints) {
    const d = sheetCurve(c);
    if (!d) continue;
    const curve = svg("path", { class: "s-curve" + (c.dup ? " dup" : ""), stroke: netColour(c.net), "data-net": c.net, d: d });
    hover(curve, () => c.chip + "  x" + c.x + " y" + c.y + "\nnet " + netLabel(c.net) + ", path " + c.path
      + (c.dup ? " (a duplicate)" : ""));
    curve.addEventListener("click", () => isolate(c.net));
    curves.append(curve);
  }

  for (const b of paint.bridges) {                           // what was asked for and is not there
    if (b.state === "routed") continue;
    for (const node of [b.n1, b.n2]) {
      const known = state.info.nodes[String(node)];
      if (!known) continue;
      // at the wire's labels; a wire drawn without one (GND, the current sense) at its crossbar pins
      let points = s.nets[known.wire] ? s.nets[known.wire].labels : [];
      if (!points.length && paint.wires[known.wire]) {
        points = paint.wires[known.wire].pins.map((pin) => s.pins[pin.chip + "." + pin.axis + pin.pin]).filter(Boolean);
      }
      for (const p of points) {
        marks.append(svg("circle", { class: "s-want", cx: p[0], cy: p[1], r: 2.4,
          stroke: failed(b) ? netColour(b.net) : GREY }));
      }
    }
  }
  sheet.live.append(curves, copper, marks);
  drawGhost();
}

// ---------------------------------------------------------------- a netlist made by clicking nodes
//
// A click on a node picks it up; a click on a second makes a bridge between
// the two, added to what is on screen: to the bridges of the case shown, or
// to nothing when no case is. The netlist so made (state.drawn) is routed at
// once, with the Router named, on the arrangement picked, and its result is
// shown as a run of one case, "drawn". On an arrangement only the solver can
// route, the firmware still makes the netlist (on V5's copper) and the solver
// routes it.

// The bridges of the case shown, as a netlist to add to: its own pairs, each once, without the probe feed's (the
// firmware makes that itself). Stacking and power are not a case's bridges and are not carried: they are the default.
function shownBridges() {
  const seen = new Set();
  const once = ([a, b]) => !seen.has(Math.min(a, b) + "-" + Math.max(a, b)) && seen.add(Math.min(a, b) + "-" + Math.max(a, b));
  return state.current.paint.bridges.filter((b) => !b.infra).map((b) => [b.n1, b.n2]).filter(once);
}

// The node on a wire, for a click on its pad: the lowest-numbered one when the copper has several names.
function nodeOn(wire) {
  let found = null;
  for (const [node, info] of Object.entries(state.info.nodes)) {
    if (info.wire === wire && (found == null || Number(node) < found)) found = Number(node);
  }
  return found;
}

function markFrom() {
  const held = state.from == null ? null : (state.info.nodes[String(state.from)] || {}).wire;
  for (const [wire, g] of Object.entries(fabric.pads)) g.classList.toggle("from", wire === held);
}

function clickNode(wire) {
  if (STATIC || state.tab === "ranking") return;
  const node = nodeOn(wire);
  if (node == null) return;                        // copper with no node on it
  if (state.from == null || state.from === node) {
    state.from = state.from == null ? node : null; // picked up, or let go of
    markFrom();
    renderDrawn();
    return;
  }
  const pair = [state.from, node];
  state.from = null;
  markFrom();
  if (state.busy) {                                // nothing is added that would not be routed
    renderDrawn();
    showProblem("A run is in flight: click the two nodes again when it is done.");
    return;
  }
  // on to what is on screen: the first bridge made while a case of a run is shown starts from that case's own
  if (!state.drawn.length && state.current && !(state.run && state.run.drawn)) state.drawn = shownBridges();
  const same = ([a, b]) => (a === pair[0] && b === pair[1]) || (a === pair[1] && b === pair[0]);
  if (!state.drawn.some(same)) state.drawn.push(pair);      // the firmware would merge the same pair twice
  routeDrawn(pair);
}

// Route state.drawn on the arrangement picked and show it. `added`: the bridge just put in, taken out again if
// the netlist is refused with it.
async function routeDrawn(added) {
  renderDrawn();
  if (!state.drawn.length) {                       // the last bridge was taken out: nothing made by hand is shown any more
    if (state.run && state.run.drawn) {
      Object.assign(state, { run: null, current: null, selected: null, base: null, cases: {} });
      renderRegressions();
      renderBattery();
      $("case").replaceChildren(el("p", { class: "hint", text: "Run a battery, then pick a case." }));
      $("view-title").textContent = "";
      drawSheet(null);
      drawFabric(null);
    }
    return;
  }
  if (state.busy) {
    showProblem("A run is in flight: change the netlist made by hand again when it is done, and it is routed.");
    return;
  }
  state.busy = true;
  $("busy").textContent = "routing " + count(state.drawn.length, "bridge") + " made by hand on " + state.arrangement + "...";
  $("busy").hidden = false;
  renderArrangement();
  try {
    const data = await api("/api/route", { variant: variantSpec(), arrangement: state.arrangement, bridges: state.drawn });
    if (data.build_error) {
      showBuildError(data);
      return;
    }
    $("build-error").hidden = true;
    state.run = data;
    state.cases = {};
    state.compare = false;
    $("compare").checked = false;
    $("compare-box").hidden = true;
    state.closed.drawn = false;
    renderRegressions();
    renderBattery();
    await selectCase("drawn");
    // copper the firmware's router cannot route: the run only made the netlist. The solver routes it, and that is the picture.
    if (ranOn().name !== state.arrangement && state.info.solver) await askCeiling("firmware");
  } catch (err) {
    if (added) state.drawn = state.drawn.filter((pair) => pair !== added);
    showProblem(err.message);
  } finally {
    $("busy").hidden = true;
    state.busy = false;
    renderArrangement();
    renderDrawn();
  }
}

// The box under the controls: what the netlist holds, with a way to take each bridge out, to clear it, and to
// start it from the bridges of the case shown.
function renderDrawn() {
  const box = $("drawn");
  box.hidden = Boolean(STATIC);
  if (STATIC) return;
  box.replaceChildren();
  const shown = state.current && !(state.run && state.run.drawn);
  const from = el("button", { type: "button", text: "start from the case shown", disabled: shown ? null : "",
    title: "make the netlist the bridges of the case shown, to take some out or add to them. Its stacking and power "
      + "settings are not bridges and are not kept: the netlist is routed with the defaults.",
    onclick: () => { state.drawn = shownBridges(); routeDrawn(); } });
  if (!state.drawn.length) {
    box.append(el("div", { class: "hint", text: state.from == null
      ? "Click two nodes on the Fabric tab to connect them" + (shown ? ": the bridge is added to the case shown" : "")
        + ". The netlist is routed at once, on the arrangement picked."
      : "From " + nodeName(state.from) + ": click another node to connect it (Esc lets go)." }), from);
    return;
  }
  box.append(el("div", { class: "hint", text: "Made by hand (" + count(state.drawn.length, "bridge") + "), routed on the arrangement picked"
    + (state.from == null ? ". Click two nodes to add one." : ". From " + nodeName(state.from) + ": click another node (Esc lets go).") }));
  const list = el("div", { class: "away" });
  for (const pair of state.drawn) {
    list.append(el("span", { text: nodeName(pair[0]) + " - " + nodeName(pair[1]) + " ×", title: "take this bridge out",
      onclick: () => { state.drawn = state.drawn.filter((p) => p !== pair); routeDrawn(); } }));
  }
  box.append(list, el("div", { class: "row" },
    el("button", { type: "button", text: "clear", onclick: () => { state.drawn = []; routeDrawn(); } }), from));
}

// ---------------------------------------------------------------- the ranking tab
//
// What `lab.py rank` wrote for the Router named and the arrangement picked:
// for each lane, bounce row and hub lane, what the firmware's router loses
// without it (signed: it sometimes routes more) and, when the solver was
// asked, how many netlists are proved to need it. The fabric is tinted by one
// of the two, dim through teal to yellow and never red. A click on a wire, in
// the drawing or the table, picks it to take away.

const HEAT = ["#2f3347", "#4db6ac", "#fff176"];    // nothing, half, the most
const GAIN = "#9ab4ff";                            // a wire the router routes more without
const RANK_COLUMNS = [
  { key: "kind", head: "kind", tip: "lane: between two breadboard chips. sf lane: a breadboard chip to an SF chip. bounce: a chip's bounce row. hub: between two SF chips", of: (w) => w.kind },
  { key: "wire", head: "wire", tip: "a bounce row has no name of its own on the sheet: it is shown by its chip and pin", of: (w) => w.wire,
    show: (w) => (w.kind === "bounce" ? "chip " + w.pins[0][0] + " Y" + w.pins[0][2] : w.wire) },
  { key: "used", head: "used", tip: "cases in which the router puts a net on it. This follows the router's search order and says nothing of need", of: (w) => w.usage.cases },
  { key: "loss", head: "loss", tip: "primaries the firmware's router routes with every wire, minus what it routes without this one. Negative: it does better without", of: (w) => w.loss.primaries, signed: true },
  { key: "cases", head: "cases", tip: "cases fully routed with every wire, minus without this one", of: (w) => w.loss.fully_routed, signed: true },
  { key: "needed", head: "needed by", tip: "netlists the exact solver proves cannot be routed without the wire (firmware-shaped paths)", of: (w) => (w.needed_by ? w.needed_by.length : null), list: "needed_by" },
  { key: "free", head: "not needed", tip: "netlists with a routing that does without the wire", of: (w) => (w.needed_by ? w.not_needed : null) },
  { key: "unknown", head: "unknown", tip: "netlists for which neither was found in the solver's time", of: (w) => (w.unknown ? w.unknown.length : null), list: "unknown" },
];

function heatColour(t) {                           // 0 to 1 along HEAT
  const rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const [from, to] = t < 0.5 ? [rgb(HEAT[0]), rgb(HEAT[1])] : [rgb(HEAT[1]), rgb(HEAT[2])];
  const part = t < 0.5 ? t * 2 : t * 2 - 1;
  return "rgb(" + from.map((v, i) => Math.round(v + (to[i] - v) * part)).join(",") + ")";
}

function hasNeeded() {
  return Boolean(state.ranking && state.ranking.needed_cases != null);
}

// The number a wire is tinted by: the netlists proved to need it, or the router's loss (a gain tints as nothing lost).
function heatValue(w) {
  return state.heat === "needed" && hasNeeded() ? (w.needed_by ? w.needed_by.length : 0) : Math.max(0, w.loss.primaries);
}

function drawHeat() {
  for (const path of Object.values(fabric.wires)) {
    if (path.classList.contains("heat")) path.style.stroke = "";
    path.classList.remove("heat", "take");
  }
  if (state.tab !== "ranking") return;
  const r = state.ranking;
  $("view-title").textContent = !r ? state.arrangement + ": not ranked yet"
    : "tinted by " + (state.heat === "needed" && hasNeeded() ? "the netlists proved to need each wire (the exact solver)"
      : "the primaries the firmware's router loses without each wire") + "   arrangement " + r.arrangement
      + ", probe feed " + (r.feed ? "on" : "off") + " the fabric";
  if (!r) return;
  const byLoss = !(state.heat === "needed" && hasNeeded());
  if (byLoss && r.wires.some((w) => w.loss.primaries < 0)) $("view-title").textContent += "   blue: the router routes more without it";
  const most = Math.max(1, ...r.wires.map(heatValue));
  for (const w of r.wires) {
    const path = fabric.wires[w.wire];
    if (!path) continue;
    path.classList.add("heat");
    path.classList.toggle("take", state.takeAway.includes(w.wire));
    // a gain is not "nothing lost": it has a colour of its own (the page's blue for a change; never red)
    path.style.stroke = byLoss && w.loss.primaries < 0 ? GAIN : heatColour(heatValue(w) / most);
  }
}

function rankTip(name) {
  const w = state.ranking && state.ranking.wires.find((x) => x.wire === name);
  if (!w) return name + "\nnot ranked: a node's own wire, or no ranking is shown";
  const sign = (n) => (n > 0 ? "+" + n : String(n));       // a loss, as the table has it: positive is worse without the wire
  return name + "  (" + w.kind + ")\nthe router's loss without it: " + sign(w.loss.primaries) + " primaries, " + sign(w.loss.fully_routed)
    + " cases fully routed" + (w.loss.primaries < 0 ? "  (the router routes more without it)" : "")
    + "\nused in " + w.usage.cases + " cases"
    + (w.needed_by ? "\nproved needed by " + w.needed_by.length + (w.needed_by.length ? " (" + w.needed_by.slice(0, 4).join(", ")
      + (w.needed_by.length > 4 ? ", ..." : "") + ")" : "") + ", not needed by " + w.not_needed + ", unknown for " + w.unknown.length : "")
    + "\nclick: " + (state.takeAway.includes(name) ? "keep it" : "take it away");
}

function toggleTakeAway(name) {
  if (!state.ranking || !state.ranking.wires.some((w) => w.wire === name)) return;      // only a wire that is ranked
  const at = state.takeAway.indexOf(name);
  if (at >= 0) state.takeAway.splice(at, 1);
  else state.takeAway.push(name);
  renderRanking();
  drawHeat();
}

// The ranking on file for the Router named and the arrangement picked, or none (and how to make one).
async function loadRanking() {
  const wanted = baseSpec() + "\n" + state.arrangement;
  state.rankingFor = wanted;
  let found = null;
  let note = "";
  try {
    found = await api("/api/rank?variant=" + encodeURIComponent(baseSpec()) + "&arrangement=" + encodeURIComponent(state.arrangement));
  } catch (err) {
    note = err.status === 404 && err.data && err.data.hint ? "" : err.message;
  }
  if (state.rankingFor !== wanted) return;         // another arrangement was picked while this was asked
  state.ranking = found;
  state.rankNote = note;
  renderRanking();
  drawHeat();
}

// Make the router's part now. It takes minutes; /api/job says how far it is.
async function rankNow() {
  if (state.rankBusy) return;
  state.rankBusy = true;
  state.rankNote = "ranking: starting...";
  renderRanking();
  const watch = setInterval(async () => {
    try {
      const job = await api("/api/job");
      if (job.what && state.rankBusy) {
        state.rankNote = "ranking: " + job.done + " of " + job.of + (job.wire ? " (" + job.wire + ")" : "");
        renderRanking();
      }
    } catch (e) { /* the answer to the ranking itself will say */ }
  }, 1000);
  const classes = [...document.querySelectorAll("#classes input:checked")].map((box) => box.value);
  const wanted = baseSpec() + "\n" + state.arrangement;
  state.rankingFor = wanted;
  try {
    const made = await api("/api/rank", { variant: baseSpec(), arrangement: state.arrangement, classes: classes });
    if (made.build_error) throw new Error("the router did not build");
    if (state.rankingFor === wanted) state.ranking = made;    // else another arrangement was picked meanwhile: its own is shown
    state.rankNote = "";
  } catch (err) {
    state.rankNote = err.message;
  } finally {
    clearInterval(watch);
    state.rankBusy = false;
    renderRanking();
    drawHeat();
  }
}

function renderRanking() {
  const box = $("ranking");
  const r = state.ranking;
  const a = picked();
  box.replaceChildren(el("h1", { text: "Ranking" }));
  box.append(el("div", { class: "hint", text: "Which lanes, bounce rows and hub lanes could a board do without. Two different "
    + "answers: what the firmware's router loses without the wire, and whether any netlist is proved to need it." }));
  if (r) {
    box.append(el("div", { text: "router " + r.variant.name + ", arrangement " + r.arrangement + ", probe feed "
      + (r.feed ? "on" : "off") + " the fabric: the firmware's router over " + r.cases + " cases"
      + (hasNeeded() ? "; the exact solver (firmware-shaped paths, " + r.seconds + " s a question) over " + r.needed_cases + " netlists" : "")
      + ". Made " + r.made + "." }));
  } else {
    box.append(el("div", { text: "No ranking of router " + baseSpec() + " on " + state.arrangement + " yet." }));
  }
  const cannot = a.engine !== "router";
  const now = el("button", { type: "button", text: "Rank now", disabled: state.rankBusy || cannot ? "" : null,
    title: cannot ? "the firmware's router cannot route this arrangement" : "the router's part: the ticked classes without each wire in turn, a few minutes",
    onclick: rankNow });
  const tint = el("select", { title: "what the fabric is tinted by" },
    el("option", { value: "loss", text: "tint: router's loss" }),
    hasNeeded() ? el("option", { value: "needed", text: "tint: needed by" }) : null);
  tint.value = state.heat === "needed" && hasNeeded() ? "needed" : "loss";
  tint.addEventListener("change", () => { state.heat = tint.value; drawHeat(); });
  box.append(el("div", { class: "ask" }, now, tint, el("span", { class: "hint", text: state.rankNote })));
  if (Object.keys(state.upload).length) {
    box.append(el("div", { class: "hint", text: "The files dropped on the page are not part of a ranking: it is of the Router "
      + "named, as it is on disk." }));
  }
  if (!hasNeeded()) {
    box.append(el("div", { class: "hint", text: "Whether a wire is needed is asked of the exact solver, which takes the better "
      + "part of an hour and is not started from here" + (a.json ? ". This arrangement is no file: save its file first (left "
        + "column, under the picker) as arrangements/NAME.json, then:" : ":") }),
      el("pre", { text: "python3 tools/routing_lab/lab.py rank --needed"
        + (state.arrangement === "v6_feed_off" ? "" : " --arrangement " + (a.json ? "NAME" : state.arrangement)) }));
  }
  if (!r) return;

  // wires picked to take away, and the run without them
  const away = el("div", { class: "away" }, state.takeAway.length ? el("span", { class: "hint", style: "border:0;cursor:default",
    text: "take away:" }) : el("div", { class: "hint", text: "Click a wire, here or in the drawing, to take it away." }));
  for (const name of state.takeAway) away.append(el("span", { text: name + " ×", title: "keep it", onclick: () => toggleTakeAway(name) }));
  box.append(away);
  if (state.takeAway.length) {
    box.append(el("div", { class: "ask" },
      el("button", { type: "button", text: "Run without these", disabled: state.busy || cannot ? "" : null,
        title: "route the ticked classes on " + state.arrangement + " without these wires, and show it on the Fabric tab",
        onclick: async () => { if (await runBattery(state.takeAway.slice())) showTab("fabric"); } }),
      el("button", { type: "button", text: "clear", onclick: () => { state.takeAway = []; renderRanking(); drawHeat(); } }),
      el("span", { class: "hint", text: "the run's arrangement can then be saved as a file (left column)" })));
  }

  const sort = state.rankSort;
  const column = RANK_COLUMNS.find((c) => c.key === sort.key) || RANK_COLUMNS[3];
  const columns = RANK_COLUMNS.filter((c) => hasNeeded() || !["needed", "free", "unknown"].includes(c.key));
  const rows = r.wires.slice().sort((x, y) => {
    const [p, q] = [column.of(x), column.of(y)];
    const order = typeof p === "string" ? String(p).localeCompare(String(q)) : (p == null ? -1 : p) - (q == null ? -1 : q);
    return (sort.down ? -order : order) || x.wire.localeCompare(y.wire);
  });
  const table = el("table", { class: "battery" }, el("tr", {}, columns.map((c) => el("th", {
    text: c.head + (c.key === sort.key ? (sort.down ? " ▾" : " ▴") : ""), title: c.tip + (c.tip ? ". " : "") + "Click to sort.",
    class: c.key === sort.key ? "on" : "",
    onclick: () => { state.rankSort = { key: c.key, down: c.key === sort.key ? !sort.down : false }; renderRanking(); } }))));
  for (const w of rows) {
    table.append(el("tr", { class: "case" + (state.takeAway.includes(w.wire) ? " take" : ""), onclick: () => toggleTakeAway(w.wire),
      title: rankTip(w.wire) },
      columns.map((c) => {
        const v = c.show ? c.show(w) : c.of(w);
        return el("td", { text: v == null ? "" : c.signed && v > 0 ? "+" + v : String(v),
          title: c.list && w[c.list] && w[c.list].length ? w[c.list].join("\n") : null });
      })));
  }
  box.append(table);
  box.append(el("div", { class: "hint", text: "usage counts follow the router's search order and say nothing of need; a negative "
    + "loss is the router doing better without the wire" }));
  if (hasNeeded()) {
    box.append(el("div", { class: "hint", text: "needed: the exact solver proves the netlist cannot be routed without the wire "
      + "(firmware-shaped paths). not needed: a routing without it exists. The router's loss is beside these, not instead of them. "
      + "Each wire is taken away alone: several at once is another question, which \"Run without these\" asks of the router." }));
  }
}

// ---------------------------------------------------------------- starting

function showTab(name) {
  state.tab = name;
  for (const button of document.querySelectorAll("#tabs button")) {
    button.classList.toggle("on", button.dataset.tab === name);
  }
  $("fabric").hidden = name === "sheet";           // the ranking is drawn on the fabric too
  $("sheet").hidden = name !== "sheet";
  $("case").hidden = name === "ranking";
  $("ranking").hidden = name !== "ranking";
  document.querySelector("main").classList.toggle("ranking", name === "ranking");      // its table is wider than a case's
  renderArrangement();                             // the sheet's note belongs to the sheet tab
  if (name === "ranking") {
    renderRanking();
    loadRanking();
  }
  if (state.current || name === "ranking") redraw();
  else drawHeat();                                 // nothing routed is shown: only the tint, if any, is taken off
}

async function start() {
  state.info = await api("/api/info");
  state.v5nodes = state.info.nodes;                // V5's own, whatever arrangement is picked later
  state.ohms = state.info.ohms;
  $("ohms").value = state.ohms;
  $("verified").hidden = state.info.verified;
  for (const v of state.info.variants) $("variant-list").append(el("option", { value: v.spec }));
  for (const name of state.info.classes) {
    const about = (state.info.about || {})[name] || {};     // what the class is, on hover, and how many cases it runs
    $("classes").append(el("label", { title: about.what ? name + ": " + about.what : null },
      el("input", { type: "checkbox", value: name, checked: ["dense", "real", "stress", "edge"].includes(name) ? "" : null }),
      name, about.cases == null ? null : el("span", { class: "count", text: String(about.cases) })));
  }
  drawFabricBase();
  await drawSheetBase();
  renderArrangement();
  $("arrangement").addEventListener("change", async () => {
    const wanted = $("arrangement").value;
    try {
      await pickArrangement(wanted);
      $("build-error").hidden = true;
      if (state.run && state.run.drawn) await routeDrawn();      // the netlist made by hand goes with the copper looked at
    } catch (err) {                                // a file that has gained a mistake since the list was made
      $("arrangement").value = state.arrangement;
      showProblem(err.message + (err.data && err.data.problems ? ":\n" + err.data.problems.join("\n") : ""));
    }
  });

  $("controls").addEventListener("submit", (event) => { event.preventDefault(); runBattery(); });
  $("ohms").addEventListener("input", () => {
    state.ohms = Number($("ohms").value) || state.info.ohms;
    renderBattery();
    if (state.current) renderCase();
  });
  $("filter-unclean").addEventListener("change", renderBattery);
  $("filter-changed").addEventListener("change", renderBattery);
  for (const button of document.querySelectorAll("#tabs button")) {
    button.addEventListener("click", () => showTab(button.dataset.tab));
  }
  $("compare").addEventListener("change", () => {
    state.compare = $("compare").checked;
    if (state.selected) selectCase(state.selected);
  });
  if (!STATIC) {
    installDrop();
    installPaste();
    installLive();
    window.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && state.from != null) {      // let go of the node picked up
        state.from = null;
        markFrom();
        renderDrawn();
      }
    });
  }
  renderDrawn();
  $("drop-hint").hidden = Boolean(STATIC);

  if (STATIC) {
    document.querySelector('#tabs button[data-tab="ranking"]').hidden = true;      // a ranking is asked of the server
    for (const id of ["variant", "baseline", "arrangement", "run", "live"]) $(id).disabled = true;
    $("classes").hidden = true;
    $("exported").hidden = false;
    $("exported").textContent = "exported " + STATIC.when + " from " + STATIC.run.variant.name;
    $("variant").value = STATIC.run.variant.name;
    if (STATIC.run.baseline) $("baseline").value = STATIC.run.baseline.name;
    state.run = STATIC.run;
    renderRegressions();
    renderBattery();
    const first = state.run.rows.find(unclean) || state.run.rows[0];
    if (first) await selectCase(first.case);
  }
}

start().catch((err) => {
  $("build-error").hidden = false;
  $("build-error").textContent = "The page could not start: " + err.message;
});
