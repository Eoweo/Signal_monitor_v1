// XYTEKFlow Test - Standalone Communication
// Sky-Walkers adaptation by ChatGPT (2025)
// For Arduino Mega (Serial3 -> RS485 to XYTEK sensor)

#include "Arduino.h"
#include "XYTEKFlow.h"

// ---------------------------
// Hardware definitions
// ---------------------------

#define FLOW_RE_NEG_PIN 34   // RE- pin for RS485
#define FLOW_DE_PIN     35   // DE pin for RS485

#define FLOW_ADDR       4    // Modbus address of the XYTEK sensor (adjust as needed)
#define FLOW_BAUD       115200

// ---------------------------
// XYTEK Sensor Objects
// ---------------------------
void flow_pre_transmission();
void flow_post_transmission();

XYTEKFlow flow_sensor(&Serial3, FLOW_ADDR, flow_pre_transmission, flow_post_transmission);

// ---------------------------
// RS485 Direction Control
// ---------------------------
void flow_init_pins() {
  pinMode(FLOW_RE_NEG_PIN, OUTPUT);
  pinMode(FLOW_DE_PIN, OUTPUT);
  flow_post_transmission(); // Ensure we start in receive mode
}

void flow_pre_transmission() {
  digitalWrite(FLOW_RE_NEG_PIN, HIGH);
  digitalWrite(FLOW_DE_PIN, HIGH);
}

void flow_post_transmission() {
  digitalWrite(FLOW_RE_NEG_PIN, LOW);
  digitalWrite(FLOW_DE_PIN, LOW);

  // Patch for preceding zeros response
  long zero_patch_timeout_ms = 100;
  long zero_patch_t0 = millis();
  while (millis() - zero_patch_t0 < zero_patch_timeout_ms) {
    if (Serial3.available()) {
      byte b = Serial3.peek(); // Keep byte in buffer
      if (b != 0)
        break;
      else
        Serial3.read(); // Flush zeros
    }
  }
}

// ---------------------------
// Setup
// ---------------------------
void setup() {
  Serial.begin(115200);
  Serial.println("XYTEK Flow Sensor Standalone Test");
  
  flow_init_pins();

  delay(100);
  flow_sensor.init();

  Serial.println("Sensor initialized.");
}

// ---------------------------
// Loop
// ---------------------------
unsigned long last_measure_time = 0;
#define MEASURE_INTERVAL_MS 500

void loop() {
  unsigned long now = millis();
  if (now - last_measure_time >= MEASURE_INTERVAL_MS) {
    last_measure_time = now;

    bool ok = flow_sensor.read_flowrate();
    if (ok) {
      Serial.print("Flow rate: ");
      Serial.print(flow_sensor.flow_rate);
      Serial.println(" L/min");
    } else {
      Serial.println("Read failed!");
    }

    // Optional: also read volume
    // flow_sensor.read_volume_net();
    // Serial.print("Volume: ");
    // Serial.println(flow_sensor.flow_volume_net);
  }
}
