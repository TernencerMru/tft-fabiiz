"""Composition root: builds and wires every component.

All dependency injection happens here and only here — modules below never
instantiate their own collaborators, which is what keeps them swappable
(e.g. replacing the comps source or adding an OCR game source is a one-line
change in this file).
"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .config import AppConfig
from .core.recommender import RecommendationEngine
from .data.cache import JsonDiskCache
from .data.providers.comps import LocalJsonCompProvider, MetaTFTCompProvider
from .game.live_client import LiveClientSource
from .game.manual import ManualSource
from .services.bus import EventBus
from .services.game_tracker import GameTracker
from .services.static_data import load_set_data
from .ui.main_window import MainWindow


def build_app(argv: list[str]) -> tuple[QApplication, MainWindow]:
    app = QApplication(argv)
    config = AppConfig.load()
    cache = JsonDiskCache(config.cache_dir, ttl_seconds=config.cache_ttl_seconds)

    set_data, warnings = load_set_data(config, cache)

    bus = EventBus()
    sources = [LiveClientSource(), ManualSource()]  # ManualSource: máxima prioridad
    tracker = GameTracker(sources=sources, set_data=set_data,
                          poll_ms=config.poll_interval_ms)

    comp_providers = {"Local (JSON)": LocalJsonCompProvider(config.local_comps_file)}
    if config.metatft_url:
        comp_providers["MetaTFT (no oficial)"] = MetaTFTCompProvider(
            config.metatft_url, cache=cache
        )

    engine = RecommendationEngine()
    window = MainWindow(config, set_data, tracker, engine, comp_providers, bus)

    for warning in warnings:
        bus.notify.emit(warning)
    tracker.start()
    return app, window


def main() -> int:
    app, window = build_app(sys.argv)
    window.show()
    return app.exec()
