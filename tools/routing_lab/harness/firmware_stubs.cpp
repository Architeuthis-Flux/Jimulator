// SPDX-License-Identifier: MIT
//
// Every firmware symbol the routing sources reference that the harness does
// not link: one definition each, with what it stands in for. Hardware is a
// no-op. Display and probe state is "nothing there". Policy inputs are set
// from the case in lab_harness.cpp. Nothing here builds a netlist or routes.
#include <Arduino.h>
#include <EEPROM.h>
#include "JumperlessDefines.h"
#include "config.h"
#include "MatrixState.h"
#include "States.h"
#include "ArduinoStuff.h"
#include "CH446Q.h"
#include "FakeGpio.h"
#include "Graphics.h"
#include "Highlighting.h"
#include "LEDs.h"
#include "Peripherals.h"
#include "Probing.h"

// --- streams and storage ----------------------------------------------------
bool g_quiet = true;                 // lab_harness.cpp opens it for the b report
Stream Serial;                       // USB serial: stdout
Stream Jerial;                       // the firmware's tee'd serial
Stream USBSer3;                      // the backchannel port
EEPROMClass EEPROM;                  // no EEPROM: reads 0

// --- firmware state -----------------------------------------------------------
JumperlessState globalState;         // stubs/States.h
struct config jumperlessConfig;      // the firmware's own defaults, from config.h

// --- crossbar hardware --------------------------------------------------------
chipXYBitfield lastChipXY[12];       // filled by fillSentViewFromPaths()
int ch446q_timeout_count = 0;
void sendXYrawUnchecked(int, int, int, int, unsigned long) {}   // no crossbar to send to
void updateLiveCrossbarDisplay(void) {}                         // no OLED crossbar view

// --- GPIO, ADC and DAC hardware ---------------------------------------------
// gpioDef is the firmware's table (src/Peripherals.cpp): {pin, node, index}.
const int gpioDef[10][3] = {{20, RP_GPIO_1, 0}, {21, RP_GPIO_2, 1}, {22, RP_GPIO_3, 2}, {23, RP_GPIO_4, 3},
                            {24, RP_GPIO_5, 4}, {25, RP_GPIO_6, 5}, {26, RP_GPIO_7, 6}, {27, RP_GPIO_8, 7},
                            {0, RP_UART_TX, 8}, {1, RP_UART_RX, 9}};
int gpioNet[50];                     // which net each GPIO is in
uint8_t gpioReading[50];             // no pins to read
uint8_t gpioState[50];               // all "output low"
uint32_t gpioReadingColors[50];
int showADCreadings[8];
float adcReadings[8];                // no ADC: 0 V
float getDacVoltage(int dac) { return dac == 0 ? globalState.power.dac0 : globalState.power.dac1; }  // the case's voltages
bool dacUserClaimed(int) { return false; }                      // no live dac_set() latch; the case's voltage decides
void setDac0voltage(float, int, int, bool) {}                   // no DAC chip
void setDac1voltage(float, int, int, bool) {}

// --- fake GPIO (time-multiplexed virtual pins): none configured --------------
FakeGpioOutput fakeGpioOutputs[MAX_FAKE_GP_OUT];
FakeGpioInput fakeGpioInputs[MAX_FAKE_GP_IN];
int fakeGpioInputAdcChannel = -1;
TimeDomainMultiplexer tdmInputs;     // no multiplexed ADC channels

// --- the rebuild itself ---------------------------------------------------------
// infraNudge() / infraServiceTick() ask Commands.cpp for a rebuild; the harness
// runs the rebuild explicitly for each case instead.
volatile bool refreshInProgress = false;
volatile bool refreshLocalInProgress = false;
void refreshLocalConnections(int, int, int) {}

// --- probe ------------------------------------------------------------------
ProbingStub probing;                 // no probe buttons
volatile unsigned long blockProbeButton = 0;
volatile unsigned long blockProbeButtonTimer = 0;
int probePowerDAC = 0;               // infraEvaluate's compatibility view
void probeGpioPowerHwClaim(int) {}   // would drive the feed GPIO high
void probeGpioPowerHwRelease(int) {}

// --- OLED ---------------------------------------------------------------------
bool oledUsingHardwiredPins = false; // no OLED: its I2C lock bridges are off anyway (config default)
bool oledOwnsUartPins = false;

// --- display, colours, highlighting -----------------------------------------
int numberOfShownNets = 0;
rgbColor netColors[MAX_NETS];        // nets are not coloured on the host
uint8_t gpioAnimationBaseHues[10];
CurrentSenseOverlayState currentSenseOverlayState;   // -1/-1: no overlay wire
int highlightedRow = -1;
int highlightedNet = -1;
int brightenedNode = -1;
void changeTerminalColor(int, bool, Stream*) {}      // no ANSI colour in the reports
static char s_noName[] = "";
char* colorToName(uint32_t, int) { return s_noName; }
char* colorToName(int, int) { return s_noName; }
char* colorToName(rgbColor, int) { return s_noName; }
int colorToVT100(uint32_t, int) { return 15; }
int colorToAnsi(uint32_t) { return 15; }
hsvColor RgbToHsv(rgbColor) { return {0, 0, 0}; }
rgbColor HsvToRgb(hsvColor) { return {0, 0, 0}; }
uint32_t HsvToRaw(hsvColor) { return 0; }
uint32_t packRgb(rgbColor c) { return ((uint32_t)c.r << 16) | ((uint32_t)c.g << 8) | c.b; }
uint32_t measurementToColor(float, float, float) { return 0; }
