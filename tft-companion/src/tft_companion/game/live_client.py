"""Riot Live Client Data API source.

While a game is running, the client serves ``https://127.0.0.1:2999`` with a
self-signed Riot certificate. This is the *officially sanctioned* local API.
Caveat: it was designed for League — in TFT it responds, but exposes only a
subset of fields, and Riot adjusts the payload between patches. Because of
that, this source (a) extracts defensively, and (b) ships a ``dump()``
helper: run it during a real TFT match, inspect the JSON, and extend
:meth:`_extract` with whatever your patch actually provides.

``verify=False`` is required and safe here: the endpoint is loopback-only
and Riot signs it with its own local certificate.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import requests
import urllib3

from ..core.models import GameSnapshot

BASE_URL = "https://127.0.0.1:2999/liveclientdata"

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class LiveClientSource:
    name = "live_client"
    priority = 10

    def __init__(self, timeout: float = 0.8) -> None:
        self.timeout = timeout
        self._session = requests.Session()
        self._session.verify = False

    # ------------------------------------------------------------------
    def is_available(self) -> bool:
        return self._get("/gamestats") is not None

    def poll(self) -> Optional[GameSnapshot]:
        data = self._get("/allgamedata")
        if data is None:
            return None
        return self._extract(data)

    def dump(self, path: Path | str = "liveclient_dump.json") -> Optional[Path]:
        """Save the raw payload of the current game for exploration."""
        data = self._get("/allgamedata")
        if data is None:
            return None
        out = Path(path)
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return out

    # ------------------------------------------------------------------
    def _get(self, endpoint: str) -> Optional[Any]:
        try:
            resp = self._session.get(BASE_URL + endpoint, timeout=self.timeout)
            if resp.status_code != 200:
                return None
            return resp.json()
        except (requests.RequestException, ValueError):
            return None

    @staticmethod
    def _extract(data: dict[str, Any]) -> GameSnapshot:
        """Defensive field mapping. Extend after inspecting a dump()."""
        active = data.get("activePlayer") or {}
        level = active.get("level")
        return GameSnapshot(
            source="live_client",
            level=int(level) if isinstance(level, (int, float)) else None,
        )
