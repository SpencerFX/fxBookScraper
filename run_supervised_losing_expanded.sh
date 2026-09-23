#!/usr/bin/env bash
# Fourth trade-history pipeline: a wider losing-accounts filter the user found
# manually (drawValue=1000, lastTraded=1095 days vs the original filter's 50/90),
# sorted ascending by gain (sb=19&st=1) so the biggest losers come first - the
# default forward walk (no --reverse) naturally starts there. --exclude-existing
# drops any system already in systems.csv or losing_discovery.json (the main
# directory + the original narrower losing filter), so this never re-ingests
# accounts another pipeline already owns.
#
# Universe is 25,280 systems (post-exclusion). --max-pages 20 takes a bounded
# first slice of EVERY system rather than walking a few whales to completion,
# but the sheer system COUNT still means ~18 days single-threaded. This is
# SHARD 1 of 4 (index 0:6320, i.e. the single biggest losers) - a hard index
# slice into the shared discovery-order list, same non-overlap guarantee used
# for the forward/reverse losing-accounts split. Shards 2-4 are
# run_supervised_losing_expanded_{2,3,4}.sh, each with its own progress/out/log
# so none of the four ever touches another's systems or files.
cd "$(dirname "$0")"
LOG=data/state/losing_accounts_expanded.log
PY=.venv/Scripts/python.exe
MAX=200
FILTER_URL='https://www.myfxbook.com/systems?p=1&st=1&sb=19&profitType=1&profitValue=-0.01&drawType=1&drawValue=1000&profitabilityType=0&profitabilityValue=0&ageType=0&ageValue=30&systemType=0&tradingType=0&platformOid=0&serverOid=0&accountType=2&lastTraded=1095&regulationType=1&tradesType=0&size=40&pt=6'
for i in $(seq 1 $MAX); do
  printf '\n=== SUPERVISED (losing-expanded shard1) attempt %s/%s %s ===\n' "$i" "$MAX" "$(date)" >> "$LOG"
  PYTHONIOENCODING=utf-8 "$PY" -u losing_accounts.py --filter-url "$FILTER_URL" \
    --discovery losing_discovery_expanded.json --out losingAccountsExpanded_v5/losingAccountsExpanded.csv \
    --progress losing_progress_expanded.json --exclude-existing --max-pages 20 \
    --slice :6320 --cdp http://127.0.0.1:922 \
    >> "$LOG" 2>&1
  rc=$?
  printf '=== attempt %s EXITED rc=%s %s ===\n' "$i" "$rc" "$(date)" >> "$LOG"
  [ "$rc" = "0" ] && break
  sleep 90
done
printf '=== SUPERVISOR (losing-expanded shard1) finished %s ===\n' "$(date)" >> "$LOG"
