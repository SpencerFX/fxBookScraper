"""Append-oriented CSV sinks for the four output tables.

  systems.csv    upsert by systemId              (rewritten on flush; small)
  snapshots.csv  append-only (one row per system per run)
  daily.csv      insert-once by (systemId, date)  -- delete the file to force a refresh
  trades.csv     insert-once by tradeKey

Column order is fixed by the *_FIELDS lists in normalizer.normalize.
"""

import csv
import os
from pathlib import Path

from normalizer.normalize import (
    SYSTEM_FIELDS, SNAPSHOT_FIELDS, DAILY_FIELDS, TRADE_FIELDS,
)


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


class CsvStore:
    def __init__(self, csv_dir):
        self.dir = Path(csv_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

        self.paths = {
            "systems": self.dir / "systems.csv",
            "snapshots": self.dir / "snapshots.csv",
            "daily": self.dir / "daily.csv",
            "trades": self.dir / "trades.csv",
        }
        self.fields = {
            "systems": SYSTEM_FIELDS,
            "snapshots": SNAPSHOT_FIELDS,
            "daily": DAILY_FIELDS,
            "trades": TRADE_FIELDS,
        }

        self._systems = self._load_systems()
        self._daily_keys = self._load_keys("daily", lambda r: (r["systemId"], r["date"]))
        self._trade_keys = self._load_keys("trades", lambda r: r["tradeKey"])

        self._appended = {"snapshots": 0, "daily": 0, "trades": 0}

    # -- load existing -----------------------------------------------------------

    def _load_systems(self):
        p = self.paths["systems"]
        if not p.exists():
            return {}
        with p.open("r", encoding="utf-8", newline="") as f:
            return {row["systemId"]: row for row in csv.DictReader(f)}

    def _load_keys(self, name, keyfn):
        p = self.paths[name]
        if not p.exists():
            return set()
        keys = set()
        with p.open("r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                try:
                    keys.add(keyfn(row))
                except KeyError:
                    pass
        return keys

    # -- append helpers -------------------------------------------------------

    def _append(self, name, rows):
        if not rows:
            return
        fields = self.fields[name]
        p = self.paths[name]
        new_file = not p.exists() or p.stat().st_size == 0
        with p.open("a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(fields)
            for r in rows:
                w.writerow([_fmt(r.get(k)) for k in fields])
        self._appended[name] = self._appended.get(name, 0) + len(rows)

    # -- public API ---------------------------------------------------------

    def get_system(self, system_id):
        """Return the stored registry row for an id (dict) or None."""
        return self._systems.get(str(system_id))

    def upsert_system(self, rec):
        sid = str(rec["systemId"])
        existing = self._systems.get(sid)
        if existing:
            existing["displayName"] = rec["displayName"] or existing.get("displayName")
            existing["url"] = rec["url"]
            existing["lastSeen"] = rec["lastSeen"]
        else:
            self._systems[sid] = {k: _fmt(rec.get(k)) for k in SYSTEM_FIELDS}

    def add_snapshot(self, row):
        self._append("snapshots", [row])

    def add_daily(self, rows):
        fresh = []
        for r in rows:
            key = (str(r["systemId"]), str(r["date"]))
            if key in self._daily_keys:
                continue
            self._daily_keys.add(key)
            fresh.append(r)
        self._append("daily", fresh)
        return len(fresh)

    def add_trades(self, rows):
        fresh = []
        for r in rows:
            if r["tradeKey"] in self._trade_keys:
                continue
            self._trade_keys.add(r["tradeKey"])
            fresh.append(r)
        self._append("trades", fresh)
        return len(fresh)

    def flush(self):
        """Rewrite systems.csv from memory (atomic)."""
        p = self.paths["systems"]
        tmp = p.with_suffix(".csv.tmp")
        with tmp.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(SYSTEM_FIELDS)
            for rec in self._systems.values():
                w.writerow([_fmt(rec.get(k)) for k in SYSTEM_FIELDS])
        os.replace(tmp, p)

    @property
    def counts(self):
        return dict(self._appended, systems=len(self._systems))
