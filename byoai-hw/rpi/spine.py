#!/usr/bin/env python3
"""
BYOAI spine v1 — Raspberry Pi gateway (in-memory).

The "spine": owns the physics of a space. Holds live capability state in a
plain dict, talks line-JSON over TCP (port 8765) to phones, and line-JSON over
serial (115200) to the Arduino node. No persistence yet — restart loses state.

Capabilities exposed in v1: light, air_quality, climate.
(Climate later removed once we committed to the heater-less box, and the whole
store moved to SQLite — see spine v2.)
"""
import json
import socket
import threading
import time

HOST = "0.0.0.0"
PORT = 8765
SERIAL_PORT = "/dev/ttyACM0"
BAUD = 115200

try:
    import serial  # pyserial
except Exception:
    serial = None


# ---------------------------------------------------------------- capabilities
class Capability:
    kind = "generic"

    def __init__(self, cid):
        self.cid = cid
        self.state = {}

    def snapshot(self):
        return {"id": self.cid, "kind": self.kind, "state": dict(self.state)}


class Light(Capability):
    kind = "light"

    def __init__(self, cid="light0"):
        super().__init__(cid)
        self.state = {"lux": 0.0, "duty": 0, "target": None, "source": "auto"}

    def apply(self, target):
        self.state["target"] = target
        self.state["source"] = "auto"

    def manual(self, duty):
        self.state["duty"] = duty
        self.state["source"] = "manual"


class AirQuality(Capability):
    kind = "air_quality"

    def __init__(self, cid="air0"):
        super().__init__(cid)
        self.state = {"dust": 0.0, "grade": "unknown"}

    def grade_of(self, dust):
        if dust < 30:
            return "good"
        if dust < 80:
            return "normal"
        return "bad"


class Climate(Capability):
    """v1 only — heater/cooler abstraction. Removed in v2."""
    kind = "climate"

    def __init__(self, cid="clim0"):
        super().__init__(cid)
        self.state = {"t": 0.0, "h": 0.0, "target_t": 23.0, "heat": 0, "source": "auto"}

    def apply(self, target_t):
        self.state["target_t"] = target_t
        # crude bang-bang: heat on when below target
        self.state["heat"] = 1 if self.state["t"] < target_t else 0
        self.state["source"] = "auto"

    def manual(self, target_t):
        self.state["target_t"] = target_t
        self.state["source"] = "manual"


class Spine:
    def __init__(self):
        self.caps = {
            "light0": Light(),
            "air0": AirQuality(),
            "clim0": Climate(),
        }
        self.clients = []
        self.lock = threading.Lock()
        self.ser = None

    # ---- serial (Arduino telemetry) ----
    def open_serial(self):
        if serial is None:
            print("[spine] pyserial missing; running sim telemetry")
            return
        try:
            self.ser = serial.Serial(SERIAL_PORT, BAUD, timeout=1)
            print("[spine] serial open", SERIAL_PORT)
        except Exception as e:
            print("[spine] serial fail:", e)
            self.ser = None

    def serial_loop(self):
        while True:
            if self.ser is None:
                self._sim_tick()
                time.sleep(1.0)
                continue
            try:
                line = self.ser.readline().decode("utf-8", "ignore").strip()
            except Exception:
                line = ""
            if not line:
                continue
            try:
                msg = json.loads(line)
            except Exception:
                continue
            self.ingest(msg)

    def _sim_tick(self):
        # very rough simulated environment when no Arduino present
        light = self.caps["light0"]
        clim = self.caps["clim0"]
        light.state["lux"] = 300 + (light.state["duty"] * 2.5)
        if clim.state["heat"]:
            clim.state["t"] = min(26.0, clim.state["t"] + 0.2)
        else:
            clim.state["t"] = max(18.0, clim.state["t"] - 0.1)
        self.broadcast()

    def ingest(self, msg):
        with self.lock:
            if "lux" in msg:
                self.caps["light0"].state["lux"] = float(msg["lux"])
            if "dust" in msg:
                air = self.caps["air0"]
                air.state["dust"] = float(msg["dust"])
                air.state["grade"] = air.grade_of(air.state["dust"])
            if "t" in msg:
                self.caps["clim0"].state["t"] = float(msg["t"])
            if "h" in msg:
                self.caps["clim0"].state["h"] = float(msg["h"])
        self.broadcast()

    def write_serial(self, obj):
        if self.ser is None:
            return
        try:
            self.ser.write((json.dumps(obj) + "\n").encode())
        except Exception as e:
            print("[spine] serial write fail:", e)

    # ---- TCP (phone) ----
    def state_msg(self):
        with self.lock:
            return {
                "type": "STATE",
                "caps": [c.snapshot() for c in self.caps.values()],
                "ts": int(time.time()),
            }

    def broadcast(self):
        data = (json.dumps(self.state_msg()) + "\n").encode()
        dead = []
        for cl in list(self.clients):
            try:
                cl.sendall(data)
            except Exception:
                dead.append(cl)
        for d in dead:
            try:
                self.clients.remove(d)
                d.close()
            except Exception:
                pass

    def handle(self, msg):
        t = msg.get("type")
        if t == "COMMAND":
            cid = msg.get("target")
            cap = self.caps.get(cid)
            if isinstance(cap, Light) and "duty" in msg:
                cap.apply(msg.get("duty"))
                self.write_serial({"light": msg["duty"]})
            elif isinstance(cap, Climate) and "target_t" in msg:
                cap.apply(float(msg["target_t"]))
                self.write_serial({"heat": cap.state["heat"]})
        elif t == "MANUAL":
            cid = msg.get("target")
            cap = self.caps.get(cid)
            if isinstance(cap, Light):
                cap.manual(msg.get("duty", 0))
            elif isinstance(cap, Climate):
                cap.manual(float(msg.get("target_t", 23.0)))
        self.broadcast()

    def client_loop(self, conn):
        conn.sendall((json.dumps(self.state_msg()) + "\n").encode())
        buf = b""
        for line in conn.makefile("r"):
            line = line.strip()
            if not line:
                continue
            try:
                self.handle(json.loads(line))
            except Exception as e:
                print("[spine] bad client msg:", e)
        self.clients.remove(conn)

    def serve(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, PORT))
        srv.listen(8)
        print("[spine] listening", PORT)
        while True:
            conn, addr = srv.accept()
            print("[spine] phone connected", addr)
            self.clients.append(conn)
            threading.Thread(target=self.client_loop, args=(conn,), daemon=True).start()


def main():
    sp = Spine()
    sp.open_serial()
    threading.Thread(target=sp.serial_loop, daemon=True).start()
    sp.serve()


if __name__ == "__main__":
    main()
