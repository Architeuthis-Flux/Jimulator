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
  keys: "battery",   // the list the arrow keys move through: "battery", or "case" (the bridges and nets of the case)
  sort: null,        // {col, down}: the battery's cases in the order of a column, within each class
  bridge: null,      // "n1-n2" of the bridge picked in the case panel: its row and its two ends are marked
  pickedWire: null,  // a wire clicked on the Fabric tab that carries no single net: lit by itself
  pointed: null,     // what a clicked problem or note names: {nets, wires, pins, nodes}
  side: "case",      // the right panel's face: "case", or "ranking" (and then the fabric wears the ranking's tint)
  tests: false,      // the test battery is listed too; without it, only the examples (when the run has any)
  only: null,        // a kind picked in the legend ("dup", "unrouted", ...): the rest of the routing steps back
  v5nodes: null,     // V5's nodes, for the name of one the arrangement picked has dropped
  drawn: [],         // the netlist made by clicking nodes: [[node, node]]
  drawnFrom: null,   // {cls, case} whose settings it is routed with, when it started from a case of the battery
  from: null,        // the node picked up by a first click, waiting for the second
  // a board linked over port 7 (connectBoard). name: "idle", or a state of the link; moved: the last "changed" the
  // server gave that held anything; held: the newest reading, waiting for a run or a post to be done; granted: the
  // ports the browser already lets this page open; run: the server's newest answer for the board's run; first: the
  // next reading is the link's first; movedAt: when the board changed while another run or case was shown
  link: { link: null, name: "idle", words: "", fw: null, moved: null, held: null, granted: [],
          run: null, first: true, posting: false, movedAt: null },
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
  if (pathname === "/api/rank" && STATIC.rank) return STATIC.rank;      // the one ranking it carries, of the run's arrangement
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
  $("arrangement-json").title = "save it as Routing/arrangements/<a name>.json to keep it";
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
  state.info.pins = data.pins;
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
  if (ranking()) loadRanking();
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

const CLASS_HUES = [2, 3, 7, 8, 9, 10, 11];           // the rainbow's steps a class row may wear: no blue, no orange, and not
                                                      // the first pink, which sits too near the red that means a problem

function classRow(name, rows, at) {
  const worst = (key) => {
    const values = rows.map((r) => r.metrics[key]).filter((v) => v != null);
    return values.length ? Math.max(...values) : null;
  };
  const sum = (f) => rows.reduce((total, r) => total + f(r), 0);
  const broken = rows.filter((r) => ["problems", "crash", "timeout"].includes(r.status)).length;
  const missed = sum((r) => r.metrics.missed || 0);
  const tr = el("tr", { class: "class" + (state.closed[name] ? " closed" : ""), "data-cls": name,
    style: "--c: var(--r" + CLASS_HUES[at % CLASS_HUES.length] + ")" },
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
    const elsewhere = ranOn().name !== state.arrangement && picked().engine === "solver";
    box.replaceChildren(el("b", { text: "Shown: " }), "a netlist made by hand, router " + run.variant.name + "; "
      + arrangementWords(ranOn())
      + (elsewhere ? ". That run only made the netlist: on " + state.arrangement + " it is the exact solver that routes it." : "."));
    return;
  }
  const classes = [];
  for (const row of run.rows) if (!classes.includes(row.cls)) classes.push(row.cls);
  box.title = RUN_CHECKS + classes.map((c) => "\n" + c + ": " + (((state.info.about || {})[c] || {}).what || "")).join("");
  const toClass = (c) => el("span", { class: "does", text: c + " " + run.rows.filter((r) => r.cls === c).length,
    title: "click: go to this class in the table",
    onclick: () => {
      state.closed[c] = false;
      renderBattery();
      const row = [...document.querySelectorAll("#battery tr.class")].find((tr) => tr.dataset.cls === c);
      if (row) row.scrollIntoView({ block: "start" });
    } });
  box.replaceChildren(
    el("div", {}, el("b", { text: "router" }), run.variant.name + (run.baseline ? "   against " + run.baseline.name : "")),
    el("div", {}, el("b", { text: "copper" }), arrangementWords(ranOn())),
    el("div", {}, el("b", { text: "cases" }), String(run.rows.length), classes.map(toClass)));
}

// A click on a case in the left panel: every view shows that case. With the ranking open the fabric wears the
// ranking's tint and not the case, so the click leaves the ranking first.
function openCase(name) {
  if (ranking()) showSide("case");
  state.keys = "battery";
  return selectCase(name);
}

// The examples: what a visitor sees first. Each is a small case that shows one kind of routing, with its title,
// a line about it, and how much of it routed. The test battery stays behind the "tests" box.
function renderExamples(rows) {
  return el("div", { class: "examples" }, rows.map((row, i) => {
    const [title, ...about] = (row.about || row.case).split("\n");
    const m = row.metrics || {};
    const bad = unclean(row);
    const item = el("div", { class: "example case" + (row.case === state.selected ? " on" : "") + (bad ? " short" : ""),
      "data-case": row.case, role: "button", tabindex: "0", style: "--c: var(--r" + (1 + (i * 5) % 12) + ")" },
      el("span", { class: "how", title: "jumpers routed, of those asked for",
        text: (bad ? "\u25B2 " : "") + (m.routed_primaries == null ? row.status : m.routed_primaries + "/" + m.primaries) }),
      el("b", { text: title }), el("p", { text: about.join(" ") }));
    item.addEventListener("click", () => openCase(row.case));
    item.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); openCase(row.case); }
    });
    return item;
  }));
}

function renderBattery() {
  const box = $("battery");
  box.replaceChildren();
  renderShowing();
  if (!state.run) return;
  // a run that has examples lists them alone until the tests are asked for
  const examples = state.run.rows.filter((r) => r.cls === "example");
  const alone = examples.length > 0 && !state.tests;
  $("show-tests-label").hidden = !examples.length || examples.length === state.run.rows.length;
  $("show-tests").checked = state.tests;
  for (const label of document.querySelectorAll("#filters .of-tests")) label.hidden = alone;
  $("tests-plate").textContent = alone || examples.length === state.run.rows.length ? "Examples" : "Tests";
  if (alone) {
    box.append(renderExamples(examples));
    $("tests-note").textContent = count(examples.length, "example");
    keepUi();
    return;
  }
  const onlyUnclean = $("filter-unclean").checked;
  const onlyChanged = $("filter-changed").checked;
  const table = el("table", { class: "battery" },
    el("tr", {}, el("th", { text: "case", title: "Click to put the cases back in their own order.",
      onclick: () => { state.sort = null; renderBattery(); } }),
      COLUMNS.map((c, i) => el("th", { text: c.head + (state.sort && state.sort.col === i ? (state.sort.down ? " ▾" : " ▴") : ""),
        title: c.tip + ". Click to sort the cases of each class by it; a third click puts them back.",
        class: state.sort && state.sort.col === i ? "on" : "",
        onclick: () => {
          const now = state.sort;
          state.sort = !now || now.col !== i ? { col: i, down: true } : now.down ? { col: i, down: false } : null;
          renderBattery();
        } }))));
  const classes = [];
  for (const row of state.run.rows) if (!classes.includes(row.cls)) classes.push(row.cls);
  for (const name of classes) {
    const rows = state.run.rows.filter((r) => r.cls === name);
    if (!(name in state.closed)) state.closed[name] = rows.length > 60;    // long classes start folded
    table.append(classRow(name, rows, classes.indexOf(name)));
    if (state.closed[name]) continue;
    let listed = 0;
    const column = state.sort && COLUMNS[state.sort.col];
    const value = (row) => { const v = column.get(row); return v == null ? -Infinity : v; };
    const shown = column ? rows.slice().sort((x, y) => (state.sort.down ? value(y) - value(x) : value(x) - value(y))) : rows;
    for (const row of shown) {
      if (onlyUnclean && !unclean(row)) continue;
      if (onlyChanged && !changedFromBase(row)) continue;
      listed += 1;
      const tr = el("tr", { class: "case" + (row.case === state.selected ? " on" : ""), "data-case": row.case },
        el("td", { text: row.case, title: row.case }), COLUMNS.map((c) => cell(c, row)));
      tr.addEventListener("click", () => openCase(row.case));
      table.append(tr);
    }
    if (!listed) {                                 // the filters hid every case: say so, an empty class reads as a fault
      const why = [onlyUnclean ? "not clean" : null, onlyChanged ? "changed from the baseline" : null].filter(Boolean);
      table.append(el("tr", { class: "note" }, el("td", { colspan: String(COLUMNS.length + 1),
        text: "none of the " + rows.length + " is " + why.join(" and ") + "; untick the filter to list them" })));
    }
  }
  box.append(table);
  const dirty = state.run.rows.filter(unclean).length;
  $("tests-note").textContent = count(state.run.rows.length, "case") + (dirty ? ", " + dirty + " not clean" : ", all clean");
  keepUi();
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
  renderDrawn();                                   // the netlist's buttons go quiet while a run is out
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
    forgetDrawn();
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
    renderDrawn();
    takeHeld();
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
  renderDrawn();                                   // the netlist's buttons go quiet while a run is out
  $("busy").textContent = "reading the board's output...";
  $("busy").hidden = false;
  renderArrangement();
  try {
    const data = await postBoards(list);
    await takeBoardRun(data, data.shown);
  } catch (err) {
    showProblem(err.message);
  } finally {
    $("busy").hidden = true;
    state.busy = false;
    renderArrangement();
    renderDrawn();
    takeHeld();
  }
}

// Reports posted to the server, each kept as a case of the board's run; its answer for the last.
async function postBoards(list, about, live) {
  let data = null;
  for (const [name, text] of list) data = await api("/api/board", { name: name, text: text, about: about, live: live });
  return data;
}

// The board's run (the server's answer) becomes the run shown, with the case named selected.
async function takeBoardRun(data, name) {
  if (state.arrangement !== "v5") await pickArrangement("v5");      // a board is V5: draw its output on V5's copper
  $("build-error").hidden = true;
  state.run = data;
  state.cases = {};
  forgetDrawn();
  state.compare = false;
  $("compare").checked = false;
  $("compare-box").hidden = true;
  state.closed.board = false;
  renderRegressions();
  renderBattery();
  await selectCase(name);
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

// ---------------------------------------------------------------- a board linked over port 7
//
// Connect opens the board's fourth USB serial port (board_port.js, BoardLink), which sends only BOARD_PORT.SENDS,
// and only after the click. Each reading the link gives is judged as a pasted report is, as the case live_board,
// and drawn again where it is shown, with what changed since the reading before lit (drawMoved). A board that
// stands, is gone or is too old is not a problem of the routing: it is said under the button, and never in red.

const LINK_CASE = "live_board";
const LINK_STALE = ["waiting", "lost", "too_old"];       // the view's title dims, and says when the board was last read
const tooOld = (fw) => "This board's firmware (" + fw + ") is too old for a live view: it has no :gen and :paths on port 7. "
  + "They come with " + BOARD_PORT.NEEDS + ": https://github.com/Architeuthis-Flux/JumperlOS/releases. "
  + "The page does not ask b in their place, because b prints on the board's terminal.";

const linkOpen = () => Boolean(state.link.link && !state.link.link.closing);
const linkShown = () => Boolean(state.run && state.run.board && state.selected === LINK_CASE && state.current);

function linkSaid(name, words) {
  state.link.name = name;
  state.link.words = name === "too_old" ? tooOld(state.link.fw) : words;
  renderLink();
}

// The button, the words under it, "read again" and "save trace"; and the view's title while the board stands.
function renderLink() {
  const L = state.link;
  const why = state.info.replay ? null : serialWhyNot(navigator, window.isSecureContext);
  $("connect").textContent = linkOpen() ? "Disconnect" : L.granted.length === 1 ? "Connect the board again" : "Connect a board";
  $("connect").disabled = Boolean(why);
  $("link-again").hidden = !linkOpen() || L.name === "probing";
  $("link-trace").hidden = !L.link;
  if (linkShown()) L.movedAt = null;
  const status = $("link-status");
  if (why) status.replaceChildren(why);
  else {
    status.replaceChildren((L.name === "idle" ? "" : L.name.replace("_", " ") + ": ") + L.words);
    if (L.movedAt) {
      status.append(" ", el("span", { class: "does", text: "the board changed at " + L.movedAt,
        title: "click: show the board's newest reading", onclick: showLinkRun }));
    }
  }
  const title = $("view-title");
  const stale = linkShown() && LINK_STALE.includes(L.name);
  const at = L.link && L.link.lastAt;
  title.classList.toggle("link-stale", stale);
  title.dataset.read = stale && at ? "   last read " + hhmmss(at) : "";
}

// The button's click: connect (the port the browser already lets this page open when it is one, else the one picked),
// or, when linked, disconnect.
async function connectBoard() {
  const L = state.link;
  if (linkOpen()) {
    L.link.byHand = true;
    await L.link.close();
    linkSaid("idle", "disconnected. Nothing more is sent.");
    return;
  }
  let port;
  try {
    if (state.info.replay) port = new FakePort((await api("/api/replay")).trace, { gapMs: 300 });
    else if (L.granted.length === 1) port = L.granted[0];
    else port = await navigator.serial.requestPort({ filters: [BOARD_PORT.FILTER] });      // the picker needs the click
  } catch (err) {
    linkSaid("idle", err.name === "NotFoundError" ? "no port was picked. Nothing was sent." : err.message);
    return;
  }
  // the link takes a throw in these for a port that failed: they show their own faults instead
  const link = new BoardLink(port, {
    reading: (r) => { if (state.link.link === link) showReading(r); },
    state: (name, words) => {
      try { if (state.link.link === link) linkSaid(name, words); } catch (err) { showProblem("The link's state could not be shown: " + err.message); }
    },
  });
  Object.assign(L, { link: link, fw: null, first: true, held: null });
  renderLink();
  try {
    L.fw = (await link.connect()).fw;
  } catch (err) {
    if (link.byHand || L.link !== link) return;   // disconnected while it was being proved
    await link.close();                            // a port that would not open leaves the link unclosed: not linked now
    const kind = err instanceof LinkError ? err.kind : null;
    if (kind !== "too_old") L.granted = L.granted.filter((p) => p !== port);    // the next click opens the picker
    if (kind === "not_port_7") {
      try { if (port.forget) await port.forget(); } catch (e) { /* the browser keeps it */ }
      linkSaid("idle", "That port did not answer N with a net list: it is not the board's fourth port, or the board was not "
        + "answering just then (it answers from its main loop only: not in probe mode, a menu or an app). "
        + "Nothing but one N was sent to it. Pick the one whose name ends port7 (macOS), or the last of the four.");
    } else if (kind === "busy") {
      linkSaid("idle", "The port you picked is open in another program or tab (a Jumperlessim viewer, a script). Close it there, then connect again.");
    } else if (kind === "too_old") {
      L.fw = err.fw;
      linkSaid("too_old", "");
    } else linkSaid("lost", err.message);
    return;
  }
  linkSaid("live", "firmware " + L.fw + ". Asking the board to say when its routing changes.");
  link.run();                                      // never throws; it says how it ends
}

// A reading of the linked board, posted as the case live_board. The first of a link is shown as a pasted report is;
// a later one replaces that case's row and, when it is the case shown, is drawn where it is with nothing else moved.
async function showReading(r) {
  const L = state.link;
  if (state.busy || L.posting) {                   // the newest waits for the run, or the post, to be done
    L.held = r;
    return;
  }
  L.posting = true;
  try {
    const about = "a V5's own routing, read over port 7 at " + hhmmss(r.at) + ", firmware " + r.fw + ", generation " + r.gen
      + "; not a run of the lab's router";
    const data = await postBoards([[LINK_CASE, r.b + "\n" + r.xbar]], about, true);
    const c = data.changed;
    L.run = data;
    if (c && (c.closed.length || c.opened.length || c.bridges.length)) L.moved = c;
    delete state.cases[data.variant.hash + "/v5/" + LINK_CASE];
    if (state.busy) {                              // a run began while it was posted: shown when that is done
      if (!L.held) L.held = r;
    } else if (L.first) {
      L.first = false;
      L.movedAt = null;
      await takeBoardRun(data, LINK_CASE);
    } else if (state.run && state.run.board) {
      const row = data.rows.find((x) => x.case === LINK_CASE);
      const i = state.run.rows.findIndex((x) => x.case === LINK_CASE);
      if (i >= 0) state.run.rows[i] = row;
      else state.run.rows.push(row);
      const left = $("left").scrollTop;
      renderBattery();
      $("left").scrollTop = left;
      if (state.selected === LINK_CASE) await redrawLinkCase();
      else L.movedAt = hhmmss(r.at);
    } else L.movedAt = hhmmss(r.at);
  } catch (err) {
    showProblem("A reading of the board could not be shown: " + err.message);
  } finally {
    L.posting = false;
    renderLink();
    takeHeld();
  }
}

// The reading held while a run or a post was out, now that neither is.
function takeHeld() {
  const r = state.link.held;
  if (!r || state.busy || state.link.posting) return;
  state.link.held = null;
  showReading(r);
}

// The board's case, shown, read again: its result and paint fetched again and drawn. The zoom and place of each
// view, the layout, the tab, the face, the filters, the net lit and the bridge picked stay as they were.
async function redrawLinkCase() {
  const run = state.run, mine = state.picking;
  const current = await caseOf(run.variant, LINK_CASE);
  if (run !== state.run || mine !== state.picking || state.selected !== LINK_CASE) return;     // a click came first
  const grid = $("xbar").querySelector(".xgrid");
  const scrolled = [$("case").scrollTop, grid ? grid.scrollTop : 0, grid ? grid.scrollLeft : 0];
  state.current = current;
  state.ceiling = newCeiling(run);                 // the solver's word was on the reading before
  showMissed();
  renderCase();
  redraw();
  const now = $("xbar").querySelector(".xgrid");
  $("case").scrollTop = scrolled[0];
  if (now) [now.scrollTop, now.scrollLeft] = [scrolled[1], scrolled[2]];
}

// "the board changed at ...": the board's newest reading, shown.
function showLinkRun() {
  if (!state.link.run || state.busy) return;
  if (ranking()) showSide("case");
  takeBoardRun(state.link.run, LINK_CASE).catch((err) => showProblem(err.message));
}

// What the board changed at its last change that changed anything, on every view on screen: a crosspoint it closed
// ringed in the colour of a change, one it opened hollow and grey where it was. Neither is red.
function drawMoved() {
  const m = state.link.moved;
  if (!m || !linkShown()) return;
  if (!ranking() && fabric.marks) {                // with the ranking open the fabric wears its tint
    for (const [chip, x, y, net] of m.closed) {
      const [cx, cy] = cellCentre(chip, x, y);
      fabric.marks.append(svg("circle", { class: "link-closed", cx: cx, cy: cy, r: 6, "data-net": net }));
    }
    for (const [chip, x, y] of m.opened) {
      const [cx, cy] = cellCentre(chip, x, y);
      fabric.marks.append(svg("circle", { class: "link-opened", cx: cx, cy: cy, r: 3.3 }));
    }
  }
  if (sheet.data && sheet.live) {
    const under = svg("g", {}), over = svg("g", {});
    for (const [chip, x, y, net] of m.closed) {
      const d = sheetCurve({ chip: chip, x: x, y: y });
      if (d) under.append(svg("path", { class: "s-link link-closed", d: d, "data-net": net }));
    }
    for (const [chip, x, y] of m.opened) {
      const d = sheetCurve({ chip: chip, x: x, y: y });
      if (d) over.append(svg("path", { class: "s-link link-opened", d: d }));
    }
    sheet.live.prepend(under);                     // under the net's own curve, which stays as it is
    sheet.live.append(over);
  }
  for (const [list, cls] of [[m.closed, "link-closed"], [m.opened, "link-opened"]]) {
    for (const [chip, x, y] of list) {
      const cell = $("xbar").querySelector('[data-at="' + chip + "." + x + "." + y + '"]');
      if (cell) cell.classList.add(cls);
    }
  }
  applyIsolation();
}

// A bridge whose state changed, in words: "was routed, now unrouted".
function movedWords(b) {
  return "was " + (b.was || "not there") + ", now " + (b.now || "gone");
}

// The trace as a file: a link made for the download alone, clicked, and let go.
function saveTrace() {
  if (!state.link.link) return;
  const d = new Date();
  const two = (n) => String(n).padStart(2, "0");
  const name = "port7_" + d.getFullYear() + "-" + two(d.getMonth() + 1) + "-" + two(d.getDate()) + "_" + hhmmss(d).replace(/:/g, "") + ".jsonl";
  const url = URL.createObjectURL(new Blob([state.link.link.trace()], { type: "application/x-ndjson" }));
  const a = el("a", { href: url, download: name, hidden: "" });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function installLink() {
  const L = state.link;
  if (state.info.replay) L.words = "this server replays a trace (serve --replay): Connect reads it in place of a board and opens no port.";
  $("connect").addEventListener("click", () => { connectBoard().catch((err) => linkSaid("lost", err.message)); });
  $("link-again").addEventListener("click", () => {
    if (!linkOpen()) return;
    L.link.again();
    linkSaid(L.name, "reading the board again, whether or not its counter has moved.");
  });
  $("link-trace").addEventListener("click", saveTrace);
  renderLink();
  if (state.info.replay || serialWhyNot(navigator, window.isSecureContext)) return;
  try { L.granted = await navigator.serial.getPorts(); } catch (e) { L.granted = []; }      // asks the browser, not a board
  renderLink();
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
  state.bridge = null;
  state.pointed = null;
  state.pickedWire = null;
  say("");
  showMissed();
  for (const tr of document.querySelectorAll("#battery .case")) {
    tr.classList.toggle("on", tr.dataset.case === name);
  }
  renderCase();
  renderDrawn();                                   // "start from the case shown" goes with what is shown
  redraw();
  keepUi();
}

// Both views of the selected case. The fabric is drawn against a second routing of the same case when there is
// one: the solver's when that is asked for, else the baseline's.
function redraw() {
  renderLink();
  if (ranking() && !state.current) {               // the ranking's tint, and no case to show yet
    drawFabric(null);
    drawHeat();
    drawXbar(null);
    return;
  }
  // with the ranking in the side panel the fabric wears its tint; the sheet and the crossbars still show the case
  const fabricOf = (paint, base, who) => {
    if (!ranking()) return drawFabric(paint, base, who);
    drawFabric(null);
    drawHeat();
  };
  const on = ranOn();
  if (on.name !== state.arrangement) {             // the run is on other copper than the drawing: draw none of it
    const solved = solvedShown();
    $("view-title").textContent = solved
      ? state.selected + "   the exact solver's routing on " + state.arrangement + ", one of many; not the firmware's router"
        + "   probe feed " + (on.feed ? "on" : "off") + " the fabric"
      : state.run.drawn && picked().engine === "solver"     // made by hand, on copper only the solver routes, not routed yet
        ? state.arrangement + ": its copper. The firmware made the netlist; routing it here is the exact solver's work"
          + (state.info.solver ? " (ask under Ceiling)." : ", and the solver is not installed: python3 Routing/lab.py solver-setup")
        : state.arrangement + ": its copper. The run shown is on " + on.name + ": pick that arrangement to see it drawn"
          + (state.info.solver ? ", or ask the solver for this case on " + state.arrangement + " (Ceiling)." : ".");
    drawSheet(null);                               // the sheet is V5's own
    drawXbar(solved);
    fabricOf(solved);
    return;
  }
  const solved = state.ceiling.draw && state.ceiling.answer && state.ceiling.answer.paint;
  const base = solved || (state.base && state.base.paint);
  const title = state.selected + "   " + state.run.variant.name
    + (state.run.board ? "" : "   " + arrangementWords(on))
    + (solved ? "   against the solver's routing" : base ? "   against " + state.run.baseline.name : "");
  $("view-title").textContent = title;
  drawSheet(state.current.paint);
  drawXbar(state.current.paint);
  fabricOf(state.current.paint, base, solved ? "the solver" : "the baseline");
  if (ranking() && state.tab !== "fabric") $("view-title").textContent = title;     // the tint's own words belong to the fabric
  drawMoved();
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
  $("xbar").classList.toggle("isolating", state.isolated != null);
  for (const node of $("xbar").querySelectorAll("[data-net], [data-net2]")) {
    node.classList.toggle("iso", [node.dataset.net, node.dataset.net2].includes(String(state.isolated)));
  }
  for (const row of document.querySelectorAll("#case .bridges tr[data-bridge-key]")) {
    row.classList.toggle("on", state.isolated != null && Number(row.dataset.net) === state.isolated);
    row.classList.toggle("at", row.dataset.bridgeKey === state.bridge);
  }
  const pointed = state.pointed || { wires: [], pins: [], nodes: [] };
  const ends = new Set(pointed.nodes);            // the wires of the nodes to ring: a bridge's two ends, or the nodes a note names
  for (const node of (state.bridge ? state.bridge.split("-") : [])) {
    if (state.info.nodes[node]) ends.add(state.info.nodes[node].wire);
  }
  for (const [wire, g] of Object.entries(fabric.pads)) g.classList.toggle("end", ends.has(wire));
  for (const [name, path] of Object.entries(fabric.wires)) {
    path.classList.toggle("pick", name === state.pickedWire || pointed.wires.includes(name));
  }
  for (const label of $("xbar").querySelectorAll(".xwire")) {
    label.classList.toggle("pick", label.dataset.wire === state.pickedWire || pointed.wires.includes(label.dataset.wire));
  }
  for (const old of document.querySelectorAll("#fabric-svg .spot")) old.remove();
  if (fabric.marks) {
    for (const [chip, axis, pin] of pointed.pins) {
      const [x, y] = pinPoint(chip, axis, pin);
      fabric.marks.append(svg("circle", { class: "spot", cx: x, cy: y, r: 9 }));
    }
  }
}

// ---------------------------------------------------------------- a click answers

// What was clicked, in words, under the tabs. A phone has no pointer to hover with, and a click should answer.
function say(text) {
  const box = $("said");
  box.hidden = !text;
  box.replaceChildren(el("span", { text: text || "" }),
    el("button", { type: "button", text: "×", title: "close", onclick: () => say("") }));
}

// A kind of mark shown alone (a legend key, or a count in the case panel): the rest of the routing steps back. The
// same kind again, or Escape, shows everything.
const KIND_WORDS = { closed: "closed crosspoints of first paths", dup: "crosspoints of duplicate paths", xp: "closed crosspoints",
  mismatch: "claims that do not match the copper", unrouted: "ends of bridges the router failed",
  refused: "ends of bridges the firmware said no to", ghost: "free in the copper: missed paths, or the spare copies asked for",
  thru: "on the KiCad sheet, the far side of a wire's op-amp: its signal after a buffer or a stage that scales it",
  "link-closed": "crosspoints the board closed at its last change", "link-opened": "crosspoints the board opened at its last change" };

function onlyKind(kind) {
  state.only = kind && state.only !== kind ? kind : null;
  for (const view of document.querySelectorAll(".view svg")) {
    if (state.only) view.dataset.only = state.only;
    else delete view.dataset.only;
  }
  for (const key of document.querySelectorAll("#legend .key[data-kind]")) key.classList.toggle("on", key.dataset.kind === state.only);
  say(state.only ? "shown alone: " + KIND_WORDS[state.only] + "\n(the same again, or Escape, shows everything)" : "");
}

// The view's own readout, in its lower right corner: how far in it is, and what the case shown closes.
function renderHud() {
  const view = state.tab === "xbar" ? null : document.querySelector(state.tab === "sheet" ? "#sheet-svg" : "#fabric-svg");
  const paint = ranking() && state.tab === "fabric" ? null : shownPaint();
  const parts = [];
  if (view && view.dataset.zoom) parts.push(["zoom", view.dataset.zoom + "%"]);
  if (paint) parts.push(["xp", paint.crosspoints.length], ["nets", Object.keys(paint.nets || {}).length], ["bridges", paint.bridges.length]);
  $("hud").replaceChildren(...parts.flatMap(([label, value], i) => [(i ? "   " : "") + label + " ", el("b", { text: String(value) })]));
}

// Where the page was left (the tab, the case, the table's order and what is folded), kept by the browser for
// this page and put back when it opens.
const UI_KEY = "lab.ui.v1:" + location.pathname;

function keptUi() {
  try { return JSON.parse(localStorage.getItem(UI_KEY) || "{}") || {}; } catch (e) { return {}; }
}

function keepUi() {
  try {
    localStorage.setItem(UI_KEY, JSON.stringify({ tab: state.tab, side: state.side, tests: state.tests, selected: state.selected, sort: state.sort, closed: state.closed,
      unclean: $("filter-unclean").checked }));
  } catch (e) { /* a private window */ }
}

// Let go of everything a click lit.
function letGo() {
  state.isolated = null;
  state.bridge = null;
  state.pointed = null;
  state.pickedWire = null;
  say("");
  applyIsolation();
}

// A click on a wire of the drawing, or on a node of a page that cannot connect nodes: it says what the wire is and
// carries. A wire with one net lights that net; any other is lit by itself. The same click again lets go.
function touchWire(name) {
  const paint = shownPaint();
  const live = paint && paint.wires[name];
  const net = live && live.nets.length === 1 ? live.nets[0] : null;
  const again = net != null ? state.isolated === net && !state.bridge : state.pickedWire === name;
  letGo();
  if (again) return;
  if (net != null) state.isolated = net;
  else state.pickedWire = name;
  say(wireTip(name));
  applyIsolation();
}

// A click on a chip: what it is, and what the case shown closes on it.
function touchChip(name) {
  const paint = shownPaint();
  const closed = paint ? paint.crosspoints.filter((c) => c.chip === name) : [];
  const nets = [...new Set(closed.map((c) => netLabel(c.net)))];
  say("chip " + name + "  (" + (state.info.fabric.chips[name].role === "sf" ? "specials and the Nano header on its X pins"
    : "breadboard rows on its Y pins") + ")"
    + (paint ? "\n" + count(closed.length, "crosspoint") + " closed on it in this case"
      + (nets.length ? ", for " + (nets.length === 1 ? "net " : "nets ") + nets.join(", ") : "") : ""));
}

// A bridge's row: its net is lit, and the row and the bridge's two ends are marked. The same row again lets go.
function touchBridge(key, net) {
  const again = state.bridge === key;
  letGo();
  if (again) return;
  state.bridge = key;
  state.isolated = net;
  applyIsolation();
}

// What a line of text names that the drawing can show: nets ("net 6"), pins ("chip D x7"), wires ("(DJ)"), and in
// a note about sense taps the nodes it lists.
function named(text) {
  const paint = shownPaint();
  const out = { nets: [], wires: [], pins: [], nodes: [] };
  for (const m of text.matchAll(/\bnet (\d+)\b/g)) if (paint && paint.nets[m[1]]) out.nets.push(Number(m[1]));
  for (const m of text.matchAll(/\bchip ([A-Z]) ([xyXY])(\d+)\b/g)) {
    if (state.info.fabric.chips[m[1]]) out.pins.push([m[1], m[2].toUpperCase(), Number(m[3])]);
  }
  for (const m of text.matchAll(/\(([^()\s]+)\)/g)) if (state.info.fabric.wires[m[1]]) out.wires.push(m[1]);
  const taps = /^no sense-tap route for (.+)$/.exec(text);
  if (taps) {
    const wireOf = {};
    for (const [node, known] of Object.entries(state.info.nodes)) wireOf[nodeName(Number(node))] = known.wire;
    for (const word of taps[1].split(/\s+/)) if (wireOf[word]) out.nodes.push(wireOf[word]);
  }
  return out;
}

// Show in the drawing what a line names: its first net lit, its wires lit, its pins and nodes ringed.
function point(what, text) {
  const again = state.pointed === what;
  letGo();
  if (again) return;
  state.pointed = what;
  state.isolated = what.nets.length ? what.nets[0] : null;
  say(text);
  applyIsolation();
}

// A problem or a note as a list item: one that names something the drawing can show answers a click.
function lineItem(text) {
  const what = named(text);
  if (!(what.nets.length || what.wires.length || what.pins.length || what.nodes.length)) return el("li", { text: text });
  return el("li", { text: text, class: "names", title: "click: show in the drawing what this names", onclick: () => point(what, text) });
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
  // a case that says what it is in a title and a line (an example) is headed by the title
  const [title, ...told] = (result.about || "").split("\n");
  box.replaceChildren(el("h1", { text: told.length ? title : result.case }));
  if (solved) {
    box.append(
      el("div", { class: "about", text: "the exact solver's routing on " + state.arrangement
        + ", one of many; not the firmware's router" }),
      el("div", { class: "counts", text: count(solved.crosspoints.length, "crosspoint") + " for "
        + count(solved.bridges.filter((b) => b.state === "routed").length, "bridge") + "; probe feed " + (ranOn().feed ? "on" : "off")
        + " the fabric. The netlist is the firmware's, from the run on " + ranOn().name + "." }));
  } else {
    box.append(el("div", {}, el("span", { class: "status " + result.status, text: result.status,
      title: "click: what the judge found",
      onclick: () => {
        const trouble = box.querySelector("h2.trouble");
        if (trouble) trouble.scrollIntoView({ block: "start" });
        say(result.status + ": " + (paint.problems.length ? count(paint.problems.length, "problem") + ", listed under PROBLEMS"
          : "the judge found nothing wrong with this routing"));
      } }),
      // what kind of case this is: a board's own routing, one the bench suite requires to route, or one that is scored
      el("span", { class: "hint", text: "  " + result.cls + " · "
        + (result.cls === "board" ? "as a board routed it" : result.must_route ? "must route" : "scored") })));
    if (result.about) box.append(el("div", { class: "about", text: told.length ? told.join(" ") : result.about }));
    if (["crash", "timeout"].includes(result.status)) {
      box.append(el("h2", { text: "what the harness said", class: "trouble" }),
        el("ul", { class: "problems" }, result.problems.map((p) => el("li", { text: p }))),
        el("pre", { class: "report", text: result.stderr || "(nothing on stderr)" }));
      return;
    }
    const does = (text, tip, act) => el("span", { class: "does", text: text, title: "click: " + tip, onclick: act });
    const tapNote = paint.notes.find((n) => n.startsWith("no sense-tap route for"));
    box.append(el("div", { class: "counts" },
      m.routed_primaries + " of " + (m.primaries - (m.refused || 0)) + " primaries routed, ",
      does(m.routed_duplicates + " copies", "show the duplicate paths alone", () => onlyKind("dup")), ", ",
      does(m.crosspoints + " crosspoints", "show the crosspoints alone", () => onlyKind("xp")),
      m.taps == null ? null : ", ",
      m.taps == null ? null : does((m.taps - m.taps_dead.length) + " of " + m.taps + " taps reachable", "ring the nodes with no sense-tap route",
        () => (tapNote ? point(named(tapNote), tapNote) : say("every scanned node has a sense-tap route"))),
      m.repeat_same === false ? ", ROUTES DIFFER ON A SECOND REBUILD" : null));
    const mv = linkShown() && state.link.moved;
    if (mv) {
      box.append(el("div", { class: "counts" }, "at the board's last change: ",
        does(mv.closed.length + " closed", "show the crosspoints it closed alone", () => onlyKind("link-closed")), ", ",
        does(mv.opened.length + " opened", "show the crosspoints it opened alone", () => onlyKind("link-opened")), ", ",
        does(count(mv.bridges.length, "bridge") + " changed", "say which", () => say(mv.bridges.length
          ? mv.bridges.map((x) => nodeName(x.n1) + " - " + nodeName(x.n2) + ": " + movedWords(x)).join("\n") : "no bridge changed"))));
    }
  }
  const moved = (b) => (linkShown() && state.link.moved ? state.link.moved.bridges : [])
    .find((x) => (x.n1 === b.n1 && x.n2 === b.n2) || (x.n1 === b.n2 && x.n2 === b.n1));

  if (paint.problems.length) {
    box.append(el("h2", { text: "problems", class: "trouble" }),
      el("ul", { class: "problems" }, paint.problems.map(lineItem)));
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
    const change = moved(b);
    const tr = el("tr", { class: (routed ? "" : (failed(b) ? "unrouted" : "no")) + (change ? " link-moved" : ""), "data-net": b.net, "data-bridge-key": b.n1 + "-" + b.n2 },
      el("td", {}, b.net == null ? null : el("span", { class: "swatch", style: "display:inline-block;margin-right:5px;background:" + netColour(b.net) }),
        nodeName(b.n1) + " - " + nodeName(b.n2) + (b.infra ? "  (probe feed)" : ""),
        routed ? null : el("div", { class: "state", text: stateWords(b, paint) }),
        change ? el("div", { class: "moved-words", text: movedWords(change) }) : null,
        old && old.state !== b.state ? el("div", { class: "state", text: "baseline: " + STATE_WORDS[old.state] }) : null),
      el("td", {}, routed ? String(b.copies) : "", versus(routed ? String(b.copies) : "", oldRouted ? String(old.copies) : undefined)),
      el("td", { text: routed ? String(b.hops) : "" }),
      el("td", {}, ohmsText(b.r), versus(ohmsText(b.r), oldRouted ? ohmsText(old.r) : undefined)),
      // copies the free copper still allows, and the ohms with them; a click draws them dashed
      b.spare ? el("td", { class: "spare" + (state.spareOf === b.n1 + "-" + b.n2 ? " on" : ""), "data-bridge": b.n1 + "-" + b.n2,
        title: SPARE_TIP, text: "+" + b.spare + " → " + ohmsText(b.r_spare),
        onclick: (event) => { event.stopPropagation(); toggleSpare(b); } }) : el("td", {}));
    tr.addEventListener("click", () => { state.keys = "case"; touchBridge(b.n1 + "-" + b.n2, b.net); });
    bridges.append(tr);
  }
  box.append(bridges);
  if (!STATIC) box.append(ceilingSection());       // an exported page cannot ask the solver

  box.append(el("h2", { text: "nets" }));
  for (const [net, info] of Object.entries(paint.nets)) {
    box.append(el("div", { class: "net", "data-net": net,
      onclick: () => { state.keys = "case"; const again = state.isolated === Number(net) && !state.bridge; letGo(); if (!again) isolate(Number(net)); } },
      el("span", { class: "swatch", style: "background:" + info.colour }),
      el("span", { text: info.label + ":  " + info.nodes.map(nodeName).join(", ") })));
  }

  if (paint.notes.length) {
    box.append(el("h2", { text: "notes" }), el("ul", { class: "notes" }, paint.notes.map(lineItem)));
  }
  box.append(el("details", {}, el("summary", { text: solved ? "b report of the run on " + ranOn().name : "b report" }),
    el("pre", { text: result.b })));
  $("case-note").textContent = ranking() ? $("case-note").textContent : result.case;
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
      el("pre", { text: "python3 Routing/lab.py solver-setup" }),
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
function panZoom(view, full, widest = full[2] * 1.5, all = null) {
  let box = full.slice();
  const apply = () => {
    view.setAttribute("viewBox", box.join(" "));
    view.dataset.zoom = String(Math.round(100 * full[2] / box[2]));
    renderHud();
  };
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
  const zoomAbout = (point, wanted) => {           // point: {clientX, clientY}; wanted: the box's new size over its old
    const k = Math.min(widest / box[2], Math.max(full[2] / 60 / box[2], wanted));    // stop at the limits, do not stick
    const [x, y] = at(point);
    box = [x - (x - box[0]) * k, y - (y - box[1]) * k, box[2] * k, box[3] * k];
    apply();
  };
  view.addEventListener("wheel", (event) => {
    event.preventDefault();
    const unit = event.deltaMode === 1 ? ZOOM_PER_PIXEL * 25 : event.deltaMode === 2 ? ZOOM_PER_PIXEL * 500 : ZOOM_PER_PIXEL;
    zoomAbout(event, Math.pow(2, event.deltaY * unit * (event.ctrlKey ? 10 : 1)));
  }, { passive: false });
  let drag = null;
  // On a touch screen one finger pans, as a drag does, and two zoom about the point between them by as much as
  // they spread or close (the page itself stays put: the view has touch-action none).
  const fingers = new Map();                       // pointerId -> {clientX, clientY}, the fingers down on the view
  let spread = 0;                                  // how far apart the two were at the last move
  const apart = () => {
    const [a, b] = [...fingers.values()];
    return { clientX: (a.clientX + b.clientX) / 2, clientY: (a.clientY + b.clientY) / 2,
             far: Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY) };
  };
  const lift = (event) => { fingers.delete(event.pointerId); };
  window.addEventListener("pointerup", lift);
  window.addEventListener("pointercancel", lift);
  view.addEventListener("pointerdown", (event) => {
    if (event.pointerType === "touch") fingers.set(event.pointerId, { clientX: event.clientX, clientY: event.clientY });
    if (fingers.size === 2) {
      drag = null;                                 // the second finger ends the pan
      spread = apart().far;
      return;
    }
    drag = { x: event.clientX, y: event.clientY, box: box.slice(), moved: false };
  });
  window.addEventListener("pointermove", (event) => {
    if (fingers.has(event.pointerId)) fingers.set(event.pointerId, { clientX: event.clientX, clientY: event.clientY });
    if (fingers.size === 2) {
      const now = apart();
      if (spread > 0 && now.far > 0) zoomAbout(now, spread / now.far);
      spread = now.far;
      return;
    }
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
  // back to the box it opened on; when it is there already and there is more to show (the whole sheet), to that
  const whole = () => {
    const there = box.every((v, i) => Math.abs(v - full[i]) < 0.5);
    box = (there && all ? all : full).slice();
    apply();
  };
  view.addEventListener("dblclick", whole);
  view.addEventListener("fit", whole);          // the fit button
  view.addEventListener("zoomby", (event) => {   // the zoom buttons: about the middle of the view
    const r = view.getBoundingClientRect();
    zoomAbout({ clientX: r.left + r.width / 2, clientY: r.top + r.height / 2 }, event.detail);
  });
  apply();
}

function hover(node, text) {
  node.addEventListener("pointermove", (event) => {
    const tip = $("tip");
    tip.textContent = typeof text === "function" ? text() : text;
    tip.hidden = false;
    tip.style.left = Math.max(4, Math.min(event.clientX + 14, window.innerWidth - 350)) + "px";
    tip.style.top = Math.min(event.clientY + 14, window.innerHeight - 90) + "px";
  });
  node.addEventListener("pointerleave", () => { $("tip").hidden = true; });
}

function wireTip(name, ofCase = false) {
  if (ranking() && !ofCase) return rankTip(name);
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

// ---------------------------------------------------------------- the crossbars, as the board prints them

// A wire's name in the few letters the board's own print gives it.
const SHORT_NAMES = [[/^(ROUTABLE_)?BUF(FER)?_IN$/, "BFi"], [/^(ROUTABLE_)?BUF(FER)?_OUT$/, "BFo"], [/^TOP_RAIL$/, "TRl"],
  [/^BOTTOM_RAIL$/, "BRl"], [/^DAC_?(\d)$/, "Da$1"], [/^ADC_?(\d)$/, "Ad$1"], [/^GPIO_?(\d+)$/, "GP$1"], [/^(?:NANO_)?([AD]\d+)$/, "n$1"],
  [/^ISENSE_PLUS$/, "I+"], [/^ISENSE_MINUS$/, "I-"], [/^UART_RX$/, "uRX"], [/^UART_TX$/, "uTX"], [/^AREF$/, "ARF"], [/^RESET$/, "RST"]];

function shortWire(name, nodeOf) {
  if (name == null) return "x";                    // this arrangement has no copper on the pin
  if (name.startsWith("unconnected")) return "u";
  const lane = /^\/?([A-L]{2}\d?)$/.exec(name);
  if (lane) return lane[1];
  const full = nodeOf[name] == null ? name : nodeName(Number(nodeOf[name]));
  for (const [from, to] of SHORT_NAMES) if (from.test(full)) return full.replace(from, to);
  return /^\d+$/.test(full) ? full : full.slice(0, 4);
}

// Every chip as the grid the firmware's crossbar print draws (its C command): a row for each X pin, a column for
// each Y pin, a block where the two are joined (a lighter one for a duplicate path's), and lines along the pins
// that carry something, each in its net's colour. The wire on each pin is named at the row's end and under the
// column. A block or a name answers a click as its dot or its wire does in the fabric.
function drawXbar(paint) {
  const box = $("xbar");
  const pins = state.info.pins;
  if (!pins) {
    box.replaceChildren(el("pre", { class: "hint", style: "padding:16px; white-space:pre-wrap",
      text: "This page was made before it could draw the crossbars." }));
    return;
  }
  const nodeOf = {};
  for (const [node, known] of Object.entries(state.info.nodes)) nodeOf[known.wire] = node;
  const closed = {};                               // "chip.x.y" -> the crosspoint
  const on = {};                                   // "chip.X3" or "chip.Y1" -> the nets on that pin
  const add = (key, net) => { (on[key] = on[key] || new Set()).add(net); };
  for (const c of (paint ? paint.crosspoints : [])) {
    closed[c.chip + "." + c.x + "." + c.y] = c;
    add(c.chip + ".X" + c.x, c.net);
    add(c.chip + ".Y" + c.y, c.net);
  }
  // A piece of a pin's line. The letter is the board's (it is what a copy takes), and the style sheet draws the
  // line over it so that the pieces join whatever the font: along the row in the row's net's colour, down the
  // column in the column's; red when two nets are on the pin.
  const line = (text, row, col) => {
    const node = el("span", { text: text, class: "xl" + (row ? " xh" : "") + (col ? " xv" : "") });
    for (const [nets, hue, key] of [[row, "--h", "net"], [col, "--v", "net2"]]) {
      if (!nets) continue;
      node.style.setProperty(hue, nets.size === 1 ? netColour([...nets][0]) : "var(--problem)");
      if (nets.size === 1) node.dataset[key] = [...nets][0];
    }
    return node;
  };
  const label = (wire, width) => el("span", { class: "xwire", "data-wire": wire, title: wire || "no copper on this pin",
    text: shortWire(wire, nodeOf).padEnd(width),
    onclick: () => { if (wire && fabric.wires[wire] && !ranking()) touchWire(wire); } });
  const grid = el("div", { class: "xgrid" });
  for (const chip of Object.keys(pins)) {
    const pre = el("pre", { class: "xchip" });
    pre.append(el("span", { class: "xname", text: "          chip " + chip + "\n" }), "     0  1  2  3  4  5  6  7\n");
    for (let x = 0; x < 16; x++) {
      const row = on[chip + ".X" + x];
      pre.append(String(x).padStart(3) + " ");
      for (let y = 0; y < 8; y++) {
        const col = on[chip + ".Y" + y];
        const c = closed[chip + "." + x + "." + y];
        pre.append(row ? line("─", row, null) : " ");
        let cell;
        if (c) {
          const words = () => c.chip + "  x" + c.x + " y" + c.y + "\nnet " + netLabel(c.net) + ", path " + c.path
            + (c.dup ? " (a duplicate)" : "");
          const block = el("span", { class: "xblock" + (c.dup ? " dup" : ""), text: c.dup ? "▓" : "█", "data-net": c.net,
            style: "--h:" + netColour(c.net) });
          hover(block, words);
          block.addEventListener("click", () => {
            const again = state.isolated === c.net && !state.bridge;
            letGo();
            if (again) return;
            state.isolated = c.net;
            say(words());
            applyIsolation();
          });
          cell = block;
        } else if (row || col) cell = line(row && col ? "┼" : row ? "─" : "│", row, col);
        else cell = el("span", { class: "xdot", text: "." });
        cell.dataset.at = chip + "." + x + "." + y;      // where drawMoved finds it
        pre.append(cell);
        pre.append(row ? line("─", row, null) : " ");
      }
      pre.append(" ", label(pins[chip].x[x], 0), "\n");
    }
    pre.append("    ");
    for (let y = 0; y < 8; y++) pre.append(" ", label(pins[chip].y[y], 2));
    grid.append(pre);
  }
  box.replaceChildren(grid);
  applyIsolation();
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
    const chip = svg("g", { class: "chip" },
      svg("rect", { x: c.x, y: c.y, width: 16 * f.cell, height: 8 * f.cell }),
      svg("text", { x: c.x + 16 * f.cell + 6, y: c.y + 14, text: name }));
    chip.addEventListener("click", () => { if (!ranking()) touchChip(name); });
    chips.append(chip);
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
    hit.addEventListener("pointerenter", () => path.classList.add("under"));
    hit.addEventListener("pointerleave", () => path.classList.remove("under"));
    hit.addEventListener("click", () => {
      if (ranking()) {
        toggleTakeAway(name);
        say(state.takeAway.includes(name) ? rankTip(name) : "");
        return;
      }
      touchWire(name);
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
    hover(g, () => wireTip(name) + (STATIC || ranking() ? "" : "\nclick: connect this node to another"));
    g.addEventListener("click", () => {
      if (ranking()) return;
      if (STATIC) touchWire(name);                 // a page that cannot connect nodes says what the node is on
      else clickNode(name);
    });
    pads.append(g);
    fabric.pads[name] = g;
  }
  fabric.dots = svg("g", { class: "dots" });
  fabric.marks = svg("g", { class: "marks" });
  fabric.ghost = svg("g", { class: "ghosts" });
  // the pads lie over the wires' hit areas, so that a click on a node lands on the node and not on its wire
  view.append(chips, wires, fabric.ghost, fabric.dots, fabric.marks, hits, pads, pinMarks);
  view.addEventListener("click", (event) => { if (event.target === view && !ranking()) letGo(); });
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
    const words = () => c.chip + "  x" + c.x + " y" + c.y + "\nnet " + netLabel(c.net) + ", path " + c.path
      + (c.dup ? " (a duplicate)" : "");
    hover(dot, words);
    dot.addEventListener("click", () => {
      const again = state.isolated === c.net && !state.bridge;
      letGo();
      if (again) return;
      state.isolated = c.net;
      say(words());
      applyIsolation();
    });
    fabric.dots.append(dot);
  }

  for (const b of paint.bridges) {
    if (b.state === "routed") continue;
    for (const node of [b.n1, b.n2]) {
      const known = state.info.nodes[String(node)];
      const pad = known && fabric.pads[known.wire];
      if (!pad) continue;
      const centre = pad.firstChild;
      pad.append(svg("circle", { class: "want " + (failed(b) ? "failed" : "refused"), cx: centre.getAttribute("cx"), cy: centre.getAttribute("cy"), r: 7,
        stroke: failed(b) ? netColour(b.net) : GREY }));
    }
  }
  if (base) drawCompare(paint, base, who);
  drawGhost();
  applyIsolation();
  renderHud();
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

// The backdrop is 10 MB: it is fetched when the sheet tab is first opened, not with the page. Its bitmap, when one
// was made, is beside it and named alike.
function loadBackdrop() {
  for (const image of document.querySelectorAll("#sheet-svg image")) {
    if (image.getAttribute("href")) continue;
    image.setAttribute("href", image === sheet.fast ? sheet.backdrop.replace(/\.svg$/, ".png") : sheet.backdrop);
  }
}

// The plot is some 160,000 paths and takes about an eighth of a second to draw again at each step of a zoom or a
// drag. So while the view moves a bitmap of the same plot stands in for it, and the plot comes back once the view
// has been still for a moment (and has arrived: it is the bigger of the two to fetch).
function sheetMoved() {
  sizeStripes();
  if (!sheet.fast) return;
  sheet.fast.style.visibility = "";
  sheet.sharp.style.visibility = "hidden";
  clearTimeout(sheet.still);
  sheet.still = setTimeout(() => {
    if (!sheet.sharpHere) return;
    sheet.sharp.style.visibility = "";
    sheet.fast.style.visibility = "hidden";
  }, 220);
}

async function drawSheetBase() {
  // an exported page carries the sheet's data when it was exported with its backdrop beside it
  let why = "This exported page was made without the KiCad sheet (lab.py export --backdrop NAME carries it).";
  sheet.backdrop = STATIC ? STATIC.backdrop : "sheet/backdrop.svg";
  if (STATIC) sheet.data = STATIC.sheet || null;
  else {
    why = "The KiCad sheet has not been built. Build it once with:\n\n    python3 Routing/lab.py sheet"
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
  sheet.defs = svg("defs", {});
  const light = s.theme ? "" : " light";
  sheet.fast = s.bitmap ? svg("image", { class: "fast" + light, x: 0, y: 0, width: s.size[0], height: s.size[1] }) : null;
  sheet.sharp = svg("image", { class: "sharp" + light, x: 0, y: 0, width: s.size[0], height: s.size[1] });
  sheet.sharpHere = false;
  sheet.sharp.addEventListener("load", () => { sheet.sharpHere = true; sheetMoved(); });
  if (sheet.fast) sheet.sharp.style.visibility = "hidden";       // until it has arrived and the view is still
  view.append(sheet.defs, sheet.fast, sheet.sharp, sheet.live);
  $("sheet").replaceChildren(view);
  new MutationObserver(sheetMoved).observe(view, { attributes: true, attributeFilter: ["viewBox"] });
  new ResizeObserver(sizeStripes).observe(view);
  const bodies = Object.values(s.bodies);                    // a double-click fits the crossbar blocks
  const x0 = Math.min(...bodies.map((b) => b[0])) - 40;
  const y0 = Math.min(...bodies.map((b) => b[1])) - 30;
  const x1 = Math.max(...bodies.map((b) => b[2])) + 50;
  const y1 = Math.max(...bodies.map((b) => b[3])) + 20;
  panZoom(view, bodies.length ? [x0, y0, x1 - x0, y1 - y0] : [0, 0, s.size[0], s.size[1]], s.size[0] * 1.2,
    bodies.length ? [0, 0, s.size[0], s.size[1]] : null);
}

// What a piece of copper past the crossbar is to its wire (sheet.py's BEYOND).
function pastTip(wire, t) {
  const stage = t.by + " (" + (t.kind === "buffer" ? "a buffer" : "scaled" + (t.gain ? ": " + t.gain : "")) + ")";
  return t.net + "\n" + (t.kind === "same" ? "the same signal as " + wire + ", across " + t.by
    : t.way === "in" ? "drives " + wire + " through " + stage : wire + " after " + stage);
}

// The paint of copper past an op-amp: a colour with thin white diagonal stripes, as a pattern of the sheet's own
// (one a colour, made when first asked for). The stripes are sized in screen pixels: sizeStripes keeps them so.
const STRIPE = 9;                                  // the pattern's period, px
function stripeOf(colour) {
  const id = "stripe-" + colour.replace(/[^0-9a-z]/gi, "");
  if (!sheet.defs.querySelector("#" + id)) {
    sheet.defs.append(svg("pattern", { id: id, patternUnits: "userSpaceOnUse", width: STRIPE, height: STRIPE },
      svg("rect", { width: STRIPE, height: STRIPE, fill: colour }),
      svg("rect", { width: 1.6, height: STRIPE, fill: "#fff" })));
    sizeStripes();
  }
  return "url(#" + id + ")";
}

// One pattern unit is one screen pixel at any zoom: the sheet's units to a pixel, by the view box and the room.
function sizeStripes() {
  const view = $("sheet-svg");
  if (!view || !sheet.defs) return;
  const box = view.viewBox.baseVal;
  const room = view.getBoundingClientRect();
  if (!box.width || !room.width) return;
  const k = Math.max(box.width / room.width, box.height / room.height);       // "meet": the tighter of the two
  for (const pattern of sheet.defs.children) pattern.setAttribute("patternTransform", "rotate(45) scale(" + k + ")");
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
        hover(part, () => wireTip(name, true));
        if (!short) part.addEventListener("click", () => isolate(w.nets[0]));
        copper.append(part);
      }
      // Past the crossbar: the copper on the other side of the wire's jumper or shunt, drawn as the wire is, and
      // of its op-amp, striped, since a buffer or a scaling stage has changed the signal by then. A wire that
      // carries a net of its own (the routable buffer's other end) is drawn as that instead.
      for (const t of (s.beyond && s.beyond[name]) || []) {
        const far = s.nets[t.net];
        if (!far || (paint.wires[t.net] && paint.wires[t.net].nets.length)) continue;
        const cls = (t.kind === "same" ? "" : " thru") + (short ? " short" : "");
        // after a stage: the same colour, whole, with thin white stripes across it (dashes are a duplicate path's)
        const paint2 = t.kind === "same" || short ? look : Object.assign({}, look, { stroke: stripeOf(look.stroke) });
        const past = far.segments.map(([ax, ay, bx, by]) => svg("path",
          Object.assign({ class: "s-wire" + cls, d: "M" + ax + " " + ay + "L" + bx + " " + by }, paint2)));
        for (const p of far.labels) past.push(sheetDot("s-tag" + cls, p, paint2));
        for (const part of past) {
          hover(part, () => pastTip(name, t));
          if (!short) part.addEventListener("click", () => isolate(w.nets[0]));
          copper.append(part);
        }
      }
    }
    for (const pin of w.pins) {
      const p = pin.mark && s.pins[pin.chip + "." + pin.axis + pin.pin];
      if (!p) continue;
      if (pin.mark === "mismatch") {
        const ring = svg("circle", { class: "s-ring", cx: p[0], cy: p[1], r: 2.2 });
        hover(ring, () => wireTip(name, true));
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
        marks.append(svg("circle", { class: "s-want " + (failed(b) ? "failed" : "refused"), cx: p[0], cy: p[1], r: 2.4,
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
  if (STATIC || ranking()) return;
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
  // on to what is on screen: while a case of a run (not a netlist made by hand) is shown, start from that case
  if (caseToAddTo()) startFromShown();
  else if (!(state.run && state.run.drawn)) forgetDrawn();          // a case with nothing routed: a netlist of its own
  const same = ([a, b]) => (a === pair[0] && b === pair[1]) || (a === pair[1] && b === pair[0]);
  if (!state.drawn.some(same)) state.drawn.push(pair);      // the firmware would merge the same pair twice
  routeDrawn(pair);
}

// Is a case of a run shown that a click adds to? Not a netlist made by hand (that is added to as it is), and not a
// case whose paint holds no bridge (a crash, a timeout, a case that cannot be placed): there is nothing to add to.
function caseToAddTo() {
  return Boolean(state.current && !(state.run && state.run.drawn) && state.current.paint.bridges.some((b) => !b.infra));
}

// The netlist made by hand becomes the case shown: its bridges, and (for a case of the battery) its settings, which
// the server takes from the case itself. A board's output has bridges only.
function startFromShown() {
  state.drawn = shownBridges();
  state.drawnFrom = state.run.board ? null : { cls: state.current.result.cls, case: state.current.result.case };
}

// A run or a board's output put on screen: what was made by hand before is not what a click adds to any more.
function forgetDrawn() {
  state.drawn = [];
  state.drawnFrom = null;
  state.from = null;
  markFrom();
}

// Route state.drawn on the arrangement picked and show it. `added`: the bridge just put in, taken out again if
// the netlist is refused with it.
async function routeDrawn(added) {
  renderDrawn();
  if (state.busy) {
    showProblem("A run is in flight: change the netlist made by hand again when it is done, and it is routed.");
    return;
  }
  if (!state.drawn.length) {                       // the last bridge was taken out: nothing made by hand is shown any more
    state.drawnFrom = null;
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
  state.busy = true;
  const asked = state.arrangement;
  renderDrawn();                                   // the netlist's buttons go quiet while it is routed
  $("busy").textContent = "routing " + count(state.drawn.length, "bridge") + " made by hand on " + asked + "...";
  $("busy").hidden = false;
  renderArrangement();
  try {
    const data = await api("/api/route", { variant: variantSpec(), arrangement: asked, bridges: state.drawn,
      from: state.drawnFrom });
    if (data.build_error) {
      if (added) state.drawn = state.drawn.filter((pair) => pair !== added);     // not routed, so not kept: as a refusal
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
    if (state.arrangement === asked && picked().engine === "solver" && state.info.solver) await askCeiling("firmware");
  } catch (err) {
    if (added) state.drawn = state.drawn.filter((pair) => pair !== added);
    showProblem(err.message);
  } finally {
    $("busy").hidden = true;
    state.busy = false;
    renderArrangement();
    renderDrawn();
    takeHeld();
  }
  // another arrangement was picked while this one was routed: the netlist goes with the copper looked at
  if (state.arrangement !== asked && state.run && state.run.drawn && state.drawn.length) await routeDrawn();
}

// The box under the controls: what the netlist holds, with a way to take each bridge out, to clear it, and to
// start it from the bridges of the case shown.
function renderDrawn() {
  const box = $("drawn");
  box.hidden = Boolean(STATIC);
  if (STATIC) return;
  box.replaceChildren();
  const shown = caseToAddTo();
  const idle = (act) => () => {                    // nothing changes the netlist while a run is out, and a press says so
    if (state.busy) showProblem("A run is in flight: wait for it, then change the netlist made by hand.");
    else act();
  };
  const from = el("button", { type: "button", text: "start from the case shown", disabled: shown && !state.busy ? null : "",
    title: "make the netlist the case shown: its bridges, and its stacking, power and probe settings, to take bridges out "
      + "of or add to. A board's output has its bridges only.",
    onclick: idle(() => { startFromShown(); routeDrawn(); }) });
  if (!state.drawn.length) {
    box.append(el("div", { class: "hint", text: state.from == null
      ? "Click two nodes on the Fabric tab to connect them" + (shown ? ": the bridge is added to the case shown" : "")
        + ". The netlist is routed at once, on the arrangement picked."
      : "From " + nodeName(state.from) + ": click another node to connect it (Esc lets go)." }), from);
    return;
  }
  box.append(el("div", { class: "hint", text: "Made by hand (" + count(state.drawn.length, "bridge")
    + (state.drawnFrom ? ", from " + state.drawnFrom.case + " with its settings" : "") + "), routed on the arrangement picked"
    + (state.from == null ? ". Click two nodes to add one." : ". From " + nodeName(state.from) + ": click another node (Esc lets go).") }));
  const list = el("div", { class: "away" });
  for (const pair of state.drawn) {
    list.append(el("span", { text: nodeName(pair[0]) + " - " + nodeName(pair[1]) + " ×", title: "take this bridge out",
      onclick: idle(() => { state.drawn = state.drawn.filter((p) => p !== pair); routeDrawn(); }) }));
  }
  box.append(list, el("div", { class: "row" },
    el("button", { type: "button", text: "clear", disabled: state.busy ? "" : null,
      onclick: idle(() => { state.drawn = []; state.drawnFrom = null; routeDrawn(); }) }), from));
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
  const drawing = document.querySelector("#fabric svg");
  if (drawing) drawing.classList.toggle("picking", ranking() && state.takeAway.length > 0);
  if (!ranking()) return;
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
    + "\nclick: " + (state.takeAway.includes(name) ? "let it go" : STATIC ? "light it here and in the table" : "pick it: lit here and in the table, and taken away by Run without these");
}

// A click on a ranked wire, in the drawing or on its row, picks it or lets it go. A picked wire is lit in both
// places (its row, and its line in the drawing while the others step back), and picked wires are what "Run
// without these" takes away. An exported page lights them too; only the run is the lab's.
function toggleTakeAway(name) {
  if (!state.ranking || !state.ranking.wires.some((w) => w.wire === name)) return;      // only a wire that is ranked
  const at = state.takeAway.indexOf(name);
  if (at >= 0) state.takeAway.splice(at, 1);
  else state.takeAway.push(name);
  state.justPicked = at >= 0 ? null : name;        // its row is brought into sight
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
    if (r.stale) {
      box.append(el("div", { class: "hint", text: "This ranking is of other copper than " + r.arrangement + "'s file now has "
        + "(the file was edited since). Rank now makes the router's part again; the solver's part is lab.py rank --needed." }));
    }
    if (r.set_aside) {
      box.append(el("div", { class: "hint", text: "The ranking that was here held the solver's columns for other copper or "
        + "other netlists; it is kept beside this one as " + r.set_aside.split("/").pop() + "." }));
    }
  } else {
    box.append(el("div", { text: "No ranking of router " + baseSpec() + " on " + state.arrangement + " yet." }));
  }
  const cannot = a.engine !== "router";
  // an exported page shows the ranking it carries: it cannot make one, nor run the battery without some wires
  const now = STATIC ? null : el("button", { type: "button", text: "Rank now", disabled: state.rankBusy || cannot ? "" : null,
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
  if (!hasNeeded() && !STATIC) {
    box.append(el("div", { class: "hint", text: "Whether a wire is needed is asked of the exact solver, which takes the better "
      + "part of an hour and is not started from here" + (a.json ? ". This arrangement is no file: save its file first (left "
        + "column, under the picker) as arrangements/NAME.json, then:" : ":") }),
      el("pre", { text: "python3 Routing/lab.py rank --needed"
        + (state.arrangement === "v6_feed_off" ? "" : " --arrangement " + (a.json ? "NAME" : JSON.stringify(state.arrangement))) }));
  }
  if (!r) return;

  // wires picked to take away, and the run without them
  const away = el("div", { class: "away" }, state.takeAway.length ? el("span", { class: "hint", style: "border:0;cursor:default",
    text: STATIC ? "lit:" : "picked, to take away:" }) : el("div", { class: "hint", text: "Click a wire, here or in the drawing: it is lit in both"
      + (STATIC ? "." : ", and the battery can be run without the wires picked.") }));
  for (const name of state.takeAway) away.append(el("span", { text: name + " ×", title: "let it go", onclick: () => toggleTakeAway(name) }));
  box.append(away);
  if (state.takeAway.length) {
    box.append(el("div", { class: "ask" },
      STATIC ? null : el("button", { type: "button", text: "Run without these", disabled: state.busy || cannot ? "" : null,
        title: "route the ticked classes on " + state.arrangement + " without these wires, and show it on the Fabric tab",
        onclick: async () => { if (await runBattery(state.takeAway.slice())) showSide("case"); } }),
      el("button", { type: "button", text: "clear", onclick: () => { state.takeAway = []; renderRanking(); drawHeat(); } }),
      STATIC ? null : el("span", { class: "hint", text: "the run's arrangement can then be saved as a file (left column)" })));
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
      "data-wire": w.wire, title: rankTip(w.wire) },
      columns.map((c) => {
        const v = c.show ? c.show(w) : c.of(w);
        return el("td", { text: v == null ? "" : c.signed && v > 0 ? "+" + v : String(v),
          title: c.list && w[c.list] && w[c.list].length ? w[c.list].join("\n") : null });
      })));
  }
  box.append(table);
  if (state.justPicked) {                          // picked in the drawing, its row may be far down the table
    const row = [...table.rows].find((r) => r.dataset.wire === state.justPicked);
    state.justPicked = null;
    if (row) row.scrollIntoView({ block: "nearest" });
  }
  box.append(el("div", { class: "hint", text: "usage counts follow the router's search order and say nothing of need; a negative "
    + "loss is the router doing better without the wire" }));
  if (hasNeeded()) {
    box.append(el("div", { class: "hint", text: "needed: the exact solver proves the netlist cannot be routed without the wire "
      + "(firmware-shaped paths). not needed: a routing without it exists. The router's loss is beside these, not instead of them. "
      + "Each wire is taken away alone: several at once is another question, which \"Run without these\" asks of the router." }));
  }
}

// ---------------------------------------------------------------- starting

// The ranking is in the side panel, and then the fabric wears its tint.
function ranking() {
  return state.side === "ranking";
}

// The view's tabs pick a view and nothing else: the fabric, the KiCad sheet, or the crossbars as the board prints
// them. A view that has a panel of its own (layout.out) has no tab and is always shown.
function showTab(name) {
  if (layout.out.includes(name)) name = Object.keys(VIEWS).find((v) => !layout.out.includes(v));
  state.tab = name;
  say("");
  for (const button of document.querySelectorAll("#tabs button[data-tab]")) {
    const on = button.dataset.tab === name;
    button.classList.toggle("on", on);
    button.setAttribute("aria-pressed", String(on));
    button.hidden = layout.out.includes(button.dataset.tab);
  }
  for (const view of Object.keys(VIEWS)) if (!layout.out.includes(view)) $(view).hidden = view !== name;
  if (name === "sheet" || layout.out.includes("sheet")) loadBackdrop();
  renderArrangement();                             // the sheet's note belongs to the sheet tab
  if (state.current || ranking()) redraw();
  else drawHeat();                                 // nothing routed is shown: only the tint, if any, is taken off
  renderHud();
  keepUi();
}

// The right panel's two faces: the case picked, or the ranking (a lesser view; its tint is drawn on the fabric).
function showSide(name) {
  state.side = name;
  say("");
  for (const button of document.querySelectorAll("#side-tabs button")) {
    const on = button.dataset.side === name;
    button.classList.toggle("on", on);
    button.setAttribute("aria-pressed", String(on));
  }
  $("case").hidden = name === "ranking";
  $("ranking").hidden = name !== "ranking";
  $("case-plate").textContent = name === "ranking" ? "Ranking" : "Case";
  $("case-note").textContent = name === "ranking" ? state.arrangement : (state.selected || "");
  if (name === "ranking") {
    renderRanking();
    loadRanking();
    if (state.tab !== "fabric" && !layout.out.includes("fabric")) return showTab("fabric");     // where its tint is drawn
  }
  if (state.current || ranking()) redraw();
  else drawHeat();
  renderHud();
  keepUi();
}

// The zoom buttons, for the view shown: further out, the whole of it, closer in. The crossbars are text, and their
// size is their zoom.
function zoomView(how, which = state.tab) {
  if (which === "xbar") {
    const now = parseFloat($("xbar").style.getPropertyValue("--xfont")) || 11;
    $("xbar").style.setProperty("--xfont", (how === "fit" ? 11 : Math.max(7, Math.min(22, now + (how === "in" ? 1 : -1)))) + "px");
    return;
  }
  const view = document.querySelector(which === "sheet" ? "#sheet-svg" : "#fabric-svg");
  if (!view) return;
  view.dispatchEvent(how === "fit" ? new Event("fit") : new CustomEvent("zoomby", { detail: how === "in" ? 0.7 : 1 / 0.7 }));
}

// ---------------------------------------------------------------- the panels: where they are, how big, what is shut

// The page is three panels: the tests, the view and the case; and a view (the fabric, the sheet, the crossbars) can
// be given a panel of its own, so that several show at once. They sit in a tree of rows and stacks. Drag a panel
// by its plate onto a side of another and it goes there; drag the line between two to size them; a panel's fold
// button shuts it to its bar. A double-click on a plate puts all of it back. The browser keeps the tree, the sizes
// and what is shut (when it keeps anything). In the one-column page (a phone) the panels keep one order, the view
// first, and only the view's height drags.
const BASE = ["tests", "view", "case"];
const VIEWS = { fabric: "Fabric", sheet: "KiCad sheet", xbar: "Crossbars" };      // each is the id of its element too
const LAYOUT0 = { d: "r", k: ["tests", "view", "case"] };          // d: "r" a row, "c" a stack; k: panels and trees
const SIZE0 = { tests: [490, 320], case: [450, 320] };             // a panel's own width in a row, height in a stack
const LAYOUT_KEY = "lab.layout.v1";
const layout = { tree: LAYOUT0, size: {}, shut: [], out: [] };         // out: the views with panels of their own
const panelsNow = () => BASE.concat(layout.out);

const leaves = (t) => (typeof t === "string" ? [t] : t.k.flatMap(leaves));
const wide = () => window.matchMedia("(min-width: 1201px)").matches;
const panelOf = (name) => document.querySelector('.panel[data-panel="' + name + '"]');

// A tree with nothing spare in it: no row or stack of one, no row straight inside a row.
function layNorm(t) {
  if (typeof t === "string") return t;
  let kids = [];
  for (let c of t.k) {
    c = layNorm(c);
    if (c === null) continue;
    if (typeof c !== "string" && c.d === t.d) kids = kids.concat(c.k);
    else kids.push(c);
  }
  return !kids.length ? null : kids.length === 1 ? kids[0] : { d: t.d, k: kids };
}

function layWithout(t, v) {
  if (typeof t === "string") return t === v ? null : t;
  return { d: t.d, k: t.k.map((c) => layWithout(c, v)).filter((c) => c !== null) };
}

// v beside (left, right) or above or below (top, bottom) the panel `target`
function layPut(t, target, v, side) {
  const want = side === "left" || side === "right" ? "r" : "c";
  const first = side === "left" || side === "top";
  if (t === target) return { d: want, k: first ? [v, t] : [t, v] };
  if (typeof t === "string") return t;
  const kids = [];
  for (const c of t.k) {
    if (c !== target) kids.push(layPut(c, target, v, side));
    else if (t.d === want) kids.push(...(first ? [v, c] : [c, v]));
    else kids.push({ d: want, k: first ? [v, c] : [c, v] });
  }
  return { d: t.d, k: kids };
}

function soundTree(t) {
  if (typeof t === "string") return BASE.includes(t) || t in VIEWS;
  return Boolean(t) && (t.d === "r" || t.d === "c") && Array.isArray(t.k) && t.k.length > 0 && t.k.every(soundTree);
}

function keptLayout() {
  try {
    const kept = JSON.parse(localStorage.getItem(LAYOUT_KEY) || "null");
    if (!kept || !soundTree(kept.tree)) return null;
    const all = leaves(kept.tree);
    const out = all.filter((n) => n in VIEWS);
    // each panel once, the three that are always there among them, and a view left for the tabs
    if (new Set(all).size !== all.length || BASE.some((n) => !all.includes(n)) || out.length >= Object.keys(VIEWS).length) return null;
    const size = {};
    for (const [key, px] of Object.entries(kept.size || {})) if (Number.isFinite(px) && px > 0) size[key] = px;
    return { tree: kept.tree, size: size, out: out,
      shut: (Array.isArray(kept.shut) ? kept.shut : []).filter((n) => n !== "view" && all.includes(n)) };
  } catch (e) { return null; }
}

function keepLayout() {
  try { localStorage.setItem(LAYOUT_KEY, JSON.stringify(layout)); } catch (e) { /* a private window: it lasts for the visit */ }
}

const sizeKey = (c, d) => leaves(c).slice().sort().join("+") + ":" + d;
// a panel's own size when it has one; a row or a stack is as big as the biggest of what it holds would be alone
const sizeOf = (c, d) => layout.size[sizeKey(c, d)]
  || Math.max(...leaves(c).map((n) => (SIZE0[n] ? SIZE0[n][d === "r" ? 0 : 1] : d === "r" ? 460 : 320)));
// the child of a row or a stack that takes what the others leave: the one holding the view, else the last one open
function flexibleOf(t) {
  const open = (c) => !(typeof c === "string" && layout.shut.includes(c));
  const view = t.k.findIndex((c) => leaves(c).includes("view"));
  if (view >= 0) return view;
  for (let i = t.k.length - 1; i >= 0; i--) if (open(t.k[i])) return i;
  return t.k.length - 1;
}

function applySizes() {
  const walk = (t, box) => {
    const kids = [...box.children].filter((n) => !n.classList.contains("split"));
    const flexible = flexibleOf(t);
    t.k.forEach((c, i) => {
      const shut = typeof c === "string" && layout.shut.includes(c);
      // a sized one gives way when there is not room for them all; the flexible one keeps a least size (lab.css)
      kids[i].style.flex = shut ? "0 0 auto" : i === flexible ? "1 1 0" : "0 1 " + sizeOf(c, t.d) + "px";
      kids[i].classList.toggle("flexi", i === flexible && !shut);
      if (typeof c !== "string") walk(c, kids[i]);
    });
  };
  walk(layout.tree, document.querySelector("main"));
  for (const name of panelsNow()) {
    const shut = layout.shut.includes(name);
    panelOf(name).classList.toggle("shut", shut);
    const fold = panelOf(name).querySelector(".fold");
    if (fold) fold.setAttribute("aria-expanded", String(!shut));
  }
  document.querySelector("main").style.setProperty("--view-h", layout.size.under ? layout.size.under + "px" : "");
  if (!layout.size.under) document.querySelector("main").style.removeProperty("--view-h");
}

// The line between child i-1 and child i of a row or a stack: drag it to size them, double-click to put it back,
// and with the keyboard the arrows move it.
function splitBetween(t, i) {
  const bar = el("div", { class: "split " + (t.d === "r" ? "ew" : "ns"), role: "separator", tabindex: "0",
    title: "drag to size the panels; double-click to put it back" });
  const sized = () => (i - 1 !== flexibleOf(t) ? i - 1 : i);      // the one of the two that has a size of its own
  const nodeOf = (n) => [...bar.parentNode.children].filter((x) => !x.classList.contains("split"))[n];
  const span = (node) => (t.d === "r" ? node.getBoundingClientRect().width : node.getBoundingClientRect().height);
  const set = (which, px) => {
    const most = span(bar.parentNode) - 160;
    layout.size[sizeKey(t.k[which], t.d)] = Math.round(Math.max(150, Math.min(most, px)));
    applySizes();
  };
  bar.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    const which = sized();
    const from = t.d === "r" ? event.clientX : event.clientY;
    const was = span(nodeOf(which));
    const sign = which === i - 1 ? 1 : -1;
    bar.classList.add("on");
    document.body.classList.add("sizing");
    const move = (e) => set(which, was + sign * ((t.d === "r" ? e.clientX : e.clientY) - from));
    const done = () => {
      bar.classList.remove("on");
      document.body.classList.remove("sizing");
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", done);
      window.removeEventListener("pointercancel", done);
      keepLayout();
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", done);
    window.addEventListener("pointercancel", done);
  });
  bar.addEventListener("dblclick", () => { delete layout.size[sizeKey(t.k[sized()], t.d)]; applySizes(); keepLayout(); });
  bar.addEventListener("keydown", (event) => {
    const step = { ArrowLeft: -24, ArrowUp: -24, ArrowRight: 24, ArrowDown: 24 }[event.key];
    if (!step) return;
    event.preventDefault();
    event.stopPropagation();                       // the arrows are the line's here, not a list's
    const which = sized();
    set(which, span(nodeOf(which)) + (which === i - 1 ? step : -step));
    keepLayout();
  });
  return bar;
}

// A view's own panel: made when the view is first given one. The view itself moves into it and is drawn there.
const viewPanels = {};

function viewPanel(name) {
  let panel = viewPanels[name];
  const view = $(name);                            // null while its panel is out of the page, and then it is in it
  if (panel) {
    if (view && view.parentNode !== panel) { view.hidden = false; panel.append(view); }
    return panel;
  }
  const number = String(4 + Object.keys(VIEWS).indexOf(name)).padStart(2, "0");
  panel = el("section", { class: "panel viewpanel", "data-panel": name },
    el("header", { class: "bar" },
      el("span", { class: "plate", title: "drag onto a side of another panel to move this one there; double-click to put the panels back" },
        el("b", { text: number }), " " + VIEWS[name]),
      el("span", { class: "bar-note" }),
      ...[["out", "\u2212", "further out"], ["fit", "fit", "the whole drawing"], ["in", "+", "closer in"]].map(([how, text, title]) =>
        el("button", { type: "button", class: "quiet", text: text, title: title, onclick: () => zoomView(how, name) })),
      el("button", { type: "button", class: "quiet", text: "tabs", title: "put this view back among the view's tabs", onclick: () => dockBack(name) }),
      el("button", { type: "button", class: "fold", title: "fold this panel away, or open it", "aria-expanded": "true" })));
  view.hidden = false;
  panel.append(view);
  wirePanel(panel, name);
  viewPanels[name] = panel;
  return panel;
}

// The tree as nested boxes in <main>, the panels moved into their places (they are never made again). A view
// with a panel of its own gets it; one that has lost its panel goes back among the view's tabs.
function buildLayout() {
  const root = document.querySelector("main");
  const panels = {};
  for (const view of Object.keys(VIEWS)) {
    if (layout.out.includes(view)) viewPanel(view);
    else if ($(view).parentNode !== $("centre")) {
      $("centre").insertBefore($(view), $("zoom"));
      $(view).hidden = state.tab !== view;
      viewPanels[view].remove();
    }
  }
  for (const name of panelsNow()) panels[name] = name in VIEWS ? viewPanel(name) : panelOf(name);
  for (const name of panelsNow()) panels[name].remove();
  root.replaceChildren();
  const make = (t, box) => {
    box.classList.add(t.d === "r" ? "vrow" : "vcol");
    box.classList.remove(t.d === "r" ? "vcol" : "vrow");
    t.k.forEach((c, i) => {
      if (i) box.append(splitBetween(t, i));
      box.append(typeof c === "string" ? panels[c] : make(c, el("div", {})));
    });
    return box;
  };
  make(layout.tree, root);
  applySizes();
}

function movePanel(v, target, side) {
  let t = layNorm(layPut(layNorm(layWithout(layout.tree, v)) || target, target, v, side));
  if (typeof t === "string") t = { d: "r", k: [t] };
  layout.tree = t;
  buildLayout();
  keepLayout();
}

function resetLayout() {
  layout.tree = LAYOUT0;
  layout.size = {};
  layout.shut = [];
  layout.out = [];
  buildLayout();
  showTab(state.tab);
  keepLayout();
}

// Give a view a panel of its own, on a side of another panel. One view always stays among the tabs.
function popOut(view, target, side) {
  if (layout.out.includes(view)) return;
  if (layout.out.length + 1 >= Object.keys(VIEWS).length) {
    say("One view stays in the view panel: put another back among its tabs first.");
    return;
  }
  layout.out.push(view);
  layout.tree = layNorm(layPut(layout.tree, target, view, side));
  buildLayout();
  showTab(state.tab);                              // the tabs that are left, and one of them shown
  keepLayout();
}

// Put a view back among the view panel's tabs, and show it there.
function dockBack(view) {
  layout.out = layout.out.filter((v) => v !== view);
  layout.shut = layout.shut.filter((n) => n !== view);
  layout.tree = layNorm(layWithout(layout.tree, view));
  buildLayout();
  showTab(view);
  keepLayout();
}

// Where a panel being dragged would go: the panel nearest the pointer, and the side of it the pointer is at.
let dropLine = null;

function dropPlace(x, y, skip) {
  let best = null;
  for (const name of panelsNow()) {
    if (name === skip) continue;
    const r = panelOf(name).getBoundingClientRect();
    const ox = x < r.left ? r.left - x : x > r.right ? x - r.right : 0;
    const oy = y < r.top ? r.top - y : y > r.bottom ? y - r.bottom : 0;
    const far = Math.hypot(ox, oy);
    if (best && far >= best.far) continue;
    const fx = (x - (r.left + r.right) / 2) / Math.max(1, r.width);
    const fy = (y - (r.top + r.bottom) / 2) / Math.max(1, r.height);
    best = { v: name, r: r, far: far, side: Math.abs(fx) >= Math.abs(fy) ? (fx < 0 ? "left" : "right") : (fy < 0 ? "top" : "bottom") };
  }
  return best;
}

// A drag that moves a panel: from a plate (the panel itself) or from a view's tab (the view, into a panel of its
// own). Nothing moves until the pointer has gone 6 px; a line shows where the drop would put it; Escape calls it off.
function dragToPlace(handle, skip, dimmed, drop) {
  handle.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || !wide()) return;
    const from = [event.clientX, event.clientY];
    let on = false;
    let to = null;
    const move = (e) => {
      if (!on) {
        if (Math.abs(e.clientX - from[0]) + Math.abs(e.clientY - from[1]) < 6) return;
        on = true;
        dimmed().classList.add("moving");
        document.body.classList.add("paneldrag");
      }
      to = dropPlace(e.clientX, e.clientY, skip);
      if (!to) return;
      if (!dropLine) { dropLine = el("div", { class: "dropbar" }); document.body.append(dropLine); }
      const across = to.side === "left" || to.side === "right";
      dropLine.style.left = (to.side === "right" ? to.r.right - 4 : to.r.left) + "px";
      dropLine.style.top = (to.side === "bottom" ? to.r.bottom - 4 : to.r.top) + "px";
      dropLine.style.width = (across ? 4 : to.r.width) + "px";
      dropLine.style.height = (across ? to.r.height : 4) + "px";
    };
    const end = (done) => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", cancel);
      window.removeEventListener("keydown", key, true);
      if (dropLine) dropLine.remove();
      dropLine = null;
      dimmed().classList.remove("moving");
      document.body.classList.remove("paneldrag");
      if (on) {                                      // the click that ends the drag is not a click on the handle,
        handle.dataset.dragged = "1";                // and when the drag ends elsewhere there is no such click to wait for
        setTimeout(() => { delete handle.dataset.dragged; }, 0);
      }
      if (done && on && to) drop(to);
    };
    const up = () => end(true);
    const cancel = () => end(false);
    const key = (e) => { if (e.key === "Escape") { e.stopPropagation(); end(false); } };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", cancel);
    window.addEventListener("keydown", key, true);
  });
}

// A panel's bar: its plate moves it (by a drag, or with the plate in focus by the arrow keys), and its fold button
// shuts it.
function wirePanel(panel, name) {
  const plate = panel.querySelector(".plate");
  dragToPlace(plate, name, () => panel, (to) => movePanel(name, to.v, to.side));
  plate.addEventListener("dblclick", resetLayout);
  plate.tabIndex = 0;
  plate.setAttribute("role", "button");
  plate.setAttribute("aria-label", "the " + name + " panel: an arrow key moves it to that side of the "
    + (name === "view" ? "tests" : "view") + ", Home puts the panels back");
  plate.addEventListener("keydown", (event) => {
    const side = { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "top", ArrowDown: "bottom" }[event.key];
    if (!side && event.key !== "Home") return;
    event.preventDefault();
    event.stopPropagation();                       // the keys are the plate's here, not a list's
    if (event.key === "Home") resetLayout();
    else if (wide()) movePanel(name, name === "view" ? "tests" : "view", side);
    if (panelOf(name)) panelOf(name).querySelector(".plate").focus();      // taken out and put back: its plate keeps the keys
  });
  const fold = panel.querySelector(".fold");
  if (fold) {
    fold.addEventListener("click", () => {
      const at = layout.shut.indexOf(name);
      if (at >= 0) layout.shut.splice(at, 1);
      else layout.shut.push(name);
      applySizes();
      keepLayout();
    });
  }
}

function installPanels() {
  const kept = keptLayout();
  if (kept) Object.assign(layout, kept);
  for (const name of BASE) wirePanel(panelOf(name), name);
  buildLayout();
  // a view's tab, dragged onto a side of a panel, gives the view a panel of its own there; the dock button does the
  // same for the view shown, under the tests
  for (const button of document.querySelectorAll("#tabs button[data-tab]")) {
    dragToPlace(button, null, () => button, (to) => popOut(button.dataset.tab, to.v, to.side));
  }
  $("pop").addEventListener("click", () => popOut(state.tab, "tests", "bottom"));
  // the one-column page: the view's lower edge drags its height
  const grip = el("div", { class: "grip under", title: "drag to size the drawing; double-click to put it back" });
  grip.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    grip.classList.add("on");
    const move = (e) => {
      const asked = e.clientY - $("centre").getBoundingClientRect().top;
      layout.size.under = Math.round(Math.max(0.2 * window.innerHeight, Math.min(0.8 * window.innerHeight, asked)));
      applySizes();
    };
    const done = () => {
      grip.classList.remove("on");
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", done);
      window.removeEventListener("pointercancel", done);
      keepLayout();
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", done);
    window.addEventListener("pointercancel", done);
  });
  grip.addEventListener("dblclick", () => { delete layout.size.under; applySizes(); keepLayout(); });
  $("centre").append(grip);
}

// ---------------------------------------------------------------- the arrow keys

// Up and Down move through a list: the battery (another case is shown), the case's bridges and nets (another is
// lit), or on the Ranking tab its lanes (another is lit). Right goes to the case's list and Left back to the
// battery. Home and End go to a list's ends. Escape lets go of what is lit.
function keyList() {
  if (ranking()) {
    return { rows: [...document.querySelectorAll("#ranking tr.case")], at: (tr) => tr.classList.contains("take"),
      go: (tr) => {
        if (state.takeAway.length > 1) return;     // several are picked: they are a set, not a place in the list
        state.takeAway = [tr.dataset.wire];
        state.justPicked = tr.dataset.wire;
        renderRanking();
        drawHeat();
        say(rankTip(tr.dataset.wire));
      } };
  }
  if (state.keys === "case") {
    return { rows: [...document.querySelectorAll("#case .bridges tr[data-bridge-key], #case .net")],
      at: (row) => (state.bridge ? row.dataset.bridgeKey === state.bridge : row.classList.contains("net") && row.classList.contains("on")),
      go: (row) => {
        letGo();
        if (row.dataset.bridgeKey) state.bridge = row.dataset.bridgeKey;
        state.isolated = row.dataset.net == null ? null : Number(row.dataset.net);
        applyIsolation();
        row.scrollIntoView({ block: "nearest" });
      } };
  }
  return { rows: [...document.querySelectorAll("#battery .case")], at: (tr) => tr.classList.contains("on"),
    go: (tr) => { selectCase(tr.dataset.case); tr.scrollIntoView({ block: "nearest" }); } };
}

function installKeys() {
  window.addEventListener("keydown", (event) => {
    const t = event.target;
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    if (t instanceof HTMLTextAreaElement || t instanceof HTMLSelectElement || (t && t.isContentEditable)) return;
    if (t instanceof HTMLInputElement && !["checkbox", "radio", "button"].includes(t.type)) return;      // typing
    if (event.key === "Escape") {
      if (ranking() && state.takeAway.length) {
        state.takeAway = [];
        renderRanking();
        drawHeat();
        say("");
      } else letGo();
      if (state.only) onlyKind(null);
      return;
    }
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      if (ranking()) return;
      state.keys = event.key === "ArrowRight" && state.current ? "case" : "battery";
      event.preventDefault();
      return;
    }
    const step = { ArrowDown: 1, ArrowUp: -1 }[event.key];
    if (!step && event.key !== "Home" && event.key !== "End") return;
    const list = keyList();
    if (!list.rows.length) return;
    event.preventDefault();
    const at = list.rows.findIndex(list.at);
    const to = event.key === "Home" ? 0 : event.key === "End" ? list.rows.length - 1
      : at < 0 ? (step > 0 ? 0 : list.rows.length - 1) : Math.max(0, Math.min(list.rows.length - 1, at + step));
    if (to !== at) list.go(list.rows[to]);
  });
}

async function start() {
  state.info = await api("/api/info");
  // an exported page is of one run: it carries that run's arrangement (its drawing and its nodes) and no other
  if (STATIC && STATIC.run.arrangement) state.arrangement = STATIC.run.arrangement.name;
  state.v5nodes = state.info.nodes;                // V5's own, whatever arrangement is picked later
  state.ohms = state.info.ohms;
  $("ohms").value = state.ohms;
  $("verified").hidden = state.info.verified;
  for (const v of state.info.variants) $("variant-list").append(el("option", { value: v.spec }));
  for (const name of state.info.classes) {
    const about = (state.info.about || {})[name] || {};     // what the class is, on hover, and how many cases it runs
    $("classes").append(el("label", { title: about.what ? name + ": " + about.what : null },
      el("input", { type: "checkbox", value: name, checked: ["example", "dense", "real", "stress", "edge"].includes(name) ? "" : null }),
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
      // the netlist made by hand goes with the copper looked at (a route in flight routes it again by itself when done)
      if (state.run && state.run.drawn && !state.busy) await routeDrawn();
    } catch (err) {                                // a file that has gained a mistake since the list was made
      $("arrangement").value = state.arrangement;
      showProblem(err.message + (err.data && err.data.problems ? ":\n" + err.data.problems.join("\n") : ""));
    }
  });

  installPanels();
  installKeys();
  for (const key of document.querySelectorAll("#legend .key[data-kind]")) {
    key.addEventListener("click", () => onlyKind(key.dataset.kind));
    key.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onlyKind(key.dataset.kind); } });
  }
  for (const button of document.querySelectorAll("#zoom button")) button.addEventListener("click", () => zoomView(button.dataset.zoom));
  for (const button of document.querySelectorAll("#side-tabs button")) button.addEventListener("click", () => showSide(button.dataset.side));
  $("controls").addEventListener("submit", (event) => { event.preventDefault(); runBattery(); });
  $("ohms").addEventListener("input", () => {
    state.ohms = Number($("ohms").value) || state.info.ohms;
    renderBattery();
    if (state.current) renderCase();
  });
  $("show-tests").addEventListener("change", () => { state.tests = $("show-tests").checked; renderBattery(); });
  $("filter-unclean").addEventListener("change", renderBattery);
  $("filter-changed").addEventListener("change", renderBattery);
  for (const button of document.querySelectorAll("#tabs button[data-tab]")) {
    button.addEventListener("click", () => {
      if (button.dataset.dragged) return delete button.dataset.dragged;      // it was dragged out, not clicked
      showTab(button.dataset.tab);
    });
    button.setAttribute("aria-pressed", String(button.classList.contains("on")));
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
  $("link-row").hidden = Boolean(STATIC);          // an exported page has no judge to show a board's routing with
  if (!STATIC) installLink();

  if (STATIC) {
    $("side-tabs").hidden = !STATIC.rank;         // the ranking's face is there when one travelled
    for (const id of ["variant", "baseline", "arrangement", "run", "live"]) $(id).disabled = true;
    // what cannot be changed here is said once, in words ("Shown:"), and takes no room: the table is what there is to use
    for (const id of ["variant", "arrangement"]) $(id).closest("label").hidden = true;
    $("baseline").closest("label").hidden = !STATIC.run.baseline;
    $("run").closest(".row").hidden = true;
    $("classes").hidden = true;
    $("exported").hidden = false;
    $("exported").textContent = "exported " + STATIC.when + " from " + STATIC.run.variant.name;
    $("variant").value = STATIC.run.variant.name;
    if (STATIC.run.baseline) $("baseline").value = STATIC.run.baseline.name;
    state.run = STATIC.run;
    const kept = keptUi();                         // where this page was left
    if (kept.sort && COLUMNS[kept.sort.col]) state.sort = { col: kept.sort.col, down: Boolean(kept.sort.down) };
    if (kept.closed && typeof kept.closed === "object") Object.assign(state.closed, kept.closed);
    $("filter-unclean").checked = Boolean(kept.unclean);
    state.tests = Boolean(kept.tests);
    renderRegressions();
    renderBattery();
    // where it was left; else the first example; else, on a page of tests alone, the first that is not clean
    const first = state.run.rows.find((r) => r.case === kept.selected) || state.run.rows.find((r) => r.cls === "example")
      || state.run.rows.find(unclean) || state.run.rows[0];
    if (first) await selectCase(first.case);
    showTab(kept.tab in VIEWS ? kept.tab : state.tab);       // and the tabs of the views that have panels of their own go
    if (kept.side === "ranking" && STATIC.rank) showSide("ranking");
  } else if (layout.out.length) showTab(state.tab);
}

start().catch((err) => {
  $("build-error").hidden = false;
  $("build-error").textContent = "The page could not start: " + err.message;
});
