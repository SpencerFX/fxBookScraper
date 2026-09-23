#!/usr/bin/env bash
# Broker-info collection, shard 1 of 4. Index :6320 of losing_discovery_expanded.json.
cd "$(dirname "$0")"
LOG=data/state/broker_info_1.log
PY=.venv/Scripts/python.exe
MAX=200
for i in $(seq 1 $MAX); do
  printf '\n=== SUPERVISED (broker-info shard1) attempt %s/%s %s ===\n' "$i" "$MAX" "$(date)" >> "$LOG"
  PYTHONIOENCODING=utf-8 "$PY" -u broker_info.py \
    --out brokerInfo_1.csv --progress broker_progress_1.json \
    --slice :6320 --cdp http://127.0.0.1:9223 \
    >> "$LOG" 2>&1
  rc=$?
  printf '=== attempt %s EXITED rc=%s %s ===\n' "$i" "$rc" "$(date)" >> "$LOG"
  [ "$rc" = "0" ] && break
  sleep 90
done
printf '=== SUPERVISOR (broker-info shard1) finished %s ===\n' "$(date)" >> "$LOG"
