from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, Signal, Slot


class RefreshWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, callback: Callable[[], Any]):
        super().__init__()
        self.callback = callback

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(self.callback())
        except Exception as exc:
            self.failed.emit(str(exc))

