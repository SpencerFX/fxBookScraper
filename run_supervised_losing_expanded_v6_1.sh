#!/usr/bin/env bash
# v6 FINAL CLEANUP shard 1 of 4. As of 2026-09-22, the union of all six prior
# shards' progress files (shards 1-6, covering the full 25,280-system
# discovery-order universe) leaves only 89 systems undone - a handful of
# scattered stragglers from earlier shards plus shard5's leftover tail (it was
# stopped mid-way by request rather than run to completion). Those 89 are NOT
# a contiguous index range, so this uses --systems (explicit comma-separated
# IDs) instead of --slice. The 89 were split round-robin into 4 groups of
# ~22-23 so none of the four v6 shards can ever touch the same system.
cd "$(dirname "$0")"
LOG=data/state/losing_accounts_expanded_v6_1.log
PY=.venv/Scripts/python.exe
MAX=200
FILTER_URL='https://www.myfxbook.com/systems?p=1&st=1&sb=19&profitType=1&profitValue=-0.01&drawType=1&drawValue=1000&profitabilityType=0&profitabilityValue=0&ageType=0&ageValue=30&systemType=0&tradingType=0&platformOid=0&serverOid=0&accountType=2&lastTraded=1095&regulationType=1&tradesType=0&size=40&pt=6'
SYSTEMS='10153114,11255824,6431763,10958888,11919738,10604814,10967042,12035242,11519723,8565119,11770964,10150782,10130547,11831714,11884274,11070859,10844917,11447319,12068719,11557697,10479120,11212103,10791862'
for i in $(seq 1 $MAX); do
  printf '\n=== SUPERVISED (losing-expanded v6-1) attempt %s/%s %s ===\n' "$i" "$MAX" "$(date)" >> "$LOG"
  PYTHONIOENCODING=utf-8 "$PY" -u losing_accounts.py --filter-url "$FILTER_URL" \
    --discovery losing_discovery_expanded.json --out losingAccountsExpanded_v6/losingAccountsExpanded_v6_1.csv \
    --progress losing_progress_expanded_v6_1.json --systems "$SYSTEMS" --max-pages 20 \
    --cdp http://127.0.0.1:9222 \
    >> "$LOG" 2>&1
  rc=$?
  printf '=== attempt %s EXITED rc=%s %s ===\n' "$i" "$rc" "$(date)" >> "$LOG"
  [ "$rc" = "0" ] && break
  sleep 90
done
printf '=== SUPERVISOR (losing-expanded v6-1) finished %s ===\n' "$(date)" >> "$LOG"
