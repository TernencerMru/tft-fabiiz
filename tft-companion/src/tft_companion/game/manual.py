"""Manual game-data source.

The user is the most reliable sensor available: scouting info (which enemies
hold which units) is something no sanctioned API exposes anyway. The UI
writes into this source; the tracker reads it like any other source, with
top priority so manual corrections always win over automated guesses.
"""
from __future__ import annotations

from typing import Optional

from ..core.models import GameSnapshot


class ManualSource:
    name = "manual"
    priority = 100

    def __init__(self) -> None:
        self._pending: dict = {}

    # UI-facing -----------------------------------------------------------
    def update(self, **fields) -> None:
        """Stage manual values, e.g. ``update(gold=34, level=7)``."""
        self._pending.update({k: v for k, v in fields.items() if v is not None})

    # GameDataSource ------------------------------------------------------
    def is_available(self) -> bool:
        return bool(self._pending)

    def poll(self) -> Optional[GameSnapshot]:
        if not self._pending:
            return None
        snap = GameSnapshot(source=self.name, **self._pending)
        self._pending = {}
        return snap
