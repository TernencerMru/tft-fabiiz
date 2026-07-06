"""Run blocking work (network fetches) off the UI thread.

Qt idiom: QRunnable on the global QThreadPool + signals to hop the result
back onto the GUI thread. Usage::

    run_in_pool(provider.fetch_comps, on_result=self._fill, on_error=self._oops)
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)


class Worker(QRunnable):
    def __init__(self, fn: Callable, *args, **kwargs) -> None:
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.signals = WorkerSignals()

    def run(self) -> None:  # executes in a pool thread
        try:
            self.signals.result.emit(self.fn(*self.args, **self.kwargs))
        except Exception as exc:  # noqa: BLE001 — boundary: report, don't crash
            self.signals.error.emit(str(exc))


def run_in_pool(
    fn: Callable,
    on_result: Callable[[object], None],
    on_error: Optional[Callable[[str], None]] = None,
    *args,
    **kwargs,
) -> Worker:
    worker = Worker(fn, *args, **kwargs)
    worker.signals.result.connect(on_result)
    if on_error:
        worker.signals.error.connect(on_error)
    QThreadPool.globalInstance().start(worker)
    return worker
