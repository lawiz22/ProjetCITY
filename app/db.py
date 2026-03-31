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

        # Region tables (created if missing)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dim_region (
                region_id INTEGER PRIMARY KEY AUTOINCREMENT,
                region_name TEXT NOT NULL,
                region_slug TEXT NOT NULL UNIQUE,
                country_name TEXT NOT NULL,
                region_color TEXT,
                source_file TEXT NOT NULL DEFAULT 'manual'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS fact_region_population (
                region_pop_id INTEGER PRIMARY KEY AUTOINCREMENT,
                region_id INTEGER NOT NULL,
                time_id INTEGER NOT NULL,
                year INTEGER NOT NULL,
                population INTEGER NOT NULL,
                is_key_year INTEGER NOT NULL DEFAULT 0 CHECK (is_key_year IN (0, 1)),
                annotation_id INTEGER,
                source_file TEXT NOT NULL DEFAULT 'manual',
                UNIQUE(region_id, year),
                FOREIGN KEY (region_id) REFERENCES dim_region(region_id),
                FOREIGN KEY (time_id) REFERENCES dim_time(time_id),
                FOREIGN KEY (annotation_id) REFERENCES dim_annotation(annotation_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dim_region_period_detail (
                region_period_id INTEGER PRIMARY KEY AUTOINCREMENT,
                region_id INTEGER NOT NULL,
                period_order INTEGER NOT NULL,
                period_range_label TEXT NOT NULL,
                period_title TEXT NOT NULL,
                start_year INTEGER,
                end_year INTEGER,
                start_time_id INTEGER,
                end_time_id INTEGER,
                summary_text TEXT NOT NULL,
                source_file TEXT NOT NULL,
                UNIQUE(region_id, period_order),
                FOREIGN KEY (region_id) REFERENCES dim_region(region_id),
                FOREIGN KEY (start_time_id) REFERENCES dim_time(time_id),
                FOREIGN KEY (end_time_id) REFERENCES dim_time(time_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dim_region_period_detail_item (
                item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                region_period_id INTEGER NOT NULL,
                item_order INTEGER NOT NULL,
                item_text TEXT NOT NULL,
                FOREIGN KEY (region_period_id) REFERENCES dim_region_period_detail(region_period_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS dim_region_photo (
                photo_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                region_id  INTEGER NOT NULL REFERENCES dim_region(region_id) ON DELETE CASCADE,
                filename   TEXT NOT NULL,
                caption    TEXT,
                source_url TEXT,
                attribution TEXT,
                is_primary INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
    finally:
        conn.close()