"""One-time script: create dim_country_photo table in the live DB."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import create_app
from app.db import get_db

app = create_app()
with app.app_context():
    conn = get_db()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS dim_country_photo (
            photo_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            country_id INTEGER NOT NULL REFERENCES dim_country(country_id) ON DELETE CASCADE,
            filename   TEXT NOT NULL,
            caption    TEXT,
            source_url TEXT,
            attribution TEXT,
            is_primary INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_country_photo_country ON dim_country_photo (country_id)"
    )
    conn.commit()
    print("dim_country_photo table created.")
