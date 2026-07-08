from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget

from epub_llm_translate.config import load_config
from epub_llm_translate.db.connection import initialize_database
from epub_llm_translate.db.repositories import Repository

from .chapter_browser import ChapterBrowserWidget
from .dashboard import DashboardWidget
from .edit_history_viewer import EditHistoryViewer
from .glossary_editor import GlossaryEditorWidget
from .issue_queue import IssueQueueWidget
from .logs_viewer import LogsViewer
from .reference_examples_viewer import ReferenceExamplesViewer


class MainWindow(QMainWindow):
    def __init__(self, config_path: Path):
        super().__init__()
        self.config = load_config(config_path)
        self.conn = initialize_database(self.config.db_path)
        self.repo = Repository(self.conn)
        self.setWindowTitle("EPUB LLM Translate Review")
        self.resize(1280, 820)
        tabs = QTabWidget()
        self.dashboard = DashboardWidget(self.repo)
        self.chapter_browser = ChapterBrowserWidget(self.repo)
        self.issue_queue = IssueQueueWidget(self.config, self.repo)
        self.glossary = GlossaryEditorWidget(self.repo)
        self.reference_examples = ReferenceExamplesViewer(self.repo)
        self.edit_history = EditHistoryViewer(self.repo)
        self.logs = LogsViewer(self.repo)
        tabs.addTab(self.dashboard, "Dashboard")
        tabs.addTab(self.chapter_browser, "Chapters")
        tabs.addTab(self.issue_queue, "Issue Queue")
        tabs.addTab(self.glossary, "Glossary")
        tabs.addTab(self.reference_examples, "Reference Examples")
        tabs.addTab(self.edit_history, "Edit History")
        tabs.addTab(self.logs, "Logs")
        self.setCentralWidget(tabs)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_current)
        self.timer.start(max(1, self.config.gui.refresh_seconds) * 1000)

    def refresh_current(self) -> None:
        widget = self.centralWidget().currentWidget()
        if hasattr(widget, "refresh"):
            widget.refresh()


def run_gui(config_path: Path) -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(config_path)
    window.show()
    app.exec()

