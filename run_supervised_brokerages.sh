#!/usr/bin/env bash
# Relaunch the brokerage-info scrape until it completes (rc 0) or we exhaust
# attempts. One page nav per system (no history pagination), covering the
# union of systems.csv + losing_discovery.json, so this single run/supervisor
# picks up systems from all three trade-history pipelines. A re-run skips
# systems already marked done in brokerages_progress.json.
cd "$(dirname "$0")"
LOG=data/state/brokerages.log
PY=.venv/Scripts/python.exe
MAX=200
for i in $(seq 1 $MAX); do
  printf '\n=== SUPERVISED (brokerages) attempt %s/%s %s ===\n' "$i" "$MAX" "$(date)" >> "$LOG"
  PYTHONIOENCODING=utf-8 "$PY" -u brokerages.py >> "$LOG" 2>&1
  rc=$?
  printf '=== attempt %s EXITED rc=%s %s ===\n' "$i" "$rc" "$(date)" >> "$LOG"
  [ "$rc" = "0" ] && break
  sleep 90
done
printf '=== SUPERVISOR (brokerages) finished %s ===\n' "$(date)" >> "$LOG"
