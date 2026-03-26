from __future__ import annotations

import sqlite3

from flask import current_app, g


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        connection = sqlite3.connect(current_app.config["DATABASE_PATH"])
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON;")
        g.db = connection
    return g.db


def close_db(_error: Exception | None = None) -> None:
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def run_migrations(db_path: str) -> None:
    """Apply lightweight schema migrations (add missing columns)."""
    conn = sqlite3.connect(db_path)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(dim_annotation)")}
        if "photo_filename" not in cols:
            conn.execute("ALTER TABLE dim_annotation ADD COLUMN photo_filename TEXT")
        if "photo_source_url" not in cols:
            conn.execute("ALTER TABLE dim_annotation ADD COLUMN photo_source_url TEXT")
        conn.commit()
    finally:
        conn.close()