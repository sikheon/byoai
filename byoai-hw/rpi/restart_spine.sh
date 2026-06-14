#!/bin/bash
# 척수 재시작 (Pi에서 실행). 사용: bash restart_spine.sh [spine.py 추가 인자...]
cd ~/byoai
pkill -f 'spine\.py' 2>/dev/null
sleep 0.5
if [ $# -eq 0 ]; then set -- --sim --mdns; fi
nohup ./venv/bin/python spine.py "$@" > spine.log 2>&1 &
sleep 3
tail -5 spine.log
