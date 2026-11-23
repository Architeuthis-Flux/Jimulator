// SPDX-License-Identifier: MIT
// Host stand-in for src/eyecandy/Highlighting.h: nothing is highlighted.
#pragma once
extern int highlightedRow;
extern int highlightedNet;
extern int brightenedNode;
inline int encoderNetHighlight(int = 1, int = 1, int = 8) { return -1; }
