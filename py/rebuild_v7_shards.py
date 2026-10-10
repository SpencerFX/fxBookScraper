"""Rebalance the v7 losing-expanded backlog across a NEW shard count, picking
up from wherever each system currently stands (its own v7 progress file's
pages_done, not from scratch). Run this after stopping all running v7 shards.

    py -3.12 rebuild_v7_shards.py --shards 6

Systems already finished (done=True in any existing v7 progress file) are
dropped. The rest are re-sorted fewest-remaining-pages-first and rebalanced
by remaining pages across the new shard count. Output CSV filenames are
reused positionally (v7_1..v7_N) so shards that keep the same number keep
accumulating into the same file - losing_accounts.py's --dedupe-against
already scans every sibling losingAccountsExpanded_v7/*.csv (the glob
'losingAccountsExpanded*/*.csv' matches that directory too), so a system
moving to a different shard number still never re-writes a trade any shard
already collected for it.
"""
import argparse
import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "state"


def best_records():
    best = {}
    for f in glob.glob(str(STATE / "losing_progress_expanded_v7_*.json")):
        for sid, v in json.load(open(f, encoding="utf-8")).items():
            if not isinstance(v, dict):
                continue
            cur = best.get(sid)
            if (cur is None or (v.get("done") and not cur.get("done"))
                    or v.get("pages_done", 0) > cur.get("pages_done", 0)):
                best[sid] = v
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shards", type=int, required=True)
    args = ap.parse_args()

    remaining = []
    for sid, v in best_records().items():
        if v.get("done"):
            continue
        pages, pd = int(v.get("pages") or 0), int(v.get("pages_done") or 0)
        rem = max(1, pages - pd)
        remaining.append((rem, sid, v))
    remaining.sort(key=lambda t: (t[0], int(t[1])))

    shards = [[] for _ in range(args.shards)]
    load = [0] * args.shards
    for rem, sid, v in remaining:
        i = load.index(min(load))
        shards[i].append((sid, v))
        load[i] += rem

    for n, items in enumerate(shards, 1):
        (STATE / f"v7_systems_{n}.txt").write_text(
            "\n".join(sid for sid, _ in items) + "\n", encoding="utf-8")
        prog = {sid: {"populated": True, "total": v.get("total", 0),
                      "pages": v["pages"], "pages_done": v["pages_done"],
                      "done": False, "capped": False}
                for sid, v in items}
        (STATE / f"losing_progress_expanded_v7_{n}.json").write_text(
            json.dumps(prog), encoding="utf-8")
        print(f"shard {n}: {len(items)} systems, {load[n-1]:,} pages remaining")
    print(f"total: {len(remaining)} systems, {sum(load):,} pages remaining "
          f"across {args.shards} shards")


if __name__ == "__main__":
    main()
