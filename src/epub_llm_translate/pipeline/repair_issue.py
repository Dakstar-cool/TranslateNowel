from __future__ import annotations

from epub_llm_translate.backends import ChatMessage, create_backend
from epub_llm_translate.config import AppConfig
from epub_llm_translate.db.repositories import Repository
from epub_llm_translate.reference.retrieve_examples import retrieve_reference_examples
from epub_llm_translate.reference.style_guide import load_style_guide


def repair_issue(config: AppConfig, repo: Repository, issue_id: int, glossary: list[dict[str, str]]) -> dict[str, object]:
    issue = repo.conn.execute("SELECT * FROM quality_issues WHERE issue_id = ?", (issue_id,)).fetchone()
    if issue is None:
        raise KeyError(f"Unknown issue_id: {issue_id}")
    block = repo.get_block(issue["block_id"])
    if block is None:
        raise KeyError(f"Missing block for issue_id: {issue_id}")
    context = repo.get_context(block["block_id"], before=1, after=1)
    previous = [row for row in context["rows"] if row["block_index"] < block["block_index"]]
    next_rows = [row for row in context["rows"] if row["block_index"] > block["block_index"]]
    target = block["human_final_edit"] or block["revised_translation"] or block["human_draft_edit"] or block["draft_translation"] or ""
    prompt = "\n".join(
        [
            "Fix only the target Russian paragraph. Do not rewrite previous or next paragraphs.",
            "Return only the corrected target paragraph.",
            f"Issue: {dict(issue)}",
            f"Previous source context: {[row['source_text'] for row in previous]}",
            f"Target Korean source: {block['source_text']}",
            f"Next source context: {[row['source_text'] for row in next_rows]}",
            f"Previous Russian context: {[row['human_final_edit'] or row['revised_translation'] or row['human_draft_edit'] or row['draft_translation'] or '' for row in previous]}",
            f"Target Russian paragraph:\nTARGET:{target}",
            f"Next Russian context: {[row['human_final_edit'] or row['revised_translation'] or row['human_draft_edit'] or row['draft_translation'] or '' for row in next_rows]}",
            f"Approved glossary: {glossary}",
            f"Reference style guide: {load_style_guide(config.workdir / 'reference' / 'reference_style_guide.yaml')}",
            f"Reference examples: {retrieve_reference_examples(repo, config.reference.max_examples_per_block)}",
        ]
    )
    backend = create_backend(config.models.revise)
    repaired = backend.generate([ChatMessage("user", prompt)]).strip()
    if not repaired:
        raise RuntimeError("Empty repair output")
    repo.save_human_edit(block["block_id"], "human_final_edit", repaired, edited_by="repair_issue", reason=f"issue:{issue_id}")
    repo.approve_issue(issue_id)
    repo.log_event("repair_issue", f"Repaired issue {issue_id}")
    return {"issue_id": issue_id, "block_id": block["block_id"]}

