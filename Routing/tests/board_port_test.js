"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const P = require("../web/board_port.js");
const [CAPTURES, TRACE, WATCH] = process.argv.slice(2);
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
  assert.deepEqual(P.BOARD_PORT.SENDS, ["N", ":ver\n", ":gen\n", ":paths\n", ":crossbar\n", ":watch:routing:on\n", ":watch:routing:off\n"]);
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

const FAST = { POLL_MS: 4, PROBE_MS: 80, STALL_MS: 60, WAIT_SAY_MS: 30, GAP_MS: 2 };
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
const NOWATCH = { sent: ":watch:routing:on\n", got: ':watch:routing:on\r\n{"error":"unknown_verb","verb":"watch:routing:on"}\r\n' };

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
  const half = made([N, VER, gen(3, 1), NOWATCH, gen(3, 1), { sent: ":paths\n", got: refused("paths") }]);
  const [link, seen] = linked(half);
  await link.connect();
  await link.run();                                                             // it ends by itself
  assert.equal(seen.states.at(-1)[0], "too_old");
  assert.deepEqual([half.written, seen.readings, half.closed], [["N", ":ver\n", ":gen\n", ":watch:routing:on\n", ":gen\n", ":paths\n"], [], true]);
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
  assert.ok(port.written.every((w) => P.BOARD_PORT.SENDS.includes(w)));      // the seven, and no other byte
  assert.ok(!port.written.includes(":watch:routing:off\n"));                  // the watch was refused
  assert.equal(port.most, 1);                                                   // never two queries out
});

test("a routing that moved between the report and the dump is read again", async () => {   // Review Focus 3
  const port = made([N, VER, gen(3, 1), NOWATCH, gen(3, 1), paths("same_chip_pairs"), dump("sf_to_sf"), gen(5, 1),
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
  const take = port.take.bind(port);
  port.take = (text) => { if (port.written.length === 4) port.cut(8); take(text); };   // the loop's first :gen stops at ":gen\r\nge"
  link.run();
  while (seen.readings.length < 1) await sleep(5);
  await link.close();
  assert.deepEqual(port.written.slice(3, 7), [":watch:routing:on\n", ":gen\n", ":gen\n", ":paths\n"]);
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
  assert.equal(trace[0].source, "replay");                                     // a fake port: not a board
  assert.deepEqual(trace.slice(1, 6).map((e) => e.sent), ["N", ":ver\n", ":gen\n", ":watch:routing:on\n", ":gen\n"]);
  assert.ok(trace[4].got.includes("oled_b64{128x32:AAAA}") && P.watchOf(trace[4].got).error === "unknown_verb");   // kept, with the reply after them
  assert.ok(trace.length < 40 && trace.some((e) => e.times > 2));              // the polls of a still board are one line
});

test("the trace says what it was read from", async () => {
  const head = (link) => JSON.parse(link.trace().split("\n")[0]);
  const real = head(new P.BoardLink({}, { reading: () => {}, state: () => {} }));      // a port that is not a FakePort
  assert.deepEqual([real.source, real.about], ["board", "recorded by the routing lab from a board"]);
  const port = built();
  const [link] = linked(port);
  await link.connect();
  await link.close();
  const fake = head(link);
  assert.equal(fake.source, "replay");
  assert.match(fake.about, /replays a trace/);
  assert.match(fake.about, /not a recording from a board/);
});

// Every write the port saw, from the trace: its sent values, a "times" line counted as many.
const sentIn = (trace) => trace.trim().split("\n").map((l) => JSON.parse(l)).filter((e) => !e.h && e.sent !== null)
  .flatMap((e) => Array(e.times || 1).fill(e.sent));

test("a query still unanswered is in the trace: while out, at Disconnect, at a pulled cable", async () => {
  for (const end of ["close", "pull"]) {
    const port = built();
    const [link, seen] = linked(port);
    await link.connect();
    const running = link.run();
    try {
      while (seen.readings.length < 1) await sleep(5);
      port.hush();
      while (!port.waiting.length) await sleep(2);                                // a query is out, unanswered
      assert.deepEqual(sentIn(link.trace()), port.written, end + ": while it is out");
      const last = JSON.parse(link.trace().trim().split("\n").at(-1));
      assert.deepEqual([last.sent, last.got], [port.waiting[0], null], end);
      if (end === "close") await link.close(); else port.pull();
      await running;
      assert.deepEqual(sentIn(link.trace()), port.written, end);
      assert.equal(JSON.parse(link.trace().trim().split("\n").at(-1)).sent, port.waiting[0], end);
    } finally { await link.close(); }                                           // a failed check leaves no link polling
  }
});

const STRAY = "oled_b64{128x32:AAAA}\r\n";

test("a stray line while a query is out is no reply, and the query is not sent again", async () => {
  const port = built();
  const [link, seen] = linked(port);
  await link.connect();
  link.run();
  while (seen.readings.length < 1) await sleep(5);
  port.hush();
  await sleep(20);                                                              // the next :gen is out, unanswered
  const sent = port.written.length;
  port.add(STRAY);
  await sleep(250);                                                             // four STALL_MS of silence after it
  assert.equal(port.most, 1);
  assert.ok(port.written.length <= sent + 1);
  port.speak();
  await link.close();
});

test("bytes between polls do not hurry the next poll", async () => {
  const port = made([N, VER, gen(3, 1), NOWATCH, gen(3, 1), paths("same_chip_pairs"), dump("same_chip_pairs"), gen(3, 1)]);
  const [link, seen] = linked(port, { POLL_MS: 50 });
  await link.connect();
  link.run();
  while (seen.readings.length < 1) await sleep(5);
  const before = port.written.length;
  const chatter = setInterval(() => port.add(STRAY), 2);
  await sleep(300);
  clearInterval(chatter);
  await link.close();
  const polls = port.written.length - before;                                   // about 300 / 50 = 6
  assert.ok(polls >= 2 && polls <= 9, polls + " polls in 300 ms at POLL_MS 50");
});

test("only the timings can be changed: not the speed, not what is sent", async () => {
  const port = built();
  const [link] = linked(port, { BAUD: 9600, BUFFER: 16, SENDS: P.BOARD_PORT.SENDS.concat(["b"]) });
  await link.connect();
  assert.deepEqual(port.opened, { baudRate: 115200, bufferSize: 65536 });
  await assert.rejects(link.send("b"));
  await link.close();
  assert.ok(!port.written.includes("b"));
});

const FASTW = Object.assign({}, FAST, { WATCH_POLL_MS: 400, GAP_MS: 2, OFF_MS: 40 });
const ACK = { sent: ":watch:routing:on\n", got: ':watch:routing:on\r\n{"watch":"routing","state":"on","gen":3}\r\n' };
const OFF = { sent: ":watch:routing:off\n", got: ':watch:routing:off\r\n{"watch":"routing","state":"off","gen":9}\r\n' };
const told = (n) => ({ sent: null, got: "changed{routing," + n + "}\r\n" });

test("the watch's lines and its answers are read by their whole shape", () => {
  assert.equal(P.changedOf("changed{routing,12}"), 12);
  for (const no of ["changed{routing,<n>}", "xchanged{routing,5}", "changed{routing,5} ", "gen{5,1}", ":gen", ""])
    assert.equal(P.changedOf(no), null, no);
  assert.equal(P.genOf("changed{routing,7}\r\n"), null);                       // not a reply to :gen
  assert.deepEqual(P.watchOf(ACK.got), { topic: "routing", on: true, gen: 3 });
  assert.deepEqual(P.watchOf(NOWATCH.got), { error: "unknown_verb" });
  assert.equal(P.watchOf(":watch:routing:on\r\n"), null);                      // the echo alone
  assert.equal(P.watchOf('{"watches":{"routing":"on"}}\r\n'), null);
});

test("a watching board is read when it says so, and asked little else", async () => {   // Review Focus 7
  const port = new P.FakePort(fs.readFileSync(WATCH, "utf8"));
  const [link, seen] = linked(port, FASTW);
  await link.connect();
  link.run();
  while (seen.readings.length < 4) await sleep(5);
  await link.close();
  assert.deepEqual(seen.readings.map((r) => r.gen), [3, 5, 7, 9]);
  assert.equal(port.written.filter((w) => w === ":paths\n").length, 4);
  assert.ok(port.written.filter((w) => w === ":gen\n").length <= 8);          // connect, the first round, one confirm a reading
  assert.equal(port.written.at(-1), ":watch:routing:off\n");
  assert.ok(port.written.every((w) => P.BOARD_PORT.SENDS.includes(w)));
  assert.equal(port.most, 1);
});

test("a line in the chunk of a reply, split in two, and during a query", async () => {  // Review Focus 7
  const port = made([N, VER, gen(3, 1), ACK, gen(3, 1), paths("same_chip_pairs"), dump("same_chip_pairs"),
    { sent: ":gen\n", got: ":gen\r\ngen{3,1}\r\nchanged{routing,5}\r\n" },    // the line rides behind a reply
    paths("sf_to_sf"), dump("sf_to_sf"), gen(5, 1), paths("sf_to_sf"), dump("sf_to_sf"), gen(7, 1, 9), OFF]);
  const [link, seen] = linked(port, FASTW);
  await link.connect();
  link.run();
  while (seen.readings.length < 2) await sleep(5);
  assert.deepEqual(seen.readings.map((r) => r.gen), [3, 5]);                   // not lost with the reply's text
  port.add("changed{rou"); await sleep(20); port.add("ting,7}\r\n");           // one line, two chunks
  while (seen.readings.length < 3) await sleep(5);
  assert.equal(seen.readings[2].gen, 7);
  await link.close();
  const trace = link.trace().trim().split("\n").map((l) => JSON.parse(l));
  assert.ok(trace.some((e) => e.sent === null && /changed\{routing,7\}/.test(e.got)));
});

test("a line that never comes is caught by the slow poll, and a board that cannot watch is polled", async () => {
  const quiet = made([N, VER, gen(3, 1), ACK, gen(3, 1), paths("same_chip_pairs"), dump("same_chip_pairs"), gen(3, 1),
    gen(5, 1), paths("sf_to_sf"), dump("sf_to_sf"), gen(5, 1, 9), OFF]);
  const [link, seen] = linked(quiet, Object.assign({}, FASTW, { WATCH_POLL_MS: 30 }));
  await link.connect();
  link.run();
  while (seen.readings.length < 2) await sleep(5);
  await link.close();
  assert.deepEqual(seen.readings.map((r) => r.gen), [3, 5]);
  const old = built();                                                         // its watch is refused
  const [link2, seen2] = linked(old, FASTW);
  await link2.connect();
  link2.run();
  while (seen2.readings.length < 4) await sleep(5);                            // far sooner than WATCH_POLL_MS allows
  await link2.close();
  assert.ok(!old.written.includes(":watch:routing:off\n"));
});

test("disconnect says off once, within its limit, and not over a query that is out", async () => {
  const port = new P.FakePort(fs.readFileSync(WATCH, "utf8"));
  const [link, seen] = linked(port, FASTW);
  await link.connect();
  link.run();
  while (seen.readings.length < 1) await sleep(5);
  port.hush();                                                                 // the board goes silent
  const t = Date.now();
  await link.close();
  assert.ok(Date.now() - t < 400 && port.most === 1);
  assert.ok(port.written.filter((w) => w === ":watch:routing:off\n").length <= 1);
});

test("a line that rides behind the reply to a round's first :gen starts the next round, with no slow wait", async () => {
  const port = made([N, VER, gen(3, 1), ACK,
    { sent: ":gen\n", got: ":gen\r\ngen{3,1}\r\nchanged{routing,5}\r\n" },    // one chunk: the reply, then the line
    paths("same_chip_pairs"), dump("same_chip_pairs"), gen(3, 1), paths("sf_to_sf"), dump("sf_to_sf"), gen(5, 1), OFF]);
  const [link, seen] = linked(port, Object.assign({}, FASTW, { WATCH_POLL_MS: 5000 }));
  await link.connect();
  const t = Date.now();
  link.run();
  while (seen.readings.length < 2 && Date.now() - t < 2000) await sleep(5);
  await link.close();
  assert.deepEqual(seen.readings.map((r) => r.gen), [3, 5]);                   // not after WATCH_POLL_MS
  assert.equal(port.written.filter((w) => w === ":gen\n").length, 4);          // connect, the first round, a confirm each reading
});

test("disconnect: off once when nothing is out, and not at all over a query that is out", async () => {
  const still = made([N, VER, gen(3, 1), ACK, gen(3, 1), paths("same_chip_pairs"), dump("same_chip_pairs"), gen(3, 1), OFF]);
  const [link, seen] = linked(still, Object.assign({}, FASTW, { WATCH_POLL_MS: 5000 }));
  await link.connect();
  link.run();
  while (seen.readings.length < 1) await sleep(5);                             // idle: nothing out for 5 s
  await link.close();
  assert.equal(still.written.filter((w) => w === ":watch:routing:off\n").length, 1);
  assert.deepEqual([still.written.at(-1), still.closed, still.most], [":watch:routing:off\n", true, 1]);
  const out = made([N, VER, gen(3, 1), ACK, gen(3, 1), { sent: ":paths\n", got: null }, OFF]);   // :paths is never answered
  const [link2] = linked(out, FASTW);
  await link2.connect();
  const running = link2.run();
  while (!out.written.includes(":paths\n")) await sleep(2);
  await sleep(20);
  await link2.close();
  await running;
  assert.deepEqual(out.written, ["N", ":ver\n", ":gen\n", ":watch:routing:on\n", ":gen\n", ":paths\n"]);
  assert.deepEqual([out.closed, out.most], [true, 1]);
});

(async () => {
  for (const [name, fn] of tests) {
    try { await fn(); } catch (e) { console.log("FAIL " + name + "\n" + (e.stack || e)); process.exitCode = 1; }
  }
  console.log(tests.length + " tests");
})();
