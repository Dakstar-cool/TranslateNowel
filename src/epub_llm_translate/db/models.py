from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChapterBlock:
    block_id: str
    chapter_id: int
    block_index: int
    paragraph_index: int | None
    source_text: str
    source_hash: str
    status: str = "pending"


@dataclass(frozen=True)
class QualityIssue:
    block_id: str
    chapter_id: int
    paragraph_index: int
    issue_type: str
    issue_severity: str
    source_term: str | None = None
    expected_translation: str | None = None
    actual_translation: str | None = None
    target_text: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    status: str = "needs_review"

