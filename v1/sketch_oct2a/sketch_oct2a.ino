#include <Adafruit_MAX31865.h>
#include "HX711.h"
#include <LiquidCrystal_I2C.h>

// ------------------- CONFIGURACIÓN MAX31865 (PT100) -------------------
#define MAX_CS 4  // Chip Select en D4
Adafruit_MAX31865 thermo = Adafruit_MAX31865(10, 11, 12, 13);
#define RREF 430.0
#define RNOMINAL 100.0

// ------------------- CONFIGURACIÓN HX711 -------------------
#define DT 3   // Pin DT del HX711
#define SCK 2  // Pin SCK del HX711
HX711 balanza;

// ------------------- LCD -------------------
LiquidCrystal_I2C lcd(0x26, 16, 2);

// ------------------- VARIABLES -------------------
float temp = 0;
float presion = 0;
double m = -0.00010343572090560042;
double n = 0;  //-9.817084271150536;
unsigned long T = 0;

void setup() {
  Serial.begin(115200);

  // Inicia el sensor de temperatura
  thermo.begin(MAX31865_2WIRE);

  // Inicia LCD
  lcd.init();
  lcd.clear();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("Presion:");
  lcd.setCursor(13, 0);
  lcd.print("mmHg");
  lcd.setCursor(0, 1);
  lcd.print("Temp:");
  lcd.setCursor(13, 1);
  lcd.print("C");

  // Inicia HX711
  balanza.begin(DT, SCK);
  delay(1000);
  if (!balanza.is_ready()) {
    Serial.println("Error: No se detecta el HX711.");
    while (1)
      ;
  }
  balanza.set_scale();  // A calibrar luego
  balanza.tare();       // Pone a cero la balanza
}

void loop() {

  // --- Lectura del serial ---
  //if (Serial.available() > 0) {
  //  String data = Serial.readStringUntil('\n');
  //  double a, b;
  //    if (sscanf(data.c_str(), "%lf %lf", &a, &b) == 2) {      m = a;
  //    n = b;
  //    Serial.print("Nuevos valores recibidos: m=");
  //    Serial.print(m, 5);
  //    Serial.print(" n=");
  //    Serial.println(n, 5);
  //  }
  //}

  T = millis();

  // -------- Temperatura --------
  temp = thermo.temperature(RNOMINAL, RREF);

  // -------- Presión desde HX711 --------
  if (balanza.is_ready()) {
    long lectura = balanza.get_units(5);
    // Conversión a presión con tu ecuación de calibración
    presion = (m * lectura) + n;
  } else {
    presion = 0;
  }
  // -------- LCD --------
  lcd.setCursor(8, 0);
  lcd.print("    ");
  lcd.setCursor(7, 0);
  lcd.print(presion, 1);

  lcd.setCursor(5, 1);
  lcd.print("    ");
  lcd.setCursor(5, 1);
  lcd.print(temp, 1);

  // -------- ENVÍO SERIAL --------
  Serial.print(T);
  Serial.print(" ");
  Serial.print(presion, 2);
  Serial.print(" ");
  Serial.print(temp, 2);
  Serial.println();

    // 2 Hz
}
