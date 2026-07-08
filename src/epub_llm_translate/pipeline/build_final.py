from __future__ import annotations

from epub_llm_translate.config import AppConfig, normalize_build_mode
from epub_llm_translate.db.repositories import Repository
from epub_llm_translate.epub.writer import build_epub


def build_final(config: AppConfig, repo: Repository, mode: str, override_high_issues: bool = False) -> dict[str, object]:
    build_mode = normalize_build_mode(mode)
    high_count = repo.unresolved_high_issue_count()
    if high_count and not override_high_issues:
        raise RuntimeError(f"Cannot build final EPUB with {high_count} unresolved high-severity issues.")
    return build_epub(config, repo, build_mode, draft=False)


def build_draft(config: AppConfig, repo: Repository) -> dict[str, object]:
    translated = repo.draft_translation_count()
    total = repo.total_block_count()
    if translated == 0:
        raise RuntimeError(
            "No draft translations found in SQLite. Run `draft-translate` before `build-draft`."
        )
    result = build_epub(config, repo, "uniform_machine", draft=True)
    result["translated_blocks"] = translated
    result["total_blocks"] = total
    if translated < total:
        result["warning"] = "Draft EPUB is partial; untranslated blocks remain in the original language."
    return result
