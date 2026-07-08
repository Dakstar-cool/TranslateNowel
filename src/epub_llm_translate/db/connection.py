from __future__ import annotations

from pathlib import Path
import sqlite3

from .migrations import migrate


def connect(path: str | Path) -> sqlite3.Connection:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def initialize_database(path: str | Path) -> sqlite3.Connection:
    conn = connect(path)
    migrate(conn)
    return conn

