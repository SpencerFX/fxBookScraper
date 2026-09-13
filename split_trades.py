"""Split the master data/csv/trades.csv into one CSV per system.

Output: data/csv/trades/<systemId>.csv  (same columns as the master, rows sorted
by closeTime then openTime) plus data/csv/trades/_index.csv summarising each file.

Regenerates from the master every run, so it is safe to re-run after each
`trades_backfill.py` pass. The master trades.csv stays the source of truth.

    .venv/Scripts/python.exe split_trades.py
"""

import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MASTER = ROOT / "data" / "csv" / "trades.csv"
OUT_DIR = ROOT / "data" / "csv" / "trades"


def _sort_key(r):
    return (r.get("closeTime") or "", r.get("openTime") or "")


def main():
    if not MASTER.exists():
        print(f"no master file at {MASTER}")
        return 1

    with MASTER.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames
        by_system = {}
        for row in reader:
            by_system.setdefault(row["systemId"], []).append(row)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # drop per-system files for systems no longer present
    keep = {f"{sid}.csv" for sid in by_system}
    for old in OUT_DIR.glob("*.csv"):
        if old.name != "_index.csv" and old.name not in keep:
            old.unlink()

    index_rows = []
    for sid, rows in sorted(by_system.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0):
        rows.sort(key=_sort_key)
        path = OUT_DIR / f"{sid}.csv"
        tmp = path.with_suffix(".csv.tmp")
        with tmp.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=header)
            w.writeheader()
            w.writerows(rows)
        os.replace(tmp, path)

        first = rows[0]
        index_rows.append({
            "systemId": sid,
            "username": first.get("username", ""),
            "systemName": first.get("systemName", ""),
            "trades": len(rows),
            "firstClose": rows[0].get("closeTime", ""),
            "lastClose": rows[-1].get("closeTime", ""),
            "file": f"trades/{sid}.csv",
        })

    idx_path = OUT_DIR / "_index.csv"
    tmp = idx_path.with_suffix(".csv.tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["systemId", "username", "systemName",
                                          "trades", "firstClose", "lastClose", "file"])
        w.writeheader()
        w.writerows(index_rows)
    os.replace(tmp, idx_path)

    total = sum(r["trades"] for r in index_rows)
    print(f"wrote {len(index_rows)} per-system files ({total} trade rows) -> {OUT_DIR}")
    print(f"index -> {idx_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
