"""Collect broker/account info (broker name, leverage, platform, currency,
account type) for every system in a saved discovery cache - one page load per
system, no trade-history pagination needed.

Reuses the same discovery cache the losing-accounts pipelines already built
(losing_discovery_expanded.json, 25,280 systems) rather than re-crawling the
filter. parser.system.parse_account_info() extracts the info from the
member page's "portfolio-resolve-account-type" block, e.g.:
    Real (USD), Vantage Markets, Technical, Automated, 1:500, MetaTrader 4

Usage:
    .venv/Scripts/python.exe broker_info.py
    .venv/Scripts/python.exe broker_info.py --slice :6320 --cdp http://127.0.0.1:9222

Shard into N by giving each instance its own --slice/--progress/--out/--cdp,
same non-overlap convention as losing_accounts.py.
"""

import argparse
import csv
import json
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import yaml

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.browser import Browser, CloudflareBlocked
from parser.system import parse_account_info

ROOT = Path(__file__).resolve().parent.parent

FIELDS = ["systemId", "username", "systemName", "accountType", "currency",
          "broker", "brokerSlug", "brokerId", "leverage", "platform", "tags",
          "collectedAt"]


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


class BrokerInfoCsv:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seen = set()
        if self.path.exists():
            with self.path.open("r", encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    sid = row.get("systemId")
                    if sid:
                        self._seen.add(sid)

    def add(self, row):
        sid = str(row["systemId"])
        if sid in self._seen:
            return False
        self._seen.add(sid)
        new_file = not self.path.exists() or self.path.stat().st_size == 0
        with self.path.open("a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(FIELDS)
            w.writerow([row.get(k, "") for k in FIELDS])
        return True


class Progress:
    def __init__(self, path):
        self.path = Path(path)
        self.data = {}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self.data = {}

    def get(self, sid):
        return self.data.get(str(sid), {})

    def set(self, sid, **kw):
        row = self.data.setdefault(str(sid), {})
        row.update(kw)
        row["updated"] = _utcnow()
        self._save()

    def _save(self):
        tmp = self.path.with_suffix(".json.tmp")
        for attempt in range(5):
            try:
                tmp.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
                tmp.replace(self.path)
                return
            except OSError:
                time.sleep(0.3 * (attempt + 1))
        print(f"[broker] WARNING: could not persist {self.path.name}", flush=True)


def load_config(cdp=None):
    cfg = yaml.safe_load(open(ROOT / "config.yaml", encoding="utf-8"))
    cfg.setdefault("browser", {})["new_tab"] = True
    if cdp:
        cfg["browser"]["cdp_url"] = cdp
    return cfg


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--discovery", default="losing_discovery_expanded.json",
                    help="discovery cache filename under data/state/ to read systems from")
    ap.add_argument("--out", default="brokerInfo.csv",
                    help="output CSV filename under data/csv/")
    ap.add_argument("--progress", default="broker_progress.json",
                    help="progress state filename under data/state/")
    ap.add_argument("--force", action="store_true", help="ignore 'done' progress flags")
    ap.add_argument("--limit", type=int, help="process at most N systems this run")
    ap.add_argument("--slice", metavar="START:END",
                    help="hard-partition the discovery list by index before "
                         "processing, python-slice style - use this to run "
                         "multiple instances that never touch the same system")
    ap.add_argument("--systems", help="comma-separated system IDs (skip discovery list)")
    ap.add_argument("--cdp", help="DevTools URL of your running browser")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args(argv)

    config = load_config(args.cdp)
    state_dir = ROOT / config["storage"]["state_dir"]
    state_dir.mkdir(parents=True, exist_ok=True)
    csv_out = BrokerInfoCsv(ROOT / config["storage"]["csv_dir"] / args.out)
    prog = Progress(state_dir / args.progress)

    disc_path = state_dir / args.discovery
    systems = json.loads(disc_path.read_text(encoding="utf-8"))
    print(f"[broker] loaded {len(systems)} systems from {disc_path.name}", flush=True)

    if args.systems:
        want = {int(s) for s in args.systems.split(",") if s.strip()}
        systems = [s for s in systems if s["system_id"] in want]

    if args.slice:
        lo, _, hi = args.slice.partition(":")
        lo = int(lo) if lo else None
        hi = int(hi) if hi else None
        systems = systems[lo:hi]

    print(f"[broker] {len(systems)} target systems"
          f"{' slice='+args.slice if args.slice else ''}", flush=True)

    done = ok = skipped = errors = added_total = 0
    cf_deferred, cf_streak, error_streak = set(), 0, 0

    with Browser(config) as browser:
        for n, sysd in enumerate(systems, 1):
            if args.limit and done >= args.limit:
                break
            sid = sysd["system_id"]
            if str(sid) in cf_deferred:
                skipped += 1
                continue
            st = prog.get(sid)
            if st.get("done") and not args.force:
                skipped += 1
                continue

            done += 1
            if n == 1 or n % 25 == 0:
                print(f"[{n}/{len(systems)}] system {sid} "
                      f"{sysd.get('system_name', '')}", flush=True)

            try:
                html, _ = browser.goto(sysd["url"])
                info = parse_account_info(html)
                cf_streak = 0
                error_streak = 0

                if info is None:
                    prog.set(sid, populated=False, done=True)
                    continue

                row = {
                    "systemId": sid,
                    "username": sysd.get("username", ""),
                    "systemName": sysd.get("system_name", ""),
                    "collectedAt": _utcnow(),
                    **info,
                }
                added = csv_out.add(row)
                added_total += int(added)
                prog.set(sid, populated=True, done=True)
                ok += 1

            except CloudflareBlocked as exc:
                cf_deferred.add(str(sid))
                cf_streak += 1
                print(f"\n[broker] Cloudflare blocked on {sid} - deferring "
                      f"(streak {cf_streak}): {exc}", flush=True)
                if cf_streak >= 8:
                    print("[broker] 8 CF blocks in a row - exiting so a "
                          "supervisor can back off", flush=True)
                    return 2
                continue
            except Exception as exc:  # noqa: BLE001
                errors += 1
                error_streak += 1
                print(f"      ERROR {sid}: {exc}", flush=True)
                if args.debug:
                    traceback.print_exc()
                if error_streak >= 5:
                    print(f"[broker] {error_streak} errors in a row - likely a "
                          f"dead browser/tab - exiting so the supervisor can "
                          f"get a fresh one", flush=True)
                    return 2

    print(f"\n[broker] processed {done}, ok {ok}, skipped(done) {skipped}, "
          f"errors {errors}, cf-deferred {len(cf_deferred)}, "
          f"+{added_total} new rows -> {args.out}", flush=True)
    return 2 if (cf_deferred or errors) else 0


if __name__ == "__main__":
    raise SystemExit(main())
