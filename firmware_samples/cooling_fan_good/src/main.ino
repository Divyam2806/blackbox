// cooling_fan_good.ino  (Fixed Arduino-style cooling fan firmware)
const int TEMP_PIN = A0;        // analog temperature sensor
const int FAN_PIN  = 9;         // MOSFET driving the fan
const int ERR_LED  = 13;        // lights on sensor error
const float THRESH_ON_C  = 30.0; // fan ON at/above 30 C
const float THRESH_OFF_C = 28.0; // hysteresis: fan OFF at/below 28 C

bool fanOn = false;
bool errorState = false;

float readTempC(bool &isError) {
  int raw = analogRead(TEMP_PIN); // 0..1023
  // Plausibility check: open circuit (raw >= 1019) or short circuit (raw <= 4)
  if (raw <= 4 || raw >= 1019) {
    isError = true;
    return -999.0f;
  }
  isError = false;
  return raw * (100.0f / 1023.0f);
}

void setup() {
  Serial.begin(9600);
  pinMode(FAN_PIN, OUTPUT);
  pinMode(ERR_LED, OUTPUT);
  digitalWrite(FAN_PIN, LOW);
  digitalWrite(ERR_LED, LOW);
}

void loop() {
  bool isError = false;
  float t = readTempC(isError);

  if (isError) {
    errorState = true;
    digitalWrite(ERR_LED, HIGH);
    digitalWrite(FAN_PIN, HIGH); // Fail-safe ON when sensor fails
    Serial.println("ERR: Sensor Fault");
  } else {
    errorState = false;
    digitalWrite(ERR_LED, LOW);

    // Hysteresis control loop
    if (t >= THRESH_ON_C) {
      fanOn = true;
    } else if (t <= THRESH_OFF_C) {
      fanOn = false;
    }

    digitalWrite(FAN_PIN, fanOn ? HIGH : LOW);
    Serial.print("T="); Serial.print(t);
    Serial.print(" FAN="); Serial.println(fanOn ? "ON" : "OFF");
  }

  delay(200);
}
