"""Resumable-crawl bookkeeping under data/state/."""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path


class CrawlState:
    def __init__(self, state_dir):
        self.dir = Path(state_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.seen_path = self.dir / "seen_systems.json"
        self.progress_path = self.dir / "crawl_progress.json"
        self.seen = self._load(self.seen_path, {})
        self.progress = self._load(self.progress_path, {"pending": [], "done": []})

    @staticmethod
    def _load(path, default):
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return json.loads(json.dumps(default))

    def _save(self, path, obj):
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(obj, indent=1), encoding="utf-8")
        tmp.replace(path)

    # -- system recency ----------------------------------------------------------

    def recently_collected(self, system_id, min_recheck_hours):
        ts = self.seen.get(str(system_id))
        if not ts:
            return False
        try:
            when = datetime.fromisoformat(ts)
        except ValueError:
            return False
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - when < timedelta(hours=min_recheck_hours)

    def mark_collected(self, system_id):
        self.seen[str(system_id)] = datetime.now(timezone.utc).isoformat()
        self._save(self.seen_path, self.seen)

    # -- crawl queue ------------------------------------------------------------

    def set_pending(self, system_ids):
        done = set(self.progress.get("done", []))
        self.progress["pending"] = [s for s in system_ids if s not in done]
        self._save(self.progress_path, self.progress)

    def next_pending(self):
        return list(self.progress.get("pending", []))

    def mark_done(self, system_id):
        pend = [s for s in self.progress.get("pending", []) if s != system_id]
        done = self.progress.get("done", [])
        if system_id not in done:
            done.append(system_id)
        self.progress["pending"] = pend
        self.progress["done"] = done
        self._save(self.progress_path, self.progress)

    def reset_progress(self):
        self.progress = {"pending": [], "done": []}
        self._save(self.progress_path, self.progress)
