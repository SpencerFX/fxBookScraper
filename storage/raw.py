"""Persist raw collected artefacts under data/raw/<system_id>/ for replay/debugging."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def _safe(value):
    return (str(value).replace("/", "_").replace("\\", "_").replace(":", "_")
            .replace("?", "_").replace("*", "_"))


def _stamp(collected_at):
    return _safe(collected_at or datetime.now(timezone.utc).isoformat())


def save_system_snapshot(raw_dir, system_id, collected_at, html):
    root = Path(raw_dir) / str(system_id)
    root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(html.encode("utf-8")).hexdigest()[:12]
    path = root / f"{_stamp(collected_at)}_{digest}.stats.html"
    path.write_text(html, encoding="utf-8")
    return str(path)


def save_raw_bundle(raw_dir, system_id, snapshot):
    """snapshot: the dict returned by SystemCollector.collect()."""
    root = Path(raw_dir) / str(system_id)
    root.mkdir(parents=True, exist_ok=True)
    stamp = _stamp(snapshot.get("collected_at"))

    stats_path = save_system_snapshot(raw_dir, system_id,
                                      snapshot.get("collected_at"),
                                      snapshot.get("stats_html", ""))

    if snapshot.get("charts_obj") is not None:
        (root / f"{stamp}.charts.json").write_text(
            json.dumps(snapshot["charts_obj"])[:2_000_000], encoding="utf-8")

    for i, frag in enumerate(snapshot.get("history_fragments") or []):
        (root / f"{stamp}.history.{i:03d}.html").write_text(frag, encoding="utf-8")

    return stats_path


def save_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
