// ================== INTEGRACIÓN HX711 + YSI400 + XYTEKFLOW ==================

#include "HX711.h"
#include <LiquidCrystal_I2C.h>
#include <math.h>
#include "XYTEKFlow.h"

// ================== CONFIGURACIÓN HX711 ==================
#define DT 2
#define SCK 4
HX711 balanza;

// ================== CONFIGURACIÓN LCD ==================
LiquidCrystal_I2C lcd(0x26, 16, 2);
#define UPDATE_LCD 1000

// ================== CONFIGURACIÓN TERMISTOR YSI400 ==================
#define A_COEFF 0.0015000578
#define B_COEFF 0.0002316643
#define C_COEFF 0.0000001426
#define ThermPin 15
const float R_FIXED = 2206.0;
const float V_IN = 3.278;

// ================== CONFIGURACIÓN XYTEKFLOW ==================
#define ENABLE_XYTEKFLOW true
#define FLOW_TX_PIN 17
#define FLOW_RX_PIN 16
#define FLOW_DE_PIN 5
#define FLOW_RE_PIN 18
#define FLOW_ADDR_1 3
#define FLOW_SENSOR_COUNT 1
#define FLOW_SENSOR_MEASURE_PERIOD_MS 500

unsigned long flow_sensor_measure_last_time = 0;
float flow_last_valid_values[3] = {0.0, 0.0, 0.0};
uint8_t flow_valid_index = 0;
bool flow_buffer_filled = false;
float flow_tare_offset = 0.0;

XYTEKFlow flow_sensors[] = {
  XYTEKFlow(&Serial2, FLOW_ADDR_1, [](){
    digitalWrite(FLOW_RE_PIN, HIGH);
    digitalWrite(FLOW_DE_PIN, HIGH);
  }, [](){
    digitalWrite(FLOW_RE_PIN, LOW);
    digitalWrite(FLOW_DE_PIN, LOW);
  })
};

void flow_init_pins() {
  pinMode(FLOW_RE_PIN, OUTPUT);
  pinMode(FLOW_DE_PIN, OUTPUT);
  digitalWrite(FLOW_RE_PIN, LOW);
  digitalWrite(FLOW_DE_PIN, LOW);
}

// Promedia las últimas lecturas válidas
float getAverageFlow() {
  uint8_t count = flow_buffer_filled ? 3 : flow_valid_index;
  if (count == 0) return 0.0;
  float sum = 0.0;
  for (uint8_t i = 0; i < count; i++) sum += flow_last_valid_values[i];
  return sum / count;
}

// Guarda una nueva lectura válida
void saveValidFlow(float newFlow) {
  flow_last_valid_values[flow_valid_index] = newFlow;
  flow_valid_index = (flow_valid_index + 1) % 3;
  if (flow_valid_index == 0) flow_buffer_filled = true;
}

// ================== TIMER ==================
hw_timer_t *timer = NULL;
volatile bool refreshLCD = false;

void IRAM_ATTR onTimer() {
  refreshLCD = true;
}

void setupTimer() {
  timer = timerBegin(1);
  timerAttachInterrupt(timer, &onTimer);
  timerAlarm(timer, 1000000, true, 0); // Cada 1 segundo
}

// ================== VARIABLES ==================
double presion = 0;
double m = 1;//0.90043889 * -0.00010343572090560042;
double n = 0;
unsigned long T = 0;
double lastTemps[3];
int tempIndex = 0;
bool bufferFilled = false;

double ThermistorTemperature(double R) {
  double logR = log(R);
  return (1.0 / (A_COEFF + B_COEFF * logR + C_COEFF * pow(logR, 3))) - 273.15;
}

double averageLastTemps(double newTemp) {
  lastTemps[tempIndex] = newTemp;
  tempIndex = (tempIndex + 1) % 3;
  if (tempIndex == 0) bufferFilled = true;
  double sum = 0;
  int count = bufferFilled ? 3 : tempIndex;
  for (int i = 0; i < count; i++) sum += lastTemps[i];
  return sum / count;
}

// ================== LCD ==================
void printLCDHeader() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("IBP :");
  lcd.setCursor(12, 0);
  lcd.print("mmHg");

  lcd.setCursor(4, 1);
  lcd.print("mL/min");
  lcd.setCursor(14, 1);
  lcd.print((char)223);
  lcd.setCursor(15, 1);
  lcd.print("C");
}

// ================== SETUP ==================
void setup() {
  Serial.begin(115200);
  lcd.init();
  lcd.backlight();
  printLCDHeader();

  // HX711
  balanza.begin(DT, SCK);
  delay(1000);
  if (!balanza.is_ready()) {
    Serial.println("Error: No se detecta el HX711.");
    while (1);
  }
  balanza.set_scale();
  //balanza.tare();

  // TIMER
  setupTimer();

  // XYTEKFLOW
  Serial2.begin(115200, SERIAL_8N1, FLOW_RX_PIN, FLOW_TX_PIN);
  flow_init_pins();
  flow_sensors[0].zero_calibration();
  flow_sensors[0].reset_volume();
  flow_sensors[0].init();
  Serial.println("[SETUP] Sensores XYTEKFlow listos");
}

// ================== LOOP ==================
void loop() {
  T = millis();

  // --- Termistor ---
  int adcValue = analogRead(ThermPin) + 205;
  double voltage = adcValue * V_IN / 4095.0;
  double R_therm = (V_IN * R_FIXED / voltage) - R_FIXED;
  double tempC = ThermistorTemperature(R_therm);
  double avgTemp = averageLastTemps(tempC);

  // --- HX711 Presión ---
  if (balanza.is_ready()) {
    long lectura = balanza.get_units(5);
    presion = (m * lectura) + n;
  } else {
    presion = 0;
  }

  // --- XYTEKFlow ---
  static unsigned long lastFlowRead = 0;
  static unsigned long lastLCD_UPDATE = 0;
  float avgFlow = 0.0;
  if (millis() - lastFlowRead >= FLOW_SENSOR_MEASURE_PERIOD_MS) {
    lastFlowRead = millis();
    bool ok_rate = flow_sensors[0].read_flowrate();
    float measured_flow = 0.0;

    if (ok_rate) {
      measured_flow = flow_sensors[0].flow_rate;
      saveValidFlow(measured_flow);
      avgFlow = getAverageFlow();
    }
  }
  
  if (millis() - lastLCD_UPDATE >= UPDATE_LCD) {
    lastLCD_UPDATE = millis();
    printLCDHeader();
  }
  // --- LCD actualización ---
  lcd.setCursor(6, 0);
  lcd.print("      ");
  lcd.setCursor(6, 0);
  lcd.print(presion, 1);

  lcd.setCursor(0, 1);
  lcd.print("    ");
  lcd.setCursor(0, 1);
  lcd.print(avgFlow, 0);

  lcd.setCursor(11, 1);
  lcd.print("   ");
  lcd.setCursor(11, 1);
  lcd.print(avgTemp, 0);



  // --- Serial Output ---
  Serial.print(T);
  Serial.print(" ");
  Serial.print(presion, 2);
  Serial.print(" ");
  Serial.print(avgTemp, 1);
  Serial.print(" ");
  Serial.print(avgFlow, 1);
  Serial.println();

  //delay(200);
}
