from __future__ import annotations

import json
from pathlib import Path
import sys
import time
from typing import Annotated

import typer

from epub_llm_translate.config import ensure_workdir, load_config
from epub_llm_translate.db.connection import initialize_database
from epub_llm_translate.db.repositories import Repository
from epub_llm_translate.epub.reader import inspect_epub
from epub_llm_translate.glossary.extractor import extract_candidates
from epub_llm_translate.glossary.merger import load_candidate_file, merge_candidates
from epub_llm_translate.glossary.review_export import export_glossary_review
from epub_llm_translate.glossary.validator import GlossaryValidationError, validate_approved_glossary
from epub_llm_translate.pipeline.build_final import build_draft, build_final as build_final_impl
from epub_llm_translate.pipeline.check_draft import check_draft as check_draft_impl
from epub_llm_translate.pipeline.common import approved_glossary_path, require_approved_glossary
from epub_llm_translate.pipeline.draft_translate import draft_translate as draft_translate_impl
from epub_llm_translate.pipeline.final_check import final_check as final_check_impl
from epub_llm_translate.pipeline.repair_issue import repair_issue as repair_issue_impl
from epub_llm_translate.pipeline.revise import revise as revise_impl
from epub_llm_translate.pipeline.runner import run_pipeline as run_pipeline_impl
from epub_llm_translate.reference.analyze_reference import analyze_reference as analyze_reference_impl
from epub_llm_translate.reference.import_reference import import_reference_chapters
from epub_llm_translate.utils import parse_chapter_range


app = typer.Typer(help="Local Korean-to-Russian EPUB translation pipeline.", pretty_exceptions_enable=False)


ConfigOption = Annotated[Path, typer.Option("--config", exists=True, dir_okay=False, help="Path to config YAML.")]
DryRunOption = Annotated[bool, typer.Option("--dry-run", help="Print planned action without requiring local assets or model calls.")]


def _repo(config_path: Path) -> tuple:
    config = load_config(config_path)
    ensure_workdir(config)
    conn = initialize_database(config.db_path)
    return config, Repository(conn)


def _print(data: object) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    try:
        typer.echo(text)
    except UnicodeEncodeError:
        typer.echo(json.dumps(data, ensure_ascii=True, indent=2))


def _dry_run(command: str, config_path: Path, extra: dict | None = None) -> None:
    config = load_config(config_path)
    payload = {
        "command": command,
        "config": str(config.config_path),
        "workdir": str(config.workdir),
        "input_epub": str(config.input_epub_path),
    }
    payload.update(extra or {})
    _print({"dry_run": payload})


def _fail(message: str, code: int = 1) -> None:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(code=code)


class CliProgressReporter:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.started_at = time.monotonic()
        self.last_render_at = 0.0
        self.finished = False

    def __call__(self, payload: dict[str, object]) -> None:
        if not self.enabled:
            return
        now = time.monotonic()
        status = str(payload.get("status") or "running")
        if status not in {"done", "aborted"} and now - self.last_render_at < 1.0:
            return
        total = int(payload.get("total") or 0)
        processed = int(payload.get("processed") or 0)
        translated = int(payload.get("translated") or 0)
        failed = int(payload.get("failed") or 0)
        skipped = int(payload.get("skipped") or 0)
        pending = int(payload.get("pending") or 0)
        concurrency = int(payload.get("concurrency") or 1)
        percent = (processed / total) if total else 0.0
        width = 28
        filled = min(width, int(width * percent))
        bar = "#" * filled + "-" * (width - filled)
        elapsed = max(0.0, now - self.started_at)
        eta = "--:--"
        if processed > 0 and total > processed:
            rate = processed / elapsed if elapsed > 0 else 0.0
            if rate > 0:
                eta = _format_duration((total - processed) / rate)
        line = (
            f"\r[{bar}] {processed}/{total} {percent * 100:5.1f}% "
            f"ok:{translated} fail:{failed} skip:{skipped} pending:{pending} "
            f"c:{concurrency} eta:{eta}"
        )
        if status == "aborted":
            line += " aborted"
        elif status == "done":
            line += " done"
            self.finished = True
        sys.stderr.write(line)
        if status in {"done", "aborted"}:
            sys.stderr.write("\n")
        sys.stderr.flush()
        self.last_render_at = now


def _format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _approved_glossary_or_exit(cfg) -> list[dict[str, str]]:
    try:
        return require_approved_glossary(cfg)
    except RuntimeError as exc:
        _fail(
            f"{exc}\n"
            f"Create and fill {approved_glossary_path(cfg)} before running translation/check/revision commands. "
            "Start from workdir/glossary.draft.yaml or workdir/glossary_review.md."
        )


@app.command("inspect")
def inspect_cmd(config: ConfigOption, dry_run: DryRunOption = False) -> None:
    if dry_run:
        _dry_run("inspect", config, {"outputs": ["00_book_index.json", "00_chapter_map.json", "work.sqlite"]})
        return
    cfg, _repo_obj = _repo(config)
    _print(inspect_epub(cfg))


@app.command("import-reference")
def import_reference_cmd(config: ConfigOption, dry_run: DryRunOption = False) -> None:
    if dry_run:
        _dry_run("import-reference", config, {"reference_dir": str(load_config(config).reference_dir)})
        return
    cfg, repo = _repo(config)
    _print(import_reference_chapters(cfg, repo))


@app.command("analyze-reference")
def analyze_reference_cmd(
    config: ConfigOption,
    dry_run: DryRunOption = False,
    use_llm: Annotated[bool, typer.Option("--use-llm/--no-use-llm", help="Use the configured local glossary model to extract reference-derived glossary candidates.")] = True,
    max_reference_chapters: Annotated[int | None, typer.Option("--max-reference-chapters", help="Limit LLM glossary extraction to the first N imported reference chapters.")] = None,
) -> None:
    if dry_run:
        _dry_run(
            "analyze-reference",
            config,
            {
                "use_llm": use_llm,
                "max_reference_chapters": max_reference_chapters,
                "outputs": [
                    "reference_style_guide.yaml",
                    "reference_glossary_candidates.yaml",
                    "reference_examples.jsonl",
                ],
            },
        )
        return
    cfg, repo = _repo(config)
    try:
        _print(analyze_reference_impl(cfg, repo, use_llm=use_llm, max_reference_chapters=max_reference_chapters))
    except RuntimeError as exc:
        _fail(str(exc))


@app.command("build-glossary")
def build_glossary_cmd(config: ConfigOption, dry_run: DryRunOption = False) -> None:
    if dry_run:
        _dry_run("build-glossary", config, {"manual_approval_required": True})
        return
    cfg, repo = _repo(config)
    candidate_sets = [extract_candidates(repo)]
    reference_candidates = cfg.workdir / "reference" / "reference_glossary_candidates.yaml"
    if cfg.reference.use_for_glossary:
        candidate_sets.append(load_candidate_file(reference_candidates))
    candidates = merge_candidates(*candidate_sets)
    _print(export_glossary_review(cfg.workdir, candidates))


@app.command("validate-glossary")
def validate_glossary_cmd(config: ConfigOption) -> None:
    cfg, repo = _repo(config)
    try:
        terms = validate_approved_glossary(approved_glossary_path(cfg))
    except GlossaryValidationError as exc:
        _fail(str(exc))
    version = repo.save_glossary_terms(str(approved_glossary_path(cfg)), terms, "approved")
    _print({"valid": True, "terms": len(terms), "version": version})


@app.command("benchmark-reference")
def benchmark_reference_cmd(config: ConfigOption, dry_run: DryRunOption = False) -> None:
    if dry_run:
        _dry_run("benchmark-reference", config, {"validation_reference": load_config(config).chapters.validation_reference})
        return
    cfg, repo = _repo(config)
    rows = repo.list_reference_chapters()
    report_csv = cfg.workdir / "benchmark_report.csv"
    report_html = cfg.workdir / "benchmark_report.html"
    report_csv.write_text("chapter_id,status\n" + "\n".join(f"{row['chapter_id']},reference_available" for row in rows), encoding="utf-8")
    report_html.write_text("<html><body><h1>Benchmark Report</h1></body></html>", encoding="utf-8")
    _print({"chapters": len(rows), "csv": str(report_csv), "html": str(report_html)})


@app.command("draft-translate")
def draft_translate_cmd(
    config: ConfigOption,
    chapters: Annotated[str | None, typer.Option("--chapters", help="Chapter range, e.g. 1-315 or 1,3,5-7.")] = None,
    concurrency: Annotated[int | None, typer.Option("--concurrency", min=1, max=16, help="Override concurrent model requests for this run.")] = None,
    overwrite_model_drafts: Annotated[bool, typer.Option("--overwrite-model-drafts", help="Retranslate existing machine draft blocks while preserving human edits.")] = False,
    progress: Annotated[bool, typer.Option("--progress/--no-progress", help="Show a CLI progress bar with ETA on stderr.")] = True,
    dry_run: DryRunOption = False,
) -> None:
    cfg = load_config(config)
    chapter_ids = parse_chapter_range(chapters, cfg.chapters.machine_translate)
    if dry_run:
        _dry_run(
            "draft-translate",
            config,
            {
                "chapters": chapter_ids[:5] + (["..."] if len(chapter_ids) > 5 else []),
                "concurrency": concurrency or cfg.pipeline.max_concurrent_requests,
                "overwrite_model_drafts": overwrite_model_drafts,
                "progress": progress,
            },
        )
        return
    cfg, repo = _repo(config)
    glossary = _approved_glossary_or_exit(cfg)
    try:
        _print(
            draft_translate_impl(
                cfg,
                repo,
                chapter_ids,
                glossary,
                overwrite_model_drafts=overwrite_model_drafts,
                concurrency=concurrency,
                progress_callback=CliProgressReporter(progress),
            )
        )
    except RuntimeError as exc:
        _fail(str(exc))


@app.command("check-draft")
def check_draft_cmd(config: ConfigOption, dry_run: DryRunOption = False) -> None:
    if dry_run:
        _dry_run("check-draft", config, {"outputs": ["draft_quality_report.csv", "draft_quality_report.html"]})
        return
    cfg, repo = _repo(config)
    glossary = _approved_glossary_or_exit(cfg)
    _print(check_draft_impl(cfg, repo, glossary))


@app.command("revise")
def revise_cmd(
    config: ConfigOption,
    profile: Annotated[str, typer.Option("--profile")] = "accurate",
    use_reference: Annotated[bool, typer.Option("--use-reference/--no-use-reference")] = True,
    chapters: Annotated[str | None, typer.Option("--chapters")] = None,
    dry_run: DryRunOption = False,
) -> None:
    cfg = load_config(config)
    chapter_ids = parse_chapter_range(chapters, cfg.chapters.machine_translate)
    if dry_run:
        _dry_run("revise", config, {"profile": profile, "use_reference": use_reference, "chapters_count": len(chapter_ids)})
        return
    cfg, repo = _repo(config)
    glossary = _approved_glossary_or_exit(cfg)
    _print(revise_impl(cfg, repo, chapter_ids, glossary, profile, use_reference))


@app.command("final-check")
def final_check_cmd(config: ConfigOption, dry_run: DryRunOption = False) -> None:
    if dry_run:
        _dry_run("final-check", config, {"outputs": ["final_quality_report.csv", "final_quality_report.html"]})
        return
    cfg, repo = _repo(config)
    glossary = _approved_glossary_or_exit(cfg)
    _print(final_check_impl(cfg, repo, glossary))


@app.command("build-final")
def build_final_cmd(
    config: ConfigOption,
    mode: Annotated[str, typer.Option("--mode")] = "uniform-machine",
    override_high_issues: Annotated[bool, typer.Option("--override-high-issues")] = False,
    dry_run: DryRunOption = False,
) -> None:
    if dry_run:
        _dry_run("build-final", config, {"mode": mode})
        return
    cfg, repo = _repo(config)
    _print(build_final_impl(cfg, repo, mode, override_high_issues=override_high_issues))


@app.command("build-draft")
def build_draft_cmd(config: ConfigOption, dry_run: DryRunOption = False) -> None:
    if dry_run:
        _dry_run("build-draft", config)
        return
    cfg, repo = _repo(config)
    try:
        _print(build_draft(cfg, repo))
    except RuntimeError as exc:
        _fail(str(exc))


@app.command("gui")
def gui_cmd(config: ConfigOption, dry_run: DryRunOption = False) -> None:
    if dry_run:
        _dry_run("gui", config, {"backend": "pyside6"})
        return
    from epub_llm_translate.gui.main_window import run_gui

    run_gui(config)


@app.command("repair-issue")
def repair_issue_cmd(
    config: ConfigOption,
    issue_id: Annotated[int, typer.Option("--issue-id")],
    dry_run: DryRunOption = False,
) -> None:
    if dry_run:
        _dry_run("repair-issue", config, {"issue_id": issue_id})
        return
    cfg, repo = _repo(config)
    glossary = _approved_glossary_or_exit(cfg)
    try:
        _print(repair_issue_impl(cfg, repo, issue_id, glossary))
    except RuntimeError as exc:
        _fail(str(exc))


@app.command("run-pipeline")
def run_pipeline_cmd(config: ConfigOption, dry_run: DryRunOption = False) -> None:
    if dry_run:
        _dry_run("run-pipeline", config, {"sequence": ["inspect", "draft-translate", "check-draft", "revise", "final-check"]})
        return
    cfg, repo = _repo(config)
    try:
        _print(run_pipeline_impl(cfg, repo))
    except RuntimeError as exc:
        _fail(str(exc))


if __name__ == "__main__":
    app()
