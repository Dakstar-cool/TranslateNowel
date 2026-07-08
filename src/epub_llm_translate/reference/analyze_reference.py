from __future__ import annotations

import json

import yaml

from epub_llm_translate.config import AppConfig
from epub_llm_translate.db.repositories import Repository
from epub_llm_translate.utils import truncate

from .glossary_from_reference import extract_reference_glossary


def analyze_reference(
    config: AppConfig,
    repo: Repository,
    use_llm: bool = True,
    max_reference_chapters: int | None = None,
) -> dict[str, str | int | list[str]]:
    rows = repo.list_reference_chapters()
    if not rows:
        raise RuntimeError("No reference chapters imported. Run import-reference first.")
    reference_dir = config.workdir / "reference"
    reference_dir.mkdir(parents=True, exist_ok=True)
    style_path = reference_dir / "reference_style_guide.yaml"
    candidates_path = reference_dir / "reference_glossary_candidates.yaml"
    examples_path = reference_dir / "reference_examples.jsonl"
    alignment_path = reference_dir / "reference_alignment.sqlite"
    style = {
        "language": "ru",
        "source": "reference_chapters",
        "guidance": [
            "Prefer fluent literary Russian.",
            "Preserve dialogue paragraphing and speaker intent.",
            "Avoid summaries and meta commentary.",
        ],
    }
    style_path.write_text(yaml.safe_dump(style, allow_unicode=True, sort_keys=False), encoding="utf-8")
    candidates, llm_errors = extract_reference_glossary(
        config,
        repo,
        rows,
        use_llm=use_llm and config.reference.use_for_glossary,
        max_chapters=max_reference_chapters,
    )
    example_count = 0
    with examples_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            paragraphs = [line.strip() for line in row["text"].splitlines() if line.strip()]
            if paragraphs:
                excerpt = truncate("\n".join(paragraphs[:3]), config.reference.example_max_chars)
                repo.insert_reference_example(row["chapter_id"], excerpt, tags="style")
                fh.write(json.dumps({"chapter_id": row["chapter_id"], "reference_excerpt": excerpt, "tags": ["style"]}, ensure_ascii=False) + "\n")
                example_count += 1
    candidates_path.write_text(yaml.safe_dump({"terms": candidates}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    alignment_path.write_text("placeholder alignment index; SQLite alignment can be expanded later\n", encoding="utf-8")
    repo.log_event(
        "analyze_reference",
        f"Analyzed {len(rows)} reference chapters and extracted {len(candidates)} reference glossary candidates",
        {"llm_errors": llm_errors[:20]},
    )
    return {
        "chapters": len(rows),
        "glossary_chapters_analyzed": min(len(rows), max_reference_chapters) if max_reference_chapters else len(rows),
        "examples": example_count,
        "glossary_candidates_count": len(candidates),
        "glossary_llm_errors": llm_errors[:20],
        "style_guide": str(style_path),
        "glossary_candidates": str(candidates_path),
        "examples_path": str(examples_path),
    }
