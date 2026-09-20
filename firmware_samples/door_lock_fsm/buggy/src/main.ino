// Smart Door Lock FSM - Buggy Firmware
const int KEYPAD_PIN = A0;   // PIN Code Analog Resistor Ladder
const int SOLENOID_PIN = 9;  // Door Solenoid Lock
const int LOCK_LED = 8;      // Locked Status LED
const int ALARM_LED = 13;    // Alarm LED (Meant for 3 failed attempts)
const int BUZZER_PIN = 12;   // Alarm Buzzer

enum LockState { LOCKED, UNLOCKING, UNLOCKED, ALARM };
LockState currentState = LOCKED;
int failedAttempts = 0;

void setup() {
  Serial.begin(9600);
  pinMode(SOLENOID_PIN, OUTPUT);
  pinMode(LOCK_LED, OUTPUT);
  pinMode(ALARM_LED, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(LOCK_LED, HIGH);
}

void loop() {
  int rawKey = analogRead(KEYPAD_PIN);

  if (currentState == LOCKED) {
    if (rawKey > 500) { // Valid PIN key pressed
      currentState = UNLOCKED;
      digitalWrite(SOLENOID_PIN, HIGH);
      digitalWrite(LOCK_LED, LOW);
      Serial.println("STATE=UNLOCKED PIN=CORRECT");
    } else if (rawKey > 100) {
      failedAttempts++;
      Serial.print("STATE=LOCKED ERR_PIN ATTEMPTS=");
      Serial.println(failedAttempts);
      // BUG: Never enters ALARM state or drives ALARM_LED/BUZZER on failedAttempts >= 3!
    }
  } else if (currentState == UNLOCKED) {
    // BUG: Missing auto-relock timeout timer! Door stays unlocked forever once opened.
  }

  delay(200);
}
