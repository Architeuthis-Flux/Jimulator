// SPDX-License-Identifier: MIT
// Routing lab page. Python does the reckoning (server.py, copper.py,
// fabric_view.py); this file only asks and draws.
"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";
const STATIC = window.LAB_STATIC || null;   // an exported page carries its data and asks nothing
const GREY = "#8a90ad";

const state = {
  info: null,        // /api/info: classes, variants, the fabric layout, node names
  run: null,         // the last good /api/run answer
  cases: {},         // "variant hash/case name" -> {result, paint}
  selected: null,    // case name
  current: null,     // {result, paint} of the selected case
  isolated: null,    // a net number lit alone, or null
  ohms: 60,          // ohms per crosspoint; resistance arrives in crosspoint units
  closed: {},        // class name -> collapsed in the table
  tab: "fabric",
  upload: {},        // dropped file name -> {path, text, choices}
  busy: false,       // a run is in flight
  liveTried: null,   // the last tree hash live mode ran, good build or not
  compare: false,    // draw the selected case against the baseline's routing of it
  base: null,        // {result, paint} of the selected case as the baseline routed it
};

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
  const reply = await fetch(path, init);
  let data = {};
  try { data = await reply.json(); } catch (e) { /* an empty or non-JSON answer */ }
  if (!reply.ok) {
    const err = new Error(data.error || ("the server answered " + reply.status));
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

function nodeName(node) {
  const known = state.info.nodes[String(node)];
  return known ? known.name : String(node);
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
  { head: "ohm", tip: "worst bridge, ohms", better: -1, get: (r) => r.metrics.worst_r, text: (r) => ohmsText(r.metrics.worst_r) },
  { head: "rail", tip: "worst bridge to GND or a rail, ohms", better: -1, get: (r) => r.metrics.rail_worst_r, text: (r) => ohmsText(r.metrics.rail_worst_r) },
  { head: "taps", tip: "scanned nodes with no sense-tap route", better: -1, get: (r) => r.metrics.taps_dead.length },
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
  const tr = el("tr", { class: "class" + (state.closed[name] ? " closed" : "") },
    el("td", { text: name + "  (" + rows.length + ")" }),
    el("td", { text: rows.filter((r) => r.fully_routed).length + "/" + rows.length, title: "cases fully routed" }),
    el("td", { text: String(sum((r) => r.metrics.routed_duplicates)) }),
    el("td", { text: String(sum((r) => r.metrics.crosspoints)) }),
    el("td", { text: ohmsText(worst("worst_r")) }),
    el("td", { text: ohmsText(worst("rail_worst_r")) }),
    el("td", { text: String(sum((r) => r.metrics.taps_dead.length)) }),
    el("td", { text: broken ? String(broken) : "", class: broken ? "problem" : "" }));
  tr.addEventListener("click", () => {
    state.closed[name] = !state.closed[name];
    renderBattery();
  });
  return tr;
}

function renderBattery() {
  const box = $("battery");
  box.replaceChildren();
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
    for (const row of rows) {
      if (onlyUnclean && !unclean(row)) continue;
      if (onlyChanged && !changedFromBase(row)) continue;
      const tr = el("tr", { class: "case" + (row.case === state.selected ? " on" : ""), "data-case": row.case },
        el("td", { text: row.case, title: row.case }), COLUMNS.map((c) => cell(c, row)));
      tr.addEventListener("click", () => selectCase(row.case));
      table.append(tr);
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
    for (const file of event.dataTransfer.files) await addUpload(file.name, await file.text());
  });
}

// ---------------------------------------------------------------- live: re-run when the router's tree changes

function installLive() {
  setInterval(async () => {
    if (!$("live").checked || state.busy || !state.run || Object.keys(state.upload).length) return;
    let hash;
    try { hash = (await api("/api/watch?spec=" + encodeURIComponent(baseSpec()))).hash; } catch (e) { return; }
    // one try per new hash: a tree that does not build is not rebuilt every tick
    if (hash !== state.run.variant.hash && hash !== state.liveTried) {
      state.liveTried = hash;
      await runBattery();
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

async function runBattery() {
  const classes = [...document.querySelectorAll("#classes input:checked")].map((box) => box.value);
  const body = { variant: variantSpec(), baseline: $("baseline").value.trim() || null, classes: classes };
  $("busy").hidden = false;
  state.busy = true;
  try {
    const data = await api("/api/run", body);
    if (data.build_error) {
      showBuildError(data);         // the last good table stays on screen
      return false;
    }
    $("build-error").hidden = true;
    state.run = data;
    state.cases = {};
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
    showBuildError({ build_error: err.message, which: "request" });
    return false;
  } finally {
    $("busy").hidden = true;
    state.busy = false;
  }
}

async function caseOf(variant, name) {
  const key = variant.hash + "/" + name;
  if (!state.cases[key]) {
    state.cases[key] = await api("/api/case?variant=" + encodeURIComponent(variant.hash)
      + "&case=" + encodeURIComponent(name));
  }
  return state.cases[key];
}

async function selectCase(name) {
  if (!state.run) return;
  const current = await caseOf(state.run.variant, name);
  // with compare on, the same case as the baseline routed it
  const base = state.compare && state.run.baseline ? await caseOf(state.run.baseline, name) : null;
  state.selected = name;
  state.current = current;
  state.base = base;
  state.isolated = null;
  for (const tr of document.querySelectorAll("#battery tr.case")) {
    tr.classList.toggle("on", tr.dataset.case === name);
  }
  $("view-title").textContent = name + "   " + state.run.variant.name
    + (base ? "   against " + state.run.baseline.name : "");
  renderCase();
  drawSheet(state.current.paint);
  drawFabric(state.current.paint, base && base.paint);
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

const STATE_WORDS = { routed: "routed", unrouted: "NOT ROUTED", refused: "refused by the safety check",
                      left_out: "left out of every net", rejected: "rejected" };

function renderCase() {
  const box = $("case");
  const { result, paint } = state.current;
  const m = result.metrics;
  box.replaceChildren(
    el("h1", { text: result.case }),
    el("div", {}, el("span", { class: "status " + result.status, text: result.status }),
      el("span", { class: "hint", text: "  " + result.cls })));
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

  if (paint.problems.length) {
    box.append(el("h2", { text: "problems" }),
      el("ul", { class: "problems" }, paint.problems.map((p) => el("li", { text: p }))));
  }

  box.append(el("h2", { text: "bridges" }));
  const bridges = el("table", { class: "bridges" },
    el("tr", {}, ["bridge", "copies", "hops", "ohm"].map((h) => el("th", { text: h }))));
  // with compare on, the baseline's value follows in brackets where it differs
  const before = {};
  for (const b of (state.base ? state.base.paint.bridges : [])) before[b.n1 + "-" + b.n2] = b;
  const versus = (now, was) => (was === undefined || was === now || was === "" ? []
    : [el("span", { class: "was", text: " (" + (was === "" ? "-" : was) + ")" })]);
  for (const b of paint.bridges) {
    const routed = b.state === "routed";
    const old = before[b.n1 + "-" + b.n2];
    const oldRouted = old && old.state === "routed";
    const tr = el("tr", { class: routed ? "" : (b.state === "unrouted" ? "unrouted" : "no") },
      el("td", {}, b.net == null ? null : el("span", { class: "swatch", style: "display:inline-block;margin-right:5px;background:" + netColour(b.net) }),
        nodeName(b.n1) + " - " + nodeName(b.n2) + (b.infra ? "  (probe feed)" : ""),
        routed ? null : el("div", { class: "state", text: STATE_WORDS[b.state] }),
        old && old.state !== b.state ? el("div", { class: "state", text: "baseline: " + STATE_WORDS[old.state] }) : null),
      el("td", {}, routed ? String(b.copies) : "", versus(routed ? String(b.copies) : "", oldRouted ? String(old.copies) : undefined)),
      el("td", { text: routed ? String(b.hops) : "" }),
      el("td", {}, ohmsText(b.r), versus(ohmsText(b.r), oldRouted ? ohmsText(old.r) : undefined)));
    if (b.net != null) tr.addEventListener("click", () => isolate(b.net));
    bridges.append(tr);
  }
  box.append(bridges);

  box.append(el("h2", { text: "nets" }));
  for (const [net, info] of Object.entries(paint.nets)) {
    box.append(el("div", { class: "net", "data-net": net, onclick: () => isolate(Number(net)) },
      el("span", { class: "swatch", style: "background:" + info.colour }),
      el("span", { text: info.label + ":  " + info.nodes.map(nodeName).join(", ") })));
  }

  if (paint.notes.length) {
    box.append(el("h2", { text: "notes" }), el("ul", { class: "notes" }, paint.notes.map((n) => el("li", { text: n }))));
  }
  box.append(el("details", {}, el("summary", { text: "b report" }), el("pre", { text: result.b })));
  applyIsolation();
}

// ---------------------------------------------------------------- pan, zoom, hover

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
  view.addEventListener("wheel", (event) => {
    event.preventDefault();
    const [x, y] = at(event);
    const k = event.deltaY < 0 ? 0.85 : 1 / 0.85;
    if (box[2] * k > widest || box[2] * k < full[2] / 60) return;
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
  const paint = state.current && state.current.paint;
  const w = paint && paint.wires[name];
  const kind = state.info.fabric.wires[name] ? state.info.fabric.wires[name].kind : "";
  if (!w) return name + "  (" + kind + ")";
  const riding = w.nets.length ? w.nets.map(netLabel).join(" and ") : "no net";
  const pins = w.pins.map((p) => "  " + p.chip + "." + p.axis + p.pin + "  "
    + (p.claim == null ? "free" : "claimed for " + netLabel(p.claim))
    + (p.mark === "mismatch" ? "   <- does not match the copper" : "")).join("\n");
  return name + "  (" + w.kind + ")\ncarries: " + riding + (w.nets.length > 1 ? "   SHORT" : "") + "\n" + pins;
}

// ---------------------------------------------------------------- the fabric view

const fabric = { wires: {}, pads: {}, dots: null, marks: null };

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

function drawFabricBase() {
  const f = state.info.fabric;
  const view = svg("svg", { id: "fabric-svg", preserveAspectRatio: "xMidYMid meet" });
  const chips = svg("g", { class: "chips" });
  for (const [name, c] of Object.entries(f.chips)) {
    chips.append(svg("g", { class: "chip" },
      svg("rect", { x: c.x, y: c.y, width: 16 * f.cell, height: 8 * f.cell }),
      svg("text", { x: c.x + 16 * f.cell + 6, y: c.y + 14, text: name })));
  }
  const wires = svg("g", { class: "wires" });
  const hits = svg("g", { class: "hits" });
  for (const [name, w] of Object.entries(f.wires)) {
    const path = svg("path", { class: "wire", d: w.d });
    const hit = svg("path", { class: "hit", d: w.d });
    hover(hit, () => wireTip(name));
    hit.addEventListener("click", () => {
      const live = state.current && state.current.paint.wires[name];
      if (live && live.nets.length === 1) isolate(live.nets[0]);
    });
    wires.append(path);
    hits.append(hit);
    fabric.wires[name] = path;
  }
  const pads = svg("g", { class: "pads" });
  const above = f.chips.I.y;
  for (const [name, p] of Object.entries(f.pads)) {
    const text = p.y < above
      ? svg("text", { x: p.x + 3, y: p.y - 7, transform: "rotate(-60 " + (p.x + 3) + " " + (p.y - 7) + ")", text: p.label })
      : svg("text", { x: p.x, y: p.y + 13, "text-anchor": "middle", text: p.label });
    const g = svg("g", { class: "pad" }, svg("circle", { cx: p.x, cy: p.y, r: 3.6 }), text);
    hover(g, () => wireTip(name));
    pads.append(g);
    fabric.pads[name] = g;
  }
  fabric.dots = svg("g", { class: "dots" });
  fabric.marks = svg("g", { class: "marks" });
  view.append(chips, wires, fabric.dots, pads, fabric.marks, hits);
  $("fabric").replaceChildren(view);
  panZoom(view, [0, 0, f.size[0], f.size[1]]);
}

// With a baseline's paint of the same case: copper only this router closes is
// outlined, copper only the baseline closes is drawn dashed grey.
function drawCompare(paint, base) {
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
    hover(ghost, () => c.chip + "  x" + c.x + " y" + c.y + "\nclosed only by the baseline");
    fabric.dots.append(ghost);
  }
  for (const [name, path] of Object.entries(fabric.wires)) {
    const a = paint.wires[name] && paint.wires[name].nets.length > 0;
    const b = base.wires[name] && base.wires[name].nets.length > 0;
    if (a && !b) path.classList.add("only-a");
    if (b && !a) path.classList.add("only-b");
  }
}

function drawFabric(paint, base) {
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
  if (!paint) return;

  for (const [name, w] of Object.entries(paint.wires)) {
    const path = fabric.wires[name];
    if (!path) continue;
    const pad = fabric.pads[name];
    if (w.nets.length === 1) {
      path.classList.add("live");
      path.style.stroke = netColour(w.nets[0]);
      path.dataset.net = w.nets[0];
      if (pad) {
        pad.classList.add("live");
        pad.firstChild.style.fill = netColour(w.nets[0]);
        pad.dataset.net = w.nets[0];
      }
    } else if (w.nets.length > 1) {
      path.classList.add("live", "short");
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
        stroke: b.state === "unrouted" ? netColour(b.net) : GREY }));
    }
  }
  if (base) drawCompare(paint, base);
  applyIsolation();
}

// ---------------------------------------------------------------- the KiCad sheet view
//
// The board's own schematic as the backdrop, and over it, in the sheet's
// millimetres: the wires and labels of each net-carrying piece of copper, and
// each closed crosspoint as a curve inside its chip from the X pin to the Y pin.

const sheet = { data: null, live: null };

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
      const short = w.nets.length > 1;
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
    const a = s.pins[c.chip + ".X" + c.x];
    const b = s.pins[c.chip + ".Y" + c.y];
    const body = s.bodies[c.chip];
    if (!a || !b || !body) continue;
    // bow into the body, away from the side the pins leave it on
    const width = body[2] - body[0];
    const deep = a[0] > (body[0] + body[2]) / 2 ? body[0] + width * 0.15 : body[2] - width * 0.15;
    const curve = svg("path", { class: "s-curve" + (c.dup ? " dup" : ""), stroke: netColour(c.net), "data-net": c.net,
      d: "M" + a[0] + " " + a[1] + "C" + deep + " " + a[1] + " " + deep + " " + b[1] + " " + b[0] + " " + b[1] });
    hover(curve, () => c.chip + "  x" + c.x + " y" + c.y + "\nnet " + netLabel(c.net) + ", path " + c.path
      + (c.dup ? " (a duplicate)" : ""));
    curve.addEventListener("click", () => isolate(c.net));
    curves.append(curve);
  }

  for (const b of paint.bridges) {                           // what was asked for and is not there
    if (b.state === "routed") continue;
    for (const node of [b.n1, b.n2]) {
      const known = state.info.nodes[String(node)];
      for (const p of (known && s.nets[known.wire] ? s.nets[known.wire].labels : [])) {
        marks.append(svg("circle", { class: "s-want", cx: p[0], cy: p[1], r: 2.4,
          stroke: b.state === "unrouted" ? netColour(b.net) : GREY }));
      }
    }
  }
  sheet.live.append(curves, copper, marks);
}

// ---------------------------------------------------------------- starting

function showTab(name) {
  state.tab = name;
  for (const button of document.querySelectorAll("#tabs button")) {
    button.classList.toggle("on", button.dataset.tab === name);
  }
  $("fabric").hidden = name !== "fabric";
  $("sheet").hidden = name !== "sheet";
}

async function start() {
  state.info = await api("/api/info");
  state.ohms = state.info.ohms;
  $("ohms").value = state.ohms;
  $("verified").hidden = state.info.verified;
  for (const v of state.info.variants) $("variant-list").append(el("option", { value: v.spec }));
  for (const name of state.info.classes) {
    $("classes").append(el("label", {},
      el("input", { type: "checkbox", value: name, checked: ["dense", "real", "stress"].includes(name) ? "" : null }), name));
  }
  drawFabricBase();
  await drawSheetBase();

  $("controls").addEventListener("submit", (event) => { event.preventDefault(); runBattery(); });
  $("ohms").addEventListener("input", () => {
    state.ohms = Number($("ohms").value) || 60;
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
    installLive();
  }

  if (STATIC) {
    for (const id of ["variant", "baseline", "run", "live"]) $(id).disabled = true;
    $("classes").hidden = true;
    $("exported").hidden = false;
    $("exported").textContent = "exported " + STATIC.when + " from " + STATIC.run.variant.name;
    $("variant").value = STATIC.run.variant.name;
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
