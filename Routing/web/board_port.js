// SPDX-License-Identifier: MIT
// A board's port 7, read in the page's own code: what the board answers to the
// seven things the lab ever sends, the lines it writes by itself when watched, and a fake
// port that replays a trace of those exchanges. No DOM, no import; under node the last line exports it.
"use strict";

const BOARD_PORT = {
  FILTER: { usbVendorId: 0x1D50, usbProductId: 0xACAB },   // usb_descriptors.cpp:71-72
  BAUD: 115200,                                            // ArduinoStuff.cpp:212
  BUFFER: 65536,                                           // lineChannel.ts:21
  SENDS: ["N", ":ver\n", ":gen\n", ":paths\n", ":crossbar\n", ":watch:routing:on\n", ":watch:routing:off\n"],   // the only bytes ever sent to a board
  POLL_MS: 500,                                            // the :gen poll of a board that cannot watch
  WATCH_POLL_MS: 3000,                                     // the :gen poll of a watching board, for a changed{} line that was lost
  GAP_MS: 100,                                             // the least time between two rounds
  OFF_MS: 300,                                             // how long Disconnect waits for :watch:routing:off's answer
  PROBE_MS: 1500,                                          // Jumperlessim's probe (engine.ts:31)
  STALL_MS: 3000,                                          // first guess
  WAIT_SAY_MS: 1500,                                       // first guess
  NEEDS: "a JumperlOS release after 5.7.11.5 (not out when this was written)",
};

// Why Web Serial cannot be used here, in words; null when it can.
function serialWhyNot(nav, secure) {
  if (!nav || !nav.serial) return "This browser has no Web Serial. Chrome, Edge, Opera and Brave have it. Paste or drop the board's b output here.";
  if (!secure) return "Web Serial needs a page served over https, or from 127.0.0.1.";
  return null;
}

// True when the text holds a whole JSON object with a "nets" list: the proof of port 7.
function netListIn(text) {
  const start = /\{\s*"nets"\s*:/g;
  let m;
  while ((m = start.exec(text))) {
    let depth = 0, inString = false;
    for (let i = m.index; i < text.length; i++) {
      const c = text[i];
      if (inString) {
        if (c === "\\") i++;
        else if (c === '"') inString = false;
      } else if (c === '"') inString = true;
      else if (c === "{") depth++;
      else if (c === "}" && --depth === 0) {
        try { if (Array.isArray(JSON.parse(text.slice(m.index, i + 1)).nets)) return true; } catch (e) { /* not JSON */ }
        break;
      }
    }
  }
  return false;
}

// The last match of a global pattern in the text, or null.
function lastMatch(re, text) {
  let found = null, m;
  while ((m = re.exec(text))) found = m;
  return found;
}

// The X of "firmware version: X", once its line has ended.
function versionOf(text) {
  const m = lastMatch(/firmware version: ([^\r\n]+)[\r\n]/g, text);
  return m ? m[1] : null;
}

// The last gen{<n>,<i>} in the text: the routing's count, and whether the board is idle.
function genOf(text) {
  const m = lastMatch(/gen\{(\d+),([01])\}/g, text);
  return m ? { n: Number(m[1]), idle: m[2] === "1" } : null;
}

// The verb a board refused as unknown, or null.
function refusedVerb(text) {
  const m = lastMatch(/\{"error":"unknown_verb","verb":"([^"]*)"\}/g, text);
  return m ? m[1] : null;
}

// The answer to :watch:<topic>:on|off, from the last whole line that gives one: {topic, on, gen}, or {error} for a
// refusal (unknown_verb from firmware without :watch, busy in probe mode), or null before either.
function watchOf(text) {
  const lines = text.split("\n").slice(0, -1);
  for (let i = lines.length - 1; i >= 0; i--) {
    const line = lines[i].replace(/\r$/, "");
    const m = /^\{"watch":"([^"]*)","state":"(on|off)","gen":(\d+)\}$/.exec(line);
    if (m) return { topic: m[1], on: m[2] === "on", gen: Number(m[3]) };
    let o = null;
    try { o = JSON.parse(line); } catch (e) { continue; }
    if (o && typeof o === "object" && !Array.isArray(o) && "error" in o) return { error: o.error };
  }
  return null;
}

// The generation of a line the watched board wrote by itself, changed{routing,<n>}, or null. Not a reply to anything.
function changedOf(line) {
  const m = /^changed\{routing,(\d+)\}(\r?\n)?$/.exec(line);
  return m ? Number(m[1]) : null;
}

// The last whole crossbar dump, as it stands, or null.
function xbarOf(text) {
  const m = lastMatch(/xbar\{12x8:[0-9a-f]{384}\}/g, text);
  return m ? m[0] : null;
}

// The text up to the end of chip L's status row once the report holds that whole row, or null.
function reportOf(text) {
  const bridge = text.indexOf("Bridge Array");
  if (bridge < 0) return null;
  const chips = text.indexOf("Chip Status", bridge);
  if (chips < 0) return null;
  const rows = [...text.slice(chips).matchAll(/^[A-L]\t[^\n]*\n/gm)];
  if (rows.length < 12) return null;
  return text.slice(0, chips + rows[11].index + rows[11][0].length);
}

// What a SerialPort has that the link uses, answering from a trace (JSON Lines).
class FakePort {
  constructor(traceText, { gapMs = 1 } = {}) {
    this.gapMs = gapMs;
    this.exchanges = [];                                   // one per write answered or line unasked, a "times" line spread out
    for (const line of traceText.split("\n")) {
      if (!line.trim()) continue;
      const e = JSON.parse(line);
      if (e.h) continue;
      for (let i = 0; i < (e.times || 1); i++) this.exchanges.push({ sent: e.sent, got: e.got });
    }
    this.place = 0;
    this.written = [];
    this.opened = null;
    this.closed = false;
    this.forgotten = false;
    this.most = 0;
    this.readable = null;
    this.writable = null;
    this.hushed = false;
    this.waiting = [];                                     // writes left unanswered while hushed
    this.unanswered = 0;
    this.cutAt = null;
    this.controller = null;
  }

  async open(options) {
    this.opened = options;
    this.closed = false;
    this.readable = new ReadableStream({ start: (c) => { this.controller = c; } });
    this.writable = new WritableStream({ write: (chunk) => this.take(new TextDecoder().decode(chunk)) });
    this.unasked();
  }

  // The lines at the place that nobody asked for (sent null): each sent by itself, gapMs after the one before,
  // and the place moved past them.
  unasked() {
    for (let k = 1; this.place < this.exchanges.length && this.exchanges[this.place].sent === null; k++) {
      const got = this.exchanges[this.place++].got;
      if (got != null) setTimeout(() => this.add(got), this.gapMs * k);
    }
  }

  async close() {
    this.closed = true;
    this.pull();
    this.readable = null;
    this.writable = null;
  }

  getInfo() { return { ...BOARD_PORT.FILTER }; }

  async forget() { this.forgotten = true; }

  take(text) {
    this.written.push(text);
    this.most = Math.max(this.most, ++this.unanswered);
    if (this.hushed) this.waiting.push(text);
    else setTimeout(() => this.answer(text), this.gapMs);
  }

  // The next exchange from here that was a reply to this text, else the last one behind.
  answer(text) {
    this.unanswered--;
    let i = this.exchanges.findIndex((e, k) => k >= this.place && e.sent === text);
    if (i >= 0) { if (this.cutAt === null) { this.place = i + 1; this.unasked(); } }
    else {
      for (i = Math.min(this.place, this.exchanges.length) - 1; i >= 0 && this.exchanges[i].sent !== text; i--);
    }
    const got = i >= 0 ? this.exchanges[i].got : null;
    if (got == null) return;
    const cut = this.cutAt;
    this.cutAt = null;
    this.add(cut === null ? got : got.slice(0, cut));
  }

  // Bytes nobody asked for.
  add(text) {
    try { this.controller.enqueue(new TextEncoder().encode(text)); } catch (e) { /* the cable is out */ }
  }

  hush() { this.hushed = true; }

  speak() {
    this.hushed = false;
    for (const text of this.waiting.splice(0)) setTimeout(() => this.answer(text), this.gapMs);
  }

  // The next answer stops after n characters, and its exchange is not used up.
  cut(n) { this.cutAt = n; }

  // The cable out: the readable ends.
  pull() {
    try { this.controller.close(); } catch (e) { /* already ended */ }
  }
}

// Why a link could not be made: "busy", "not_port_7", "too_old" or "gone".
class LinkError extends Error {
  constructor(kind, message, fw) {
    super(message);
    this.name = "LinkError";
    this.kind = kind;
    this.fw = fw === undefined ? null : fw;
  }
}

const hhmmss = (ms) => new Date(ms).toTimeString().slice(0, 8);
const GONE = "the board is gone: unplugged, or the port was closed.";

// A board's port 7, held open: proves the port, then asks one thing at a time and
// gives a reading each time the routing stands idle at a generation not yet shown.
class BoardLink {
  constructor(port, on, opts) {
    this.port = port;
    this.on = on;
    this.t = Object.assign({}, BOARD_PORT);               // the timings may be changed; the speed and the seven may not
    for (const k of Object.keys(opts || {})) if (k.endsWith("_MS")) this.t[k] = opts[k];
    this.reader = null;
    this.writer = null;
    this.pumping = null;
    this.text = "";                                        // every byte since the last whole reply
    this.lines = "";                                       // the bytes since the last line end, looked at for changed{}
    this.told = null;                                      // {n} of the last changed{} line not yet acted on
    this.watching = false;                                 // the board said it will write changed{} lines
    this.how = "";                                         // in words: watched, or asked every half second
    this.stopping = false;                                 // close() has begun
    this.heard = 0;                                        // when the last byte came
    this.ended = false;
    this.closing = false;
    this.proven = false;                                   // the port answered N with a net list
    this.out = null;                                       // the query unanswered, or null
    this.unkept = null;                                    // the query written and not yet in the trace, or null
    this.wakers = [];
    this.exchanges = [];
    this.t0 = 0;
    this.fw = null;
    this.count = 0;
    this.lastAt = null;                                    // when the last reading was given
    this.said = null;                                      // the last state said
    this.silent = false;                                   // "waiting" was said for a board that does not answer
    this.rereading = false;
  }

  say(name, words) {
    this.said = name;
    this.on.state(name, words);
  }

  lastRead() { return this.lastAt === null ? "" : " Last read " + hhmmss(this.lastAt) + "."; }

  // Wakes every wait; with byte, only the waits a byte ends.
  wake(byte) {
    for (const w of this.wakers.slice()) if (!byte || w.byByte) w();
  }

  // Resolves after ms, or sooner on the end, a close or again(), and with byByte on the next byte.
  // It leaves no timer behind.
  nap(ms, byByte) {
    return new Promise((resolve) => {
      const done = () => {
        clearTimeout(timer);
        const i = this.wakers.indexOf(done);
        if (i >= 0) this.wakers.splice(i, 1);
        resolve();
      };
      const timer = setTimeout(done, Math.max(0, ms));
      done.byByte = byByte;
      this.wakers.push(done);
    });
  }

  // The one reader: appends what comes to the text. A read error takes the reader again
  // from port.readable (lineChannel.ts:29-46); only a readable gone, or ended, is the end.
  async pump() {
    const decoder = new TextDecoder();
    while (!this.closing) {
      if (!this.reader) {
        if (!this.port.readable) break;
        try { this.reader = this.port.readable.getReader(); } catch (e) { break; }
      }
      let res;
      try { res = await this.reader.read(); }
      catch (e) {
        try { this.reader.releaseLock(); } catch (e2) { /* already let go */ }
        this.reader = null;
        if (this.closing) break;
        await new Promise((r) => setTimeout(r, 10));
        continue;
      }
      if (res.done) break;
      const chunk = decoder.decode(res.value, { stream: true });
      this.text += chunk;
      this.heard = Date.now();
      this.wake(true);
      const lines = (this.lines + chunk).split(/[\r\n]/);   // the reports end lines with \n\r: either one ends a line
      this.lines = lines.pop();                            // a line cut by the chunk's end waits for its rest
      for (const line of lines) {
        const n = changedOf(line);
        if (n === null) continue;
        this.told = { n };
        if (!this.out) {                                   // no query out: the bytes are a trace line of their own
          this.exchanges.push({ t: Math.round(Date.now() - this.t0) / 1000, sent: null, got: this.text });
          this.text = "";
        }
        this.wake();
      }
    }
    try { if (this.reader) this.reader.releaseLock(); } catch (e) { /* already let go */ }
    this.reader = null;
    this.ended = true;
    this.wake();
  }

  // One line of the trace; a run of the same exchange is one line with "times".
  keep(sent, got) {
    const last = this.exchanges[this.exchanges.length - 1];
    if (last && last.sent === sent && last.got === got) last.times = (last.times || 1) + 1;
    else this.exchanges.push({ t: Math.round(Date.now() - this.t0) / 1000, sent, got });
  }

  async send(text) {
    if (!BOARD_PORT.SENDS.includes(text)) throw new Error("the link sends only " + JSON.stringify(BOARD_PORT.SENDS));
    if (text !== "N" && !this.proven) throw new Error("no : before the port has answered N with a net list");
    await this.writer.write(new TextEncoder().encode(text));
  }

  // Sends text and returns what find first finds in the bytes since. With a limit, null
  // after it. Without, it waits for ever: "waiting" when silent, asked once more after a stall.
  // A reply has begun once the board has echoed the query; bytes before the echo are no answer.
  async ask(text, find, limit) {
    if (this.out) throw new Error("a query is already out: " + JSON.stringify(this.out));
    if (this.closing || this.ended) throw new LinkError("gone", GONE);
    this.out = text;
    try {
      const echo = text.trimEnd();
      let start = this.text.length, sentAt = Date.now(), again = true, said = -1;
      await this.send(text);
      this.unkept = text;
      for (;;) {
        const reply = find(this.text.slice(start));
        if (reply != null) {
          this.keep(text, this.text);
          this.text = "";
          this.unkept = null;
          if (this.silent) { this.silent = false; this.say("live", "reading the board." + this.lastRead()); }
          return reply;
        }
        if (this.closing || this.ended) throw new LinkError("gone", GONE);
        const now = Date.now(), began = this.text.indexOf(echo, start) >= 0;
        if (limit !== undefined) {
          if (now - sentAt < limit) { await this.nap(limit - (now - sentAt), true); continue; }
          this.keep(text, this.text || null);
          this.text = "";
          this.unkept = null;
          return null;
        }
        const quiet = now - (began ? this.heard : sentAt);
        if (began && again && quiet >= this.t.STALL_MS) {        // cut short: thrown away, asked once more
          this.keep(text, this.text);
          this.text = "";
          this.unkept = null;
          start = 0; sentAt = Date.now(); again = false;
          await this.send(text);
          this.unkept = text;
          continue;
        }
        if (quiet >= this.t.WAIT_SAY_MS && Math.floor(quiet / 1000) !== said) {
          said = Math.floor(quiet / 1000);
          this.silent = true;
          this.say("waiting", "the board has not answered for " + said + " s. It answers port 7 from its main loop only: "
            + "not in probe mode, a menu or an app." + this.lastRead());
        }
        const next = [quiet < this.t.WAIT_SAY_MS ? this.t.WAIT_SAY_MS - quiet : 1000 - (quiet % 1000)];
        if (began && again) next.push(this.t.STALL_MS - quiet);
        await this.nap(Math.min(...next), true);
      }
    } finally {
      if (this.unkept) {                                   // ended by a throw or a close: the query is kept all the same
        this.keep(this.unkept, this.text || null);
        this.text = "";
        this.unkept = null;
      }
      this.out = null;
    }
  }

  askGen() { return this.ask(":gen\n", (t) => (refusedVerb(t) === "gen" ? { refused: true } : genOf(t))); }

  async connect() {
    this.say("probing", "asking the port for a net list, to be sure it is the board's port 7.");
    try { await this.port.open({ baudRate: BOARD_PORT.BAUD, bufferSize: BOARD_PORT.BUFFER }); }
    catch (e) {
      if (e && e.name === "NetworkError") throw new LinkError("busy", "the port is held by another program or tab.");
      throw e;
    }
    this.t0 = Date.now();
    this.writer = this.port.writable.getWriter();
    this.pumping = this.pump();
    try {
      if (!(await this.ask("N", (t) => netListIn(t) || null, this.t.PROBE_MS)))
        throw new LinkError("not_port_7", "this port did not answer N with a net list: it is not the board's port 7.");
      this.proven = true;
      this.fw = (await this.ask(":ver\n", (t) => (refusedVerb(t) === "ver" ? { fw: null } : versionOf(t) && { fw: versionOf(t) }))).fw;
      if ((await this.askGen()).refused) throw new LinkError("too_old", "the board's firmware is too old for a live view.", this.fw);
    } catch (e) {
      await this.close();
      throw e;
    }
    return { fw: this.fw };
  }

  // Waits until the time, or sooner on a close, the end, or done(). Nothing else cuts it.
  async rest(until, done) {
    while (!this.stopping && !this.ended && !done() && Date.now() < until) await this.nap(until - Date.now());
  }

  // The loop: one reading at each generation the board stands idle at. A watching board says when its routing
  // changed and is asked :gen every WATCH_POLL_MS besides; one that cannot watch is asked every POLL_MS. Never throws.
  async run() {
    let shown = null, busySince = null;
    try {
      const w = await this.ask(":watch:routing:on\n", watchOf);
      this.watching = Boolean(w.on);
      this.how = this.watching ? "the board says when its routing changes" : "asking every half second: this firmware has no :watch";
      this.say("live", this.how + "." + this.lastRead());
      while (!this.closing && !this.stopping) {
        const told = this.told;                            // taken before :gen is asked: a line that comes while it is out
        this.told = null;                                  // stays, and starts the next round
        let g = told ? { n: told.n, idle: true } : await this.askGen();      // a changed{} line stands in for :gen
        if (g.refused) return await this.tooOld();
        while (g.idle && (g.n !== shown || this.rereading)) {
          const b = await this.ask(":paths\n", (t) => (refusedVerb(t) === "paths" ? { refused: true } : reportOf(t)));
          if (b.refused) return await this.tooOld();
          const xbar = await this.ask(":crossbar\n", xbarOf);
          const h = await this.askGen();
          if (h.refused) return await this.tooOld();
          if (h.idle && h.n === g.n) {
            shown = g.n;
            this.rereading = false;
            this.lastAt = Date.now();
            this.on.reading({ n: ++this.count, gen: g.n, b, xbar, fw: this.fw, at: this.lastAt });
            this.say("live", "generation " + g.n + ": " + this.how + "." + this.lastRead());
            break;
          }
          g = h;
        }
        if (!g.idle && g.n !== shown) {                    // a routing on its way
          if (busySince === null) busySince = Date.now();
          if (Date.now() - busySince >= this.t.WAIT_SAY_MS && this.said !== "waiting")
            this.say("waiting", "the board's routing changed and it has not finished sending it." + this.lastRead());
        } else {
          busySince = null;
          if (this.said === "waiting") this.say("live", "reading the board: " + this.how + "." + this.lastRead());
        }
        const end = Date.now();
        await this.rest(end + this.t.GAP_MS, () => false);
        const poll = this.watching && g.idle && g.n === shown ? this.t.WATCH_POLL_MS : this.t.POLL_MS;
        await this.rest(end + poll, () => this.told || this.rereading);
      }
    } catch (e) {
      if (this.closing || this.stopping) return;
      await this.close();
      this.say("lost", GONE);
    }
  }

  async tooOld() {
    await this.close();
    this.say("too_old", "the board's firmware (" + this.fw + ") is too old for a live view: it needs " + this.t.NEEDS + ".");
  }

  // The next round reads the report and the dump whatever the number says.
  again() { this.rereading = true; this.wake(); }

  // Stops the loop, lets go of the reader and the writer, closes the port.
  // A watch the board said it keeps is turned off first, unless a query is out; its answer is waited for OFF_MS at most.
  async close() {
    if (this.stopping) return;
    this.stopping = true;
    this.wake();
    if (this.watching && this.proven && !this.ended && !this.out) {
      try { await this.ask(":watch:routing:off\n", watchOf, this.t.OFF_MS); } catch (e) { /* gone: closed all the same */ }
    }
    this.closing = true;
    this.wake();
    try { if (this.reader) await this.reader.cancel(); } catch (e) { /* already ended */ }
    if (this.pumping) await this.pumping;
    try { if (this.writer) this.writer.releaseLock(); } catch (e) { /* already let go */ }
    this.writer = null;
    try { await this.port.close(); } catch (e) { /* already closed */ }
  }

  // The header and every exchange since connect. The header's source is "board", or "replay" when the port is a
  // FakePort. A query still unanswered is a last line with what has come (null for nothing); else bytes after the
  // last whole reply are a last line with sent null.
  trace() {
    const head = this.port instanceof FakePort
      ? { h: 1, what: "routing lab port 7 trace", source: "replay", fw: this.fw,
        about: "made by the routing lab while it replays a trace (serve --replay): not a recording from a board" }
      : { h: 1, what: "routing lab port 7 trace", source: "board", fw: this.fw, about: "recorded by the routing lab from a board" };
    const lines = [head, ...this.exchanges];
    if (this.unkept || this.text) lines.push({ t: Math.round(Date.now() - this.t0) / 1000, sent: this.unkept, got: this.text || null });
    return lines.map((l) => JSON.stringify(l) + "\n").join("");
  }
}

if (typeof module !== "undefined") {
  module.exports = { BOARD_PORT, serialWhyNot, netListIn, versionOf, genOf, refusedVerb, watchOf, changedOf, xbarOf, reportOf, FakePort,
    LinkError, BoardLink };
}
