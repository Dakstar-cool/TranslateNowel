from __future__ import annotations

from PySide6.QtWidgets import QPushButton, QTextEdit, QVBoxLayout, QWidget

from epub_llm_translate.db.repositories import Repository


class ReferenceExamplesViewer(QWidget):
    def __init__(self, repo: Repository):
        super().__init__()
        self.repo = repo
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        layout = QVBoxLayout(self)
        layout.addWidget(refresh)
        layout.addWidget(self.text)
        self.refresh()

    def refresh(self) -> None:
        examples = self.repo.list_reference_examples(limit=100)
        chunks = []
        for row in examples:
            chunks.append(f"Chapter {row['chapter_id']} | {row['tags'] or ''}\n{row['reference_excerpt']}")
        self.text.setPlainText("\n\n---\n\n".join(chunks))

