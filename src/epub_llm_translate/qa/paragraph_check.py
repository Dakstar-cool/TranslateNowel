from __future__ import annotations


def paragraph_count(text: str | None) -> int:
    return len([line for line in (text or "").splitlines() if line.strip()])


def paragraph_count_mismatch(source: str, target: str | None) -> bool:
    source_count = paragraph_count(source)
    target_count = paragraph_count(target)
    if source_count <= 1:
        return False
    return source_count != target_count

