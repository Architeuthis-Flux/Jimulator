# Cases

A case is one netlist and the settings it is routed under (`Routing/cases.py`). Some are generated
(`Routing/generators.py`, `Routing/routing_cases.py`); the rest are the JSON files here, one folder per class.

## Classes

| class | what |
|---|---|
| example | 14 small cases that each show one kind of routing, with a title and a line about it (`cases/example/`): what the page lists first |
| dense | the 21 cases of JumperlOS's bench test `JumperlOS/test/hil/test_routing_dense.py`, as data in `Routing/routing_cases.py` |
| real | saved board states, imported with `import-state` into `cases/real/` |
| typical | 200 seeded circuits shaped like everyday use: an IC or two across the gap, power, ground, a few signals |
| fuzz | 2,000 seeded random netlists |
| stress | 21 cases each aimed at one scarce resource (one-chip floods, hub lanes, a 40-node net, maximum duplicates) |
| beyond | 3 cases over the fabric on purpose; scored, and must stay short-free |
| edge | 12 random netlists, each the longest prefix of its list that the solver proves routable with firmware-shaped paths (`cases/edge/`, grown by `lab.py edge`) |

Only the dense cases that the HIL suite requires to route are required to
route here. Everything else is scored. A JSON file dropped in `cases/<class>/`
joins that class.

Generated netlists are legal: no net holds a pair of nodes the firmware keeps
apart (a rail and a GPIO, DAC0 and DAC1, and so on; the table is checked
against the firmware's own). So an unrouted primary in `typical`, `fuzz` or
`stress` is the router's doing. `beyond` overflows on purpose.

## Examples

`cases/example/NN_<name>.json`, shown on the page in file order, each headed by its title. A file is a case like any
other; what makes it an example is its `notes`: a title on the first line and a sentence or two on the second, which
the page shows in its list and over the case. To add one, copy a file, give it the next number, change `name`,
`bridges` (`[node, node, copies]`; `-1` copies is the firmware's default, `0` one path) and `notes`, and run the
tests: every example must route in full on V5 with the firmware's router, except `more_than_fits`, which is there to
show what happens when it cannot. Node numbers are the firmware's (`JumperlOS/src/JumperlessDefines.h`): rows 1 to
60, GND 100, TOP_RAIL 101, BOTTOM_RAIL 102, DAC0 106, DAC1 107, ISENSE 108 and 109, ADC0 to ADC3 110 to 113,
UART_TX 116, UART_RX 117, GPIO_1 to GPIO_8 131 to 138, the Nano's D0 to D13 70 to 83 and A0 to A7 86 to 93.

## The dense cases

`Routing/routing_cases.py` began as the case list of JumperlOS's bench test, which pastes each onto a real board.
The firmware checkout's `test/hil/test_routing_dense.py` carries its own copy of the list, so a case changed in one
place is changed in the other by hand. (A change that had the bench test import this file was made while the lab
lived in the JumperlOS repository and was not pushed; it is kept as `Routing/docs/jumperlos-side-changes.patch`.)
