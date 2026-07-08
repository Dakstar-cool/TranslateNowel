from __future__ import annotations

from epub_llm_translate.backends import BackendUnavailableError, ChatMessage, create_backend
from epub_llm_translate.config import AppConfig
from epub_llm_translate.db.repositories import Repository
from epub_llm_translate.memory.chapter_summary import chapter_summary
from epub_llm_translate.reference.retrieve_examples import retrieve_reference_examples
from epub_llm_translate.reference.style_guide import load_style_guide


def revise(config: AppConfig, repo: Repository, chapter_ids: list[int], glossary: list[dict[str, str]], profile: str, use_reference: bool) -> dict[str, int]:
    backend = create_backend(config.models.revise)
    style_guide = load_style_guide(config.workdir / "reference" / "reference_style_guide.yaml")
    examples = retrieve_reference_examples(repo, config.reference.max_examples_per_block) if use_reference else []
    revised = 0
    skipped = 0
    failed = 0
    high_count = repo.unresolved_high_issue_count()
    pause_revision = (
        config.review_flow.mode == "assisted"
        and high_count > config.review_flow.max_unreviewed_high_issues
        and config.review_flow.action_when_limit_reached == "pause_revision_only"
    )
    if pause_revision:
        repo.log_event("revise", f"Revision paused because high severity backlog is {high_count}")
        return {"revised": 0, "skipped": 0, "failed": 0}
    high_blocks = {row["block_id"] for row in repo.conn.execute("SELECT DISTINCT block_id FROM quality_issues WHERE status != 'approved' AND issue_severity = 'high'")}
    for row in repo.list_blocks(chapter_ids):
        if row["locked_by"] or (config.review_flow.mode == "assisted" and row["block_id"] in high_blocks):
            skipped += 1
            continue
        draft = row["human_draft_edit"] or row["draft_translation"]
        if not draft:
            skipped += 1
            continue
        prompt = _revision_prompt(config, repo, row, draft, glossary, style_guide, examples, profile)
        try:
            result = backend.generate([ChatMessage("user", prompt)]).strip()
            if not result:
                raise RuntimeError("Empty model output")
            repo.save_model_translation(row["block_id"], "revised_translation", result, config.models.revise.model, "revision_done")
            revised += 1
        except BackendUnavailableError as exc:
            message = (
                "Revision aborted: LLM backend is unavailable. "
                f"Saved {revised} revised blocks; {failed} model-output failures; {skipped} skipped. "
                "Restart LM Studio and rerun revise without changing completed rows to continue."
            )
            repo.log_event("revise", message, {"error": str(exc)})
            raise RuntimeError(f"{message} Last backend error: {exc}") from exc
        except Exception as exc:
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
            failed += 1
    repo.log_event("revise", f"Revision finished: {revised} revised, {skipped} skipped, {failed} failed")
    return {"revised": revised, "skipped": skipped, "failed": failed}


def _revision_prompt(config: AppConfig, repo: Repository, row, draft: str, glossary: list[dict[str, str]], style_guide: str, examples: list[str], profile: str) -> str:
    context = repo.get_context(row["block_id"], before=config.revision.previous_revised_paragraphs, after=config.revision.next_draft_paragraphs)
    previous = []
    for item in context["rows"]:
        if item["block_index"] < row["block_index"]:
            previous.append(item["human_final_edit"] or item["revised_translation"] or "")
    return "\n".join(
        [
            f"Revise Korean-to-Russian literary translation. Profile: {profile}.",
            "Improve Russian quality while preserving meaning. Return only revised Russian text.",
            "Do not delete details. Do not add new events. Preserve approved names and terms.",
            f"Korean source:\n{row['source_text']}",
            f"Russian draft:\n{draft}",
            f"Approved glossary:\n{glossary}",
            f"Reference style guide:\n{style_guide}",
            f"Reference examples:\n{examples}",
            f"Chapter summary: {chapter_summary(row['chapter_id'])}",
            f"Previous revised Russian paragraphs: {previous}",
        ]
    )
