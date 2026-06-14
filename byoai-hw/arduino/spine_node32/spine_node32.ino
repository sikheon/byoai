/*
 * BYOAI spine node 32 — 무선 말단 (ESP32 DevKit). 판단 로직 0, USB 대신 WiFi.
 * 척수(spine.py --node)의 TCP 8766 에 접속해 시리얼판과 동일한 줄단위 JSON 사용:
 *   송신 (1초): {"lux":120,"pir":1}
 *   수신       : {"heater":0,"light":180,"fan":1}
 * 차이점: 무선 단절 대비 — 명령 10초 두절 시 액추에이터 전부 OFF (안전정지).
 *
 * ⚠ 보드별 설정: 아래 4개만 바꾸면 됨.
 */
#define WIFI_SSID   "YOUR_WIFI"        // 공간 WiFi
#define WIFI_PASS   "YOUR_PASS"
#define SPINE_HOST  "192.168.0.11"     // 척수(Pi) IP
#define SPINE_PORT  8766               // spine.py --node 포트

#define USE_LDR     1
#define USE_PIR     0

// ESP32 DevKit 핀 (Uno와 다름!)
#define PIN_LIGHT   25   // 백색 LED (PWM 가능 핀)
#define PIN_FAN     26   // 청색 LED / 팬 스위치
#define PIN_HEATER  27   // 적색 LED / 히터 스위치
#define PIN_LDR     34   // ADC1 (입력 전용 핀, 3.3V 기준!)
#define PIN_PIR     33

#define CMD_TIMEOUT_MS 10000   // 명령 두절 → 안전정지

#include <WiFi.h>
WiFiClient spine;
unsigned long lastReport = 0, lastCmd = 0;
char buf[96]; byte idx = 0;

long jget(const char* s, const char* key, long def) {
  const char* p = strstr(s, key);
  if (!p) return def;
  p += strlen(key);
  while (*p && (*p < '0' || *p > '9') && *p != '-') p++;
  return (*p) ? atol(p) : def;
}

void allOff() {
  analogWrite(PIN_LIGHT, 0);
  digitalWrite(PIN_FAN, LOW);
  digitalWrite(PIN_HEATER, LOW);
}

void applyCommand(const char* line) {
  lastCmd = millis();
  long h = jget(line, "\"heater\"", -1);
  long l = jget(line, "\"light\"",  -1);
  long f = jget(line, "\"fan\"",    -1);
  if (h >= 0) digitalWrite(PIN_HEATER, h ? HIGH : LOW);
  if (l >= 0) analogWrite(PIN_LIGHT, constrain(l, 0, 255));
  if (f >= 0) digitalWrite(PIN_FAN, f ? HIGH : LOW);
}

void ensureConnected() {
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    for (int i = 0; i < 20 && WiFi.status() != WL_CONNECTED; i++) delay(500);
  }
  if (!spine.connected()) {
    spine.stop();
    if (spine.connect(SPINE_HOST, SPINE_PORT)) idx = 0;
    else delay(3000);
  }
}

void setup() {
  pinMode(PIN_LIGHT, OUTPUT); pinMode(PIN_FAN, OUTPUT); pinMode(PIN_HEATER, OUTPUT);
  allOff();
#if USE_PIR
  pinMode(PIN_PIR, INPUT);
#endif
  WiFi.mode(WIFI_STA);
}

void loop() {
  ensureConnected();

  while (spine.connected() && spine.available()) {   // 명령 수신
    char c = spine.read();
    if (c == '\n') { buf[idx] = 0; applyCommand(buf); idx = 0; }
    else if (idx < sizeof(buf) - 1) buf[idx++] = c;
  }

  if (millis() - lastCmd > CMD_TIMEOUT_MS) allOff(); // 척수 두절 → 안전정지

  if (spine.connected() && millis() - lastReport >= 1000) {  // 텔레메트리
    lastReport = millis();
    String out = "{";
    bool first = true;
#if USE_LDR
    long lux = map(analogRead(PIN_LDR), 0, 4095, 0, 1000);   // ESP32 ADC=12비트
    out += "\"lux\":" + String(lux); first = false;
#endif
#if USE_PIR
    if (!first) out += ",";
    out += "\"pir\":" + String(digitalRead(PIN_PIR));
#endif
    out += "}\n";
    spine.print(out);
  }
}
