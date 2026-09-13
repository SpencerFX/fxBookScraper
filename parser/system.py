"""Parse a myfxbook system (member) page.

Sources, all reachable once Cloudflare is cleared in the attached browser:
  * stats     -> the 5 `table.table-small` blocks in the member-page HTML
  * trades    -> POST /systemPageGetHistoryFirstPage.json  (+ paging) -> content.history HTML
  * daily     -> GET  /private/charts.json?chartType=1&accountOid=<id>&...  (Highcharts series)
"""

import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from parser.stats import (
    STAT_LABELS, clean_text, number, money, parse_ts, parse_duration_seconds,
)


# --------------------------------------------------------------------------- stats

def _label_field(label):
    if not label:
        return None
    key = clean_text(label).lower().strip().rstrip(":").strip()
    if key in STAT_LABELS:
        return STAT_LABELS[key]
    for lbl, mapping in STAT_LABELS.items():
        if key == lbl or key.startswith(lbl + " ") or lbl == key.rstrip(" :"):
            return mapping
    return None


def parse_stats(html):
    soup = BeautifulSoup(html, "lxml")
    out = {}

    blocks = soup.find_all("table", class_=lambda c: c and "table-small" in c)
    rows = []
    for t in blocks:
        for tr in t.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if len(cells) >= 2:
                rows.append((clean_text(cells[0].get_text(" ")),
                             clean_text(cells[1].get_text(" "))))

    for label, value in rows:
        mapping = _label_field(label)
        if not mapping or value in (None, "", "-"):
            continue
        field, coerce = mapping
        if field in out:
            continue
        try:
            out[field] = coerce(value)
        except Exception:
            out[field] = clean_text(value)

    # explicit id fallbacks
    for _id, field in (("statsBalance", "balance"), ("statsEquity", "equity")):
        el = soup.find(id=_id)
        if el and field not in out:
            out[field] = money(el.get_text(" "))

    # "Updated 59 seconds ago" isn't a timestamp; drop if non-parseable
    if isinstance(out.get("lastUpdate"), str) and "ago" in out["lastUpdate"].lower():
        out["lastUpdateText"] = out.pop("lastUpdate")
    return out


# ------------------------------------------------------------------------- trades

_TRADE_HEADER_MAP = {
    "open date": "openTime", "date open": "openTime", "open": "openTime",
    "close date": "closeTime", "date close": "closeTime", "close": "closeTime",
    "symbol": "symbol", "currency": "symbol", "action": "action", "type": "action",
    "size": "lots", "lots": "lots", "units": "lots", "volume": "lots",
    "sl": "sl", "t/p": "tp", "tp": "tp", "s/l": "sl",
    "open price": "openPrice", "close price": "closePrice",
    "pips": "pips", "profit": "profit", "gain": "gainPct", "%": "gainPct",
    "duration": "duration", "swap": "swap", "commission": "commission",
    "ticket": "ticket", "order": "ticket",
}
_NUM = {"lots", "sl", "tp", "openPrice", "closePrice", "pips", "profit", "gainPct",
        "swap", "commission"}
_TIME = {"openTime", "closeTime"}


def _first_price(text):
    """SL/TP cells look like '4,372.83 3,080.0 305.8' or '- - -'."""
    m = re.search(r"-?[\d,]+\.\d+", text or "")
    return number(m.group(0)) if m else None


_ACTION_WORDS = {"buy", "sell", "buy limit", "sell limit", "buy stop", "sell stop"}


def parse_trades_fragment(fragment_html):
    """The myfxbook history table (#tradingHistoryTable). The two date columns each
    render two <td> (order time + fill time) and there are two trailing icon <td>.
    Some accounts additionally render an extra leading icon <td> before the date
    columns, so columns are anchored dynamically off the Action cell (identified by
    content, "buy"/"sell"/...) rather than by a fixed index - a fixed-index read
    silently shifted symbol/action/lots/sl/tp by one column on those accounts
    (symbol became a date string, action became the real symbol).

    row: [<icon>?, openOrder, openFill, closeOrder, closeFill, Symbol, Action, Lots,
          SL(px pips), TP(px pips), OpenPrice, ClosePrice, Pips, Profit, Duration,
          Gain, <icon>, <icon>]
    """
    if not fragment_html:
        return []
    soup = BeautifulSoup(fragment_html, "lxml")
    table = soup.find("table", id="tradingHistoryTable")
    if table is None:
        for t in soup.find_all("table"):
            heads = [clean_text(th.get_text(" ")).lower() for th in t.find_all("th")]
            if sum(h in _TRADE_HEADER_MAP for h in heads) >= 4 and "symbol" in heads:
                table = t
                break
    if table is None:
        return []

    body = table.find("tbody") or table
    trades = []
    for tr in body.find_all("tr"):
        cells = [clean_text(td.get_text(" ")) for td in tr.find_all("td")]
        while cells and cells[-1] in ("", "-"):
            cells.pop()
        if len(cells) < 12:
            continue
        # anchor on the Action cell (buy/sell/...) instead of a fixed index - this
        # also correctly skips non-trade rows (balance/deposit/withdrawal) that
        # don't contain an action word at all.
        action_idx = next((i for i, c in enumerate(cells) if c.lower() in _ACTION_WORDS),
                           None)
        if action_idx is None or action_idx < 5:
            continue
        sym_idx = action_idx - 1
        sym = cells[sym_idx]
        if not sym:
            continue
        # tail (from right): gain=-1, duration=-2, profit=-3, pips=-4, close=-5, open=-6
        row = {
            "openTime": parse_ts(cells[sym_idx - 3]) or parse_ts(cells[sym_idx - 4]),
            "closeTime": parse_ts(cells[sym_idx - 1]) or parse_ts(cells[sym_idx - 2]),
            "symbol": sym,
            "action": cells[action_idx].lower() or None,
            "lots": number(cells[action_idx + 1]),
            "openPrice": number(cells[-6]),
            "closePrice": number(cells[-5]),
            "pips": number(cells[-4]),
            "profit": number(cells[-3]),
            "durationSec": parse_duration_seconds(cells[-2]),
            "gainPct": number(cells[-1]),
        }
        if len(cells) >= action_idx + 4:
            row["sl"] = _first_price(cells[action_idx + 2])
            row["tp"] = _first_price(cells[action_idx + 3])
        trades.append(row)
    return trades


def history_total(fragment_html):
    m = re.search(r'total=["\'](\d+)["\']', fragment_html or "")
    return int(m.group(1)) if m else None


# -------------------------------------------------------------------------- daily

_SERIES_FIELD = {
    "growth": "gain",
    "equity growth": "equityGrowth",
    "balance": "balance",
    "equity": "equity",
    "profit": "profit",
    "pips": "pips",
    "lots": "lots",
}
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _cat_to_date(cat):
    """'Aug 24, \\'26' / 'Aug 24, 2026' / '24 Aug 2026' -> ISO date string."""
    s = clean_text(cat).replace("'", "")
    m = re.search(r"([A-Za-z]{3})\w*\.?\s+(\d{1,2}),?\s+(\d{2,4})", s)
    if not m:
        m2 = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\w*\.?\s+(\d{2,4})", s)
        if not m2:
            return None
        day, mon, yr = m2.group(1), m2.group(2), m2.group(3)
    else:
        mon, day, yr = m.group(1), m.group(2), m.group(3)
    mi = _MONTHS.get(mon.lower()[:3])
    if not mi:
        return None
    yr = int(yr)
    if yr < 100:
        yr += 2000
    try:
        return datetime(yr, mi, int(day)).date().isoformat()
    except ValueError:
        return None


def parse_daily(charts_obj):
    """charts_obj: parsed /private/charts.json (chartType=1). Highcharts shape:
       {"categories":[...], "series":[{"name":..., "data":[[i,val],...]}, ...]}"""
    if not isinstance(charts_obj, dict):
        return []
    cats = charts_obj.get("categories") or []
    dates = [_cat_to_date(c) for c in cats]
    rows = {d: {"date": d} for d in dates if d}
    for ser in charts_obj.get("series") or []:
        field = _SERIES_FIELD.get(str(ser.get("name", "")).strip().lower())
        if not field:
            continue
        for point in ser.get("data") or []:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                idx, val = point[0], point[1]
            elif isinstance(point, dict):
                idx, val = point.get("x"), point.get("y")
            else:
                continue
            try:
                idx = int(idx)
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(dates) and dates[idx]:
                try:
                    rows[dates[idx]][field] = float(val)
                except (TypeError, ValueError):
                    pass
    return [rows[d] for d in sorted(rows)]


# ------------------------------------------------------------------------ combine

def build_parsed(stats_html, history_fragments, charts_obj, system_ref):
    trades = []
    for frag in history_fragments or []:
        trades.extend(parse_trades_fragment(frag))
    # dedupe by (ticket|openTime|symbol|closeTime|profit)
    seen, uniq = set(), []
    for t in trades:
        k = (t.get("ticket"), t.get("openTime"), t.get("symbol"),
             t.get("closeTime"), t.get("profit"))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(t)
    return {
        "system_id": system_ref["system_id"],
        "username": system_ref["username"],
        "system_name": system_ref["system_name"],
        "url": system_ref["url"],
        "stats": parse_stats(stats_html),
        "trades": uniq,
        "daily": parse_daily(charts_obj),
    }
