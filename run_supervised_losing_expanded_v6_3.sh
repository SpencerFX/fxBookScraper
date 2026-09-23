#!/usr/bin/env bash
# v6 FINAL CLEANUP shard 3 of 4 - see run_supervised_losing_expanded_v6_1.sh
# for the full explanation. Its own disjoint slice of the 89 remaining systems.
cd "$(dirname "$0")"
LOG=data/state/losing_accounts_expanded_v6_3.log
PY=.venv/Scripts/python.exe
MAX=200
FILTER_URL='https://www.myfxbook.com/systems?p=1&st=1&sb=19&profitType=1&profitValue=-0.01&drawType=1&drawValue=1000&profitabilityType=0&profitabilityValue=0&ageType=0&ageValue=30&systemType=0&tradingType=0&platformOid=0&serverOid=0&accountType=2&lastTraded=1095&regulationType=1&tradesType=0&size=40&pt=6'
SYSTEMS='11670086,9579224,10521473,9617626,10735866,11102262,11763211,12026138,10979326,10926865,11217598,3133351,11162584,11638650,11373645,10960957,10993770,9732185,7563722,10347104,9403548,10695632'
for i in $(seq 1 $MAX); do
  printf '\n=== SUPERVISED (losing-expanded v6-3) attempt %s/%s %s ===\n' "$i" "$MAX" "$(date)" >> "$LOG"
  PYTHONIOENCODING=utf-8 "$PY" -u losing_accounts.py --filter-url "$FILTER_URL" \
    --discovery losing_discovery_expanded.json --out losingAccountsExpanded_v6/losingAccountsExpanded_v6_3.csv \
    --progress losing_progress_expanded_v6_3.json --systems "$SYSTEMS" --max-pages 20 \
    --cdp http://127.0.0.1:9222 \
    >> "$LOG" 2>&1
  rc=$?
  printf '=== attempt %s EXITED rc=%s %s ===\n' "$i" "$rc" "$(date)" >> "$LOG"
  [ "$rc" = "0" ] && break
  sleep 90
done
printf '=== SUPERVISOR (losing-expanded v6-3) finished %s ===\n' "$(date)" >> "$LOG"
