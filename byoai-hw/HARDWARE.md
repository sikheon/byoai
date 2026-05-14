# BYOAI 하드웨어 설계도 (v1.0 — 2026-06-10)

> 물리 구성 정본. 회로·핀맵·BOM·박스 구성. 동작 규칙은 [`../ARCHITECTURE.md`](../ARCHITECTURE.md),
> 작업 순서는 [`../ROADMAP.md`](../ROADMAP.md). **D-6 (LED 액추에이터 대체) 반영.**

---

## 1. 전체 토폴로지

```
폰 (대뇌)                    라즈베리파이 (척수)              미니룸 박스 A
┌──────────┐   WiFi/TCP     ┌──────────────┐   USB 시리얼   ┌─────────────────┐
│ Gemma E4B │ ───:8765────▶ │ spine.py ×2  │ ──/dev/ttyUSB0─▶│ Arduino #1 + 회로 │
│ byoai-app │ ◀──mDNS─────  │ (인스턴스 2개)│ ──/dev/ttyUSB1─▶│ Arduino #2 + 회로 │
└──────────┘                └──────────────┘                └─────────────────┘
                                                             미니룸 박스 B
```

- **Pi 1대가 척수 2개 호스팅** (박스당 spine 인스턴스 1개):
  - 박스A: `python3 spine.py --port /dev/ttyUSB0 --tcp 8765 --config space_a.json --mdns`
  - 박스B: `python3 spine.py --port /dev/ttyUSB1 --tcp 8766 --config space_b.json --mdns`
  - 각자 자기 `space_config.json`(space_id·place) → mDNS에 별개 공간으로 광고 → 복리효과 데모(D-2) 성립.
  - Arduino가 1대뿐인 동안: 박스B는 `--sim`으로 리허설 가능 (프로토콜 동일).

---

## 2. 능력 ↔ 실물 매핑 (D-6: 미보유 기기는 LED 대체)

| 능력 | 센서 (입력) | 액추에이터 (출력) | 물리성 |
|------|------------|------------------|--------|
| `light` | **LDR 실물** (A0) | **백색 LED PWM** (D9) | ★ 완전 실물 폐루프 (히어로) |
| `air_quality` | sim (척수가 모델링) | **청색 LED** (D6) = 팬 대역 | 제어로직 실물·물리 sim |
| `climate` | sim (척수 RC 모델) | **적색 LED** (D7) = 히터 대역 | 제어로직 실물·물리 sim |
| `occupancy` | **PIR 실물** (D3) | (신호만, 카드 없음) | 실물 |

> 액추에이터는 `{type,pin,range}`로 추상화되어 있어 팬이든 LED든 동일 경로(N-7의 실물 증거).
> 센서는 입력이라 LED로 대체 불가 → 미보유 센서(pm·t)는 척수 **HybridBackend**가 sim 물리로 채움.
> 명령은 시리얼·sim 양쪽에 전달 → LED는 실제 점등, sim 물리는 그에 반응 (pm↓, t↑).

---

## 3. 회로도 (박스 1개 기준, Arduino Uno/Nano)

```
                         Arduino
                       ┌─────────┐
   LDR ┌──────┐        │         │
 5V ───┤ LDR  ├──┬─────┤ A0      │      백색 LED (light = 조명)
       └──────┘  │     │      D9 ├──[220Ω]──▶|── GND   (PWM 0~255)
                 │     │         │
              [10kΩ]   │         │      청색 LED (air = 팬 대역)
                 │     │      D6 ├──[220Ω]──▶|── GND   (ON/OFF)
                GND    │         │
                       │         │      적색 LED (climate = 히터 대역)
   PIR (HC-SR501)      │      D7 ├──[220Ω]──▶|── GND   (ON/OFF)
   VCC ── 5V           │         │
   OUT ────────────────┤ D3      │
   GND ── GND          │         │
                       │   USB   ├───── 라즈베리파이 (115200, 줄단위 JSON)
                       └─────────┘
```

**배선 요점**
- LDR은 10kΩ과 **전압분배**: `5V ─ LDR ─ A0 ─ 10kΩ ─ GND`. 밝으면 LDR 저항↓ → A0 전압↑.
- LED는 모두 직렬 220Ω (전류 제한). D9는 PWM 핀이어야 함 (Uno: 3,5,6,9,10,11).
- PIR HC-SR501은 5V 전원, OUT은 디지털 (재트리거 모드 점퍼 H 권장).
- **조도 폐루프 검증법**: LDR을 손으로 가림 → lux↓ → 척수가 D9 PWM↑ → 백색 LED 밝아짐.
- 백색 LED와 LDR은 박스 안에서 **서로 마주보게** 배치해야 폐루프 성립 (LED 빛이 LDR에 닿게).

### 핀맵 (펌웨어 `spine_node.ino`와 1:1)

| 핀 | 연결 | 방향 | 능력 |
|----|------|------|------|
| A0 | LDR 전압분배 중점 | IN (analog) | light 센서 |
| D9 | 백색 LED (PWM) | OUT | light 액추에이터 |
| D6 | 청색 LED | OUT | air_quality 액추에이터 (팬 대역) |
| D7 | 적색 LED | OUT | climate 액추에이터 (히터 대역) |
| D3 | PIR OUT | IN | occupancy 센서 |
| 예비 D2/A1/D8 | (DHT·GP2Y10 실센서 구매 시) | — | climate/air 승격용 |

펌웨어 토글: `USE_LDR 1`, `USE_PIR 1`, `USE_DHT 0`, `USE_DUST 0` — 실센서 추가 = `#define` 한 줄 + 배선.

---

## 4. BOM (박스 2개 기준)

| 부품 | 수량 | 보유 | 비고 |
|------|------|------|------|
| Arduino Uno/Nano | 2 | 1 보유 시 박스B는 `--sim` 리허설 | USB 케이블 포함 |
| LDR (CdS) | 2 | 키트 보유 | |
| 저항 10kΩ (LDR 분배) | 2 | 키트 보유 | |
| LED 백/청/적 | 각 2 | 키트 보유 | 색 무관, 역할 구분용 |
| 저항 220Ω | 6 | 키트 보유 | LED 전류 제한 |
| PIR HC-SR501 | 2 | 1개면 박스A만 | 미보유 시 푸시버튼으로 대체 가능 |
| 브레드보드 + 점퍼 | 2조 | 보유 | |
| 미니룸 박스 (종이/폼보드) | 2 | 제작 | 내부 암실에 가까울수록 폐루프 선명 |
| **추가 구매 필요** | **0** | | 발열체·팬·미세먼지센서 불필요 (D-6) |

---

## 5. 박스 제작 가이드

- 크기: 신발상자급 (20~30cm). 내부가 어두울수록 LED↔LDR 폐루프 대비가 선명.
- 배치: 백색 LED와 LDR을 10~15cm 거리로 마주보게. PIR은 입구(손 넣는 구멍) 방향.
- 윗면에 관찰창(또는 개방) — 청중이 LED 상태 변화를 봐야 데모가 됨.
- 박스 A/B는 동일 구성. 라벨만 다르게 (예: "Room A" / "Room B") — 복리효과 데모 시 시각 구분.

## 5b. 무선 말단 옵션 (ESP32) — 박스B 권장

말단을 USB 대신 WiFi로: **Arduino+WiFi모듈(ESP-01 브릿지)은 비추**(레벨변환·AT펌웨어 고통),
정석은 **ESP32 DevKit(~5천원)로 말단 교체**. 프로토콜은 동일 줄JSON, 전송만 무선.

```
ESP32(spine_node32.ino) ── WiFi/TCP:8766 ──▶ spine.py --node --mdns
```
- 척수 실행: `bash restart_spine.sh --node --mdns` (poll 8766 수신, sim 채움 동일)
- 펌웨어: `arduino/spine_node32/spine_node32.ino` — 상단 4개 define(SSID/PASS/Pi IP/포트)만 수정
- ESP32 핀: LDR=**GPIO34**(ADC 3.3V!), 백LED=25, 청LED/팬=26, 적LED/히터=27, PIR=33
- **안전정지 내장**: 명령 10초 두절 → 액추에이터 전부 OFF (무선 단절 대비, 점진적 안전)
- 박스B를 USB 케이블 없이 라우터 권역 아무 데나 → D-2 복리효과 데모 배치 자유

12V 팬(YM1206PTS1 등) 구동 시: 핀 직결 불가(12V/0.26A) → 릴레이 모듈(IN→팬핀) 또는
MOSFET 로우사이드(D6/GPIO26→게이트, 12V− 와 보드 GND 공통) + 12V 어댑터.

## 6. 검증 절차 (WU-4.1 수용 기준과 1:1)

1. Arduino에 `spine_node.ino` 업로드 (USE_LDR=1, USE_PIR=1).
2. 시리얼 모니터 115200: 1초마다 `{"lux":...,"pir":...}` 확인.
3. `{"light":200}` 입력 → 백색 LED 점등 확인. `{"fan":1}` → 청색 LED. `{"heater":1}` → 적색 LED.
4. Pi 연결: `python3 spine.py --port /dev/ttyUSB0` → 제어루프가 lux를 목표로 수렴.
5. LDR 가림 → 백색 LED 자동 증광 = **폐루프 성립**.
