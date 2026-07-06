"""Game-state acquisition contract.

Why an abstraction here: there is no single reliable way to read a live TFT
game, so the app treats every technique as a pluggable *source* producing
partial :class:`~tft_companion.core.models.GameSnapshot` objects that the
:class:`~tft_companion.services.game_tracker.GameTracker` merges by priority.

Implemented / planned sources (see README for the full trade-off analysis):

===================  =========================================================
ManualSource         User input through the UI. Always works, zero risk,
                     ground truth for scouting data. Ship-first choice.
LiveClientSource     Riot's local Live Client Data API (https://127.0.0.1:2999).
                     Officially sanctioned, but TFT exposes only a subset of
                     the League payload — treat as enrichment, not truth.
LcuClient            League Client (LCU) lockfile API. Pre/post-game info
                     (lobby, queue, match history), NOT live board state.
OcrShopSource        Screen capture + OCR of your own screen. No injection,
                     no memory reading; brittle (resolution/skin dependent),
                     experimental, optional extra.
===================  =========================================================

Hard boundaries, on purpose: no game-memory reading, no client modification,
no input automation. Besides being against Riot's third-party policy, the
first two are exactly what Vanguard exists to detect.
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from ..core.models import GameSnapshot


@runtime_checkable
class GameDataSource(Protocol):
    name: str
    priority: int  # higher wins when merging overlapping fields

    def is_available(self) -> bool:
        """Cheap check: can this source produce data right now?"""
        ...

    def poll(self) -> Optional[GameSnapshot]:
        """Return the current partial observation, or None."""
        ...
