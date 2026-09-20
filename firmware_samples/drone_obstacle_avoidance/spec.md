# Drone Obstacle Avoidance MAVLink Controller Specification

## Inputs
- Front Ultrasonic Sensor on pin D4 (0..70 cm).
- Back Ultrasonic Sensor on pin D3 (0..70 cm).

## Outputs
- SoftwareSerial MAVLink telemetry on pins D10 (RX), D11 (TX).
- MAVLink RC Channel 2 (PITCH override output).

## Requirements
- R1: When back sensor detects obstacle (< 70 cm and != 0), pitch MUST override to backward pitch value (1500 - 30 - ((70 - BACK_SENSOR) * 6)).
- R2: When front sensor detects obstacle (< 70 cm and != 0), pitch MUST override to forward pitch value (1500 + 30 + ((70 - FRONT_SENSOR) * 6)).
- R3: When no obstacle is detected (or sensor == 0), pitch MUST default to neutral 1500.

## Universal Invariants
- I1: System MUST send periodic MAVLink Heartbeat telemetry.
- I2: Ultrasonic distance readings > 70 cm MUST NOT trigger pitch override.
