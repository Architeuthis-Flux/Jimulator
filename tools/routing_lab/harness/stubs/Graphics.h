// SPDX-License-Identifier: MIT
// Host stand-in for src/Graphics.h.
#pragma once
#include <stdint.h>
#include <Arduino.h>
extern uint32_t gpioReadingColors[50];
extern uint8_t gpioAnimationBaseHues[10];
void changeTerminalColor(int termColor = -1, bool flush = true, Stream *stream = &Serial);
// Only the two fields the router reads; -1/-1 = no current-sense overlay wire.
struct CurrentSenseOverlayState { int virtualWireNode1 = -1; int virtualWireNode2 = -1; };
extern CurrentSenseOverlayState currentSenseOverlayState;
