#!/usr/bin/env python3
"""BYOAI 척수(spine) — 라즈베리파이에서 실행.

멀티 능력(climate/light/air_quality)을 센서로 파악하고, 폰(대뇌) 명령대로
액추에이터를 제어루프로 유지하며, 각 능력의 응답모델을 자가학습한다.
폰과는 TCP 줄단위 JSON으로 통신(SPACE_DESCRIPTOR / COMMAND / STATE / FEEDBACK).

  실HW:  python spine.py --port /dev/ttyUSB0        # 실센서+sim 채움(Hybrid, D-6)
  무HW:  python spine.py --sim                       # Arduino 없이 가상 물리(Phase 0)
  박스2: python spine.py --port /dev/ttyUSB1 --tcp 8766 --config space_b.json --mdns

공간 정체성은 space_config.json(첫 실행 시 자동생성)에. 저장은 SQLite(<config>.db):
  devices / telemetry / learned_models  — 재기동 시 기기·학습모델 복원.
수동보정(사용자가 직접 액추에이터 조작) 테스트: 콘솔에 `light=450` 처럼 입력.
"""
from __future__ import annotations
import argparse, json, os, socket, sqlite3, threading, time, uuid
from collections import deque

TICK = 1.0                   # 제어/학습 주기(초)
MODEL_SAVE_EVERY = 30        # 학습모델 DB 저장 주기(틱)
TYPICAL_REFRESH = 120        # 시간대 평소값 재집계 주기(틱)
SENSOR_TO_KIND = {"lux": "light", "pm": "air_quality", "t": "climate"}


# ───────────────────────── 공간 정체성 (space_config.json) ─────────────────────────
def load_space_config(path: str) -> dict:
    """공간 정체성 로드. 없으면 MAC 기반 space_id로 자동생성(박스별 충돌 방지)."""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    cfg = {"space_id": f"spine-{uuid.getnode() & 0xFFFFFF:06x}",
           "place": "테스트 미니룸", "outside_temp": 18.0}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f"  [공간] {path} 자동생성 — space_id={cfg['space_id']} (place는 파일에서 수정)")
    return cfg


# ───────────────────────── SQLite 저장 (devices/telemetry/learned_models) ─────────
class Store:
    def __init__(self, path: str):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS devices(
                id TEXT PRIMARY KEY, kind TEXT, capability_json TEXT, added_at REAL);
            CREATE TABLE IF NOT EXISTS telemetry(
                ts REAL, device_id TEXT, metric TEXT, value REAL);
            CREATE TABLE IF NOT EXISTS learned_models(
                device_id TEXT PRIMARY KEY, model_json TEXT, updated_at REAL);
        """)
        self.lock = threading.Lock()
        self._pending = 0

    def register_device(self, dev_id: str, kind: str, cap_json: dict) -> bool:
        """기기 온보딩. 신규면 True(announce→INSERT)."""
        with self.lock:
            cur = self.db.execute(
                "INSERT OR IGNORE INTO devices VALUES(?,?,?,?)",
                (dev_id, kind, json.dumps(cap_json, ensure_ascii=False), time.time()))
            self.db.commit()
            return cur.rowcount > 0

    def load_devices(self) -> list[tuple[str, str]]:
        with self.lock:
            return self.db.execute("SELECT id, kind FROM devices").fetchall()

    def telemetry(self, dev_id: str, metric: str, value):
        if value is None: return
        with self.lock:
            self.db.execute("INSERT INTO telemetry VALUES(?,?,?,?)",
                            (time.time(), dev_id, metric, float(value)))
            self._pending += 1
            if self._pending >= 10:           # 배치 커밋(SD카드 보호)
                self.db.commit(); self._pending = 0

    def save_model(self, dev_id: str, model: dict):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO learned_models VALUES(?,?,?)",
                            (dev_id, json.dumps(model), time.time()))
            self.db.commit()

    def load_model(self, dev_id: str) -> dict | None:
        with self.lock:
            row = self.db.execute("SELECT model_json FROM learned_models WHERE device_id=?",
                                  (dev_id,)).fetchone()
        return json.loads(row[0]) if row else None

    # --- 공간 특성: 시간대별 평소값 (텔레메트리 누적 → 공간의 자기지식) ---
    def typical_now(self, dev_id: str, metric: str, min_samples=60) -> float | None:
        """이 공간의 '지금 이 시간대' 평소값 (최근 7일, 같은 시(hour) 평균)."""
        hour = time.localtime().tm_hour
        with self.lock:
            row = self.db.execute(
                "SELECT ROUND(AVG(value),1), COUNT(*) FROM telemetry "
                "WHERE device_id=? AND metric=? AND ts>? "
                "AND CAST(strftime('%H', ts, 'unixepoch', 'localtime') AS INTEGER)=?",
                (dev_id, metric, time.time() - 7 * 86400, hour)).fetchone()
        return row[0] if row and row[1] >= min_samples else None

    def hourly_profile(self) -> dict:
        """metric → {시간대: 평균} (최근 7일). 폰이 공간 성격 파악용으로 읽음."""
        with self.lock:
            rows = self.db.execute(
                "SELECT metric, CAST(strftime('%H', ts, 'unixepoch', 'localtime') AS INTEGER) h, "
                "ROUND(AVG(value),1) FROM telemetry WHERE ts>? GROUP BY metric, h "
                "HAVING COUNT(*)>=60", (time.time() - 7 * 86400,)).fetchall()
        prof: dict = {}
        for metric, h, avg in rows:
            prof.setdefault(metric, {})[str(h)] = avg
        return prof


# ───────────────────────── 능력(capability) ─────────────────────────
def _slope(samples, want_act):
    """act 상태가 want_act인 연속구간들의 (값 변화/시간) 평균 기울기[/분]."""
    num = den = 0.0
    for (t0, v0, a0), (t1, v1, a1) in zip(samples, list(samples)[1:]):
        if a0 == want_act and v0 is not None and v1 is not None and t1 > t0:
            num += (v1 - v0); den += (t1 - t0)
    return (num / den * 60.0) if den else 0.0


class Capability:
    kind = "base"; sensor = ""; actuator = ""; unit = ""; vmin = 0; vmax = 0
    def __init__(self):
        self.target = None
        self.cmd = 0
        self.samples = deque(maxlen=300)
        self.restored = None              # DB에서 복원한 과거 학습모델
        self.typical = None               # 이 시간대 평소값(공간 특성, DB 집계)
    def control(self, cur):               # 현재값 → 액추에이터 명령값
        return 0
    def record(self, cur, now):
        self.samples.append((now, cur, self.cmd))
    def _live_model(self):
        return {}
    def learned_model(self):
        """현 세션 학습이 복원본보다 미숙하면 복원본 사용(재기동 복원)."""
        live = self._live_model()
        if self.restored and live.get("confidence", 0) < self.restored.get("confidence", 0):
            return self.restored
        return live
    def state_block(self, cur):
        return {"id": f"{self.kind}-1", "kind": self.kind, "unit": self.unit,
                "range": {"min": self.vmin, "max": self.vmax},
                "current": (round(cur, 1) if cur is not None else None),
                "target": self.target, "actuator": self.cmd,
                "typical_now": self.typical,
                "learned_model": self.learned_model()}


class Climate(Capability):
    kind="climate"; sensor="t"; actuator="heater"; unit="°C"; vmin=18; vmax=30
    hyst = 0.3
    def control(self, cur):
        if self.target is None or cur is None: return self.cmd
        if cur < self.target - self.hyst: self.cmd = 1
        elif cur > self.target + self.hyst: self.cmd = 0
        return self.cmd
    def _live_model(self):
        return {"heat_rate_c_per_min": round(_slope(self.samples, 1), 3),
                "cool_rate_c_per_min": round(-_slope(self.samples, 0), 3),
                "confidence": min(1.0, len(self.samples) / 120)}


class Light(Capability):
    kind="light"; sensor="lux"; actuator="light"; unit="lux"; vmin=0; vmax=1000
    def control(self, cur):               # 비례제어 (PWM 0~255)
        if self.target is None or cur is None: return self.cmd
        err = self.target - cur
        # 약한 P(0.1) + 슬루 제한(±20/틱): 박스처럼 결합이 센 환경에서 발진 방지, 스르륵 수렴
        step = max(-20.0, min(20.0, 0.1 * err))
        self.cmd = int(max(0, min(255, self.cmd + step)))
        return self.cmd
    def _live_model(self):
        # PWM당 lux — 조명 효율(공간의 광학 응답) 근사
        pts = [v / a for (_, v, a) in self.samples if a and v is not None]
        return {"lux_per_pwm": (round(sum(pts) / len(pts), 2) if pts else None),
                "pwm_max": 255, "confidence": min(1.0, len(self.samples) / 60)}


class AirQuality(Capability):
    kind="air_quality"; sensor="pm"; actuator="fan"; unit="µg/m³"; vmin=0; vmax=200
    def control(self, cur):               # 목표(상한) 초과면 팬 ON. 목표 없음=정지.
        if self.target is None: self.cmd = 0; return self.cmd
        if cur is None: return self.cmd
        self.cmd = 1 if cur > self.target else 0
        return self.cmd
    def _live_model(self):
        return {"clear_rate_per_min": round(-_slope(self.samples, 1), 3),
                "confidence": min(1.0, len(self.samples) / 120)}


CAP_CLASSES = {"climate": Climate, "light": Light, "air_quality": AirQuality}


# ───────────────────────── 물리 백엔드 ─────────────────────────
class SerialBackend:
    """실제 Arduino: 시리얼로 텔레메트리 수신 / 액추에이터 명령 송신."""
    def __init__(self, port, baud=115200):
        import serial  # pyserial
        self.ser = serial.Serial(port, baud, timeout=1)
        self.latest = {}
        threading.Thread(target=self._reader, daemon=True).start()
    def _reader(self):
        while True:
            line = self.ser.readline().decode("utf-8", "replace").strip()
            if line.startswith("{"):
                try: self.latest.update(json.loads(line))
                except Exception: pass
    def read(self): return dict(self.latest)
    def write(self, cmd: dict):
        self.ser.write((json.dumps(cmd) + "\n").encode())


class NodeTCPBackend:
    """무선 말단(ESP32 등): WiFi/TCP 줄단위 JSON — 시리얼과 동일 프로토콜, 전송만 무선.
    말단이 이 포트(기본 8766)로 접속해 텔레메트리를 쏘고 명령을 받는다."""
    def __init__(self, port=8766, host="0.0.0.0"):
        self.latest = {}
        self.conn = None
        self.lock = threading.Lock()
        threading.Thread(target=self._serve, args=(host, port), daemon=True).start()
    def _serve(self, host, port):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, port)); srv.listen(1)
        print(f"  [말단] 무선 노드 대기 TCP:{port}")
        while True:
            c, addr = srv.accept()
            with self.lock:
                old, self.conn = self.conn, c
            if old:
                try: old.close()
                except Exception: pass
            print(f"  [말단] 무선 노드 접속 {addr[0]}")
            try:
                for line in c.makefile("r", encoding="utf-8"):
                    line = line.strip()
                    if line.startswith("{"):
                        try: self.latest.update(json.loads(line))
                        except Exception: pass
            except Exception: pass
            with self.lock:
                if self.conn is c: self.conn = None
            print("  [말단] 무선 노드 끊김 — 재접속 대기")
    def read(self): return dict(self.latest)
    def write(self, cmd: dict):
        with self.lock:
            if not self.conn: return
            try: self.conn.sendall((json.dumps(cmd) + "\n").encode())
            except Exception: self.conn = None


class SimBackend:
    """무HW 가상 물리(Phase 0): 명령에 반응하는 단순 모델."""
    def __init__(self, outside_temp=18.0):
        self.outside = outside_temp
        self.t = 19.5; self.lux = 80; self.pm = 90; self.pir = 1
        self.cmd = {"heater": 0, "light": 0, "fan": 0}
    def read(self):
        c = self.cmd
        # 온도: 히터 RC, 조도: PWM 비례, 미세먼지: 팬 제거/자연증가
        self.t += (0.45 if c.get("heater") else 0.0) - 0.013 * (self.t - self.outside)
        self.lux += 0.6 * (c.get("light", 0) * 1000 / 255 - self.lux) / 1.0 * TICK
        self.pm += (-6 if c.get("fan") else 1.2)
        self.pm = max(5, self.pm)
        return {"t": round(self.t, 2), "h": 45.0,
                "lux": int(max(0, self.lux)), "pm": int(self.pm), "pir": self.pir}
    def write(self, cmd: dict):
        self.cmd.update(cmd)


class HybridBackend:
    """실센서(시리얼/무선)는 진짜, 미보유 센서는 sim 물리로 채움 — D-6.
    명령은 양쪽 모두 → 실물(LED·팬)은 실제로 켜지고, sim 물리는 그에 반응.
    fill_keys: sim이 공급할 키 제한 — 비활성 능력이 자동온보딩으로 부활하는 것 방지."""
    def __init__(self, real, outside_temp=18.0, fill_keys=None):
        self.serial = real                # 시리얼이든 무선 노드든 동일 인터페이스
        self.sim = SimBackend(outside_temp)
        self.fill = fill_keys
    def read(self):
        data = self.sim.read()            # sim 물리 1틱 진행
        if self.fill is not None:
            data = {k: v for k, v in data.items() if k in self.fill}
        data.update(self.serial.read())   # 실측 키(lux·pir 등)가 있으면 덮어씀
        return data
    def write(self, cmd: dict):
        self.serial.write(cmd); self.sim.write(cmd)


# ───────────────────────── 척수 본체 ─────────────────────────
class Spine:
    def __init__(self, backend, kinds, cfg: dict, store: Store):
        self.backend = backend
        self.cfg = cfg
        self.store = store
        self.caps: dict[str, Capability] = {}
        self.clients = set()
        self.lock = threading.Lock()
        self.cur = {}
        # DB에 등록된 기기 ∪ --caps → 재기동 시 descriptor 복원
        for dev_id, kind in store.load_devices():
            if kind in CAP_CLASSES: kinds = list(kinds) + [kind]
        for k in dict.fromkeys(kinds):    # 순서 보존 중복 제거
            self._add_capability(k, announce=False)

    def _add_capability(self, kind: str, announce=True):
        if kind not in CAP_CLASSES or kind in self.caps: return
        cap = CAP_CLASSES[kind]()
        cap.restored = self.store.load_model(f"{kind}-1")
        self.caps[kind] = cap
        new = self.store.register_device(f"{kind}-1", kind, cap.state_block(None))
        if new or announce:
            print(f"  [온보딩] 능력 '{kind}' {'자동추가' if announce else '등록'} → DB")
        if announce:                      # 연결된 폰에 새 기기 즉시 반영
            self.broadcast(self.descriptor())

    # --- SPACE_DESCRIPTOR 생성 ---
    def descriptor(self):
        caps = [c.state_block(self.cur.get(c.sensor)) for c in self.caps.values()]
        occ = self.cur.get("pir", 1)
        return {"type": "SPACE_DESCRIPTOR", "space_id": self.cfg["space_id"],
                "place": self.cfg["place"], "outside_temp": self.cfg.get("outside_temp"),
                "capabilities": caps, "occupancy": {"present": bool(occ)},
                "profile": self.store.hourly_profile()}   # 시간대별 평소값(공간 특성)

    # --- 폰 명령 적용 (target=null → 해당 능력 정지: 앱 공기질 토글 OFF) ---
    def apply_command(self, msg):
        for kind, val in (msg.get("targets") or {}).items():
            if kind in self.caps:
                self.caps[kind].target = (None if val is None else float(val))

    # --- 제어 + 학습 + 저장 루프 ---
    def loop(self):
        tick = 0
        while True:
            self.cur = self.backend.read()
            # 외기 실측(t_out, 박스 밖 DHT): 고정 외기값 대체 + sim 열물리 기준 갱신
            if "t_out" in self.cur:
                self.cfg["outside_temp"] = self.cur["t_out"]
                sim = getattr(self.backend, "sim", None)
                if sim: sim.outside = self.cur["t_out"]
            # 텔레메트리 키 → 능력 자동 온보딩(announce: 처음 보는 센서가 나타나면)
            for key, kind in SENSOR_TO_KIND.items():
                if key in self.cur and kind not in self.caps:
                    self._add_capability(kind)
            cmd = {}
            now = time.time()
            for c in self.caps.values():
                cur = self.cur.get(c.sensor)
                cmd[c.actuator] = c.control(cur)
                c.record(cur, now)
                self.store.telemetry(f"{c.kind}-1", c.sensor, cur)
            self.backend.write(cmd)
            self.broadcast({"type": "STATE", "t": now,
                            "caps": [c.state_block(self.cur.get(c.sensor))
                                     for c in self.caps.values()]})
            tick += 1
            if tick % MODEL_SAVE_EVERY == 0:  # 학습모델 영속화
                for c in self.caps.values():
                    m = c.learned_model()
                    if m.get("confidence"): self.store.save_model(f"{c.kind}-1", m)
            if tick % TYPICAL_REFRESH == 1:   # 시간대 평소값 갱신(공간 특성)
                for c in self.caps.values():
                    c.typical = self.store.typical_now(f"{c.kind}-1", c.sensor)
            time.sleep(TICK)

    # --- 수동보정(콘솔/트윈 = 현장에서 직접 조작) → FEEDBACK(학습신호) ---
    def manual(self, kind, value):
        if kind not in self.caps: return
        c = self.caps[kind]
        before = c.target
        c.target = None if value is None else float(value)
        self.broadcast({"type": "FEEDBACK", "event": "manual_override",
                        "capability": kind, "from": before, "to": c.target,
                        "context_label": f"{self.cfg['place']} 수동조작"})
        print(f"  [FEEDBACK] {kind}: {before} → {c.target} (폰 사용자모델로 학습 신호)")

    # --- TCP ---
    def broadcast(self, obj):
        data = (json.dumps(obj, ensure_ascii=False) + "\n").encode()
        with self.lock:
            dead = []
            for cl in self.clients:
                try: cl.sendall(data)   # 소켓별 5초 타임아웃(accept 시 설정) — 잠든 폰이 전체를 못 멈추게
                except Exception: dead.append(cl)
            for d in dead:
                self.clients.discard(d)
                print(f"  [클라] 송신실패로 제거 (남은 {len(self.clients)})")
                try: d.close()          # close까지 해야 상대 리더가 EOF 받고 재접속함
                except Exception: pass

    def serve(self, host, port):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((host, port)); srv.listen()
        print(f"  [척수] TCP {host}:{port} 대기 (공간: {self.cfg['space_id']}, 능력: {list(self.caps)})")
        while True:
            cl, addr = srv.accept()
            print(f"  [클라] 접속 {addr[0]}:{addr[1]}")
            cl.settimeout(5)            # 송신 블록 방지 (수신은 _client의 makefile이 별도)
            with self.lock: self.clients.add(cl)
            try:
                cl.sendall((json.dumps(self.descriptor(), ensure_ascii=False) + "\n").encode())
            except Exception:
                with self.lock: self.clients.discard(cl)
                continue
            threading.Thread(target=self._client, args=(cl,), daemon=True).start()

    def _client(self, cl):
        # ⚠ makefile 금지: 소켓 타임아웃 후 버퍼 객체가 오염됨("cannot read from timed out object")
        #   → recv 기반 수동 라인 파서 (타임아웃 안전)
        buf = b""
        while True:
            try:
                chunk = cl.recv(4096)
            except socket.timeout:
                continue               # 수신 침묵은 정상 (타임아웃은 송신 블록 방지용)
            except Exception as e:
                print(f"  [클라] 수신오류로 종료: {type(e).__name__} {e}")
                break
            if not chunk:              # EOF = 클라이언트 종료
                print("  [클라] EOF — 상대가 끊음")
                break
            buf += chunk
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                line = raw.decode("utf-8", "replace").strip()
                if not line: continue
                self._handle(line)
        with self.lock: self.clients.discard(cl)

    def _handle(self, line: str):
        try: msg = json.loads(line)
        except Exception: return
        if msg.get("type") == "COMMAND":
            self.apply_command(msg)
            tgt = {k: v.target for k, v in self.caps.items()}
            print(f"  [명령 수신] 목표 {tgt}  이유: {msg.get('reason','')}")
            # 관측성: 결정 도착을 모든 클라이언트(트윈 등)에 재방송
            self.broadcast({"type": "EVENT", "event": "command", "t": time.time(),
                            "targets": msg.get("targets"), "reason": msg.get("reason", "")})
        elif msg.get("type") == "MANUAL":   # 트윈 = 가상 룸 현장조작 → 학습신호 생성
            self.manual(msg.get("capability"), msg.get("value"))


def start_mdns(port, kinds, cfg):
    """라파이를 '_byoai._tcp'로 광고 → 폰/클라이언트가 자동 발견(기기 자동추가)."""
    try:
        from zeroconf import Zeroconf, ServiceInfo
    except ImportError:
        print("  [mDNS] zeroconf 미설치 — `apt install python3-zeroconf` (디스커버리 생략)")
        return None
    # gethostbyname(hostname)은 데비안서 127.0.1.1 반환 함정 → 아웃바운드 소켓으로 실제 LAN IP
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80)); ip = probe.getsockname()[0]; probe.close()
    except OSError:
        ip = socket.gethostbyname(socket.gethostname())
    sid, place = cfg["space_id"], cfg["place"]
    info = ServiceInfo(
        "_byoai._tcp.local.", f"{sid}._byoai._tcp.local.",
        addresses=[socket.inet_aton(ip)], port=port,
        properties={b"space_id": sid.encode(), b"place": place.encode("utf-8"),
                    b"caps": ",".join(kinds).encode(), b"v": b"1"},
        server=f"{sid}.local.")
    zc = Zeroconf(); zc.register_service(info)
    print(f"  [mDNS] '_byoai._tcp' 광고 @ {ip}:{port} (place={place}) — 폰이 자동 발견")
    return zc


def main():
    try:
        import sys; sys.stdout.reconfigure(line_buffering=True)  # nohup 로그 즉시 보이게
    except Exception: pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", help="Arduino 시리얼 포트 (예: /dev/ttyUSB0, COM5) — Hybrid(실센서+sim채움)")
    ap.add_argument("--node", nargs="?", const=8766, type=int, metavar="PORT",
                    help="무선 말단(ESP32) TCP 수신 (기본 8766) — Hybrid(실센서+sim채움)")
    ap.add_argument("--sim", action="store_true", help="무HW 가상 물리 모드")
    ap.add_argument("--no-fill", action="store_true", help="sim 채움 없이 실측만")
    ap.add_argument("--caps", default="light,air_quality,climate",
                    help="활성 능력(쉼표): light,air_quality,climate")
    ap.add_argument("--config", default="space_config.json", help="공간 정체성 파일(박스별로 분리)")
    ap.add_argument("--host", default="0.0.0.0"); ap.add_argument("--tcp", type=int, default=8765)
    ap.add_argument("--mdns", action="store_true", help="mDNS 광고(자동 기기추가)")
    a = ap.parse_args()
    cfg = load_space_config(a.config)
    store = Store(os.path.splitext(a.config)[0] + ".db")
    out_t = cfg.get("outside_temp", 18.0)
    kinds = [k.strip() for k in a.caps.split(",") if k.strip() in CAP_CLASSES]
    if a.sim:        backend = SimBackend(out_t)
    else:
        if a.port:   real = SerialBackend(a.port)
        elif a.node: real = NodeTCPBackend(a.node)
        else:        ap.error("--port, --node 또는 --sim 필요")
        fill = {CAP_CLASSES[k].sensor for k in kinds} | {"pir"}   # 활성 능력 센서만 sim 채움
        backend = real if a.no_fill else HybridBackend(real, outside_temp=out_t, fill_keys=fill)
    sp = Spine(backend, kinds, cfg, store)
    threading.Thread(target=sp.loop, daemon=True).start()
    threading.Thread(target=sp.serve, args=(a.host, a.tcp), daemon=True).start()
    zc = start_mdns(a.tcp, list(sp.caps), cfg) if a.mdns else None
    print("  콘솔에 'light=450' 처럼 입력하면 수동보정(FEEDBACK) 테스트. Ctrl+C 종료.")
    try:
        while True:
            s = input().strip()
            if "=" in s:
                k, v = s.split("=", 1); sp.manual(k.strip(), v.strip())
    except EOFError:
        while True: time.sleep(3600)   # 헤드리스 서비스: 입력 없이 계속 서빙
    except KeyboardInterrupt:
        print("\n종료.")
    finally:
        if zc: zc.close()


if __name__ == "__main__":
    main()
