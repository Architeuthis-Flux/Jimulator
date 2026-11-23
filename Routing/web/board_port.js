// SPDX-License-Identifier: MIT
// A board's port 7, read in the page's own code: what the board answers to the
// five things the lab ever sends, and a fake port that replays a recorded trace
// of those exchanges. No DOM, no import; under node the last line exports it.
"use strict";

const BOARD_PORT = {
  FILTER: { usbVendorId: 0x1D50, usbProductId: 0xACAB },   // usb_descriptors.cpp:71-72
  BAUD: 115200,                                            // ArduinoStuff.cpp:212
  BUFFER: 65536,                                           // lineChannel.ts:21
  SENDS: ["N", ":ver\n", ":gen\n", ":paths\n", ":crossbar\n"],   // the only bytes ever sent to a board
  POLL_MS: 500,
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

// What a SerialPort has that the link uses, answering from a recorded trace (JSON Lines).
class FakePort {
  constructor(traceText, { gapMs = 1 } = {}) {
    this.gapMs = gapMs;
    this.exchanges = [];                                   // one per write answered, a "times" line spread out
    for (const line of traceText.split("\n")) {
      if (!line.trim()) continue;
      const e = JSON.parse(line);
      if (e.h || e.sent == null) continue;
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
    if (i >= 0) { if (this.cutAt === null) this.place = i + 1; }
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
    this.t = Object.assign({}, BOARD_PORT, opts);
    this.reader = null;
    this.writer = null;
    this.pumping = null;
    this.text = "";                                        // every byte since the last whole reply
    this.heard = 0;                                        // when the last byte came
    this.ended = false;
    this.closing = false;
    this.proven = false;                                   // the port answered N with a net list
    this.out = null;                                       // the query unanswered, or null
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

  wake() { for (const w of this.wakers.splice(0)) w(); }

  // Resolves on the next byte, the end, a close or again(), or after ms, and leaves no timer behind.
  nap(ms) {
    return new Promise((resolve) => {
      const done = () => {
        clearTimeout(timer);
        const i = this.wakers.indexOf(done);
        if (i >= 0) this.wakers.splice(i, 1);
        resolve();
      };
      const timer = setTimeout(done, Math.max(0, ms));
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
      this.text += decoder.decode(res.value, { stream: true });
      this.heard = Date.now();
      this.wake();
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
    if (!this.t.SENDS.includes(text)) throw new Error("the link sends only " + JSON.stringify(this.t.SENDS));
    if (text !== "N" && !this.proven) throw new Error("no : before the port has answered N with a net list");
    await this.writer.write(new TextEncoder().encode(text));
  }

  // Sends text and returns what find first finds in the bytes since. With a limit, null
  // after it. Without, it waits for ever: "waiting" when silent, asked once more after a stall.
  async ask(text, find, limit) {
    if (this.out) throw new Error("a query is already out: " + JSON.stringify(this.out));
    if (this.closing || this.ended) throw new LinkError("gone", GONE);
    this.out = text;
    try {
      let start = this.text.length, sentAt = Date.now(), again = true, said = -1;
      await this.send(text);
      for (;;) {
        const reply = find(this.text.slice(start));
        if (reply != null) {
          this.keep(text, this.text);
          this.text = "";
          if (this.silent) { this.silent = false; this.say("live", "reading the board." + this.lastRead()); }
          return reply;
        }
        if (this.closing || this.ended) throw new LinkError("gone", GONE);
        const now = Date.now(), began = this.text.length > start;
        if (limit !== undefined) {
          if (now - sentAt < limit) { await this.nap(limit - (now - sentAt)); continue; }
          this.keep(text, this.text || null);
          this.text = "";
          return null;
        }
        const quiet = now - (began ? this.heard : sentAt);
        if (began && again && quiet >= this.t.STALL_MS) {        // cut short: thrown away, asked once more
          this.keep(text, this.text);
          this.text = "";
          start = 0; sentAt = Date.now(); again = false;
          await this.send(text);
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
        await this.nap(Math.min(...next));
      }
    } finally { this.out = null; }
  }

  askGen() { return this.ask(":gen\n", (t) => (refusedVerb(t) === "gen" ? { refused: true } : genOf(t))); }

  async connect() {
    this.say("probing", "asking the port for a net list, to be sure it is the board's port 7.");
    try { await this.port.open({ baudRate: this.t.BAUD, bufferSize: this.t.BUFFER }); }
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

  // The loop: one reading at each generation the board stands idle at. Never throws.
  async run() {
    let shown = null, busySince = null;
    try {
      while (!this.closing) {
        let g = await this.askGen();
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
            this.say("live", "generation " + g.n + "." + this.lastRead());
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
          if (this.said === "waiting") this.say("live", "reading the board." + this.lastRead());
        }
        await this.nap(this.t.POLL_MS);
      }
    } catch (e) {
      if (this.closing) return;
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
  async close() {
    if (this.closing) return;
    this.closing = true;
    this.wake();
    try { if (this.reader) await this.reader.cancel(); } catch (e) { /* already ended */ }
    if (this.pumping) await this.pumping;
    try { if (this.writer) this.writer.releaseLock(); } catch (e) { /* already let go */ }
    this.writer = null;
    try { await this.port.close(); } catch (e) { /* already closed */ }
  }

  // The header and every exchange since connect; bytes after the last whole reply are a last line.
  trace() {
    const head = { h: 1, what: "routing lab port 7 trace", source: "board", fw: this.fw, about: "recorded by the routing lab from a board" };
    const lines = [head, ...this.exchanges];
    if (this.text) lines.push({ t: Math.round(Date.now() - this.t0) / 1000, sent: null, got: this.text });
    return lines.map((l) => JSON.stringify(l) + "\n").join("");
  }
}

if (typeof module !== "undefined") module.exports = { BOARD_PORT, serialWhyNot, netListIn, versionOf, genOf, refusedVerb, xbarOf, reportOf, FakePort, LinkError, BoardLink };
