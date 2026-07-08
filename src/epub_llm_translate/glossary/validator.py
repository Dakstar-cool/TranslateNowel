from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from epub_llm_translate.utils import contains_hangul


class GlossaryValidationError(ValueError):
    pass


def load_glossary(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if isinstance(data, list):
        terms = data
    else:
        terms = data.get("terms", [])
    if not isinstance(terms, list):
        raise GlossaryValidationError("Glossary must contain a list under `terms`.")
    return terms


def validate_approved_glossary(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise GlossaryValidationError(f"Manual approval is incomplete: {path} does not exist.")
    terms = load_glossary(path)
    if not terms:
        raise GlossaryValidationError("Approved glossary is empty.")
    errors: list[str] = []
    source_to_translation: dict[str, str] = {}
    translation_to_sources: dict[str, set[str]] = {}
    for index, term in enumerate(terms, start=1):
        source = str(term.get("source", "")).strip()
        translation = str(term.get("translation", "")).strip()
        status = str(term.get("status", "approved")).strip()
        if not source:
            errors.append(f"Entry {index}: missing source")
        if not translation:
            errors.append(f"Entry {index}: missing translation")
        if status == "rejected":
            errors.append(f"Entry {index}: rejected term is present in approved glossary")
        if contains_hangul(translation):
            errors.append(f"Entry {index}: approved Russian translation contains Hangul")
        if source and translation:
            existing = source_to_translation.get(source)
            if existing and existing != translation:
                errors.append(f"Source term {source!r} maps to both {existing!r} and {translation!r}")
            source_to_translation[source] = translation
            translation_to_sources.setdefault(translation, set()).add(source)
    for translation, sources in translation_to_sources.items():
        normalized_sources = {_normalize_korean_glossary_source(source) for source in sources}
        if translation and len(normalized_sources) > 1:
            errors.append(f"Russian term {translation!r} maps from multiple source terms: {', '.join(sorted(sources))}")
    if errors:
        raise GlossaryValidationError("\n".join(errors))
    normalized = []
    for term in terms:
        normalized.append(
            {
                **term,
                "source": str(term["source"]).strip(),
                "translation": str(term["translation"]).strip(),
                "status": str(term.get("status", "approved")).strip() or "approved",
            }
        )
    return normalized


KOREAN_PARTICLES = (
    "에게서",
    "으로",
    "에게",
    "에서",
    "부터",
    "까지",
    "처럼",
    "보다",
    "하고",
    "이며",
    "라며",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "의",
    "에",
    "와",
    "과",
    "도",
    "로",
    "만",
)


def _normalize_korean_glossary_source(source: str) -> str:
    normalized = source.strip()
    changed = True
    while changed:
        changed = False
        for particle in KOREAN_PARTICLES:
            if len(normalized) > len(particle) and normalized.endswith(particle):
                normalized = normalized[: -len(particle)]
                changed = True
                break
    return normalized
