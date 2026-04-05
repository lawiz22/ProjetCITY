"""Service for historical events: parse, import, CRUD, photos."""
from __future__ import annotations

import json
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
EVENT_PHOTO_DIR = PROJECT_ROOT / "static" / "images" / "events"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

EVENT_CATEGORIES = [
    "guerre",
    "catastrophe_naturelle",
    "economie",
    "politique",
    "culture",
    "environnement",
    "technologie",
    "sante",
    "migration",
    "autre",
]

CATEGORY_LABELS = {
    "guerre": "Guerre",
    "catastrophe_naturelle": "Catastrophe naturelle",
    "economie": "Économie",
    "politique": "Politique",
    "culture": "Culture",
    "environnement": "Environnement",
    "technologie": "Technologie",
    "sante": "Santé",
    "migration": "Migration",
    "autre": "Autre",
}

CATEGORY_EMOJIS = {
    "guerre": "⚔️",
    "catastrophe_naturelle": "🌪️",
    "economie": "📉",
    "politique": "🏛️",
    "culture": "🎭",
    "environnement": "🌿",
    "technologie": "💡",
    "sante": "🏥",
    "migration": "🚢",
    "autre": "📌",
}


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", normalized.strip().lower())
    return normalized.strip("-")


# ---------------------------------------------------------------------------
# Parse AI-generated event text
# ---------------------------------------------------------------------------

def parse_event_text(text: str) -> dict[str, Any]:
    """Parse structured AI-generated event text into a dict.

    Expected format::

        EVENT_NAME = "Great Fire of London"
        EVENT_DATE_START = "1666-09-02"
        EVENT_DATE_END = "1666-09-06"
        EVENT_YEAR = 1666
        EVENT_LEVEL = 1
        EVENT_CATEGORY = "catastrophe_naturelle"

        === DESCRIPTION ===
        Multi-line description text ...

        === IMPACT POPULATION ===
        Multi-line impact text ...

        === IMPACT MIGRATION ===
        Multi-line migration text ...

        === LOCATIONS ===
        London, England, United Kingdom, primary
        England, United Kingdom, secondary
    """
    result: dict[str, Any] = {
        "event_name": "",
        "event_slug": "",
        "event_date_start": None,
        "event_date_end": None,
        "event_year": None,
        "event_level": 1,
        "event_category": "autre",
        "description": "",
        "impact_population": "",
        "impact_migration": "",
        "locations": [],
    }

    # Extract key=value fields
    for line in text.splitlines():
        line = line.strip()
        # Match EVENT_NAME – use opening quote to determine closing quote
        # (avoid apostrophes in French names like "Assassinat d'Abraham Lincoln")
        m = re.match(r'^EVENT_NAME\s*=\s*"(.+)"\s*$', line) or \
            re.match(r"^EVENT_NAME\s*=\s*'(.+)'\s*$", line)
        if m:
            result["event_name"] = m.group(1).strip()
            result["event_slug"] = slugify(result["event_name"])
            continue
        # Match EVENT_DATE_START
        m = re.match(r'^EVENT_DATE_START\s*=\s*"(.+?)"\s*$', line) or \
            re.match(r"^EVENT_DATE_START\s*=\s*'(.+?)'\s*$", line)
        if m:
            result["event_date_start"] = m.group(1).strip()
            continue
        # Match EVENT_DATE_END
        m = re.match(r'^EVENT_DATE_END\s*=\s*"(.+?)"\s*$', line) or \
            re.match(r"^EVENT_DATE_END\s*=\s*'(.+?)'\s*$", line)
        if m:
            result["event_date_end"] = m.group(1).strip()
            continue
        m = re.match(r'^EVENT_YEAR\s*=\s*(\d+)', line)
        if m:
            result["event_year"] = int(m.group(1))
            continue
        m = re.match(r'^EVENT_LEVEL\s*=\s*(\d)', line)
        if m:
            result["event_level"] = int(m.group(1))
            continue
        # Match EVENT_CATEGORY
        m = re.match(r'^EVENT_CATEGORY\s*=\s*"(.+?)"\s*$', line) or \
            re.match(r"^EVENT_CATEGORY\s*=\s*'(.+?)'\s*$", line)
        if m:
            cat = m.group(1).strip().lower()
            if cat in EVENT_CATEGORIES:
                result["event_category"] = cat
            continue

    # Extract sections
    sections = re.split(r'===\s*(.+?)\s*===', text)
    # sections = ['preamble', 'DESCRIPTION', 'desc text', 'IMPACT POPULATION', 'pop text', ...]
    for i in range(1, len(sections) - 1, 2):
        header = sections[i].strip().upper()
        body = sections[i + 1].strip()
        if header == "DESCRIPTION":
            result["description"] = body
        elif header == "IMPACT POPULATION":
            result["impact_population"] = body
        elif header == "IMPACT MIGRATION":
            result["impact_migration"] = body
        elif header == "LOCATIONS":
            for loc_line in body.splitlines():
                loc_line = loc_line.strip()
                if not loc_line or loc_line.startswith("#"):
                    continue
                parts = [p.strip() for p in loc_line.split(",")]
                if len(parts) >= 3:
                    result["locations"].append({
                        "city_name": parts[0] if len(parts) >= 4 else None,
                        "region": parts[-3] if len(parts) >= 4 else parts[0],
                        "country": parts[-2] if len(parts) >= 4 else parts[1],
                        "role": parts[-1] if parts[-1] in ("primary", "secondary", "affected") else "primary",
                    })
                elif len(parts) == 2:
                    result["locations"].append({
                        "city_name": None,
                        "region": parts[0],
                        "country": parts[1],
                        "role": "primary",
                    })

    if not result["event_name"]:
        raise ValueError("EVENT_NAME introuvable dans le texte généré.")

    if len(result["event_name"]) < 10:
        raise ValueError(
            f"EVENT_NAME trop court ({result['event_name']!r}). "
            "Le nom a probablement été tronqué par une apostrophe. "
            "Vérifiez les guillemets dans le texte source."
        )

    return result


# ---------------------------------------------------------------------------
# Import / CRUD
# ---------------------------------------------------------------------------

def import_event(conn: Any, data: dict[str, Any]) -> int:
    """Upsert an event into dim_event and its locations. Returns event_id."""
    uid = _current_user_id()
    cursor = conn.execute(
        """INSERT INTO dim_event
           (event_name, event_slug, event_date_start, event_date_end,
            event_year, event_level, event_category,
            description, impact_population, impact_migration, source_text,
            created_by_user_id, updated_by_user_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(event_slug) DO UPDATE SET
               event_name = excluded.event_name,
               event_date_start = excluded.event_date_start,
               event_date_end = excluded.event_date_end,
               event_year = excluded.event_year,
               event_level = excluded.event_level,
               event_category = excluded.event_category,
               description = excluded.description,
               impact_population = excluded.impact_population,
               impact_migration = excluded.impact_migration,
               source_text = excluded.source_text,
               updated_by_user_id = excluded.updated_by_user_id,
               updated_at = CURRENT_TIMESTAMP
           RETURNING event_id""",
        (
            data["event_name"], data["event_slug"],
            data.get("event_date_start"), data.get("event_date_end"),
            data.get("event_year"), data.get("event_level", 1),
            data.get("event_category", "autre"),
            data.get("description", ""), data.get("impact_population", ""),
            data.get("impact_migration", ""), data.get("source_text", ""),
            uid, uid,
        ),
    )
    event_id = cursor.fetchone()[0]

    # Replace locations
    conn.execute("DELETE FROM dim_event_location WHERE event_id = ?", (event_id,))
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
            """INSERT INTO dim_event_location (event_id, city_id, region, country, role)
               VALUES (?, ?, ?, ?, ?)""",
            (event_id, city_id, loc.get("region"), loc.get("country"), loc.get("role", "primary")),
        )

    conn.commit()
    return event_id


def get_event(conn: Any, event_slug: str) -> dict[str, Any] | None:
    """Load a full event with locations and photos."""
    row = conn.execute(
        "SELECT * FROM dim_event WHERE event_slug = ?", (event_slug,)
    ).fetchone()
    if not row:
        return None

    event = dict(row)
    event_id = event["event_id"]

    # Locations
    locs = conn.execute(
        """SELECT el.*, dc.city_name AS matched_city_name, dc.city_slug AS matched_city_slug
           FROM dim_event_location el
           LEFT JOIN dim_city dc ON dc.city_id = el.city_id
           WHERE el.event_id = ?
           ORDER BY el.role, el.event_location_id""",
        (event_id,),
    ).fetchall()
    event["locations"] = [dict(l) for l in locs]

    # Photos
    photos = conn.execute(
        """SELECT * FROM dim_event_photo
           WHERE event_id = ? ORDER BY is_primary DESC, photo_order, event_photo_id""",
        (event_id,),
    ).fetchall()
    event["photos"] = [
        {**dict(p), "photo_path": f"images/events/{event_slug}/{p['filename']}"}
        for p in photos
    ]

    return event


def get_events_list(conn: Any, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """List events with optional filters (category, level, country, search)."""
    sql = (
        "SELECT vs.*, de.created_at AS entity_created_at, de.updated_at AS entity_updated_at,"
        " COALESCE(au_c.display_name, au_c.username) AS created_by_name,"
        " COALESCE(au_u.display_name, au_u.username) AS updated_by_name"
        " FROM vw_event_summary vs"
        " LEFT JOIN dim_event de ON de.event_id = vs.event_id"
        " LEFT JOIN app_user au_c ON au_c.user_id = de.created_by_user_id"
        " LEFT JOIN app_user au_u ON au_u.user_id = de.updated_by_user_id"
        " WHERE 1=1"
    )
    params: list[Any] = []
    if filters:
        if filters.get("category"):
            sql += " AND event_category = ?"
            params.append(filters["category"])
        if filters.get("level"):
            sql += " AND event_level = ?"
            params.append(int(filters["level"]))
        if filters.get("search"):
            sql += (
                " AND (LOWER(event_name) LIKE LOWER(?)"
                " OR LOWER(description) LIKE LOWER(?)"
                " OR LOWER(location_names) LIKE LOWER(?))"
            )
            q = f"%{filters['search']}%"
            params.extend([q, q, q])
    sql += " ORDER BY event_year DESC, event_name"
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_events_for_city(conn: Any, city_id: int) -> list[dict[str, Any]]:
    """Get events linked to a specific city."""
    rows = conn.execute(
        """SELECT e.event_id, e.event_name, e.event_slug, e.event_year,
                  e.event_level, e.event_category, e.event_date_start,
                  el.role
           FROM dim_event e
           JOIN dim_event_location el ON el.event_id = e.event_id
           WHERE el.city_id = ?
           ORDER BY e.event_year""",
        (city_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_event(conn: Any, event_id: int) -> None:
    """Delete an event and all related data."""
    # Get slug for photo cleanup
    row = conn.execute("SELECT event_slug FROM dim_event WHERE event_id = ?", (event_id,)).fetchone()
    if row:
        photo_dir = EVENT_PHOTO_DIR / row[0]
        if photo_dir.exists():
            import shutil
            shutil.rmtree(photo_dir, ignore_errors=True)

    conn.execute("DELETE FROM dim_event_photo WHERE event_id = ?", (event_id,))
    conn.execute("DELETE FROM dim_event_location WHERE event_id = ?", (event_id,))
    conn.execute("DELETE FROM dim_event WHERE event_id = ?", (event_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# Event photos
# ---------------------------------------------------------------------------

def _event_default_date(conn: Any, event_id: int) -> str:
    """Return the event's start date or year, or empty."""
    row = conn.execute(
        "SELECT event_date_start, event_year FROM dim_event WHERE event_id = ?", (event_id,)
    ).fetchone()
    if row:
        if row["event_date_start"]:
            return row["event_date_start"]
        if row["event_year"]:
            return str(row["event_year"])
    return ""


def _ensure_event_photo_dir(event_slug: str) -> Path:
    d = EVENT_PHOTO_DIR / event_slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_event_photo(
    conn: Any,
    event_id: int,
    event_slug: str,
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

    photo_dir = _ensure_event_photo_dir(event_slug)
    unique_name = f"{uuid.uuid4().hex[:12]}{suffix}"
    dest = photo_dir / unique_name
    dest.write_bytes(file_bytes)

    if set_primary:
        conn.execute("UPDATE dim_event_photo SET is_primary = FALSE WHERE event_id = ?", (event_id,))

    max_order = conn.execute(
        "SELECT COALESCE(MAX(photo_order), -1) FROM dim_event_photo WHERE event_id = ?",
        (event_id,),
    ).fetchone()[0]

    conn.execute(
        """INSERT INTO dim_event_photo
           (event_id, filename, caption, source_url, attribution, is_primary, photo_order, image_url, photo_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (event_id, unique_name, caption, source_url, attribution,
         bool(set_primary), max_order + 1, image_url,
         _event_default_date(conn, event_id)),
    )
    conn.commit()
    return {"success": True, "filename": unique_name}


def delete_event_photo(conn: Any, event_photo_id: int, event_slug: str) -> None:
    row = conn.execute(
        "SELECT filename, is_primary, event_id FROM dim_event_photo WHERE event_photo_id = ?",
        (event_photo_id,),
    ).fetchone()
    if not row:
        return
    filepath = EVENT_PHOTO_DIR / event_slug / row["filename"]
    if filepath.exists():
        filepath.unlink()
    was_primary = row["is_primary"]
    event_id = row["event_id"]
    conn.execute("DELETE FROM dim_event_photo WHERE event_photo_id = ?", (event_photo_id,))
    if was_primary:
        conn.execute(
            """UPDATE dim_event_photo SET is_primary = TRUE
               WHERE event_photo_id = (
                   SELECT event_photo_id FROM dim_event_photo
                   WHERE event_id = ? ORDER BY photo_order LIMIT 1
               )""",
            (event_id,),
        )
    conn.commit()


def set_event_photo_primary(conn: Any, event_photo_id: int, event_id: int) -> None:
    conn.execute("UPDATE dim_event_photo SET is_primary = FALSE WHERE event_id = ?", (event_id,))
    conn.execute("UPDATE dim_event_photo SET is_primary = TRUE WHERE event_photo_id = ?", (event_photo_id,))
    conn.commit()


def get_event_primary_photo(conn: Any, event_slug: str) -> str | None:
    """Return the photo_path of the primary photo, or None."""
    row = conn.execute(
        """SELECT ep.filename FROM dim_event_photo ep
           JOIN dim_event e ON e.event_id = ep.event_id
           WHERE e.event_slug = ? AND ep.is_primary = TRUE LIMIT 1""",
        (event_slug,),
    ).fetchone()
    if row:
        return f"images/events/{event_slug}/{row[0]}"
    row = conn.execute(
        """SELECT ep.filename FROM dim_event_photo ep
           JOIN dim_event e ON e.event_id = ep.event_id
           WHERE e.event_slug = ? ORDER BY ep.photo_order LIMIT 1""",
        (event_slug,),
    ).fetchone()
    if row:
        return f"images/events/{event_slug}/{row[0]}"
    return None
