// SPDX-License-Identifier: MIT
// The page's connectBoard (web/lab.js) under node, with board_port.js for the link and stubs for the page around it:
// after a connect that fails, the page is back to "not linked". Usage: node link_page_test.js WEB_DIR
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

// A port whose open throws: as a held port does (NetworkError), or for any other reason.
const portThatThrows = (name) => ({ open: async () => { const e = new Error(name); e.name = name; throw e; }, close: async () => {} });

async function connectWith(port) {
  const said = [];
  const ctx = Object.assign({ said: said, console: console }, port7);
  ctx.state = { info: { replay: false }, link: { link: null, name: "idle", words: "", fw: null, moved: null, held: null, granted: [port],
    run: null, first: true, posting: false, movedAt: null } };
  ctx.linkSaid = (name, words) => { ctx.state.link.name = name; said.push([name, words]); };
  ctx.renderLink = () => {};
  ctx.showReading = () => {};
  ctx.showProblem = (t) => { throw new Error("showProblem: " + t); };
  ctx.navigator = {};
  vm.createContext(ctx);
  vm.runInContext(line("const linkOpen = ") + piece("async function connectBoard(") + "\nthis.connectBoard = connectBoard; this.linkOpen = linkOpen;", ctx);
  await ctx.connectBoard();
  return ctx;
}

(async () => {
  for (const [name, state] of [["NetworkError", "idle"], ["InvalidStateError", "lost"]]) {
    const ctx = await connectWith(portThatThrows(name));
    assert.strictEqual(ctx.linkOpen(), false, name + ": the page still thinks it is linked");
    assert.strictEqual(ctx.state.link.name, state, name);
    assert.strictEqual(ctx.state.link.held, null, name);
  }
  console.log("ok");
})().catch((e) => { console.error(e); process.exit(1); });
