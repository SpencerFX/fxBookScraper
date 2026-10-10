#!/usr/bin/env bash
# losing expanded v9, shard 6 of 8 - continuing from v7's checkpoint: finish the trade history of the systems the
# v1-v6 runs stopped at --max-pages 20. Resumes each system at pages_done+1
# (seeded by make_v7_shards.py) with NO page cap, fewest-remaining-pages first,
# and never rewrites a tradeKey already present in the earlier expanded CSVs.
cd "$(dirname "$0")/.."
LOG=data/state/losing_accounts_expanded_v9_6.log
PY=.venv/Scripts/python.exe
MAX=200
for i in $(seq 1 $MAX); do
  printf '\n=== SUPERVISED (losing-expanded v9-6) attempt %s/%s %s ===\n' "$i" "$MAX" "$(date)" >> "$LOG"
  PYTHONIOENCODING=utf-8 "$PY" -u py/losing_accounts.py     --systems-file data/state/v7_systems_6.txt     --out losingAccountsExpanded_v9/losingAccountsExpanded_v9_6.csv     --progress losing_progress_expanded_v7_6.json     --dedupe-against 'losingAccountsExpanded*/*.csv' --dedupe-against 'losingAccountsExpanded/daily/*.csv'     --cdp http://127.0.0.1:9223     >> "$LOG" 2>&1
  rc=$?
  printf '=== attempt %s EXITED rc=%s %s ===\n' "$i" "$rc" "$(date)" >> "$LOG"
  [ "$rc" = "0" ] && break
  sleep 90
done
printf '=== SUPERVISOR (losing-expanded v9-6) finished %s ===\n' "$(date)" >> "$LOG"
