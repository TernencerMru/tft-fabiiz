"""Application event bus (Observer pattern via Qt signals).

Widgets never talk to each other directly: the comp browser emits
``comp_selected`` and whoever cares (board planner, recommendations panel,
overlay) subscribes. Keeps every widget independently testable/replaceable.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class EventBus(QObject):
    comp_selected = Signal(object)   # MetaComp (already resolved to real ids)
    notify = Signal(str)             # user-facing status messages
