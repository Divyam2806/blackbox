# Smart Plant Irrigation Controller Specification

## Inputs
- Soil moisture sensor on pin A1: 0..1023 analog count (0 = completely dry/short, 1023 = fully saturated/open).

## Outputs
- Water Pump Relay on pin D7 (GPIO output).
- Status LED on pin D13 (GPIO output).
- Alarm Buzzer on pin D8 (GPIO output).

## Requirements
- R1: Pump MUST turn ON when soil moisture is below 400.0 ADC counts (dry soil).
- R2: Pump MUST turn OFF when soil moisture is above 700.0 ADC counts (wet soil).
- R3: Alarm buzzer MUST sound (D8 HIGH) if sensor is disconnected or produces rail extreme raw readings (<= 4 or >= 1019).

## Universal Invariants
- I1: Pump MUST be OFF at boot/reset.
- I2: Sensor extreme rail values must not be accepted as valid soil moisture.
- I3: Output pump driver must not chatter near boundary.
