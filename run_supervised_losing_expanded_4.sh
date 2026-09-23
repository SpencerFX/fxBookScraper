#!/usr/bin/env bash
# SHARD 4 of 4 of the expanded losing-accounts pipeline - see
# run_supervised_losing_expanded.sh for the full explanation. This shard owns
# index 18960:25280 (the end of the list) of the shared discovery-order list
# (losing_discovery_expanded.json, worst-losers-first) and its own
# progress/out/log files, so it can never touch a system any other shard owns.
cd "$(dirname "$0")"
LOG=data/state/losing_accounts_expanded_4.log
PY=.venv/Scripts/python.exe
MAX=200
FILTER_URL='https://www.myfxbook.com/systems?p=1&st=1&sb=19&profitType=1&profitValue=-0.01&drawType=1&drawValue=1000&profitabilityType=0&profitabilityValue=0&ageType=0&ageValue=30&systemType=0&tradingType=0&platformOid=0&serverOid=0&accountType=2&lastTraded=1095&regulationType=1&tradesType=0&size=40&pt=6'
for i in $(seq 1 $MAX); do
  printf '\n=== SUPERVISED (losing-expanded shard4) attempt %s/%s %s ===\n' "$i" "$MAX" "$(date)" >> "$LOG"
  PYTHONIOENCODING=utf-8 "$PY" -u losing_accounts.py --filter-url "$FILTER_URL" \
    --discovery losing_discovery_expanded.json --out losingAccountsExpanded_v4/losingAccountsExpanded_4.csv \
    --progress losing_progress_expanded_4.json --exclude-existing --max-pages 20 \
    --slice 18960: --cdp http://127.0.0.1:922 \
    >> "$LOG" 2>&1
  rc=$?
  printf '=== attempt %s EXITED rc=%s %s ===\n' "$i" "$rc" "$(date)" >> "$LOG"
  [ "$rc" = "0" ] && break
  sleep 90
done
printf '=== SUPERVISOR (losing-expanded shard4) finished %s ===\n' "$(date)" >> "$LOG"
