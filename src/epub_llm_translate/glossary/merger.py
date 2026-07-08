from __future__ import annotations

from pathlib import Path

import yaml


def merge_candidates(*candidate_sets: list[dict[str, object]]) -> list[dict[str, object]]:
    merged: dict[str, dict[str, object]] = {}
    for candidates in candidate_sets:
        for candidate in candidates:
            source = str(candidate.get("source", "")).strip()
            if not source:
                continue
            existing = merged.setdefault(source, {**candidate, "evidence": []})
            existing["translation"] = existing.get("translation") or candidate.get("translation", "")
            existing["category"] = existing.get("category") or candidate.get("category", "unknown")
            existing["priority"] = _max_priority(str(existing.get("priority", "normal")), str(candidate.get("priority", "normal")))
            existing.setdefault("evidence", [])
            existing["evidence"].extend(candidate.get("evidence", []))
    return sorted(merged.values(), key=lambda item: str(item.get("source", "")))


def _max_priority(left: str, right: str) -> str:
    order = {"low": 0, "normal": 1, "high": 2}
    return left if order.get(left, 1) >= order.get(right, 1) else right


def load_candidate_file(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if isinstance(data, list):
        raw_terms = data
    elif isinstance(data, dict):
        raw_terms = data.get("terms", [])
    else:
        return []
    return [item for item in raw_terms if isinstance(item, dict)]
