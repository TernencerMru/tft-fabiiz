"""Main application window: tabs + overlay toggle + status bar."""
from __future__ import annotations

from typing import Optional

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QTabWidget

from ..config import AppConfig
from ..core.models import SetData
from ..core.recommender import RecommendationEngine
from ..data.providers.base import CompProvider
from ..services.bus import EventBus
from ..services.game_tracker import GameTracker
from .overlay.overlay_window import OverlayWindow
from .widgets.board_planner import BoardPlanner
from .widgets.comp_browser import CompBrowser
from .widgets.economy_panel import EconomyPanel
from .widgets.odds_panel import OddsPanel
from .widgets.recommendations_panel import RecommendationsPanel


class MainWindow(QMainWindow):
    def __init__(
        self,
        config: AppConfig,
        set_data: SetData,
        tracker: GameTracker,
        engine: RecommendationEngine,
        comp_providers: dict[str, CompProvider],
        bus: EventBus,
    ) -> None:
        super().__init__()
        self.setWindowTitle(
            f"TFT Companion — Set {set_data.set_id} · patch {set_data.patch}"
        )
        self.resize(980, 680)
        self.config = config
        self.set_data = set_data
        self.tracker = tracker
        self.engine = engine
        self.bus = bus
        self._overlay: Optional[OverlayWindow] = None

        tabs = QTabWidget()
        tabs.addTab(OddsPanel(set_data, tracker), "Probabilidades")
        tabs.addTab(CompBrowser(set_data, comp_providers, bus), "Composiciones")
        tabs.addTab(BoardPlanner(set_data, bus), "Tablero")
        tabs.addTab(RecommendationsPanel(set_data, tracker, engine, bus), "Recomendaciones")
        tabs.addTab(EconomyPanel(set_data, tracker), "Economía")
        self.setCentralWidget(tabs)

        toolbar = self.addToolBar("Principal")
        toolbar.setMovable(False)
        self.overlay_action = QAction("Overlay", self, checkable=True)
        self.overlay_action.toggled.connect(self._toggle_overlay)
        toolbar.addAction(self.overlay_action)

        self.statusBar().showMessage("Listo.")
        bus.notify.connect(lambda msg: self.statusBar().showMessage(msg, 8000))
        tracker.sources_changed.connect(
            lambda names: self.statusBar().showMessage(
                "Fuentes activas: " + (", ".join(names) if names else "ninguna"), 5000
            )
        )

    def _toggle_overlay(self, visible: bool) -> None:
        if visible:
            if self._overlay is None:
                self._overlay = OverlayWindow(
                    self.set_data, self.tracker, self.engine, self.bus,
                    game_window_title=self.config.game_window_title,
                )
            self._overlay.set_click_through(False)
            self._overlay.show()
        elif self._overlay is not None:
            self._overlay.hide()

    def closeEvent(self, event) -> None:
        if self._overlay is not None:
            self._overlay.close()
        super().closeEvent(event)
