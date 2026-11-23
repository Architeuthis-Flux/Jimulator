// SPDX-License-Identifier: MIT
// Host stand-in for src/Peripherals.h (and RoutableGpio.h's gpioState).
#pragma once
#include <stdint.h>
extern int showADCreadings[8];
extern int gpioNet[50];
extern uint8_t gpioReading[50];
extern uint8_t gpioState[50];
extern const int gpioDef[10][3];
extern float adcReadings[8];
float getDacVoltage(int dac);          // the case's DAC voltages (globalState.power)
bool dacUserClaimed(int dac);
void setDac0voltage(float value = 0.0, int save = 1, int saveEEPROM = 0, bool checkProbePower = false);
void setDac1voltage(float value = 0.0, int save = 1, int saveEEPROM = 0, bool checkProbePower = false);
uint32_t measurementToColor(float measurement, float min = -8.0, float max = 8.0);
