# Smart Door Lock FSM Specification

## Inputs & Outputs
- **Keypad Sensor**: Analog resistor ladder on pin `A0` (raw > 500 = Valid PIN, raw > 100 = Invalid PIN).
- **Door Solenoid**: Digital output pin `D9` (HIGH = Unlocked, LOW = Locked).
- **Status LED**: Digital output pin `D8` (HIGH = Locked status).
- **Alarm LED**: Digital output pin `D13` (HIGH = Alarm triggered).
- **Buzzer**: Digital output pin `D12` (HIGH = Alarm sound).

## Operational Rules
- **Rule R1**: Presenting a valid PIN MUST transition state from LOCKED to UNLOCKED (Solenoid D9 HIGH).
- **Rule R2**: 3 consecutive invalid PIN attempts MUST transition state to ALARM (Alarm LED D13 HIGH, Buzzer D12 HIGH, Serial `ERR: ALARM`).
- **Rule R3**: Unlocked door MUST automatically relock (transition to LOCKED, Solenoid D9 LOW) after 5 seconds.

## System Invariants
- **Invariant I1**: Solenoid D9 and Alarm D13 MUST be LOW at boot.
- **Invariant I2**: Brute-force invalid attempts must not be allowed indefinitely without alarm trip.
