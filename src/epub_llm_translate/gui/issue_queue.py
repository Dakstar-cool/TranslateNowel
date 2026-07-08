from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QPushButton, QTableView, QVBoxLayout, QWidget

from epub_llm_translate.config import AppConfig
from epub_llm_translate.db.repositories import Repository

from .context_review_editor import ContextReviewDialog
from .view_models import SimpleTableModel, rows_to_dicts


class IssueQueueWidget(QWidget):
    def __init__(self, config: AppConfig, repo: Repository):
        super().__init__()
        self.config = config
        self.repo = repo
        self.model = SimpleTableModel(
            [
                "issue_id",
                "chapter_id",
                "paragraph_index",
                "issue_type",
                "issue_severity",
                "source_term",
                "expected_translation",
                "actual_translation",
                "status",
            ]
        )
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.doubleClicked.connect(self.open_issue)
        self.filter = QComboBox()
        self.filter.addItems(["all", "needs_review", "high severity", "glossary issues", "remaining Hangul", "length warnings", "approved", "locked"])
        self.filter.currentTextChanged.connect(self.refresh)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        top = QHBoxLayout()
        top.addWidget(self.filter)
        top.addWidget(refresh)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table)
        self.refresh()

    def refresh(self) -> None:
        selected = self.filter.currentText()
        rows = rows_to_dicts(self.repo.list_issues(None if selected == "all" else None, limit=5000))
        if selected == "needs_review":
            rows = [row for row in rows if row.get("status") == "needs_review"]
        elif selected == "high severity":
            rows = [row for row in rows if row.get("issue_severity") == "high" and row.get("status") != "approved"]
        elif selected == "glossary issues":
            rows = [row for row in rows if "glossary" in str(row.get("issue_type", ""))]
        elif selected == "remaining Hangul":
            rows = [row for row in rows if "hangul" in str(row.get("issue_type", "")).lower()]
        elif selected == "length warnings":
            rows = [row for row in rows if "length" in str(row.get("issue_type", ""))]
        elif selected == "approved":
            rows = [row for row in rows if row.get("status") == "approved"]
        elif selected == "locked":
            locked_blocks = {row["block_id"] for row in self.repo.list_blocks() if row["locked_by"]}
            rows = [row for row in rows if row.get("block_id") in locked_blocks]
        self.model.set_rows(rows)
        self.table.resizeColumnsToContents()

    def open_issue(self, index) -> None:
        issue = self.model.row_dict(index.row())
        dialog = ContextReviewDialog(self.config, self.repo, int(issue["issue_id"]), self)
        dialog.exec()
        self.refresh()

