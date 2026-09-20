#include <Arduino.h>

#define MOISTURE_PIN A1
#define PUMP_PIN 8
#define BUZZER_PIN 12

#define MOISTURE_THRESH 25.0

void setup() {
  Serial.begin(115200);
  pinMode(PUMP_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(PUMP_PIN, LOW);
}

void loop() {
  int raw = analogRead(MOISTURE_PIN);
  float moisture = (raw / 1023.0) * 100.0;

  if (moisture < MOISTURE_THRESH) {
    digitalWrite(PUMP_PIN, HIGH);
    Serial.print("MOISTURE=");
    Serial.print(moisture, 1);
    Serial.println("% PUMP=ON");
  } else {
    digitalWrite(PUMP_PIN, LOW);
    Serial.print("MOISTURE=");
    Serial.print(moisture, 1);
    Serial.println("% PUMP=OFF");
  }
  delay(1000);
}
