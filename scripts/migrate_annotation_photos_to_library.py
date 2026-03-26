"""Migrate existing annotation photos into the city photo library (dim_city_photo)."""
import re
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.city_photos import (
    ANNOTATION_PHOTO_DIR,
    extract_exif,
    save_photo_to_library,
)

DB_PATH = PROJECT_ROOT / "data" / "city_analysis.db"


def main():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Find all annotations with photos, joined to their city
    rows = conn.execute("""
        SELECT DISTINCT
            da.annotation_id,
            da.annotation_label,
            da.photo_filename,
            da.photo_source_url,
            dc.city_id,
            dc.city_slug
        FROM dim_annotation da
        JOIN fact_city_population fcp ON fcp.annotation_id = da.annotation_id
        JOIN dim_city dc ON dc.city_id = fcp.city_id
        WHERE da.photo_filename IS NOT NULL AND da.photo_filename != ''
    """).fetchall()

    if not rows:
        # Try alternative join via view
        rows = conn.execute("""
            SELECT DISTINCT
                da.annotation_id,
                da.annotation_label,
                da.photo_filename,
                da.photo_source_url,
                v.city_id,
                v.city_slug
            FROM dim_annotation da
            JOIN vw_city_population_analysis v ON v.annotation_id = da.annotation_id
            WHERE da.photo_filename IS NOT NULL AND da.photo_filename != ''
        """).fetchall()

    print(f"Found {len(rows)} annotation-photo/city pairs to migrate")

    migrated = 0
    skipped = 0
    errors = 0

    for row in rows:
        ann_id = row["annotation_id"]
        label = row["annotation_label"]
        photo_filename = row["photo_filename"]
        source_url = row["photo_source_url"] or ""
        city_id = row["city_id"]
        city_slug = row["city_slug"]

        # Check if file exists
        photo_path = ANNOTATION_PHOTO_DIR / photo_filename
        if not photo_path.exists():
            print(f"  SKIP  ann#{ann_id} ({city_slug}) - file missing: {photo_filename}")
            skipped += 1
            continue

        # Check if already in library (avoid duplicates by checking source_url or caption)
        clean_label = re.sub(r'[\U00010000-\U0010ffff]', '', label).strip()
        existing = conn.execute(
            "SELECT photo_id FROM dim_city_photo WHERE city_id = ? AND caption = ?",
            (city_id, clean_label),
        ).fetchone()
        if existing:
            print(f"  EXIST ann#{ann_id} ({city_slug}) - already in library: {clean_label[:50]}")
            skipped += 1
            continue

        # Read file and add to library
        file_bytes = photo_path.read_bytes()
        ext = Path(photo_filename).suffix

        try:
            result = save_photo_to_library(
                conn,
                city_id=city_id,
                city_slug=city_slug,
                file_bytes=file_bytes,
                original_filename=f"annotation{ext}",
                source_url=source_url,
                attribution="Wikimedia Commons",
                caption=clean_label,
            )
            if result.get("success"):
                print(f"  OK    ann#{ann_id} ({city_slug}) -> photo#{result['photo_id']}: {clean_label[:50]}")
                migrated += 1
            else:
                print(f"  ERR   ann#{ann_id} ({city_slug}): {result.get('error')}")
                errors += 1
        except Exception as e:
            print(f"  ERR   ann#{ann_id} ({city_slug}): {e}")
            errors += 1

    print(f"\nDone: {migrated} migrated, {skipped} skipped, {errors} errors")
    conn.close()


if __name__ == "__main__":
    main()
