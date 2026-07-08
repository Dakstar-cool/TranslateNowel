from __future__ import annotations

from epub_llm_translate.db.repositories import Repository


def retrieve_reference_examples(repo: Repository, max_examples: int = 4) -> list[str]:
    return [row["reference_excerpt"] for row in repo.list_reference_examples(limit=max_examples)]

