from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QInputDialog, QPushButton, QTableView, QVBoxLayout, QWidget

from epub_llm_translate.db.repositories import Repository

from .view_models import SimpleTableModel, rows_to_dicts


class GlossaryEditorWidget(QWidget):
    def __init__(self, repo: Repository):
        super().__init__()
        self.repo = repo
        self.model = SimpleTableModel(["term_id", "source_term", "translation", "category", "status", "priority", "notes"])
        self.table = QTableView()
        self.table.setModel(self.model)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        add = QPushButton("Add Term")
        add.clicked.connect(self.add_term)
        mark = QPushButton("Mark Needs Review")
        mark.clicked.connect(self.mark_needs_review)
        top = QHBoxLayout()
        top.addWidget(refresh)
        top.addWidget(add)
        top.addWidget(mark)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.table)
        self.refresh()

    def refresh(self) -> None:
        self.model.set_rows(rows_to_dicts(self.repo.list_glossary_terms()))
        self.table.resizeColumnsToContents()

    def add_term(self) -> None:
        source, ok = QInputDialog.getText(self, "Source Term", "Korean source term")
        if not ok or not source.strip():
            return
        translation, ok = QInputDialog.getText(self, "Russian Translation", "Approved Russian term")
        if not ok or not translation.strip():
            return
        self.repo.add_glossary_term(source.strip(), translation.strip(), notes="Added in GUI")
        self.refresh()

    def mark_needs_review(self) -> None:
        index = self.table.currentIndex()
        if not index.isValid():
            return
        row = self.model.row_dict(index.row())
        self.repo.update_glossary_term_status(int(row["term_id"]), "needs_review")
        self.refresh()
