# Board captures

The harness is only worth trusting if it routes what a real board routes.
This directory holds captures of the HIL dense suite taken on a V5, one
directory per firmware commit, named `board_<commit hash>`. None is checked in
yet: until one is, `lab.py run` ends with "not verified against a board".

## Before the run

- Leave the board's `[routing] stack_rails` at its default (3). The suite's
  electrical proofs trigger extra rebuilds the replay does not repeat; with
  `stack_rails` at 0 each of those moves the GND alternator and the
  comparison could fail for that reason alone.
- No OLED lock and no serial lock (`top_oled.lock_connection`,
  `serial_1.lock_connection` at 0): they add bridges of their own. The probe
  settings stay at their defaults.
- `test/hil/test_routing_dense.py` now imports its cases from
  `test/hil/routing_cases.py`. The data was moved unchanged and checked on
  the host, but this run is the first time the edited test meets a board.

## Taking a capture (one bench run)

1. Check out the commit to verify, with a clean tree, and note its hash:

   ```bash
   git rev-parse --short=12 HEAD
   ```

   The firmware's version string is not enough: several commits report the
   same version.

2. Build and flash it:

   ```bash
   ~/.platformio/penv/bin/pio run -e jumperless_v5 -t upload
   ```

3. Power-cycle the board.

4. Run the dense suite once with captures on (it snapshots the bench first
   and restores it afterwards):

   ```bash
   JL_ROUTING_SNAP_DIR=tools/routing_lab/fidelity/board_<hash> python3 test/hil/test_routing_dense.py
   ```

5. Compare:

   ```bash
   python3 tools/routing_lab/lab.py fidelity tools/routing_lab/fidelity/board_<hash>
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
