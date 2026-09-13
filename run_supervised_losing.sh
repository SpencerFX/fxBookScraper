#!/usr/bin/env bash
# Relaunch the losing-accounts backfill until it completes (rc 0) or attempts
# are exhausted. losing_accounts.py exits nonzero after 8 consecutive CF blocks
# so a fresh browser nav / short cooldown can clear the wall; this loop is what
# was missing before - a one-off launch has no way to recover from that exit.
cd "$(dirname "$0")"
LOG=data/state/losing_accounts.log
PY=.venv/Scripts/python.exe
MAX=200
for i in $(seq 1 $MAX); do
  printf '\n=== SUPERVISED (losing) attempt %s/%s %s ===\n' "$i" "$MAX" "$(date)" >> "$LOG"
  PYTHONIOENCODING=utf-8 "$PY" -u losing_accounts.py --slice :582 >> "$LOG" 2>&1
  rc=$?
  printf '=== attempt %s EXITED rc=%s %s ===\n' "$i" "$rc" "$(date)" >> "$LOG"
  [ "$rc" = "0" ] && break
  sleep 90
done
printf '=== SUPERVISOR (losing) finished %s ===\n' "$(date)" >> "$LOG"
