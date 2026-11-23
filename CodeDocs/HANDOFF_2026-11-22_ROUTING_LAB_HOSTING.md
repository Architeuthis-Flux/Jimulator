# Handoff 2026-11-22: what the routing lab would need a server for

Kevin, 2026-11-22: "if I need to set up non-static hosting, write a short doc
explaining our needs for this so I can have another chat set that up".

**The short answer: nothing being built now needs one.** The published pages
(`slopswap.org/routing-lab/`) and the live page that follows them (design
piece 6 in `DESIGN_ROUTING_LAB.md`) run from static files: the firmware's
router is compiled to WebAssembly and runs in the tab, and so does the lab's
own Python.

Two things cannot run in a tab. A server is for these, and only if Kevin
wants them on the web. Each stands alone.

## 1. The exact solver, on demand

**What it is for.** The solver (OR-tools CP-SAT) answers "can this netlist be
routed on this copper at all, and with how few crosspoints". On the web its
answers are published data: only questions already asked on the Mac. With a
solver service the page could also:

- route nodes clicked on copper only the solver can route (`v6_rails_on_chips`
  and every V6 proposal that moves a pin);
- answer "ask the solver" for any netlist, not only the published ones.

That is most of what working on V6 arrangements from the web would need.

**What the service is.** One stateless call. The page builds the question
(the lab does this in the tab) and checks the answer itself, so the service
needs none of the lab but one file:

- `POST /solve` with the JSON `tools/routing_lab/solver/solve.py` reads on
  stdin: the question, the rule (`firmware` or `copper`), a time limit in
  seconds and whether the fewest crosspoints are wanted. It answers with the
  JSON `solve.py` prints. `ceiling.ask` (`tools/routing_lab/ceiling.py`) is
  the caller to copy: it runs `solve.py` as a subprocess with a timeout of
  the limit plus 30 s.
- Python 3 and `ortools==9.15.6755`, the version the lab pins. Nothing else.

**What it costs to run.**

- CPU only. `solve.py` runs CP-SAT with 8 workers for up to the time limit:
  5 s for a "needed" question, 20 s by default, 120 s at most. Most answers
  come in about a second (measured on the Mac, 2026-11-22). Memory was not
  measured.
- Idle nearly always. Something that starts on a request and stops after is
  the right shape. One question at a time is enough; a second waits.
- No disk. A cache of answers by the question's hash is optional.

**What it must do.**

- HTTPS, and CORS for `https://slopswap.org` (later `https://docs.jumperless.org`).
- Limit abuse: anyone can post a question that burns 8 cores for two minutes.
  Cap the seconds and the question's size, and gate it with a key that Kevin
  pastes into the page once (kept in his browser), not one written in the
  page. Visitors without the key keep the published answers.
- It must never compile or run anything it is sent. It solves a JSON
  question and nothing else.

**To decide:** where it runs (a small container that scales to zero, or a
tunnel to a machine Kevin owns), its address (for example
`lab-api.slopswap.org`; the zone is on Kevin's Cloudflare account), and who
gets a key.

## 2. Trying a changed router from the web

The local lab compiles any `src/` tree and routes with it. The web page can
only use routers already built. Two ways to get more of them there:

- **No server (recommended).** Build on the Mac and publish: `lab.py web`
  takes any number of git refs. Or a GitHub Action in JumperlOS that builds
  the router for each pushed branch and publishes it. It would be a new
  workflow file; `.github/workflows/release.yml` is not touched.
- **A compile server.** It would compile and run C++ sent by a browser. That
  needs a real sandbox and is not worth it for this.

## What the other chat needs from this repo

- `tools/routing_lab/solver/solve.py` (150 lines) and `ceiling.ask` in
  `tools/routing_lab/ceiling.py` (the protocol and the timeout).
- `tools/routing_lab/README.md`, "Ceilings", for what the answers mean.
- Design piece 6 in `CodeDocs/DESIGN_ROUTING_LAB.md` for how the page asks.

Nothing is set up, and no address or key exists yet.
