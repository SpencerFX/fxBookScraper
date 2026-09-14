"""Dedicated closed-trades backfill for myfxbook systems.

The main crawler (`main.py`) only grabs the first ~1-2 pages of a system's trade
history, so systems with hundreds of trades end up badly truncated. This script
walks *every* page of the history table for each system.

For each system it:
  1. navigates the attached Brave to the member page (clears Cloudflare),
  2. POSTs /systemPageGetHistoryFirstPage.json  -> checks the History section is
     actually populated (total > 0 and at least one row parses),
  3. reads the page count from the pager (`lastPage="true"`, else ceil(total/size)),
  4. GETs  /paging.html?pt=4&p=<N>&...  for every remaining page and parses it.

Trades stream into data/csv/trades.csv (insert-once by tradeKey). Progress is
checkpointed after every page in data/state/trades_progress.json, so a re-run
resumes mid-system. Cloudflare re-challenges pause for a manual solve in Brave.

Usage:
    .venv/Scripts/python.exe trades_backfill.py                 # all systems, fill gaps only
    .venv/Scripts/python.exe trades_backfill.py --systems 3534905
    .venv/Scripts/python.exe trades_backfill.py --recheck-all   # re-walk every page even if counts look complete
    .venv/Scripts/python.exe trades_backfill.py --limit 20 --load
"""

import argparse
import json
import math
import random
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import yaml

from collector.browser import Browser, CloudflareBlocked
from parser.system import parse_trades_fragment, history_total
from normalizer.normalize import normalize_trades
from storage.csv_store import CsvStore

ROOT = Path(__file__).resolve().parent

HISTORY_FIRST = "/systemPageGetHistoryFirstPage.json"
PAGING = "/paging.html"

_PARAMS_P1_RE = re.compile(r'params="([^"]*&p=1&[^"]*)"')
_LASTPAGE_RE = re.compile(r'page="(\d+)"\s+lastPage="true"')


class TradeBackfillIncomplete(RuntimeError):
    """A page fetch kept failing; caller should checkpoint and allow a resume."""


# --------------------------------------------------------------------------- util

def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def _fragment(data):
    if isinstance(data, dict) and not data.get("error"):
        c = data.get("content")
        if isinstance(c, dict):
            return c.get("history") or c.get("historyHtml")
        if isinstance(c, str):
            return c
    if isinstance(data, str):
        return data
    return None


def _sig(t):
    return (t.get("openTime"), t.get("symbol"), t.get("closeTime"),
            t.get("profit"), t.get("openPrice"))


def _swap_page(params, p):
    # params looks like "?pt=4&p=1&ts=2585&&id=..&start=2019-08-16 00:00&.."
    out = re.sub(r'(?<=[?&])p=\d+', f"p={p}", params)
    return out.replace(" ", "%20")


# ----------------------------------------------------------------------- progress

class TradeProgress:
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
        tmp.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
        tmp.replace(self.path)


# ---------------------------------------------------------------------- collector

class TradeHistoryCollector:
    def __init__(self, browser, config):
        self.browser = browser
        ccfg = config.get("collector", {}) or {}
        self.page_delay = float(ccfg.get("history_page_delay_seconds", 2.5))
        self.max_pages = int(ccfg.get("history_max_pages_full", 0)) or 100000

    # -- one system -------------------------------------------------------------

    def first_page(self, sid, url):
        """Navigate to the member page, pull history page 1. Returns
        (fragment_html | None, total:int|None)."""
        self.browser.goto(url)
        status, data = self.browser.fetch_json(HISTORY_FIRST, method="POST",
                                               form={"accountOid": sid})
        frag = _fragment(data)
        return frag, (history_total(frag) if frag else None)

    def walk(self, sid, url, frag1, total, resume_from=2,
             max_pages=None, on_page=None):
        """Walk pages resume_from..last. `frag1` is page 1's fragment.
        on_page(page_no, last_page, trades_list) fires after each parsed page
        (page 1 included when resume_from<=1)."""
        max_pages = max_pages or self.max_pages
        page1 = parse_trades_fragment(frag1)
        size = len(page1) or 20

        m = _LASTPAGE_RE.search(frag1)
        if m:
            last_page = int(m.group(1))
        elif total:
            last_page = max(1, math.ceil(total / size))
        else:
            last_page = 1

        pm = _PARAMS_P1_RE.search(frag1)
        tmpl = pm.group(1) if pm else None

        seen = set()
        all_trades = []
        if resume_from <= 1:
            for t in page1:
                if _sig(t) not in seen:
                    seen.add(_sig(t))
                    all_trades.append(t)
            if on_page:
                on_page(1, last_page, page1)

        if last_page <= 1 or tmpl is None:
            return all_trades, last_page, 1

        highest_done = max(1, resume_from - 1)
        empty_streak = 0
        for p in range(max(2, resume_from), last_page + 1):
            if p - 1 >= max_pages:
                break
            body = self._get_page(sid, url, tmpl, p)
            trades = parse_trades_fragment(body)
            new = [t for t in trades if _sig(t) not in seen]
            for t in new:
                seen.add(_sig(t))
            all_trades.extend(new)
            highest_done = p
            if on_page:
                on_page(p, last_page, trades)
            if not trades:
                # a single empty page isn't necessarily the end of history - a
                # page can legitimately be all balance/deposit/withdrawal rows
                # (which parse_trades_fragment correctly excludes) with real
                # trade pages still beyond it. Only bail after several empty
                # pages in a row; last_page (from myfxbook's own total) is
                # still the real loop bound either way.
                empty_streak += 1
                if empty_streak >= 3:
                    break
            else:
                empty_streak = 0
            time.sleep(self.page_delay + random.uniform(0, self.page_delay * 0.4))

        return all_trades, last_page, highest_done

    # -- one page, with retry + CF recovery -----------------------------------

    def _get_page(self, sid, url, tmpl, p, tries=4):
        params = _swap_page(tmpl, p)
        for attempt in range(tries):
            status, body = self.browser.fetch_text(PAGING + params)
            if status == 200 and "tradingHistoryTable" in body:
                return body
            # 403 (CF) / 429 (rate) / transient: back off, then re-clear via nav
            wait = min(30, 3 * (2 ** attempt))
            print(f"      page {p}: status={status} len={len(body or '')} "
                  f"- retry in {wait}s", flush=True)
            time.sleep(wait)
            if status in (403, 0) or attempt == 1:
                try:
                    self.browser.goto(url)  # forces a manual CF solve if needed
                except CloudflareBlocked:
                    raise
        raise TradeBackfillIncomplete(f"system {sid} page {p}: last status {status}")


# --------------------------------------------------------------------------- main

def load_config():
    with open(ROOT / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def iter_targets(store, args):
    """Yield {system_id, username, system_name, url} dicts to process."""
    rows = list(store._systems.values())
    if args.systems:
        want = {s.strip() for s in args.systems.split(",") if s.strip()}
        rows = [r for r in rows if str(r["systemId"]) in want]
        # allow ids not in systems.csv
        known = {str(r["systemId"]) for r in rows}
        for sid in want - known:
            rows.append({"systemId": sid, "username": "_", "systemName": "_",
                         "url": f"https://www.myfxbook.com/members/_/_/{sid}"})
    for r in rows:
        yield {
            "system_id": int(r["systemId"]),
            "username": r.get("username") or "_",
            "system_name": r.get("systemName") or "_",
            "url": r.get("url") or f"https://www.myfxbook.com/members/_/_/{r['systemId']}",
        }


def count_trades_by_system(store):
    """One pass over trades.csv -> {systemId(str): row count}."""
    import csv
    from collections import Counter
    p = store.paths["trades"]
    if not p.exists():
        return Counter()
    with p.open("r", encoding="utf-8", newline="") as f:
        return Counter(row.get("systemId", "") for row in csv.DictReader(f))


def saved_history_totals(raw_dir):
    """{systemId(str): total trades} read offline from each system's saved
    first-page history fragment (the `total="N"` attribute). Systems with no
    saved fragment are absent (callers treat them as 0 = process early)."""
    out = {}
    for frag in Path(raw_dir).glob("*/*.history.000.html"):
        try:
            txt = frag.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        m = re.search(r'total="(\d+)"', txt)
        if m:
            out[frag.parent.name] = int(m.group(1))
    return out


def run_load(config):
    import subprocess
    q_exe = config.get("kdb", {}).get("q_exe", "q")
    hdb = str(ROOT / config["storage"]["hdb_dir"])
    csv_dir = str(ROOT / config["storage"]["csv_dir"])
    cmd = [q_exe, str(ROOT / "q" / "load.q"), "-hdb", hdb, "-csv", csv_dir, "-q"]
    print("[load]", " ".join(cmd), flush=True)
    return subprocess.call(cmd)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--systems", help="comma-separated system IDs (default: all in systems.csv)")
    ap.add_argument("--limit", type=int, help="process at most N systems this run")
    ap.add_argument("--recheck-all", action="store_true",
                    help="re-walk every page even when the stored count already matches total")
    ap.add_argument("--force", action="store_true",
                    help="ignore trades_progress 'done' flags")
    ap.add_argument("--max-pages", type=int, default=0,
                    help="cap pages walked per system (0 = no cap)")
    ap.add_argument("--shallow-first", action="store_true",
                    help="process fewest-trades systems first (offline sort on the "
                         "total= in each saved history fragment; unknowns go first)")
    ap.add_argument("--page-delay", type=float, default=None,
                    help="seconds between page fetches (default config 2.5)")
    ap.add_argument("--cdp", help="DevTools URL of your running Brave")
    ap.add_argument("--load", action="store_true", help="run q/load.q afterwards")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args(argv)

    config = load_config()
    if args.cdp:
        config.setdefault("browser", {})["cdp_url"] = args.cdp
    if args.page_delay is not None:
        config.setdefault("collector", {})["history_page_delay_seconds"] = args.page_delay

    store = CsvStore(ROOT / config["storage"]["csv_dir"])
    raw_dir = ROOT / config["storage"]["raw_dir"]
    state_dir = ROOT / config["storage"]["state_dir"]
    prog = TradeProgress(state_dir / "trades_progress.json")

    # systems to leave alone this run (persistent Cloudflare gate, or deferred to a
    # dedicated --force pass). JSON list of id strings; auto-read if present.
    skip_set = set()
    skip_path = state_dir / "trades_skip.json"
    if skip_path.exists():
        try:
            skip_set = {str(x) for x in json.loads(skip_path.read_text(encoding="utf-8"))}
        except Exception:
            skip_set = set()
    if skip_set:
        print(f"[trades] skip-list: {len(skip_set)} systems held out", flush=True)

    targets = list(iter_targets(store, args))
    have_by_sid = count_trades_by_system(store)
    if args.shallow_first:
        totals = saved_history_totals(raw_dir)
        # known-small first, then unknowns (no saved fragment), then known-large.
        # 301 = just past the "quick" (<=~15 pages) band, so unknowns never delay
        # the genuine low-hanging fruit but a hidden big one still can't jump ahead.
        unknown_rank = 301
        targets.sort(key=lambda s: totals.get(str(s["system_id"]), unknown_rank))
        known = sum(1 for s in targets if str(s["system_id"]) in totals)
        print(f"[trades] shallow-first order: {known} known trade counts, "
              f"{len(targets) - known} unknown (slotted mid-queue)", flush=True)
    print(f"[trades] {len(targets)} candidate systems", flush=True)

    done = ok = skipped = gaps = errors = 0
    added_total = 0
    cf_deferred = set()          # systems whose page-1 nav hit Cloudflare this run
    cf_streak = 0                # consecutive CF blocks -> bail so supervisor cools off
    cf_path = state_dir / "trades_cf_deferred.json"

    with Browser(config) as browser:
        coll = TradeHistoryCollector(browser, config)
        for n, sysd in enumerate(targets, 1):
            if args.limit and done >= args.limit:
                break
            sid = sysd["system_id"]
            if str(sid) in skip_set or str(sid) in cf_deferred:
                skipped += 1
                continue
            st = prog.get(sid)
            if st.get("done") and not args.force and not args.recheck_all:
                skipped += 1
                continue

            done += 1
            have = have_by_sid.get(str(sid), 0)
            print(f"[{n}/{len(targets)}] system {sid} {sysd['system_name']} "
                  f"(have {have} trades)", flush=True)

            try:
                frag1, total = coll.first_page(sid, sysd["url"])
                page1_trades = parse_trades_fragment(frag1) if frag1 else []

                cf_streak = 0  # nav succeeded, CF isn't hard-blocking right now

                if not frag1 or not page1_trades or (total is not None and total == 0):
                    print("      history section empty / not populated", flush=True)
                    prog.set(sid, populated=False, total=total or 0,
                             pages=0, pages_done=0, trades=0, done=True)
                    continue

                if (total and have >= total and not args.recheck_all
                        and not args.force):
                    print(f"      already complete ({have}/{total}) - skip", flush=True)
                    prog.set(sid, populated=True, total=total, trades=have, done=True)
                    continue

                resume_from = 2
                if not args.recheck_all and st and not st.get("done"):
                    resume_from = max(2, int(st.get("pages_done", 1)) + 1)
                    if resume_from > 2:
                        print(f"      resuming from page {resume_from}", flush=True)
                else:
                    resume_from = 1  # fresh walk: include page 1

                sys_pages_raw = raw_dir / str(sid)
                sys_pages_raw.mkdir(parents=True, exist_ok=True)
                running = {"have": have}  # avoid re-scanning trades.csv each page

                def on_page(p, last_page, trades, _sid=sid, _sysd=sysd):
                    nonlocal added_total
                    parsed = {"trades": trades}
                    rows = normalize_trades(_sysd, parsed, collected_at=_utcnow())
                    n_new = store.add_trades(rows)
                    store.flush()
                    added_total += n_new
                    running["have"] += n_new
                    prog.set(_sid, populated=True, total=total or 0,
                             pages=last_page, pages_done=p,
                             trades=running["have"], done=False)
                    if p == 1 or p % 10 == 0 or p == last_page:
                        print(f"      page {p}/{last_page}  (+{n_new}, {running['have']} total)",
                              flush=True)

                max_pages = args.max_pages or None
                all_trades, last_page, hi = coll.walk(
                    sid, sysd["url"], frag1, total,
                    resume_from=resume_from, max_pages=max_pages, on_page=on_page)

                final_have = running["have"]
                complete = (not total) or final_have >= total or hi >= last_page
                prog.set(sid, populated=True, total=total or 0, pages=last_page,
                         pages_done=hi, trades=final_have, done=bool(complete))
                ok += 1
                cf_streak = 0
                if not complete:
                    gaps += 1
                print(f"      done: {final_have}/{total or '?'} trades over "
                      f"{hi}/{last_page} pages{'' if complete else '  (INCOMPLETE)'}",
                      flush=True)

            except CloudflareBlocked as exc:
                cf_deferred.add(str(sid))
                cf_streak += 1
                try:
                    cf_path.write_text(json.dumps(sorted(cf_deferred), indent=1),
                                       encoding="utf-8")
                except Exception:
                    pass
                store.flush()
                print(f"\n[trades] Cloudflare blocked on {sid} - deferring "
                      f"(streak {cf_streak}): {exc}", flush=True)
                if cf_streak >= 8:
                    print("[trades] 8 CF blocks in a row - exiting so the "
                          "supervisor can back off", flush=True)
                    return 2
                continue
            except TradeBackfillIncomplete as exc:
                errors += 1
                gaps += 1
                print(f"      INCOMPLETE {exc}", flush=True)
                store.flush()
            except Exception as exc:  # noqa: BLE001
                errors += 1
                print(f"      ERROR {sid}: {exc}", flush=True)
                if args.debug:
                    traceback.print_exc()

        store.flush()

    print(f"\n[trades] processed {done}, ok {ok}, skipped(done) {skipped}, "
          f"incomplete {gaps}, errors {errors}, cf-deferred {len(cf_deferred)}, "
          f"+{added_total} new trade rows", flush=True)
    if cf_deferred:
        print(f"[trades] cf-deferred systems -> {cf_path.name}: "
              f"{sorted(cf_deferred)}", flush=True)

    if args.load:
        rc = run_load(config)
        if rc != 0:
            print(f"[load] q exited {rc}", flush=True)
            return rc
    # non-zero so the supervisor loops back and retries the deferred systems
    # (a later pass catches them once Cloudflare relaxes). gaps (walk() bailing
    # early / TradeBackfillIncomplete) need a retry just as much as a CF defer
    # does - otherwise rc=0 declares victory while systems sit at done=false
    # forever and the supervisor stops relaunching.
    return 2 if (cf_deferred or gaps) else 0


if __name__ == "__main__":
    sys.exit(main())
