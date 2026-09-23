#!/usr/bin/env bash
# Broker-info collection, shard 4 of 4. Index 18960: of losing_discovery_expanded.json.
cd "$(dirname "$0")"
LOG=data/state/broker_info_4.log
PY=.venv/Scripts/python.exe
MAX=200
for i in $(seq 1 $MAX); do
  printf '\n=== SUPERVISED (broker-info shard4) attempt %s/%s %s ===\n' "$i" "$MAX" "$(date)" >> "$LOG"
  PYTHONIOENCODING=utf-8 "$PY" -u broker_info.py \
    --out brokerInfo_4.csv --progress broker_progress_4.json \
    --slice 18960: --cdp http://127.0.0.1:9223 \
    >> "$LOG" 2>&1
  rc=$?
  printf '=== attempt %s EXITED rc=%s %s ===\n' "$i" "$rc" "$(date)" >> "$LOG"
  [ "$rc" = "0" ] && break
  sleep 90
done
printf '=== SUPERVISOR (broker-info shard4) finished %s ===\n' "$(date)" >> "$LOG"
