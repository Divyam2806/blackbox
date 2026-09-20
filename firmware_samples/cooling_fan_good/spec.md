# Cooling Fan Controller Specification (Fixed Version)

## Inputs & Outputs
- **Temperature Sensor**: Analog sensor on pin `A0`, reading range 0.0 to 100.0 °C mapped across 10-bit ADC counts (0 to 1023).
- **Cooling Fan**: Digital output pin `D9` (HIGH = Fan ON, LOW = Fan OFF).
- **Error Indicator**: Digital output pin `D13` (HIGH = Error active, LOW = Normal operation).
- **Telemetry**: Serial UART log output at 9600 baud (`T=<temp> FAN=<state>` or `ERR: Sensor Fault`).

## Operational Rules
- **Rule R1**: The fan MUST turn ON when temperature is at or above 30.0 °C.
- **Rule R2**: The fan MUST turn OFF when temperature drops at or below 28.0 °C (2 °C hysteresis band).
- **Rule R3**: An error MUST be signaled (ERR_LED pin D13 HIGH, Serial log `ERR: Sensor Fault`) if sensor reading is raw <= 4 or raw >= 1019. Fan MUST enter fail-safe HIGH state.

## System Invariants
- **Invariant I1**: The fan/motor MUST be OFF at boot initialization.
- **Invariant I2**: Implausible sensor values MUST NOT be accepted as valid operating temperatures.
- **Invariant I3**: Output MUST NOT chatter near threshold.
