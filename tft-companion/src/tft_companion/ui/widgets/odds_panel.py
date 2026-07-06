"""Shop odds panel.

Live table of every champion with copies remaining and hit probabilities,
plus a scouting editor (my copies / copies seen on rivals) and a rolldown
planner (probability of hitting N copies with X gold, analytic + Monte
Carlo). Everything reacts to GameTracker.state_changed.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...core import odds
from ...core.models import GameState, SetData
from ...services.game_tracker import GameTracker


class OddsPanel(QWidget):
    def __init__(self, set_data: SetData, tracker: GameTracker,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.set_data = set_data
        self.tracker = tracker
        self._state: GameState = tracker.state
        self._selected_champ: Optional[str] = None
        self._build_ui()
        tracker.state_changed.connect(self._on_state)
        self._on_state(self._state)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        top = QHBoxLayout()
        top.addWidget(QLabel("Nivel:"))
        self.level_spin = QSpinBox(minimum=1, maximum=10)
        self.level_spin.valueChanged.connect(lambda v: self.tracker.set_fields(level=v))
        top.addWidget(self.level_spin)
        top.addWidget(QLabel("Oro:"))
        self.gold_spin = QSpinBox(minimum=0, maximum=999)
        self.gold_spin.valueChanged.connect(lambda v: self.tracker.set_fields(gold=v))
        top.addWidget(self.gold_spin)
        top.addStretch(1)
        self.filter_edit = QLineEdit(placeholderText="Filtrar campeón…")
        self.filter_edit.textChanged.connect(lambda _t: self._refresh_table())
        top.addWidget(self.filter_edit, stretch=1)
        root.addLayout(top)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Campeón", "Coste", "Quedan", "% próx. tienda", "≥1 con tu oro"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        root.addWidget(self.table, stretch=1)

        detail = QGroupBox("Campeón seleccionado")
        grid = QGridLayout(detail)
        self.detail_name = QLabel("—")
        grid.addWidget(self.detail_name, 0, 0, 1, 4)

        grid.addWidget(QLabel("Mis copias:"), 1, 0)
        self.owned_spin = QSpinBox(minimum=0, maximum=30)
        self.owned_spin.valueChanged.connect(self._on_owned_changed)
        grid.addWidget(self.owned_spin, 1, 1)
        grid.addWidget(QLabel("En rivales (scouting):"), 1, 2)
        self.taken_spin = QSpinBox(minimum=0, maximum=30)
        self.taken_spin.valueChanged.connect(self._on_taken_changed)
        grid.addWidget(self.taken_spin, 1, 3)

        grid.addWidget(QLabel("Copias que necesito:"), 2, 0)
        self.need_spin = QSpinBox(minimum=1, maximum=9, value=1)
        grid.addWidget(self.need_spin, 2, 1)
        grid.addWidget(QLabel("Oro a rollear:"), 2, 2)
        self.roll_gold_spin = QSpinBox(minimum=0, maximum=200, value=30)
        grid.addWidget(self.roll_gold_spin, 2, 3)

        self.plan_button = QPushButton("Calcular rolldown")
        self.plan_button.clicked.connect(self._compute_plan)
        grid.addWidget(self.plan_button, 3, 0)
        self.plan_label = QLabel("")
        self.plan_label.setWordWrap(True)
        grid.addWidget(self.plan_label, 3, 1, 1, 3)
        root.addWidget(detail)

    # ------------------------------------------------------------ handlers
    def _on_state(self, state: GameState) -> None:
        self._state = state
        for spin, value in ((self.level_spin, state.level), (self.gold_spin, state.gold)):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        self._refresh_table()
        self._sync_detail_spins()

    def _refresh_table(self) -> None:
        needle = self.filter_edit.text().strip().lower()
        rows = []
        for champ in self.set_data.champions.values():
            if needle and needle not in champ.name.lower():
                continue
            left = odds.champion_copies_remaining(self.set_data, self._state, champ.id)
            p_shop = odds.p_in_next_shop(self.set_data, self._state, champ.id)
            p_gold = odds.p_hit_copies_with_gold(
                self.set_data, self._state, champ.id, 1, self._state.gold
            )
            rows.append((champ, left, p_shop, p_gold))
        rows.sort(key=lambda r: r[2], reverse=True)

        self.table.setRowCount(len(rows))
        for i, (champ, left, p_shop, p_gold) in enumerate(rows):
            name_item = QTableWidgetItem(champ.name)
            name_item.setData(Qt.ItemDataRole.UserRole, champ.id)
            self.table.setItem(i, 0, name_item)
            self.table.setItem(i, 1, QTableWidgetItem(str(champ.cost)))
            self.table.setItem(i, 2, QTableWidgetItem(str(left)))
            self.table.setItem(i, 3, QTableWidgetItem(f"{p_shop:.1%}"))
            self.table.setItem(i, 4, QTableWidgetItem(f"{p_gold:.1%}"))

    def _on_row_selected(self) -> None:
        items = self.table.selectedItems()
        self._selected_champ = items[0].data(Qt.ItemDataRole.UserRole) if items else None
        champ = self.set_data.get(self._selected_champ) if self._selected_champ else None
        self.detail_name.setText(
            f"{champ.name} (coste {champ.cost})" if champ else "—"
        )
        self._sync_detail_spins()
        self.plan_label.clear()

    def _sync_detail_spins(self) -> None:
        if not self._selected_champ:
            return
        for spin, value in (
            (self.owned_spin, self._state.owned.get(self._selected_champ, 0)),
            (self.taken_spin, self._state.taken_by_others.get(self._selected_champ, 0)),
        ):
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)

    def _on_owned_changed(self, value: int) -> None:
        if self._selected_champ:
            self.tracker.set_owned(self._selected_champ, value)

    def _on_taken_changed(self, value: int) -> None:
        if self._selected_champ:
            self.tracker.set_taken_by_others(self._selected_champ, value)

    def _compute_plan(self) -> None:
        if not self._selected_champ:
            self.plan_label.setText("Selecciona un campeón en la tabla.")
            return
        need = self.need_spin.value()
        gold = self.roll_gold_spin.value()
        analytic = odds.p_hit_copies_with_gold(
            self.set_data, self._state, self._selected_champ, need, gold
        )
        mc = odds.simulate_rolldown(
            self.set_data, self._state, self._selected_champ, gold, need
        )
        expected = odds.expected_gold_per_copy(self.set_data, self._state, self._selected_champ)
        exp_txt = "∞" if expected == float("inf") else f"~{expected:.0f} oro/copia"
        self.plan_label.setText(
            f"P(≥{need} copias con {gold} oro): {analytic:.1%} (binomial) · "
            f"{mc:.1%} (Monte Carlo con pool) · esperado {exp_txt}"
        )
