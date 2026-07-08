from __future__ import annotations

from collections import Counter
import re

from epub_llm_translate.db.repositories import Repository
from epub_llm_translate.utils import HANGUL_RE


TERM_RE = re.compile(r"[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]{2,}")


def extract_candidates(repo: Repository, limit: int = 500) -> list[dict[str, object]]:
    counts: Counter[str] = Counter()
    for row in repo.list_blocks():
        counts.update(TERM_RE.findall(row["source_text"]))
    candidates = []
    for term, count in counts.most_common(limit):
        if HANGUL_RE.search(term):
            candidates.append(
                {
                    "source": term,
                    "translation": "",
                    "category": "unknown",
                    "status": "needs_review",
                    "priority": "normal",
                    "evidence": [{"type": "source_frequency", "count": count}],
                }
            )
    return candidates

