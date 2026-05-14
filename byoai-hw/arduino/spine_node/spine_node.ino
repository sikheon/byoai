/*
 * BYOAI spine node — Arduino Uno (v1)
 *
 * 末端 (peripheral nerve): no logic, just sensors + actuators.
 * Reads light / dust / temp-humid, drives heater + fan + light by line-JSON
 * from the spine over USB serial (115200).
 *
 * v1 pinmap (later corrected — heater removed, soft-PWM light moved):
 *   D7  heater  (relay-driven resistive element)   <-- removed in final
 *   D9  light   (PWM)
 *   D6  fan
 *   A0  light sensor (LDR module)
 *   A1  dust    (GP2Y10 analog out)
 *   A4/A5 AM2320 (I2C temp/humid)
 *   D3  PIR
 */
#include <Wire.h>

#define PIN_HEATER 7
#define PIN_LIGHT  9
#define PIN_FAN    6
#define PIN_DUST_LED 8
#define PIN_PIR    3
#define A_LIGHT A0
#define A_DUST  A1

#define AM2320_ADDR 0x5C

unsigned long lastReport = 0;
const unsigned long REPORT_MS = 1000;

int   lightDuty = 0;   // 0..255
bool  heaterOn  = false;
int   fanDuty   = 0;

String inbuf;

void setup() {
  Serial.begin(115200);
  pinMode(PIN_HEATER, OUTPUT);
  pinMode(PIN_LIGHT, OUTPUT);
  pinMode(PIN_FAN, OUTPUT);
  pinMode(PIN_DUST_LED, OUTPUT);
  pinMode(PIN_PIR, INPUT);
  Wire.begin();
  digitalWrite(PIN_HEATER, LOW);
}

float readDust() {
  digitalWrite(PIN_DUST_LED, LOW);
  delayMicroseconds(280);
  int raw = analogRead(A_DUST);
  delayMicroseconds(40);
  digitalWrite(PIN_DUST_LED, HIGH);
  float v = raw * (5.0 / 1024.0);
  float dust = (v - 0.6) * 170.0;   // ug/m3, crude
  return dust < 0 ? 0 : dust;
}

bool readAM2320(float &t, float &h) {
  Wire.beginTransmission(AM2320_ADDR);
  Wire.endTransmission();
  Wire.beginTransmission(AM2320_ADDR);
  Wire.write(0x03); Wire.write(0x00); Wire.write(0x04);
  if (Wire.endTransmission() != 0) return false;
  delay(2);
  Wire.requestFrom(AM2320_ADDR, 8);
  if (Wire.available() < 8) return false;
  byte buf[8];
  for (int i = 0; i < 8; i++) buf[i] = Wire.read();
  h = ((buf[2] << 8) | buf[3]) / 10.0;
  t = (((buf[4] & 0x7F) << 8) | buf[5]) / 10.0;
  if (buf[4] & 0x80) t = -t;
  return true;
}

void applyCommand(const String &line) {
  // naive JSON: look for keys
  int li = line.indexOf("\"light\"");
  if (li >= 0) lightDuty = line.substring(line.indexOf(':', li) + 1).toInt();
  int hi = line.indexOf("\"heat\"");
  if (hi >= 0) heaterOn = line.substring(line.indexOf(':', hi) + 1).toInt() != 0;
  int fi = line.indexOf("\"fan\"");
  if (fi >= 0) fanDuty = line.substring(line.indexOf(':', fi) + 1).toInt();
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') { applyCommand(inbuf); inbuf = ""; }
    else inbuf += c;
  }

  analogWrite(PIN_LIGHT, lightDuty);
  analogWrite(PIN_FAN, fanDuty);
  digitalWrite(PIN_HEATER, heaterOn ? HIGH : LOW);

  unsigned long now = millis();
  if (now - lastReport >= REPORT_MS) {
    lastReport = now;
    int lux = analogRead(A_LIGHT);
    float dust = readDust();
    float t = 0, h = 0;
    readAM2320(t, h);
    int pir = digitalRead(PIN_PIR);
    Serial.print("{\"lux\":"); Serial.print(lux);
    Serial.print(",\"dust\":"); Serial.print(dust, 1);
    Serial.print(",\"t\":"); Serial.print(t, 1);
    Serial.print(",\"h\":"); Serial.print(h, 1);
    Serial.print(",\"pir\":"); Serial.print(pir);
    Serial.println("}");
  }
}
