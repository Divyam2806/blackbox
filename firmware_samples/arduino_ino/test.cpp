// Object Detection using HC-SR04 Ultrasonic Sensor

const int trigPin = 11;
const int echoPin = 12;
const int ledPin = 13;

// Define distance threshold in centimeters (detects objects closer than 30cm)
const int detectionThreshold = 30; 

void setup() {
  Serial.begin(9600);
  
  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);
  pinMode(ledPin, OUTPUT);
}

void loop() {
  long duration;
  int distance;

  // Clear the trigger pin
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);

  // Set the trigger pin HIGH for 10 microseconds to send out a pulse
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  // Read the echo pin; returns the sound wave travel time in microseconds
  duration = pulseIn(echoPin, HIGH);

  // Calculate the distance in centimeters
  // Speed of sound wave divided by 2 (go and back)
  distance = duration * 0.034 / 2;

  // Print distance to Serial Monitor
  Serial.print("Distance: ");
  Serial.print(distance);
  Serial.println(" cm");

  // Check if an object is within the threshold
  if (distance > 0 && distance <= detectionThreshold) {
    digitalWrite(ledPin, HIGH); // Object detected, turn on LED
    Serial.println("⚠️ Object Detected!");
  } else {
    digitalWrite(ledPin, LOW);  // No object, turn off LED
  }

  delay(200); // Small delay between scans
}
