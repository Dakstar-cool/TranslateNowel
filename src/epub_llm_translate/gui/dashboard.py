from __future__ import annotations

from datetime import datetime, timezone
import json

from PySide6.QtWidgets import QFormLayout, QLabel, QProgressBar, QPushButton, QWidget

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
        self.draft_progress = QProgressBar()
        self.draft_progress.setRange(0, 100)
        self.draft_progress.setValue(0)
        self.draft_progress.setFormat("0/0")
        self.draft_progress_detail = QLabel("No draft translation job yet")
        self.draft_eta = QLabel("ETA: --:--")
        layout.addRow("Draft Progress", self.draft_progress)
        layout.addRow("Draft Details", self.draft_progress_detail)
        layout.addRow("Draft ETA", self.draft_eta)
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
        self._refresh_draft_progress()
        events = self.repo.recent_events(1)
        self.status_label.setText(events[0]["message"] if events else "idle")

    def _refresh_draft_progress(self) -> None:
        job = self.repo.latest_pipeline_job("draft_translate")
        if job is None:
            self.draft_progress.setValue(0)
            self.draft_progress.setFormat("0/0")
            self.draft_progress_detail.setText("No draft translation job yet")
            self.draft_eta.setText("ETA: --:--")
            return
        try:
            payload = json.loads(job["payload_json"] or "{}")
        except json.JSONDecodeError:
            payload = {}
        total = int(payload.get("total") or 0)
        processed = int(payload.get("processed") or 0)
        translated = int(payload.get("translated") or 0)
        failed = int(payload.get("failed") or 0)
        skipped = int(payload.get("skipped") or 0)
        pending = int(payload.get("pending") or 0)
        concurrency = int(payload.get("concurrency") or 1)
        status = str(payload.get("status") or job["status"] or "unknown")
        percent = int((processed / total) * 100) if total else 0
        self.draft_progress.setValue(max(0, min(100, percent)))
        self.draft_progress.setFormat(f"{processed}/{total} ({percent}%)")
        self.draft_progress_detail.setText(
            f"{status} | translated {translated}, failed {failed}, skipped {skipped}, pending {pending}, concurrency {concurrency}"
        )
        self.draft_eta.setText(f"ETA: {_eta_text(job['created_at'], processed, total, status)}")


def _eta_text(created_at: str, processed: int, total: int, status: str) -> str:
    if status == "done":
        return "done"
    if status == "aborted":
        return "aborted"
    if processed <= 0 or total <= processed:
        return "--:--"
    try:
        started = datetime.fromisoformat(created_at)
    except ValueError:
        return "--:--"
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    if elapsed <= 0:
        return "--:--"
    rate = processed / elapsed
    if rate <= 0:
        return "--:--"
    return _format_duration((total - processed) / rate)


def _format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
