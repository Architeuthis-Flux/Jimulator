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

const FAST = { POLL_MS: 4, PROBE_MS: 80, STALL_MS: 60, WAIT_SAY_MS: 30 };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function linked(port, opts) {
  const seen = { readings: [], states: [] };
  const link = new P.BoardLink(port, { reading: (r) => seen.readings.push(r), state: (name, words) => seen.states.push([name, words]) },
    Object.assign({}, FAST, opts));
  return [link, seen];
}
const built = () => new P.FakePort(fs.readFileSync(TRACE, "utf8"));
const HEAD = '{"h":1,"what":"routing lab port 7 trace","source":"built","fw":null,"about":"made in a test"}\n';
const made = (steps) => new P.FakePort(HEAD + steps.map((s, i) => JSON.stringify(Object.assign({ t: i }, s))).join("\n") + "\n");
const N = { sent: "N", got: NETS };
const VER = { sent: ":ver\n", got: ":ver\r\nJumperless firmware version: 0.0.0.0\r\n" };
const gen = (n, idle, times) => ({ sent: ":gen\n", got: ":gen\r\ngen{" + n + "," + idle + "}\r\n", times: times || 1 });
const paths = (name) => ({ sent: ":paths\n", got: pathsReply(name) });
const dump = (name) => ({ sent: ":crossbar\n", got: cap(name, ".xbar.txt") });
const xbarOfCase = (name) => P.xbarOf(cap(name, ".xbar.txt"));

test("a port that is not port 7 gets one byte and is closed", async () => {     // Review Focus 1
  const port = made([{ sent: "N", got: "\r\n\tMenu\r\n\tm = show this menu\r\n" }]);
  await assert.rejects(linked(port)[0].connect(), (e) => e.kind === "not_port_7");
  assert.deepEqual([port.written, port.closed], [["N"], true]);
  const held = made([N]);
  held.open = async () => { throw Object.assign(new Error("Failed to open serial port."), { name: "NetworkError" }); };
  await assert.rejects(linked(held)[0].connect(), (e) => e.kind === "busy");
  assert.deepEqual(held.written, []);
});

test("firmware without :gen or :paths is too old, and nothing is sent in their place", async () => {   // Review Focus 4
  const old = made([N, VER, { sent: ":gen\n", got: refused("gen") }]);
  await assert.rejects(linked(old)[0].connect(), (e) => e.kind === "too_old" && e.fw === "0.0.0.0");
  assert.deepEqual([old.written, old.closed], [["N", ":ver\n", ":gen\n"], true]);
  const half = made([N, VER, gen(3, 1, 2), { sent: ":paths\n", got: refused("paths") }]);
  const [link, seen] = linked(half);
  await link.connect();
  await link.run();                                                             // it ends by itself
  assert.equal(seen.states.at(-1)[0], "too_old");
  assert.deepEqual([half.written, seen.readings, half.closed], [["N", ":ver\n", ":gen\n", ":gen\n", ":paths\n"], [], true]);
});

test("a still board is asked its generation and nothing else", async () => {    // Review Focus 7, 10
  const port = built();
  const [link, seen] = linked(port);
  assert.deepEqual(await link.connect(), { fw: "0.0.0.0" });
  assert.deepEqual(port.written, ["N", ":ver\n", ":gen\n"]);
  link.run();
  while (seen.readings.length < 4) await sleep(5);
  await sleep(60);                                                              // many polls of a board that stands
  await link.close();
  assert.deepEqual(seen.readings.map((r) => r.gen), [3, 5, 7, 9]);
  assert.deepEqual(seen.readings.map((r) => r.xbar),
    ["same_chip_pairs", "sf_to_sf", "k_rows_overflow_metric", "same_chip_pairs"].map(xbarOfCase));
  assert.ok(seen.readings.every((r) => P.reportOf(r.b)));
  assert.equal(port.written.filter((w) => w === ":paths\n").length, 4);         // one report a routing, not one a tick
  assert.deepEqual([...new Set(port.written)].sort(), P.BOARD_PORT.SENDS.slice().sort());      // the five, and no other byte
  assert.equal(port.most, 1);                                                   // never two queries out
});

test("a routing that moved between the report and the dump is read again", async () => {   // Review Focus 3
  const port = made([N, VER, gen(3, 1, 2), paths("same_chip_pairs"), dump("sf_to_sf"), gen(5, 1),
    paths("sf_to_sf"), dump("sf_to_sf"), gen(5, 1, 3)]);
  const [link, seen] = linked(port);
  await link.connect();
  link.run();
  while (seen.readings.length < 1) await sleep(5);
  await sleep(40);
  await link.close();
  assert.deepEqual(seen.readings.map((r) => [r.gen, r.xbar]), [[5, xbarOfCase("sf_to_sf")]]);
  assert.equal(port.written.filter((w) => w === ":paths\n").length, 2);
});

test("a silent board is waited for, not asked again", async () => {             // Review Focus 2
  const port = built();
  const [link, seen] = linked(port);
  await link.connect();
  link.run();
  while (seen.readings.length < 1) await sleep(5);
  port.hush();
  await sleep(40);
  const sent = port.written.length;
  await sleep(200);
  assert.ok(port.written.length <= sent + 1);                                   // at most the one that was on its way
  assert.equal(seen.states.at(-1)[0], "waiting");
  assert.match(seen.states.at(-1)[1], /probe mode/);
  port.speak();
  while (seen.states.at(-1)[0] !== "live") await sleep(5);
  await link.close();
});

test("a reply cut short is asked once more", async () => {                      // Review Focus 5
  const port = built();
  const [link, seen] = linked(port);
  await link.connect();
  port.cut(8);                                                                  // the loop's first :gen stops at ":gen\r\nge"
  link.run();
  while (seen.readings.length < 1) await sleep(5);
  await link.close();
  assert.deepEqual(port.written.slice(3, 6), [":gen\n", ":gen\n", ":paths\n"]);
  assert.deepEqual([seen.readings[0].gen, seen.readings[0].xbar], [3, xbarOfCase("same_chip_pairs")]);
});

test("bytes nobody asked for, read again, a pulled cable", async () => {        // Review Focus 6, 9, 13
  const port = built();
  const [link, seen] = linked(port);
  await link.connect();
  port.add("oled_b64{128x32:AAAA}\r\n");
  link.run();
  while (seen.readings.length < 4) await sleep(5);
  link.again();                                                                 // the number stands: read all the same
  while (seen.readings.length < 5) await sleep(5);
  assert.equal(seen.readings[4].gen, 9);
  port.pull();
  while (seen.states.at(-1)[0] !== "lost") await sleep(5);
  const trace = link.trace().trim().split("\n").map((line) => JSON.parse(line));
  assert.equal(trace[0].source, "board");
  assert.deepEqual(trace.slice(1, 5).map((e) => e.sent), ["N", ":ver\n", ":gen\n", ":gen\n"]);
  assert.ok(trace[4].got.includes("oled_b64{128x32:AAAA}") && P.genOf(trace[4].got).n === 3);   // kept, with the reply after them
  assert.ok(trace.length < 40 && trace.some((e) => e.times > 2));              // the polls of a still board are one line
});

(async () => {
  for (const [name, fn] of tests) {
    try { await fn(); } catch (e) { console.log("FAIL " + name + "\n" + (e.stack || e)); process.exitCode = 1; }
  }
  console.log(tests.length + " tests");
})();
