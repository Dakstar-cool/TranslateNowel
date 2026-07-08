from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from epub_llm_translate.config import AppConfig
from epub_llm_translate.db.repositories import Repository
from epub_llm_translate.pipeline.jobs import enqueue_job


class ContextReviewDialog(QDialog):
    def __init__(self, config: AppConfig, repo: Repository, issue_id: int, parent=None):
        super().__init__(parent)
        self.config = config
        self.repo = repo
        self.issue_id = issue_id
        self.issue = self.repo.get_issue(issue_id)
        if self.issue is None:
            raise KeyError(f"Unknown issue_id: {issue_id}")
        self.block = self.repo.get_block(self.issue["block_id"])
        if self.block is None:
            raise KeyError(f"Missing block for issue_id: {issue_id}")
        self.setWindowTitle(f"Issue {issue_id} - Context Review")
        self.resize(1100, 760)
        self.full_context_override = QCheckBox("Edit full context")
        self.full_context_override.toggled.connect(self._set_edit_scope)
        self.term_label = QLabel(self._issue_label())
        self.source_edits: list[QTextEdit] = []
        self.target_edits: list[QTextEdit] = []
        self._build()
        self.refresh()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(self.term_label)
        layout.addWidget(self.full_context_override)
        grid = QGridLayout()
        grid.addWidget(QLabel("Korean source context"), 0, 0)
        grid.addWidget(QLabel("Russian draft/revised context"), 0, 1)
        self.context_layout = grid
        layout.addLayout(grid)
        actions = QHBoxLayout()
        for title, callback in [
            ("Save Human Draft Edit", self.save_human_draft),
            ("Save Human Final Edit", self.save_human_final),
            ("Approve Issue", self.approve_issue),
            ("Approve Block", self.approve_block),
            ("Retry Draft", self.retry_draft),
            ("Retry Revision", self.retry_revision),
            ("Repair Issue", self.queue_repair),
            ("Lock Block", self.lock_block),
            ("Unlock Block", self.unlock_block),
            ("Add Glossary Term", self.add_glossary_term),
            ("Open Next Issue", self.open_next_issue),
            ("Refresh", self.refresh),
        ]:
            button = QPushButton(title)
            button.clicked.connect(callback)
            actions.addWidget(button)
        layout.addLayout(actions)

    def refresh(self) -> None:
        while self.context_layout.count() > 2:
            item = self.context_layout.takeAt(2)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.source_edits.clear()
        self.target_edits.clear()
        context = self.repo.get_context(self.block["block_id"], self.config.review.context_before_paragraphs, self.config.review.context_after_paragraphs)
        for visual_row, row in enumerate(context["rows"], start=1):
            source = QTextEdit()
            source.setPlainText(row["source_text"])
            source.setReadOnly(True)
            target = QTextEdit()
            target.setPlainText(row["human_final_edit"] or row["revised_translation"] or row["human_draft_edit"] or row["draft_translation"] or "")
            is_target = row["block_id"] == self.block["block_id"]
            target.setReadOnly(not is_target)
            if is_target:
                self.target_edit = target
            self.source_edits.append(source)
            self.target_edits.append(target)
            self.context_layout.addWidget(source, visual_row, 0)
            self.context_layout.addWidget(target, visual_row, 1)
        self._set_edit_scope(self.full_context_override.isChecked())

    def _set_edit_scope(self, enabled: bool) -> None:
        for edit in self.target_edits:
            edit.setReadOnly(not enabled)
        if hasattr(self, "target_edit"):
            self.target_edit.setReadOnly(False)

    def _issue_label(self) -> str:
        parts = [
            f"Type: {self.issue['issue_type']}",
            f"Severity: {self.issue['issue_severity']}",
        ]
        if self.issue["source_term"]:
            parts.append(f"Term: {self.issue['source_term']}")
        if self.issue["expected_translation"]:
            parts.append(f"Expected: {self.issue['expected_translation']}")
        return " | ".join(parts)

    def save_human_draft(self) -> None:
        self.repo.save_human_edit(self.block["block_id"], "human_draft_edit", self.target_edit.toPlainText(), reason=f"issue:{self.issue_id}")
        QMessageBox.information(self, "Saved", "Human draft edit saved.")

    def save_human_final(self) -> None:
        self.repo.save_human_edit(self.block["block_id"], "human_final_edit", self.target_edit.toPlainText(), reason=f"issue:{self.issue_id}")
        QMessageBox.information(self, "Saved", "Human final edit saved.")

    def approve_issue(self) -> None:
        self.repo.approve_issue(self.issue_id)
        self.accept()

    def approve_block(self) -> None:
        self.repo.set_status(self.block["block_id"], "approved")
        QMessageBox.information(self, "Approved", "Block approved.")

    def retry_draft(self) -> None:
        enqueue_job(self.repo, "retry_draft", block_id=self.block["block_id"], chapter_id=self.block["chapter_id"], priority=10)
        QMessageBox.information(self, "Queued", "Retry draft job queued.")

    def retry_revision(self) -> None:
        enqueue_job(self.repo, "retry_revision", block_id=self.block["block_id"], chapter_id=self.block["chapter_id"], priority=10)
        QMessageBox.information(self, "Queued", "Retry revision job queued.")

    def queue_repair(self) -> None:
        enqueue_job(self.repo, "repair_issue", block_id=self.block["block_id"], chapter_id=self.block["chapter_id"], priority=20, payload={"issue_id": self.issue_id})
        QMessageBox.information(self, "Queued", "Repair issue job queued.")

    def lock_block(self) -> None:
        self.repo.lock_block(self.block["block_id"])
        QMessageBox.information(self, "Locked", "Block locked.")

    def unlock_block(self) -> None:
        self.repo.unlock_block(self.block["block_id"])
        QMessageBox.information(self, "Unlocked", "Block unlocked.")

    def add_glossary_term(self) -> None:
        source = self.issue["source_term"] or ""
        translation = self.issue["expected_translation"] or ""
        if not source or not translation:
            QMessageBox.warning(self, "Missing term", "Issue does not contain a source and expected translation.")
            return
        self.repo.add_glossary_term(source, translation, notes=f"Added from issue {self.issue_id}")
        self.repo.set_status(self.block["block_id"], "needs_review", "needs_recheck")
        QMessageBox.information(self, "Glossary", "Glossary term added and block marked for recheck.")

    def open_next_issue(self) -> None:
        rows = self.repo.list_issues(status="needs_review", limit=2)
        for row in rows:
            if row["issue_id"] != self.issue_id:
                self.issue_id = row["issue_id"]
                self.issue = row
                self.block = self.repo.get_block(row["block_id"])
                self.term_label.setText(self._issue_label())
                self.refresh()
                return
        QMessageBox.information(self, "Done", "No next issue found.")
