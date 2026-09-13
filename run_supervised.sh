#!/usr/bin/env bash
# Relaunch the shallow-first trades backfill until it completes (rc 0) or we
# exhaust attempts. Each run skips done systems and resumes partials from their
# page checkpoints, so a Cloudflare exit (rc 2) just costs the relaunch gap.
cd "$(dirname "$0")"
LOG=data/state/trades_backfill.log
PY=.venv/Scripts/python.exe
MAX=80
for i in $(seq 1 $MAX); do
  printf '\n=== SUPERVISED attempt %s/%s %s ===\n' "$i" "$MAX" "$(date)" >> "$LOG"
  PYTHONIOENCODING=utf-8 "$PY" -u trades_backfill.py --shallow-first --page-delay 4.0 >> "$LOG" 2>&1
  rc=$?
  printf '=== attempt %s EXITED rc=%s %s ===\n' "$i" "$rc" "$(date)" >> "$LOG"
  [ "$rc" = "0" ] && break
  sleep 90
done
printf '=== SUPERVISOR finished %s ===\n' "$(date)" >> "$LOG"
printf '=== q load + split_trades.py disabled for this session on request - CSV ingest only ===\n' >> "$LOG"
# PYTHONIOENCODING=utf-8 "$PY" -u -c "import yaml,subprocess,pathlib; c=yaml.safe_load(open('config.yaml')); r=pathlib.Path('.').resolve(); subprocess.call([c['kdb']['q_exe'], str(r/'q'/'load.q'), '-hdb', str(r/'data'/'hdb'), '-csv', str(r/'data'/'csv'), '-q'])" >> "$LOG" 2>&1
# PYTHONIOENCODING=utf-8 "$PY" split_trades.py >> "$LOG" 2>&1
printf '=== ALL DONE %s ===\n' "$(date)" >> "$LOG"
