# SPDX-License-Identifier: MIT
"""Edge cases: random netlists grown to the longest prefix the exact solver
proves routable.

One random legal list of bridges is drawn, and bisection finds the longest
prefix of it for which the solver finds a routing. Each probe routes the
prefix with the harness first, so the netlist asked about is the firmware's
own (its nets, its probe feed). A kept case is proved routable in its own
right, by a routing that is saved beside it; bisection only decides where to
look, so the edge may sit a bridge short of the true one where routability is
not monotone.

"Provably routable" is a ceiling for any router that keeps the rule's path
shape, not a claim that this router's method could reach it: the model does
not hold the copper the firmware reserves for sense taps.
"""
import cases
import ceiling
import generators
import runner

ROW_BIAS = 60                                       # percent of ends that are breadboard rows, as generators.fuzz
RULE_WORDS = {"firmware": "firmware-shaped paths", "copper": "any copper"}


class SolverFailed(Exception):
    """The solver died, or the lab does not stand behind what it said. That is
    no verdict on any netlist, and must not be written down as "not known"."""


def draw(rng, longest=80):
    """`longest` random bridges, ends drawn as generators.fuzz draws them. No
    pair twice (in either order; the firmware would merge it), and the list
    stays legal as it grows, so every prefix is legal too."""
    end = lambda: rng.choice(generators.ROWS) if rng.randrange(100) < ROW_BIAS else rng.choice(generators.SPECIALS)
    pairs, seen = [], set()
    while len(pairs) < longest:
        a, b = end(), end()
        if a != b and frozenset((a, b)) not in seen and generators.legal(pairs + [(a, b)]):
            seen.add(frozenset((a, b)))
            pairs.append((a, b))
    return pairs


def grow(binary, rng, name, seconds=20.0, longest=80, rule="firmware", arrangement=None, reasons=None):
    """(case, {"bridges": k, "closed": the solver's routing of it, "next_is":
    why one more bridge is not proved}) for the longest prefix found proved
    routable, or None when not even one bridge is. next_is: "not_routable"
    (proved), "unknown" (not known in `seconds`), "unplaced" (it uses a node
    the arrangement does not have), "dropped" (the firmware would not take
    the next prefix whole), "failed" (the harness crashed or timed out on it,
    so there was no netlist to ask about), "end" (all `longest` were proved).
    A prefix that needs no crosspoint at all fits, with an empty routing.

    On an arrangement the solver is asked on its copper, and every probe's
    netlist is the firmware's with the probe feed as the arrangement has it
    (the harness makes it on V5's copper: only the bridges it allows and
    their nets are used). With none, V5 with its feed, as ever.

    A prefix of which the firmware rejected, left out or refused a bridge is
    never asked about, so an edge case holds only bridges the firmware took.
    When nothing is proved, a `reasons` dict given is told why the first
    bridge alone is not: reasons["next_is"]. Raises SolverFailed when an
    answer comes back with an error."""
    pairs = draw(rng, longest)
    probe_line = {} if arrangement is None or arrangement.feed else {"probe": (0, 0)}
    case_of = lambda k, notes="": cases.Case(name, "edge", [(a, b, -1) for a, b in pairs[:k]], notes=notes, **probe_line)
    routings = {}                                   # prefix length -> the routing that proved it; never asked for twice

    def probe(k):
        result = runner.run_case(binary, case_of(k))
        if result["rejected"] or result["left_out"] or result["refused"]:
            return "dropped"
        if result.get("status") in ("crash", "timeout"):     # no netlist came back: nothing to ask, and nothing proved
            return "failed"
        said = ceiling.verdict(result, rule, seconds, fewest=False, arrangement=arrangement)
        if said.get("error"):
            raise SolverFailed("asked about %d bridges: %s" % (k, said["error"]))
        if said["verdict"] in ("routable", "nothing"):     # "nothing": the prefix needs no crosspoint, so it fits
            routings[k] = said["closed"] if said["verdict"] == "routable" else []
            return "routable"
        # a node the arrangement lacks was never asked about: that is not "not known in the time"
        return said["verdict"] if said["verdict"] in ("not_routable", "unplaced") else "unknown"

    proved, short, why = 0, longest + 1, "end"      # `proved` bridges fit; `short` do not, for the reason `why`
    while short - proved > 1:
        k = (proved + short) // 2
        said = probe(k)
        if said == "routable":
            proved = k
        else:
            short, why = k, said
    if not proved:
        if reasons is not None:
            reasons["next_is"] = why
        return None
    words = {"not_routable": "not routable, proved", "unknown": "not known after %g s" % seconds,
             "unplaced": "it uses a node the arrangement does not have",
             "failed": "the firmware's harness crashed or timed out on it",
             "dropped": "the firmware drops a bridge", "end": "none left, the list of %d ends here" % longest}
    notes = "proved routable with %s (%d bridges); one more bridge: %s" % (RULE_WORDS[rule], proved, words[why])
    return case_of(proved, notes), {"bridges": proved, "closed": routings[proved], "next_is": why}
