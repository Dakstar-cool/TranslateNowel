from __future__ import annotations

import json
from pathlib import Path

import ebooklib
from ebooklib import epub

from epub_llm_translate.config import AppConfig, ensure_workdir
from epub_llm_translate.db.connection import initialize_database
from epub_llm_translate.db.repositories import Repository
from epub_llm_translate.utils import text_hash

from .chapter_map import ChapterMapEntry
from .html_blocks import extract_blocks


def _item_title(item: epub.EpubItem) -> str | None:
    name = getattr(item, "title", None)
    if name:
        return str(name)
    return Path(item.get_name()).stem


def inspect_epub(config: AppConfig) -> dict[str, object]:
    if not config.input_epub_path.exists():
        raise FileNotFoundError(f"Input EPUB not found: {config.input_epub_path}")
    ensure_workdir(config)
    book = epub.read_epub(str(config.input_epub_path))
    conn = initialize_database(config.db_path)
    repo = Repository(conn)
    chapter_map: list[ChapterMapEntry] = []
    book_index: dict[str, object] = {
        "input_epub": str(config.input_epub_path),
        "spine": [],
        "metadata": {},
    }
    for namespace, values_by_key in getattr(book, "metadata", {}).items():
        book_index["metadata"].setdefault(namespace, {})
        for key, values in values_by_key.items():
            book_index["metadata"][namespace][key] = [
                {"value": value, "attrs": attrs} for value, attrs in values
            ]

    chapter_id = 0
    for spine_index, spine_entry in enumerate(book.spine):
        idref = spine_entry[0] if isinstance(spine_entry, tuple) else spine_entry
        item = book.get_item_with_id(idref)
        book_index["spine"].append({"idref": idref, "href": item.get_name() if item else None})
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT or _is_navigation_item(idref, item):
            continue
        html = item.get_content().decode("utf-8", errors="replace")
        blocks = extract_blocks(html)
        if not blocks:
            continue
        chapter_id += 1
        title = _item_title(item)
        entry = ChapterMapEntry(chapter_id, title, item.get_name(), spine_index, len(blocks))
        chapter_map.append(entry)
        repo.upsert_chapter(chapter_id, title, item.get_name(), spine_index, len(blocks))
        for block in blocks:
            block_id = f"ch{chapter_id:04d}-b{block.block_index:05d}"
            repo.upsert_block(
                block_id=block_id,
                chapter_id=chapter_id,
                block_index=block.block_index,
                paragraph_index=block.paragraph_index,
                source_text=block.text,
                source_hash=text_hash(block.text),
            )
    repo.commit()
    (config.workdir / "00_book_index.json").write_text(
        json.dumps(book_index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (config.workdir / "00_chapter_map.json").write_text(
        json.dumps([entry.to_dict() for entry in chapter_map], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    repo.log_event("inspect", f"Imported {len(chapter_map)} chapters from EPUB")
    return {"chapters": len(chapter_map), "blocks": len(repo.list_blocks())}


def _is_navigation_item(idref: str, item: epub.EpubItem) -> bool:
    name = item.get_name().lower()
    return idref.lower() in {"nav", "toc"} or name.endswith("nav.xhtml") or name.endswith("nav.html")
