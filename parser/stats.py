"""Coercion helpers + the member-page stats label map.

The member page renders its headline numbers as a set of label/value pairs (a table
or a definition list). `parse_stats` in parser/system.py collects those pairs; this
module maps the myfxbook labels onto our snapshot field names and coerces values.
"""

import re

from dateutil import parser as _dateparser


def clean_text(value):
    if value is None:
        return None
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def number(value):
    """First numeric token in the string as float, sign-aware. Strips , % $ and units."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = clean_text(str(value)).replace(",", "")
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    return float(m.group(0)) if m else None


def percent(value):
    """Like number(); percentages are stored as their bare numeric value (12.3 == 12.3%)."""
    return number(value)


def money(value):
    """Prefer a $-prefixed amount ('(100.00%) $10,969.75' -> 10969.75)."""
    if value is None:
        return None
    text = clean_text(str(value))
    m = re.findall(r"\$\s*(-?[\d,]+(?:\.\d+)?)", text)
    if m:
        return float(m[-1].replace(",", ""))
    return number(value)


def integer(value):
    n = number(value)
    return int(n) if n is not None else None


def parse_ts(value):
    if not value:
        return None
    try:
        return _dateparser.parse(clean_text(str(value))).isoformat()
    except Exception:
        return None


_DUR_RE = re.compile(
    r"(?:(\d+)\s*y)?\s*(?:(\d+)\s*mon?)?\s*(?:(\d+)\s*w)?\s*(?:(\d+)\s*d)?\s*"
    r"(?:(\d+)\s*h)?\s*(?:(\d+)\s*m(?:in)?)?\s*(?:(\d+)\s*s)?",
    re.I,
)
_DUR_UNITS = (365 * 86400, 30 * 86400, 7 * 86400, 86400, 3600, 60, 1)


def parse_duration_seconds(value):
    """'1d 04h 32m' / '3 hours' / '00:45:12' -> seconds (int), or None."""
    if not value:
        return None
    text = clean_text(str(value)).lower()
    hms = re.match(r"^(\d+):(\d{2}):(\d{2})$", text)
    if hms:
        h, m, s = map(int, hms.groups())
        return h * 3600 + m * 60 + s
    m = _DUR_RE.match(text)
    if not m or not any(m.groups()):
        return None
    total = 0
    for grp, unit in zip(m.groups(), _DUR_UNITS):
        if grp:
            total += int(grp) * unit
    return total or None


# myfxbook stat label (lower-cased, trimmed of trailing ':') -> (snapshot field, coercer)
STAT_LABELS = {
    "gain": ("gain", percent),
    "abs. gain": ("absGain", percent),
    "absolute gain": ("absGain", percent),
    "daily": ("daily", percent),
    "monthly": ("monthly", percent),
    "drawdown": ("drawdown", percent),
    "balance": ("balance", money),
    "equity": ("equity", money),
    "highest": ("equityPeak", money),
    "interest": ("interest", money),
    "profit": ("profit", money),
    "pips": ("pips", number),
    "deposits": ("deposits", money),
    "withdrawals": ("withdrawals", money),
    "interest": ("interest", money),
    "commissions": ("commissions", money),
    "profit factor": ("profitFactor", number),
    "expectancy": ("expectancyPips", number),
    "trades": ("trades", integer),
    "lots": ("lots", number),
    "won": ("winRatePct", percent),
    "win %": ("winRatePct", percent),
    "average win": ("avgWin", number),
    "average loss": ("avgLoss", number),
    "tracking": ("trackingSince", parse_ts),
    "first trade": ("firstTradeAt", parse_ts),
    "last update": ("lastUpdate", parse_ts),
    "last updated": ("lastUpdate", parse_ts),
    "broker": ("broker", clean_text),
    "leverage": ("leverage", integer),
    "type": ("accountType", clean_text),
    "system": ("strategyName", clean_text),
    "currency": ("currency", clean_text),
}
