#include "arduino_shim.h"

std::map<int, int> g_pin_states;
std::map<int, int> g_adc_states;
unsigned long g_virtual_millis = 0;
FakeSerial Serial;

// Sketch setup & loop prototypes
extern void setup();
extern void loop();

int main() {
    g_adc_states[A0] = 256;
    setup();
    
    std::string cmd;
    while (std::cin >> cmd) {
        if (cmd == "SET_ADC") {
            int pin, val;
            std::cin >> pin >> val;
            g_adc_states[pin] = val;
        } else if (cmd == "RUN") {
            int ms;
            std::cin >> ms;
            unsigned long target = g_virtual_millis + ms;
            while (g_virtual_millis < target) {
                loop();
            }
        } else if (cmd == "RESET") {
            g_virtual_millis = 0;
            g_pin_states.clear();
            setup();
        }
    }
    return 0;
}
