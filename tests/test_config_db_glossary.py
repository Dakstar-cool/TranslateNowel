from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from epub_llm_translate.backends import BackendUnavailableError, ChatMessage
from epub_llm_translate.config import load_config
from epub_llm_translate.db.connection import initialize_database
from epub_llm_translate.db.repositories import Repository
from epub_llm_translate.glossary.validator import GlossaryValidationError, validate_approved_glossary
import epub_llm_translate.pipeline.draft_translate as draft_translate_module
from epub_llm_translate.utils import parse_chapter_range, text_hash


def write_config(tmp_path: Path, input_epub: str = "book.ko.epub") -> Path:
    data = {
        "project": {
            "input_epub": input_epub,
            "workdir": "workdir",
            "output_draft_epub": "draft.epub",
            "output_final_epub": "final.epub",
        },
        "chapters": {
            "total": 2,
            "reference_translated": [1, 1],
            "machine_translate": [1, 2],
            "validation_reference": [1, 1],
        },
        "reference": {"translation_dir": "reference_ru"},
        "models": {
            "glossary": {"backend": "fake", "model": "fake", "disable_thinking": True},
            "draft_translate": {"backend": "fake", "model": "fake", "disable_thinking": True},
            "revise": {"backend": "fake", "model": "fake", "disable_thinking": True},
            "final_check": {"backend": "fake", "model": "fake", "disable_thinking": True},
        },
        "translation": {},
        "revision": {},
        "review": {},
        "review_flow": {},
        "quality": {},
        "gui": {},
        "pipeline": {},
        "final_build": {},
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def test_config_and_chapter_range(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    config = load_config(path)
    assert config.workdir == tmp_path / "workdir"
    assert config.models.draft_translate.disable_thinking is True
    assert config.pipeline.max_concurrent_requests == 1
    assert parse_chapter_range("1,3-4", (1, 2)) == [1, 3, 4]


def test_repository_edit_precedence_and_locks(tmp_path: Path) -> None:
    conn = initialize_database(tmp_path / "work.sqlite")
    repo = Repository(conn)
    repo.upsert_chapter(1, "One", "one.xhtml", 0, 1)
    repo.upsert_block("ch0001-b00000", 1, 0, 0, "안녕", text_hash("안녕"))
    repo.commit()
    assert repo.save_model_translation("ch0001-b00000", "draft_translation", "Draft", "fake", "draft_done")
    row = repo.get_block("ch0001-b00000")
    assert repo.final_text_for_row(row) == "Draft"
    repo.save_human_edit("ch0001-b00000", "human_final_edit", "Final", reason="test")
    row = repo.get_block("ch0001-b00000")
    assert repo.final_text_for_row(row) == "Final"
    repo.lock_block("ch0001-b00000")
    assert not repo.save_model_translation("ch0001-b00000", "revised_translation", "Revised", "fake", "revision_done")


def test_repository_pipeline_progress(tmp_path: Path) -> None:
    conn = initialize_database(tmp_path / "work.sqlite")
    repo = Repository(conn)
    job_id = repo.save_pipeline_progress(
        "draft_translate",
        "running",
        {"total": 10, "processed": 3, "status": "running"},
    )
    repo.save_pipeline_progress(
        "draft_translate",
        "done",
        {"total": 10, "processed": 10, "status": "done"},
    )
    job = repo.latest_pipeline_job("draft_translate")
    assert job is not None
    assert job["job_id"] == job_id
    assert job["status"] == "done"
    assert '"processed": 10' in job["payload_json"]


def test_glossary_validation(tmp_path: Path) -> None:
    path = tmp_path / "glossary.approved.yaml"
    path.write_text(
        yaml.safe_dump(
            {"terms": [{"source": "안녕", "translation": "Привет", "status": "approved"}]},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    assert validate_approved_glossary(path)[0]["translation"] == "Привет"
    path.write_text(
        yaml.safe_dump(
            {"terms": [{"source": "안녕", "translation": "안녕", "status": "approved"}]},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    with pytest.raises(GlossaryValidationError):
        validate_approved_glossary(path)


def test_glossary_validation_allows_korean_particle_variants(tmp_path: Path) -> None:
    path = tmp_path / "glossary.approved.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "terms": [
                    {"source": "\uc720\ub9ad", "translation": "\u0423\u043b\u044c\u0440\u0438\u0445", "status": "approved"},
                    {"source": "\uc720\ub9ad\uc740", "translation": "\u0423\u043b\u044c\u0440\u0438\u0445", "status": "approved"},
                    {"source": "\uc720\ub9ad\uc744", "translation": "\u0423\u043b\u044c\u0440\u0438\u0445", "status": "approved"},
                ]
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    assert len(validate_approved_glossary(path)) == 3


def test_draft_translate_aborts_without_marking_blocks_failed_when_backend_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class UnavailableBackend:
        def generate(self, messages: list[ChatMessage]) -> str:
            raise BackendUnavailableError("connection refused")

    config = load_config(write_config(tmp_path))
    conn = initialize_database(config.db_path)
    repo = Repository(conn)
    repo.upsert_chapter(1, "One", "one.xhtml", 0, 2)
    repo.upsert_block("ch0001-b00000", 1, 0, 0, "\uc548\ub155", text_hash("\uc548\ub155"))
    repo.upsert_block("ch0001-b00001", 1, 1, 1, "\uc138\uacc4", text_hash("\uc138\uacc4"))
    repo.commit()

    monkeypatch.setattr(draft_translate_module, "create_backend", lambda _config: UnavailableBackend())

    with pytest.raises(RuntimeError, match="LLM backend is unavailable"):
        draft_translate_module.draft_translate(config, repo, [1], [], concurrency=2)

    assert [row["status"] for row in repo.list_blocks([1])] == ["pending", "pending"]
    assert repo.list_issues() == []
    assert "aborted" in repo.recent_events(1)[0]["message"]
