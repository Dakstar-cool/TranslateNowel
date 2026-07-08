from __future__ import annotations


def suspicious_length_ratio(source: str, target: str | None, min_ratio: float, max_ratio: float) -> float | None:
    if not source or not target:
        return None
    ratio = len(target) / max(len(source), 1)
    if ratio < min_ratio or ratio > max_ratio:
        return ratio
    return None

