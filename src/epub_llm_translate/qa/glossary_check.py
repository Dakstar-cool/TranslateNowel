from __future__ import annotations


def missing_glossary_terms(source: str, target: str | None, terms: list[dict[str, str]]) -> list[dict[str, str]]:
    target_text = target or ""
    missing: list[dict[str, str]] = []
    for term in terms:
        src = str(term.get("source", ""))
        ru = str(term.get("translation", ""))
        if src and ru and src in source and ru not in target_text:
            missing.append(term)
    return missing

