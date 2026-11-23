# The exact solver, and the ceilings it gives

`solve.py` is a CP-SAT model (OR-tools) that knows nothing of the lab or of V5: it is handed copper and a netlist
and says whether the netlist can be routed, with the fewest crosspoints when it can. `Routing/ceiling.py` asks it.
`service/` is the same solver as a web service (its own README).

## Ceilings

How far a routing is from what the copper allows. The model is the judge's:
a wire carries one net, and a node outside the net (in another net, or in no
net) may not be touched. A bridge the firmware rejected, left out or refused
is never searched for and never counts as a miss.

**miss: the path a failed bridge had.** For each bridge the router failed,
the cheapest path through copper that is free or already carries its net,
with everything else where the router put it: fewest new crosspoints, then
fewest in all. Each failed bridge is taken alone and shown its cheapest path,
so two paths may use the same free copper. That does not by itself mean only
one of those bridges could be made: there may be other paths (finding 10
below is such a case). A miss is a statement about copper, not about the
firmware's path shape: the path may be longer than the four crosspoints one
firmware path holds, or ride copper the net already has.

**spare: copies the free copper still allows.** For each routed bridge, up
to eight more paths of at most four new crosspoints each, through wires that
carry nothing and are no node's copper, sharing no wire with each other; then
the bridge's resistance with all of them closed. Each bridge is taken alone,
as if all the free copper were its own, and the firmware holds some copper
back so sense taps stay reachable. So this is "available in copper", an upper
bound, not what the firmware would give. The firmware's tap planner is not
yet asked which of them it would allow.

**The exact solver** answers what the two searches cannot: with everything
free to move, can this netlist be routed at all, and with how few
crosspoints?

```bash
python3 Routing/lab.py solver-setup      # once; needs the network
python3 Routing/lab.py ceiling --classes dense,real,beyond
python3 Routing/lab.py ceiling --case nano_dense_metric --rule copper --seconds 60
```

`solver-setup` installs OR-tools 9.15 into `build/solver-venv`. Without it
everything else works, the solver's tests skip, and the page says how to get
it. An environment a failed setup left behind, with no OR-tools in it,
counts as not installed.

The netlist asked about is the case's as the firmware built it: the bridges
it allowed, its nets, and its probe feed where the firmware put it. Two
rules:

- **firmware-shaped paths**: every bridge is its own path of at most four
  crosspoints, as `pathStruct` holds one; paths of one net may share copper.
- **any copper**: the nodes a net's bridges tie together are joined by any
  tree through the copper, of any length. (Where the firmware dropped the
  bridge between two parts of one net, the parts need not be joined.)

A verdict is one of:

- **routable**, with the fewest crosspoints (`= 16`, proved) or the fewest
  found before the time ran out (`<= 18`). The lab checks the solver's
  routing with its own copper model before saying so (`ceiling.faults`: only
  offered crosspoints, no piece of copper holding two nets, every bridge
  joined, and under the firmware rule within four crosspoints). An answer
  that fails is shown as an error, not a verdict. The routing drawn is one
  of many with that count.
- **not routable**, proved. This rests on the solver and on the model, which
  the tests exercise on fabrics small enough to check on paper. If the
  solver says it of a case whose copper, as the router left it, is a routing
  the lab's own check accepts, the lab reports that the model is wrong
  instead of the verdict.
- **unknown** after the time limit (20 s by default). An answer near the
  limit is not the same from run to run; nothing committed rests on one.

What a verdict does not say. The model does not hold the copper the firmware
reserves for sense taps, nor its duplicates: "routable" is a ceiling for any
router that keeps the rule's path shape, not a promise that this router's
method could reach it. And fewer crosspoints is not better by itself: the
fewest shares as much copper inside a net as it can.

**Edge cases** (`lab.py edge --seed 1 --count 12`, about two minutes a case)
are where the router and the ceiling are compared. A random legal list of 80
bridges is drawn as `fuzz` draws its ends, and bisection finds the longest
prefix the solver proves routable with firmware-shaped paths. A prefix of
which the firmware itself drops a bridge is never asked about. Each case is
saved with the routing that proves it (`cases/edge/proof/`), and a test
checks every one of those routings against the harness's netlist with no
solver, so "provably routable" does not depend on the solver being installed
or on its luck with the clock. If the solver fails while a case is grown,
the command stops with exit 1 and writes nothing for that case. A proof
routes the probe feed too, from where today's firmware puts it: a firmware
change that moves the feed fails that test although the case's own bridges
still fit, and the cases are then grown again.

How near the true edge a case sits depends on why it stopped. Where the next
bridge is proved not to fit, it is at the edge of its list, save that
bisection assumes a longer prefix never fits where a shorter one does not.
Where the next bridge is only "not known" after the time limit, the true
edge may be several bridges further on: the case is the longest the solver
could prove, not the longest that fits. `lab.py run --classes edge` is the
headline score: how many of these the router routes in full.

`lab.py ceiling --classes edge` can answer "unknown" for an edge case (two
of the twelve, on 2026-11-21). It looks for the fewest crosspoints inside
its limit, which is a harder search than the one that grew the case, and
these cases sit at what the solver can do in 20 s. The saved proof is what
stands.

The headline on 2026-11-21, router at 5374d38: **1 of 12**. The twelve cases
hold 49 to 60 bridges each; for five the next bridge is proved not to fit,
for seven it is not known after 20 s. Of their 655 primaries (each case's
probe feed is one) the router routes 603. "Findings so far" (`Routing/docs/FINDINGS.md`) has the detail.
