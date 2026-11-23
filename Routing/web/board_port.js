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

if (typeof module !== "undefined") module.exports = { BOARD_PORT, serialWhyNot, netListIn, versionOf, genOf, refusedVerb, xbarOf, reportOf, FakePort };
