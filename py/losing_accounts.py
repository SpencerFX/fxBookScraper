"""Discover myfxbook systems matching a saved filter (e.g. a "losing accounts"
search) and fully backfill their closed-trade history into a dedicated CSV,
separate from the main pipeline's data/csv/trades.csv.

Discovery: the filter URL's results list uses the same generic paging widget as
everything else on myfxbook (`GET /paging.html?pt=6&p=<N>&ts=<total>&...<filter
params>`). Page 1 is a normal navigation; parser/directory.py's parse_systems_page
/ last_page_number already understand the results table unchanged.

Collection: reuses collector.trades_backfill's TradeHistoryCollector to walk every
page of each system's closed-trade history (identical mechanism to trades_backfill.py).

Runs in its OWN browser tab (new_tab=True) so it can operate at the same time as
another run (e.g. trades_backfill.py) already driving the shared Brave instance --
they don't fight over navigating the same tab. They do share one Cloudflare
identity/IP though, so running both at once increases the overall challenge rate.

Usage:
    .venv/Scripts/python.exe losing_accounts.py
    .venv/Scripts/python.exe losing_accounts.py --limit 20
    .venv/Scripts/python.exe losing_accounts.py --systems 12049087,12164483

A second, independent filter (e.g. a wider drawdown/lastTraded net) gets its own
discovery cache, progress file and output CSV so it never touches the first's:
    .venv/Scripts/python.exe losing_accounts.py --filter-url "<url>" \\
        --discovery losing_discovery_expanded.json --out losingAccountsExpanded.csv \\
        --progress losing_progress_expanded.json
Systems are processed in the order the filter URL's own sort returns them - a
filter sorted ascending by gain (sb=19&st=1) already lists the biggest losers
first, so the default forward walk (no --reverse) naturally starts there.
"""

import argparse
import csv
import html as html_lib
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.browser import Browser, CloudflareBlocked
from parser.directory import parse_systems_page, last_page_number
from parser.system import parse_trades_fragment
from normalizer.normalize import normalize_trades, TRADE_FIELDS
from trades_backfill import TradeHistoryCollector, TradeBackfillIncomplete, _swap_page

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://www.myfxbook.com"

DEFAULT_FILTER_URL = (
    "https://www.myfxbook.com/systems?p=1&profitType=1&profitValue=-0.01&drawType=1"
    "&drawValue=50&profitabilityType=0&profitabilityValue=0&ageType=0&ageValue=30"
    "&systemType=0&tradingType=0&platformOid=0&serverOid=0&accountType=2"
    "&lastTraded=90&regulationType=1&tradesType=0&size=15&pt=6&sb=19&st=2"
    "&sb=19&st=2&sb=19&st=2"
)

_PAGING_PARAMS_RE = re.compile(r'params="([^"]*)"')


# --------------------------------------------------------------------- discovery

def _extract_params_template(html_text):
    """Find a paging-btn params="..." attribute for this results list. HTML-entity
    unescape FIRST (&amp; -> &), then check the decoded string - the raw markup has
    p=1&amp;ts=... so a raw-text regex for '&p=' never matches the escaped form."""
    for m in _PAGING_PARAMS_RE.finditer(html_text):
        cand = html_lib.unescape(m.group(1))
        if "pt=" in cand and re.search(r"[?&]p=\d+&", cand):
            return cand
    return None


def _save_discovery_checkpoint(path, total_pages, tmpl, discovered, next_page):
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps({
        "total_pages": total_pages, "tmpl": tmpl,
        "systems": list(discovered.values()), "next_page": next_page,
    }), encoding="utf-8")
    tmp.replace(path)


def discover_filtered(browser, filter_url, page_delay, on_page=None,
                       checkpoint_path=None, resume=None):
    """Walk every results page of the filter. Returns list of system dicts.

    A large filter (hundreds of result pages) takes long enough that a hung
    browser fetch (rare, but seen in practice - see collector.browser.fetch_text's
    AbortController fix) losing the whole run is a real cost. If `checkpoint_path`
    is given, progress (the paging template + systems found so far) is saved
    every 10 pages, and `resume` (that checkpoint's parsed JSON, if the caller
    found one on disk) restarts from `next_page` instead of page 1."""
    if resume:
        discovered = {s["system_id"]: s for s in resume["systems"]}
        total_pages = resume["total_pages"]
        tmpl = resume["tmpl"]
        start_page = resume["next_page"]
        print(f"[losing] resuming discovery from checkpoint: page {start_page}/"
              f"{total_pages}, {len(discovered)} systems already found", flush=True)
    else:
        html_text, _ = browser.goto(filter_url)
        systems = parse_systems_page(html_text, BASE_URL)
        discovered = {s["system_id"]: s for s in systems}
        total_pages = last_page_number(html_text) or 1
        print(f"[losing] filter reports {total_pages} result pages", flush=True)
        if on_page:
            on_page(1, total_pages, systems)
        tmpl = _extract_params_template(html_text)
        start_page = 2
        if checkpoint_path and tmpl:
            _save_discovery_checkpoint(checkpoint_path, total_pages, tmpl, discovered, start_page)

    if not tmpl:
        print("[losing] no pager params found - only page 1 available", flush=True)
        return list(discovered.values())

    for p in range(start_page, total_pages + 1):
        params = _swap_page(tmpl, p)
        status, body = browser.fetch_text("/paging.html" + params)
        if status != 200:
            print(f"[losing] discovery page {p}: status={status} - retrying once",
                  flush=True)
            time.sleep(5)
            status, body = browser.fetch_text("/paging.html" + params)
        page_systems = parse_systems_page(body or "", BASE_URL)
        for s in page_systems:
            discovered.setdefault(s["system_id"], s)
        if on_page:
            on_page(p, total_pages, page_systems)
        if checkpoint_path and (p % 10 == 0 or p == total_pages):
            _save_discovery_checkpoint(checkpoint_path, total_pages, tmpl, discovered, p + 1)
        if p % 10 == 0 or p == total_pages:
            print(f"[losing] discovery {p}/{total_pages}: "
                  f"{len(discovered)} systems so far", flush=True)
        time.sleep(page_delay)

    return list(discovered.values())


# --------------------------------------------------------------------------- csv

def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


class LosingTradesCsv:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fields = TRADE_FIELDS
        self._keys = set()
        if self.path.exists():
            with self.path.open("r", encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    k = row.get("tradeKey")
                    if k:
                        self._keys.add(k)

    def add(self, rows):
        fresh = []
        for r in rows:
            k = r["tradeKey"]
            if k in self._keys:
                continue
            self._keys.add(k)
            fresh.append(r)
        if not fresh:
            return 0
        new_file = not self.path.exists() or self.path.stat().st_size == 0
        with self.path.open("a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(self.fields)
            for r in fresh:
                w.writerow([_fmt(r.get(k)) for k in self.fields])
        return len(fresh)


# ---------------------------------------------------------------------- progress

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
        row["updated"] = datetime.now(timezone.utc).isoformat()
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
        # last resort: leave the previous file intact rather than crash the run
        print(f"[losing] WARNING: could not persist {self.path.name}", flush=True)


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- main

def load_config(cdp=None):
    cfg = yaml.safe_load(open(ROOT / "config.yaml", encoding="utf-8"))
    cfg.setdefault("browser", {})["new_tab"] = True  # never share a tab
    if cdp:
        cfg["browser"]["cdp_url"] = cdp
    return cfg


def _existing_system_ids(root):
    """systemIds already covered by the main directory crawl (systems.csv) and the
    original narrower losing-accounts filter (losing_discovery.json) - the two
    universes every other pipeline is already ingesting."""
    ids = set()
    p = root / "data" / "csv" / "systems.csv"
    if p.exists():
        with p.open("r", encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                try:
                    ids.add(int(r["systemId"]))
                except (KeyError, ValueError, TypeError):
                    pass
    p2 = root / "data" / "state" / "losing_discovery.json"
    if p2.exists():
        try:
            for r in json.loads(p2.read_text(encoding="utf-8")):
                ids.add(int(r["system_id"]))
        except Exception:
            pass
    return ids


def run_discovery(browser, args, state_dir):
    disc_path = state_dir / args.discovery
    if disc_path.exists() and not args.rediscover:
        systems = json.loads(disc_path.read_text(encoding="utf-8"))
        print(f"[losing] using saved discovery: {len(systems)} systems "
              f"(--rediscover to re-crawl the filter)", flush=True)
        return systems

    def checkpoint(page, total_pages, found):
        pass  # discover_filtered already prints progress; nothing extra to persist per-page

    ckpt_path = state_dir / (args.discovery + ".partial")
    resume = None
    if ckpt_path.exists() and not args.rediscover:
        try:
            resume = json.loads(ckpt_path.read_text(encoding="utf-8"))
        except Exception:
            resume = None

    systems = discover_filtered(browser, args.filter_url, page_delay=args.page_delay,
                                on_page=checkpoint, checkpoint_path=ckpt_path, resume=resume)
    if args.exclude_existing:
        existing = _existing_system_ids(ROOT)
        before = len(systems)
        systems = [s for s in systems if s["system_id"] not in existing]
        print(f"[losing] excluded {before - len(systems)} systems already covered by "
              f"systems.csv/losing_discovery.json - {len(systems)} new systems remain",
              flush=True)
    disc_path.write_text(json.dumps(systems, indent=1), encoding="utf-8")
    try:
        ckpt_path.unlink()
    except FileNotFoundError:
        pass
    print(f"[losing] discovery done: {len(systems)} systems -> {disc_path.name}",
          flush=True)
    return systems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--filter-url", default=DEFAULT_FILTER_URL,
                    help="myfxbook /systems search URL with filter query params")
    ap.add_argument("--systems", help="comma-separated system IDs (skip discovery)")
    ap.add_argument("--systems-file", help="file of system IDs, one per line, processed in "
                    "file order (skip discovery) - for lists too long for the command line")
    ap.add_argument("--dedupe-against", action="append", default=[], metavar="GLOB",
                    help="glob under data/csv/ of existing trade CSVs (repeatable); tradeKeys "
                         "already in them, for THIS run's systems, are never written again. "
                         "Use when resuming past a previously-capped page range, since "
                         "history shifts as a live system closes new trades")
    ap.add_argument("--limit", type=int, help="process at most N systems this run")
    ap.add_argument("--force", action="store_true", help="ignore 'done' progress flags")
    ap.add_argument("--rediscover", action="store_true",
                    help="ignore saved discovery, re-crawl the filter results")
    ap.add_argument("--discovery", default="losing_discovery.json",
                    help="discovery cache filename under data/state/ (default "
                         "losing_discovery.json) - give a different filter its own file "
                         "so multiple filter-based pipelines don't clobber each other")
    ap.add_argument("--exclude-existing", action="store_true",
                    help="drop any freshly-discovered system already present in "
                         "systems.csv or losing_discovery.json (the main directory + "
                         "the original narrower losing filter) - use this for a new, "
                         "wider filter so it doesn't re-ingest systems another pipeline "
                         "already owns. Only applied on a fresh crawl, not a cached "
                         "discovery file (use --rediscover to recompute).")
    ap.add_argument("--page-delay", type=float, default=4.0,
                    help="seconds between /paging.html fetches (default 4.0)")
    ap.add_argument("--max-pages", type=int, default=0, help="cap pages per system")
    ap.add_argument("--cdp", help="DevTools URL of your running Brave")
    ap.add_argument("--out", default="losingAccounts.csv",
                    help="output CSV filename under data/csv/ (default losingAccounts.csv)")
    ap.add_argument("--progress", default="losing_progress.json",
                    help="progress state filename under data/state/ (default "
                         "losing_progress.json) - give a second concurrent run its own "
                         "file, the Progress class isn't safe to share across processes")
    ap.add_argument("--reverse", action="store_true",
                    help="walk the (possibly --slice'd) systems list back-to-front")
    ap.add_argument("--slice", metavar="START:END",
                    help="hard-partition the discovered systems list by index before "
                         "processing, python-slice style e.g. ':582' or '582:' - use this "
                         "to run two instances that can never touch the same system, "
                         "rather than relying on --reverse timing to avoid overlap")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args(argv)

    config = load_config(args.cdp)
    config.setdefault("collector", {})["history_page_delay_seconds"] = args.page_delay
    state_dir = ROOT / config["storage"]["state_dir"]
    state_dir.mkdir(parents=True, exist_ok=True)
    csv_out = LosingTradesCsv(ROOT / config["storage"]["csv_dir"] / args.out)
    prog = Progress(state_dir / args.progress)

    cf_deferred, cf_streak = set(), 0
    error_streak = 0
    done = ok = skipped = gaps = errors = added_total = 0

    with Browser(config) as browser:
        coll = TradeHistoryCollector(browser, config)

        if args.systems or args.systems_file:
            if args.systems_file:
                ids = [ln.strip() for ln in
                       Path(args.systems_file).read_text(encoding="utf-8").splitlines()
                       if ln.strip()]
            else:
                ids = [s.strip() for s in args.systems.split(",") if s.strip()]
            systems = [{"system_id": int(s), "username": "_", "system_name": "_",
                       "url": f"{BASE_URL}/members/_/_/{s}"} for s in ids]
        else:
            systems = run_discovery(browser, args, state_dir)

        if args.slice:
            lo, _, hi = args.slice.partition(":")
            lo = int(lo) if lo else None
            hi = int(hi) if hi else None
            systems = systems[lo:hi]

        if args.reverse:
            systems = list(reversed(systems))

        if args.dedupe_against:
            want = {str(s["system_id"]) for s in systems}
            csv.field_size_limit(10 ** 9)
            before = len(csv_out._keys)
            files = sorted({p for g in args.dedupe_against
                            for p in (ROOT / config["storage"]["csv_dir"]).glob(g)
                            if p.resolve() != csv_out.path.resolve()})
            for p in files:
                with p.open("r", encoding="utf-8", newline="") as f:
                    rd = csv.reader(f)
                    hdr = next(rd, None)
                    if not hdr:
                        continue
                    ik, isid = hdr.index("tradeKey"), hdr.index("systemId")
                    for row in rd:
                        if len(row) > isid and row[isid] in want:
                            csv_out._keys.add(row[ik])
            print(f"[losing] dedupe-against: {len(files)} files, "
                  f"{len(csv_out._keys) - before} existing tradeKeys for these "
                  f"{len(want)} systems", flush=True)

        print(f"[losing] {len(systems)} target systems"
              f"{' slice='+args.slice if args.slice else ''}"
              f"{' (reversed)' if args.reverse else ''}", flush=True)

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
            print(f"[{n}/{len(systems)}] system {sid} {sysd.get('system_name', '')} "
                  f"(list gain {sysd.get('list_gain')})", flush=True)

            try:
                frag1, total = coll.first_page(sid, sysd["url"])
                page1_trades = parse_trades_fragment(frag1) if frag1 else []
                cf_streak = 0
                error_streak = 0

                if not frag1 or not page1_trades or (total is not None and total == 0):
                    print("      history section empty / not populated", flush=True)
                    prog.set(sid, populated=False, total=total or 0, done=True)
                    continue

                resume_from = 1
                if st and not st.get("done"):
                    resume_from = max(2, int(st.get("pages_done", 1)) + 1)

                def on_page(p, last_page, trades, _sid=sid, _sysd=sysd):
                    nonlocal added_total
                    rows = normalize_trades(_sysd, {"trades": trades}, collected_at=_utcnow())
                    n_new = csv_out.add(rows)
                    added_total += n_new
                    prog.set(_sid, populated=True, total=total or 0, pages=last_page,
                             pages_done=p, done=False)
                    if p == 1 or p % 10 == 0 or p == last_page:
                        print(f"      page {p}/{last_page}  (+{n_new})", flush=True)

                max_pages = args.max_pages or None
                all_trades, last_page, hi = coll.walk(
                    sid, sysd["url"], frag1, total,
                    resume_from=resume_from, max_pages=max_pages, on_page=on_page)

                capped = bool(max_pages) and hi >= max_pages and hi < last_page
                complete = (not total) or hi >= last_page or capped
                prog.set(sid, populated=True, total=total or 0, pages=last_page,
                         pages_done=hi, done=bool(complete), capped=capped)
                ok += 1
                if not complete:
                    gaps += 1
                tag = "  (CAPPED)" if capped else ("" if complete else "  (INCOMPLETE)")
                print(f"      done over {hi}/{last_page} pages{tag}", flush=True)

            except CloudflareBlocked as exc:
                cf_deferred.add(str(sid))
                cf_streak += 1
                print(f"\n[losing] Cloudflare blocked on {sid} - deferring "
                      f"(streak {cf_streak}): {exc}", flush=True)
                if cf_streak >= 8:
                    print("[losing] 8 CF blocks in a row - exiting so a "
                          "supervisor can back off", flush=True)
                    return 2
                continue
            except TradeBackfillIncomplete as exc:
                errors += 1
                gaps += 1
                print(f"      INCOMPLETE {exc}", flush=True)
            except Exception as exc:  # noqa: BLE001
                errors += 1
                error_streak += 1
                print(f"      ERROR {sid}: {exc}", flush=True)
                if args.debug:
                    traceback.print_exc()
                # a dead tab/browser (e.g. "Target page, context or browser has
                # been closed") fails EVERY subsequent system for the rest of this
                # process - each failure can cost a full nav_timeout (~60s) with
                # zero progress, so grinding through thousands of remaining
                # systems this way can burn hours doing nothing. Bail early so
                # the supervisor relaunches with a fresh browser/tab instead.
                if error_streak >= 5:
                    print(f"[losing] {error_streak} errors in a row - likely a "
                          f"dead browser/tab - exiting so the supervisor can "
                          f"get a fresh one", flush=True)
                    return 2

    print(f"\n[losing] processed {done}, ok {ok}, skipped(done) {skipped}, "
          f"incomplete {gaps}, errors {errors}, cf-deferred {len(cf_deferred)}, "
          f"+{added_total} new trade rows -> {args.out}", flush=True)
    # rc 0 must mean "a real full pass with nothing left to retry" - gaps
    # (TradeBackfillIncomplete / walk() bailing early) and generic errors (e.g.
    # "Target page, context or browser has been closed" when the CDP tab/
    # browser drops mid-run) need another attempt just as much as a CF defer
    # does, otherwise the supervisor loop declares victory and stops while
    # systems are still sitting at done=false forever.
    return 2 if (cf_deferred or gaps or errors) else 0


if __name__ == "__main__":
    sys.exit(main())
