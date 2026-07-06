"""Purchase recommendations panel.

The 5 shop slots are entered with combo boxes (or filled by an automated
source when one can read the shop); the RecommendationEngine ranks them
against the comp selected in the browser, with human-readable reasons.
"Comprar" applies the purchase to the GameState (gold and copies update,
which immediately re-ranks everything — the feedback loop is the point).
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ...core.models import GameState, MetaComp, SetData
from ...core.recommender import RecommendationEngine
from ...services.bus import EventBus
from ...services.game_tracker import GameTracker


class RecommendationsPanel(QWidget):
    def __init__(
        self,
        set_data: SetData,
        tracker: GameTracker,
        engine: RecommendationEngine,
        bus: EventBus,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.set_data = set_data
        self.tracker = tracker
        self.engine = engine
        self._target: Optional[MetaComp] = None
        self._state: GameState = tracker.state
        self._build_ui()
        tracker.state_changed.connect(self._on_state)
        bus.comp_selected.connect(self._on_comp)
        self._recompute()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        shop_box = QGroupBox("Tienda actual (manual o vía fuente automática)")
        shop_layout = QHBoxLayout(shop_box)
        champs = sorted(self.set_data.champions.values(), key=lambda c: (c.cost, c.name))
        self.slot_combos: list[QComboBox] = []
        for slot in range(5):
            combo = QComboBox()
            combo.addItem("—", None)
            for champ in champs:
                combo.addItem(f"{champ.name} ({champ.cost})", champ.id)
            combo.currentIndexChanged.connect(
                lambda _i, s=slot, c=combo: self.tracker.set_shop_slot(s, c.currentData())
            )
            shop_layout.addWidget(combo)
            self.slot_combos.append(combo)
        root.addWidget(shop_box)

        self.target_label = QLabel("Comp objetivo: (ninguna — selecciónala en «Composiciones»)")
        root.addWidget(self.target_label)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Unidad", "Coste", "Puntos", "Por qué"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        root.addWidget(self.table, stretch=1)

        bottom = QHBoxLayout()
        self.buy_button = QPushButton("Comprar seleccionada")
        self.buy_button.clicked.connect(self._buy_selected)
        bottom.addWidget(self.buy_button)
        bottom.addStretch(1)
        root.addLayout(bottom)

        self.advice_label = QLabel("")
        self.advice_label.setWordWrap(True)
        root.addWidget(self.advice_label)

    # ------------------------------------------------------------ handlers
    def _on_state(self, state: GameState) -> None:
        self._state = state
        for slot, combo in enumerate(self.slot_combos):
            champ_id = state.shop[slot] if slot < len(state.shop) else None
            idx = combo.findData(champ_id)
            combo.blockSignals(True)
            combo.setCurrentIndex(max(idx, 0))
            combo.blockSignals(False)
        self._recompute()

    def _on_comp(self, comp: MetaComp) -> None:
        self._target = comp
        self.target_label.setText(f"Comp objetivo: {comp.name}")
        self._recompute()

    def _recompute(self) -> None:
        recs = self.engine.recommend_shop(self._state, self.set_data, self._target)
        self.table.setRowCount(len(recs))
        for i, rec in enumerate(recs):
            name = rec.name + ("" if rec.affordable else "  (sin oro)")
            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.ItemDataRole.UserRole, rec)
            self.table.setItem(i, 0, name_item)
            self.table.setItem(i, 1, QTableWidgetItem(str(rec.cost)))
            self.table.setItem(i, 2, QTableWidgetItem(f"{rec.score:g}"))
            self.table.setItem(i, 3, QTableWidgetItem(" · ".join(rec.reasons)))
        tips = self.engine.roll_or_level(self._state, self.set_data, self._target)
        self.advice_label.setText("\n".join(f"→ {t}" for t in tips))

    def _buy_selected(self) -> None:
        items = self.table.selectedItems()
        if not items:
            return
        rec = items[0].data(Qt.ItemDataRole.UserRole)
        if rec and rec.slots:
            self.tracker.buy_from_shop(rec.slots[0])
