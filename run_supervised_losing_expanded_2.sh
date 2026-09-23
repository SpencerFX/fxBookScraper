#!/usr/bin/env bash
# SHARD 2 of 4 of the expanded losing-accounts pipeline - see
# run_supervised_losing_expanded.sh for the full explanation. This shard owns
# index 6320:12640 of the shared discovery-order list (losing_discovery_expanded.json,
# worst-losers-first) and its own progress/out/log files, so it can never
# touch a system any other shard owns.
#
# v5 NARROWING: as of 2026-09-21, this shard's own progress file shows indices
# 6320:10829 are done (a clean prefix, bar 7 stragglers left for a future sweep),
# so shard2's remaining backlog is really just 10829:12640. Since shard4
# finished its whole slice (18960:25280, 6320/6320) and was retired, its
# capacity was reallocated to split shard2's remaining tail in half: shard2
# kept 10829:11734, and the other half (11734:12640) ran as
# run_supervised_losing_expanded_5.sh with its own fresh progress/out/log.
#
# v5 RE-NARROWING (2026-09-22): shard1 has since finished its own whole slice
# (0:6320, 6320/6320) and was retired too. Its capacity was reallocated the
# same way: shard2's own progress file now shows indices 10829:11441 done (a
# clean prefix, bar 3 stragglers left for a future sweep), so shard2's real
# remaining backlog is just 11441:11734. That was split in half again: shard2
# keeps 11441:11587 here, and the other half (11587:11734) now runs as the new
# run_supervised_losing_expanded_6.sh with its own fresh progress/out/log.
cd "$(dirname "$0")"
LOG=data/state/losing_accounts_expanded_2.log
PY=.venv/Scripts/python.exe
MAX=200
FILTER_URL='https://www.myfxbook.com/systems?p=1&st=1&sb=19&profitType=1&profitValue=-0.01&drawType=1&drawValue=1000&profitabilityType=0&profitabilityValue=0&ageType=0&ageValue=30&systemType=0&tradingType=0&platformOid=0&serverOid=0&accountType=2&lastTraded=1095&regulationType=1&tradesType=0&size=40&pt=6'
for i in $(seq 1 $MAX); do
  printf '\n=== SUPERVISED (losing-expanded shard2) attempt %s/%s %s ===\n' "$i" "$MAX" "$(date)" >> "$LOG"
  PYTHONIOENCODING=utf-8 "$PY" -u losing_accounts.py --filter-url "$FILTER_URL" \
    --discovery losing_discovery_expanded.json --out losingAccountsExpanded_v5/losingAccountsExpanded_2.csv \
    --progress losing_progress_expanded_2.json --exclude-existing --max-pages 20 \
    --slice 11441:11587 --cdp http://127.0.0.1:922 \
    >> "$LOG" 2>&1
  rc=$?
  printf '=== attempt %s EXITED rc=%s %s ===\n' "$i" "$rc" "$(date)" >> "$LOG"
  [ "$rc" = "0" ] && break
  sleep 90
done
printf '=== SUPERVISOR (losing-expanded shard2) finished %s ===\n' "$(date)" >> "$LOG"
