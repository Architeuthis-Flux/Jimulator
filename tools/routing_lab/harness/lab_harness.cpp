// SPDX-License-Identifier: MIT
//
// Routing-lab harness: the firmware's own V5 routing sources, driven from
// stdin, printing what a board prints. Built by build.sh against one src/
// tree; see CodeDocs/DESIGN_ROUTING_LAB.md ("Piece 1") for the rules.
//
// The netlist is built and routed by firmware code only. This file feeds the
// bridge array, sets the policy inputs a case carries, and prints.
//
// stdin, one or more cases, routed in order in this one process:
//   case <name>
//   stack <paths> <rails> <dacs> <gpio> <adcs>
//   power <top> <bottom> <dac0> <dac1>
//   probe <auto_connect> <power_source>
//   block X <chip> <x>                    pin claimed for a phantom net
//   block Y <chip> <y>
//   bridge <node1> <node2> <dup>          node ids; dup -1 = default
//   end
// stdout, per case: "=== case <name>", then sections "--- rejected",
// "--- trace" (with --trace), "--- b", "--- xbar", "--- taps", "--- repeat"
// (with --repeat), then "=== end".
//
// flags:  --repeat N           route every case N times, report same/different
//         --gnd-alternator N   starting value of the router's GND K/L counter
//         --trace              the router's debug prints, under "--- trace"
// Exit 2 on a malformed line or flag.
#include <Arduino.h>
#include "JumperlessDefines.h"
#include "config.h"
#include "MatrixState.h"
#include "States.h"
#include "NetManager.h"
#include "NetsToChipConnections.h"
#include "InfraPaths.h"
#include "RouteSafety.h"
#include "NetVoltageScan.h"
#include "CH446Q.h"

#include <algorithm>
#include <string>
#include <vector>

extern bool debugNTCC3, debugNTCC5, debugNTCC6;   // NetsToChipConnections.cpp
extern char routeTrace[64];                       // RouteSafety.cpp: why the last tap plan failed

// A blocked pin is claimed for this net before routing. It is a valid net
// index (printChipStatus looks the net up) that no netlist reaches.
static const int kBlockNet = MAX_NETS - 1;

struct Bridge { int a, b, dup; };
struct Block { bool isX; int chip, pin; };

struct Case {
    std::string name;
    int stack[5] = {2, 3, 0, 0, 0};             // config.h defaults
    float power[4] = {0.0f, 0.0f, 3.33f, 0.0f}; // PowerState defaults
    int probe[2] = {1, 0};                      // auto_connect, power_source
    std::vector<Block> blocks;
    std::vector<Bridge> bridges;
};

static void die(int lineNo, const char* msg) {
    fprintf(stderr, "lab_harness: line %d: %s\n", lineNo, msg);
    exit(2);
}

// Reads one "case ... end" block. Returns false at end of input.
static bool readCase(Case& c, int& lineNo) {
    char line[512];
    bool inCase = false;
    while (fgets(line, sizeof line, stdin)) {
        lineNo++;
        if (char* hash = strchr(line, '#')) *hash = 0;
        char word[32];
        int off = 0;
        if (sscanf(line, "%31s%n", word, &off) != 1) continue;
        const char* rest = line + off;
        if (!strcmp(word, "case")) {
            char name[128];
            if (inCase || sscanf(rest, "%127s", name) != 1) die(lineNo, "expected 'case <name>'");
            c = Case();
            c.name = name;
            inCase = true;
        } else if (!inCase) {
            die(lineNo, "expected 'case <name>'");
        } else if (!strcmp(word, "stack")) {
            if (sscanf(rest, "%d %d %d %d %d", &c.stack[0], &c.stack[1], &c.stack[2], &c.stack[3], &c.stack[4]) != 5)
                die(lineNo, "expected 'stack <paths> <rails> <dacs> <gpio> <adcs>'");
        } else if (!strcmp(word, "power")) {
            if (sscanf(rest, "%f %f %f %f", &c.power[0], &c.power[1], &c.power[2], &c.power[3]) != 4)
                die(lineNo, "expected 'power <top> <bottom> <dac0> <dac1>'");
        } else if (!strcmp(word, "probe")) {
            if (sscanf(rest, "%d %d", &c.probe[0], &c.probe[1]) != 2)
                die(lineNo, "expected 'probe <auto_connect> <power_source>'");
        } else if (!strcmp(word, "block")) {
            char axis;
            Block b;
            if (sscanf(rest, " %c %d %d", &axis, &b.chip, &b.pin) != 3 || (axis != 'X' && axis != 'Y'))
                die(lineNo, "expected 'block X|Y <chip> <pin>'");
            b.isX = axis == 'X';
            if (b.chip < 0 || b.chip >= 12 || b.pin < 0 || b.pin >= (b.isX ? 16 : 8)) die(lineNo, "block pin out of range");
            c.blocks.push_back(b);
        } else if (!strcmp(word, "bridge")) {
            Bridge b;
            if (sscanf(rest, "%d %d %d", &b.a, &b.b, &b.dup) != 3) die(lineNo, "expected 'bridge <node1> <node2> <dup>'");
            c.bridges.push_back(b);
        } else if (!strcmp(word, "end")) {
            return true;
        } else {
            die(lineNo, "unknown line");
        }
    }
    if (inCase) die(lineNo, "missing 'end'");
    return false;
}

// The policy inputs a case carries. Everything else stays at the firmware's
// own defaults (struct config's initialisers; the state stub's PowerState).
static void applySettings(const Case& c) {
    jumperlessConfig.routing.stack_paths = c.stack[0];
    jumperlessConfig.routing.stack_rails = c.stack[1];
    jumperlessConfig.routing.stack_dacs = c.stack[2];
    jumperlessConfig.routing.stack_gpio = c.stack[3];
    jumperlessConfig.routing.stack_adcs = c.stack[4];
    jumperlessConfig.probe.auto_connect = c.probe[0];
    jumperlessConfig.probe.power_source = c.probe[1];
    globalState.power.topRail = c.power[0];
    globalState.power.bottomRail = c.power[1];
    globalState.power.dac0 = c.power[2];
    globalState.power.dac1 = c.power[3];
}

// Feeds the bridge array and runs the head of the firmware's rebuild, in the
// order src/Commands.cpp runs it. A bridge the firmware's own rules refuse
// (isConnectable, connectionAllowed) or with equal ends is listed, not fed.
static void routeCase(const Case& c, std::vector<Bridge>& rejected) {
    ConnectionState& cs = globalState.connections;
    cs.numBridges = 0;
    for (const Bridge& b : c.bridges) {
        bool ok = b.a != b.b && isConnectable(b.a) && isConnectable(b.b) && connectionAllowed(b.a, b.b) &&
                  cs.numBridges < MAX_BRIDGES;
        if (!ok) {
            rejected.push_back(b);
            continue;
        }
        cs.bridges[cs.numBridges][0] = (int16_t)b.a;
        cs.bridges[cs.numBridges][1] = (int16_t)b.b;
        cs.bridges[cs.numBridges][2] = (int16_t)b.dup;
        cs.bridgeColors[cs.numBridges] = 0xFFFFFFFF;
        cs.numBridges++;
    }
    infraEvaluate();
    clearAllNTCC();
    // clearAllNTCC() is the only place the router resets chip status, so a
    // claim made here stands for the whole rebuild.
    for (const Block& b : c.blocks) {
        chipStatus& chip = cs.chipStates[b.chip];
        if (b.isX) chip.xStatus[b.pin] = kBlockNet;
        else chip.yStatus[b.pin] = kBlockNet;
    }
    loadBridgesFromState();
    getNodesToConnect();
    bridgesToPaths();
}

// The `b` command's report: the block in src/SingleCharCommands.cpp that
// prints "pathDuplicates:" through printChipStatus. That file cannot be
// linked, so its fifteen print lines are repeated here.
static void printBReport() {
    Stream* target = &Serial;
    target->print("\n\rpathDuplicates: ");
    target->println(jumperlessConfig.routing.stack_paths);
    target->print("dacDuplicates: ");
    target->println(jumperlessConfig.routing.stack_dacs);
    target->print("railsDuplicates: ");
    target->println(jumperlessConfig.routing.stack_rails);
    target->print("gpioDuplicates: ");
    target->println(jumperlessConfig.routing.stack_gpio);
    target->print("adcDuplicates: ");
    target->println(jumperlessConfig.routing.stack_adcs);
    couldntFindPath(1);
    target->print("\n\rBridge Array\n\r");
    printBridgeArray(target);
    target->print("\n\n\n\rPaths\n\r");
    printPathsCompact(1, target);
    target->print("\n\n\rChip Status\n\r");
    printChipStatus(target);
    target->print("\n\n\r");
}

// The "sent" view. Crossbar sends are NOT exercised on the host: CH446Q.cpp
// is PIO and DMA code and is not linked. This repeats the bookkeeping of its
// sendAllPaths(clean = 1) / sendPath: every hop of every path whose chip, x
// and y are in range is a closed crosspoint. So "sent equals planned" cannot
// fail here; the HIL suite keeps that check.
static void fillSentViewFromPaths() {
    memset(lastChipXY, 0, sizeof lastChipXY);
    for (int i = 0; i < numberOfPaths; i++) {
        const pathStruct& p = globalState.connections.paths[i];
        for (int h = 0; h < 4; h++) {
            int chip = p.chip[h], x = p.x[h], y = p.y[h];
            if (chip >= 0 && chip < 12 && x >= 0 && x < 16 && y >= 0 && y < 8) {
                lastChipXY[chip].connected[y] |= (uint16_t)(1u << x);
            }
        }
    }
}

// Port 7's ":crossbar" reply, in the format of usbSer3_sendCrossbar
// (src/tubes/Ser3Backchannel.cpp): chip-major, one 16-bit X mask per Y.
static void printXbar() {
    printf("xbar{12x8:");
    for (int chip = 0; chip < 12; chip++) {
        for (int y = 0; y < 8; y++) printf("%04x", lastChipXY[chip].connected[y]);
    }
    printf("}\n");
}

// The net-voltage scan's node list. A COPY of one firmware rule: isScannable()
// and rebuildScanList() in src/sensing/NetVoltageScan.cpp, which needs the ADC
// ring and cannot be linked. Keep the two in step. (The display-bus exclusion
// is left out: there is no breadboard display on the host.)
static std::vector<int> harnessScanList(bool& gndInUse) {
    std::vector<int> nodes;
    gndInUse = false;
    for (int i = 1; i < MAX_NETS; i++) {
        const netStruct& net = globalState.connections.nets[i];
        if (net.number <= 0 || net.specialFunction == EMPTY_NET) continue;
        if (net.virtual_net) continue;
        for (int n = 0; n < MAX_NODES; n++) {
            int node = net.nodes[n];
            if (node <= 0) break;
            if (node == GND) gndInUse = true;
            bool source = node == GND || node == TOP_RAIL || node == BOTTOM_RAIL || node == DAC0 || node == DAC1;
            if (node >= NODE_VOLTAGE_MAX || source || (node >= ADC0 && node <= ADC4) || node == ADC7_PROBE) continue;
            if (std::find(nodes.begin(), nodes.end(), node) == nodes.end()) nodes.push_back(node);
        }
    }
    return nodes;
}

// One line per scanned node: the sense route the firmware's own planner
// (planFastPath, RouteSafety.cpp) finds for it against the routing just made,
// printed as NetVoltageScan.cpp's printSenseRoute prints it for `i!`. A dry
// run: nothing is closed or claimed. The ADC is the first one the firmware
// says is free, as in the scan's own report.
static void printTaps() {
    uint8_t freeMask = infraFreeAdcMask(0x0F);
    if (!freeMask) {
        printf("skipped: no free ADC\n");
        return;
    }
    int adc = __builtin_ctz(freeMask);
    bool gndInUse = false;
    std::vector<int> nodes = harnessScanList(gndInUse);
    if (!gndInUse) nodes.push_back(GND);            // the scan's auto-zero tap
    for (int node : nodes) {
        printf("[nvscan] route %d:", node);
        pathStruct r;
        if (!planFastPath(node, ADC0 + adc, &r)) {
            printf(" (none - lanes busy, short, or node unknown) tier4:%s\n", routeTrace);
            continue;
        }
        for (int h = 0; h < 4; h++) {
            if (r.chip[h] < 0 || r.x[h] < 0 || r.y[h] < 0) continue;
            printf(" %c(x%d,y%d)", 'A' + r.chip[h], r.x[h], r.y[h]);
        }
        printf(" -> ADC%d\n", adc);
    }
}

// Runs fn with the firmware's prints going into a string.
template <typename F> static std::string captured(F fn) {
    char* buf = nullptr;
    size_t len = 0;
    FILE* mem = open_memstream(&buf, &len);
    FILE* saved = g_out;
    bool savedQuiet = g_quiet;
    g_out = mem;
    g_quiet = false;
    fn();
    g_quiet = savedQuiet;
    g_out = saved;
    fclose(mem);
    std::string s(buf, len);
    free(buf);
    return s;
}

struct Pass {
    std::vector<Bridge> rejected;
    std::string trace, b;
};

// One rebuild of one case, exactly what a second identical case block on
// stdin would get: settings, infraEvaluate and all. Nothing is skipped on a
// repeat, because the probe-feed code keeps state between rebuilds.
static Pass runPass(const Case& c, bool trace) {
    Pass p;
    applySettings(c);
    if (trace) {
        p.trace = captured([&] { routeCase(c, p.rejected); });
    } else {
        g_quiet = true;
        routeCase(c, p.rejected);
    }
    fillSentViewFromPaths();
    p.b = captured(printBReport);
    return p;
}

// The b report without its header (the five stack settings and the unrouted
// list): what must be identical when one case is routed twice.
static std::string afterHeader(const std::string& b) {
    size_t at = b.find("Bridge Array");
    return at == std::string::npos ? b : b.substr(at);
}

static void runCase(const Case& c, int repeat, bool trace) {
    Pass first = runPass(c, trace);
    printf("=== case %s\n--- rejected\n", c.name.c_str());
    for (const Bridge& b : first.rejected) printf("%d %d\n", b.a, b.b);
    if (trace) printf("--- trace\n%s\n", first.trace.c_str());
    printf("--- b\n%s\n--- xbar\n", first.b.c_str());
    printXbar();
    printf("--- taps\n");
    printTaps();
    if (repeat > 1) {
        bool same = true;
        for (int i = 1; i < repeat; i++) {
            if (afterHeader(runPass(c, false).b) != afterHeader(first.b)) same = false;
        }
        printf("--- repeat\n%s\n", same ? "same" : "different");
    }
    printf("=== end\n");
    fflush(stdout);
}

int main(int argc, char** argv) {
    int repeat = 1;
    bool trace = false;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--repeat") && i + 1 < argc) {
            repeat = atoi(argv[++i]);
        } else if (!strcmp(argv[i], "--gnd-alternator") && i + 1 < argc) {
            gndChipAlternator = atoi(argv[++i]);
        } else if (!strcmp(argv[i], "--trace")) {
            trace = true;
        } else {
            fprintf(stderr, "lab_harness: unknown flag %s\n", argv[i]);
            return 2;
        }
    }
    if (trace) debugNTCC = debugNTCC2 = debugNTCC3 = debugNTCC5 = debugNTCC6 = true;

    initNets();
    // A board boots with the probe's measure buffer wanted (Probing.cpp calls
    // this from routableBufferPower); probe.auto_connect then gates the feed.
    infraSetProbePowerEnabled(true);

    Case c;
    int lineNo = 0;
    while (readCase(c, lineNo)) runCase(c, repeat, trace);
    return 0;
}
