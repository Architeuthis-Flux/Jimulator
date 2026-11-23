# The exact solver as a web service

`POST https://slopswap.org/api/solve` answers the question `../solve.py`
answers on the Mac, so the lab's page on slopswap.org can ask the solver
things nobody asked first. It is what
`Routing/docs/HANDOFF_2026-11-22_ROUTING_LAB_HOSTING.md` asked for, part 1.

It solves a JSON question and nothing else. Nothing sent to it is compiled
or run.

## Asking

Send what `ceiling.ask` writes to `solve.py`'s stdin, with the key:

```
POST /api/solve
Authorization: Bearer <key>

{"bridges": [...], "terminals": {...}, "crosspoints": [...],
 "rule": "firmware" | "copper", "seconds": 20, "fewest": true}
```

| Status | Body | Meaning |
|---|---|---|
| 200 | what `solve.py` prints | The answer. `verdict` may still be `unknown`. |
| 400 | `{"error": ...}` | Not a question: bad JSON, a `rule` or `seconds` out of range, or `solve.py`'s own "malformed problem". |
| 401 | `{"error": ...}` | The key is missing or wrong. |
| 413 | `{"error": ...}` | Longer than 512 KB. V5's largest question is 36 KB. |
| 429 | `{"error": ...}` | The day's time is used up (see "What it costs"). |
| 502, 504 | `{"error": ...}` | The solver died, or gave no answer by its limit plus 90 s. |
| 503 | `{"error": ...}` | No key is stored on the server. Nothing is answered until one is. |

A caller treats everything but 200 as `ceiling.ask` treats a solver that
died: `unknown`, with the error. It is never "not routable".

`seconds` may be at most 120. A longer one is refused, not shortened.

The first question after a quiet spell waits for the container to start.
Questions are answered one at a time; a second waits its turn. A question
whose asker has gone is stopped: on Cloudflare, a question asked right after
a 20 s one was abandoned came back in 1.4 s (2026-11-23). Under
`wrangler dev` it is not stopped, because the disconnect never reaches the
Worker there: it runs to its own `seconds` and the next one waits.

## How it is made

- `src/check.js`: what a request must pass before the solver is woken, and
  the count behind the daily cap. No imports.
- `src/index.js`: the Worker, and the Durable Object that owns the container.
  It runs `python3 /app/solve.py` once per question with the question on
  stdin. There is no server inside the container.
- `Dockerfile`, `../.dockerignore`: Python, the OR-tools version `ceiling.py`
  pins, and `../solve.py`. The image is built from the lab's own file, so the
  web solver cannot drift from the local one.
- `wrangler.jsonc`: the route on slopswap.org. There is no `workers.dev`
  address.

The container has no internet access, 4 vCPU and 12 GiB (`standard-4`, the
largest Cloudflare offers). `solve.py` asks CP-SAT for 8 workers, so it is
slower than the Mac. Measured on 2026-11-23 with ten questions from the
battery, each whole request against the Mac's `solve.py` run:

| Bridges | Cloudflare | Mac |
|---|---|---|
| 4 | 1.3 to 1.8 s | 0.7 to 1.5 s |
| 8 to 9 | 3.1 to 5.5 s | 1.2 to 1.4 s |
| 15 | 10.9 to 11.6 s | 2.8 to 3.2 s |
| 63 | the full 20 s | the full 20 s |

All ten got the Mac's verdict. A question the Mac only just settles inside
its limit will come back `unknown`, or with `fewest` unproved, here. How
long a sleeping container takes to wake was not measured: every timed
question found it up. A 110 s question was answered after 112 s, so a long
request is not cut off. Peak memory on the Mac was 0.2 to 2.1 GB.

## What it costs

It needs Cloudflare's Workers Paid plan ($5 a month). The container is
billed while it is up: about $0.11 an hour idle and $0.40 an hour solving
flat out. It is set to stay up 5 minutes after the last question, then
sleeps and costs nothing; on 2026-11-23 Cloudflare listed no active instance
4.5 minutes after the last one (`npx wrangler containers list`). The plan
includes roughly the first 2 hours a month.

Two things bound what a leaked key can spend:

- the key itself (below);
- a cap of 2 hours up per UTC day, whoever asks (`DAILY_SECONDS` in
  `src/index.js`). That is about $0.80 a day at worst.

## Checking it

```bash
node test.mjs
```

Needs nothing installed. It covers the key, the limits, the daily count,
that the Dockerfile pins the lab's OR-tools, and that `sample-question.json`
(the battery's `isense_loop_stacked`) is let through.

## Running and deploying it

Both need a Docker daemon and `npm install` here. The image must be
`linux/amd64`. On Kevin's Mac the daemon is Colima, set up on 2026-11-23 to
build that through Rosetta; it is not started at login:

```bash
colima start            # the settings of the first start are kept
colima stop
```

The wrangler pinned here needs Node 22.12 or later, and the `node` first on
that Mac's PATH is 20. So:

```bash
export PATH="/opt/homebrew/opt/node/bin:$PATH"
npx wrangler dev        # the Worker and the container on this machine
npx wrangler deploy     # builds the image, pushes it, publishes the route
```

For `wrangler dev`, put a test key in `.dev.vars` (ignored by git):
`SOLVE_KEY=<24 characters or more>`.

After a deploy, a sleeping container starts on the new image; a running one
keeps the old image until it sleeps.

## The key

One secret on the Worker, `SOLVE_KEY`, 24 characters or more. It is pasted
into the lab's page once and kept in that browser. Make one, store it, and
copy it to the clipboard:

```bash
k=$(openssl rand -base64 32) && printf %s "$k" | npx wrangler secret put SOLVE_KEY && printf %s "$k" | pbcopy
```

Run it again to replace the key; the old one stops working at once.

A key kept in the browser for slopswap.org can be read by any page on that
hostname, and some folders of that site are edited by other people. So the
key keeps strangers out, and the daily cap is what bounds the cost if a page
there ever takes it.

## Asking it by hand

```bash
curl -s https://slopswap.org/api/solve -H "Authorization: Bearer $KEY" --data-binary @sample-question.json
```

The Mac's answer to that question is `routable`, `fewest_proved`, 12
crosspoints.
