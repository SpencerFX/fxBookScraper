"""fxBookScraper — crawl myfxbook.com/systems into CSVs (and then a kdb+ HDB).

Prereq: a real Brave/Chrome running with a debug port, with myfxbook's Cloudflare
check solved once in it:

    & "C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe" --remote-debugging-port=9222
    # then open https://www.myfxbook.com/systems in it and pass the check

Typical use:

    python main.py --unlock            # navigate that browser to /systems, wait for a solve
    python main.py --max-pages 3       # smoke test (3 directory pages)
    python main.py                     # full directory crawl (resumable)
    python main.py --load              # crawl, then load CSVs into data/hdb

The crawl is resumable: it records progress under data/state/ and picks up where it
left off. Re-run after an interruption (or a Cloudflare re-solve) with the same args.
One manual solve covers a long run; the crawler pauses for another only if challenged.
"""

import argparse
import subprocess
import sys
import traceback
from pathlib import Path

import yaml

from collector.browser import Browser, CloudflareBlocked
from collector.directory import DirectoryCrawler
from collector.system import SystemCollector
from parser.system import build_parsed
from normalizer.normalize import (
    normalize_system_registry, normalize_snapshot, normalize_daily, normalize_trades,
)
from storage.csv_store import CsvStore
from storage.raw import save_raw_bundle
from storage.state import CrawlState

ROOT = Path(__file__).resolve().parent


def load_config(path="config.yaml"):
    with open(ROOT / path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_browser(config, args):
    if getattr(args, "cdp", None):
        config.setdefault("browser", {})["cdp_url"] = args.cdp
    return Browser(config)


def cmd_unlock(config, args):
    with build_browser(config, args) as browser:
        url = config["source"]["systems_url"]
        print(f"Navigating your Brave to {url} — solve Cloudflare in that window "
              f"if it appears.\n")
        try:
            browser.goto(url, wait_selector="#systemsContTable tbody tr")
        except CloudflareBlocked as exc:
            print(f"Not solved in time: {exc}")
            return 1
        if browser.looks_blocked():
            print("Still blocked.")
            return 1
        print("Cleared. cf cookies:", sorted(browser.cf_cookies()) or "(present, page loaded)")
        print("Now run:  python main.py --load")
    return 0


def cmd_probe(config, args):
    out = ROOT / "data" / "probe"
    out.mkdir(parents=True, exist_ok=True)
    with build_browser(config, args) as browser:
        for url in args.probe:
            html, _ = browser.goto(url)
            tag = url.rstrip("/").split("/")[-1].split("?")[0] or "page"
            (out / f"{tag}.html").write_text(html, encoding="utf-8")
            print(f"{url}\n  -> data/probe/{tag}.html ({len(html)} bytes)")
    return 0


def run_load(config):
    q_exe = config.get("kdb", {}).get("q_exe", "q")
    hdb = str(ROOT / config["storage"]["hdb_dir"])
    csv_dir = str(ROOT / config["storage"]["csv_dir"])
    cmd = [q_exe, str(ROOT / "q" / "load.q"), "-hdb", hdb, "-csv", csv_dir, "-q"]
    print("[load]", " ".join(cmd))
    return subprocess.call(cmd)


def crawl(config, args):
    state = CrawlState(ROOT / config["storage"]["state_dir"])
    store = CsvStore(ROOT / config["storage"]["csv_dir"])
    raw_dir = ROOT / config["storage"]["raw_dir"]
    min_recheck = config["collector"]["min_recheck_hours"]

    if args.reset_progress:
        state.reset_progress()

    with build_browser(config, args) as browser:
        crawler = DirectoryCrawler(browser, config["source"]["base_url"],
                                   config["source"]["systems_url"])
        collector = SystemCollector(browser, config)

        base = config["source"]["base_url"]

        def blind(system_id):
            """A work item for an id we have no directory row for yet."""
            row = store.get_system(system_id)
            if row:
                return {"system_id": int(system_id), "username": row["username"],
                        "system_name": row["systemName"],
                        "display_name": row.get("displayName"), "url": row["url"]}
            return {"system_id": int(system_id), "username": "_", "system_name": "_",
                    "url": f"{base}/members/_/_/{system_id}"}

        # -- decide the work list --------------------------------------------
        if args.systems:
            systems = [blind(int(x)) for x in args.systems.split(",") if x.strip()]
        elif state.next_pending() and not args.rediscover:
            systems = [blind(i) for i in state.next_pending()]
            print(f"[crawl] resuming: {len(systems)} systems still pending")
        else:
            max_pages = args.max_pages if args.max_pages is not None \
                else config["collector"]["max_pages"]

            def _checkpoint(page_no, found):
                for s in found:
                    store.upsert_system(normalize_system_registry(s))
                store.flush()
                state.set_pending([s["system_id"] for s in found])

            systems = crawler.discover(max_pages=max_pages, on_page=_checkpoint)
            _checkpoint(None, systems)
            print(f"[crawl] discovered {len(systems)} systems")

        by_id = {s["system_id"]: s for s in systems}
        work = list(by_id.values())
        if args.limit:
            work = work[:args.limit]

        # -- per-system collection -----------------------------------------
        ok = err = skipped = 0
        for n, system in enumerate(work, 1):
            sid = system["system_id"]
            if not args.force and not args.systems and \
                    state.recently_collected(sid, min_recheck):
                skipped += 1
                state.mark_done(sid)
                continue

            print(f"[{n}/{len(work)}] system {sid} {system.get('system_name', '')}")
            try:
                snap = collector.collect(system,
                                         want_history=not args.no_history,
                                         want_daily=not args.no_daily)
                # backfill identity from the resolved URL if we came in blind
                system.setdefault("username", "_")
                save_raw_bundle(raw_dir, sid, snap)

                parsed = build_parsed(
                    snap["stats_html"], snap["history_fragments"],
                    snap["charts_obj"], system)

                store.upsert_system(normalize_system_registry(system))
                store.add_snapshot(normalize_snapshot(system, parsed, ts=snap["collected_at"]))
                d = store.add_daily(normalize_daily(system, parsed))
                t = store.add_trades(normalize_trades(system, parsed,
                                                      collected_at=snap["collected_at"]))
                store.flush()
                state.mark_collected(sid)
                state.mark_done(sid)
                ok += 1
                print(f"      stats={len(parsed['stats'])} fields, "
                      f"+{d} daily rows, +{t} trades")
            except CloudflareBlocked as exc:
                print(f"\n[crawl] Cloudflare blocked: {exc}")
                print("[crawl] progress saved — re-run `python main.py` to resume.")
                store.flush()
                return 2
            except Exception as exc:  # noqa: BLE001 - keep the crawl going
                err += 1
                print(f"      ERROR {sid}: {exc}")
                if args.debug:
                    traceback.print_exc()

        store.flush()
        print(f"\n[crawl] done: {ok} ok, {skipped} skipped (recent), {err} errors")
        print(f"[crawl] csv counts: {store.counts}")

    if args.load:
        rc = run_load(config)
        if rc != 0:
            print(f"[load] q exited {rc}")
            return rc
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unlock", action="store_true",
                    help="headful: open /systems so you can solve Cloudflare once")
    ap.add_argument("--probe", nargs="+", metavar="URL",
                    help="fetch URL(s), dump HTML + JSON captures to data/probe/")
    ap.add_argument("--max-pages", type=int, default=None,
                    help="limit directory pages crawled (default: config, 0 = all)")
    ap.add_argument("--limit", type=int, default=None,
                    help="only collect the first N systems this run")
    ap.add_argument("--systems", type=str, default=None,
                    help="comma-separated system IDs to collect (skips discovery)")
    ap.add_argument("--force", action="store_true",
                    help="re-collect even if collected within min_recheck_hours")
    ap.add_argument("--rediscover", action="store_true",
                    help="ignore a saved pending queue; re-crawl the directory")
    ap.add_argument("--reset-progress", action="store_true",
                    help="clear the resumable-crawl progress file first")
    ap.add_argument("--cdp", type=str, default=None,
                    help="DevTools URL of your running Brave (default http://127.0.0.1:9222)")
    ap.add_argument("--no-history", action="store_true", help="skip closed-trades history")
    ap.add_argument("--no-daily", action="store_true", help="skip the daily series")
    ap.add_argument("--load", action="store_true",
                    help="after crawling, load the CSVs into data/hdb via q/load.q")
    ap.add_argument("--debug", action="store_true", help="print tracebacks on errors")
    args = ap.parse_args(argv)

    config = load_config()

    if args.unlock:
        return cmd_unlock(config, args)
    if args.probe:
        return cmd_probe(config, args)
    return crawl(config, args)


if __name__ == "__main__":
    sys.exit(main())
