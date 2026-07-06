"""Economy tracker panel: interest, projected income and heuristic advice."""
from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QListWidget, QSpinBox,
    QVBoxLayout, QWidget,
)

from ...core import economy
from ...core.models import GameState, SetData
from ...services.game_tracker import GameTracker

_ICONS = {"info": "•", "warn": "⚠", "danger": "‼"}


class EconomyPanel(QWidget):
    def __init__(self, set_data: SetData, tracker: GameTracker,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.set_data = set_data
        self.tracker = tracker
        self._build_ui()
        tracker.state_changed.connect(self._on_state)
        self._on_state(tracker.state)

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)

        inputs = QGroupBox("Estado")
        form = QFormLayout(inputs)
        self.gold_spin = QSpinBox(minimum=0, maximum=999)
        self.gold_spin.valueChanged.connect(lambda v: self.tracker.set_fields(gold=v))
        form.addRow("Oro:", self.gold_spin)
        self.xp_spin = QSpinBox(minimum=0, maximum=200)
        self.xp_spin.valueChanged.connect(lambda v: self.tracker.set_fields(xp=v))
        form.addRow("XP actual:", self.xp_spin)
        self.streak_spin = QSpinBox(minimum=-15, maximum=15)
        self.streak_spin.setToolTip("Positivo = racha de victorias, negativo = derrotas")
        self.streak_spin.valueChanged.connect(lambda v: self.tracker.set_fields(streak=v))
        form.addRow("Racha:", self.streak_spin)
        self.health_spin = QSpinBox(minimum=0, maximum=100)
        self.health_spin.valueChanged.connect(lambda v: self.tracker.set_fields(health=v))
        form.addRow("Vida:", self.health_spin)
        root.addWidget(inputs)

        right = QVBoxLayout()
        outputs = QGroupBox("Proyección")
        out_form = QFormLayout(outputs)
        self.interest_label = QLabel("—")
        out_form.addRow("Interés:", self.interest_label)
        self.income_label = QLabel("—")
        out_form.addRow("Ingreso próxima ronda:", self.income_label)
        self.breakpoint_label = QLabel("—")
        out_form.addRow("Próximo escalón:", self.breakpoint_label)
        self.level_cost_label = QLabel("—")
        out_form.addRow("Subir de nivel:", self.level_cost_label)
        right.addWidget(outputs)

        self.advice_list = QListWidget()
        right.addWidget(self.advice_list, stretch=1)
        root.addLayout(right, stretch=1)

    def _on_state(self, state: GameState) -> None:
        for spin, value in (
            (self.gold_spin, state.gold), (self.xp_spin, state.xp),
            (self.streak_spin, state.streak), (self.health_spin, state.health),
        ):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)

        self.interest_label.setText(f"+{economy.interest(state.gold)}")
        self.income_label.setText(f"+{economy.round_income(state.gold, state.streak)}")
        bp = economy.next_interest_breakpoint(state.gold)
        self.breakpoint_label.setText("interés máximo" if bp is None else f"faltan {bp} de oro")
        lvl = economy.gold_to_next_level(state, self.set_data)
        self.level_cost_label.setText("—" if lvl is None else f"~{lvl} de oro")

        self.advice_list.clear()
        for advice in economy.advise(state, self.set_data):
            self.advice_list.addItem(f"{_ICONS.get(advice.severity, '•')} {advice.text}")
