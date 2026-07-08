from __future__ import annotations

import ebooklib
from ebooklib import epub

from epub_llm_translate.config import AppConfig, normalize_build_mode
from epub_llm_translate.db.repositories import Repository

from .html_blocks import replace_blocks


def build_epub(config: AppConfig, repo: Repository, mode: str = "uniform-machine", draft: bool = False) -> dict[str, object]:
    build_mode = normalize_build_mode(mode)
    if not config.input_epub_path.exists():
        raise FileNotFoundError(f"Input EPUB not found: {config.input_epub_path}")
    book = epub.read_epub(str(config.input_epub_path))
    chapters = repo.chapters_summary()
    href_by_chapter = {row["chapter_id"]: row["href"] for row in chapters}
    blocks_by_chapter: dict[int, list] = {}
    for row in repo.list_blocks():
        blocks_by_chapter.setdefault(row["chapter_id"], []).append(row)
    references = {row["chapter_id"]: row["text"] for row in repo.list_reference_chapters()}
    for chapter_id, href in href_by_chapter.items():
        item = book.get_item_with_href(href)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        if build_mode == "hybrid_reference_plus_machine" and chapter_id in references:
            replacement = _reference_as_html(references[chapter_id])
            item.set_content(replacement.encode("utf-8"))
            continue
        replacements: dict[int, str] = {}
        for row in blocks_by_chapter.get(chapter_id, []):
            text = row["draft_translation"] if draft else repo.final_text_for_row(row)
            if text:
                replacements[int(row["block_index"])] = text
        html = item.get_content().decode("utf-8", errors="replace")
        item.set_content(replace_blocks(html, replacements).encode("utf-8"))
    _ensure_document_uids(book)
    _ensure_toc_uids(book)
    output = config.output_draft_epub_path if draft else config.output_final_epub_path
    epub.write_epub(str(output), book)
    repo.log_event("build_final", f"Built EPUB: {output}", {"mode": build_mode, "draft": draft})
    return {"output": str(output), "mode": build_mode}


def _reference_as_html(text: str) -> str:
    paragraphs = [line.strip() for line in text.splitlines() if line.strip()]
    body = "\n".join(f"<p>{_escape(paragraph)}</p>" for paragraph in paragraphs)
    return f"<?xml version='1.0' encoding='utf-8'?><html><body>{body}</body></html>"


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _ensure_document_uids(book: epub.EpubBook) -> None:
    for index, item in enumerate(book.get_items_of_type(ebooklib.ITEM_DOCUMENT), start=1):
        if getattr(item, "uid", None):
            continue
        fallback = item.get_id() or f"doc_{index}"
        setattr(item, "uid", fallback)


def _ensure_toc_uids(book: epub.EpubBook) -> None:
    def fix(entry, index_path: str):
        if isinstance(entry, tuple):
            section, children = entry
            fix(section, index_path)
            for child_index, child in enumerate(children, start=1):
                fix(child, f"{index_path}_{child_index}")
            return
        if getattr(entry, "uid", None):
            return
        href = getattr(entry, "href", None)
        title = getattr(entry, "title", None)
        fallback = href or title or f"toc_{index_path}"
        safe = "".join(ch if ch.isalnum() else "_" for ch in str(fallback)).strip("_") or f"toc_{index_path}"
        setattr(entry, "uid", safe[:80])

    for index, item in enumerate(book.toc or [], start=1):
        fix(item, str(index))
