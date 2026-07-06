"""Meta composition browser.

Pulls comps from whichever CompProvider the user picks (local JSON, MetaTFT…)
without blocking the UI, resolves unit names to the current set's champion
ids, and publishes the selection on the EventBus for the board planner,
recommendation panel and overlay to consume.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
    QVBoxLayout, QWidget,
)

from ...core.models import MetaComp, SetData
from ...data.providers.base import CompProvider
from ...services.bus import EventBus
from ...services.static_data import resolve_comp
from ...services.workers import run_in_pool


class CompBrowser(QWidget):
    def __init__(
        self,
        set_data: SetData,
        providers: dict[str, CompProvider],
        bus: EventBus,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.set_data = set_data
        self.providers = providers
        self.bus = bus
        self._build_ui()
        if self.providers:
            self._refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Fuente:"))
        self.source_combo = QComboBox()
        self.source_combo.addItems(list(self.providers))
        bar.addWidget(self.source_combo, stretch=1)
        self.refresh_button = QPushButton("Actualizar")
        self.refresh_button.clicked.connect(self._refresh)
        bar.addWidget(self.refresh_button)
        root.addLayout(bar)

        self.list = QListWidget()
        self.list.itemSelectionChanged.connect(self._on_selected)
        root.addWidget(self.list, stretch=1)

        self.detail = QLabel("Selecciona una composición.")
        self.detail.setWordWrap(True)
        root.addWidget(self.detail)

    # ------------------------------------------------------------------
    def _refresh(self) -> None:
        name = self.source_combo.currentText()
        provider = self.providers.get(name)
        if provider is None:
            return
        self.refresh_button.setEnabled(False)
        self.bus.notify.emit(f"Cargando comps de {name}…")
        run_in_pool(provider.fetch_comps, self._on_comps, self._on_error)

    def _on_comps(self, comps: object) -> None:
        self.refresh_button.setEnabled(True)
        self.list.clear()
        for comp in comps:  # type: ignore[assignment]
            label = comp.name
            if comp.avg_place is not None:
                label += f"  ·  media {comp.avg_place:.2f}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, comp)
            self.list.addItem(item)
        self.bus.notify.emit(f"{self.list.count()} composiciones cargadas.")

    def _on_error(self, message: str) -> None:
        self.refresh_button.setEnabled(True)
        self.bus.notify.emit(f"Error cargando comps: {message}")

    def _on_selected(self) -> None:
        items = self.list.selectedItems()
        if not items:
            return
        comp: MetaComp = items[0].data(Qt.ItemDataRole.UserRole)
        resolved, warnings = resolve_comp(self.set_data, comp)
        lines = [f"{len(resolved.units)} unidades · fuente: {resolved.source}"]
        for unit in resolved.units:
            champ = self.set_data.get(unit.champion_id)
            display = champ.name if champ else unit.champion_id
            lines.append(f"  • {display} ({unit.role.value})")
        if warnings:
            lines.append("⚠ " + " · ".join(warnings))
        self.detail.setText("\n".join(lines))
        self.bus.comp_selected.emit(resolved)
