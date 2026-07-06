"""Application configuration. One dataclass, sane defaults, env overrides."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_LOCAL_DATA = Path(__file__).resolve().parent / "data" / "local"


def _default_cache_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "tft-companion" / "cache"


@dataclass
class AppConfig:
    cache_dir: Path = field(default_factory=_default_cache_dir)
    cache_ttl_seconds: int = 12 * 3600

    # Static data (champions/traits)
    cdragon_url: str = "https://raw.communitydragon.org/latest/cdragon/tft/{locale}.json"

    # Per-set numbers (pool sizes, shop odds) — update this file each set/patch
    local_odds_file: Path = _LOCAL_DATA / "shop_odds.set17.json"

    # Comps
    local_comps_file: Path = _LOCAL_DATA / "comps.sample.json"
    # MetaTFT has no public API: set the endpoint you observe in the browser's
    # Network tab (see data/providers/comps.py) or leave empty to disable.
    metatft_url: str = os.environ.get("TFT_COMPANION_METATFT_URL", "")

    # Tracking / overlay
    poll_interval_ms: int = 1000
    game_window_title: str = "League of Legends"

    @classmethod
    def load(cls) -> "AppConfig":
        cfg = cls()
        cfg.cache_dir.mkdir(parents=True, exist_ok=True)
        return cfg
