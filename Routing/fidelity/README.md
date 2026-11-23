# Board captures

The harness is only worth trusting if it routes what a real board routes.
This directory holds captures of the HIL dense suite taken on a V5, one
directory per firmware commit, named `board_<commit hash>`. While none of
them has passed for the harness as it is now, `lab.py run` ends with "not
verified against a board".

`board_0621e4f44e23` (2026-11-21) passes. Its `board_live_config.txt` is the
terminal's `~` print taken right after the run: the settings in RAM, which
are not always the ones in `config.txt` (`top_oled.enabled` is 1 there and 0
in the file, and that difference is what the first comparison tripped on).
The board was rebooted by the upload, not by pulling its power.

## Before the run

- Leave the board's `[routing] stack_rails` at its default (3). The suite's
  electrical proofs trigger extra rebuilds the replay does not repeat; with
  `stack_rails` at 0 each of those moves the GND alternator and the
  comparison could fail for that reason alone.
- No OLED lock and no serial lock (`top_oled.lock_connection`,
  `serial_1.lock_connection` at 0): they add bridges of their own. The probe
  settings stay at their defaults. A slot can lock the OLED too (`oled:
  {lockConnection: true}` in its own config); that one does not reach the
  capture, because every case pastes a state of its own that leaves it off.
- Let the board boot normally. Boot runs `oled.init()`, which sets
  `top_oled.enabled` in RAM, and the harness assumes exactly that.
- The capture of 2026-11-21 was taken with a `test_routing_dense.py` that imported its
  cases from a shared `routing_cases.py` (now `Routing/routing_cases.py`); in that form it
  ran on a V5 (78 checks, pass). That change was not pushed to JumperlOS, whose own
  `test/hil/test_routing_dense.py` carries the same cases inline.

## Taking a capture (one bench run)

1. Check out the commit to verify, with a clean tree, and note its hash:

   ```bash
   git rev-parse --short=12 HEAD
   ```

   The firmware's version string is not enough: several commits report the
   same version.

2. Build and flash it (a fresh worktree needs its flash-layer submodule
   first, or the build stops at `FlashInterfaceRP2040.h`):

   ```bash
   git submodule update --init lib/FatFS/lib/SPIFTL
   ```

   ```bash
   ~/.platformio/penv/bin/pio run -e jumperless_v5 -t upload
   ```

   The build rewrites the tracked `.pio/build/jumperless_v5/firmware.uf2`;
   put it back with `git restore` afterwards and never commit it here.

3. Power-cycle the board.

4. Run the dense suite once with captures on (it snapshots the bench first
   and restores it afterwards):

   ```bash
   JL_ROUTING_SNAP_DIR=Routing/fidelity/board_<hash> python3 JumperlOS/test/hil/test_routing_dense.py
   ```

   Then, before anything reboots the board, save what the terminal prints
   for `~` (the live config) into the capture directory as
   `board_live_config.txt`. The comparison does not read it; whoever chases
   a mismatch will.

5. Compare:

   ```bash
   python3 Routing/lab.py fidelity Routing/fidelity/board_<hash>
   ```

   A pass writes `verified.json` into the capture directory, naming the
   harness that passed.

6. Commit the capture directory, `verified.json` included.

## What the comparison does

It builds the harness from the commit in the directory's name, then routes
the 21 dense cases in the suite's order in one process, each under the
stacking settings printed at the top of its own capture. It compares, per
case, every path row, every chip-status claim and every closed crosspoint.

The board does not reboot between cases, and the router's GND alternator is
never reset, so its value when the suite starts depends on what the board
routed at boot. The replay is tried with both starting parities and passes if
either matches exactly. Any other difference is a fidelity bug in the harness
to chase, not to waive.

Sense-tap routes are not part of the comparison: the suite's captures do not
hold the `i!` report.

## Checked against a board

On 2026-11-21 a V5 was flashed with this tree's firmware (commit 0621e4f,
whose `src/` is main's 5374d38) and ran the HIL dense suite with captures on
(`fidelity/board_0621e4f44e23/`; the suite passed, 78 checks). The harness
routes all 21 cases as the board did: every path row, every chip-status
claim, every closed crosspoint.

The first comparison failed, on one thing. A board that has booted has run
`oled.init()` (`top_oled.connect_on_boot` defaults to 1), and that sets
`top_oled.enabled` in RAM whether or not a panel answers, while
`config.txt` can still say 0. From then on the probe feed's GPIO scan skips
the OLED's GPIO 7 and 8, so with DAC0 outside the probe window the feed sits
on GPIO 6. The harness had booted with the OLED off and put it on GPIO 8.
It now boots as the board does. No routed count and no finding below
changed with it.

A second, smaller check came from a report pasted on 2026-11-22 (ten bridges
made by hand, eight duplicates). Routing the same bridges, the lab closes the
same crosspoints as that board in 51 of 52 places. The one that differs is
the probe feed's end: GPIO 8 on that board, GPIO 6 in the lab. So that board
had the top OLED off when it routed, and the harness always assumes it on.
Where a board's feed sits on GPIO 7 or 8, expect that one difference.

The pass is recorded for the harness as it is (`verified.json` holds its
hash). Change anything under `harness/` and `lab.py run` says "not verified
against a board" again until `lab.py fidelity <capture>` is re-run, which
needs no board while the capture's commit still describes the router.
`fidelity/README.md` has the bench procedure for a new capture.
