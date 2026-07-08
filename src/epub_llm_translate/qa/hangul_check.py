from __future__ import annotations

from epub_llm_translate.utils import contains_hangul


def has_remaining_hangul(text: str | None) -> bool:
    return contains_hangul(text)

