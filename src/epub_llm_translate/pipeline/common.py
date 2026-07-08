from __future__ import annotations

from pathlib import Path

from epub_llm_translate.config import AppConfig
from epub_llm_translate.glossary.validator import GlossaryValidationError, validate_approved_glossary


def approved_glossary_path(config: AppConfig) -> Path:
    return config.workdir / "glossary.approved.yaml"


def require_approved_glossary(config: AppConfig) -> list[dict[str, str]]:
    try:
        return validate_approved_glossary(approved_glossary_path(config))
    except GlossaryValidationError as exc:
        raise RuntimeError(str(exc)) from exc

