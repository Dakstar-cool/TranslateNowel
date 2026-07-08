from __future__ import annotations

import csv
from pathlib import Path

from jinja2 import Template


REPORT_TEMPLATE = Template(
    """
<!doctype html>
<html>
<head><meta charset="utf-8"><title>{{ title }}</title></head>
<body>
<h1>{{ title }}</h1>
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


def write_issue_reports(rows, csv_path: Path, html_path: Path, title: str) -> dict[str, str]:
    headers = [
        "issue_id",
        "block_id",
        "chapter_id",
        "paragraph_index",
        "issue_type",
        "issue_severity",
        "source_term",
        "expected_translation",
        "actual_translation",
        "status",
    ]
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    dict_rows = [{header: row[header] if header in row.keys() else "" for header in headers} for row in rows]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()
        writer.writerows(dict_rows)
    html_path.write_text(REPORT_TEMPLATE.render(title=title, headers=headers, rows=dict_rows), encoding="utf-8")
    return {"csv": str(csv_path), "html": str(html_path)}

