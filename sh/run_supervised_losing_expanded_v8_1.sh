#!/usr/bin/env bash
# losing expanded v8, shard 1 of 8 - continuing from v7's checkpoint: finish the trade history of the systems the
# v1-v6 runs stopped at --max-pages 20. Resumes each system at pages_done+1
# (seeded by make_v7_shards.py) with NO page cap, fewest-remaining-pages first,
# and never rewrites a tradeKey already present in the earlier expanded CSVs.
cd "$(dirname "$0")/.."
LOG=data/state/losing_accounts_expanded_v8_1.log
PY=.venv/Scripts/python.exe
MAX=200
for i in $(seq 1 $MAX); do
  printf '\n=== SUPERVISED (losing-expanded v8-1) attempt %s/%s %s ===\n' "$i" "$MAX" "$(date)" >> "$LOG"
  PYTHONIOENCODING=utf-8 "$PY" -u py/losing_accounts.py     --systems-file data/state/v7_systems_1.txt     --out losingAccountsExpanded_v8/losingAccountsExpanded_v8_1.csv     --progress losing_progress_expanded_v7_1.json     --dedupe-against 'losingAccountsExpanded*/*.csv'     --cdp http://127.0.0.1:9223     >> "$LOG" 2>&1
  rc=$?
  printf '=== attempt %s EXITED rc=%s %s ===\n' "$i" "$rc" "$(date)" >> "$LOG"
  [ "$rc" = "0" ] && break
  sleep 90
done
printf '=== SUPERVISOR (losing-expanded v8-1) finished %s ===\n' "$(date)" >> "$LOG"
