// SPDX-License-Identifier: MIT
//
// Routing-lab harness: the firmware's own V5 routing sources, driven from
// stdin, printing what a board prints. Built by build.sh against one src/
// tree; see CodeDocs/DESIGN_ROUTING_LAB.md ("Piece 1") for the rules.
//
// The netlist is built and routed by firmware code only. This file feeds the
// bridge array, sets the policy inputs a case carries, and prints.
//
// stdin, one or more cases:
//   case <name>
//   stack <paths> <rails> <dacs> <gpio> <adcs>
//   power <top> <bottom> <dac0> <dac1>
//   probe <auto_connect> <power_source>
//   bridge <node1> <node2> <dup>          node ids; dup -1 = default
//   end
// stdout, per case: "=== case <name>", then sections "--- rejected",
// "--- b", "--- xbar", then "=== end". Exit 2 on a malformed line.
#include <Arduino.h>
#include "JumperlessDefines.h"
#include "config.h"
#include "MatrixState.h"
#include "States.h"
#include "NetManager.h"
#include "NetsToChipConnections.h"
#include "InfraPaths.h"
#include "CH446Q.h"

#include <string>
#include <vector>

struct Bridge { int a, b, dup; };

struct Case {
    std::string name;
    int stack[5] = {2, 3, 0, 0, 0};            // config.h defaults
    float power[4] = {0.0f, 0.0f, 3.33f, 0.0f}; // PowerState defaults
    int probe[2] = {1, 0};                     // auto_connect, power_source
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

static void runCase(const Case& c) {
    std::vector<Bridge> rejected;
    applySettings(c);
    g_quiet = true;
    routeCase(c, rejected);
    fillSentViewFromPaths();

    printf("=== case %s\n--- rejected\n", c.name.c_str());
    for (const Bridge& b : rejected) printf("%d %d\n", b.a, b.b);
    printf("--- b\n");
    g_quiet = false;
    printBReport();
    g_quiet = true;
    printf("\n--- xbar\n");
    printXbar();
    printf("=== end\n");
    fflush(stdout);
}

int main() {
    initNets();
    // A board boots with the probe's measure buffer wanted (Probing.cpp calls
    // this from routableBufferPower); probe.auto_connect then gates the feed.
    infraSetProbePowerEnabled(true);

    Case c;
    int lineNo = 0;
    while (readCase(c, lineNo)) runCase(c);
    return 0;
}
