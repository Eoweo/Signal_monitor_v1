//#include <Adafruit_MAX31865.h>
#include "HX711.h"
//#include <LiquidCrystal_I2C.h>

// ------------------- CONFIGURACIÓN MAX31865 (PT100) -------------------
//Adafruit_MAX31865 thermo = Adafruit_MAX31865(53, 51, 50, 52);
//#define RREF      430.0
//#define RNOMINAL  100.0

// ------------------- CONFIGURACIÓN HX711 -------------------
#define DT  3   // Pin DT del HX711
#define SCK 2   // Pin SCK del HX711
HX711 balanza;

// ------------------- LCD -------------------
//LiquidCrystal_I2C lcd(0x26, 16, 2);

// ------------------- VARIABLES -------------------
float temp = 0;
float presion = 0;
unsigned long T = 0;

void setup() {
  Serial.begin(9600);

  // Inicia el sensor de temperatura
  //thermo.begin(MAX31865_3WIRE);

  // Inicia LCD
  //lcd.init();
  //lcd.clear();
  //lcd.backlight();
  //lcd.setCursor(0, 0); lcd.print("Presion:");
  //lcd.setCursor(13, 0); lcd.print("kPa");
  //lcd.setCursor(0, 1); lcd.print("Temp:");
  //lcd.setCursor(13, 1); lcd.print("C");

  // Inicia HX711
  balanza.begin(DT, SCK);
  delay(1000);
  if (!balanza.is_ready()) {
    Serial.println("Error: No se detecta el HX711.");
    while (1);
  }
  balanza.set_scale();  // Sin calibrar aún
  balanza.tare();       // Pone a cero la balanza
}

void loop() {
  T = millis();

  // -------- Temperatura --------
  //temp = thermo.temperature(RNOMINAL, RREF);
    temp = 0.00;
  // -------- Presión desde HX711 --------
  if (balanza.is_ready()) {
    // Lee en "gramos" (valor depende de calibración)
    long lectura = balanza.get_units(5);

    // Ajuste de escala: aquí decides cómo convertir a "kPa"
    // ⚠️ Esto depende de tu celda de carga + calibración
    presion = lectura;  // ejemplo: convierte a kPa
  } else {
    presion = 0;
  }

  // -------- LCD --------
  //lcd.setCursor(8, 0); lcd.print("    ");  // limpia
  //lcd.setCursor(8, 0); lcd.print(presion, 1);

  //lcd.setCursor(5, 1); lcd.print("    ");
  //lcd.setCursor(5, 1); lcd.print(temp, 1);

  // -------- ENVÍO SERIAL --------
  Serial.print(T);
  Serial.print(" ");
  Serial.print(presion, 2);
  Serial.print(" ");
  Serial.print(temp, 2);
  Serial.println();

  delay(500);  // 2 Hz
}
