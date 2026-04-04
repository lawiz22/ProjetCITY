"""Service for monuments: parse, import, CRUD, photos."""
from __future__ import annotations

import re
import unicodedata
import uuid
from pathlib import Path
from typing import Any

from flask import g


def _current_user_id() -> int | None:
    """Return the logged-in user's id, or None."""
    user = getattr(g, "user", None)
    return user["user_id"] if user else None

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MONUMENT_PHOTO_DIR = PROJECT_ROOT / "static" / "images" / "monuments"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

MONUMENT_CATEGORIES = [
    "gratte_ciel",
    "hotel",
    "eglise",
    "mairie",
    "musee",
    "stade",
    "pont",
    "monument_historique",
    "gare",
    "theatre",
    "parc",
    "autre",
]

CATEGORY_LABELS = {
    "gratte_ciel": "Gratte-ciel",
    "hotel": "Hôtel",
    "eglise": "Église / Lieu de culte",
    "mairie": "Hôtel de ville / Mairie",
    "musee": "Musée",
    "stade": "Stade / Aréna",
    "pont": "Pont",
    "monument_historique": "Monument historique",
    "gare": "Gare / Station",
    "theatre": "Théâtre / Salle de spectacle",
    "parc": "Parc / Jardin",
    "autre": "Autre",
}

CATEGORY_EMOJIS = {
    "gratte_ciel": "🏙️",
    "hotel": "🏨",
    "eglise": "⛪",
    "mairie": "🏛️",
    "musee": "🖼️",
    "stade": "🏟️",
    "pont": "🌉",
    "monument_historique": "🏰",
    "gare": "🚉",
    "theatre": "🎭",
    "parc": "🌳",
    "autre": "📌",
}

LOCATION_ROLES = ["primary", "secondary"]


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", normalized.strip().lower())
    return normalized.strip("-")


# ---------------------------------------------------------------------------
# Parse AI-generated monument text
# ---------------------------------------------------------------------------

def parse_monument_text(text: str) -> dict[str, Any]:
    """Parse structured AI-generated monument text into a dict.

    Expected format::

        MONUMENT_NAME = "Empire State Building"
        CONSTRUCTION_DATE = "1931-04-11"
        INAUGURATION_DATE = "1931-05-01"
        CONSTRUCTION_YEAR = 1931
        DEMOLITION_YEAR =
        ARCHITECT = "Shreve, Lamb and Harmon"
        ARCHITECTURAL_STYLE = "Art déco"
        HEIGHT_METERS = 443
        FLOORS = 102
        MONUMENT_LEVEL = 1
        MONUMENT_CATEGORY = "gratte_ciel"

        === RÉSUMÉ ===
        Court résumé...

        === DESCRIPTION ===
        Description détaillée...

        === HISTOIRE ===
        Histoire...

        === SIGNIFICATION ===
        Signification et importance...

        === LIEUX ===
        New York, New York, États-Unis, primary
    """
    result: dict[str, Any] = {
        "monument_name": "",
        "monument_slug": "",
        "construction_date": None,
        "inauguration_date": None,
        "construction_year": None,
        "demolition_year": None,
        "architect": None,
        "architectural_style": None,
        "height_meters": None,
        "floors": None,
        "monument_level": 2,
        "monument_category": "autre",
        "latitude": None,
        "longitude": None,
        "summary": "",
        "description": "",
        "history": "",
        "significance": "",
        "locations": [],
    }

    # Extract key=value fields
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r'^MONUMENT_NAME\s*=\s*"(.+)"\s*$', line) or \
            re.match(r"^MONUMENT_NAME\s*=\s*'(.+)'\s*$", line)
        if m:
            result["monument_name"] = m.group(1).strip()
            result["monument_slug"] = slugify(result["monument_name"])
            continue
        m = re.match(r'^CONSTRUCTION_DATE\s*=\s*"(.+?)"\s*$', line) or \
            re.match(r"^CONSTRUCTION_DATE\s*=\s*'(.+?)'\s*$", line)
        if m:
            result["construction_date"] = m.group(1).strip()
            continue
        m = re.match(r'^INAUGURATION_DATE\s*=\s*"(.+?)"\s*$', line) or \
            re.match(r"^INAUGURATION_DATE\s*=\s*'(.+?)'\s*$", line)
        if m:
            result["inauguration_date"] = m.group(1).strip()
            continue
        m = re.match(r'^CONSTRUCTION_YEAR\s*=\s*(-?\d+)', line)
        if m:
            result["construction_year"] = int(m.group(1))
            continue
        m = re.match(r'^DEMOLITION_YEAR\s*=\s*(-?\d+)', line)
        if m:
            result["demolition_year"] = int(m.group(1))
            continue
        m = re.match(r'^ARCHITECT\s*=\s*"(.+?)"\s*$', line) or \
            re.match(r"^ARCHITECT\s*=\s*'(.+?)'\s*$", line)
        if m:
            result["architect"] = m.group(1).strip()
            continue
        m = re.match(r'^ARCHITECTURAL_STYLE\s*=\s*"(.+?)"\s*$', line) or \
            re.match(r"^ARCHITECTURAL_STYLE\s*=\s*'(.+?)'\s*$", line)
        if m:
            result["architectural_style"] = m.group(1).strip()
            continue
        m = re.match(r'^HEIGHT_METERS\s*=\s*([\d.]+)', line)
        if m:
            try:
                result["height_meters"] = float(m.group(1))
            except ValueError:
                pass
            continue
        m = re.match(r'^FLOORS\s*=\s*(\d+)', line)
        if m:
            result["floors"] = int(m.group(1))
            continue
        m = re.match(r'^MONUMENT_LEVEL\s*=\s*(\d)', line)
        if m:
            result["monument_level"] = int(m.group(1))
            continue
        m = re.match(r'^MONUMENT_CATEGORY\s*=\s*"(.+?)"\s*$', line) or \
            re.match(r"^MONUMENT_CATEGORY\s*=\s*'(.+?)'\s*$", line)
        if m:
            cat = m.group(1).strip().lower()
            if cat in MONUMENT_CATEGORIES:
                result["monument_category"] = cat
            continue
        m = re.match(r'^LATITUDE\s*=\s*([\-\d.]+)', line)
        if m:
            try:
                result["latitude"] = float(m.group(1))
            except ValueError:
                pass
            continue
        m = re.match(r'^LONGITUDE\s*=\s*([\-\d.]+)', line)
        if m:
            try:
                result["longitude"] = float(m.group(1))
            except ValueError:
                pass
            continue

    # Extract sections
    sections = re.split(r'===\s*(.+?)\s*===', text)
    for i in range(1, len(sections) - 1, 2):
        header = sections[i].strip().upper()
        body = sections[i + 1].strip()
        if header in ("RÉSUMÉ", "RESUME"):
            result["summary"] = body
        elif header in ("DESCRIPTION",):
            result["description"] = body
        elif header in ("HISTOIRE", "HISTORY"):
            result["history"] = body
        elif header in ("SIGNIFICATION", "SIGNIFICANCE"):
            result["significance"] = body
        elif header in ("LIEUX", "LOCATIONS"):
            for loc_line in body.splitlines():
                loc_line = loc_line.strip()
                if not loc_line or loc_line.startswith("#"):
                    continue
                parts = [p.strip() for p in loc_line.split(",")]
                if len(parts) >= 4:
                    role = parts[-1].lower()
                    if role not in LOCATION_ROLES:
                        role = "primary"
                    result["locations"].append({
                        "city_name": parts[0],
                        "region": parts[1],
                        "country": parts[2],
                        "role": role,
                    })
                elif len(parts) == 3:
                    result["locations"].append({
                        "city_name": parts[0],
                        "region": parts[1],
                        "country": parts[2],
                        "role": "primary",
                    })
                elif len(parts) == 2:
                    result["locations"].append({
                        "city_name": None,
                        "region": parts[0],
                        "country": parts[1],
                        "role": "primary",
                    })

    if not result["monument_name"]:
        raise ValueError("MONUMENT_NAME introuvable dans le texte généré.")

    if len(result["monument_name"]) < 3:
        raise ValueError(
            f"MONUMENT_NAME trop court ({result['monument_name']!r}). "
            "Vérifiez les guillemets dans le texte source."
        )

    return result


# ---------------------------------------------------------------------------
# Import / CRUD
# ---------------------------------------------------------------------------

def import_monument(conn: Any, data: dict[str, Any]) -> int:
    """Upsert a monument into dim_monument and its locations. Returns monument_id."""
    uid = _current_user_id()
    cursor = conn.execute(
        """INSERT INTO dim_monument
           (monument_name, monument_slug,
            construction_date, inauguration_date, construction_year, demolition_year,
            architect, architectural_style, height_meters, floors,
            latitude, longitude,
            monument_level, monument_category,
            summary, description, history, significance,
            source_text,
            created_by_user_id, updated_by_user_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(monument_slug) DO UPDATE SET
               monument_name = excluded.monument_name,
               construction_date = excluded.construction_date,
               inauguration_date = excluded.inauguration_date,
               construction_year = excluded.construction_year,
               demolition_year = excluded.demolition_year,
               architect = excluded.architect,
               architectural_style = excluded.architectural_style,
               height_meters = excluded.height_meters,
               floors = excluded.floors,
               latitude = excluded.latitude,
               longitude = excluded.longitude,
               monument_level = excluded.monument_level,
               monument_category = excluded.monument_category,
               summary = excluded.summary,
               description = excluded.description,
               history = excluded.history,
               significance = excluded.significance,
               source_text = excluded.source_text,
               updated_by_user_id = excluded.updated_by_user_id,
               updated_at = CURRENT_TIMESTAMP
           RETURNING monument_id""",
        (
            data["monument_name"], data["monument_slug"],
            data.get("construction_date"), data.get("inauguration_date"),
            data.get("construction_year"), data.get("demolition_year"),
            data.get("architect"), data.get("architectural_style"),
            data.get("height_meters"), data.get("floors"),
            data.get("latitude"), data.get("longitude"),
            data.get("monument_level", 2),
            data.get("monument_category", "autre"),
            data.get("summary", ""), data.get("description", ""),
            data.get("history", ""), data.get("significance", ""),
            data.get("source_text", ""),
            uid, uid,
        ),
    )
    monument_id = cursor.fetchone()[0]

    # Replace locations
    conn.execute("DELETE FROM dim_monument_location WHERE monument_id = ?", (monument_id,))
    for loc in data.get("locations", []):
        city_id = None
        if loc.get("city_name"):
            row = conn.execute(
                "SELECT city_id FROM dim_city WHERE LOWER(city_name) = LOWER(?) AND country = ?",
                (loc["city_name"], loc.get("country", "")),
            ).fetchone()
            if row:
                city_id = row[0]
        conn.execute(
            """INSERT INTO dim_monument_location (monument_id, city_id, region, country, role)
               VALUES (?, ?, ?, ?, ?)""",
            (monument_id, city_id, loc.get("region"), loc.get("country"), loc.get("role", "primary")),
        )

    conn.commit()
    return monument_id


def get_monument(conn: Any, monument_slug: str) -> dict[str, Any] | None:
    """Load a full monument with locations and photos."""
    row = conn.execute(
        "SELECT * FROM dim_monument WHERE monument_slug = ?", (monument_slug,)
    ).fetchone()
    if not row:
        return None

    monument = dict(row)
    monument_id = monument["monument_id"]

    locs = conn.execute(
        """SELECT ml.*, dc.city_name AS matched_city_name, dc.city_slug AS matched_city_slug
           FROM dim_monument_location ml
           LEFT JOIN dim_city dc ON dc.city_id = ml.city_id
           WHERE ml.monument_id = ?
           ORDER BY ml.role, ml.monument_location_id""",
        (monument_id,),
    ).fetchall()
    monument["locations"] = [dict(l) for l in locs]

    photos = conn.execute(
        """SELECT * FROM dim_monument_photo
           WHERE monument_id = ? ORDER BY is_primary DESC, photo_order, monument_photo_id""",
        (monument_id,),
    ).fetchall()
    monument["photos"] = [
        {**dict(p), "photo_path": f"images/monuments/{monument_slug}/{p['filename']}"}
        for p in photos
    ]

    return monument


def get_monuments_list(conn: Any, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """List monuments with optional filters (category, level, search)."""
    sql = (
        "SELECT vs.*, dm.latitude, dm.longitude,"
        " dm.created_at AS entity_created_at, dm.updated_at AS entity_updated_at,"
        " COALESCE(au_c.display_name, au_c.username) AS created_by_name,"
        " COALESCE(au_u.display_name, au_u.username) AS updated_by_name"
        " FROM vw_monument_summary vs"
        " LEFT JOIN dim_monument dm ON dm.monument_id = vs.monument_id"
        " LEFT JOIN app_user au_c ON au_c.user_id = dm.created_by_user_id"
        " LEFT JOIN app_user au_u ON au_u.user_id = dm.updated_by_user_id"
        " WHERE 1=1"
    )
    params: list[Any] = []
    if filters:
        if filters.get("category"):
            sql += " AND monument_category = ?"
            params.append(filters["category"])
        if filters.get("level"):
            sql += " AND monument_level = ?"
            params.append(int(filters["level"]))
        if filters.get("search"):
            sql += (
                " AND (LOWER(monument_name) LIKE LOWER(?)"
                " OR LOWER(summary) LIKE LOWER(?)"
                " OR LOWER(architect) LIKE LOWER(?)"
                " OR LOWER(location_names) LIKE LOWER(?))"
            )
            q = f"%{filters['search']}%"
            params.extend([q, q, q, q])
    sql += " ORDER BY construction_year DESC NULLS LAST, monument_name"
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_monuments_for_city(conn: Any, city_id: int) -> list[dict[str, Any]]:
    """Get monuments linked to a specific city."""
    rows = conn.execute(
        """SELECT m.monument_id, m.monument_name, m.monument_slug,
                  m.construction_year, m.demolition_year,
                  m.monument_level, m.monument_category,
                  m.architect, m.architectural_style,
                  ml.role
           FROM dim_monument m
           JOIN dim_monument_location ml ON ml.monument_id = m.monument_id
           WHERE ml.city_id = ?
           ORDER BY m.construction_year""",
        (city_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_monument(conn: Any, monument_id: int) -> None:
    """Delete a monument and all related data."""
    row = conn.execute("SELECT monument_slug FROM dim_monument WHERE monument_id = ?", (monument_id,)).fetchone()
    if row:
        photo_dir = MONUMENT_PHOTO_DIR / row[0]
        if photo_dir.exists():
            import shutil
            shutil.rmtree(photo_dir, ignore_errors=True)

    conn.execute("DELETE FROM dim_monument_photo WHERE monument_id = ?", (monument_id,))
    conn.execute("DELETE FROM dim_monument_location WHERE monument_id = ?", (monument_id,))
    conn.execute("DELETE FROM dim_monument WHERE monument_id = ?", (monument_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# Monument photos
# ---------------------------------------------------------------------------

def _ensure_monument_photo_dir(monument_slug: str) -> Path:
    d = MONUMENT_PHOTO_DIR / monument_slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_monument_photo(
    conn: Any,
    monument_id: int,
    monument_slug: str,
    file_bytes: bytes,
    original_filename: str,
    source_url: str = "",
    attribution: str = "",
    caption: str = "",
    set_primary: bool = False,
    image_url: str = "",
) -> dict[str, Any]:
    suffix = Path(original_filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return {"success": False, "error": "Format non supporté. Utilisez JPG, PNG ou WebP."}

    photo_dir = _ensure_monument_photo_dir(monument_slug)
    unique_name = f"{uuid.uuid4().hex[:12]}{suffix}"
    dest = photo_dir / unique_name
    dest.write_bytes(file_bytes)

    if set_primary:
        conn.execute("UPDATE dim_monument_photo SET is_primary = FALSE WHERE monument_id = ?", (monument_id,))

    max_order = conn.execute(
        "SELECT COALESCE(MAX(photo_order), -1) FROM dim_monument_photo WHERE monument_id = ?",
        (monument_id,),
    ).fetchone()[0]

    conn.execute(
        """INSERT INTO dim_monument_photo
           (monument_id, filename, caption, source_url, attribution, is_primary, photo_order, image_url)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (monument_id, unique_name, caption, source_url, attribution,
         bool(set_primary), max_order + 1, image_url),
    )
    conn.commit()
    return {"success": True, "filename": unique_name}


def delete_monument_photo(conn: Any, monument_photo_id: int, monument_slug: str) -> None:
    row = conn.execute(
        "SELECT filename, is_primary, monument_id FROM dim_monument_photo WHERE monument_photo_id = ?",
        (monument_photo_id,),
    ).fetchone()
    if not row:
        return
    filepath = MONUMENT_PHOTO_DIR / monument_slug / row["filename"]
    if filepath.exists():
        filepath.unlink()
    was_primary = row["is_primary"]
    monument_id = row["monument_id"]
    conn.execute("DELETE FROM dim_monument_photo WHERE monument_photo_id = ?", (monument_photo_id,))
    if was_primary:
        conn.execute(
            """UPDATE dim_monument_photo SET is_primary = TRUE
               WHERE monument_photo_id = (
                   SELECT monument_photo_id FROM dim_monument_photo
                   WHERE monument_id = ? ORDER BY photo_order LIMIT 1
               )""",
            (monument_id,),
        )
    conn.commit()


def set_monument_photo_primary(conn: Any, monument_photo_id: int, monument_id: int) -> None:
    conn.execute("UPDATE dim_monument_photo SET is_primary = FALSE WHERE monument_id = ?", (monument_id,))
    conn.execute("UPDATE dim_monument_photo SET is_primary = TRUE WHERE monument_photo_id = ?", (monument_photo_id,))
    conn.commit()


def get_monument_primary_photo(conn: Any, monument_slug: str) -> str | None:
    """Return the photo_path of the primary photo, or None."""
    row = conn.execute(
        """SELECT mp.filename FROM dim_monument_photo mp
           JOIN dim_monument m ON m.monument_id = mp.monument_id
           WHERE m.monument_slug = ? AND mp.is_primary = TRUE LIMIT 1""",
        (monument_slug,),
    ).fetchone()
    if row:
        return f"images/monuments/{monument_slug}/{row[0]}"
    row = conn.execute(
        """SELECT mp.filename FROM dim_monument_photo mp
           JOIN dim_monument m ON m.monument_id = mp.monument_id
           WHERE m.monument_slug = ? ORDER BY mp.photo_order LIMIT 1""",
        (monument_slug,),
    ).fetchone()
    if row:
        return f"images/monuments/{monument_slug}/{row[0]}"
    return None
