#!/usr/bin/env bash
# v6 FINAL CLEANUP shard 2 of 4 - see run_supervised_losing_expanded_v6_1.sh
# for the full explanation. Its own disjoint slice of the 89 remaining systems.
cd "$(dirname "$0")"
LOG=data/state/losing_accounts_expanded_v6_2.log
PY=.venv/Scripts/python.exe
MAX=200
FILTER_URL='https://www.myfxbook.com/systems?p=1&st=1&sb=19&profitType=1&profitValue=-0.01&drawType=1&drawValue=1000&profitabilityType=0&profitabilityValue=0&ageType=0&ageValue=30&systemType=0&tradingType=0&platformOid=0&serverOid=0&accountType=2&lastTraded=1095&regulationType=1&tradesType=0&size=40&pt=6'
SYSTEMS='11672262,3952471,10814018,8715348,10335237,8739748,11732944,12027585,11191847,10924904,10319202,11074011,11555347,11637643,11969023,10976334,10343519,11268055,12083788,10518602,11494174,10878834'
for i in $(seq 1 $MAX); do
  printf '\n=== SUPERVISED (losing-expanded v6-2) attempt %s/%s %s ===\n' "$i" "$MAX" "$(date)" >> "$LOG"
  PYTHONIOENCODING=utf-8 "$PY" -u losing_accounts.py --filter-url "$FILTER_URL" \
    --discovery losing_discovery_expanded.json --out losingAccountsExpanded_v6/losingAccountsExpanded_v6_2.csv \
    --progress losing_progress_expanded_v6_2.json --systems "$SYSTEMS" --max-pages 20 \
    --cdp http://127.0.0.1:9222 \
    >> "$LOG" 2>&1
  rc=$?
  printf '=== attempt %s EXITED rc=%s %s ===\n' "$i" "$rc" "$(date)" >> "$LOG"
  [ "$rc" = "0" ] && break
  sleep 90
done
printf '=== SUPERVISOR (losing-expanded v6-2) finished %s ===\n' "$(date)" >> "$LOG"
