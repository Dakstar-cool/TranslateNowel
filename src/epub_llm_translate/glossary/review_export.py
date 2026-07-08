from __future__ import annotations

import csv
from pathlib import Path

import yaml


def export_glossary_review(workdir: Path, candidates: list[dict[str, object]]) -> dict[str, str]:
    workdir.mkdir(parents=True, exist_ok=True)
    csv_path = workdir / "glossary_candidates.csv"
    md_path = workdir / "glossary_review.md"
    draft_path = workdir / "glossary.draft.yaml"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["source", "translation", "category", "status", "priority"])
        writer.writeheader()
        for item in candidates:
            writer.writerow(
                {
                    "source": item.get("source", ""),
                    "translation": item.get("translation", ""),
                    "category": item.get("category", ""),
                    "status": item.get("status", "needs_review"),
                    "priority": item.get("priority", "normal"),
                }
            )
    md_lines = [
        "# Glossary Review",
        "",
        "Manual approval is required. Copy reviewed entries to `glossary.approved.yaml`.",
        "",
        "| Source | Translation | Category | Status | Priority |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in candidates:
        md_lines.append(
            f"| {item.get('source', '')} | {item.get('translation', '')} | {item.get('category', '')} | {item.get('status', '')} | {item.get('priority', '')} |"
        )
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    draft_path.write_text(yaml.safe_dump({"terms": candidates}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {"csv": str(csv_path), "markdown": str(md_path), "draft": str(draft_path)}

