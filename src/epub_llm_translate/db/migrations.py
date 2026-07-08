from __future__ import annotations

import sqlite3


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chapters (
    chapter_id INTEGER PRIMARY KEY,
    title TEXT,
    href TEXT,
    spine_index INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    block_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS translation_blocks (
    block_id TEXT PRIMARY KEY,
    chapter_id INTEGER NOT NULL,
    block_index INTEGER NOT NULL,
    paragraph_index INTEGER,
    source_text TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    draft_translation TEXT,
    human_draft_edit TEXT,
    revised_translation TEXT,
    human_final_edit TEXT,
    status TEXT NOT NULL,
    quality_status TEXT,
    glossary_version INTEGER,
    draft_model TEXT,
    revision_model TEXT,
    locked_by TEXT,
    locked_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(chapter_id) REFERENCES chapters(chapter_id)
);

CREATE INDEX IF NOT EXISTS idx_translation_blocks_chapter
    ON translation_blocks(chapter_id, block_index);

CREATE TABLE IF NOT EXISTS quality_issues (
    issue_id INTEGER PRIMARY KEY AUTOINCREMENT,
    block_id TEXT NOT NULL,
    chapter_id INTEGER NOT NULL,
    paragraph_index INTEGER NOT NULL,
    issue_type TEXT NOT NULL,
    issue_severity TEXT NOT NULL,
    source_term TEXT,
    expected_translation TEXT,
    actual_translation TEXT,
    target_text TEXT,
    char_start INTEGER,
    char_end INTEGER,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(block_id) REFERENCES translation_blocks(block_id)
);

CREATE INDEX IF NOT EXISTS idx_quality_issues_status
    ON quality_issues(status, issue_severity, chapter_id, paragraph_index);

CREATE TABLE IF NOT EXISTS edit_history (
    edit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    block_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    old_text TEXT,
    new_text TEXT,
    edited_by TEXT NOT NULL,
    edit_reason TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(block_id) REFERENCES translation_blocks(block_id)
);

CREATE TABLE IF NOT EXISTS pipeline_jobs (
    job_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_type TEXT NOT NULL,
    block_id TEXT,
    chapter_id INTEGER,
    status TEXT NOT NULL,
    priority INTEGER DEFAULT 0,
    payload_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pipeline_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    payload_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS glossary_versions (
    version INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS glossary_terms (
    term_id INTEGER PRIMARY KEY AUTOINCREMENT,
    glossary_version INTEGER,
    source_term TEXT NOT NULL,
    translation TEXT NOT NULL,
    category TEXT,
    status TEXT NOT NULL,
    priority TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(glossary_version) REFERENCES glossary_versions(version)
);

CREATE TABLE IF NOT EXISTS reference_chapters (
    chapter_id INTEGER PRIMARY KEY,
    path TEXT NOT NULL,
    text TEXT NOT NULL,
    text_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reference_examples (
    example_id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER,
    source_excerpt TEXT,
    reference_excerpt TEXT NOT NULL,
    tags TEXT,
    created_at TEXT NOT NULL
);
"""


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()

