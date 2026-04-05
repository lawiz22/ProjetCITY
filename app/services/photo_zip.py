"""Export and import photo libraries as ZIP archives."""
from __future__ import annotations

import io
import json
import os
import uuid
import zipfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Entity type → (photo_table, id_column, fk_column, photo_id_column, slug_column, entity_table, photo_dir)
ENTITY_CONFIG: dict[str, dict[str, str]] = {
    "city": {
        "photo_table": "dim_city_photo",
        "photo_id_col": "photo_id",
        "fk_col": "city_id",
        "entity_table": "dim_city",
        "slug_col": "city_slug",
        "photo_dir": "static/images/cities",
    },
    "event": {
        "photo_table": "dim_event_photo",
        "photo_id_col": "event_photo_id",
        "fk_col": "event_id",
        "entity_table": "dim_event",
        "slug_col": "event_slug",
        "photo_dir": "static/images/events",
    },
    "person": {
        "photo_table": "dim_person_photo",
        "photo_id_col": "person_photo_id",
        "fk_col": "person_id",
        "entity_table": "dim_person",
        "slug_col": "person_slug",
        "photo_dir": "static/images/persons",
    },
    "country": {
        "photo_table": "dim_country_photo",
        "photo_id_col": "photo_id",
        "fk_col": "country_id",
        "entity_table": "dim_country",
        "slug_col": "country_slug",
        "photo_dir": "static/images/countries",
    },
    "region": {
        "photo_table": "dim_region_photo",
        "photo_id_col": "photo_id",
        "fk_col": "region_id",
        "entity_table": "dim_region",
        "slug_col": "region_slug",
        "photo_dir": "static/images/regions",
    },
    "monument": {
        "photo_table": "dim_monument_photo",
        "photo_id_col": "monument_photo_id",
        "fk_col": "monument_id",
        "entity_table": "dim_monument",
        "slug_col": "monument_slug",
        "photo_dir": "static/images/monuments",
    },
    "legend": {
        "photo_table": "dim_legend_photo",
        "photo_id_col": "legend_photo_id",
        "fk_col": "legend_id",
        "entity_table": "dim_legend",
        "slug_col": "legend_slug",
        "photo_dir": "static/images/legends",
    },
}

# Metadata fields to export (common across all photo tables)
_META_FIELDS = ("filename", "caption", "source_url", "attribution", "is_primary", "photo_order", "image_url")


def export_photos_zip(conn: Any, entity_type: str, entity_slug: str) -> io.BytesIO | None:
    """Build a ZIP containing all photos + metadata JSON for a given entity.

    Returns a BytesIO buffer ready to be sent as a download, or None if no photos.
    """
    cfg = ENTITY_CONFIG.get(entity_type)
    if cfg is None:
        return None

    # Resolve entity id
    cur = conn.execute(
        f"SELECT {cfg['fk_col']} FROM {cfg['entity_table']} WHERE {cfg['slug_col']} = %s",
        (entity_slug,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    entity_id = row[0]

    # Fetch photo records
    has_photo_order = entity_type not in ("city", "country", "region")
    order_clause = f"photo_order, {cfg['photo_id_col']}" if has_photo_order else cfg["photo_id_col"]
    cur = conn.execute(
        f"SELECT * FROM {cfg['photo_table']} WHERE {cfg['fk_col']} = %s ORDER BY {order_clause}",
        (entity_id,),
    )
    photos = cur.fetchall()
    if not photos:
        return None

    photo_dir = PROJECT_ROOT / cfg["photo_dir"] / entity_slug
    buf = io.BytesIO()
    manifest: list[dict[str, Any]] = []

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for photo in photos:
            rec = dict(photo.items())
            filename = rec.get("filename", "")
            file_path = photo_dir / filename
            if not file_path.is_file():
                continue
            # Add file to ZIP
            zf.write(file_path, filename)
            # Build metadata entry
            meta: dict[str, Any] = {}
            for field in _META_FIELDS:
                if field in rec:
                    val = rec[field]
                    meta[field] = val
            manifest.append(meta)

        # Write manifest
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    buf.seek(0)
    return buf


ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def import_photos_zip(conn: Any, entity_type: str, entity_slug: str, zip_data: bytes) -> dict[str, Any]:
    """Import photos from a ZIP archive into an entity's photo library.

    The ZIP should contain image files and an optional manifest.json with metadata.
    Returns {"success": True, "imported": N} or {"success": False, "error": "..."}.
    """
    cfg = ENTITY_CONFIG.get(entity_type)
    if cfg is None:
        return {"success": False, "error": f"Type d'entité inconnu : {entity_type}"}

    # Resolve entity id
    cur = conn.execute(
        f"SELECT {cfg['fk_col']} FROM {cfg['entity_table']} WHERE {cfg['slug_col']} = %s",
        (entity_slug,),
    )
    row = cur.fetchone()
    if row is None:
        return {"success": False, "error": "Entité introuvable."}
    entity_id = row[0]

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_data), "r")
    except zipfile.BadZipFile:
        return {"success": False, "error": "Fichier ZIP invalide."}

    # Read manifest if present
    manifest_map: dict[str, dict[str, Any]] = {}
    if "manifest.json" in zf.namelist():
        try:
            manifest = json.loads(zf.read("manifest.json"))
            for entry in manifest:
                fn = entry.get("filename", "")
                if fn:
                    manifest_map[fn] = entry
        except (json.JSONDecodeError, KeyError):
            pass  # proceed without metadata

    photo_dir = PROJECT_ROOT / cfg["photo_dir"] / entity_slug
    photo_dir.mkdir(parents=True, exist_ok=True)

    # Current max photo_order (for entity types that support it)
    has_photo_order = entity_type not in ("city", "country", "region")
    next_order = 0
    if has_photo_order:
        cur = conn.execute(
            f"SELECT COALESCE(MAX(photo_order), -1) FROM {cfg['photo_table']} WHERE {cfg['fk_col']} = %s",
            (entity_id,),
        )
        max_order_row = cur.fetchone()
        next_order = max_order_row[0] + 1

    imported = 0

    for name in zf.namelist():
        if name == "manifest.json":
            continue
        # Security: only allow plain filenames, no path traversal
        basename = os.path.basename(name)
        if not basename:
            continue
        ext = os.path.splitext(basename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            continue

        data = zf.read(name)
        if not data:
            continue

        # Generate unique filename
        new_filename = uuid.uuid4().hex[:12] + ext
        dest = photo_dir / new_filename
        dest.write_bytes(data)
        from app.services.city_photos import generate_thumbnail
        generate_thumbnail(dest)

        # Metadata from manifest
        meta = manifest_map.get(basename, {})
        caption = meta.get("caption", "") or ""
        source_url = meta.get("source_url", "") or ""
        attribution = meta.get("attribution", "") or ""
        is_primary = bool(meta.get("is_primary", False))

        # If setting as primary, unset existing primary first
        if is_primary:
            conn.execute(
                f"UPDATE {cfg['photo_table']} SET is_primary = FALSE WHERE {cfg['fk_col']} = %s AND is_primary = TRUE",
                (entity_id,),
            )

        # Insert DB record
        if has_photo_order:
            conn.execute(
                f"""INSERT INTO {cfg['photo_table']} ({cfg['fk_col']}, filename, caption, source_url, attribution, is_primary, photo_order)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (entity_id, new_filename, caption, source_url, attribution, is_primary, next_order),
            )
            next_order += 1
        else:
            conn.execute(
                f"""INSERT INTO {cfg['photo_table']} ({cfg['fk_col']}, filename, caption, source_url, attribution, is_primary)
                    VALUES (%s, %s, %s, %s, %s, %s)""",
                (entity_id, new_filename, caption, source_url, attribution, is_primary),
            )

        imported += 1

    conn.commit()
    zf.close()
    return {"success": True, "imported": imported}
