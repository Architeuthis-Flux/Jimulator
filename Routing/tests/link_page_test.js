// SPDX-License-Identifier: MIT
// The page's connectBoard (web/lab.js) under node, with board_port.js for the link and stubs for the page around it:
// after a connect that fails, the page is back to "not linked", says why in the page's own words, and a port that
// failed is not used again without the picker. Usage: node link_page_test.js WEB_DIR
"use strict";
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const web = process.argv[2];
const port7 = require(path.join(web, "board_port.js"));
const js = fs.readFileSync(path.join(web, "lab.js"), "utf8");
const piece = (start) => { const i = js.indexOf(start); assert.ok(i >= 0, start); return js.slice(i, js.indexOf("\n}\n", i) + 2); };
const line = (start) => { const i = js.indexOf(start); assert.ok(i >= 0, start); return js.slice(i, js.indexOf("\n", i) + 1); };
const statement = (start) => { const i = js.indexOf(start); assert.ok(i >= 0, start); return js.slice(i, js.indexOf(";\n", i) + 2); };

// A port whose open throws: as a held port does (NetworkError), or for any other reason.
const portThatThrows = (name) => ({ open: async () => { const e = new Error(name); e.name = name; throw e; }, close: async () => {} });

// A fake port answering these exchanges (JSON Lines, as a trace has them).
const NETS = '{\r\n  "nets": []\r\n}\r\n';
const fake = (steps) => new port7.FakePort(steps.map((s) => JSON.stringify(s)).join("\n") + "\n");
const FAST = { POLL_MS: 4, PROBE_MS: 80, STALL_MS: 60, WAIT_SAY_MS: 30 };

async function connectWith(port) {
  const said = [];
  const ctx = Object.assign({ said: said, console: console }, port7);
  ctx.BoardLink = class extends port7.BoardLink { constructor(p, on) { super(p, on, FAST); } };   // the probe not 1.5 s
  ctx.state = { info: { replay: false }, link: { link: null, name: "idle", words: "", fw: null, moved: null, held: null, granted: [port],
    run: null, first: true, posting: false, movedAt: null } };
  ctx.renderLink = () => { said.push([ctx.state.link.name, ctx.state.link.words]); };
  ctx.showReading = () => {};
  ctx.showProblem = (t) => { throw new Error("showProblem: " + t); };
  ctx.picked = 0;                                                     // times the picker was opened
  ctx.navigator = { serial: { requestPort: async () => { ctx.picked++; throw Object.assign(new Error("none"), { name: "NotFoundError" }); } } };
  vm.createContext(ctx);
  vm.runInContext(statement("const tooOld = ") + line("const linkOpen = ") + piece("function linkSaid(") + piece("async function connectBoard(")
    + "\nthis.connectBoard = connectBoard; this.linkOpen = linkOpen;", ctx);
  await ctx.connectBoard();
  return ctx;
}

// After a failed connect: not linked, in this state, with these words; and the next click opens the picker.
async function failed(port, state, words) {
  const ctx = await connectWith(port);
  assert.strictEqual(ctx.linkOpen(), false, state + ": the page still thinks it is linked");
  assert.strictEqual(ctx.state.link.name, state);
  assert.strictEqual(ctx.state.link.held, null, state);
  for (const w of words) assert.ok(ctx.state.link.words.includes(w), state + ": " + JSON.stringify(ctx.state.link.words));
  assert.deepStrictEqual(ctx.state.link.granted, [], state + ": the port that failed is still offered without the picker");
  await ctx.connectBoard();
  assert.strictEqual(ctx.picked, 1, state + ": the second click did not open the picker");
  return ctx;
}

(async () => {
  const busy = await failed(portThatThrows("NetworkError"), "idle",
    ["The port you picked is open in another program or tab (a Jumperlessim viewer, a script). Close it there, then connect again."]);
  assert.ok(!busy.said.some(([, w]) => w.includes("Port 7 is open")), "busy: it names port 7");
  await failed(portThatThrows("InvalidStateError"), "lost", ["InvalidStateError"]);

  // a port that answers N with no net list: the main port's menu, or port 7 of a board in a menu, an app or probe mode
  const menu = fake([{ sent: "N", got: "\r\n\tMenu\r\n\tm = show this menu\r\n" }]);
  await failed(menu, "idle", ["it is not the board's fourth port, or the board was not answering just then",
    "it answers from its main loop only: not in probe mode, a menu or an app", "Nothing but one N was sent to it."]);
  assert.deepStrictEqual([menu.written, menu.forgotten, menu.closed], [["N"], true, true]);

  // firmware too old: the port is the board's fourth, so it is kept for the next click
  const old = fake([{ sent: "N", got: NETS }, { sent: ":ver\n", got: ":ver\r\nJumperless firmware version: 5.7.11.5\r\n" },
    { sent: ":gen\n", got: ':gen\r\n{"error":"unknown_verb","verb":"gen"}\r\n' }]);
  const ctx = await connectWith(old);
  assert.strictEqual(ctx.linkOpen(), false, "too_old: the page still thinks it is linked");
  assert.deepStrictEqual([ctx.state.link.name, ctx.state.link.fw], ["too_old", "5.7.11.5"]);
  assert.ok(ctx.state.link.words.startsWith("This board's firmware (5.7.11.5) is too old for a live view"), ctx.state.link.words);
  assert.deepStrictEqual([old.written, old.closed, ctx.state.link.granted.length], [["N", ":ver\n", ":gen\n"], true, 1]);
  console.log("ok");
})().catch((e) => { console.error(e); process.exit(1); });
