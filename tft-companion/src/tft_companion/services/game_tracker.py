"""GameTracker: single source of truth for the live GameState.

Responsibilities:
* Poll every registered :class:`GameDataSource` on a timer, merge their
  partial snapshots by ascending priority (highest priority wins on
  conflicting fields) and apply the result to the canonical GameState.
* Offer explicit mutators for the UI (manual edits, buying from shop...).
* Emit ``state_changed`` with an immutable copy whenever anything changes —
  widgets and the overlay only ever *react* to this signal.
"""
from __future__ import annotations

import dataclasses
from typing import Iterable, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from ..core.models import GameSnapshot, GameState, SetData
from ..game.source import GameDataSource


class GameTracker(QObject):
    state_changed = Signal(object)          # GameState copy
    sources_changed = Signal(list)          # [str] names of active sources

    def __init__(
        self,
        sources: Iterable[GameDataSource] = (),
        set_data: Optional[SetData] = None,
        poll_ms: int = 1000,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._sources = sorted(sources, key=lambda s: s.priority)
        self._set_data = set_data
        self._state = GameState()
        self._active: list[str] = []
        self._timer = QTimer(self)
        self._timer.setInterval(poll_ms)
        self._timer.timeout.connect(self._tick)

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        self._timer.start()
        self._tick()

    def stop(self) -> None:
        self._timer.stop()

    @property
    def state(self) -> GameState:
        return self._state.copy()

    def set_set_data(self, set_data: SetData) -> None:
        self._set_data = set_data

    # -- polling / merging ---------------------------------------------------
    def _tick(self) -> None:
        active: list[str] = []
        merged: dict = {}
        for source in self._sources:  # ascending priority: later overwrites
            try:
                if not source.is_available():
                    continue
                snap = source.poll()
            except Exception:  # a broken source must never kill the loop
                continue
            active.append(source.name)
            if snap is not None:
                merged.update(self._snapshot_fields(snap))

        if active != self._active:
            self._active = active
            self.sources_changed.emit(list(active))
        if merged:
            self._apply(merged)

    @staticmethod
    def _snapshot_fields(snap: GameSnapshot) -> dict:
        fields = dataclasses.asdict(snap)
        fields.pop("source", None)
        return {k: v for k, v in fields.items() if v is not None}

    def _apply(self, fields: dict) -> None:
        changed = False
        for key, value in fields.items():
            if getattr(self._state, key, None) != value:
                setattr(self._state, key, value)
                changed = True
        if changed:
            self._emit()

    def _emit(self) -> None:
        self.state_changed.emit(self._state.copy())

    # -- UI mutators ---------------------------------------------------------
    def set_fields(self, **fields) -> None:
        self._apply({k: v for k, v in fields.items() if v is not None})

    def set_shop_slot(self, slot: int, champion_id: Optional[str]) -> None:
        if 0 <= slot < len(self._state.shop) and self._state.shop[slot] != champion_id:
            self._state.shop[slot] = champion_id
            self._emit()

    def set_owned(self, champion_id: str, copies: int) -> None:
        if copies <= 0:
            self._state.owned.pop(champion_id, None)
        else:
            self._state.owned[champion_id] = copies
        self._emit()

    def set_taken_by_others(self, champion_id: str, copies: int) -> None:
        if copies <= 0:
            self._state.taken_by_others.pop(champion_id, None)
        else:
            self._state.taken_by_others[champion_id] = copies
        self._emit()

    def buy_from_shop(self, slot: int) -> bool:
        """Move a shop unit to owned, paying its cost. Returns success."""
        if not (0 <= slot < len(self._state.shop)):
            return False
        champ_id = self._state.shop[slot]
        if not champ_id or self._set_data is None:
            return False
        champ = self._set_data.get(champ_id)
        if champ is None or self._state.gold < champ.cost:
            return False
        self._state.gold -= champ.cost
        self._state.owned[champ_id] = self._state.owned.get(champ_id, 0) + 1
        self._state.shop[slot] = None
        self._emit()
        return True
