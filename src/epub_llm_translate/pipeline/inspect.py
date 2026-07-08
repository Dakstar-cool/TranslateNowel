from __future__ import annotations

from epub_llm_translate.config import AppConfig
from epub_llm_translate.epub.reader import inspect_epub


def run_inspect(config: AppConfig) -> dict[str, object]:
    return inspect_epub(config)

