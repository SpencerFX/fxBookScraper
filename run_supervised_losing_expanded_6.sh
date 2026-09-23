#!/usr/bin/env bash
# SHARD 6 (v5 only) of the expanded losing-accounts pipeline - see
# run_supervised_losing_expanded.sh for the full explanation. This is the
# freed capacity from shard1, which fully finished its own slice (0:6320,
# 6320/6320) as of 2026-09-22 and was retired. That capacity was reallocated
# to shard2 (the slowest-progressing shard once shard1 was gone): shard2's own
# progress file showed its true remaining backlog is just indices 11441:11734
# (a clean prefix up to 11441, bar 3 stragglers left for a future sweep). That
# tail was split in half - shard2 keeps 11441:11587, and this shard owns
# 11587:11734 - with its own fresh progress/out/log so it can never touch a
# system shard2 (or any other shard) owns.
cd "$(dirname "$0")"
LOG=data/state/losing_accounts_expanded_6.log
PY=.venv/Scripts/python.exe
MAX=200
FILTER_URL='https://www.myfxbook.com/systems?p=1&st=1&sb=19&profitType=1&profitValue=-0.01&drawType=1&drawValue=1000&profitabilityType=0&profitabilityValue=0&ageType=0&ageValue=30&systemType=0&tradingType=0&platformOid=0&serverOid=0&accountType=2&lastTraded=1095&regulationType=1&tradesType=0&size=40&pt=6'
for i in $(seq 1 $MAX); do
  printf '\n=== SUPERVISED (losing-expanded shard6) attempt %s/%s %s ===\n' "$i" "$MAX" "$(date)" >> "$LOG"
  PYTHONIOENCODING=utf-8 "$PY" -u losing_accounts.py --filter-url "$FILTER_URL" \
    --discovery losing_discovery_expanded.json --out losingAccountsExpanded_v5/losingAccountsExpanded_6.csv \
    --progress losing_progress_expanded_6.json --exclude-existing --max-pages 20 \
    --slice 11587:11734 --cdp http://127.0.0.1:922 \
    >> "$LOG" 2>&1
  rc=$?
  printf '=== attempt %s EXITED rc=%s %s ===\n' "$i" "$rc" "$(date)" >> "$LOG"
  [ "$rc" = "0" ] && break
  sleep 90
done
printf '=== SUPERVISOR (losing-expanded shard6) finished %s ===\n' "$(date)" >> "$LOG"
