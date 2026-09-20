// Smart Plant Irrigation Controller Firmware
const int SOIL_PIN = A1;
const int PUMP_PIN = 7;
const int STATUS_LED = 13;
const int BUZZER_PIN = 8;

const float DRY_THRESH = 400.0;
const float WET_THRESH = 700.0;

bool pumpState = false;

int readSoilMoisture() {
  int raw = analogRead(SOIL_PIN);
  return raw; // bug: no rail fault check for raw <= 4 or raw >= 1019
}

void setup() {
  Serial.begin(9600);
  pinMode(PUMP_PIN, OUTPUT);
  pinMode(STATUS_LED, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(PUMP_PIN, LOW);
}

void loop() {
  int moisture = readSoilMoisture();
  
  if (moisture < DRY_THRESH) {
    pumpState = true;
  } else if (moisture > WET_THRESH) {
    pumpState = false;
  }
  
  digitalWrite(PUMP_PIN, pumpState ? HIGH : LOW);
  digitalWrite(STATUS_LED, pumpState ? HIGH : LOW);
  
  Serial.print("SOIL="); Serial.print(moisture);
  Serial.print(" PUMP="); Serial.println(pumpState ? "ON" : "OFF");
  delay(250);
}
