from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QPushButton, QTableView, QTextEdit, QVBoxLayout, QWidget

from epub_llm_translate.db.repositories import Repository

from .view_models import SimpleTableModel, rows_to_dicts


class ChapterBrowserWidget(QWidget):
    def __init__(self, repo: Repository):
        super().__init__()
        self.repo = repo
        self.model = SimpleTableModel(["chapter_id", "title", "status", "block_count", "issue_count", "high_issue_count"])
        self.table = QTableView()
        self.table.setModel(self.model)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        self.table.doubleClicked.connect(self.open_preview)
        layout = QVBoxLayout(self)
        layout.addWidget(refresh)
        split = QHBoxLayout()
        split.addWidget(self.table, 2)
        split.addWidget(self.preview, 3)
        layout.addLayout(split)
        self.refresh()

    def refresh(self) -> None:
        self.model.set_rows(rows_to_dicts(self.repo.chapters_summary()))
        self.table.resizeColumnsToContents()

    def open_preview(self, index) -> None:
        row = self.model.row_dict(index.row())
        blocks = self.repo.list_blocks([int(row["chapter_id"])])
        lines = [block["human_final_edit"] or block["revised_translation"] or block["human_draft_edit"] or block["draft_translation"] or block["source_text"] for block in blocks[:40]]
        self.preview.setPlainText("\n\n".join(lines))

