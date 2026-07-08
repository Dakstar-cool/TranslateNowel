from __future__ import annotations

import csv
from pathlib import Path
import re

from jinja2 import Template

from epub_llm_translate.config import AppConfig
from epub_llm_translate.db.repositories import Repository
from epub_llm_translate.qa.checks import check_block_quality


HANGUL_RE = re.compile(r"[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]")

BENCHMARK_TEMPLATE = Template(
    """
<!doctype html>
<html>
<head><meta charset="utf-8"><title>Reference Benchmark</title></head>
<body>
<h1>Reference Benchmark</h1>
<p>Compares aggregate draft/revised metrics against available human reference chapters. Text content is intentionally omitted.</p>
<table border="1" cellspacing="0" cellpadding="4">
<thead>
<tr>{% for header in headers %}<th>{{ header }}</th>{% endfor %}</tr>
</thead>
<tbody>
{% for row in rows %}
<tr>{% for header in headers %}<td>{{ row.get(header, '') }}</td>{% endfor %}</tr>
{% endfor %}
</tbody>
</table>
</body>
</html>
"""
)


HEADERS = [
    "chapter_id",
    "blocks",
    "reference_chars",
    "draft_blocks",
    "revised_blocks",
    "draft_chars",
    "revised_chars",
    "draft_ref_ratio",
    "revised_ref_ratio",
    "draft_quality_issues",
    "revised_quality_issues",
    "draft_remaining_hangul",
    "revised_remaining_hangul",
]


def benchmark_reference(
    config: AppConfig,
    repo: Repository,
    chapter_ids: list[int],
    glossary: list[dict[str, str]],
) -> dict[str, object]:
    rows = [_chapter_metrics(config, repo, chapter_id, glossary) for chapter_id in chapter_ids]
    rows = [row for row in rows if row is not None]
    csv_path = config.workdir / "reference_benchmark_report.csv"
    html_path = config.workdir / "reference_benchmark_report.html"
    _write_csv(rows, csv_path)
    html_path.write_text(BENCHMARK_TEMPLATE.render(headers=HEADERS, rows=rows), encoding="utf-8")
    repo.log_event("benchmark_reference", f"Benchmarked {len(rows)} chapters against reference")
    return {"chapters": len(rows), "csv": str(csv_path), "html": str(html_path), "rows": rows}


def _chapter_metrics(config: AppConfig, repo: Repository, chapter_id: int, glossary: list[dict[str, str]]) -> dict[str, object] | None:
    reference = repo.get_reference_chapter(chapter_id)
    if reference is None:
        return None
    blocks = repo.list_blocks([chapter_id])
    reference_text = reference["text"] or ""
    draft_parts: list[str] = []
    revised_parts: list[str] = []
    draft_issues = 0
    revised_issues = 0
    draft_blocks = 0
    revised_blocks = 0
    for block in blocks:
        draft = block["human_draft_edit"] or block["draft_translation"] or ""
        revised = block["human_final_edit"] or block["revised_translation"] or ""
        if draft:
            draft_blocks += 1
            draft_parts.append(draft)
        if revised:
            revised_blocks += 1
            revised_parts.append(revised)
        draft_issues += len(check_block_quality(block, draft, glossary, config.quality, "draft_benchmark"))
        revised_target = revised or draft
        revised_issues += len(check_block_quality(block, revised_target, glossary, config.quality, "revised_benchmark"))
    draft_text = "\n".join(draft_parts)
    revised_text = "\n".join(revised_parts)
    reference_chars = len(reference_text)
    return {
        "chapter_id": chapter_id,
        "blocks": len(blocks),
        "reference_chars": reference_chars,
        "draft_blocks": draft_blocks,
        "revised_blocks": revised_blocks,
        "draft_chars": len(draft_text),
        "revised_chars": len(revised_text),
        "draft_ref_ratio": _ratio(len(draft_text), reference_chars),
        "revised_ref_ratio": _ratio(len(revised_text), reference_chars),
        "draft_quality_issues": draft_issues,
        "revised_quality_issues": revised_issues,
        "draft_remaining_hangul": len(HANGUL_RE.findall(draft_text)),
        "revised_remaining_hangul": len(HANGUL_RE.findall(revised_text)),
    }


def _ratio(value: int, baseline: int) -> str:
    if not baseline:
        return ""
    return f"{value / baseline:.2f}"


def _write_csv(rows: list[dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)
