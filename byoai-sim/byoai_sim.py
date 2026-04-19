"""
BYOAI Smart Home — End-to-End Simulation
=========================================

휴대용 AI(폰의 실제 Gemma 4)가 어느 공간에 가도 사용자에게 최적화되는
스마트홈을 시뮬레이션한다.

아키텍처 (신경계 비유):
  - 대뇌(PhoneBrain) : 폰의 실제 on-device Gemma 4 (adb로 호출). 결정만 내림.
  - 척수(SpaceHub)   : 각 공간의 RPi. 항상 켜짐. 제어루프 + 센서 + 열모델 발행.
  - 기억(UserModel)  : 폰에 들고 다니는 휴대용 선호 모델. 수동보정으로 학습.
  - 신체(Room)       : 물리 열역학 시뮬 (RC 모델).

핵심 시연:
  1. 공간 A 진입 → 대뇌가 [공간 descriptor + 내 선호] 결합해 목표온도 결정
  2. 척수가 제어루프로 목표 향해 가열 (대뇌 없이도 유지)
  3. 사용자가 수동으로 온도 보정 → 척수가 FEEDBACK 푸시 → 사용자모델 학습
  4. 전혀 다른 공간 B 진입 → 학습된 선호로 더 정확한 초기 결정 (복리 효과)

LLM 두뇌는 폰의 진짜 Gemma 4를 쓴다 (adb shell + llama.cpp). 모델 미가용 시
heuristic 폴백으로 시뮬은 계속 진행된다.
"""

from __future__ import annotations
import dataclasses
import json
import re
import subprocess
import sys
import hashlib
from dataclasses import dataclass, field, asdict
from pathlib import Path

# ----------------------------------------------------------------------------
# 설정
# ----------------------------------------------------------------------------
import shutil
ADB = (shutil.which("adb")
       or r"C:\Users\HS\Downloads\platform-tools-latest-windows\platform-tools\adb.exe")
DEVICE_DIR = "/data/local/tmp/llama"
LLAMA_LIB = DEVICE_DIR  # LD_LIBRARY_PATH
MODEL_E2B = "gemma-4-E2B-it-Q4_K_M.gguf"
MODEL_E4B = "gemma-4-E4B-it-Q4_K_M.gguf"
DECISION_MODEL = MODEL_E4B  # 실측 결론: 온도결정은 추론깊이 우위인 E4B 채택
CACHE_FILE = Path(__file__).parent / "llm_cache.json"


# ----------------------------------------------------------------------------
# 물리 시뮬: 방 (RC 열모델)
# ----------------------------------------------------------------------------
@dataclass
class Room:
    """단순 RC 열모델.  dT/dt = heat_input(on) - k_loss*(T - T_out)"""
    name: str
    temp: float                 # 현재 실내온도(℃)
    outside: float              # 외부온도(℃)
    heat_rate: float            # 난방 켰을 때 분당 가열(℃/min, loss 전)
    k_loss: float               # 외기 손실계수 (1/min) — 클수록 외풍 심함
    heating_on: bool = False

    def step(self, minutes: float = 1.0):
        for _ in range(int(minutes)):
            gain = self.heat_rate if self.heating_on else 0.0
            loss = self.k_loss * (self.temp - self.outside)
            self.temp += (gain - loss)

    # 척수가 발행할 "학습된 열모델" (관측 가능한 근사치)
    def published_thermal_model(self) -> dict:
        # 평형 추정: 켜짐 상승률(초기), 꺼짐 하강률(초기)
        heat_per_min = self.heat_rate - self.k_loss * (self.temp - self.outside)
        cool_per_min = self.k_loss * (self.temp - self.outside)
        return {
            "heat_rate_c_per_min": round(max(heat_per_min, 0.01), 3),
            "cool_rate_c_per_min": round(max(cool_per_min, 0.01), 3),
            "confidence": 0.8,
        }


# ----------------------------------------------------------------------------
# 척수: 공간 허브 (RPi)
# ----------------------------------------------------------------------------
@dataclass
class SpaceHub:
    space_id: str
    place: str
    room: Room
    target_temp: float | None = None
    hysteresis: float = 0.3
    granted_scopes: tuple = ("climate.read", "climate.write")

    # --- 능력 발행 (SPACE_DESCRIPTOR) ---
    def descriptor(self, occupancy: int) -> dict:
        return {
            "type": "SPACE_DESCRIPTOR",
            "space_id": self.space_id,
            "place": self.place,
            "granted_scopes": list(self.granted_scopes),
            "capabilities": [
                {
                    "id": "climate-1",
                    "kind": "climate",
                    "controls": {"target_temp": {"min": 18, "max": 30, "step": 0.5}},
                    "state": {
                        "current_temp": round(self.room.temp, 1),
                        "outside_temp": self.room.outside,
                        "mode": "heat",
                    },
                    "thermal_model": self.room.published_thermal_model(),
                }
            ],
            "occupancy": {"people": occupancy},
        }

    # --- 명령 적용 (COMMAND) ---
    def apply_command(self, cmd: dict):
        cap = cmd.get("target_temp")
        if cap is not None:
            self.target_temp = float(cap)

    # --- 척수 반사: 제어 루프 (대뇌 없이도 목표 유지) ---
    def control_tick(self):
        if self.target_temp is None:
            return
        if self.room.temp < self.target_temp - self.hysteresis:
            self.room.heating_on = True
        elif self.room.temp > self.target_temp + self.hysteresis:
            self.room.heating_on = False


# ----------------------------------------------------------------------------
# 기억: 휴대용 사용자 모델 (폰에 들고 다님)
# ----------------------------------------------------------------------------
@dataclass
class UserModel:
    user_id: str
    cold_sensitive_offset: float = 2.0     # 평소 사람 대비 선호 +오프셋
    corrections: list = field(default_factory=list)  # (맥락, 보정) 학습 누적

    def summary_for_prompt(self) -> str:
        lines = [f"- 추위 민감도: 평소보다 +{self.cold_sensitive_offset}도 선호"]
        if self.corrections:
            lines.append("- 과거 수동보정 학습 기록:")
            for c in self.corrections[-4:]:
                lines.append(
                    f"    · {c['context']} → 사용자가 {c['delta']:+.1f}도 보정"
                )
        else:
            lines.append("- 과거 보정 기록: 없음")
        return "\n".join(lines)

    def learn_from_feedback(self, fb: dict):
        """수동보정 = 암묵적 피드백. (맥락 + 보정값) 쌍으로 누적."""
        delta = fb["to"] - fb["from"]
        self.corrections.append({"context": fb["context_label"], "delta": delta})
        # 영구 선호 추정: 비슷한 보정이 반복되면 base offset 소폭 이동
        if abs(delta) >= 1.0:
            self.cold_sensitive_offset += 0.5 * (1 if delta > 0 else -1)

    def save(self, path: Path):
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2),
                        encoding="utf-8")


# ----------------------------------------------------------------------------
# 대뇌: 폰의 실제 Gemma 4 (adb 브릿지)
# ----------------------------------------------------------------------------
def _load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict):
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2),
                          encoding="utf-8")


def _extract_json(text: str) -> dict | None:
    """모델 출력(배너/생각 섞임)에서 마지막으로 파싱되는 {...} 추출."""
    candidates = re.findall(r"\{[^{}]*\}", text, flags=re.DOTALL)
    for cand in reversed(candidates):
        try:
            obj = json.loads(cand)
            if "target_temp" in obj:
                return obj
        except Exception:
            continue
    return None


def build_prompt(descriptor: dict, user: UserModel, situation: str) -> str:
    cap = descriptor["capabilities"][0]
    st = cap["state"]
    tm = cap["thermal_model"]
    return f"""너는 BYOAI 스마트홈의 의사결정 AI다. 아래 공간 정보와 사용자 정보를 결합해 최적 난방 온도를 정하라. 반드시 JSON 한 개만 출력한다.

[공간] {descriptor['place']}
- 기기: climate-1 (난방, 18~30도), 현재 {st['current_temp']}도, 외부 {st['outside_temp']}도
- 열모델: 난방시 분당 +{tm['heat_rate_c_per_min']}도, 끄면 분당 -{tm['cool_rate_c_per_min']}도 (신뢰도 {tm['confidence']})

[사용자]
{user.summary_for_prompt()}
- 현재 상황: {situation}

[출력] JSON만: {{"target_temp": 숫자, "reason": "한문장", "preheat_minutes": 숫자}}
"""


def llm_decide(prompt: str, model: str = DECISION_MODEL, use_cache: bool = True) -> dict:
    """폰의 실제 Gemma 4로 결정. 실패 시 heuristic 폴백."""
    key = hashlib.sha1((model + prompt).encode("utf-8")).hexdigest()
    cache = _load_cache()
    if use_cache and key in cache:
        out = cache[key]
        out["_source"] = "cache"
        return out

    # 프롬프트를 폰에 push 후 llama-cli 실행
    local_prompt = Path(__file__).parent / "_sim_prompt.txt"
    local_prompt.write_text(prompt, encoding="utf-8")
    try:
        subprocess.run([ADB, "push", str(local_prompt),
                        f"{DEVICE_DIR}/_sim_prompt.txt"],
                       capture_output=True, timeout=30)
        # 대화모드 llama-cli는 -f 프롬프트 처리 후 stdin을 기다린다.
        # stdin으로 "/exit"를 보내 생성 직후 깔끔히 종료시킨다.
        # (< /dev/null은 EOF→빈 "> " 무한루프를 유발해 타임아웃됨)
        # device-side timeout은 백스톱.
        cmd = (f"cd {DEVICE_DIR} && LD_LIBRARY_PATH={LLAMA_LIB} "
               f"timeout 150 ./llama-cli -m {model} -f _sim_prompt.txt "
               f"-n 200 -t 4 --temp 0.3 -rea off 2>/dev/null")
        res = subprocess.run([ADB, "shell", cmd], input="/exit\n",
                             capture_output=True, text=True, timeout=200,
                             encoding="utf-8", errors="replace")
        parsed = _extract_json(res.stdout or "")
        if parsed:
            parsed["_source"] = f"gemma:{model.split('-')[2]}"  # E2B/E4B
            cache[key] = {k: v for k, v in parsed.items() if k != "_source"}
            _save_cache(cache)
            return parsed
    except Exception as e:
        print(f"  [LLM 호출 실패: {e}] heuristic 폴백 사용")

    # --- heuristic 폴백 ---
    fb = _heuristic_decision(prompt)
    fb["_source"] = "heuristic"
    return fb


def _heuristic_decision(prompt: str) -> dict:
    cur = float(re.search(r"현재 ([\d.]+)도", prompt).group(1))
    base = 21.0 + 2.0
    if "비" in prompt:
        base += 2.0
    return {
        "target_temp": round(base, 1),
        "reason": "추위 민감 + 비 진입 보정(폴백)",
        "preheat_minutes": 0,
    }


# ----------------------------------------------------------------------------
# 시나리오 러너
# ----------------------------------------------------------------------------
def run_space_episode(hub: SpaceHub, user: UserModel, situation: str,
                      occupancy: int, manual_override_to: float | None,
                      max_minutes: int = 40):
    print("\n" + "=" * 64)
    print(f"  공간 진입: {hub.place}  (space_id={hub.space_id})")
    print("=" * 64)
    desc = hub.descriptor(occupancy)
    st = desc["capabilities"][0]["state"]
    print(f"  [척수→대뇌] 현재 {st['current_temp']}도 / 외부 {st['outside_temp']}도 / 인원 {occupancy}")

    # 대뇌(폰 Gemma) 결정
    prompt = build_prompt(desc, user, situation)
    decision = llm_decide(prompt)
    src = decision.get("_source", "?")
    print(f"  [대뇌 결정 · {src}] 목표 {decision['target_temp']}도 / "
          f"예열 {decision.get('preheat_minutes', 0)}분")
    print(f"     이유: {decision.get('reason', '')}")

    # 척수가 명령 적용 + 제어루프 (대뇌는 이제 빠져도 됨)
    hub.apply_command(decision)
    print(f"  [척수 제어루프 시작 — 대뇌 없이 자율 유지]")
    for t in range(max_minutes):
        hub.control_tick()
        hub.room.step(1.0)
        if t % 5 == 0 or abs(hub.room.temp - hub.target_temp) < hub.hysteresis:
            heat = "🔥" if hub.room.heating_on else "  "
            print(f"     t+{t:2d}분 {heat} 실내 {hub.room.temp:5.2f}도 (목표 {hub.target_temp})")
        if abs(hub.room.temp - hub.target_temp) < hub.hysteresis and t > 2:
            print(f"     → 목표 도달 (t+{t}분)")
            break

    # 사용자 수동보정 발생 → 척수가 FEEDBACK 푸시 → 대뇌가 사용자모델 학습
    if manual_override_to is not None:
        print(f"\n  [사용자 수동보정] {hub.target_temp}도 → {manual_override_to}도 손수 올림")
        feedback = {
            "type": "FEEDBACK", "event": "manual_override",
            "from": hub.target_temp, "to": manual_override_to,
            "context_label": situation,
        }
        before = user.cold_sensitive_offset
        user.learn_from_feedback(feedback)
        hub.apply_command({"target_temp": manual_override_to})
        print(f"  [대뇌 학습] 선호 오프셋 {before:+.1f} → {user.cold_sensitive_offset:+.1f}, "
              f"보정기록 {len(user.corrections)}건 누적")

    return decision


def main():
    print("#" * 64)
    print("#  BYOAI 스마트홈 — End-to-End 시뮬레이션")
    print(f"#  대뇌 = 폰의 실제 Gemma 4 ({DECISION_MODEL})")
    print("#" * 64)

    user = UserModel(user_id="hs-2026")

    # === 공간 A: 카페 (비 오는 날, 외풍 있는 큰 공간) ===
    cafe = SpaceHub(
        space_id="cafe-301", place="카페 거실존",
        room=Room(name="cafe", temp=19.5, outside=2.0,
                  heat_rate=0.45, k_loss=0.013),  # 외풍 있지만 난방이 손실은 이김
    )
    run_space_episode(
        cafe, user,
        situation="방금 비 맞고 들어옴, 진입 3분 경과",
        occupancy=1, manual_override_to=26.0,
    )

    # === 공간 B: 친구집 작은방 (전혀 다른 공간, 단열 좋음) — 학습 효과 검증 ===
    friend = SpaceHub(
        space_id="home-villa-2", place="친구집 작은방",
        room=Room(name="villa", temp=20.0, outside=5.0,
                  heat_rate=0.40, k_loss=0.010),
    )
    run_space_episode(
        friend, user,
        situation="외출에서 막 도착, 평상시 상태",
        occupancy=1, manual_override_to=None,
    )

    # 휴대용 사용자모델 저장 (다음 세션/공간으로 이식)
    out = Path(__file__).parent / "user_model.json"
    user.save(out)
    print("\n" + "=" * 64)
    print(f"  휴대용 사용자모델 저장 → {out.name}")
    print(f"  최종 선호 오프셋: +{user.cold_sensitive_offset}도, 학습기록 {len(user.corrections)}건")
    print("  ※ 이 파일이 사용자와 함께 다음 공간으로 이동 = BYOAI 복리 효과")
    print("=" * 64)


if __name__ == "__main__":
    main()
