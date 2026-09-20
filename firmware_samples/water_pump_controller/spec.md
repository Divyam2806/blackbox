# Smart Water Pump Controller Specification

## Hardware Pinout
- Moisture Sensor: Input on A1 (Analog 0..1023 -> 0.0..100.0%)
- Water Pump Relay: Output on D8 (Digital)
- Warning Buzzer: Output on D12 (Digital)

## Requirements
- R1: When soil moisture drops below 25.0%, activate the water pump (`pump` ON).
- R2: When soil moisture is 25.0% or above, deactivate the water pump (`pump` OFF).
- R3: If the moisture sensor stops responding or returns invalid readings, activate warning buzzer (`buzzer` ON).

## Operational Invariants
- I1: Water pump must be OFF at system boot.
- I2: Implausible sensor readings must be rejected.
- I3: Pump output must not chatter rapidly near the threshold.
