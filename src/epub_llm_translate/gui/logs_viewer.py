from __future__ import annotations

from PySide6.QtWidgets import QPushButton, QTableView, QVBoxLayout, QWidget

from epub_llm_translate.db.repositories import Repository

from .view_models import SimpleTableModel, rows_to_dicts


class LogsViewer(QWidget):
    def __init__(self, repo: Repository):
        super().__init__()
        self.repo = repo
        self.model = SimpleTableModel(["event_id", "event_type", "message", "payload_json", "created_at"])
        self.table = QTableView()
        self.table.setModel(self.model)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        layout = QVBoxLayout(self)
        layout.addWidget(refresh)
        layout.addWidget(self.table)
        self.refresh()

    def refresh(self) -> None:
        self.model.set_rows(rows_to_dicts(self.repo.list_logs(limit=500)))
        self.table.resizeColumnsToContents()

