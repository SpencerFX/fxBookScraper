#!/usr/bin/env bash
# Relaunch the brokerage-info scrape (FIRST half, index 0:913 of the sorted
# target list) until it completes (rc 0) or we exhaust attempts. One page nav
# per system (no history pagination), covering the union of systems.csv +
# losing_discovery.json (1826 systems total), so this + the reverse half
# (run_supervised_brokerages_reverse.sh, index 913: walked back-to-front)
# together pick up every system from all three trade-history pipelines with
# no overlap - the index slice, not run order, guarantees that. A re-run
# skips systems already marked done in brokerages_progress.json.
cd "$(dirname "$0")"
LOG=data/state/brokerages.log
PY=.venv/Scripts/python.exe
MAX=200
for i in $(seq 1 $MAX); do
  printf '\n=== SUPERVISED (brokerages) attempt %s/%s %s ===\n' "$i" "$MAX" "$(date)" >> "$LOG"
  PYTHONIOENCODING=utf-8 "$PY" -u brokerages.py --slice :913 >> "$LOG" 2>&1
  rc=$?
  printf '=== attempt %s EXITED rc=%s %s ===\n' "$i" "$rc" "$(date)" >> "$LOG"
  [ "$rc" = "0" ] && break
  sleep 90
done
printf '=== SUPERVISOR (brokerages) finished %s ===\n' "$(date)" >> "$LOG"
