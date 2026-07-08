from __future__ import annotations


def semantic_check_placeholder(source: str, draft: str | None, revised: str | None) -> list[str]:
    issues: list[str] = []
    if revised and draft and len(revised) < max(1, len(draft) * 0.45):
        issues.append("possible_semantic_drift_shortening")
    if source and not (draft or revised):
        issues.append("missing_translation")
    return issues

