from __future__ import annotations

from collections.abc import Iterable
import json
import sqlite3
from typing import Any

from epub_llm_translate.utils import utc_now


EDITABLE_TEXT_FIELDS = {"draft_translation", "human_draft_edit", "revised_translation", "human_final_edit"}
HUMAN_EDIT_FIELDS = {"human_draft_edit", "human_final_edit"}


class Repository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def log_event(self, event_type: str, message: str, payload: dict[str, Any] | None = None) -> None:
        self.conn.execute(
            """
            INSERT INTO pipeline_events(event_type, message, payload_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (event_type, message, json.dumps(payload or {}, ensure_ascii=False), utc_now()),
        )
        self.conn.commit()

    def save_pipeline_progress(self, job_type: str, status: str, payload: dict[str, Any]) -> int:
        stored_status = "running" if status in {"starting", "running"} else status
        now = utc_now()
        running = self.conn.execute(
            """
            SELECT job_id FROM pipeline_jobs
            WHERE job_type = ? AND status = 'running'
            ORDER BY job_id DESC LIMIT 1
            """,
            (job_type,),
        ).fetchone()
        if running is not None:
            job_id = int(running["job_id"])
            self.conn.execute(
                """
                UPDATE pipeline_jobs
                SET status = ?, payload_json = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (stored_status, json.dumps(payload, ensure_ascii=False), now, job_id),
            )
        else:
            cur = self.conn.execute(
                """
                INSERT INTO pipeline_jobs(job_type, status, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_type, stored_status, json.dumps(payload, ensure_ascii=False), now, now),
            )
            job_id = int(cur.lastrowid)
        self.conn.commit()
        return job_id

    def latest_pipeline_job(self, job_type: str | None = None) -> sqlite3.Row | None:
        if job_type:
            return self.conn.execute(
                """
                SELECT * FROM pipeline_jobs
                WHERE job_type = ?
                ORDER BY job_id DESC LIMIT 1
                """,
                (job_type,),
            ).fetchone()
        return self.conn.execute(
            "SELECT * FROM pipeline_jobs ORDER BY job_id DESC LIMIT 1"
        ).fetchone()

    def recent_events(self, limit: int = 100) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM pipeline_events ORDER BY event_id DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def upsert_chapter(self, chapter_id: int, title: str | None, href: str | None, spine_index: int, block_count: int) -> None:
        now = utc_now()
        self.conn.execute(
            """
            INSERT INTO chapters(chapter_id, title, href, spine_index, status, block_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
            ON CONFLICT(chapter_id) DO UPDATE SET
                title = excluded.title,
                href = excluded.href,
                spine_index = excluded.spine_index,
                block_count = excluded.block_count,
                updated_at = excluded.updated_at
            """,
            (chapter_id, title, href, spine_index, block_count, now, now),
        )

    def upsert_block(
        self,
        block_id: str,
        chapter_id: int,
        block_index: int,
        paragraph_index: int | None,
        source_text: str,
        source_hash: str,
        status: str = "pending",
    ) -> None:
        now = utc_now()
        self.conn.execute(
            """
            INSERT INTO translation_blocks(
                block_id, chapter_id, block_index, paragraph_index, source_text, source_hash,
                status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(block_id) DO UPDATE SET
                chapter_id = excluded.chapter_id,
                block_index = excluded.block_index,
                paragraph_index = excluded.paragraph_index,
                source_text = excluded.source_text,
                source_hash = excluded.source_hash,
                updated_at = excluded.updated_at
            """,
            (block_id, chapter_id, block_index, paragraph_index, source_text, source_hash, status, now, now),
        )

    def commit(self) -> None:
        self.conn.commit()

    def list_blocks(self, chapter_ids: Iterable[int] | None = None) -> list[sqlite3.Row]:
        ids = list(chapter_ids or [])
        if ids:
            placeholders = ",".join("?" for _ in ids)
            return self.conn.execute(
                f"""
                SELECT * FROM translation_blocks
                WHERE chapter_id IN ({placeholders})
                ORDER BY chapter_id, block_index
                """,
                ids,
            ).fetchall()
        return self.conn.execute(
            "SELECT * FROM translation_blocks ORDER BY chapter_id, block_index"
        ).fetchall()

    def get_block(self, block_id: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM translation_blocks WHERE block_id = ?",
            (block_id,),
        ).fetchone()

    def get_block_by_issue_id(self, issue_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            """
            SELECT b.* FROM translation_blocks b
            JOIN quality_issues q ON q.block_id = b.block_id
            WHERE q.issue_id = ?
            """,
            (issue_id,),
        ).fetchone()

    def get_context(self, block_id: str, before: int = 1, after: int = 1) -> dict[str, Any]:
        target = self.get_block(block_id)
        if target is None:
            raise KeyError(f"Unknown block_id: {block_id}")
        rows = self.conn.execute(
            """
            SELECT * FROM translation_blocks
            WHERE chapter_id = ?
              AND block_index BETWEEN ? AND ?
            ORDER BY block_index
            """,
            (
                target["chapter_id"],
                max(0, target["block_index"] - before),
                target["block_index"] + after,
            ),
        ).fetchall()
        return {"target": target, "rows": rows}

    def set_status(self, block_id: str, status: str, quality_status: str | None = None) -> None:
        self.conn.execute(
            """
            UPDATE translation_blocks
            SET status = ?, quality_status = COALESCE(?, quality_status), updated_at = ?
            WHERE block_id = ?
            """,
            (status, quality_status, utc_now(), block_id),
        )
        self.conn.commit()

    def save_model_translation(self, block_id: str, field_name: str, text: str, model: str | None, status: str) -> bool:
        if field_name not in {"draft_translation", "revised_translation"}:
            raise ValueError(f"Unsupported model translation field: {field_name}")
        row = self.get_block(block_id)
        if row is None:
            raise KeyError(block_id)
        if row["locked_by"]:
            return False
        model_field = "draft_model" if field_name == "draft_translation" else "revision_model"
        self.conn.execute(
            f"""
            UPDATE translation_blocks
            SET {field_name} = ?, {model_field} = ?, status = ?, updated_at = ?
            WHERE block_id = ?
            """,
            (text, model, status, utc_now(), block_id),
        )
        self.conn.commit()
        return True

    def save_human_edit(self, block_id: str, field_name: str, text: str, edited_by: str = "user", reason: str | None = None) -> None:
        if field_name not in HUMAN_EDIT_FIELDS:
            raise ValueError(f"Human edits are only allowed for {sorted(HUMAN_EDIT_FIELDS)}")
        row = self.get_block(block_id)
        if row is None:
            raise KeyError(block_id)
        old_text = row[field_name]
        now = utc_now()
        self.conn.execute(
            f"UPDATE translation_blocks SET {field_name} = ?, status = 'human_edited', updated_at = ? WHERE block_id = ?",
            (text, now, block_id),
        )
        self.conn.execute(
            """
            INSERT INTO edit_history(block_id, field_name, old_text, new_text, edited_by, edit_reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (block_id, field_name, old_text, text, edited_by, reason, now),
        )
        self.conn.commit()

    def lock_block(self, block_id: str, locked_by: str = "user") -> None:
        self.conn.execute(
            "UPDATE translation_blocks SET locked_by = ?, locked_at = ?, status = 'locked', updated_at = ? WHERE block_id = ?",
            (locked_by, utc_now(), utc_now(), block_id),
        )
        self.conn.commit()

    def unlock_block(self, block_id: str) -> None:
        self.conn.execute(
            "UPDATE translation_blocks SET locked_by = NULL, locked_at = NULL, status = 'needs_review', updated_at = ? WHERE block_id = ?",
            (utc_now(), block_id),
        )
        self.conn.commit()

    def final_text_for_row(self, row: sqlite3.Row) -> str:
        for field in ("human_final_edit", "revised_translation", "human_draft_edit", "draft_translation"):
            value = row[field]
            if value:
                return value
        return ""

    def insert_issue(self, issue: dict[str, Any]) -> int:
        now = utc_now()
        cur = self.conn.execute(
            """
            INSERT INTO quality_issues(
                block_id, chapter_id, paragraph_index, issue_type, issue_severity,
                source_term, expected_translation, actual_translation, target_text,
                char_start, char_end, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                issue["block_id"],
                issue["chapter_id"],
                issue.get("paragraph_index") or 0,
                issue["issue_type"],
                issue["issue_severity"],
                issue.get("source_term"),
                issue.get("expected_translation"),
                issue.get("actual_translation"),
                issue.get("target_text"),
                issue.get("char_start"),
                issue.get("char_end"),
                issue.get("status", "needs_review"),
                now,
                now,
            ),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def clear_issues(self, stage: str | None = None) -> None:
        if stage:
            self.conn.execute("DELETE FROM quality_issues WHERE issue_type LIKE ?", (f"{stage}:%",))
        else:
            self.conn.execute("DELETE FROM quality_issues")
        self.conn.commit()

    def list_issues(self, status: str | None = None, limit: int = 1000) -> list[sqlite3.Row]:
        if status:
            return self.conn.execute(
                """
                SELECT * FROM quality_issues
                WHERE status = ?
                ORDER BY
                    CASE issue_severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                    chapter_id, paragraph_index, issue_id
                LIMIT ?
                """,
                (status, limit),
            ).fetchall()
        return self.conn.execute(
            """
            SELECT * FROM quality_issues
            ORDER BY
                CASE issue_severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                chapter_id, paragraph_index, issue_id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    def get_issue(self, issue_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM quality_issues WHERE issue_id = ?",
            (issue_id,),
        ).fetchone()

    def approve_issue(self, issue_id: int) -> None:
        self.conn.execute(
            "UPDATE quality_issues SET status = 'approved', updated_at = ? WHERE issue_id = ?",
            (utc_now(), issue_id),
        )
        self.conn.commit()

    def update_issue_status(self, issue_id: int, status: str) -> None:
        self.conn.execute(
            "UPDATE quality_issues SET status = ?, updated_at = ? WHERE issue_id = ?",
            (status, utc_now(), issue_id),
        )
        self.conn.commit()

    def unresolved_high_issue_count(self) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS count FROM quality_issues
            WHERE status != 'approved' AND issue_severity = 'high'
            """
        ).fetchone()
        return int(row["count"])

    def chapters_summary(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            """
            SELECT c.*,
                   COUNT(q.issue_id) AS issue_count,
                   SUM(CASE WHEN q.issue_severity = 'high' AND q.status != 'approved' THEN 1 ELSE 0 END) AS high_issue_count
            FROM chapters c
            LEFT JOIN quality_issues q ON q.chapter_id = c.chapter_id
            GROUP BY c.chapter_id
            ORDER BY c.chapter_id
            """
        ).fetchall()

    def dashboard_summary(self) -> dict[str, int]:
        row = self.conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM chapters) AS total_chapters,
              (SELECT COUNT(*) FROM translation_blocks) AS total_blocks,
              (SELECT COUNT(*) FROM translation_blocks WHERE draft_translation IS NOT NULL OR human_draft_edit IS NOT NULL) AS draft_done,
              (SELECT COUNT(*) FROM translation_blocks WHERE revised_translation IS NOT NULL OR human_final_edit IS NOT NULL) AS revision_done,
              (SELECT COUNT(*) FROM quality_issues) AS issue_count,
              (SELECT COUNT(*) FROM quality_issues WHERE issue_severity = 'high' AND status != 'approved') AS high_issue_count,
              (SELECT COUNT(*) FROM translation_blocks WHERE locked_by IS NOT NULL) AS locked_block_count,
              (SELECT COUNT(*) FROM pipeline_jobs WHERE status IN ('pending', 'running')) AS backlog_size
            """
        ).fetchone()
        return {key: int(row[key] or 0) for key in row.keys()}

    def draft_translation_count(self) -> int:
        row = self.conn.execute(
            """
            SELECT COUNT(*) AS count FROM translation_blocks
            WHERE draft_translation IS NOT NULL AND draft_translation != ''
            """
        ).fetchone()
        return int(row["count"] or 0)

    def total_block_count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) AS count FROM translation_blocks").fetchone()
        return int(row["count"] or 0)

    def upsert_reference_chapter(self, chapter_id: int, path: str, text: str, text_hash: str) -> None:
        now = utc_now()
        self.conn.execute(
            """
            INSERT INTO reference_chapters(chapter_id, path, text, text_hash, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(chapter_id) DO UPDATE SET
                path = excluded.path,
                text = excluded.text,
                text_hash = excluded.text_hash,
                updated_at = excluded.updated_at
            """,
            (chapter_id, path, text, text_hash, now, now),
        )
        self.conn.commit()

    def list_reference_chapters(self) -> list[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM reference_chapters ORDER BY chapter_id").fetchall()

    def get_reference_chapter(self, chapter_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM reference_chapters WHERE chapter_id = ?",
            (chapter_id,),
        ).fetchone()

    def insert_reference_example(self, chapter_id: int, reference_excerpt: str, source_excerpt: str | None = None, tags: str | None = None) -> None:
        self.conn.execute(
            """
            INSERT INTO reference_examples(chapter_id, source_excerpt, reference_excerpt, tags, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (chapter_id, source_excerpt, reference_excerpt, tags, utc_now()),
        )
        self.conn.commit()

    def list_reference_examples(self, limit: int = 20) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM reference_examples ORDER BY example_id DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def save_glossary_terms(self, path: str, terms: list[dict[str, Any]], status: str = "approved") -> int:
        now = utc_now()
        cur = self.conn.execute(
            "INSERT INTO glossary_versions(path, status, created_at) VALUES (?, ?, ?)",
            (path, status, now),
        )
        version = int(cur.lastrowid)
        for term in terms:
            self.conn.execute(
                """
                INSERT INTO glossary_terms(
                    glossary_version, source_term, translation, category, status, priority, notes, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version,
                    term["source"],
                    term["translation"],
                    term.get("category"),
                    term.get("status", status),
                    term.get("priority"),
                    term.get("notes"),
                    now,
                    now,
                ),
            )
        self.conn.commit()
        return version

    def list_glossary_terms(self, status: str | None = None) -> list[sqlite3.Row]:
        if status:
            return self.conn.execute(
                "SELECT * FROM glossary_terms WHERE status = ? ORDER BY source_term",
                (status,),
            ).fetchall()
        return self.conn.execute("SELECT * FROM glossary_terms ORDER BY source_term").fetchall()

    def add_glossary_term(
        self,
        source_term: str,
        translation: str,
        category: str = "manual",
        status: str = "approved",
        priority: str = "high",
        notes: str | None = None,
    ) -> int:
        latest = self.conn.execute("SELECT MAX(version) AS version FROM glossary_versions").fetchone()
        version = latest["version"] or None
        now = utc_now()
        cur = self.conn.execute(
            """
            INSERT INTO glossary_terms(
                glossary_version, source_term, translation, category, status, priority, notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (version, source_term, translation, category, status, priority, notes, now, now),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def update_glossary_term_status(self, term_id: int, status: str) -> None:
        self.conn.execute(
            "UPDATE glossary_terms SET status = ?, updated_at = ? WHERE term_id = ?",
            (status, utc_now(), term_id),
        )
        self.conn.commit()

    def list_edit_history(self, block_id: str | None = None, limit: int = 200) -> list[sqlite3.Row]:
        if block_id:
            return self.conn.execute(
                "SELECT * FROM edit_history WHERE block_id = ? ORDER BY edit_id DESC LIMIT ?",
                (block_id, limit),
            ).fetchall()
        return self.conn.execute(
            "SELECT * FROM edit_history ORDER BY edit_id DESC LIMIT ?",
            (limit,),
        ).fetchall()

    def list_logs(self, limit: int = 200) -> list[sqlite3.Row]:
        return self.recent_events(limit)
