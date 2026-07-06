"""Transparent in-game overlay.

Technique: a frameless, always-on-top, translucent top-level QWidget. That is
exactly how mainstream overlays work and it involves ZERO interaction with
the game process — no injection, no memory access, no hooks — so it is safe
with Vanguard. The trade-off everyone accepts: the game must run in
**Borderless / Windowed** mode; exclusive fullscreen bypasses the desktop
compositor and external overlays simply do not show (the "solutions" to that
are injection-based and off the table by design).

Windows extras via ctypes (no pywin32 dependency):
* true click-through (``WS_EX_TRANSPARENT``) so mouse events reach the game;
* locating the game window rect to dock the overlay to its top-right corner.
On other platforms those degrade gracefully to Qt-only behaviour.
"""
from __future__ import annotations

import sys
from typing import Optional

from PySide6.QtCore import QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ...core.models import GameState, MetaComp
from ...core.recommender import RecommendationEngine
from ...core.models import SetData
from ...services.bus import EventBus
from ...services.game_tracker import GameTracker

_IS_WINDOWS = sys.platform == "win32"

if _IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    _GWL_EXSTYLE = -20
    _WS_EX_LAYERED = 0x00080000
    _WS_EX_TRANSPARENT = 0x00000020


def _set_click_through_win(win_id: int, enabled: bool) -> None:
    style = _user32.GetWindowLongW(win_id, _GWL_EXSTYLE)
    if enabled:
        style |= _WS_EX_LAYERED | _WS_EX_TRANSPARENT
    else:
        style &= ~_WS_EX_TRANSPARENT
    _user32.SetWindowLongW(win_id, _GWL_EXSTYLE, style)


def find_game_window_rect(title_substring: str) -> Optional[QRect]:
    """Locate a visible window whose title contains ``title_substring``."""
    if not _IS_WINDOWS:
        return None
    found: list[QRect] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd, _lparam):
        if not _user32.IsWindowVisible(hwnd):
            return True
        length = _user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buffer, length + 1)
        if title_substring.lower() in buffer.value.lower():
            rect = wintypes.RECT()
            _user32.GetWindowRect(hwnd, ctypes.byref(rect))
            found.append(QRect(rect.left, rect.top,
                               rect.right - rect.left, rect.bottom - rect.top))
            return False
        return True

    _user32.EnumWindows(_enum, 0)
    return found[0] if found else None


class OverlayWindow(QWidget):
    MARGIN = 16

    def __init__(
        self,
        set_data: SetData,
        tracker: GameTracker,
        engine: RecommendationEngine,
        bus: EventBus,
        game_window_title: str = "League of Legends",
    ) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.set_data = set_data
        self.engine = engine
        self.game_window_title = game_window_title
        self._target: Optional[MetaComp] = None
        self._state: GameState = tracker.state
        self._drag_offset: Optional[QPoint] = None
        self._click_through = False

        self._build_ui()
        self.resize(320, 190)

        tracker.state_changed.connect(self._on_state)
        bus.comp_selected.connect(self._on_comp)

        self._follow_timer = QTimer(self)
        self._follow_timer.setInterval(500)
        self._follow_timer.timeout.connect(self._dock_to_game)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)

        header = QHBoxLayout()
        title = QLabel("TFT Companion")
        title.setStyleSheet("color:#e5e7eb; font-weight:600;")
        header.addWidget(title)
        header.addStretch(1)
        self.pin_button = QPushButton("👻")
        self.pin_button.setToolTip("Click-through: el ratón atraviesa el overlay")
        self.pin_button.setFixedSize(26, 22)
        self.pin_button.clicked.connect(lambda: self.set_click_through(True))
        header.addWidget(self.pin_button)
        self.dock_button = QPushButton("⚓")
        self.dock_button.setToolTip("Anclar a la ventana del juego (Windows)")
        self.dock_button.setFixedSize(26, 22)
        self.dock_button.setCheckable(True)
        self.dock_button.toggled.connect(self._toggle_docking)
        header.addWidget(self.dock_button)
        root.addLayout(header)

        self.comp_label = QLabel("Sin comp objetivo")
        self.comp_label.setStyleSheet("color:#93c5fd;")
        root.addWidget(self.comp_label)

        self.body_label = QLabel("Introduce la tienda para ver recomendaciones.")
        self.body_label.setWordWrap(True)
        self.body_label.setStyleSheet("color:#e5e7eb; font-size:12px;")
        root.addWidget(self.body_label, stretch=1)

        self.econ_label = QLabel("")
        self.econ_label.setStyleSheet("color:#9ca3af; font-size:11px;")
        root.addWidget(self.econ_label)

        for btn in (self.pin_button, self.dock_button):
            btn.setStyleSheet(
                "QPushButton{background:#374151;color:#e5e7eb;border:none;"
                "border-radius:4px;} QPushButton:checked{background:#2563eb;}"
            )

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(15, 17, 26, 215))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 12, 12)

    # ----------------------------------------------------------- behaviour
    def set_click_through(self, enabled: bool) -> None:
        """When enabled the overlay is display-only and untouchable — restore
        it from the main window's Overlay action."""
        self._click_through = enabled
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, enabled)
        if _IS_WINDOWS and self.isVisible():
            _set_click_through_win(int(self.winId()), enabled)

    def _toggle_docking(self, enabled: bool) -> None:
        if enabled:
            self._follow_timer.start()
            self._dock_to_game()
        else:
            self._follow_timer.stop()

    def _dock_to_game(self) -> None:
        rect = find_game_window_rect(self.game_window_title)
        if rect is None:
            return
        self.move(rect.right() - self.width() - self.MARGIN, rect.top() + self.MARGIN)

    # Dragging (only while not click-through)
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, _event) -> None:
        self._drag_offset = None

    # ------------------------------------------------------------- updates
    def _on_comp(self, comp: MetaComp) -> None:
        self._target = comp
        self.comp_label.setText(f"▶ {comp.name}")
        self._refresh()

    def _on_state(self, state: GameState) -> None:
        self._state = state
        self._refresh()

    def _refresh(self) -> None:
        recs = self.engine.recommend_shop(self._state, self.set_data, self._target)
        if recs:
            lines = [
                f"{i + 1}. {r.name} ({r.cost}) — {r.reasons[0] if r.reasons else ''}"
                for i, r in enumerate(recs[:3])
            ]
            self.body_label.setText("\n".join(lines))
        else:
            self.body_label.setText("Nada destacable en la tienda actual.")
        from ...core import economy  # local import keeps overlay import-light
        self.econ_label.setText(
            f"Oro {self._state.gold} · interés +{economy.interest(self._state.gold)}"
            f" · vida {self._state.health}"
        )
