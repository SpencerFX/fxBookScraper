#!/usr/bin/env bash
# Third concurrent instance: same losing-accounts filter/discovery list as
# run_supervised_losing.sh, but hard-partitioned to the SECOND half by index
# (--slice 582:) and walked back-to-front (--reverse) within that half, into
# its own progress file and CSV. The index slice - not run-order/timing - is
# what guarantees the two instances can never touch the same system.
cd "$(dirname "$0")"
LOG=data/state/losing_accounts_reverse.log
PY=.venv/Scripts/python.exe
MAX=200
for i in $(seq 1 $MAX); do
  printf '\n=== SUPERVISED (losing-reverse) attempt %s/%s %s ===\n' "$i" "$MAX" "$(date)" >> "$LOG"
  PYTHONIOENCODING=utf-8 "$PY" -u losing_accounts.py --reverse --slice 582: \
    --progress losing_progress_reverse.json --out losingAccounts_reverse.csv \
    >> "$LOG" 2>&1
  rc=$?
  printf '=== attempt %s EXITED rc=%s %s ===\n' "$i" "$rc" "$(date)" >> "$LOG"
  [ "$rc" = "0" ] && break
  sleep 90
done
printf '=== SUPERVISOR (losing-reverse) finished %s ===\n' "$(date)" >> "$LOG"
