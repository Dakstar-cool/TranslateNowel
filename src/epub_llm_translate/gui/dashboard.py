from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QLabel, QPushButton, QWidget

from epub_llm_translate.db.repositories import Repository


class DashboardWidget(QWidget):
    def __init__(self, repo: Repository):
        super().__init__()
        self.repo = repo
        self.labels: dict[str, QLabel] = {}
        layout = QFormLayout(self)
        for key in [
            "total_chapters",
            "total_blocks",
            "draft_done",
            "revision_done",
            "issue_count",
            "high_issue_count",
            "locked_block_count",
            "backlog_size",
        ]:
            label = QLabel("0")
            self.labels[key] = label
            layout.addRow(key.replace("_", " ").title(), label)
        self.status_label = QLabel("idle")
        layout.addRow("Current Pipeline Status", self.status_label)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        layout.addRow(refresh)
        self.refresh()

    def refresh(self) -> None:
        summary = self.repo.dashboard_summary()
        for key, label in self.labels.items():
            label.setText(str(summary.get(key, 0)))
        events = self.repo.recent_events(1)
        self.status_label.setText(events[0]["message"] if events else "idle")

