# Cooling Fan Controller Specification

## Inputs
- Temperature sensor on pin A0: 0..100 °C mapped to 10-bit ADC (0..1023).

## Outputs
- Fan on pin D9 (GPIO output).
- Error LED on pin D13 (GPIO output).

## Requirements
- R1: Fan MUST turn ON when temperature is above 30.0 °C.
- R2: Fan MUST turn OFF when temperature is below 30.0 °C.
- R3: An error MUST be signalled (Error LED ON) if sensor stops responding or produces invalid readings (open/short circuit).

## Universal Invariants
- I1: Fan/motor MUST be OFF at boot/reset.
- I2: Implausible sensor values (e.g. raw 0 or 1023) must not be accepted as valid temperature.
- I3: Output must not chatter (rapidly toggle) near the threshold.
