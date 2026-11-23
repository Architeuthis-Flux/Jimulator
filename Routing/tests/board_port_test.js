"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const P = require("../web/board_port.js");
const [CAPTURES, TRACE] = process.argv.slice(2);
const cap = (name, ext) => fs.readFileSync(path.join(CAPTURES, name + ext), "utf8");
const tests = [];
const test = (name, fn) => tests.push([name, fn]);
const NETS = '{\r\n  "nets": [\r\n    {\r\n      "index": 6,\r\n      "name": "Net 6",\r\n      "nodes": ["1", "2"],\r\n'
  + '      "special": "",\r\n      "voltage": 1.203\r\n    }\r\n  ]\r\n}\r\n';
const refused = (verb) => ":" + verb + '\r\n{"error":"unknown_verb","verb":"' + verb + '"}\r\n';
const pathsReply = (name) => ":paths\r\n\n\r" + cap(name, ".b.txt").slice(cap(name, ".b.txt").indexOf("Bridge Array"));

test("the crossbar dump is found whatever stands around it", () => {            // Review Focus 6
  const reply = cap("same_chip_pairs", ".xbar.txt");                            // the echoed ":crossbar", then the dump
  assert.match(P.xbarOf(reply), /^xbar\{12x8:[0-9a-f]{384}\}$/);
  assert.equal(P.xbarOf(reply.slice(0, 200)), null);
  assert.equal(P.xbarOf("oled_b64{128x32:AAAA}\r\n" + reply), P.xbarOf(reply));
});

test("a report is whole when chip L's row has ended, and not before", () => {
  const files = fs.readdirSync(CAPTURES).filter((f) => f.endsWith(".b.txt"));
  assert.equal(files.length, 21);
  for (const file of files) {
    const text = pathsReply(file.slice(0, -6));
    const whole = P.reportOf(text);
    assert.ok(whole && whole.includes("Bridge Array") && whole.includes("Chip Status"), file);
    assert.equal(P.reportOf(text.slice(0, text.lastIndexOf("\nL") + 20)), null, file);      // inside the last row
    assert.equal(P.reportOf(text.slice(0, text.indexOf("Chip Status"))), null, file);
  }
});

test("the generation, and a board too old to give it", () => {                  // Review Focus 4, 6
  assert.deepEqual(P.genOf(":gen\r\ngen{12,1}\r\n"), { n: 12, idle: true });
  assert.deepEqual(P.genOf("gen{4294967295,0}\r\n"), { n: 4294967295, idle: false });
  assert.equal(P.genOf(":gen\r\n"), null);                                      // the echo alone
  assert.equal(P.genOf(":gen\r\ngen{12,"), null);
  assert.deepEqual(P.genOf("oled_b64{128x32:AAAA}\r\n:gen\r\ngen{4,0}\r\n"), { n: 4, idle: false });
  assert.equal(P.refusedVerb(refused("gen")), "gen");
  assert.equal(P.refusedVerb(":gen\r\ngen{12,1}\r\n"), null);
  assert.equal(P.refusedVerb('{"error":"blocked","cmd":"!","reason":"not_a_command"}\r\n'), null);
});

test("a net list proves port 7, and the main port's menu does not", () => {     // Review Focus 1
  assert.equal(P.netListIn(NETS), true);
  assert.equal(P.netListIn(NETS.slice(0, 60)), false);                          // not all of it yet
  assert.equal(P.netListIn('{"nets":[]}\r\n'), true);
  assert.equal(P.netListIn("\r\n\tMenu\r\n\tm = show this menu\r\n"), false);   // the main port's answer to N
  assert.equal(P.netListIn("oled_b64{128x32:AAAA}\r\n" + NETS), true);
  assert.equal(P.versionOf(":ver\r\nJumperless firmware version: 5.7.11.5\r\n"), "5.7.11.5");
  assert.equal(P.versionOf(":ver\r\nJumperless firmware ver"), null);
  assert.deepEqual(P.BOARD_PORT.SENDS, ["N", ":ver\n", ":gen\n", ":paths\n", ":crossbar\n"]);
});

test("why this browser cannot connect, in words", () => {
  assert.equal(P.serialWhyNot({ serial: {} }, true), null);
  assert.match(P.serialWhyNot({}, true), /Chrome/);
  assert.match(P.serialWhyNot({ serial: {} }, false), /127\.0\.0\.1/);
});

test("the fake port answers from the trace, in order, and then repeats", async () => {
  const port = new P.FakePort(fs.readFileSync(TRACE, "utf8"));
  await port.open({ baudRate: 115200, bufferSize: 65536 });
  const ask = async (text, done) => {
    const w = port.writable.getWriter(), r = port.readable.getReader();
    await w.write(new TextEncoder().encode(text));
    let got = "";
    while (done(got) == null) got += new TextDecoder().decode((await r.read()).value);
    w.releaseLock(); r.releaseLock();
    return done(got);
  };
  const gen = () => ask(":gen\n", P.genOf);
  assert.equal(await ask("N", (t) => P.netListIn(t) || null), true);
  assert.equal(await ask(":ver\n", P.versionOf), "0.0.0.0");
  assert.deepEqual([(await gen()).n, (await gen()).n], [3, 3]);                 // connecting, then the first round
  assert.equal(await ask(":paths\n", P.reportOf), P.reportOf(pathsReply("same_chip_pairs")));
  assert.equal(await ask(":crossbar\n", P.xbarOf), P.xbarOf(cap("same_chip_pairs", ".xbar.txt")));
  for (let i = 0; i < 4; i++) assert.deepEqual(await gen(), { n: 3, idle: true });      // one line, four times
  assert.deepEqual(await gen(), { n: 4, idle: false });                         // the second routing, on its way
  for (let i = 0; i < 60; i++) await gen();                                     // past the end: the last answer again
  assert.deepEqual(await gen(), { n: 9, idle: true });
  assert.equal(await ask(":crossbar\n", P.xbarOf), P.xbarOf(cap("same_chip_pairs", ".xbar.txt")));
  assert.deepEqual([port.most, port.opened.baudRate], [1, 115200]);
});

(async () => {
  for (const [name, fn] of tests) {
    try { await fn(); } catch (e) { console.log("FAIL " + name + "\n" + (e.stack || e)); process.exitCode = 1; }
  }
  console.log(tests.length + " tests");
})();
