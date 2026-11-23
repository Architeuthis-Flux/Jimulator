// SPDX-License-Identifier: MIT
// What the Worker asks of a request before the solver is woken. No imports,
// so `node test.mjs` runs it as it is.

export const MAX_BYTES = 512 * 1024;    // a question; the largest of V5's battery is 36 KB
export const MAX_SECONDS = 120;         // the longest time limit the lab asks for
const MIN_KEY = 24;                     // a shorter secret on the server is taken as none

export const answer = (status, body) => new Response(typeof body === "string" ? body : JSON.stringify(body),
    { status, headers: { "content-type": "application/json", "cache-control": "no-store" } });
export const refuse = (status, message) => answer(status, { error: message });

async function digest(text) {
    const hash = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
    return Array.from(new Uint8Array(hash), (b) => b.toString(16).padStart(2, "0")).join("");
}

// The body as text, or null once it is longer than `most` bytes.
async function read(request, most) {
    if (!request.body) return "";
    const chunks = [];
    let size = 0;
    for await (const chunk of request.body) {
        size += chunk.length;
        if (size > most) return null;
        chunks.push(chunk);
    }
    return new Blob(chunks).text();
}

// The seconds the container has been up today. What is billed is the time it
// is up, so that is what the daily cap counts: {day, seconds, until}, where
// `until` is the moment it is already counted up to.
export const usedToday = (used, now) => (used?.day === new Date(now).toISOString().slice(0, 10) ? used.seconds : 0);

/** The count after a question that ran from `started` to `ended` (ms). It
 *  keeps the container up for `awake` ms past its end; time the question
 *  before it already counted is not counted twice. */
export function count(used, started, ended, awake) {
    return {
        day: new Date(started).toISOString().slice(0, 10),
        seconds: usedToday(used, started) + (ended + awake - Math.max(used?.until || 0, started)) / 1000,
        until: ended + awake,
    };
}

/** The question, as {text, seconds}, or the Response that refuses it. */
export async function check(request, env) {
    if (request.method !== "POST") return refuse(405, "POST a question");
    const key = env.SOLVE_KEY || "";
    if (key.length < MIN_KEY) return refuse(503, "no key is set on the server");
    // Digests are compared so that how long the comparison takes says nothing of the key.
    const given = (request.headers.get("authorization") || "").replace(/^Bearer /, "");
    if (await digest(given) !== await digest(key)) return refuse(401, "the key is missing or wrong");

    const tooBig = "a question may be at most " + MAX_BYTES + " bytes";
    if (Number(request.headers.get("content-length")) > MAX_BYTES) return refuse(413, tooBig);
    const text = await read(request, MAX_BYTES);
    if (text === null) return refuse(413, tooBig);

    let q;
    try {
        q = JSON.parse(text);
    } catch {
        return refuse(400, "the question is not JSON");
    }
    if (q === null || typeof q !== "object" || Array.isArray(q)) return refuse(400, "the question is not a JSON object");
    if (q.rule !== "copper" && q.rule !== "firmware") return refuse(400, 'rule must be "copper" or "firmware"');
    if (typeof q.seconds !== "number" || !(q.seconds > 0) || q.seconds > MAX_SECONDS) {
        return refuse(400, "seconds must be a number above 0 and at most " + MAX_SECONDS);
    }
    return { text, seconds: q.seconds };
}
