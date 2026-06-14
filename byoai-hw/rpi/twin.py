#!/usr/bin/env python3
"""BYOAI 디지털 트윈 — 척수 STATE를 웹으로 시각화 + 가상 룸 현장조작(선호 데이터 생성).

척수에 폰과 동일한 프로토콜로 붙는 또 하나의 클라이언트.
  보기: 미니룸(램프·연무·팬·히터) + 수치 + LLM 결정 피드 + 공간 기억(학습모델)
  조작: 슬라이더/토글 → MANUAL → 척수가 FEEDBACK 발행 → 폰 휴대모델이 학습

  python3 twin.py --spine 127.0.0.1:8766 --http 8088
"""
from __future__ import annotations
import argparse, json, socket, threading, time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

latest = {"desc": None, "state": None, "ts": 0, "connected": False, "events": []}
events: deque = deque(maxlen=12)
conn = {"sock": None}
lock = threading.Lock()


def follow(host: str, port: int):
    """척수 TCP 상시 접속(재접속 포함). EVENT/FEEDBACK은 결정 피드로 적재."""
    while True:
        try:
            s = socket.create_connection((host, port), 5)
            s.settimeout(15)   # STATE는 1초 주기 — 15초 침묵이면 죽은 연결로 보고 재접속
            with lock:
                conn["sock"] = s
            latest["connected"] = True
            # makefile 금지(타임아웃 후 버퍼 오염) → recv 기반 라인 파서
            buf = b""
            while True:
                chunk = s.recv(4096)   # 15초 침묵 → socket.timeout → 바깥 except → 재접속
                if not chunk:
                    break              # EOF
                buf += chunk
                while b"\n" in buf:
                    raw, buf = buf.split(b"\n", 1)
                    line = raw.decode("utf-8", "replace").strip()
                    if not line:
                        continue
                    m = json.loads(line)
                    t = m.get("type")
                    if t == "SPACE_DESCRIPTOR":
                        latest["desc"] = m
                    elif t == "STATE":
                        latest["state"] = m
                        latest["ts"] = time.time()
                    elif t in ("EVENT", "FEEDBACK"):
                        m.setdefault("t", time.time())
                        events.appendleft(m)
                        latest["events"] = list(events)
        except Exception:
            pass
        with lock:
            conn["sock"] = None
        latest["connected"] = False
        time.sleep(2)


def send_manual(capability: str, value):
    with lock:
        s = conn["sock"]
        if not s:
            return False
        try:
            s.sendall((json.dumps({"type": "MANUAL", "capability": capability,
                                   "value": value}) + "\n").encode())
            return True
        except Exception:
            conn["sock"] = None
            return False


HTML = r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BYOAI Twin</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap" rel="stylesheet">
<style>
:root{
  --bg0:#0A0B0E; --bg1:#111318; --s1:#16191F;
  --t1:#EEF1F6; --t2:#9DA3B0; --t3:#6A7180;
  --accent:#86A4C8; --good:#79B89A; --warn:#C2A878; --danger:#C88686;
  --stroke:rgba(255,255,255,.12);
}
*{margin:0;padding:0;box-sizing:border-box}
body{
  min-height:100vh; background:linear-gradient(180deg,var(--bg1),var(--bg0));
  font-family:'Inter','Pretendard',system-ui,sans-serif; color:var(--t1);
  display:flex; flex-direction:column; align-items:center; padding:36px 20px 60px;
}
.h-g{font-family:'Space Grotesk','Inter',sans-serif}
.head{display:flex;align-items:baseline;gap:12px;margin-bottom:6px}
.head .brand{font-size:13px;letter-spacing:3px;color:var(--t3);font-weight:700}
.head .live{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--t3)}
.dot{width:7px;height:7px;border-radius:50%;background:var(--accent);animation:pulse 1.8s infinite}
.dot.dead{background:var(--danger);animation:none}
@keyframes pulse{0%,100%{opacity:.35}50%{opacity:1}}
#place{font-size:26px;font-weight:700;margin-bottom:22px}
.wrap{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:20px;max-width:1180px;width:100%}
.card{background:var(--s1);border:1px solid var(--stroke);border-radius:18px;padding:16px 18px}
.card h3{font-size:12px;letter-spacing:1.5px;color:var(--t3);font-weight:600;margin-bottom:13px}

/* ── 미니룸 ── */
.room{width:100%;height:280px;border-radius:16px;position:relative;overflow:hidden;background:#0D0F13;border:1px solid var(--stroke)}
#haze{position:absolute;inset:0;background:radial-gradient(closest-side at 50% 45%,rgba(160,160,150,.85),rgba(120,120,112,.5) 70%,transparent);opacity:0;transition:opacity 1s;pointer-events:none}
#lamp{position:absolute;top:24px;left:50%;transform:translateX(-50%);width:32px;height:32px;border-radius:50%;background:#23262E;transition:all .8s}
#lampbeam{position:absolute;top:28px;left:50%;transform:translateX(-50%);width:230px;height:215px;background:radial-gradient(ellipse at top,rgba(255,244,214,.9),rgba(255,244,214,.25) 55%,transparent 75%);opacity:0;transition:opacity .8s;pointer-events:none}
#fan{position:absolute;right:20px;top:20px;width:40px;height:40px}
#fan.on svg{animation:spin .5s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
#heater{position:absolute;left:20px;bottom:16px;width:58px;height:13px;border-radius:7px;background:#23262E;transition:all .8s}
#person{position:absolute;right:28px;bottom:12px;font-size:28px;opacity:0;transition:opacity .6s}
.lbl{position:absolute;font-size:9px;color:var(--t3);letter-spacing:.5px}

/* ── 수치/조절 ── */
.row{display:flex;align-items:center;margin-bottom:4px}
.row .name{font-size:14px;font-weight:600}
.row .tgt{margin-left:9px;font-size:11px;color:var(--t3)}
.row .val{margin-left:auto;font-size:19px;font-weight:700;color:var(--accent);font-family:'Space Grotesk',sans-serif}
.cap{padding:9px 0;border-bottom:1px solid rgba(255,255,255,.05)}
.cap:last-child{border-bottom:none}
input[type=range]{width:100%;accent-color:var(--accent);margin-top:7px}
.airrow{display:flex;align-items:center;margin-top:7px}
.airrow .g{font-size:13px;font-weight:600;margin-right:auto}
.switch{position:relative;width:42px;height:24px}
.switch input{opacity:0;width:0;height:0}
.knob{position:absolute;inset:0;border-radius:13px;background:rgba(255,255,255,.1);transition:.25s;cursor:pointer}
.knob:before{content:"";position:absolute;left:3px;top:3px;width:18px;height:18px;border-radius:50%;background:var(--t3);transition:.25s}
input:checked + .knob{background:rgba(134,164,200,.55)}
input:checked + .knob:before{transform:translateX(18px);background:var(--t1)}
.hint{font-size:10.5px;color:var(--t3);margin-top:10px}

/* ── 결정 피드 / 기억 ── */
.feed{display:flex;flex-direction:column;gap:9px;max-height:300px;overflow-y:auto}
.ev{font-size:12px;line-height:1.45}
.ev .when{color:var(--t3);font-size:10.5px}
.ev .who{font-weight:700}
.ev .who.ai{color:var(--accent)}
.ev .who.hand{color:var(--good)}
.ev .why{color:var(--t2);font-size:11.5px}
.mem{font-size:12px;display:flex;flex-direction:column;gap:8px}
.mem .k{color:var(--t2);font-weight:600}
.mem .v{color:var(--t3)}
.priv{margin-top:10px;padding-top:10px;border-top:1px solid rgba(255,255,255,.06);font-size:11px;color:var(--t3)}
</style>
</head>
<body>
<div class="head">
  <span class="brand">BYOAI · DIGITAL TWIN</span>
  <span class="live"><span class="dot" id="livedot"></span><span id="livetxt">connecting</span></span>
</div>
<div id="place" class="h-g">—</div>

<div class="wrap">
  <div class="card">
    <h3>ROOM</h3>
    <div class="room">
      <div id="lampbeam"></div><div id="haze"></div><div id="lamp"></div>
      <div id="fan"><svg viewBox="0 0 24 24" fill="none" stroke="#9DA3B0" stroke-width="1.5" style="width:100%;height:100%">
        <circle cx="12" cy="12" r="2"/>
        <path d="M12 10c0-4-1.5-6-4-6s-2.5 5 0 6 4 0 4 0zM14 12c4 0 6-1.5 6-4s-5-2.5-6 0 0 4 0 4zM12 14c0 4 1.5 6 4 6s2.5-5 0-6-4 0-4 0zM10 12c-4 0-6 1.5-6 4s5 2.5 6 0 0-4 0-4z"/>
      </svg></div>
      <div id="heater"></div><div id="person">🧍</div>
      <div class="lbl" style="left:22px;bottom:33px">HEAT</div>
      <div class="lbl" style="right:22px;top:62px">FAN</div>
    </div>
    <div class="hint" id="meta">—</div>
  </div>

  <div class="card">
    <h3>CONTROL — 직접 조절 = 학습 신호</h3>
    <div class="cap">
      <div class="row"><span class="name">Light</span><span class="tgt" id="lt"></span><span class="val" id="lv">—</span></div>
      <input type="range" id="lslider" min="0" max="100" value="35">
    </div>
    <div class="cap">
      <div class="row"><span class="name">Temp</span><span class="tgt" id="tt"></span><span class="val" id="tv">—</span></div>
      <input type="range" id="tslider" min="18" max="30" step="0.5" value="22">
    </div>
    <div class="cap">
      <div class="row"><span class="name">Air</span><span class="tgt" id="at"></span><span class="val" id="av">—</span></div>
      <div class="airrow"><span class="g" id="ag"></span>
        <label class="switch"><input type="checkbox" id="aswitch"><span class="knob"></span></label>
      </div>
    </div>
    <div class="hint">여기서 만지면 공간이 FEEDBACK을 발행 — 연결된 폰의 휴대 모델이 학습한다</div>
  </div>

  <div class="card">
    <h3>DECISIONS — 두뇌의 판단 기록</h3>
    <div class="feed" id="feed"><div class="ev"><span class="why">아직 결정 없음 — 폰에서 AI Auto를 누르거나 여기서 조절해봐</span></div></div>
  </div>

  <div class="card">
    <h3>SPACE MEMORY — 공간이 저장 중인 것 (SQLite)</h3>
    <div class="mem" id="mem">—</div>
    <div class="priv">사용자 선호·보정 이력은 여기 없음 — <b>폰에만</b> 저장된다 (공간은 사용자를 모름)</div>
  </div>
</div>

<script>
const $ = id => document.getElementById(id);
const grade = pm => pm<=30?['Good','var(--good)']:pm<=80?['Fair','var(--t2)']:pm<=150?['Bad','var(--warn)']:['Danger','var(--danger)'];
let dragging = null, ranges = {};

function manual(capability, value){
  fetch('/manual', {method:'POST', body: JSON.stringify({capability, value})});
}
$('lslider').oninput = () => { dragging='light'; $('lv').textContent = $('lslider').value + '%'; };
$('lslider').onchange = () => { const r=ranges.light||{min:0,max:1000};
  manual('light', r.min + $('lslider').value/100*(r.max-r.min)); dragging=null; };
$('tslider').oninput = () => { dragging='climate'; $('tv').textContent = (+$('tslider').value).toFixed(1) + '°'; };
$('tslider').onchange = () => { manual('climate', +$('tslider').value); dragging=null; };
$('aswitch').onchange = () => manual('air_quality', $('aswitch').checked ? 40 : null);

function fmtT(ts){ const d=new Date(ts*1000); return d.toTimeString().slice(0,8); }
function tgtsStr(t){ if(!t) return '';
  return Object.entries(t).map(([k,v])=>{
    if(v==null) return k.replace('air_quality','air')+' off';
    if(k==='light') { const r=ranges.light||{min:0,max:1000}; return 'light '+Math.round(v/(r.max-r.min)*100)+'%'; }
    if(k==='climate') return 'temp '+v+'°';
    return 'air ≤'+v;
  }).join(' · ');
}

async function tick(){
  try{
    const r = await fetch('/state'); const d = await r.json();
    const fresh = d.state && (Date.now()/1000 - d.ts) < 5;
    $('livedot').className = 'dot' + (fresh?'':' dead');
    $('livetxt').textContent = fresh ? 'live' : (d.connected ? 'waiting' : 'reconnecting');
    if (d.desc){ $('place').textContent = d.desc.place;
      d.desc.capabilities.forEach(c => ranges[c.kind] = c.range); }
    if (!d.state) return;
    const caps = {}; d.state.caps.forEach(c => caps[c.kind] = c);
    const L=caps.light, A=caps.air_quality, C=caps.climate;

    if (L){
      const span = L.range.max - L.range.min;
      const pct = Math.round((L.current ?? 0)/span*100);
      if (dragging!=='light'){ $('lv').textContent = pct+'%';
        if (L.target!=null) $('lslider').value = Math.round(L.target/span*100); }
      $('lt').textContent = L.target!=null ? '목표 '+Math.round(L.target/span*100)+'%' : '';
      const g = (L.actuator ?? 0)/255;
      $('lamp').style.background = g>.02 ? '#FFF2C9' : '#23262E';
      $('lamp').style.boxShadow = g>.02 ? `0 0 ${20+60*g}px ${8+26*g}px rgba(255,238,190,${.25+.55*g})` : 'none';
      $('lampbeam').style.opacity = g*.9;
    }
    if (A){
      const [gn, gc] = grade(A.current ?? 0);
      $('av').textContent = Math.round(A.current ?? 0);
      $('ag').textContent = gn; $('ag').style.color = gc;
      $('at').textContent = A.target!=null ? '목표 ≤'+A.target : 'off';
      $('aswitch').checked = A.target!=null;
      $('haze').style.opacity = Math.min(.92, (A.current ?? 0)/200);
      $('fan').className = (A.actuator ?? 0) ? 'on' : '';
    }
    if (C){
      if (dragging!=='climate'){ $('tv').textContent = (C.current ?? 0).toFixed(1)+'°';
        if (C.target!=null) $('tslider').value = C.target; }
      $('tt').textContent = C.target!=null ? '목표 '+C.target+'°' : '';
      const act = C.actuator ?? 0;
      $('heater').style.background = act>0 ? '#C88686' : '#23262E';
      $('heater').style.boxShadow = act>0 ? '0 0 24px 6px rgba(200,134,134,.5)' : 'none';
    }
    if (d.desc){
      const occ = d.desc.occupancy && d.desc.occupancy.present;
      $('person').style.opacity = occ ? .9 : 0;
      $('meta').textContent = `${d.desc.space_id} · outside ${d.desc.outside_temp}°`;
      // 공간 기억: 능력별 학습모델 + 시간대 평소값
      $('mem').innerHTML = d.desc.capabilities.map(c=>{
        const m = c.learned_model || {};
        const bits = [];
        if (m.heat_rate_c_per_min) bits.push('가열 '+m.heat_rate_c_per_min+'°/분');
        if (m.cool_rate_c_per_min) bits.push('냉각 '+m.cool_rate_c_per_min+'°/분');
        if (m.lux_per_pwm) bits.push('조명효율 '+m.lux_per_pwm+' lux/pwm');
        if (m.clear_rate_per_min) bits.push('정화 '+m.clear_rate_per_min+'/분');
        if (m.confidence!=null) bits.push('확신도 '+Math.round(m.confidence*100)+'%');
        const typ = c.typical_now!=null ? ` · 이 시간대 평소 ${c.typical_now}${c.unit}` : '';
        return `<div><span class="k">${c.kind}</span> <span class="v">${bits.join(' · ')||'학습 중…'}${typ}</span></div>`;
      }).join('');
    }
    // 결정 피드
    if (d.events && d.events.length){
      $('feed').innerHTML = d.events.map(e=>{
        if (e.type==='EVENT' && e.event==='command'){
          const hand = (e.reason||'').startsWith('manual');   // 앱 슬라이더/토글 = 수동
          return `<div class="ev"><span class="when">${fmtT(e.t)}</span> <span class="who ${hand?'hand':'ai'}">${hand?'✋ 수동조작':'🧠 AI 결정'}</span> ${tgtsStr(e.targets)}<br><span class="why">${hand?'학습신호 → 폰 휴대모델':(e.reason||'')}</span></div>`;
        }
        if (e.type==='FEEDBACK')
          return `<div class="ev"><span class="when">${fmtT(e.t)}</span> <span class="who hand">✋ 수동조작</span> ${e.capability} → ${e.to==null?'off':e.to}<br><span class="why">학습신호 발행 → 폰 휴대모델로</span></div>`;
        return '';
      }).join('');
    }
  }catch(e){ $('livedot').className='dot dead'; $('livetxt').textContent='no server'; }
}
setInterval(tick, 1000); tick();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body: bytes, ctype: str):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/state":
            self._send(json.dumps(latest, ensure_ascii=False).encode(), "application/json")
        else:
            self._send(HTML.encode(), "text/html; charset=utf-8")

    def do_POST(self):
        if self.path == "/manual":
            n = int(self.headers.get("Content-Length", 0))
            try:
                m = json.loads(self.rfile.read(n))
                ok = send_manual(m.get("capability"), m.get("value"))
            except Exception:
                ok = False
            self._send(json.dumps({"ok": ok}).encode(), "application/json")
        else:
            self._send(b"{}", "application/json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spine", default="127.0.0.1:8765", help="척수 주소 host:port")
    ap.add_argument("--http", type=int, default=8088, help="웹 포트")
    a = ap.parse_args()
    host, port = a.spine.rsplit(":", 1)
    threading.Thread(target=follow, args=(host, int(port)), daemon=True).start()
    print(f"  [트윈] 척수 {a.spine} 추적 → http://0.0.0.0:{a.http}")
    ThreadingHTTPServer(("0.0.0.0", a.http), Handler).serve_forever()


if __name__ == "__main__":
    main()
