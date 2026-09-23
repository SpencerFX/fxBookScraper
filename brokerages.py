"""Scrape each myfxbook system's brokerage/account-info line into brokerages.csv.

The system page (member page) renders a one-line account summary near the top:

    Real             (JPY), MYFX Markets, 1:400, MetaTrader 4
    Real             (USD), Vantage Markets, Technical, Automated, 1:500, MetaTrader 4

parsed by parser.system.parse_account_info into accountType/currency/broker/
brokerSlug/brokerId/leverage/platform/tags. It is NOT on the trader's profile
page (/members/<username>) - that page's per-system mini-boxes only repeat
accountType/leverage/platform, no broker name.

One page nav per system (no history pagination needed), so this is much
lighter than trades_backfill.py/losing_accounts.py. Target universe defaults
to the union of systems.csv (main directory) and losing_discovery.json (the
losing-accounts filter list), deduped by systemId, so one run/supervisor
covers systems seen by any of the three trade-history pipelines.

Progress is checkpointed in data/state/brokerages_progress.json (done by
systemId), so a re-run only fetches systems it hasn't already collected;
--force re-fetches everything. brokerages.csv is upserted by systemId
(rewritten on flush, same pattern as systems.csv).

Usage:
    .venv/Scripts/python.exe brokerages.py
    .venv/Scripts/python.exe brokerages.py --systems 7043279,12137904
    .venv/Scripts/python.exe brokerages.py --limit 20
    .venv/Scripts/python.exe brokerages.py --force

Two non-overlapping concurrent instances (same pattern as losing_accounts.py's
forward/reverse split - the index slice, not run order, guarantees disjoint work):
    .venv/Scripts/python.exe brokerages.py --slice :913
    .venv/Scripts/python.exe brokerages.py --slice 913: --reverse \\
        --out brokerages_reverse.csv --progress brokerages_progress_reverse.json
"""

import argparse
import csv
import json
import os
import sys
import time
import random
import traceback
from datetime import datetime, timezone
from pathlib import Path

import yaml

from collector.browser import Browser, CloudflareBlocked
from parser.system import parse_account_info

ROOT = Path(__file__).resolve().parent

FIELDS = ["systemId", "username", "systemName", "url", "accountType", "currency",
          "broker", "brokerSlug", "brokerId", "leverage", "platform", "tags",
          "collectedAt"]


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def load_config():
    with open(ROOT / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# --------------------------------------------------------------------------- targets

def _load_systems_csv(path):
    out = []
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            out.append({
                "system_id": int(r["systemId"]),
                "username": r.get("username") or "_",
                "system_name": r.get("systemName") or "_",
                "url": r.get("url") or f"https://www.myfxbook.com/members/_/_/{r['systemId']}",
            })
    return out


def _load_discovery_json(path):
    out = []
    if not path.exists():
        return out
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return out
    for r in data:
        out.append({
            "system_id": int(r["system_id"]),
            "username": r.get("username") or "_",
            "system_name": r.get("system_name") or "_",
            "url": r.get("url") or f"https://www.myfxbook.com/members/_/_/{r['system_id']}",
        })
    return out


def iter_targets(state_dir, csv_dir, args):
    if args.systems:
        want = {s.strip() for s in args.systems.split(",") if s.strip()}
        return [{"system_id": int(w), "username": "_", "system_name": "_",
                 "url": f"https://www.myfxbook.com/members/_/_/{w}"} for w in want]

    if getattr(args, "discovery", None):
        # scoped to ONE filter's discovery file, in the file's own order (a filter
        # sorted ascending by gain already lists the biggest losers first - preserve
        # that instead of re-sorting by systemId).
        by_id = {}
        for r in _load_discovery_json(Path(state_dir) / args.discovery):
            by_id.setdefault(r["system_id"], r)
        return list(by_id.values())

    by_id = {}
    for r in _load_systems_csv(Path(csv_dir) / "systems.csv"):
        by_id[r["system_id"]] = r
    for r in _load_discovery_json(Path(state_dir) / "losing_discovery.json"):
        by_id.setdefault(r["system_id"], r)
    return sorted(by_id.values(), key=lambda r: r["system_id"])


# --------------------------------------------------------------------------- store

class BrokerageStore:
    """Upsert-by-systemId CSV, same rewrite-on-flush pattern as systems.csv."""

    def __init__(self, path):
        self.path = Path(path)
        self.rows = {}
        if self.path.exists():
            with self.path.open("r", encoding="utf-8", newline="") as f:
                for r in csv.DictReader(f):
                    self.rows[r["systemId"]] = r

    def upsert(self, rec):
        row = {k: ("" if rec.get(k) is None else str(rec.get(k))) for k in FIELDS}
        self.rows[row["systemId"]] = row

    def flush(self):
        tmp = self.path.with_suffix(".csv.tmp")
        with tmp.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            for row in self.rows.values():
                w.writerow(row)
        os.replace(tmp, self.path)

    def __len__(self):
        return len(self.rows)


class Progress:
    def __init__(self, path):
        self.path = Path(path)
        self.data = {}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self.data = {}

    def done(self, sid):
        return bool(self.data.get(str(sid), {}).get("done"))

    def set(self, sid, **kw):
        row = self.data.setdefault(str(sid), {})
        row.update(kw)
        row["updated"] = _utcnow()
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)


# ---------------------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--systems", help="comma-separated system IDs (default: systems.csv + losing_discovery.json, deduped)")
    ap.add_argument("--discovery", help="scope the target list to ONE filter's discovery JSON under data/state/ (e.g. losing_discovery_expanded.json), in that file's own order, instead of the default systems.csv + losing_discovery.json union")
    ap.add_argument("--limit", type=int, help="process at most N systems this run")
    ap.add_argument("--force", action="store_true", help="re-fetch even if already done")
    ap.add_argument("--slice", help="python-slice-style START:END index partition of the target list (applied BEFORE --reverse), for running concurrent instances without overlap - the index slice, not run order, is what guarantees two instances never touch the same system")
    ap.add_argument("--reverse", action="store_true", help="walk the target list back-to-front")
    ap.add_argument("--out", default="brokerages.csv", help="output CSV filename under data/csv (default brokerages.csv) - give a concurrent instance its own file")
    ap.add_argument("--progress", default="brokerages_progress.json", help="progress checkpoint filename under data/state (default brokerages_progress.json) - give a concurrent instance its own file")
    ap.add_argument("--nav-delay", type=float, default=None, help="seconds between navigations (default config request_delay_seconds)")
    ap.add_argument("--cdp", help="DevTools URL of your running Brave")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args(argv)

    config = load_config()
    if args.cdp:
        config.setdefault("browser", {})["cdp_url"] = args.cdp
    if args.nav_delay is not None:
        config.setdefault("collector", {})["request_delay_seconds"] = args.nav_delay
    config.setdefault("browser", {})["new_tab"] = True

    csv_dir = ROOT / config["storage"]["csv_dir"]
    state_dir = ROOT / config["storage"]["state_dir"]
    csv_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)

    store = BrokerageStore(csv_dir / args.out)
    prog = Progress(state_dir / args.progress)

    targets = iter_targets(state_dir, csv_dir, args)
    if args.slice:
        lo, _, hi = args.slice.partition(":")
        lo = int(lo) if lo else None
        hi = int(hi) if hi else None
        targets = targets[lo:hi]
    if args.reverse:
        targets = list(reversed(targets))
    print(f"[brokerages] {len(targets)} candidate systems, {len(store)} already in CSV", flush=True)

    done = ok = skipped = errors = 0
    cf_deferred = set()
    cf_streak = 0

    with Browser(config) as browser:
        for n, sysd in enumerate(targets, 1):
            if args.limit and done >= args.limit:
                break
            sid = sysd["system_id"]
            if not args.force and prog.done(sid):
                skipped += 1
                continue

            done += 1
            print(f"[{n}/{len(targets)}] system {sid} {sysd['system_name']}", flush=True)
            try:
                html, _ = browser.goto(sysd["url"])
                cf_streak = 0
                info = parse_account_info(html)
                if info is None:
                    print("      account-info block not found", flush=True)
                    prog.set(sid, done=True, found=False)
                    continue

                rec = dict(info)
                rec.update({
                    "systemId": sid,
                    "username": sysd["username"],
                    "systemName": sysd["system_name"],
                    "url": sysd["url"],
                    "collectedAt": _utcnow(),
                })
                store.upsert(rec)
                store.flush()
                prog.set(sid, done=True, found=True, broker=info.get("broker"))
                ok += 1
                print(f"      {info.get('broker')!r} {info.get('leverage')} "
                      f"{info.get('platform')} ({info.get('accountType')}/{info.get('currency')})",
                      flush=True)

            except CloudflareBlocked as exc:
                cf_deferred.add(str(sid))
                cf_streak += 1
                print(f"\n[brokerages] Cloudflare blocked on {sid} - deferring "
                      f"(streak {cf_streak}): {exc}", flush=True)
                if cf_streak >= 8:
                    print("[brokerages] 8 CF blocks in a row - exiting so the "
                          "supervisor can back off", flush=True)
                    return 2
                continue
            except Exception as exc:  # noqa: BLE001
                errors += 1
                print(f"      ERROR {sid}: {exc}", flush=True)
                if args.debug:
                    traceback.print_exc()

            time.sleep(config.get("collector", {}).get("request_delay_seconds", 2.0)
                       * random.uniform(0.4, 0.9))

    print(f"\n[brokerages] processed {done}, ok {ok}, skipped(done) {skipped}, "
          f"errors {errors}, cf-deferred {len(cf_deferred)}", flush=True)
    return 2 if (cf_deferred or errors) else 0


if __name__ == "__main__":
    sys.exit(main())
