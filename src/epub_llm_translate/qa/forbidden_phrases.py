from __future__ import annotations


FORBIDDEN_PHRASES = [
    "as an ai",
    "i cannot",
    "here is the translation",
    "перевод:",
    "как языковая модель",
    "я не могу",
]


def find_forbidden_phrase(text: str | None) -> str | None:
    lowered = (text or "").lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in lowered:
            return phrase
    return None

