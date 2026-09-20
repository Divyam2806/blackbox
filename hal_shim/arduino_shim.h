#ifndef ARDUINO_SHIM_H
#define ARDUINO_SHIM_H

#include <iostream>
#include <string>
#include <map>
#include <chrono>

// Pins
#define A0 14
#define OUTPUT 1
#define INPUT 0
#define HIGH 1
#define LOW 0

extern std::map<int, int> g_pin_states;
extern std::map<int, int> g_adc_states;
extern unsigned long g_virtual_millis;

inline void pinMode(int pin, int mode) {}

inline int digitalRead(int pin) {
    return g_pin_states[pin];
}

inline void digitalWrite(int pin, int val) {
    g_pin_states[pin] = val;
    std::cout << "[" << g_virtual_millis << "ms] PIN " << pin << "=" << val << std::endl;
}

inline int analogRead(int pin) {
    return g_adc_states[pin];
}

inline unsigned long millis() {
    return g_virtual_millis;
}

inline void delay(unsigned long ms) {
    g_virtual_millis += ms;
}

class FakeSerial {
public:
    void begin(int baud) {}
    void print(const char* s) { std::cout << s; }
    void print(float f) { std::cout << f; }
    void print(int i) { std::cout << i; }
    void println(const char* s) { std::cout << s << std::endl; }
    void println(float f) { std::cout << f << std::endl; }
    void println(int i) { std::cout << i << std::endl; }
};

extern FakeSerial Serial;

#endif
