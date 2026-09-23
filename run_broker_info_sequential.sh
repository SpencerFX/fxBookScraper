#!/usr/bin/env bash
# Broker-info collection for all 25,280 systems in losing_discovery_expanded.json.
# Split into 4 index slices (same boundaries as the original losing-expanded
# shards) but run ONE AT A TIME, sequentially, against the dedicated automation
# Brave instance on port 9223 - by request, rather than 4 parallel instances.
cd "$(dirname "$0")"
PY=.venv/Scripts/python.exe
MAX=200
CDP=http://127.0.0.1:9223

SLICES=(":6320" "6320:12640" "12640:18960" "18960:")
NAMES=("1" "2" "3" "4")

for idx in 0 1 2 3; do
  n="${NAMES[$idx]}"
  slice="${SLICES[$idx]}"
  LOG="data/state/broker_info_${n}.log"
  for i in $(seq 1 $MAX); do
    printf '\n=== SUPERVISED (broker-info shard%s) attempt %s/%s %s ===\n' "$n" "$i" "$MAX" "$(date)" >> "$LOG"
    PYTHONIOENCODING=utf-8 "$PY" -u broker_info.py \
      --out brokerInfo_${n}.csv --progress broker_progress_${n}.json \
      --slice "$slice" --cdp "$CDP" \
      >> "$LOG" 2>&1
    rc=$?
    printf '=== attempt %s EXITED rc=%s %s ===\n' "$i" "$rc" "$(date)" >> "$LOG"
    [ "$rc" = "0" ] && break
    sleep 90
  done
  printf '=== SUPERVISOR (broker-info shard%s) finished %s ===\n' "$n" "$(date)" >> "$LOG"
done
printf '\n=== ALL 4 BROKER-INFO SHARDS FINISHED %s ===\n' "$(date)" >> data/state/broker_info_1.log
