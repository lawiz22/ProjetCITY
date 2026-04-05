"""Full backup service: export/import DB data + all photos in a single ZIP."""
from __future__ import annotations

import io
import json
import os
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Generator

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
IMAGES_ROOT = PROJECT_ROOT / "static" / "images"

# Photo entity configs: entity_type → (photo_table, fk_col, slug_col, entity_table, image_subdir)
_PHOTO_ENTITIES = {
    "city":     ("dim_city_photo",     "city_id",     "city_slug",     "dim_city",     "cities"),
    "event":    ("dim_event_photo",    "event_id",    "event_slug",    "dim_event",    "events"),
    "person":   ("dim_person_photo",   "person_id",   "person_slug",   "dim_person",   "persons"),
    "monument": ("dim_monument_photo", "monument_id", "monument_slug", "dim_monument", "monuments"),
    "country":  ("dim_country_photo",  "country_id",  "country_slug",  "dim_country",  "countries"),
    "region":   ("dim_region_photo",   "region_id",   "region_slug",   "dim_region",   "regions"),    "legend":   ("dim_legend_photo",    "legend_id",   "legend_slug",   "dim_legend",   "legends"),}


def _serialize_value(value: object) -> object:
    """Make a value JSON-serialisable."""
    if value is None or isinstance(value, (int, float, str, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        import base64
        return {"__bytes__": base64.b64encode(value).decode()}
    return str(value)


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

def _collect_photo_files(conn: Any) -> list[tuple[str, str, str]]:
    """Return list of (entity_type, slug, filename) for every photo on disk.

    Only files referenced in the DB are included.
    """
    results: list[tuple[str, str, str]] = []
    for etype, (photo_tbl, fk_col, slug_col, entity_tbl, subdir) in _PHOTO_ENTITIES.items():
        rows = conn.execute(
            f"SELECT e.{slug_col} AS slug, p.filename "
            f"FROM {photo_tbl} p "
            f"JOIN {entity_tbl} e ON e.{fk_col} = p.{fk_col}"
        ).fetchall()
        for r in rows:
            slug = r["slug"] if hasattr(r, "__getitem__") and isinstance(r["slug"], str) else r[0]
            fname = r["filename"] if hasattr(r, "__getitem__") and isinstance(r["filename"], str) else r[1]
            filepath = IMAGES_ROOT / subdir / slug / fname
            if filepath.is_file():
                results.append((subdir, slug, fname))
    return results


def export_full_backup_streaming(conn: Any, backup_tables: list[dict], scope_groups: set[str]) -> Generator[bytes, None, None]:
    """Stream a ZIP file containing db.json + all photos.

    Yields raw bytes suitable for a streaming HTTP response.
    """
    # We build in-memory because zipfile needs seekable for streaming —
    # but for a full project backup we accept this tradeoff.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Build db.json (same format as existing backup export)
        db_data: dict[str, Any] = {
            "_meta": {
                "exported_at": datetime.utcnow().isoformat(),
                "backend": "postgresql",
                "scope": "all",
                "scope_label": "Backup complet (BD + Photos)",
                "is_delta": False,
                "version": 2,
                "includes_photos": True,
            },
            "tables": {},
        }

        total_rows = 0
        for tdef in backup_tables:
            if tdef.get("group") not in scope_groups:
                continue
            tbl = tdef["name"]
            rows = conn.execute(f"SELECT * FROM {tbl} ORDER BY {tdef['pk']}").fetchall()
            serialized = []
            for row in rows:
                rec = {col: _serialize_value(val) for col, val in dict(row).items()}
                serialized.append(rec)
            db_data["tables"][tbl] = serialized
            total_rows += len(serialized)

        db_data["_meta"]["total_rows"] = total_rows
        zf.writestr("db.json", json.dumps(db_data, ensure_ascii=False, indent=1))

        # 2. Add all photos
        photo_files = _collect_photo_files(conn)
        for subdir, slug, fname in photo_files:
            file_path = IMAGES_ROOT / subdir / slug / fname
            arcname = f"photos/{subdir}/{slug}/{fname}"
            zf.write(str(file_path), arcname)

    buf.seek(0)
    # Yield in chunks
    while True:
        chunk = buf.read(65536)
        if not chunk:
            break
        yield chunk


def export_entity_photos_zip(conn: Any, entity_type: str) -> io.BytesIO | None:
    """Export ALL photos for a given entity type in one ZIP.

    ZIP structure:
      - db.json          → entity rows + photo rows (for re-import)
      - {slug}/file.jpg  → actual photo files
      - manifest.json    → legacy metadata index
    """
    cfg = _PHOTO_ENTITIES.get(entity_type)
    if cfg is None:
        return None

    photo_tbl, fk_col, slug_col, entity_tbl, subdir = cfg

    # Fetch photo rows joined with entity slug
    rows = conn.execute(
        f"SELECT e.{slug_col} AS slug, p.* "
        f"FROM {photo_tbl} p "
        f"JOIN {entity_tbl} e ON e.{fk_col} = p.{fk_col} "
        f"ORDER BY e.{slug_col}, p.filename"
    ).fetchall()

    if not rows:
        return None

    # Fetch entity dimension rows (only those that have photos)
    entity_ids = list({dict(r)[fk_col] for r in rows})
    placeholders = ",".join("?" for _ in entity_ids)
    entity_rows = conn.execute(
        f"SELECT * FROM {entity_tbl} WHERE {fk_col} IN ({placeholders})",
        entity_ids,
    ).fetchall()

    buf = io.BytesIO()
    manifest: dict[str, list[dict]] = {}

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Build db.json with entity + photo table data
        db_data = {
            "_meta": {
                "exported_at": datetime.utcnow().isoformat(),
                "entity_type": entity_type,
                "scope": f"photos-{entity_type}",
                "version": 2,
                "includes_photos": True,
            },
            "tables": {
                entity_tbl: [
                    {col: _serialize_value(val) for col, val in dict(er).items()}
                    for er in entity_rows
                ],
                photo_tbl: [],
            },
        }

        for row in rows:
            rec = dict(row)
            slug = rec.pop("slug", "")
            fname = rec.get("filename", "")

            # Add photo DB row (without the extra 'slug' column)
            db_data["tables"][photo_tbl].append(
                {col: _serialize_value(val) for col, val in rec.items()}
            )

            # Add photo file to ZIP
            file_path = IMAGES_ROOT / subdir / slug / fname
            if file_path.is_file():
                arcname = f"photos/{subdir}/{slug}/{fname}"
                zf.write(str(file_path), arcname)

            # Legacy manifest
            meta = {
                "filename": fname,
                "caption": rec.get("caption", "") or "",
                "source_url": rec.get("source_url", "") or "",
                "attribution": rec.get("attribution", "") or "",
                "is_primary": bool(rec.get("is_primary", False)),
            }
            if "photo_order" in rec:
                meta["photo_order"] = rec["photo_order"]
            manifest.setdefault(slug, []).append(meta)

        zf.writestr("db.json", json.dumps(db_data, ensure_ascii=False, indent=1))
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------

def import_full_backup(conn: Any, zip_data: bytes, backup_tables: list[dict],
                       reset_sequences_fn) -> Generator[dict, None, None]:
    """Import a full backup ZIP (db.json + photos).

    Yields progress events (same format as the existing streaming import).
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_data), "r")
    except zipfile.BadZipFile:
        yield {"type": "error", "message": "Fichier ZIP invalide."}
        return

    # 1. Read db.json
    if "db.json" not in zf.namelist():
        yield {"type": "error", "message": "db.json manquant dans le ZIP."}
        return

    try:
        db_data = json.loads(zf.read("db.json"))
    except (json.JSONDecodeError, KeyError) as exc:
        yield {"type": "error", "message": f"db.json invalide: {exc}"}
        return

    tables_data = db_data.get("tables", {})

    # 2. Import DB tables (same logic as existing streaming import)
    total_inserted = 0
    for tdef in backup_tables:
        tbl = tdef["name"]
        rows = tables_data.get(tbl, [])
        if not rows:
            yield {"type": "table_skip", "table": tbl}
            continue

        yield {"type": "table_start", "table": tbl, "row_count": len(rows)}

        conflict_clause = ""
        if tdef.get("conflict"):
            conflict_clause = f" ON CONFLICT {tdef['conflict']} DO NOTHING"

        inserted = 0
        for idx, row in enumerate(rows):
            # Deserialize __bytes__
            for k, v in row.items():
                if isinstance(v, dict) and "__bytes__" in v:
                    import base64
                    row[k] = base64.b64decode(v["__bytes__"])

            cols = list(row.keys())
            placeholders = ", ".join("?" for _ in cols)
            col_list = ", ".join(cols)
            sql = f"INSERT INTO {tbl} ({col_list}) VALUES ({placeholders}){conflict_clause}"

            sp_name = f"sp_{tbl}_{idx}"
            try:
                conn.execute(f"SAVEPOINT {sp_name}")
                cur = conn.execute(sql, list(row.values()))
                if hasattr(cur, "rowcount") and cur.rowcount > 0:
                    inserted += 1
                conn.execute(f"RELEASE SAVEPOINT {sp_name}")
            except Exception:
                try:
                    conn.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")
                except Exception:
                    pass

        total_inserted += inserted
        yield {"type": "table_done", "table": tbl, "inserted": inserted, "row_count": len(rows)}

    conn.commit()

    # 3. Reset sequences
    try:
        reset_sequences_fn(conn)
    except Exception:
        pass

    # 4. Import photos from ZIP
    photo_count = 0
    photo_names = [n for n in zf.namelist() if n.startswith("photos/") and not n.endswith("/")]

    # Diagnostic: check if IMAGES_ROOT is a symlink to the volume
    is_symlink = IMAGES_ROOT.is_symlink()
    resolved = str(IMAGES_ROOT.resolve())
    yield {"type": "photos_diag", "images_root": str(IMAGES_ROOT), "is_symlink": is_symlink, "resolved_to": resolved}

    if photo_names:
        yield {"type": "photos_start", "count": len(photo_names)}
        for i, arcname in enumerate(photo_names, 1):
            # arcname = photos/cities/montreal-quebec/abc123.jpg
            parts = arcname.split("/")
            if len(parts) < 4:
                continue
            subdir = parts[1]
            slug = parts[2]
            fname = "/".join(parts[3:])

            dest_dir = IMAGES_ROOT / subdir / slug
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / os.path.basename(fname)
            # Always write (overwrite) — previous imports may have written
            # to ephemeral container disk instead of the persistent volume
            dest.write_bytes(zf.read(arcname))
            photo_count += 1

            yield {
                "type": "photo_progress",
                "current": i,
                "total": len(photo_names),
                "file": f"{subdir}/{slug}/{os.path.basename(fname)}",
                "written": True,
            }

        yield {"type": "photos_done", "imported": photo_count, "total": len(photo_names)}

    zf.close()

    yield {
        "type": "summary",
        "message": f"Import terminé: {total_inserted} ligne(s) BD, {photo_count} photo(s) importée(s).",
        "inserted": total_inserted,
        "photos": photo_count,
    }
