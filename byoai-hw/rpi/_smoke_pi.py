#!/usr/bin/env python3
"""Pi 현장 스모크: spine v2 (--sim) 기동 → descriptor → COMMAND(null 포함) → DB 확인."""
import subprocess, socket, json, time, sys, sqlite3, os, glob

for f in glob.glob("smoke_pi.*"): os.remove(f)
p = subprocess.Popen([sys.executable, "spine.py", "--sim", "--config", "smoke_pi.json", "--tcp", "8790"],
                     stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                     text=True)
time.sleep(2.5)
if p.poll() is not None:
    print("DIED:\n" + p.communicate()[0]); sys.exit(1)
try:
    s = socket.create_connection(("127.0.0.1", 8790), 3)
    f = s.makefile("r", encoding="utf-8")
    d = json.loads(f.readline())
    print("1 DESC:", d["space_id"], [c["kind"] for c in d["capabilities"]])
    s.sendall((json.dumps({"type": "COMMAND", "targets": {"light": 350, "air_quality": None}, "reason": "pi-smoke"}) + "\n").encode())
    time.sleep(2.5)
    st = None
    for _ in range(8):
        m = json.loads(f.readline())
        if m["type"] == "STATE": st = m
    sm = {c["kind"]: (c["current"], c["target"], c["actuator"]) for c in st["caps"]}
    print("2 STATE:", sm)
    assert sm["air_quality"][1] is None and sm["air_quality"][2] == 0
    assert sm["light"][1] == 350
    s.close(); time.sleep(5)
finally:
    p.terminate(); time.sleep(1)
db = sqlite3.connect("smoke_pi.db")
print("3 DB devices:", db.execute("SELECT id FROM devices").fetchall(),
      "telemetry:", db.execute("SELECT COUNT(*) FROM telemetry").fetchone()[0])
db.close()
for f in glob.glob("smoke_pi.*"): os.remove(f)
print("PI ALL PASS")
