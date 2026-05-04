# BYOAI 하드웨어 — 시스템 구성 (Arduino + 라즈베리파이)

폰(Gemma) = 대뇌 · 라즈베리파이 = 척수 · Arduino = 말단신경/근육.
시뮬(`../byoai-sim/byoai_sim.py`)의 `Room`/`SpaceHub`/`UserModel`을 실물로 옮긴 것.

**BYOAI는 온도 전용이 아니라 멀티모달**이다. 공간을 여러 감각으로 파악해야
"어느 공간 가도 최적화"가 성립한다. 키트 센서가 곧 능력(capability):

| 센서 | 능력(kind) | 액추에이터 | 응답 | 발열체 |
|------|-----------|-----------|------|--------|
| 조도(LDR) | `light` | LED PWM | 즉각 | ❌ |
| 미세먼지 | `air_quality` | 팬(릴레이/MOSFET) | 빠름 | ❌ |
| PIR | `occupancy` | (신호만) | 즉각 | ❌ |
| 온습도(DHT) | `climate` | 히터(릴레이) | 느림(분) | ✅ Phase2 |

> **첫 물리 데모 = 조도(`light`)**: LDR→LED PWM은 즉각 수렴·안전·추가구매 0.
> 전체 파이프라인을 오늘 부품으로 증명. 난방은 PTC 사면 능력 하나 추가로 확장.

```
 [폰: Gemma 4 E4B]  대뇌 — 멀티 능력 보고 목표값 결정
        │  TCP(줄단위 JSON)  ※ 지금은 PC가 폰을 adb로 대리 호출
        ▼
 [라즈베리파이]      척수 — 능력별 제어루프 + 응답모델 학습 (spine.py)
        │  USB 시리얼(115200, 줄단위 JSON)
        ▼
 [Arduino]          말단 — 센서 읽기 + 액추에이터 구동 (spine_node.ino)
        │  GPIO
        ▼
 [모의환경(미니룸)]  박스 + 조명/발열체/팬 + 각종 센서
```

---

## 통신 프로토콜

### 1) 시리얼 (Arduino ↔ RPi) — 115200 baud, 줄단위 JSON
- **Arduino → RPi (텔레메트리, 1초)**: 연결된 센서만 키 포함
  `{"t":21.3,"h":45.0,"lux":120,"pm":35,"pir":1}`  (없는 값은 생략 또는 -1)
- **RPi → Arduino (명령)**: 연결된 액추에이터만
  `{"heater":0,"light":180,"fan":1}`  (light=0~255 PWM, heater/fan=0/1)

### 2) TCP (RPi ↔ 폰/대뇌) — 줄단위 JSON, 기본 포트 8765
- **접속 시 RPi → 폰: `SPACE_DESCRIPTOR`** — 장소 + **능력 배열**(각 능력의 현재값·범위·학습된 응답모델) + occupancy
- **폰 → RPi: `COMMAND`** `{"type":"COMMAND","targets":{"climate":23.5,"light":300,"air_quality":35},"reason":"..","preheat_minutes":15}`
- **RPi → 폰: `STATE`** (주기) 능력별 현재값/목표/액추에이터
- **RPi → 폰: `FEEDBACK`** (수동보정 감지) `{"type":"FEEDBACK","capability":"light","from":300,"to":450,"context_label":".."}`

> TCP 줄단위 JSON으로 시작 = 의존성 0(폰 앱 만들 때 WebSocket으로 승격).

---

## 배선 (보유 부품 기준)

**조도센서 LDR (Phase 1 주인공)** — LDR + 10kΩ 분압 → A0
**LED 조명 (조도 액추에이터)** — D9(PWM) → (저항/MOSFET) → LED
**미세먼지센서** — 모델별 상이(GP2Y10은 A1 + LED구동핀 D8). 팬은 D7(릴레이/MOSFET)
**온습도 DHT22** — D2 (DATA-VCC 10kΩ 풀업; 모듈형 내장)
**히터 릴레이 (Phase 2)** — D7 IN (발열체 전원선을 COM–NO 통과)

`spine_node.ino` 상단 `#define`으로 연결된 것만 켜면 됨.

---

## 단계별 빌드

| 단계 | 부품 | 명령 | 검증 |
|------|------|------|------|
| **0** | RPi만 | `python spine.py --sim` + `python phone_brain.py` | 폰↔척수 프로토콜 + Gemma 멀티능력 결정 (가상 물리) |
| **1** | +Arduino +LDR +LED | `.ino` 플래시 → `python spine.py --port /dev/ttyUSB0` | **조도 폐루프** 실물 (손으로 가리면 LED 밝아짐) |
| **1b** | +미세먼지 +팬 | 동일 | 공기질 능력 추가 (연기 불면 팬 가동) |
| **2** | +PTC히터 +단열박스 | 동일 | 난방 능력 = 진짜 RC 열역학 |
| **3** | 박스 2개 | 폰 들고 이동 | **복리효과 물리 실증** (학습 선호 타 공간 이식) |

## 파일
- `arduino/spine_node/spine_node.ino` — 말단 펌웨어 (멀티 센서/액추에이터, `#define`로 토글, 로직 0)
- `rpi/spine.py` — 척수 (능력별 제어루프+학습+TCP), `--sim`으로 HW 없이 테스트
- `rpi/phone_brain.py` — 대뇌 브릿지 (척수 접속→descriptor→Gemma(adb)→명령). `../byoai-sim`의 검증된 adb 브릿지(`/exit` 종료) 재사용
- `rpi/requirements.txt`
