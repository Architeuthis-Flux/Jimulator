# Documents

| File | What it is |
|---|---|
| `FINDINGS.md` | What the lab has measured so far, each finding with its date, arrangement, engine and probe feed |
| `DESIGN_ROUTING_LAB.md` | The design, piece by piece. Pieces 1 to 4 are built. Piece 5 (V6 arrangement choices) is not designed. Piece 6 (the lab running in the browser tab, no server) is designed and waits for approval. Piece 7 (a live board) is built and tested on recorded traces, on the local server; the bench check on a board is still to come |
| `PLAN_ROUTING_LAB_1_HARNESS.md` to `PLAN_ROUTING_LAB_4_ARRANGEMENTS.md` | The four implementation plans, as carried out |
| `PLAN_ROUTING_LAB_7_LIVE_BOARD.md` | The plan for piece 7: connect to a Jumperless from the browser and show its routing live. Built through its page; the bench sitting and the firmware's release are still to come |
| `NOTES_2026-11-23_FIRMWARE_PORT7_AND_TAPS.md` | The firmware reading piece 7 rests on: what asking for the routing report costs on a board, the probe's connection, and how the voltage scan's taps share copper with the user's routing |
| `HANDOFF_2026-11-22_ROUTING_LAB_5.md` | Handoff for the next phase, V6 arrangement choices |
| `HANDOFF_2026-11-22_ROUTING_LAB_HOSTING.md` | What the lab needs of a server, which is nothing but the exact solver on demand (since built: `Routing/solver/service/`) |
| `jumperlos-side-changes.patch` | Two changes the lab once made to JumperlOS's own files, kept here because they were never pushed there: the bench test importing its cases from a shared `routing_cases.py`, and a paragraph in `CodeDocs/V6_CROSSBAR_MATRIX.md` pointing at the lab. `git -C <JumperlOS checkout> apply` puts them back; the paragraph's paths would then want this repository's |
| `img/` | The pictures in the repository's README, taken from the page (`examples`, `three-views`, `crossbars`, `through-the-op-amps`, `more-than-fits`, `tests-and-ranking`) |

## Old paths

The lab was built inside the JumperlOS repository and moved here on 2026-11-23, with its history: every commit
before "Layout for this repo" was made there and names files by the paths they had there. The four plans that were
carried out, and commit messages, were left as written. Read them with this table.

| Then (in JumperlOS) | Now |
|---|---|
| `tools/routing_lab/...` | `Routing/...` |
| `CodeDocs/DESIGN_ROUTING_LAB.md`, `CodeDocs/PLAN_ROUTING_LAB_*.md`, `CodeDocs/HANDOFF_*ROUTING_LAB*.md` | `Routing/docs/...` |
| `test/hil/routing_cases.py` | `Routing/routing_cases.py` |
| `test/hil/fabric_v5.py`, `test/hil/routing_check.py`, `test/hil/tools/` | the same files in the firmware checkout: `JumperlOS/test/hil/...` |
| `src/...` | `JumperlOS/src/...` |
| the README's "Findings so far" | `Routing/docs/FINDINGS.md` |
| the README's other sections | the README of the folder they are about (`Routing/README.md` lists them) |
| `--variant worktree`, `--variant main` | the firmware checkout as it is on disk, and a git ref of it: the `JumperlOS` submodule, or the checkout `JUMPERLOS` names |
| `python3 tools/routing_lab/lab.py ...` | `python3 Routing/lab.py ...` |
| the routers named `main@256229d` and `main@...` in older pages and notes | the same source as `JumperlOS@5374d38`: the lab's commits never changed `src/`, and the hash the lab gives that source is `9524e1cf...` throughout |
