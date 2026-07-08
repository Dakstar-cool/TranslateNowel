from __future__ import annotations

import json

from epub_llm_translate.db.repositories import Repository
from epub_llm_translate.utils import utc_now


def enqueue_job(repo: Repository, job_type: str, block_id: str | None = None, chapter_id: int | None = None, priority: int = 0, payload: dict | None = None) -> int:
    cur = repo.conn.execute(
        """
        INSERT INTO pipeline_jobs(job_type, block_id, chapter_id, status, priority, payload_json, created_at, updated_at)
        VALUES (?, ?, ?, 'pending', ?, ?, ?, ?)
        """,
        (job_type, block_id, chapter_id, priority, json.dumps(payload or {}, ensure_ascii=False), utc_now(), utc_now()),
    )
    repo.conn.commit()
    return int(cur.lastrowid)

