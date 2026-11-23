// SPDX-License-Identifier: MIT
// The routing lab's exact solver as a web service: POST a question, get
// solve.py's answer. The Worker checks the request (check.js). The Durable
// Object runs solver/solve.py in its container with the question on stdin,
// the way ceiling.ask runs it on the Mac. Nothing sent here is ever compiled
// or run: it is solved as a JSON question, or refused.
//
// ponytail: no CORS, because the page is on the hostname this answers on.
// When the page is also served from docs.jumperless.org, answer OPTIONS and
// send Access-Control-Allow-Origin for that origin.
import { DurableObject } from "cloudflare:workers";
import { answer, check, count, refuse, usedToday } from "./check.js";

const GRACE = 30;                       // seconds past its limit before the solver is given up on (ceiling.GRACE)
const START = 60;                       // seconds allowed for a sleeping container to come up
const AWAKE_MS = 5 * 60 * 1000;         // how long the container stays up after the last question
const DAILY_SECONDS = 2 * 3600;         // seconds the container may be up per UTC day: what a leaked key can spend

export default {
    async fetch(request, env) {
        const q = await check(request, env);
        if (q instanceof Response) return q;
        return env.SOLVER.getByName("solver").fetch(new Request(request.url, {
            method: "POST", body: q.text, headers: { "x-seconds": String(q.seconds) }, signal: request.signal,
        }));
    },
};

export class Solver extends DurableObject {
    constructor(ctx, env) {
        super(ctx, env);
        this.line = Promise.resolve();  // one question at a time; the next waits its turn
        if (ctx.container?.running) {   // this object restarted under a running container: the timeout is not kept
            void ctx.blockConcurrencyWhile(() => ctx.container.setInactivityTimeout(AWAKE_MS));
        }
    }

    async fetch(request) {
        const turn = this.line.then(() => this.solve(request));
        this.line = turn.catch(() => {});
        try {
            return await turn;
        } catch (e) {
            console.error("solver:", e);
            return refuse(502, "the solver could not be run: " + (e?.message || e));
        }
    }

    async solve(request) {
        if (request.signal.aborted) return refuse(499, "the asker left before its turn");
        const seconds = Number(request.headers.get("x-seconds"));
        const started = Date.now();
        let used = await this.ctx.storage.get("used");
        if (usedToday(used, started) >= DAILY_SECONDS) {
            return refuse(429, "today's solver time is used up; it starts again at 00:00 UTC");
        }

        const container = this.ctx.container;
        if (!container.running) {
            container.start({ image: container.images.solver, instance: "standard-4", enableInternet: false });
            await container.setInactivityTimeout(AWAKE_MS);
        }

        // One deadline for waking and solving. solve.py stops CP-SAT at `seconds` itself; this is for a solver that
        // is stuck. exec() must be given a controller's signal, and nothing may abort it once the process is gone.
        let why = null;
        const kill = new AbortController();
        const stop = (reason) => { why = why || reason; kill.abort(); };
        const left = () => stop("left");
        const timer = setTimeout(() => stop("late"), (START + seconds + GRACE) * 1000);
        request.signal.addEventListener("abort", left, { once: true });
        const disarm = () => { clearTimeout(timer); request.signal.removeEventListener("abort", left); };

        let out;
        try {
            const process = await container.exec(["python3", "/app/solve.py"], { stdin: request.body, signal: kill.signal });
            void process.exitCode.then(disarm, disarm);
            out = await process.output();
        } catch (e) {
            disarm();
            if (!why) throw e;
        }
        const ended = Date.now();
        used = count(used, started, ended, AWAKE_MS);
        await this.ctx.storage.put("used", used);

        const text = (buffer) => new TextDecoder().decode(buffer);
        const lastLine = (buffer) => text(buffer).trim().split("\n").pop();
        console.log(JSON.stringify({ asked: seconds, took: (ended - started) / 1000, exit: out?.exitCode, why,
                                     upToday: Math.round(used.seconds) }));
        if (why === "left") return refuse(499, "the asker left");
        if (why === "late") return refuse(504, "the solver gave no answer in " + (START + seconds + GRACE) + " s");
        if (out.exitCode === 2) return refuse(400, lastLine(out.stderr));
        if (out.exitCode !== 0) return refuse(502, "the solver exited with " + out.exitCode + ": " + lastLine(out.stderr));
        try {
            JSON.parse(text(out.stdout));
        } catch {
            return refuse(502, "the solver's answer cannot be read");
        }
        return answer(200, text(out.stdout));
    }
}
