#!/usr/bin/env python3
"""BYOAI 디스커버리 클라이언트 — '자동 기기추가'의 PC 버전.

같은 WiFi의 '_byoai._tcp' 서비스를 mDNS로 탐색 → 발견 즉시 자동 연결 →
SPACE_DESCRIPTOR를 읽어 능력(기기)을 자동 목록화. 공간 이탈 시 자동 제거.
폰 앱은 이 browse를 안드로이드 NsdManager로 똑같이 구현하면 됨.

  python discover.py                # 계속 탐색
  python discover.py --seconds 6    # 6초만(테스트)
"""
import argparse, json, socket, time
from zeroconf import Zeroconf, ServiceBrowser


class Listener:
    def __init__(self): self.spaces = {}
    def add_service(self, zc, type_, name):
        info = zc.get_service_info(type_, name, timeout=2000)
        if not info or not info.addresses:
            return
        ip = socket.inet_ntoa(info.addresses[0]); port = info.port
        props = {k.decode(): (v.decode("utf-8", "replace") if v else "")
                 for k, v in (info.properties or {}).items()}
        self.spaces[name] = (ip, port)
        print(f"\n[기기 자동추가] 공간 발견: {props.get('place','?')} "
              f"(caps={props.get('caps','?')}) @ {ip}:{port}")
        try:                                     # 자동 연결 → descriptor → 기기 목록
            s = socket.create_connection((ip, port), timeout=3)
            desc = json.loads(s.makefile("r", encoding="utf-8").readline())
            for c in desc["capabilities"]:
                print(f"    + 기기: [{c['kind']}] 현재 {c['current']}{c['unit']} "
                      f"(범위 {c['range']['min']}~{c['range']['max']})")
            s.close()
        except Exception as e:
            print(f"    (descriptor 조회 실패: {e})")
    def update_service(self, *a): pass
    def remove_service(self, zc, type_, name):
        self.spaces.pop(name, None)
        print(f"[공간 이탈] 기기 자동 제거: {name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=0, help="N초 후 종료(0=계속)")
    a = ap.parse_args()
    zc = Zeroconf(); ln = Listener()
    ServiceBrowser(zc, "_byoai._tcp.local.", ln)
    print("BYOAI 공간 탐색 중... (Ctrl+C 종료)")
    try:
        if a.seconds:
            time.sleep(a.seconds)
        else:
            while True: time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        zc.close()
        print(f"\n탐색 종료. 발견 공간 {len(ln.spaces)}개.")


if __name__ == "__main__":
    main()
