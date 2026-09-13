"""Turn parsed system data into flat, typed records for the CSV writers."""

import hashlib
from datetime import datetime, timezone


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def trade_key(system_id, trade):
    ticket = trade.get("ticket") or ""
    parts = [str(system_id), str(ticket), trade.get("openTime") or "",
             trade.get("symbol") or "", trade.get("action") or ""]
    if not ticket:
        parts += [str(trade.get("openPrice") or ""), str(trade.get("closePrice") or ""),
                  str(trade.get("closeTime") or "")]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()


SNAPSHOT_FIELDS = [
    "ts", "systemId", "username", "systemName", "gain", "absGain", "daily", "monthly",
    "drawdown", "balance", "equity", "equityPeak", "profit", "pips", "deposits",
    "withdrawals", "interest", "commissions", "profitFactor", "expectancyPips", "trades",
    "lots", "winRatePct", "avgWin", "avgLoss", "trackingSince", "firstTradeAt",
    "lastUpdate", "broker", "leverage", "currency", "accountType", "strategyName",
]

DAILY_FIELDS = ["systemId", "date", "balance", "equity", "gain", "profit", "pips",
                "lots", "floatingPL"]

TRADE_FIELDS = [
    "tradeKey", "systemId", "username", "systemName", "ticket", "symbol", "action",
    "openTime", "closeTime", "openPrice", "closePrice", "sl", "tp", "lots", "pips",
    "profit", "gainPct", "durationSec", "swap", "commission", "collectedAt",
]

SYSTEM_FIELDS = ["systemId", "username", "systemName", "displayName", "url",
                 "firstSeen", "lastSeen"]


def normalize_system_registry(system, now=None):
    now = now or _utcnow()
    return {
        "systemId": system["system_id"],
        "username": system["username"],
        "systemName": system["system_name"],
        "displayName": system.get("display_name") or system["system_name"],
        "url": system["url"],
        "firstSeen": now,
        "lastSeen": now,
    }


def normalize_snapshot(system, parsed, ts=None):
    ts = ts or _utcnow()
    stats = parsed.get("stats", {}) or {}
    row = {f: None for f in SNAPSHOT_FIELDS}
    row.update({k: v for k, v in stats.items() if k in row})
    row["ts"] = ts
    row["systemId"] = system["system_id"]
    row["username"] = system["username"]
    row["systemName"] = system["system_name"]
    return row


def normalize_daily(system, parsed):
    out = []
    for d in parsed.get("daily", []) or []:
        row = {f: None for f in DAILY_FIELDS}
        row.update({k: v for k, v in d.items() if k in row})
        row["systemId"] = system["system_id"]
        if row["date"]:
            out.append(row)
    return out


def normalize_trades(system, parsed, collected_at=None):
    collected_at = collected_at or _utcnow()
    out = []
    for t in parsed.get("trades", []) or []:
        row = {f: None for f in TRADE_FIELDS}
        row.update({k: v for k, v in t.items() if k in row})
        row["systemId"] = system["system_id"]
        row["username"] = system["username"]
        row["systemName"] = system["system_name"]
        row["tradeKey"] = trade_key(system["system_id"], t)
        row["collectedAt"] = collected_at
        out.append(row)
    return out
