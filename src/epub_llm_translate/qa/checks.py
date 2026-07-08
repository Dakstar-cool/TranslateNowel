from __future__ import annotations

from epub_llm_translate.config import QualityConfig

from .forbidden_phrases import find_forbidden_phrase
from .glossary_check import missing_glossary_terms
from .hangul_check import has_remaining_hangul
from .length_check import suspicious_length_ratio
from .paragraph_check import paragraph_count_mismatch


def check_block_quality(row, target_text: str | None, terms: list[dict[str, str]], quality: QualityConfig, prefix: str) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    base = {
        "block_id": row["block_id"],
        "chapter_id": row["chapter_id"],
        "paragraph_index": row["paragraph_index"] or 0,
    }
    if not target_text:
        issues.append({**base, "issue_type": f"{prefix}:empty_block", "issue_severity": "high", "target_text": target_text})
    if target_text and quality.fail_on_remaining_hangul and has_remaining_hangul(target_text):
        issues.append({**base, "issue_type": f"{prefix}:remaining_hangul", "issue_severity": "high", "target_text": target_text})
    if target_text and (phrase := find_forbidden_phrase(target_text)):
        issues.append({**base, "issue_type": f"{prefix}:forbidden_phrase", "issue_severity": "high", "actual_translation": phrase, "target_text": target_text})
    if quality.warn_length_ratio_min and target_text:
        ratio = suspicious_length_ratio(row["source_text"], target_text, quality.warn_length_ratio_min, quality.warn_length_ratio_max)
        if ratio is not None:
            issues.append({**base, "issue_type": f"{prefix}:length_ratio", "issue_severity": "medium", "actual_translation": f"{ratio:.2f}", "target_text": target_text})
    if target_text and paragraph_count_mismatch(row["source_text"], target_text):
        issues.append({**base, "issue_type": f"{prefix}:paragraph_count", "issue_severity": "medium", "target_text": target_text})
    for term in missing_glossary_terms(row["source_text"], target_text, terms):
        issues.append(
            {
                **base,
                "issue_type": f"{prefix}:glossary_missing",
                "issue_severity": "high",
                "source_term": term.get("source"),
                "expected_translation": term.get("translation"),
                "target_text": target_text,
            }
        )
    return issues

