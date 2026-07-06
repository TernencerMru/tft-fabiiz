"""Tiny JSON disk cache with TTL.

Public data sources (CommunityDragon, MetaTFT) should never be hit more than
a few times a day; everything network-facing in this app goes through here.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Optional


class JsonDiskCache:
    def __init__(self, directory: Path, ttl_seconds: int = 12 * 3600) -> None:
        self.directory = Path(directory)
        self.ttl_seconds = ttl_seconds
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.json"

    def get(self, key: str, max_age: Optional[int] = None) -> Optional[Any]:
        path = self._path(key)
        if not path.exists():
            return None
        age = time.time() - path.stat().st_mtime
        if age > (self.ttl_seconds if max_age is None else max_age):
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def set(self, key: str, value: Any) -> None:
        try:
            self._path(key).write_text(
                json.dumps(value, ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            pass  # cache is best-effort by design
