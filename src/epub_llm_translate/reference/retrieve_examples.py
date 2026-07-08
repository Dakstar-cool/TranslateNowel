from __future__ import annotations

from epub_llm_translate.db.repositories import Repository
from epub_llm_translate.utils import truncate


def retrieve_reference_examples(repo: Repository, max_examples: int = 4, chapter_id: int | None = None) -> list[str]:
    if chapter_id is None:
        return [row["reference_excerpt"] for row in repo.list_reference_examples(limit=max_examples)]
    rows = repo.conn.execute(
        """
        SELECT * FROM reference_examples
        WHERE chapter_id = ?
        ORDER BY example_id
        LIMIT ?
        """,
        (chapter_id, max_examples),
    ).fetchall()
    examples = [row["reference_excerpt"] for row in rows]
    if len(examples) >= max_examples:
        return examples
    seen = set(examples)
    for row in repo.list_reference_examples(limit=max_examples * 2):
        excerpt = row["reference_excerpt"]
        if excerpt in seen:
            continue
        examples.append(excerpt)
        seen.add(excerpt)
        if len(examples) >= max_examples:
            break
    return examples


def retrieve_reference_context(
    repo: Repository,
    chapter_id: int,
    paragraph_index: int | None,
    before: int = 1,
    after: int = 1,
    max_chars: int = 1600,
) -> str:
    reference = repo.get_reference_chapter(chapter_id)
    if reference is None:
        return ""
    paragraphs = [line.strip() for line in reference["text"].splitlines() if line.strip()]
    if not paragraphs:
        return ""
    index = max(0, min(paragraph_index or 0, len(paragraphs) - 1))
    start = max(0, index - before)
    end = min(len(paragraphs), index + after + 1)
    lines = [f"[ref {offset}] {paragraphs[offset]}" for offset in range(start, end)]
    return truncate("\n".join(lines), max_chars)


def retrieve_reference_context_range(
    repo: Repository,
    chapter_id: int,
    start_paragraph_index: int | None,
    end_paragraph_index: int | None,
    before: int = 1,
    after: int = 1,
    max_chars: int = 3000,
) -> str:
    reference = repo.get_reference_chapter(chapter_id)
    if reference is None:
        return ""
    paragraphs = [line.strip() for line in reference["text"].splitlines() if line.strip()]
    if not paragraphs:
        return ""
    start_index = max(0, min(start_paragraph_index or 0, len(paragraphs) - 1))
    end_index = max(start_index, min(end_paragraph_index if end_paragraph_index is not None else start_index, len(paragraphs) - 1))
    start = max(0, start_index - before)
    end = min(len(paragraphs), end_index + after + 1)
    lines = [f"[ref {offset}] {paragraphs[offset]}" for offset in range(start, end)]
    return truncate("\n".join(lines), max_chars)
