#!/usr/bin/env python3
"""BYOAI 대뇌(brain) 브릿지 — 폰의 Gemma 4를 adb로 대리 호출.

척수(spine.py)에 TCP로 접속 → SPACE_DESCRIPTOR 수신 → 멀티 능력 + 휴대용
사용자모델을 결합한 프롬프트 작성 → 폰 Gemma가 능력별 목표값 결정(JSON) →
COMMAND 전송. 척수가 보내는 FEEDBACK(수동보정)은 휴대용 사용자모델에 학습.

  python phone_brain.py --host <RPi주소> --model E4B
모델 미가용 시 heuristic 폴백. 휴대용 모델은 user_model.json에 누적(공간 이동 이식).
"""
from __future__ import annotations
import argparse, hashlib, json, re, shutil, socket, subprocess, sys
from pathlib import Path

ADB = shutil.which("adb") or r"C:\Users\HS\Downloads\platform-tools-latest-windows\platform-tools\adb.exe"
DEVICE_DIR = "/data/local/tmp/llama"
MODELS = {"E2B": "gemma-4-E2B-it-Q4_K_M.gguf", "E4B": "gemma-4-E4B-it-Q4_K_M.gguf"}
HERE = Path(__file__).parent
USER_MODEL = HERE / "user_model.json"


# ───────── 휴대용 사용자모델 (폰에 들고 다님) ─────────
def load_user():
    if USER_MODEL.exists():
        return json.loads(USER_MODEL.read_text(encoding="utf-8"))
    return {"user_id": "hs-2026", "prefs": {"climate_offset": 2.0,
            "light_pref": 350, "air_max": 40}, "corrections": []}

def save_user(u):
    USER_MODEL.write_text(json.dumps(u, ensure_ascii=False, indent=2), encoding="utf-8")

def learn(u, fb):
    delta = (fb.get("to") or 0) - (fb.get("from") or 0)
    u["corrections"].append({"capability": fb.get("capability"),
                             "context": fb.get("context_label"), "delta": delta})
    if fb.get("capability") == "climate" and abs(delta) >= 1.0:
        u["prefs"]["climate_offset"] += 0.5 * (1 if delta > 0 else -1)
    if fb.get("capability") == "light" and fb.get("to"):
        u["prefs"]["light_pref"] = fb["to"]
    save_user(u)
    print(f"  [학습] {fb.get('capability')} 보정 {delta:+.0f} → 휴대용 모델 갱신")


# ───────── 프롬프트 + Gemma(adb) ─────────
def build_prompt(desc, user):
    lines = [f"너는 BYOAI 스마트홈의 의사결정 AI다. 공간 능력과 사용자 선호를 결합해 "
             f"각 능력의 목표값을 정하라. 반드시 JSON 하나만 출력.", "",
             f"[공간] {desc['place']} / 외부 {desc.get('outside_temp')}도 / "
             f"재실 {desc['occupancy'].get('present')}", "[능력]"]
    for c in desc["capabilities"]:
        lines.append(f"- {c['kind']}: 현재 {c['current']}{c['unit']} "
                     f"(범위 {c['range']['min']}~{c['range']['max']}), 학습모델 {c['learned_model']}")
    p = user["prefs"]
    lines += ["", "[사용자 휴대 선호]",
              f"- 추위민감 오프셋 +{p['climate_offset']}도, 조명선호 {p['light_pref']}lux, 공기질 상한 {p['air_max']}",
              f"- 최근 보정 {user['corrections'][-3:]}", "",
              '[출력] JSON만: {"targets":{"climate":숫자,"light":숫자,"air_quality":숫자},"reason":"한문장"}']
    return "\n".join(lines)

def _extract_targets(text):
    """균형 중괄호로 최상위 {...} 후보를 모아, "targets" 포함하고 파싱되는
    마지막 것을 반환. 대화모드가 에코한 프롬프트 예시(숫자=한글)는 자동 탈락."""
    objs, depth, start = [], 0, -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0: start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0:
                objs.append(text[start:i + 1])
    for cand in reversed(objs):
        try:
            o = json.loads(cand)
            if isinstance(o.get("targets"), dict):
                return o
        except Exception:
            continue
    return None


def gemma_decide(prompt, model_key):
    model = MODELS[model_key]
    lp = HERE / "_brain_prompt.txt"; lp.write_text(prompt, encoding="utf-8")
    try:
        subprocess.run([ADB, "push", str(lp), f"{DEVICE_DIR}/_brain_prompt.txt"],
                       capture_output=True, timeout=30)
        cmd = (f"cd {DEVICE_DIR} && LD_LIBRARY_PATH={DEVICE_DIR} "
               f"timeout 150 ./llama-cli -m {model} -f _brain_prompt.txt "
               f"-n 200 -t 4 --temp 0.3 -rea off 2>/dev/null")
        res = subprocess.run([ADB, "shell", cmd], input="/exit\n",
                             capture_output=True, text=True, timeout=200,
                             encoding="utf-8", errors="replace")
        o = _extract_targets(res.stdout or "")
        if o:
            o["_source"] = f"gemma:{model_key}"; return o
    except Exception as e:
        print(f"  [Gemma 호출 실패: {e}] heuristic")
    return None

def heuristic(desc, user):
    p = user["prefs"]; tg = {}
    for c in desc["capabilities"]:
        if c["kind"] == "climate": tg["climate"] = 21 + p["climate_offset"]
        elif c["kind"] == "light": tg["light"] = p["light_pref"]
        elif c["kind"] == "air_quality": tg["air_quality"] = p["air_max"]
    return {"targets": tg, "reason": "휴대 선호 기반(폴백)", "_source": "heuristic"}


# ───────── 메인 루프 ─────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1"); ap.add_argument("--tcp", type=int, default=8765)
    ap.add_argument("--model", default="E4B", choices=list(MODELS))
    a = ap.parse_args()
    user = load_user()
    s = socket.create_connection((a.host, a.tcp))
    f = s.makefile("r", encoding="utf-8")
    print(f"  [대뇌] 척수 {a.host}:{a.tcp} 접속, 모델 {a.model}")
    for line in f:
        line = line.strip()
        if not line: continue
        msg = json.loads(line)
        if msg.get("type") == "SPACE_DESCRIPTOR":
            print(f"\n  [공간 진입] {msg['place']} — 능력 {[c['kind'] for c in msg['capabilities']]}")
            prompt = build_prompt(msg, user)
            dec = gemma_decide(prompt, a.model) or heuristic(msg, user)
            print(f"  [대뇌 결정·{dec.get('_source')}] {dec['targets']}  이유: {dec.get('reason','')}")
            s.sendall((json.dumps({"type": "COMMAND", "targets": dec["targets"],
                                   "reason": dec.get("reason", "")}, ensure_ascii=False) + "\n").encode())
        elif msg.get("type") == "FEEDBACK":
            learn(user, msg)
        # STATE 메시지는 조용히 무시(원하면 로깅)
    print("연결 종료.")


if __name__ == "__main__":
    main()
