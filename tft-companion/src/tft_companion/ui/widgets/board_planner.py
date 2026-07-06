"""Board layout planner.

Renders the player half of the TFT board (4 rows × 7 columns of hexes,
odd rows offset by half a hex — row 0 is the FRONT line, row 3 the back
line) on a QGraphicsScene. Selecting a comp on the EventBus places one
draggable token per unit: units with an explicit ``position`` go there,
the rest are auto-placed with a simple role/cost heuristic (tanks front,
carries back). Tokens snap to the nearest hex on release.
"""
from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QGraphicsItemGroup, QGraphicsPolygonItem, QGraphicsScene,
    QGraphicsSimpleTextItem, QGraphicsView, QVBoxLayout, QWidget, QGraphicsItem,
)

from ...core.models import MetaComp, Role, SetData
from ...services.bus import EventBus

ROWS, COLS = 4, 7
HEX_SIZE = 34.0  # center-to-vertex radius (pointy-top hexes)

ROLE_COLORS = {
    Role.CARRY: QColor("#e06c75"),
    Role.CORE: QColor("#61afef"),
    Role.FLEX: QColor("#98c379"),
}


def hex_center(row: int, col: int, size: float = HEX_SIZE) -> QPointF:
    width = math.sqrt(3) * size
    x = col * width + (width / 2 if row % 2 else 0) + width / 2
    y = row * size * 1.5 + size
    return QPointF(x, y)


def hex_polygon(center: QPointF, size: float = HEX_SIZE) -> QPolygonF:
    points = []
    for i in range(6):
        angle = math.radians(60 * i - 30)  # pointy-top
        points.append(QPointF(
            center.x() + size * math.cos(angle),
            center.y() + size * math.sin(angle),
        ))
    return QPolygonF(points)


class ChampionToken(QGraphicsItemGroup):
    def __init__(self, name: str, role: Role, center: QPointF) -> None:
        super().__init__()
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

        body = QGraphicsPolygonItem(hex_polygon(QPointF(0, 0), HEX_SIZE * 0.82))
        body.setBrush(QBrush(ROLE_COLORS[role]))
        body.setPen(QPen(QColor("#1e222a"), 2))
        self.addToGroup(body)

        label = QGraphicsSimpleTextItem(name[:9])
        label.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        label.setBrush(QBrush(QColor("#1e222a")))
        rect = label.boundingRect()
        label.setPos(-rect.width() / 2, -rect.height() / 2)
        self.addToGroup(label)

        self.setPos(center)

    def mouseReleaseEvent(self, event) -> None:  # snap to nearest hex
        super().mouseReleaseEvent(event)
        best, best_d = None, float("inf")
        for row in range(ROWS):
            for col in range(COLS):
                center = hex_center(row, col)
                d = (center - self.pos()).manhattanLength()
                if d < best_d:
                    best, best_d = center, d
        if best is not None:
            self.setPos(best)


class BoardPlanner(QWidget):
    def __init__(self, set_data: SetData, bus: EventBus,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.set_data = set_data
        self._tokens: list[ChampionToken] = []

        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setBackgroundBrush(QBrush(QColor("#14161c")))
        layout = QVBoxLayout(self)
        layout.addWidget(self.view)

        self._draw_grid()
        bus.comp_selected.connect(self.place_comp)

    def _draw_grid(self) -> None:
        pen = QPen(QColor("#3a3f4b"), 1.5)
        brush = QBrush(QColor("#1e222a"))
        for row in range(ROWS):
            for col in range(COLS):
                cell = QGraphicsPolygonItem(hex_polygon(hex_center(row, col)))
                cell.setPen(pen)
                cell.setBrush(brush)
                cell.setZValue(-1)
                self.scene.addItem(cell)
        front = QGraphicsSimpleTextItem("← FRONT (fila 0)   ·   BACK (fila 3) →")
        front.setBrush(QBrush(QColor("#6b7280")))
        front.setPos(0, -26)
        self.scene.addItem(front)

    # ------------------------------------------------------------------
    def place_comp(self, comp: MetaComp) -> None:
        for token in self._tokens:
            self.scene.removeItem(token)
        self._tokens.clear()

        used: set[tuple[int, int]] = set()
        pending = []
        for unit in comp.units:
            if unit.position and 0 <= unit.position[0] < ROWS and 0 <= unit.position[1] < COLS:
                used.add(unit.position)
                self._add_token(unit.champion_id, unit.role, unit.position)
            else:
                pending.append(unit)
        for unit in pending:
            pos = self._auto_position(unit.role, unit.champion_id, used)
            used.add(pos)
            self._add_token(unit.champion_id, unit.role, pos)

    def _add_token(self, champion_id: str, role: Role, pos: tuple[int, int]) -> None:
        champ = self.set_data.get(champion_id)
        name = champ.name if champ else champion_id
        token = ChampionToken(name, role, hex_center(*pos))
        self.scene.addItem(token)
        self._tokens.append(token)

    def _auto_position(self, role: Role, champion_id: str,
                       used: set[tuple[int, int]]) -> tuple[int, int]:
        """Tanks/bruisers front, carries and squishy high-costs back."""
        champ = self.set_data.get(champion_id)
        cost = champ.cost if champ else 1
        rows = [3, 2] if (role is Role.CARRY or cost >= 4) else [0, 1]
        center_out = [3, 2, 4, 1, 5, 0, 6]
        for row in rows + [r for r in range(ROWS) if r not in rows]:
            for col in center_out:
                if (row, col) not in used:
                    return (row, col)
        return (0, 0)
