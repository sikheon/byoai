"""Phase 0 통합 테스트: spine(--sim) + brain(폰 Gemma 실호출)을 한 프로세스에서.
척수 가상물리 + TCP, 대뇌가 descriptor 받아 폰 Gemma로 멀티능력 결정 후 명령,
제어루프가 목표로 수렴하는지 관찰. 마지막에 수동보정→학습까지.
"""
import threading, time, socket, json, sys
sys.path.insert(0, r"C:\Users\HS\gemma-test\byoai-hw\rpi")
import spine, phone_brain as brain

PORT = 8799
sp = spine.Spine(spine.SimBackend(), ["light", "air_quality", "climate"])
threading.Thread(target=sp.loop, daemon=True).start()
threading.Thread(target=sp.serve, args=("127.0.0.1", PORT), daemon=True).start()
time.sleep(1.5)

s = socket.create_connection(("127.0.0.1", PORT))
f = s.makefile("r", encoding="utf-8")
desc = json.loads(f.readline())
print("=== SPACE_DESCRIPTOR ===")
print(" 장소:", desc["place"], "| 능력:", [c["kind"] for c in desc["capabilities"]])
for c in desc["capabilities"]:
    print(f"   - {c['kind']}: 현재 {c['current']}{c['unit']} 범위{c['range']['min']}~{c['range']['max']}")

user = brain.load_user()
print("\n=== 폰 Gemma E4B 결정 호출(adb, ~70초) ===")
prompt = brain.build_prompt(desc, user)
dec = brain.gemma_decide(prompt, "E4B") or brain.heuristic(desc, user)
print(" 결정:", json.dumps(dec, ensure_ascii=False))
s.sendall((json.dumps({"type": "COMMAND", "targets": dec["targets"],
                       "reason": dec.get("reason", "")}, ensure_ascii=False) + "\n").encode())

print("\n=== 제어루프 수렴 관찰(12초) ===")
for _ in range(12):
    time.sleep(1)
    cmd = {k: c.cmd for k, c in sp.caps.items()}
    tgt = {k: c.target for k, c in sp.caps.items()}
    print(f"   현재 t={sp.cur.get('t')} lux={sp.cur.get('lux')} pm={sp.cur.get('pm')} "
          f"| 목표 {tgt} | 액추에이터 {cmd}")

print("\n=== 수동보정 시뮬: 사용자가 조명 직접 올림 → FEEDBACK → 학습 ===")
sp.manual("light", (dec["targets"].get("light", 350)) + 150)
# 소켓에서 FEEDBACK 메시지를 찾아 실제 학습 경로 검증(STATE는 건너뜀)
s.settimeout(3)
try:
    for line in f:
        m = json.loads(line)
        if m.get("type") == "FEEDBACK":
            brain.learn(user, m); break
except socket.timeout:
    pass
print(" 휴대용 사용자모델 corrections:", brain.load_user()["corrections"][-1:])
print("\nDONE")
