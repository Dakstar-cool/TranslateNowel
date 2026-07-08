from __future__ import annotations

from epub_llm_translate.config import AppConfig
from epub_llm_translate.db.repositories import Repository
from epub_llm_translate.qa.checks import check_block_quality
from epub_llm_translate.qa.report_writer import write_issue_reports
from epub_llm_translate.qa.semantic_check import semantic_check_placeholder


def final_check(config: AppConfig, repo: Repository, glossary: list[dict[str, str]], chapter_ids: list[int] | None = None) -> dict[str, object]:
    _clear_stage_issues(repo, "final", chapter_ids)
    created = 0
    for row in repo.list_blocks(chapter_ids):
        target = repo.final_text_for_row(row)
        for issue in check_block_quality(row, target, glossary, config.quality, "final"):
            repo.insert_issue(issue)
            created += 1
        for issue_type in semantic_check_placeholder(row["source_text"], row["draft_translation"], target):
            repo.insert_issue(
                {
                    "block_id": row["block_id"],
                    "chapter_id": row["chapter_id"],
                    "paragraph_index": row["paragraph_index"] or 0,
                    "issue_type": f"final:{issue_type}",
                    "issue_severity": "high",
                    "target_text": target,
                }
            )
            created += 1
    rows = _list_stage_issues(repo, "final", chapter_ids)
    paths = write_issue_reports(
        rows,
        config.workdir / "final_quality_report.csv",
        config.workdir / "final_quality_report.html",
        "Final Quality Report",
    )
    repo.log_event("final_check", f"Created {created} final quality issues")
    return {"issues": created, **paths}


def _clear_stage_issues(repo: Repository, stage: str, chapter_ids: list[int] | None) -> None:
    if not chapter_ids:
        repo.clear_issues(stage)
        return
    placeholders = ",".join("?" for _ in chapter_ids)
    repo.conn.execute(
        f"DELETE FROM quality_issues WHERE issue_type LIKE ? AND chapter_id IN ({placeholders})",
        [f"{stage}:%", *chapter_ids],
    )
    repo.conn.commit()


def _list_stage_issues(repo: Repository, stage: str, chapter_ids: list[int] | None):
    if not chapter_ids:
        return repo.list_issues(limit=100000)
    placeholders = ",".join("?" for _ in chapter_ids)
    return repo.conn.execute(
        f"""
        SELECT * FROM quality_issues
        WHERE issue_type LIKE ? AND chapter_id IN ({placeholders})
        ORDER BY
            CASE issue_severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
            chapter_id, paragraph_index, issue_id
        """,
        [f"{stage}:%", *chapter_ids],
    ).fetchall()
