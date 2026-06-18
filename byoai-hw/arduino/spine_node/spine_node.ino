/*
 * BYOAI spine node — 말단(센서/액추에이터). 판단 로직 0.
 * 배선·핀맵 정본: ../../HARDWARE.md (D-6: 팬→청색LED D6, 히터→적색LED D7 대체)
 * 프로토콜(115200, 줄단위 JSON):
 *   송신 A->RPi (1초): {"t":21.3,"h":45.0,"lux":120,"pm":35,"pir":1}
 *   수신 RPi->A      : {"heater":0,"light":180,"fan":1}
 * 연결한 것만 아래 #define 을 1로. 안 쓰는 줄은 자동 생략됨.
 * 박스 안 온도(t)는 척수 sim 담당(히터 실물 없음) — AM2320은 박스 밖 외기(t_out) 전용.
 */

#define USE_TOUT    1   // AM2320 온습도(I2C: SDA=A4, SCL=A5) — ⚠ 박스 "밖" 외기(t_out). 박스 안 온도는 sim 담당
#define USE_LDR     1   // 조도   (light)  ← Phase 1 주인공
#define USE_DUST    1   // 미세먼지 (air_quality, GP2Y10) — Vo=A1, LED구동=D8
#define USE_PIR     1   // 재실   (occupancy) — HC-SR501 (미보유 시 0)

#define PIN_LIGHT   7   // 조명 LED (HW-478 G+B) — 소프트PWM 밝기조절
#define PIN_RELAY   6   // 릴레이 IN (팬 스위치)
#define PIN_FAN     9   // 팬 전원 공급선 — 사용자 회로: D9 → 릴레이접점 → 팬
#define PIN_LDR     A0
#define PIN_DUST_A  A1
#define PIN_DUST_LED 8
#define PIN_PIR     3

#if USE_TOUT
  #include <Wire.h>
  #include <Adafruit_AM2320.h>   // 라이브러리 매니저: "Adafruit AM2320" (+ Adafruit Unified Sensor)
  Adafruit_AM2320 am2320;
#endif

unsigned long lastReport = 0;
char buf[80]; byte idx = 0;
byte lightDuty = 0;   // D7 소프트PWM 듀티 (비PWM핀 밝기조절, ~244Hz)

// "key":<int> 정수값 추출. 없으면 def 반환.
long jget(const char* s, const char* key, long def) {
  const char* p = strstr(s, key);
  if (!p) return def;
  p += strlen(key);
  while (*p && (*p < '0' || *p > '9') && *p != '-') p++;
  return (*p) ? atol(p) : def;
}

void applyCommand(const char* line) {
  long l = jget(line, "\"light\"",  -1);
  long f = jget(line, "\"fan\"",    -1);
  if (l >= 0) lightDuty = constrain(l, 0, 255);   // 소프트PWM 듀티 갱신
  if (f >= 0) {                                    // 팬 = 전원(D9) + 릴레이(D6) 동시
    digitalWrite(PIN_FAN, f ? HIGH : LOW);
    digitalWrite(PIN_RELAY, f ? HIGH : LOW);
  }
}

#if USE_DUST
float readDust() {           // GP2Y10: LED ON -> 0.28ms -> 샘플 -> OFF
  digitalWrite(PIN_DUST_LED, LOW); delayMicroseconds(280);
  int raw = analogRead(PIN_DUST_A);
  delayMicroseconds(40); digitalWrite(PIN_DUST_LED, HIGH);
  float v = raw * (5.0 / 1024.0);
  float ug = (v - 0.6) * 170.0;   // 대략적 환산(보정 필요)
  return ug < 0 ? 0 : ug;
}
#endif

void setup() {
  Serial.begin(115200);
  pinMode(PIN_LIGHT, OUTPUT); pinMode(PIN_RELAY, OUTPUT); pinMode(PIN_FAN, OUTPUT);
  digitalWrite(PIN_RELAY, LOW); digitalWrite(PIN_FAN, LOW); digitalWrite(PIN_LIGHT, LOW);
#if USE_TOUT
  Wire.begin();
  Wire.setWireTimeout(25000, true);  // I2C 먹통(배선불량)이 노드 전체를 죽이지 않게 — 실패시 NaN으로 끝남
  am2320.begin();
#endif
#if USE_DUST
  pinMode(PIN_DUST_LED, OUTPUT); digitalWrite(PIN_DUST_LED, HIGH);
#endif
#if USE_PIR
  pinMode(PIN_PIR, INPUT);
#endif
}

void loop() {
  // D7 소프트PWM: 16µs×256 = 4.1ms 주기(~244Hz) — 눈에 깜빡임 없음
  digitalWrite(PIN_LIGHT, (byte)(micros() >> 4) < lightDuty ? HIGH : LOW);

  while (Serial.available()) {                 // 명령 수신
    char c = Serial.read();
    if (c == '\n') { buf[idx] = 0; applyCommand(buf); idx = 0; }
    else if (idx < sizeof(buf) - 1) buf[idx++] = c;
  }
  if (millis() - lastReport >= 1000) {         // 텔레메트리 송신
    lastReport = millis();
    Serial.print("{");
    bool first = true;
#if USE_TOUT
    // 외기 측정: 키를 t_out 으로 — "t"(박스 안)를 덮으면 히터 없는 폐루프가 수렴 못 함
    // AM2320 샘플링 주기 2초 → 2회에 1번만 읽음 (과속 폴링시 NaN)
    static byte every = 0;
    static float t = NAN, h = NAN;
    if ((every++ & 1) == 0) { t = am2320.readTemperature(); h = am2320.readHumidity(); }
    if (!isnan(t)) { Serial.print("\"t_out\":"); Serial.print(t,1); first=false; }
    if (!isnan(h)) { if(!first)Serial.print(","); Serial.print("\"h\":"); Serial.print(h,1); first=false; }
#endif
#if USE_LDR
    int ldr = analogRead(PIN_LDR);             // 0~1023 → lux 근사
    long lux = map(ldr, 0, 1023, 0, 1000);
    if(!first)Serial.print(","); Serial.print("\"lux\":"); Serial.print(lux); first=false;
#endif
#if USE_DUST
    if(!first)Serial.print(","); Serial.print("\"pm\":"); Serial.print(readDust(),0); first=false;
#endif
#if USE_PIR
    if(!first)Serial.print(","); Serial.print("\"pir\":"); Serial.print(digitalRead(PIN_PIR)); first=false;
#endif
    Serial.println("}");
  }
}
