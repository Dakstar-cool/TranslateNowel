from __future__ import annotations

from epub_llm_translate.config import AppConfig
from epub_llm_translate.db.repositories import Repository
from epub_llm_translate.qa.checks import check_block_quality
from epub_llm_translate.qa.report_writer import write_issue_reports


def check_draft(config: AppConfig, repo: Repository, glossary: list[dict[str, str]]) -> dict[str, object]:
    repo.clear_issues("draft")
    created = 0
    for row in repo.list_blocks():
        target = row["human_draft_edit"] or row["draft_translation"]
        for issue in check_block_quality(row, target, glossary, config.quality, "draft"):
            repo.insert_issue(issue)
            created += 1
    rows = repo.list_issues(limit=100000)
    paths = write_issue_reports(
        rows,
        config.workdir / "draft_quality_report.csv",
        config.workdir / "draft_quality_report.html",
        "Draft Quality Report",
    )
    repo.log_event("check_draft", f"Created {created} draft quality issues")
    return {"issues": created, **paths}

