// SPDX-License-Identifier: MIT
// Host stand-in for the Arduino core: just enough for the V5 routing sources.
// Grown from test/test_routing_og/stubs/Arduino.h. Unlike that one, print()
// returns the number of characters, because the firmware's table printers
// pad columns from those counts.
#pragma once
#include <ctype.h>
#include <math.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint8_t byte;
typedef bool boolean;
#define HIGH 1
#define LOW 0
#define INPUT 0
#define OUTPUT 1

// true: firmware prints are dropped (their lengths are still returned)
extern bool g_quiet;
// where firmware prints go: stdout, or a memory stream while the harness
// captures a report
extern FILE* g_out;

class Stream {
public:
    template <typename T> int print(T v) { return printv(v); }
    template <typename T> int println(T v) { int n = printv(v); return n + emit("\r\n"); }
    int println() { return emit("\r\n"); }
    int print(double v, int digits) {
        char b[64];
        snprintf(b, sizeof b, "%.*f", digits, v);
        return emit(b);
    }
    int println(double v, int digits) { int n = print(v, digits); return n + emit("\r\n"); }
    int printf(const char* fmt, ...) __attribute__((format(printf, 2, 3))) {
        char b[2048];
        va_list ap;
        va_start(ap, fmt);
        vsnprintf(b, sizeof b, fmt, ap);
        va_end(ap);
        return emit(b);
    }
    void flush() {}
    int available() { return 0; }
    int read() { return -1; }
    int availableForWrite() { return 1 << 20; }
    size_t write(char c) { char b[2] = {c, 0}; emit(b); return 1; }

private:
    int emit(const char* s) {
        if (!s) s = "(null)";
        size_t n = strlen(s);
        if (!g_quiet) fwrite(s, 1, n, g_out);
        return (int)n;
    }
    template <typename N> int num(const char* fmt, N v) {
        char b[48];
        snprintf(b, sizeof b, fmt, v);
        return emit(b);
    }
    int printv(const char* s) { return emit(s); }
    int printv(char* s) { return emit(s); }
    int printv(char c) { char b[2] = {c, 0}; return emit(b); }
    int printv(int v) { return num("%d", v); }
    int printv(unsigned int v) { return num("%u", v); }
    int printv(long v) { return num("%ld", v); }
    int printv(unsigned long v) { return num("%lu", v); }
    int printv(long long v) { return num("%lld", v); }
    int printv(unsigned long long v) { return num("%llu", v); }
    int printv(short v) { return num("%d", (int)v); }
    int printv(unsigned short v) { return num("%u", (unsigned)v); }
    int printv(signed char v) { return num("%d", (int)v); }
    int printv(unsigned char v) { return num("%u", (unsigned)v); }
    int printv(bool v) { return num("%d", (int)v); }
    int printv(double v) { return num("%.2f", v); }           // Arduino prints two decimals
    int printv(float v) { return num("%.2f", (double)v); }
};
extern Stream Serial;

static inline unsigned long micros() { return 0; }
static inline unsigned long millis() { return 0; }
static inline void delay(unsigned long) {}
static inline void delayMicroseconds(unsigned int) {}
static inline void digitalWrite(int, int) {}
static inline int digitalRead(int) { return 1; }
static inline void pinMode(int, int) {}
static inline long random(long n) { return rand() % (n ? n : 1); }
static inline int get_core_num() { return 0; }
static inline void gpio_set_dir(unsigned, bool) {}             // pico-sdk
static inline char* itoa(int v, char* s, int base) {
    snprintf(s, 34, base == 16 ? "%x" : "%d", v);   // callers pass buffers sized for an int
    return s;
}
