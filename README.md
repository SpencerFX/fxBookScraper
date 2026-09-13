# fxBookScraper

Crawl the public [myfxbook.com/systems](https://www.myfxbook.com/systems) directory
and record each system's trading behaviour into CSVs and a standalone kdb+ HDB.

Captured per system:

| output | grain | contents |
|---|---|---|
| `data/csv/systems.csv`   | one row per system      | id, username, name, url, first/last seen |
| `data/csv/snapshots.csv` | one row per system per run | gain, abs gain, daily, monthly, drawdown, balance, equity, highest, profit, interest, deposits, withdrawals |
| `data/csv/daily.csv`     | one row per system per day | growth % (cumulative), pips, lots per day (from the growth chart feed) |
| `data/csv/trades.csv`    | one row per closed trade | symbol, action, open/close time & price, lots, sl, tp, pips, profit, gain %, duration |

## Why it drives your real browser

myfxbook is behind Cloudflare in "challenge every request" mode. Plain HTTP, headless
browsers, `cf_clearance` hand-off, and camoufox all get blocked. What works is
attaching to your **real Brave/Chrome** over the DevTools protocol: you solve
Cloudflare once, and the scraper then navigates that same browser. One solve covers a
long run; if Cloudflare challenges again mid-crawl the scraper pauses (no clicking)
until you solve it in the window, then resumes. Progress is checkpointed after every
system.

## Setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m patchright install chromium   # patchright's CDP client
```

## Run

```powershell
# 1. Fully quit Brave (check the tray), then relaunch it with a debug port:
& "C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe" --remote-debugging-port=9222

# 2. In that Brave, open https://www.myfxbook.com/systems and solve the Cloudflare check.

# 3. Crawl.
.\.venv\Scripts\python main.py --max-pages 3      # smoke test
.\.venv\Scripts\python main.py                    # full directory (~45 pages, resumable)
.\.venv\Scripts\python main.py --load             # crawl, then build data/hdb
```

Flags: `--systems 1234,5678` (skip discovery), `--limit N`, `--force` (ignore
`min_recheck_hours`), `--no-history`, `--no-daily`, `--rediscover` (re-crawl the
directory instead of resuming the pending queue), `--reset-progress`,
`--cdp http://127.0.0.1:9222`, `--debug`.

Resume state: `data/state/crawl_progress.json` (pending / done system ids),
`data/state/seen_systems.json` (last-collected time per system). Re-run `main.py`
with the same args to continue after any stop.

Config: `config.yaml` — CDP url, request delay, page caps, output paths.

## kdb+

`q/load.q` rebuilds an on-disk, date-partitioned HDB under `data/hdb/` from the four
CSVs. Idempotent — every touched partition is rewritten from the CSV each run.

```powershell
C:\q\w64\q.exe q\load.q -hdb data\hdb -csv data\csv
```

Tables: `sys` (registry splay), `snap` (partitioned by snapshot date), `daily`
(by date), `trade` (by close date). Explore:

```q
q)\l data/hdb
q)\l q/query.q
q).fx.leaderboard 20
q).fx.curve 12168354       / growth curve for a system
q).fx.blotter 12168354     / closed-trade blotter
q).fx.bySymbol 12168354    / per-symbol P/L
```

`q/ingest.q` has in-memory upsert helpers for tests / a future live feed.

## Layout

```
collector/  browser.py  (CDP attach + Cloudflare wait + same-origin fetch)
            directory.py (crawl /systems/N pagination)
            system.py    (member page + /systemPageGetHistoryFirstPage.json + /private/charts.json)
parser/     directory.py, stats.py, system.py
normalizer/ normalize.py  (typed records + deterministic tradeKey)
storage/    csv_store.py, state.py, raw.py
q/          schema.q, load.q, query.q, ingest.q
```

## Limits

- Directory pagination is `/systems/N` (path, not query). The default listing is
  Cloudflare/myfxbook's filtered "active real accounts" set (~700 systems), not every
  account ever.
- `daily.csv` carries growth % / pips / lots per day (from `charts.json?chartType=1`);
  it does not carry balance/equity in currency.
- Closed-trades history beyond page 1 depends on a paging endpoint that isn't
  confirmed; `history_max_pages` caps it and the crawl degrades gracefully to page 1.
- Open positions, live streaming, and scheduled runs are out of scope.
