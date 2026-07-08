from __future__ import annotations

from PySide6.QtWidgets import QPushButton, QTableView, QVBoxLayout, QWidget

from epub_llm_translate.db.repositories import Repository

from .view_models import SimpleTableModel, rows_to_dicts


class EditHistoryViewer(QWidget):
    def __init__(self, repo: Repository):
        super().__init__()
        self.repo = repo
        self.model = SimpleTableModel(["edit_id", "block_id", "field_name", "old_text", "new_text", "edited_by", "edit_reason", "created_at"])
        self.table = QTableView()
        self.table.setModel(self.model)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        layout = QVBoxLayout(self)
        layout.addWidget(refresh)
        layout.addWidget(self.table)
        self.refresh()

    def refresh(self) -> None:
        self.model.set_rows(rows_to_dicts(self.repo.list_edit_history(limit=500)))
        self.table.resizeColumnsToContents()

