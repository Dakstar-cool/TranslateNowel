from __future__ import annotations

from epub_llm_translate.config import AppConfig
from epub_llm_translate.db.repositories import Repository
from epub_llm_translate.utils import parse_chapter_range

from .check_draft import check_draft
from .common import require_approved_glossary
from .draft_translate import draft_translate
from .final_check import final_check
from .inspect import run_inspect
from .revise import revise


def run_pipeline(config: AppConfig, repo: Repository) -> dict[str, object]:
    results: dict[str, object] = {}
    results["inspect"] = run_inspect(config)
    glossary = require_approved_glossary(config)
    chapters = parse_chapter_range(None, config.chapters.machine_translate)
    results["draft"] = draft_translate(config, repo, chapters, glossary)
    results["check_draft"] = check_draft(config, repo, glossary)
    results["revise"] = revise(config, repo, chapters, glossary, config.revision.profile, config.reference.use_for_revision)
    results["final_check"] = final_check(config, repo, glossary)
    return results

