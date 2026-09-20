// cooling_fan_buggy.ino (Arduino-style; ADC temperature sensor 0..100 C over 0..1023)
const int TEMP_PIN = A0;     // analog temperature sensor
const int FAN_PIN = 9;       // MOSFET driving the fan
const int ERR_LED = 13;      // meant to light on sensor error
const float THRESH_C = 30.0; // fan ON at/above this
bool fanOn = false;

float readTempC() {
  int raw = analogRead(TEMP_PIN);   // 0..1023
  return raw * (100.0f / 1023.0f); // no plausibility check
}

void setup() {
  Serial.begin(9600);
  pinMode(FAN_PIN, OUTPUT);
  pinMode(ERR_LED, OUTPUT);
}

void loop() {
  float t = readTempC();
  if (t >= THRESH_C) fanOn = true; // no hysteresis
  else fanOn = false;
  digitalWrite(FAN_PIN, fanOn);
  Serial.print("T="); Serial.print(t);
  Serial.print(" FAN="); Serial.println(fanOn ? "ON" : "OFF");
  delay(200);
}
