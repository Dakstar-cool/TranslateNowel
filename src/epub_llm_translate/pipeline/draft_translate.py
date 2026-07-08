from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait

from epub_llm_translate.backends import BackendUnavailableError, ChatMessage, create_backend
from epub_llm_translate.config import AppConfig
from epub_llm_translate.db.repositories import Repository
from epub_llm_translate.memory.book_memory import build_book_memory
from epub_llm_translate.memory.chapter_summary import chapter_summary

META_OUTPUT_MARKERS = (
    "Analyze the Source",
    "Draft Translation",
    "Final Text:",
    "Translation Strategy",
    "Korean Source:",
    "Source Text:",
    "I should",
    "Let's ",
    "**Analyze",
)


ProgressCallback = Callable[[dict[str, object]], None]


def draft_translate(
    config: AppConfig,
    repo: Repository,
    chapter_ids: list[int],
    glossary: list[dict[str, str]],
    overwrite_model_drafts: bool = False,
    concurrency: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, int]:
    max_workers = max(1, concurrency or config.pipeline.max_concurrent_requests)
    translated = 0
    failed = 0
    skipped = 0
    submitted = 0
    block_rows = repo.list_blocks(chapter_ids)
    total = len(block_rows)
    progress_step = max(1, total // 1000)
    last_progress_processed = -1

    def publish_progress(status: str, force: bool = False) -> None:
        nonlocal last_progress_processed
        processed = translated + failed + skipped
        if (
            not force
            and status == "running"
            and processed < total
            and processed - last_progress_processed < progress_step
        ):
            return
        payload = _progress_payload(total, translated, failed, skipped, submitted, max_workers, status)
        repo.save_pipeline_progress("draft_translate", status, payload)
        if progress_callback is not None:
            progress_callback(payload)
        last_progress_processed = processed

    publish_progress("starting", force=True)

    if max_workers == 1:
        backend = create_backend(config.models.draft_translate)
        for row in block_rows:
            if _should_skip_row(row, overwrite_model_drafts):
                skipped += 1
                publish_progress("running")
                continue
            relevant_terms = _relevant_terms(row["source_text"], glossary)
            prompt = _draft_prompt(config, repo, row, relevant_terms)
            submitted += 1
            try:
                result = _generate_with_backend(backend, prompt)
                if repo.save_model_translation(row["block_id"], "draft_translation", result, config.models.draft_translate.model, "draft_done"):
                    translated += 1
                else:
                    skipped += 1
            except BackendUnavailableError as exc:
                publish_progress("aborted", force=True)
                _abort_backend_unavailable(repo, exc, translated, failed, skipped, max_workers, submitted)
            except Exception as exc:
                _record_model_error(repo, row, exc)
                failed += 1
            publish_progress("running")
        repo.log_event(
            "draft_translate",
            f"Draft translation finished: {translated} translated, {failed} failed, {skipped} skipped",
            {"concurrency": max_workers},
        )
        publish_progress("done", force=True)
        return {"translated": translated, "failed": failed, "skipped": skipped, "concurrency": max_workers}

    rows = iter(block_rows)
    pending: dict[Future[str], object] = {}
    exhausted = False
    fatal_error: BackendUnavailableError | None = None

    executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="draft-translate")
    try:
        while (pending or not exhausted) and fatal_error is None:
            while len(pending) < max_workers and not exhausted:
                next_row = None
                for row in rows:
                    if _should_skip_row(row, overwrite_model_drafts):
                        skipped += 1
                        publish_progress("running")
                        continue
                    next_row = row
                    break
                if next_row is None:
                    exhausted = True
                    break

                relevant_terms = _relevant_terms(next_row["source_text"], glossary)
                prompt = _draft_prompt(config, repo, next_row, relevant_terms)
                future = executor.submit(_generate_draft, config.models.draft_translate, prompt)
                pending[future] = next_row
                submitted += 1

            if not pending:
                continue

            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                row = pending.pop(future)
                try:
                    result = future.result()
                    if repo.save_model_translation(row["block_id"], "draft_translation", result, config.models.draft_translate.model, "draft_done"):
                        translated += 1
                    else:
                        skipped += 1
                except BackendUnavailableError as exc:
                    fatal_error = exc
                    for pending_future in pending:
                        pending_future.cancel()
                    break
                except Exception as exc:
                    _record_model_error(repo, row, exc)
                    failed += 1
                publish_progress("running")
    finally:
        executor.shutdown(wait=fatal_error is None, cancel_futures=fatal_error is not None)

    if fatal_error is not None:
        publish_progress("aborted", force=True)
        _abort_backend_unavailable(repo, fatal_error, translated, failed, skipped, max_workers, submitted)

    repo.log_event(
        "draft_translate",
        f"Draft translation finished: {translated} translated, {failed} failed, {skipped} skipped",
        {"concurrency": max_workers, "submitted": submitted},
    )
    publish_progress("done", force=True)
    return {"translated": translated, "failed": failed, "skipped": skipped, "concurrency": max_workers}


def _progress_payload(
    total: int,
    translated: int,
    failed: int,
    skipped: int,
    submitted: int,
    concurrency: int,
    status: str,
) -> dict[str, object]:
    processed = translated + failed + skipped
    return {
        "status": status,
        "total": total,
        "processed": processed,
        "translated": translated,
        "failed": failed,
        "skipped": skipped,
        "submitted": submitted,
        "pending": max(0, submitted - translated - failed - skipped),
        "concurrency": concurrency,
    }


def _should_skip_row(row, overwrite_model_drafts: bool) -> bool:
    if row["locked_by"]:
        return True
    if row["human_draft_edit"]:
        return True
    if row["draft_translation"] and not overwrite_model_drafts:
        return True
    return False


def _generate_draft(model_config, prompt: str) -> str:
    return _generate_with_backend(create_backend(model_config), prompt)


def _generate_with_backend(backend, prompt: str) -> str:
    result = _postprocess_draft_output(backend.generate([ChatMessage("user", prompt)]).strip())
    if not result:
        raise RuntimeError("Empty model output")
    if _looks_like_meta_output(result):
        raise RuntimeError("Model output contains reasoning/meta text")
    return result


def _record_model_error(repo: Repository, row, exc: Exception) -> None:
    repo.set_status(row["block_id"], "draft_failed")
    repo.insert_issue(
        {
            "block_id": row["block_id"],
            "chapter_id": row["chapter_id"],
            "paragraph_index": row["paragraph_index"] or 0,
            "issue_type": "draft:model_error",
            "issue_severity": "high",
            "actual_translation": str(exc),
        }
    )


def _abort_backend_unavailable(
    repo: Repository,
    exc: BackendUnavailableError,
    translated: int,
    failed: int,
    skipped: int,
    concurrency: int,
    submitted: int,
) -> None:
    message = (
        "Draft translation aborted: LLM backend is unavailable. "
        f"Saved {translated} translated blocks; {failed} model-output failures; {skipped} skipped. "
        "Restart LM Studio and rerun draft-translate without --overwrite-model-drafts to continue."
    )
    repo.log_event(
        "draft_translate",
        message,
        {
            "concurrency": concurrency,
            "submitted": submitted,
            "error": str(exc),
        },
    )
    raise RuntimeError(f"{message} Last backend error: {exc}") from exc


def _relevant_terms(source_text: str, glossary: list[dict[str, str]]) -> list[dict[str, str]]:
    return [term for term in glossary if str(term.get("source", "")) in source_text]


def _draft_prompt(config: AppConfig, repo: Repository, row, terms: list[dict[str, str]]) -> str:
    context = repo.get_context(row["block_id"], before=config.translation.previous_translated_paragraphs, after=config.translation.next_source_paragraphs)
    previous = []
    next_source = []
    for item in context["rows"]:
        if item["block_index"] < row["block_index"]:
            previous.append(item["human_draft_edit"] or item["draft_translation"] or "")
        elif item["block_index"] > row["block_index"]:
            next_source.append(item["source_text"])
    return "\n".join(
        [
            "/no_think",
            "Translate Korean source to Russian. Return only Russian translation.",
            "Do not think out loud. Do not output reasoning, comments, labels, or explanations.",
            "Preserve meaning, paragraph order, dialogue structure, and glossary terms.",
            f"Book memory: {build_book_memory()}",
            f"Chapter summary: {chapter_summary(row['chapter_id'])}",
            f"Glossary: {terms}",
            f"Previous translated paragraphs: {previous}",
            f"Next source paragraphs for context only: {next_source}",
            f"Korean source:\n{row['source_text']}",
        ]
    )


def _postprocess_draft_output(text: str) -> str:
    result = text.strip()
    if result.startswith("```") and result.endswith("```"):
        lines = result.splitlines()
        if len(lines) >= 3:
            result = "\n".join(lines[1:-1]).strip()
    if len(result) >= 2 and result[0] == "\u201c" and result[-1] == "\u201c":
        result = result[:-1] + "\u201d"
    if len(result) >= 2 and result[0] == "\u2018" and result[-1] == "\u2018":
        result = result[:-1] + "\u2019"
    return result


def _looks_like_meta_output(text: str) -> bool:
    return any(marker in text for marker in META_OUTPUT_MARKERS)
