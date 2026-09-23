#!/usr/bin/env bash
# Broker-info collection, shard 2 of 4. Index 6320:12640 of losing_discovery_expanded.json.
cd "$(dirname "$0")"
LOG=data/state/broker_info_2.log
PY=.venv/Scripts/python.exe
MAX=200
for i in $(seq 1 $MAX); do
  printf '\n=== SUPERVISED (broker-info shard2) attempt %s/%s %s ===\n' "$i" "$MAX" "$(date)" >> "$LOG"
  PYTHONIOENCODING=utf-8 "$PY" -u broker_info.py \
    --out brokerInfo_2.csv --progress broker_progress_2.json \
    --slice 6320:12640 --cdp http://127.0.0.1:9223 \
    >> "$LOG" 2>&1
  rc=$?
  printf '=== attempt %s EXITED rc=%s %s ===\n' "$i" "$rc" "$(date)" >> "$LOG"
  [ "$rc" = "0" ] && break
  sleep 90
done
printf '=== SUPERVISOR (broker-info shard2) finished %s ===\n' "$(date)" >> "$LOG"
