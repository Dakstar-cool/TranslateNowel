from __future__ import annotations

import shutil
from pathlib import Path

import ebooklib
from ebooklib import epub
import yaml

from epub_llm_translate.config import AppConfig, ensure_workdir
from epub_llm_translate.db.repositories import Repository
from epub_llm_translate.epub.html_blocks import extract_blocks
from epub_llm_translate.utils import text_hash


def import_reference_chapters(config: AppConfig, repo: Repository) -> dict[str, int]:
    ensure_workdir(config)
    if not config.reference_dir.exists():
        raise FileNotFoundError(f"Reference directory not found: {config.reference_dir}")
    mapping = _load_mapping(config)
    files = sorted(
        path
        for path in config.reference_dir.iterdir()
        if path.is_file()
        and path.suffix.lower() in {".txt", ".md", ".html", ".xhtml", ".epub"}
        and not _is_generated_reference_file(path)
    )
    if not files and not mapping:
        raise FileNotFoundError(f"No reference files found in {config.reference_dir}")
    imported = 0
    if mapping:
        for chapter_id, rel_path in mapping.items():
            path = config.reference_dir / rel_path
            imported += _import_one(config, repo, chapter_id, path)
    else:
        start, _end = config.chapters.reference_translated
        next_chapter_id = start
        for path in files:
            count = _import_one(config, repo, next_chapter_id, path)
            imported += count
            next_chapter_id += count
    repo.log_event("import_reference", f"Imported {imported} reference chapters")
    return {"imported": imported}


def _load_mapping(config: AppConfig) -> dict[int, str]:
    path = config.resolve_path("reference_map.yaml")
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if "chapters" in data:
        data = data["chapters"]
    return {int(key): str(value) for key, value in data.items()}


def _import_one(config: AppConfig, repo: Repository, chapter_id: int, path: Path) -> int:
    if not path.exists():
        raise FileNotFoundError(f"Reference chapter file not found: {path}")
    if path.suffix.lower() == ".epub":
        return _import_epub(config, repo, chapter_id, path)
    text = path.read_text(encoding="utf-8")
    target = config.workdir / "reference" / f"chapter_{chapter_id:04d}{path.suffix.lower() or '.txt'}"
    if path.resolve() != target.resolve():
        shutil.copyfile(path, target)
    repo.upsert_reference_chapter(chapter_id, str(target), text, text_hash(text))
    return 1


def _import_epub(config: AppConfig, repo: Repository, start_chapter_id: int, path: Path) -> int:
    book = epub.read_epub(str(path))
    imported = 0
    archive_copy = config.workdir / "reference" / path.name
    if path.resolve() != archive_copy.resolve():
        shutil.copyfile(path, archive_copy)
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        if _is_navigation_item(item):
            continue
        html = item.get_content().decode("utf-8", errors="replace")
        blocks = extract_blocks(html)
        if not blocks:
            continue
        chapter_id = start_chapter_id + imported
        text = "\n\n".join(block.text for block in blocks)
        target = config.workdir / "reference" / f"chapter_{chapter_id:04d}.txt"
        target.write_text(text, encoding="utf-8")
        repo.upsert_reference_chapter(chapter_id, str(target), text, text_hash(text))
        imported += 1
    return imported


def _is_navigation_item(item: epub.EpubItem) -> bool:
    name = item.get_name().lower()
    item_id = (item.get_id() or "").lower()
    return item_id in {"nav", "toc"} or name.endswith("nav.xhtml") or name.endswith("nav.html")


def _is_generated_reference_file(path: Path) -> bool:
    return path.name.startswith("chapter_") and path.suffix.lower() in {".txt", ".md", ".html", ".xhtml"}
