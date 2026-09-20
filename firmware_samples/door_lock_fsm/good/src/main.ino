// Smart Door Lock FSM - Fixed Firmware
const int KEYPAD_PIN = A0;   // PIN Code Analog Resistor Ladder
const int SOLENOID_PIN = 9;  // Door Solenoid Lock
const int LOCK_LED = 8;      // Locked Status LED
const int ALARM_LED = 13;    // Alarm LED
const int BUZZER_PIN = 12;   // Alarm Buzzer

enum LockState { LOCKED, UNLOCKING, UNLOCKED, ALARM };
LockState currentState = LOCKED;
int failedAttempts = 0;
unsigned long unlockedTimestamp = 0;
const unsigned long AUTO_RELOCK_MS = 5000;

void setup() {
  Serial.begin(9600);
  pinMode(SOLENOID_PIN, OUTPUT);
  pinMode(LOCK_LED, OUTPUT);
  pinMode(ALARM_LED, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(SOLENOID_PIN, LOW);
  digitalWrite(LOCK_LED, HIGH);
  digitalWrite(ALARM_LED, LOW);
  digitalWrite(BUZZER_PIN, LOW);
}

void loop() {
  int rawKey = analogRead(KEYPAD_PIN);

  if (currentState == LOCKED) {
    if (rawKey > 500) { // Valid PIN key pressed
      currentState = UNLOCKED;
      unlockedTimestamp = millis();
      failedAttempts = 0;
      digitalWrite(SOLENOID_PIN, HIGH);
      digitalWrite(LOCK_LED, LOW);
      Serial.println("STATE=UNLOCKED PIN=CORRECT");
    } else if (rawKey > 100) {
      failedAttempts++;
      Serial.print("STATE=LOCKED ERR_PIN ATTEMPTS=");
      Serial.println(failedAttempts);

      if (failedAttempts >= 3) {
        currentState = ALARM;
        digitalWrite(ALARM_LED, HIGH);
        digitalWrite(BUZZER_PIN, HIGH);
        Serial.println("ERR: ALARM Brute-force Attempt Blocked");
      }
    }
  } else if (currentState == UNLOCKED) {
    // Fixed: Auto-relock after 5 seconds
    if (millis() - unlockedTimestamp >= AUTO_RELOCK_MS) {
      currentState = LOCKED;
      digitalWrite(SOLENOID_PIN, LOW);
      digitalWrite(LOCK_LED, HIGH);
      Serial.println("STATE=LOCKED TIMEOUT");
    }
  } else if (currentState == ALARM) {
    digitalWrite(ALARM_LED, HIGH);
    digitalWrite(BUZZER_PIN, HIGH);
  }

  delay(200);
}
