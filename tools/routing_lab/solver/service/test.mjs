// SPDX-License-Identifier: MIT
// node test.mjs: what the Worker lets through to the solver. Needs nothing installed.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { MAX_BYTES, MAX_SECONDS, check, count, usedToday } from "./src/check.js";

const here = (name) => new URL(name, import.meta.url);
const KEY = "k".repeat(32);
const GOOD = JSON.stringify({ bridges: [], terminals: {}, crosspoints: [], rule: "firmware", seconds: 20, fewest: true });
const post = (body, key = KEY, method = "POST") => new Request("https://slopswap.org/api/solve", {
    method, body: method === "POST" ? body : undefined, headers: key === null ? {} : { authorization: "Bearer " + key },
});
const status = async (request, env = { SOLVE_KEY: KEY }) => {
    const r = await check(request, env);
    return r instanceof Response ? r.status : r;
};
const asking = (changes) => post(JSON.stringify({ ...JSON.parse(GOOD), ...changes }));
let checks = 0;
const is = async (request, want, env) => { assert.deepEqual(await status(request, env), want); checks++; };

// No key on the server: nothing gets through, not even the right-looking key.
await is(post(GOOD), 503, {});
await is(post(GOOD, ""), 503, { SOLVE_KEY: "" });
await is(post(GOOD, "short"), 503, { SOLVE_KEY: "short" });
// The key.
await is(post(GOOD, null), 401);
await is(post(GOOD, ""), 401);
await is(post(GOOD, KEY + "x"), 401);
await is(post(GOOD, KEY.slice(1)), 401);
await is(new Request("https://slopswap.org/api/solve", { method: "POST", body: GOOD, headers: { authorization: KEY } }),
    { text: GOOD, seconds: 20 });                    // "Bearer " is optional
// Only POST, and the key is asked for before the body is read.
await is(post(null, KEY, "GET"), 405);
await is(post("x".repeat(MAX_BYTES + 1), "wrong"), 401);
// Size.
await is(post("x".repeat(MAX_BYTES + 1)), 413);
// What is in it.
await is(post("not json"), 400);
await is(post("[1]"), 400);
await is(post("null"), 400);
await is(asking({ rule: "any" }), 400);
await is(asking({ rule: undefined }), 400);
for (const seconds of [0, -1, MAX_SECONDS + 1, "20", null, Infinity]) await is(asking({ seconds }), 400);
// A good one comes back as it was sent.
await is(post(GOOD), { text: GOOD, seconds: 20 });
await is(asking({ rule: "copper", seconds: MAX_SECONDS }),
    { text: JSON.stringify({ ...JSON.parse(GOOD), rule: "copper", seconds: MAX_SECONDS }), seconds: MAX_SECONDS });
// A refusal is JSON with an error, never a verdict.
const refusal = await (await check(post(GOOD, null), { SOLVE_KEY: KEY })).json();
assert.deepEqual(Object.keys(refusal), ["error"]); checks++;

// The daily count is of the time the container is up: each question to 300 s past its end, no second counted twice.
const DAY = Date.UTC(2026, 10, 23), AWAKE = 300_000, at = (s) => DAY + s * 1000;
let used = count(undefined, at(0), at(10), AWAKE);                  // 10 s of solving
assert.deepEqual(used, { day: "2026-11-23", seconds: 310, until: at(310) }); checks++;
used = count(used, at(110), at(120), AWAKE);                        // asked while still up: only the extension
assert.equal(used.seconds, 420); checks++;
used = count(used, at(5000), at(5010), AWAKE);                      // asked after it slept: all of it
assert.equal(used.seconds, 730); checks++;
assert.equal(usedToday(used, at(6000)), 730); checks++;
assert.equal(usedToday(used, at(86400)), 0); checks++;              // the next UTC day starts from nothing
assert.equal(count(used, at(86400), at(86410), AWAKE).seconds, 310); checks++;
assert.equal(usedToday(undefined, at(0)), 0); checks++;

// The image has the OR-tools the lab pins, and the sample question is one the Worker lets through.
const pinned = readFileSync(here("../../ceiling.py"), "utf8").match(/^ORTOOLS = "([^"]+)"/m)[1];
assert.ok(readFileSync(here("Dockerfile"), "utf8").includes("ortools==" + pinned + "\n"), "Dockerfile and ceiling.py pin different OR-tools"); checks++;
const sample = readFileSync(here("sample-question.json"), "utf8");
assert.equal((await status(post(sample))).seconds, JSON.parse(sample).seconds); checks++;

console.log("ok, " + checks + " checks");
