from __future__ import annotations


HIGH_SEVERITY_STATUSES = {"needs_review", "open"}


def can_revise_block(row, unresolved_high_issue_count: int, review_mode: str) -> bool:
    if row["locked_by"]:
        return False
    if review_mode == "auto":
        return True
    if review_mode == "assisted" and unresolved_high_issue_count > 0:
        return False
    if review_mode == "strict" and row["status"] != "approved":
        return False
    return True

