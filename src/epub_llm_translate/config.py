from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator


ChapterRange = tuple[int, int]


class ProjectConfig(BaseModel):
    input_epub: str = "book.ko.epub"
    workdir: str = "workdir"
    output_draft_epub: str = "book.draft.ru.epub"
    output_final_epub: str = "book.final.ru.epub"


class ChaptersConfig(BaseModel):
    total: int = 315
    reference_translated: ChapterRange = (1, 60)
    machine_translate: ChapterRange = (1, 315)
    validation_reference: ChapterRange = (51, 60)


class ReferenceConfig(BaseModel):
    enabled: bool = True
    mode: str = "aligned_chapters"
    translation_dir: str = "reference_ru"
    use_as_final_for_reference_chapters: bool = False
    use_for_glossary: bool = True
    use_for_style_guide: bool = True
    use_for_benchmark: bool = True
    use_for_draft: bool = False
    use_for_revision: bool = True
    max_examples_per_block: int = 4
    example_max_chars: int = 1200


class ModelEndpointConfig(BaseModel):
    backend: Literal["ollama", "openai_compatible", "fake"] = "ollama"
    model: str
    endpoint: str | None = None
    num_ctx: int = 8192
    temperature: float = 0.0
    top_p: float = 0.9
    max_output_tokens: int = 4096
    disable_thinking: bool = False
    extra_body: dict[str, Any] = Field(default_factory=dict)


class ModelsConfig(BaseModel):
    glossary: ModelEndpointConfig
    draft_translate: ModelEndpointConfig
    revise: ModelEndpointConfig
    final_check: ModelEndpointConfig


class TranslationConfig(BaseModel):
    chunk_max_chars: int = 3500
    previous_translated_paragraphs: int = 4
    next_source_paragraphs: int = 2
    preserve_html: bool = True
    keep_paragraph_count: bool = True


class RevisionConfig(BaseModel):
    profile: str = "accurate"
    chunk_max_chars: int = 3000
    previous_revised_paragraphs: int = 3
    next_draft_paragraphs: int = 1
    use_korean_source: bool = True
    use_russian_draft: bool = True
    use_reference_examples: bool = True
    strict_glossary: bool = True
    max_retries: int = 2


class ReviewConfig(BaseModel):
    context_before_paragraphs: int = 1
    context_after_paragraphs: int = 1
    editable_scope: str = "target_paragraph"
    show_source_context: bool = True
    show_draft_context: bool = True
    show_revised_context: bool = True
    highlight_issue_terms: bool = True
    allow_context_edit_override: bool = True


class ReviewFlowConfig(BaseModel):
    mode: Literal["auto", "assisted", "strict"] = "assisted"
    max_unreviewed_high_issues: int = 200
    action_when_limit_reached: str = "pause_revision_only"


class QualityConfig(BaseModel):
    create_review_windows: bool = True
    issue_context_mode: str = "paragraph"
    store_issue_offsets: bool = True
    fail_on_remaining_hangul: bool = True
    fail_on_empty_blocks: bool = True
    fail_on_forbidden_phrases: bool = True
    warn_length_ratio_min: float = 0.45
    warn_length_ratio_max: float = 1.85


class GuiConfig(BaseModel):
    enabled: bool = True
    backend: str = "pyside6"
    refresh_seconds: int = 5
    default_queue: str = "needs_review"
    allow_glossary_edit: bool = True
    allow_retry_actions: bool = True
    allow_context_edit_override: bool = True


class PipelineConfig(BaseModel):
    skip_locked_blocks: bool = True
    never_overwrite_human_edits: bool = True
    stale_lock_minutes: int = 60
    max_concurrent_requests: int = Field(default=1, ge=1, le=16)


class FinalBuildConfig(BaseModel):
    default_mode: str = "uniform_machine"
    supported_modes: list[str] = Field(default_factory=lambda: ["uniform_machine", "hybrid_reference_plus_machine"])


class AppConfig(BaseModel):
    config_path: Path | None = None
    base_dir: Path = Field(default_factory=lambda: Path.cwd())
    project: ProjectConfig
    chapters: ChaptersConfig
    reference: ReferenceConfig
    models: ModelsConfig
    translation: TranslationConfig
    revision: RevisionConfig
    review: ReviewConfig
    review_flow: ReviewFlowConfig
    quality: QualityConfig
    gui: GuiConfig
    pipeline: PipelineConfig
    final_build: FinalBuildConfig

    @field_validator("base_dir", mode="before")
    @classmethod
    def _base_dir(cls, value: Any) -> Path:
        return Path(value)

    @property
    def workdir(self) -> Path:
        return self.resolve_path(self.project.workdir)

    @property
    def db_path(self) -> Path:
        return self.workdir / "work.sqlite"

    @property
    def input_epub_path(self) -> Path:
        return self.resolve_path(self.project.input_epub)

    @property
    def output_draft_epub_path(self) -> Path:
        return self.resolve_path(self.project.output_draft_epub)

    @property
    def output_final_epub_path(self) -> Path:
        return self.resolve_path(self.project.output_final_epub)

    @property
    def reference_dir(self) -> Path:
        return self.resolve_path(self.reference.translation_dir)

    def resolve_path(self, value: str | Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return self.base_dir / path


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path).resolve()
    with config_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    cfg = AppConfig.model_validate(
        {
            **raw,
            "config_path": config_path,
            "base_dir": config_path.parent,
        }
    )
    return cfg


def ensure_workdir(config: AppConfig) -> None:
    config.workdir.mkdir(parents=True, exist_ok=True)
    (config.workdir / "reference").mkdir(parents=True, exist_ok=True)


def normalize_build_mode(mode: str) -> str:
    normalized = mode.strip().lower().replace("-", "_")
    aliases = {
        "uniform_machine": "uniform_machine",
        "hybrid": "hybrid_reference_plus_machine",
        "hybrid_reference_plus_machine": "hybrid_reference_plus_machine",
    }
    if normalized not in aliases:
        raise ValueError(f"Unsupported build mode: {mode}")
    return aliases[normalized]
