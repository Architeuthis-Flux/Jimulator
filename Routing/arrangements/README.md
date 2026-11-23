# Arrangements, and the lane ranking

An arrangement is crossbar copper: V5's own, or a JSON file here saying what differs from V5.
`Routing/arrangement.py` reads one, `Routing/score.py` compares two, `Routing/rank.py` ranks the wires of one.

## Arrangements

An arrangement is the crossbar copper: which wire is on each chip pin, and
which node is which wire. V5's is `JumperlOS/test/hil/fabric_v5.py`. Any other is a
small JSON file under `arrangements/` that says what it changes from V5:

| key | what it says |
|---|---|
| `"about"` | one line of text |
| `"base"` | `"v5"`, the only base there is |
| `"feed"` | `false` when the probe feed is not routed through the fabric (V6 takes it off); `true` when not given, and then every end the feed can have must keep a pin: BUF_IN, DAC0 and GPIO_1 to GPIO_8 |
| `"remove"` | wire names: every pin on such a wire is taken away |
| `"pins"` | `{"A.X7": "TOP_RAIL", "K.X2": null}`: a pin put on a wire (and so joined to every other pin of that name), or taken away |
| `"chips"` | `{"M": {"role": "sf", "x": [16 names or null], "y": [8 names or null]}}`: a chip added; role `"bb"` or `"sf"` |
| `"nodes"` | `{"150": {"wire": "PORT_0", "name": "PORT_0"}, "139": null}`: a node added or moved, or removed |

A pin taken away is no copper at all: nothing routes over it and no search
passes it. A node whose last pin is taken away drops out, and a netlist that
uses it "cannot be placed" there, which is neither routable nor not.

Mistakes `check` lists besides the obvious ones, all at once: a key given
twice in one object (JSON would keep only the last); a pin written another
way than `A.X7` (no `A.X07`); a key a chip or a node does not have; a name
with spaces at its ends; and a new wire name on a single X pin with no node
on it, under `"pins"` or in a new chip's own list, which is nearly always a
misspelt name (`TOP_RIAL`). A spare pin left as a no-connect is named as V5
names one, `unconnected-...` (as V5's bounce rows are), and is no slip. A
one-pin wire on a Y pin is a bounce row, a shape V5 has eight of, so it is
taken for a slip only when it is a near copy of a name V5 has. A misspelling
repeated on two pins or more is not caught, nor is one unlike any name (`3O`
for `30`).

Two ship. `v6_feed_off` is V5's copper with the probe feed off the fabric.
`v6_rails_on_chips` is the worked example, P1 + P2 of
`Routing/docs/V6_CROSSBAR_MATRIX.md`: the feed off, and on every breadboard chip
the second lane of three doubled pairs given to TOP_RAIL, BOTTOM_RAIL and
GND. Its file is the feed line and 24 pins:

```json
{"about": "...", "base": "v5", "feed": false,
 "pins": {"A.X7": "TOP_RAIL", "A.X11": "BOTTOM_RAIL", "A.X15": "GND", "B.X5": "TOP_RAIL", "...": "..."}}
```

```bash
python3 Routing/lab.py arrangement list                       # each one: feed, who can answer for it
python3 Routing/lab.py arrangement show v6_rails_on_chips     # pin by pin; changed pins starred
python3 Routing/lab.py arrangement check my_idea.json         # every mistake, each with its pin or name
python3 Routing/lab.py arrangement score v6_rails_on_chips    # the solver, against V5, on the same netlists
```

To try an idea: write the file, `check` it, pick it on the page. A file with
a mistake is listed greyed with its problems; nothing runs on it, and
nothing else stops.

**Who can answer for it.** The firmware's router can route an arrangement
only when that is V5 with pins taken away (`"remove"`, or pins set to
`null`): the harness blocks those pins and the real router routes around
them. `lab.py run --arrangement`, the page's Run and the ranking do that.
Any arrangement that moves a pin, adds a chip or adds a node is the solver's
alone, because the router has V5's chips and pins as literals in its code.
So is one that takes away one pin of a node that keeps another (GND has a
pin on K and one on L): the firmware still has the node there and closes the
pin, blocked or not. With the feed on the fabric, the file must keep every
end the feed can have: BUF_IN, and DAC0, or, when DAC0 is not free for it (a
bridge on DAC0, DAC0 out of the probe's window as in the dense cases, or the
probe's power set to come from a GPIO first), the highest free GPIO from 8
down to 1. (The harness keeps the top OLED on, so it never feeds from GPIO 7
or 8; a board with the OLED off can, and the rule keeps them.)
Should the router still close a crosspoint on a blocked pin, that case fails
and says which.

**`arrangement score NAME [--against v5]`** asks the solver the same netlists
on both. The netlists are the firmware's own: each case is run once by the
harness on V5's copper with NAME's feed, for the bridges the firmware allows
and the nets it makes of them, and then both arrangements are asked. It
prints both verdicts and both fewest-crosspoint counts for every case, then
what fits on only one, and the crosspoints each needs over the cases proved
on both. `--grow N` also grows N of the edge class's random lists on each
(the longest prefix proved routable; about a minute and a half a list an
arrangement). On the page, pick the arrangement, open a case of a run with
the same feed, and ask under "ceiling": the solver's routing is drawn as the
picture, and the case panel says whose routing it is.

**What the solver's answer is worth for V6.** It says a routing exists on
that copper with each bridge on its own path of at most four crosspoints, or
proves there is none. A V6 router may find less than that, and one with
longer paths or other rules may find more. It knows nothing of sense taps,
of what the firmware reserves, or of resistance beyond counting crosspoints.
So read a score as: this copper can carry these netlists, and for this many
crosspoints at best.

## The lane ranking

Which wires could a board do without? The wires ranked are the ones that are
only copper between chips: the 48 lanes between breadboard chips, the 32
lanes from a breadboard chip to an SF chip, the 8 bounce rows and the 6 hub
lanes. That is 94 on V5. A node's own wire is not ranked.

```bash
python3 Routing/lab.py rank                    # the router's part, about three minutes
python3 Routing/lab.py rank --needed           # and the solver's; see below for how long
python3 Routing/lab.py rank --wires KL,AK --classes dense
```

It routes the battery on the arrangement (`v6_feed_off` unless
`--arrangement` says otherwise: V6 takes the probe feed off the fabric),
then again without each wire in turn, and prints one line a wire. The
ranking is kept under `build/rank/`, one file a router and arrangement. A
ranking of some wires (`--wires`) or of one case (`--case`) is printed and
not kept, so it cannot take the place of the whole one; `--json FILE` writes
it.

There are two answers, and they are different questions:

- **loss**: what the firmware's router loses without the wire, in primaries
  routed and in cases fully routed. **It is signed.** With a wire gone the
  router sometimes routes more, because its search takes another turn, and
  that is printed as a negative loss, not as zero. A loss is about this
  router. It is not the answer to "is the wire needed".
- **needed by / not needed / unknown** (`--needed`): for every netlist the
  solver is asked whether it can be routed without the wire at all. "Needed"
  is said only on a proof that it cannot. "Not needed" is said only on a
  routing that does without it. Anything else, a solver out of time
  included, is "unknown" and counts as neither.

**Usage is no guide.** The table has how many cases use each wire, because
people ask, but it follows the router's search order. With the feed off the
least used wire, IJ, is in 10 of 256 cases and costs the router nine
primaries.

**One wire at a time.** Every line is about taking that one wire away. Two
wires that are each not needed may be needed together. To ask about a set,
take them all away and run: with the page's ranking open, click the wires (in
the drawing or the table), then "Run without these". The run is on the
arrangement "NAME without A, B"; the text of a file for it is shown under
the Arrangement picker, to save under `arrangements/` if it is worth
keeping, and then `arrangement score` can ask the solver about it.

`--needed` asks only where it has to (a wire no known routing of the case
touches is settled without a question), about a second a question. Over its
default classes (dense, real, typical and stress, 244 netlists) it took 40
minutes on top of the router's three; with `--needed-classes
dense,real,stress` (44 netlists), six. Run nothing else heavy beside it: an
answer that runs out of its 5 s is "unknown". A ranking made again without
`--needed` keeps what the solver proved before, as long as the arrangement's
copper is what it was. The solver's work is never thrown away: whenever a
file holding it would be written over (the copper changed, or a new
`--needed` over other classes), the old file is first copied aside beside it
as `<name>.set-aside.json` (then `-2`, `-3`: one never replaces another), and
the command and the page's ranking say so. The page also says when a ranking is
of copper the arrangement's file no longer has.

**The page's ranking** shows the file for the Router named and the arrangement
picked: the fabric tinted by the router's loss or by how many netlists need
each wire (dim through teal to yellow; a wire the router routes more without
is blue; nothing there is red), and the table, sorted by a click on a
heading. "Rank now" makes the router's part from the
page, with its progress; the solver's part is started from the command line.
