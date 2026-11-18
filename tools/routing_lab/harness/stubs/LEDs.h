// SPDX-License-Identifier: MIT
// Host stand-in for src/LEDs.h: colour types and helpers the net printers use.
#pragma once
#include <stdint.h>
#include "JumperlessDefines.h"
typedef struct rgbColor { unsigned char r; unsigned char g; unsigned char b; } rgbColor;
typedef struct hsvColor { unsigned char h; unsigned char s; unsigned char v; } hsvColor;
extern int numberOfShownNets;
extern rgbColor netColors[MAX_NETS];
char* colorToName(uint32_t color, int length = -1);
char* colorToName(int hue, int length = -1);
char* colorToName(rgbColor color, int length = -1);
int colorToVT100(uint32_t color, int colorDepth = 256);
int colorToAnsi(uint32_t color);
hsvColor RgbToHsv(rgbColor rgb);
rgbColor HsvToRgb(hsvColor hsv);
uint32_t HsvToRaw(hsvColor hsv);
uint32_t packRgb(rgbColor color);
