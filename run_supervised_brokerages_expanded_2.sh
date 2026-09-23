#!/usr/bin/env bash
# SHARD 2 of 2 - see run_supervised_brokerages_expanded.sh for the full
# explanation. This shard owns index 12640: (the milder half of the losses)
# of losing_discovery_expanded.json, with its own out/progress files.
cd "$(dirname "$0")"
LOG=data/state/brokerages_expanded_2.log
PY=.venv/Scripts/python.exe
MAX=200
for i in $(seq 1 $MAX); do
  printf '\n=== SUPERVISED (brokerages-expanded shard2) attempt %s/%s %s ===\n' "$i" "$MAX" "$(date)" >> "$LOG"
  PYTHONIOENCODING=utf-8 "$PY" -u brokerages.py \
    --discovery losing_discovery_expanded.json \
    --out brokerages/brokerages_expanded_2.csv \
    --progress brokerages_progress_expanded_2.json \
    --slice 12640: --cdp http://127.0.0.1:922 \
    >> "$LOG" 2>&1
  rc=$?
  printf '=== attempt %s EXITED rc=%s %s ===\n' "$i" "$rc" "$(date)" >> "$LOG"
  [ "$rc" = "0" ] && break
  sleep 90
done
printf '=== SUPERVISOR (brokerages-expanded shard2) finished %s ===\n' "$(date)" >> "$LOG"
