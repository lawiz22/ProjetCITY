"""Migrate existing photos from manifest.json to dim_city_photo table + per-city dirs."""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "data" / "city_analysis.db"
PHOTO_DIR = PROJECT_ROOT / "static" / "images" / "cities"
MANIFEST = PHOTO_DIR / "manifest.json"


def migrate():
    if not MANIFEST.exists():
        print("No manifest.json found — nothing to migrate.")
        return

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not manifest:
        print("Manifest is empty.")
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    migrated = 0
    skipped = 0

    for slug, payload in manifest.items():
        filename = payload.get("filename")
        if not filename:
            continue

        # Look up city_id
        row = conn.execute(
            "SELECT city_id FROM dim_city WHERE city_slug = ?", (slug,)
        ).fetchone()
        if not row:
            print(f"  SKIP {slug}: city not found in DB")
            skipped += 1
            continue
        city_id = row["city_id"]

        # Check if already migrated
        existing = conn.execute(
            "SELECT photo_id FROM dim_city_photo WHERE city_id = ? LIMIT 1", (city_id,)
        ).fetchone()
        if existing:
            skipped += 1
            continue

        # Source file
        src = PHOTO_DIR / filename
        if not src.exists():
            print(f"  SKIP {slug}: file {filename} not found on disk")
            skipped += 1
            continue

        # Create per-city directory and copy
        dest_dir = PHOTO_DIR / slug
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename
        shutil.copy2(str(src), str(dest))

        # Insert into DB
        conn.execute(
            """INSERT INTO dim_city_photo
               (city_id, filename, caption, source_url, attribution, is_primary)
               VALUES (?, ?, ?, ?, ?, 1)""",
            (
                city_id,
                filename,
                "",
                payload.get("source_page", ""),
                payload.get("attribution", ""),
            ),
        )
        migrated += 1

    conn.commit()
    conn.close()
    print(f"Migration complete: {migrated} photos migrated, {skipped} skipped.")


if __name__ == "__main__":
    migrate()
