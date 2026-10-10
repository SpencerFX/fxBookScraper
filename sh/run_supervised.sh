#!/usr/bin/env bash
# Generic supervisor: relaunch <script.py> with the given args until it exits
# 0 or MAX attempts are exhausted, appending every attempt's output to
# <log_path>. Every losing_accounts.py / broker_info.py / brokerages.py /
# trades_backfill.py run this project has ever done used this exact
# retry-loop shape, because each of those scripts checkpoints per-system or
# per-page: a Cloudflare block or any other nonzero exit just costs the 90s
# relaunch gap, never any lost progress. This replaces ~40 near-identical
# one-off copies of the same loop - see README.md for example invocations
# (including the historical shard slices that used to be separate scripts).
# -
#   sh/run_supervised.sh <script.py> <log_path> [max_attempts] -- <python args...>
#
# Examples:
#   sh/run_supervised.sh py/losing_accounts.py data/state/losing_accounts.log 200 -- --slice :582
#   sh/run_supervised.sh py/broker_info.py data/state/broker_info_1.log -- --out brokerInfo_1.csv --progress broker_progress_1.json --slice :6320 --cdp http://127.0.0.1:9223
#   sh/run_supervised.sh py/trades_backfill.py data/state/trades_backfill.log 80 -- --shallow-first --page-delay 4.0
cd "$(dirname "$0")/.."

SCRIPT="$1"; shift
LOG="$1"; shift
MAX=200
if [[ "$1" =~ ^[0-9]+$ ]]; then MAX="$1"; shift; fi
if [ "$1" = "--" ]; then shift; fi

PY=.venv/Scripts/python.exe

for i in $(seq 1 "$MAX"); do
  printf '\n=== SUPERVISED (%s) attempt %s/%s %s ===\n' "$SCRIPT" "$i" "$MAX" "$(date)" >> "$LOG"
  PYTHONIOENCODING=utf-8 "$PY" -u "$SCRIPT" "$@" >> "$LOG" 2>&1
  rc=$?
  printf '=== attempt %s EXITED rc=%s %s ===\n' "$i" "$rc" "$(date)" >> "$LOG"
  [ "$rc" = "0" ] && break
  sleep 90
done
printf '=== SUPERVISOR (%s) finished %s ===\n' "$SCRIPT" "$(date)" >> "$LOG"
