from __future__ import annotations

import json
import re

from epub_llm_translate.backends import BackendUnavailableError, ChatMessage, create_backend
from epub_llm_translate.config import AppConfig
from epub_llm_translate.db.repositories import Repository
from epub_llm_translate.memory.chapter_summary import chapter_summary
from epub_llm_translate.reference.retrieve_examples import retrieve_reference_context_range, retrieve_reference_examples
from epub_llm_translate.reference.style_guide import load_style_guide


def revise(
    config: AppConfig,
    repo: Repository,
    chapter_ids: list[int],
    glossary: list[dict[str, str]],
    profile: str,
    use_reference: bool,
    batch_blocks: int | None = None,
    overwrite_revised: bool = False,
) -> dict[str, int]:
    backend = create_backend(config.models.revise)
    style_guide = load_style_guide(config.workdir / "reference" / "reference_style_guide.yaml")
    revised = 0
    skipped = 0
    failed = 0
    placeholders = ",".join("?" for _ in chapter_ids)
    high_count = repo.conn.execute(
        f"""
        SELECT COUNT(*) AS count FROM quality_issues
        WHERE status != 'approved'
          AND issue_severity = 'high'
          AND chapter_id IN ({placeholders})
        """,
        chapter_ids,
    ).fetchone()["count"]
    pause_revision = (
        config.review_flow.mode == "assisted"
        and high_count > config.review_flow.max_unreviewed_high_issues
        and config.review_flow.action_when_limit_reached == "pause_revision_only"
    )
    if pause_revision:
        repo.log_event("revise", f"Revision paused because high severity backlog is {high_count}")
        return {"revised": 0, "skipped": 0, "failed": 0}
    candidates = []
    for row in repo.list_blocks(chapter_ids):
        if row["locked_by"] or row["human_final_edit"]:
            skipped += 1
            continue
        draft = row["human_draft_edit"] or row["draft_translation"]
        if not draft:
            skipped += 1
            continue
        if row["revised_translation"] and not overwrite_revised:
            skipped += 1
            continue
        candidates.append(row)
    batches = _batch_rows(candidates, max(1, batch_blocks or config.revision.batch_blocks), config.revision.chunk_max_chars)
    for batch in batches:
        try:
            batch_revised, batch_skipped, batch_failed = _revise_batch(
                config,
                repo,
                backend,
                batch,
                glossary,
                style_guide,
                profile,
                use_reference,
            )
            revised += batch_revised
            skipped += batch_skipped
            failed += batch_failed
        except BackendUnavailableError as exc:
            message = (
                "Revision aborted: LLM backend is unavailable. "
                f"Saved {revised} revised blocks; {failed} model-output failures; {skipped} skipped. "
                "Restart LM Studio and rerun revise without changing completed rows to continue."
            )
            repo.log_event("revise", message, {"error": str(exc)})
            raise RuntimeError(f"{message} Last backend error: {exc}") from exc
    repo.log_event(
        "revise",
        f"Revision finished: {revised} revised, {skipped} skipped, {failed} failed",
        {"batch_blocks": max(1, batch_blocks or config.revision.batch_blocks), "batches": len(batches)},
    )
    return {"revised": revised, "skipped": skipped, "failed": failed, "batches": len(batches)}


def _revise_batch(
    config: AppConfig,
    repo: Repository,
    backend,
    batch,
    glossary: list[dict[str, str]],
    style_guide: str,
    profile: str,
    use_reference: bool,
) -> tuple[int, int, int]:
    prompt = _revision_batch_prompt(config, repo, batch, glossary, style_guide, profile, use_reference)
    try:
        result = backend.generate([ChatMessage("user", prompt)]).strip()
        if not result:
            raise RuntimeError("Empty model output")
        translations = _parse_batch_response(result)
    except BackendUnavailableError:
        raise
    except Exception as exc:
        if len(batch) > 1:
            return _revise_split_batch(config, repo, backend, batch, glossary, style_guide, profile, use_reference)
        _record_revision_errors(repo, batch, exc)
        return 0, 0, len(batch)

    revised = 0
    skipped = 0
    failed = 0
    missing = []
    for row in batch:
        block_id = row["block_id"]
        if block_id not in translations:
            missing.append(row)
            continue
        saved = repo.save_model_translation(
            block_id,
            "revised_translation",
            translations[block_id],
            config.models.revise.model,
            "revision_done",
        )
        if saved:
            _clear_revision_issues(repo, block_id)
            revised += 1
        else:
            skipped += 1
    if missing:
        if len(missing) < len(batch):
            sub_revised, sub_skipped, sub_failed = _revise_batch(
                config,
                repo,
                backend,
                missing,
                glossary,
                style_guide,
                profile,
                use_reference,
            )
            revised += sub_revised
            skipped += sub_skipped
            failed += sub_failed
        elif len(batch) > 1:
            sub_revised, sub_skipped, sub_failed = _revise_split_batch(
                config,
                repo,
                backend,
                batch,
                glossary,
                style_guide,
                profile,
                use_reference,
            )
            revised += sub_revised
            skipped += sub_skipped
            failed += sub_failed
        else:
            _record_revision_errors(repo, batch, RuntimeError("Batch revision output missing block_id"))
            failed += len(batch)
    return revised, skipped, failed


def _revise_split_batch(
    config: AppConfig,
    repo: Repository,
    backend,
    batch,
    glossary: list[dict[str, str]],
    style_guide: str,
    profile: str,
    use_reference: bool,
) -> tuple[int, int, int]:
    midpoint = max(1, len(batch) // 2)
    left = _revise_batch(config, repo, backend, batch[:midpoint], glossary, style_guide, profile, use_reference)
    right = _revise_batch(config, repo, backend, batch[midpoint:], glossary, style_guide, profile, use_reference)
    return left[0] + right[0], left[1] + right[1], left[2] + right[2]


def _record_revision_errors(repo: Repository, batch, exc: Exception) -> None:
    for row in batch:
        repo.set_status(row["block_id"], "revision_failed")
        repo.insert_issue(
            {
                "block_id": row["block_id"],
                "chapter_id": row["chapter_id"],
                "paragraph_index": row["paragraph_index"] or 0,
                "issue_type": "revision:model_error",
                "issue_severity": "high",
                "actual_translation": str(exc),
            }
        )


def _clear_revision_issues(repo: Repository, block_id: str) -> None:
    repo.conn.execute(
        "DELETE FROM quality_issues WHERE block_id = ? AND issue_type LIKE 'revision:%'",
        (block_id,),
    )
    repo.conn.commit()


def _batch_rows(rows, batch_blocks: int, max_chars: int) -> list[list]:
    batches: list[list] = []
    current: list = []
    current_chars = 0
    for row in rows:
        row_chars = len(row["source_text"] or "") + len(row["human_draft_edit"] or row["draft_translation"] or "")
        starts_new_chapter = current and current[-1]["chapter_id"] != row["chapter_id"]
        too_many_blocks = len(current) >= batch_blocks
        too_many_chars = current and current_chars + row_chars > max_chars
        if starts_new_chapter or too_many_blocks or too_many_chars:
            batches.append(current)
            current = []
            current_chars = 0
        current.append(row)
        current_chars += row_chars
    if current:
        batches.append(current)
    return batches


def _revision_batch_prompt(
    config: AppConfig,
    repo: Repository,
    batch,
    glossary: list[dict[str, str]],
    style_guide: str,
    profile: str,
    use_reference: bool,
) -> str:
    first = batch[0]
    last = batch[-1]
    context = repo.get_context(first["block_id"], before=config.revision.previous_revised_paragraphs, after=0)
    previous = []
    for item in context["rows"]:
        if item["block_index"] < first["block_index"]:
            previous.append(item["human_final_edit"] or item["revised_translation"] or "")
    reference_context = ""
    examples: list[str] = []
    if use_reference:
        examples = retrieve_reference_examples(repo, min(2, config.reference.max_examples_per_block), first["chapter_id"])
        reference_context = retrieve_reference_context_range(
            repo,
            first["chapter_id"],
            first["paragraph_index"],
            last["paragraph_index"],
            max_chars=max(config.reference.example_max_chars * 2, 2400),
        )
    items = [
        {
            "block_id": row["block_id"],
            "paragraph_index": row["paragraph_index"] or 0,
            "korean_source": row["source_text"],
            "russian_draft": row["human_draft_edit"] or row["draft_translation"] or "",
        }
        for row in batch
    ]
    response_shape = {"translations": [{"block_id": row["block_id"], "revised_text": "исправленный русский текст"} for row in batch]}
    return "\n".join(
        [
            "/no_think",
            f"Revise a batch of Korean-to-Russian literary translation paragraphs. Profile: {profile}.",
            "Improve Russian style, fluency, consistency, and terminology while preserving meaning.",
            "Do not delete details. Do not add new events. Preserve approved names and terms.",
            "Use the same-chapter Russian reference context to match established wording, tone, names, and terminology.",
            "Return strict JSON object only. No markdown, no comments, no explanations.",
            "Return exactly one object per input block_id, in the same order.",
            f"Approved glossary:\n{glossary}",
            f"Reference style guide:\n{style_guide}",
            f"Reference examples:\n{examples}",
            f"Same-chapter Russian reference context:\n{reference_context}",
            f"Chapter summary: {chapter_summary(first['chapter_id'])}",
            f"Previous revised Russian paragraphs: {previous}",
            f"Required JSON shape:\n{json.dumps(response_shape, ensure_ascii=False)}",
            f"Input batch:\n{json.dumps(items, ensure_ascii=False)}",
        ]
    )


def _parse_batch_response(output: str) -> dict[str, str]:
    text = _strip_json_fence(output)
    text = _extract_json_payload(text)
    data = json.loads(text)
    if isinstance(data, dict):
        if isinstance(data.get("translations"), list):
            data = data["translations"]
        elif isinstance(data.get("items"), list):
            data = data["items"]
        else:
            return {str(key): str(value).strip() for key, value in data.items() if str(value).strip()}
    if not isinstance(data, list):
        raise RuntimeError("Batch revision output must be a JSON array")
    result: dict[str, str] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        block_id = str(item.get("block_id") or "").strip()
        text_value = item.get("revised_text") or item.get("translation") or item.get("text")
        if block_id and isinstance(text_value, str) and text_value.strip():
            result[block_id] = text_value.strip()
    return result


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)```", stripped, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return stripped


def _extract_json_payload(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("[") or stripped.startswith("{"):
        return stripped
    array_start = stripped.find("[")
    object_start = stripped.find("{")
    starts = [index for index in (array_start, object_start) if index >= 0]
    if not starts:
        return stripped
    start = min(starts)
    opener = stripped[start]
    closer = "]" if opener == "[" else "}"
    end = stripped.rfind(closer)
    if end <= start:
        return stripped
    return stripped[start : end + 1]
