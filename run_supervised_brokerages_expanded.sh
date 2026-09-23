#!/usr/bin/env bash
# Brokerage-info collection for the losing-expanded universe (25,280 systems,
# losing_discovery_expanded.json) - never covered by the original two
# brokerages instances, which only targeted systems.csv + losing_discovery.json
# (the main directory + the original narrower losing filter). Scoped via
# brokerages.py's --discovery flag, which preserves that file's own order
# (worst-losers-first), matching the trade-collection shards' priority.
#
# SHARD 1 of 2 - index 0:12640 (the worse half of the losses). Own out/progress
# files under data/csv/brokerages/, so it can't collide with shard 2 or with
# the original brokerages.csv (already merged from the forward/reverse
# workers - see data/csv/brokerages/brokerages.csv).
cd "$(dirname "$0")"
LOG=data/state/brokerages_expanded.log
PY=.venv/Scripts/python.exe
MAX=200
for i in $(seq 1 $MAX); do
  printf '\n=== SUPERVISED (brokerages-expanded shard1) attempt %s/%s %s ===\n' "$i" "$MAX" "$(date)" >> "$LOG"
  PYTHONIOENCODING=utf-8 "$PY" -u brokerages.py \
    --discovery losing_discovery_expanded.json \
    --out brokerages/brokerages_expanded.csv \
    --progress brokerages_progress_expanded.json \
    --slice :12640 --cdp http://127.0.0.1:922 \
    >> "$LOG" 2>&1
  rc=$?
  printf '=== attempt %s EXITED rc=%s %s ===\n' "$i" "$rc" "$(date)" >> "$LOG"
  [ "$rc" = "0" ] && break
  sleep 90
done
printf '=== SUPERVISOR (brokerages-expanded shard1) finished %s ===\n' "$(date)" >> "$LOG"
