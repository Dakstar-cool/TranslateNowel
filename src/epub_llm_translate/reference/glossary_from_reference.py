from __future__ import annotations

from collections.abc import Iterable
import re
from typing import Any

import yaml

from epub_llm_translate.backends import BackendUnavailableError, ChatMessage, create_backend
from epub_llm_translate.config import AppConfig
from epub_llm_translate.db.repositories import Repository
from epub_llm_translate.utils import contains_hangul, truncate


def extract_reference_glossary(
    config: AppConfig,
    repo: Repository,
    reference_rows: Iterable[Any],
    use_llm: bool = True,
    max_chapters: int | None = None,
) -> tuple[list[dict[str, object]], list[str]]:
    if not use_llm:
        return [], []
    backend = create_backend(config.models.glossary)
    candidates: dict[str, dict[str, object]] = {}
    errors: list[str] = []
    max_windows = max(1, min(config.reference.max_examples_per_block, 4))
    for ref_index, ref_row in enumerate(reference_rows, start=1):
        if max_chapters is not None and ref_index > max_chapters:
            break
        chapter_id = int(ref_row["chapter_id"])
        source_paragraphs = [row["source_text"] for row in repo.list_blocks([chapter_id])]
        reference_paragraphs = [line.strip() for line in ref_row["text"].splitlines() if line.strip()]
        if not source_paragraphs or not reference_paragraphs:
            continue
        source_windows = _sample_windows(source_paragraphs, max_windows, config.reference.example_max_chars)
        reference_windows = _sample_windows(reference_paragraphs, max_windows, config.reference.example_max_chars)
        for window_index, (source_excerpt, reference_excerpt) in enumerate(zip(source_windows, reference_windows), start=1):
            prompt = _reference_glossary_prompt(source_excerpt, reference_excerpt)
            try:
                output = backend.generate([ChatMessage("user", prompt)])
            except BackendUnavailableError:
                raise
            except Exception as exc:
                errors.append(f"chapter {chapter_id} window {window_index}: {exc}")
                continue
            for term in parse_reference_glossary_terms(output):
                source = str(term.get("source", "")).strip()
                translation = str(term.get("translation", "")).strip()
                if not source or not translation or not contains_hangul(source) or contains_hangul(translation):
                    continue
                confidence = _as_float(term.get("confidence"), default=0.5)
                existing = candidates.get(source)
                if existing and _as_float(existing.get("confidence"), default=0.0) >= confidence:
                    existing.setdefault("evidence", [])
                    existing["evidence"].append(_evidence(chapter_id, window_index, confidence))
                    continue
                candidates[source] = {
                    "source": source,
                    "translation": translation,
                    "category": str(term.get("category", "unknown")).strip() or "unknown",
                    "status": "needs_review",
                    "priority": "high",
                    "confidence": confidence,
                    "evidence": [_evidence(chapter_id, window_index, confidence)],
                }
    return sorted(candidates.values(), key=lambda item: str(item["source"])), errors


def parse_reference_glossary_terms(output: str) -> list[dict[str, Any]]:
    text = _strip_code_fence(output)
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        return []
    if isinstance(data, list):
        raw_terms = data
    elif isinstance(data, dict):
        raw_terms = data.get("terms", [])
    else:
        return []
    terms: list[dict[str, Any]] = []
    for item in raw_terms:
        if isinstance(item, dict):
            terms.append(item)
    return terms


def _reference_glossary_prompt(source_excerpt: str, reference_excerpt: str) -> str:
    return "\n".join(
        [
            "/no_think",
            "Build Korean-to-Russian glossary candidates from aligned novel excerpts.",
            "Do not think out loud. Do not output reasoning, comments, labels, or explanations.",
            "Use the Russian reference only as evidence for names, titles, places, groups, and recurring world terms.",
            "Do not translate or summarize the excerpts.",
            "Do not copy long passages.",
            "Return YAML only in this exact shape:",
            "terms:",
            '  - source: "Korean term"',
            '    translation: "Russian approved-looking term"',
            '    category: "name|place|group|title|world_term|other"',
            "    confidence: 0.0",
            "",
            "KOREAN SOURCE EXCERPT:",
            truncate(source_excerpt, 1800),
            "",
            "RUSSIAN REFERENCE EXCERPT:",
            truncate(reference_excerpt, 1800),
        ]
    )


def _sample_windows(paragraphs: list[str], max_windows: int, max_chars: int) -> list[str]:
    if not paragraphs:
        return []
    if max_windows == 1 or len(paragraphs) <= max_windows:
        return [truncate("\n".join(paragraphs[: max(1, max_windows)]), max_chars)]
    indexes = [0, len(paragraphs) // 2, max(0, len(paragraphs) - 3)]
    windows: list[str] = []
    seen: set[int] = set()
    for index in indexes[:max_windows]:
        if index in seen:
            continue
        seen.add(index)
        windows.append(truncate("\n".join(paragraphs[index : index + 3]), max_chars))
    return windows


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    match = re.search(r"```(?:yaml|yml)?\s*(.*?)```", stripped, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return stripped


def _evidence(chapter_id: int, window_index: int, confidence: float) -> dict[str, object]:
    return {
        "type": "reference_llm",
        "chapter_id": chapter_id,
        "window_index": window_index,
        "confidence": confidence,
    }


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
