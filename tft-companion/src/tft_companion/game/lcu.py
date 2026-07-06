"""LCU (League Client Update) API helper.

The desktop client exposes a local REST API whose port/password rotate on
every launch and live in a ``lockfile`` inside the install directory. Useful
for *out-of-game* context: current summoner, lobby, queue, TFT match history
(``/lol-match-history/...``). It does NOT expose live in-game board state,
so it is a companion to — not a replacement for — the sources in this
package. Widely used by community tools; still technically unofficial, so
keep usage read-only and defensive.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_DEFAULT_LOCKFILE_PATHS = (
    Path("C:/Riot Games/League of Legends/lockfile"),
    Path.home() / "Riot Games/League of Legends/lockfile",
)


@dataclass(frozen=True)
class LcuCredentials:
    port: int
    password: str
    protocol: str = "https"

    @property
    def base_url(self) -> str:
        return f"{self.protocol}://127.0.0.1:{self.port}"


def find_credentials(lockfile: Optional[Path] = None) -> Optional[LcuCredentials]:
    """Parse the lockfile: ``name:pid:port:password:protocol``."""
    candidates = [lockfile] if lockfile else []
    env = os.environ.get("TFT_COMPANION_LOCKFILE")
    if env:
        candidates.append(Path(env))
    candidates.extend(_DEFAULT_LOCKFILE_PATHS)

    for path in candidates:
        if path and path.exists():
            try:
                _, _, port, password, protocol = path.read_text().strip().split(":")
                return LcuCredentials(int(port), password, protocol)
            except (OSError, ValueError):
                continue
    return None


class LcuClient:
    def __init__(self, credentials: LcuCredentials) -> None:
        self.credentials = credentials
        self._session = requests.Session()
        self._session.verify = False
        self._session.auth = ("riot", credentials.password)

    def get(self, endpoint: str, timeout: float = 3.0) -> Optional[Any]:
        try:
            resp = self._session.get(self.credentials.base_url + endpoint, timeout=timeout)
            if resp.status_code != 200:
                return None
            return resp.json()
        except (requests.RequestException, ValueError):
            return None

    # Convenience examples ------------------------------------------------
    def current_summoner(self) -> Optional[Any]:
        return self.get("/lol-summoner/v1/current-summoner")

    def gameflow_phase(self) -> Optional[str]:
        phase = self.get("/lol-gameflow/v1/gameflow-phase")
        return phase if isinstance(phase, str) else None
