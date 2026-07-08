from __future__ import annotations

from pathlib import Path

import yaml
from ebooklib import epub

from epub_llm_translate.config import load_config
from epub_llm_translate.db.connection import initialize_database
from epub_llm_translate.db.repositories import Repository
from epub_llm_translate.epub.reader import inspect_epub
from epub_llm_translate.pipeline.build_final import build_final
from epub_llm_translate.pipeline.check_draft import check_draft
from epub_llm_translate.pipeline.draft_translate import draft_translate
from epub_llm_translate.reference.glossary_from_reference import parse_reference_glossary_terms
from epub_llm_translate.reference.import_reference import import_reference_chapters
from epub_llm_translate.utils import text_hash

from .test_config_db_glossary import write_config


def create_epub(path: Path) -> None:
    book = epub.EpubBook()
    book.set_identifier("synthetic")
    book.set_title("Synthetic")
    book.set_language("ko")
    chapters = []
    for index, text in enumerate(["안녕 세계", "검은 탑"], start=1):
        chapter = epub.EpubHtml(title=f"Chapter {index}", file_name=f"chap_{index}.xhtml", lang="ko")
        chapter.content = f"<html><body><h1>Chapter {index}</h1><p>{text}</p></body></html>"
        book.add_item(chapter)
        chapters.append(chapter)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *chapters]
    book.toc = chapters
    epub.write_epub(str(path), book)


def test_inspect_draft_check_and_build_final(tmp_path: Path) -> None:
    epub_path = tmp_path / "book.ko.epub"
    create_epub(epub_path)
    config_path = write_config(tmp_path, input_epub="book.ko.epub")
    config = load_config(config_path)
    result = inspect_epub(config)
    assert result["chapters"] == 2
    repo = Repository(initialize_database(config.db_path))
    glossary_path = config.workdir / "glossary.approved.yaml"
    glossary_path.write_text(
        yaml.safe_dump(
            {"terms": [{"source": "안녕", "translation": "Привет", "status": "approved"}]},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    glossary = [{"source": "안녕", "translation": "Привет", "status": "approved"}]
    draft_result = draft_translate(config, repo, [1, 2], glossary, concurrency=2)
    assert draft_result["translated"] >= 1
    assert draft_result["concurrency"] == 2
    qa_result = check_draft(config, repo, glossary)
    assert Path(qa_result["csv"]).exists()
    for row in repo.list_blocks():
        repo.save_model_translation(row["block_id"], "revised_translation", f"Перевод {row['block_index']}", "fake", "revision_done")
    repo.clear_issues()
    built = build_final(config, repo, "uniform-machine", override_high_issues=True)
    assert Path(built["output"]).exists()


def test_import_reference_epub(tmp_path: Path) -> None:
    reference_dir = tmp_path / "workdir" / "reference"
    reference_dir.mkdir(parents=True)
    create_epub(reference_dir / "reference.epub")
    config_path = write_config(tmp_path, input_epub="book.ko.epub")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data["reference"]["translation_dir"] = "workdir/reference"
    config_path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    config = load_config(config_path)
    repo = Repository(initialize_database(config.db_path))
    result = import_reference_chapters(config, repo)
    assert result["imported"] == 2
    rows = repo.list_reference_chapters()
    assert len(rows) == 2
    assert Path(rows[0]["path"]).suffix == ".txt"


def test_parse_reference_glossary_terms() -> None:
    output = """
```yaml
terms:
  - source: "\uc548\ub155"
    translation: "\u041f\u0440\u0438\u0432\u0435\u0442"
    category: "other"
    confidence: 0.8
```
"""
    terms = parse_reference_glossary_terms(output)
    assert terms[0]["source"] == "\uc548\ub155"
    assert terms[0]["translation"] == "\u041f\u0440\u0438\u0432\u0435\u0442"
