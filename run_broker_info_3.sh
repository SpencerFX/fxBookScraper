#!/usr/bin/env bash
# Broker-info collection, shard 3 of 4. Index 12640:18960 of losing_discovery_expanded.json.
cd "$(dirname "$0")"
LOG=data/state/broker_info_3.log
PY=.venv/Scripts/python.exe
MAX=200
for i in $(seq 1 $MAX); do
  printf '\n=== SUPERVISED (broker-info shard3) attempt %s/%s %s ===\n' "$i" "$MAX" "$(date)" >> "$LOG"
  PYTHONIOENCODING=utf-8 "$PY" -u broker_info.py \
    --out brokerInfo_3.csv --progress broker_progress_3.json \
    --slice 12640:18960 --cdp http://127.0.0.1:9223 \
    >> "$LOG" 2>&1
  rc=$?
  printf '=== attempt %s EXITED rc=%s %s ===\n' "$i" "$rc" "$(date)" >> "$LOG"
  [ "$rc" = "0" ] && break
  sleep 90
done
printf '=== SUPERVISOR (broker-info shard3) finished %s ===\n' "$(date)" >> "$LOG"
