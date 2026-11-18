// SPDX-License-Identifier: MIT
// Host stand-in for src/routing/States.h: only the parts of JumperlessState
// the routing sources touch. The real header pulls in the whole firmware.
#pragma once
#include <Arduino.h>
#include "JumperlessDefines.h"
#include "MatrixState.h"

struct justXY { int8_t xStatus[16]; int8_t yStatus[8]; };

struct ConnectionState {
    int16_t bridges[MAX_BRIDGES][3];
    int16_t numBridges;
    netStruct nets[MAX_NETS];
    int16_t numNets;
    uint32_t bridgeColors[MAX_BRIDGES];
    pathStruct paths[MAX_BRIDGES];
    int16_t numPaths;
    bool pathsCacheValid;
    chipStatus chipStates[12];
    struct justXY chipXY[12];
    bool chipStatesCacheValid;
    void syncNetsFromBridges() {}        // only reached from the slot-load scrub, which the harness never runs
};

// Defaults are PowerState's in States.cpp: a fresh board parks DAC0 at 3.33 V.
struct PowerState {
    float topRail = 0.0f;
    float bottomRail = 0.0f;
    float dac0 = 3.33f;
    float dac1 = 0.0f;
};

struct DisplayState {                    // no custom net colours or names on the host
    bool getNetColor(int, rgbColor&, uint32_t&, char*) { return false; }
    const char* getNetName(int) { return nullptr; }
};

struct ConfigState {                     // no GPIO is owned by MicroPython or PWM; no OLED lock
    bool gpioPythonOwned[10] = {};
    bool gpioPwmEnabled[10] = {};
    int gpioDirection[10] = {};
    int oledLockConnection = 0;
};

struct JumperlessState {
    ConnectionState connections;
    PowerState power;
    DisplayState display;
    ConfigState config;
    bool isEphemeralConnection(int, int) { return false; }             // no measure-mode bridges
    void adjustEphemeralIndicesAfterBridgeRemoval(int) {}
};
extern JumperlessState globalState;
