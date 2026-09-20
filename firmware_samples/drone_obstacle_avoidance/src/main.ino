#if __has_include("mavlink/common/mavlink.h")
#include "mavlink/common/mavlink.h"
#elif __has_include("mavlink.h")
#include "mavlink.h"
#else
// MAVLink Stubs for Host Simulation
#define MAVLINK_MAX_PACKET_LEN 263
#define MAV_TYPE_QUADROTOR 2
#define MAV_AUTOPILOT_GENERIC 0
typedef struct { uint8_t magic; } mavlink_message_t;
inline void mavlink_msg_heartbeat_pack(int a, int b, mavlink_message_t* msg, int c, int d, int e, int f, int g) {}
inline uint16_t mavlink_msg_to_send_buffer(uint8_t* buf, mavlink_message_t* msg) { return 10; }
inline void mavlink_msg_rc_channels_override_pack(int a, int b, mavlink_message_t* msg, int c, int d, int e, int f, int g, int h, int i, int j, int k, int l) {}
#endif

#if __has_include(<NewPing.h>)
#include <NewPing.h>
#else
// NewPing Stub for Host Simulation
class NewPing {
  int pin;
  int max_dist;
public:
  NewPing(int trigger, int echo, int maxd = 70) : pin(trigger), max_dist(maxd) {}
  int ping_cm() { return 0; }
};
#endif

#if __has_include(<SoftwareSerial.h>)
#include <SoftwareSerial.h>
#else
// SoftwareSerial Stub for Host Simulation
class SoftwareSerial {
public:
  SoftwareSerial(int rx, int tx) {}
  void begin(long baud) {}
  void write(uint8_t* buf, int len) {}
};
#endif

#define MAX_DISTANCE  70 

//======================= GPIO pins intialization =========================//
SoftwareSerial mySerial(10, 11); /// RX, TX
NewPing sonar_B(3, 3, MAX_DISTANCE);
NewPing sonar_F(4, 4, MAX_DISTANCE);

//======================= Intitialize variables =========================//
unsigned long HeartbeatTime = 0;
int OUTPUT_PITCH = 0;
int TRIG_PITCH = 0;
int FRONT_SENSOR = 0;
int BACK_SENSOR = 0;
int PITCH_BACK = 0;
int PITCH_FRONT = 0;

void setup() {
  Serial.begin(9600);
  mySerial.begin(57600);
}

void loop() {
  if ( (millis() - HeartbeatTime) > 1000 ) {
    HeartbeatTime = millis();
    PIX_HEART_BEAT();
  } 
  TRIG_PITCH = sonar_F.ping_cm() + sonar_B.ping_cm(); // Checks the overall Pitch to confirm if obstacle is detetcted at either side of the drone !
  FRONT_SENSOR = sonar_F.ping_cm(); //distance in cm // Gets's the distance from front facing sensor 
  BACK_SENSOR = sonar_B.ping_cm(); //distance in cm // Gets's the distance from back facing sensor 
  OUTPUT_DATA();
}

//======================= Sends data to Mavlink =========================//  
uint8_t N = 0;
void OUTPUT_DATA() {
  CALCULATE_PITCH();
  SEND_DATA(OUTPUT_PITCH); 
}

//======================= Calculation for PITCH =========================//
void CALCULATE_PITCH(){
// Checks if sensor value is less than 70cm and is not equal to Zero.
    if (BACK_SENSOR != 0 && BACK_SENSOR < MAX_DISTANCE) {
       PITCH_FRONT = 1500-30-((70-BACK_SENSOR)*6); // 1500 = Mid Term, 30 = intital increment when object detetcted at 69cm, 70 = MAX_DISTANCE, PITCH_F = Distance calculated by the sensor, 6 = increment value by mutiple of 6  
       OUTPUT_PITCH = PITCH_FRONT;
       Serial.print("PITCH="); Serial.println(OUTPUT_PITCH);
    }
    else if (FRONT_SENSOR != 0 && FRONT_SENSOR < MAX_DISTANCE){
       PITCH_BACK = 1500+30+((70-FRONT_SENSOR)*6);
       OUTPUT_PITCH = PITCH_BACK;
       Serial.print("PITCH="); Serial.println(OUTPUT_PITCH);
    }
    else {
      OUTPUT_PITCH = 1500;
      Serial.print("PITCH="); Serial.println(OUTPUT_PITCH);
    }
}

//============================MAVLINK COMMAND==========================//
mavlink_message_t msg;
uint8_t buf[MAVLINK_MAX_PACKET_LEN];
uint16_t len;
 
void PIX_HEART_BEAT() {
  mavlink_msg_heartbeat_pack(255, 0, &msg, MAV_TYPE_QUADROTOR, MAV_AUTOPILOT_GENERIC, 0, 1, 0);    // System ID = 255 = GCS
  len = mavlink_msg_to_send_buffer(buf, &msg);
  mySerial.write(buf, len);
}

void SEND_DATA(int P) {
    if (TRIG_PITCH != 0){
    mavlink_msg_rc_channels_override_pack(255, 0 , &msg, 1, 0, 0, P, 0, 0, 0, 0, 0, 0);    // CHANNEL = 1(ROLL), 2(PITCH), 3(Throttle), 4(Yaw) , 5, 6, 7, 8
    len = mavlink_msg_to_send_buffer(buf, &msg);
    }
    else{
    mavlink_msg_rc_channels_override_pack(255, 0 , &msg, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0);    // CHANNEL = 1(ROLL), 2(PITCH), 3(Throttle), 4(Yaw) , 5, 6, 7, 8
    len = mavlink_msg_to_send_buffer(buf, &msg);
    }
  mySerial.write(buf, len);
}
