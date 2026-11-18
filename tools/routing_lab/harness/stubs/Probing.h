// SPDX-License-Identifier: MIT
// Host stand-in for src/Probing.h: there is no probe on the host.
#pragma once
struct ProbingStub { int checkProbeButtonState(void) { return 0; } };
extern ProbingStub probing;
extern volatile unsigned long blockProbeButton;
extern volatile unsigned long blockProbeButtonTimer;
extern int probePowerDAC;
void probeGpioPowerHwClaim(int gpioDefIdx);
void probeGpioPowerHwRelease(int gpioDefIdx);
