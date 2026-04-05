"""Service for historical figures: parse, import, CRUD, photos."""
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
PERSON_PHOTO_DIR = PROJECT_ROOT / "static" / "images" / "persons"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

PERSON_CATEGORIES = [
    "gouvernance",
    "guerre",
    "politique",
    "science",
    "culture_musique",
    "culture_art",
    "culture_litterature",
    "culture_cinema",
    "sport",
    "religion",
    "economie",
    "exploration",
    "autre",
]

CATEGORY_LABELS = {
    "gouvernance": "Gouvernance",
    "guerre": "Guerre",
    "politique": "Politique",
    "science": "Science",
    "culture_musique": "Musique",
    "culture_art": "Art",
    "culture_litterature": "Littérature",
    "culture_cinema": "Cinéma",
    "sport": "Sport",
    "religion": "Religion",
    "economie": "Économie",
    "exploration": "Exploration",
    "autre": "Autre",
}

CATEGORY_EMOJIS = {
    "gouvernance": "👑",
    "guerre": "⚔️",
    "politique": "🏛️",
    "science": "🔬",
    "culture_musique": "🎵",
    "culture_art": "🎨",
    "culture_litterature": "📚",
    "culture_cinema": "🎬",
    "sport": "⚽",
    "religion": "✝️",
    "economie": "💰",
    "exploration": "🧭",
    "autre": "📌",
}

LOCATION_ROLES = ["birth", "death", "residence", "activity", "primary", "secondary"]


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", normalized.strip().lower())
    return normalized.strip("-")


# ---------------------------------------------------------------------------
# Parse AI-generated person text
# ---------------------------------------------------------------------------

def parse_person_text(text: str) -> dict[str, Any]:
    """Parse structured AI-generated person text into a dict.

    Expected format::

        PERSON_NAME = "Louis Riel"
        BIRTH_DATE = "1844-10-22"
        DEATH_DATE = "1885-11-16"
        BIRTH_YEAR = 1844
        DEATH_YEAR = 1885
        BIRTH_CITY = "Saint-Boniface"
        BIRTH_COUNTRY = "Canada"
        DEATH_CITY = "Regina"
        DEATH_COUNTRY = "Canada"
        PERSON_LEVEL = 1
        PERSON_CATEGORY = "politique"

        === RÉSUMÉ ===
        Court résumé...

        === BIOGRAPHIE ===
        Biographie détaillée...

        === RÉALISATIONS ===
        Accomplissements...

        === IMPACT ===
        Impact sur la société...

        === LIEUX ===
        Saint-Boniface, Manitoba, Canada, birth
        Regina, Saskatchewan, Canada, death
    """
    result: dict[str, Any] = {
        "person_name": "",
        "person_slug": "",
        "birth_date": None,
        "death_date": None,
        "birth_year": None,
        "death_year": None,
        "birth_city": None,
        "birth_country": None,
        "death_city": None,
        "death_country": None,
        "person_level": 2,
        "person_category": "autre",
        "summary": "",
        "biography": "",
        "achievements": "",
        "impact_population": "",
        "locations": [],
    }

    # Extract key=value fields
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r'^PERSON_NAME\s*=\s*"(.+)"\s*$', line) or \
            re.match(r"^PERSON_NAME\s*=\s*'(.+)'\s*$", line)
        if m:
            result["person_name"] = m.group(1).strip()
            result["person_slug"] = slugify(result["person_name"])
            continue
        m = re.match(r'^BIRTH_DATE\s*=\s*"(.+?)"\s*$', line) or \
            re.match(r"^BIRTH_DATE\s*=\s*'(.+?)'\s*$", line)
        if m:
            result["birth_date"] = m.group(1).strip()
            continue
        m = re.match(r'^DEATH_DATE\s*=\s*"(.+?)"\s*$', line) or \
            re.match(r"^DEATH_DATE\s*=\s*'(.+?)'\s*$", line)
        if m:
            result["death_date"] = m.group(1).strip()
            continue
        m = re.match(r'^BIRTH_YEAR\s*=\s*(-?\d+)', line)
        if m:
            result["birth_year"] = int(m.group(1))
            continue
        m = re.match(r'^DEATH_YEAR\s*=\s*(-?\d+)', line)
        if m:
            result["death_year"] = int(m.group(1))
            continue
        m = re.match(r'^BIRTH_CITY\s*=\s*"(.+?)"\s*$', line) or \
            re.match(r"^BIRTH_CITY\s*=\s*'(.+?)'\s*$", line)
        if m:
            result["birth_city"] = m.group(1).strip()
            continue
        m = re.match(r'^BIRTH_COUNTRY\s*=\s*"(.+?)"\s*$', line) or \
            re.match(r"^BIRTH_COUNTRY\s*=\s*'(.+?)'\s*$", line)
        if m:
            result["birth_country"] = m.group(1).strip()
            continue
        m = re.match(r'^DEATH_CITY\s*=\s*"(.+?)"\s*$', line) or \
            re.match(r"^DEATH_CITY\s*=\s*'(.+?)'\s*$", line)
        if m:
            result["death_city"] = m.group(1).strip()
            continue
        m = re.match(r'^DEATH_COUNTRY\s*=\s*"(.+?)"\s*$', line) or \
            re.match(r"^DEATH_COUNTRY\s*=\s*'(.+?)'\s*$", line)
        if m:
            result["death_country"] = m.group(1).strip()
            continue
        m = re.match(r'^PERSON_LEVEL\s*=\s*(\d)', line)
        if m:
            result["person_level"] = int(m.group(1))
            continue
        m = re.match(r'^PERSON_CATEGORY\s*=\s*"(.+?)"\s*$', line) or \
            re.match(r"^PERSON_CATEGORY\s*=\s*'(.+?)'\s*$", line)
        if m:
            cat = m.group(1).strip().lower()
            if cat in PERSON_CATEGORIES:
                result["person_category"] = cat
            continue

    # Extract sections
    sections = re.split(r'===\s*(.+?)\s*===', text)
    for i in range(1, len(sections) - 1, 2):
        header = sections[i].strip().upper()
        body = sections[i + 1].strip()
        if header in ("RÉSUMÉ", "RESUME"):
            result["summary"] = body
        elif header in ("BIOGRAPHIE", "BIOGRAPHY"):
            result["biography"] = body
        elif header in ("RÉALISATIONS", "REALISATIONS", "ACHIEVEMENTS"):
            result["achievements"] = body
        elif header in ("IMPACT", "IMPACT POPULATION"):
            result["impact_population"] = body
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
                        "region": None,
                        "country": parts[1],
                        "role": parts[2].lower() if parts[2].lower() in LOCATION_ROLES else "primary",
                    })
                elif len(parts) == 2:
                    result["locations"].append({
                        "city_name": None,
                        "region": parts[0],
                        "country": parts[1],
                        "role": "primary",
                    })

    if not result["person_name"]:
        raise ValueError("PERSON_NAME introuvable dans le texte généré.")

    if len(result["person_name"]) < 3:
        raise ValueError(
            f"PERSON_NAME trop court ({result['person_name']!r}). "
            "Vérifiez les guillemets dans le texte source."
        )

    return result


# ---------------------------------------------------------------------------
# Import / CRUD
# ---------------------------------------------------------------------------

def import_person(conn: Any, data: dict[str, Any]) -> int:
    """Upsert a person into dim_person and its locations. Returns person_id."""
    uid = _current_user_id()
    cursor = conn.execute(
        """INSERT INTO dim_person
           (person_name, person_slug,
            birth_date, death_date, birth_year, death_year,
            birth_city, birth_country, death_city, death_country,
            person_level, person_category,
            summary, biography, achievements, impact_population,
            source_text,
            created_by_user_id, updated_by_user_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(person_slug) DO UPDATE SET
               person_name = excluded.person_name,
               birth_date = excluded.birth_date,
               death_date = excluded.death_date,
               birth_year = excluded.birth_year,
               death_year = excluded.death_year,
               birth_city = excluded.birth_city,
               birth_country = excluded.birth_country,
               death_city = excluded.death_city,
               death_country = excluded.death_country,
               person_level = excluded.person_level,
               person_category = excluded.person_category,
               summary = excluded.summary,
               biography = excluded.biography,
               achievements = excluded.achievements,
               impact_population = excluded.impact_population,
               source_text = excluded.source_text,
               updated_by_user_id = excluded.updated_by_user_id,
               updated_at = CURRENT_TIMESTAMP
           RETURNING person_id""",
        (
            data["person_name"], data["person_slug"],
            data.get("birth_date"), data.get("death_date"),
            data.get("birth_year"), data.get("death_year"),
            data.get("birth_city"), data.get("birth_country"),
            data.get("death_city"), data.get("death_country"),
            data.get("person_level", 2),
            data.get("person_category", "autre"),
            data.get("summary", ""), data.get("biography", ""),
            data.get("achievements", ""), data.get("impact_population", ""),
            data.get("source_text", ""),
            uid, uid,
        ),
    )
    person_id = cursor.fetchone()[0]

    # Replace locations
    conn.execute("DELETE FROM dim_person_location WHERE person_id = ?", (person_id,))
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
            """INSERT INTO dim_person_location (person_id, city_id, region, country, role)
               VALUES (?, ?, ?, ?, ?)""",
            (person_id, city_id, loc.get("region"), loc.get("country"), loc.get("role", "primary")),
        )

    conn.commit()
    return person_id


def get_person(conn: Any, person_slug: str) -> dict[str, Any] | None:
    """Load a full person with locations and photos."""
    row = conn.execute(
        "SELECT * FROM dim_person WHERE person_slug = ?", (person_slug,)
    ).fetchone()
    if not row:
        return None

    person = dict(row)
    person_id = person["person_id"]

    locs = conn.execute(
        """SELECT pl.*, dc.city_name AS matched_city_name, dc.city_slug AS matched_city_slug
           FROM dim_person_location pl
           LEFT JOIN dim_city dc ON dc.city_id = pl.city_id
           WHERE pl.person_id = ?
           ORDER BY pl.role, pl.person_location_id""",
        (person_id,),
    ).fetchall()
    person["locations"] = [dict(l) for l in locs]

    photos = conn.execute(
        """SELECT * FROM dim_person_photo
           WHERE person_id = ? ORDER BY is_primary DESC, photo_order, person_photo_id""",
        (person_id,),
    ).fetchall()
    person["photos"] = [
        {**dict(p), "photo_path": f"images/persons/{person_slug}/{p['filename']}"}
        for p in photos
    ]

    return person


def get_persons_list(conn: Any, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """List persons with optional filters (category, level, search)."""
    sql = (
        "SELECT vs.*, dp.created_at AS entity_created_at, dp.updated_at AS entity_updated_at,"
        " COALESCE(au_c.display_name, au_c.username) AS created_by_name,"
        " COALESCE(au_u.display_name, au_u.username) AS updated_by_name"
        " FROM vw_person_summary vs"
        " LEFT JOIN dim_person dp ON dp.person_id = vs.person_id"
        " LEFT JOIN app_user au_c ON au_c.user_id = dp.created_by_user_id"
        " LEFT JOIN app_user au_u ON au_u.user_id = dp.updated_by_user_id"
        " WHERE 1=1"
    )
    params: list[Any] = []
    if filters:
        if filters.get("category"):
            sql += " AND person_category = ?"
            params.append(filters["category"])
        if filters.get("level"):
            sql += " AND person_level = ?"
            params.append(int(filters["level"]))
        if filters.get("search"):
            sql += (
                " AND (LOWER(person_name) LIKE LOWER(?)"
                " OR LOWER(summary) LIKE LOWER(?)"
                " OR LOWER(location_names) LIKE LOWER(?))"
            )
            q = f"%{filters['search']}%"
            params.extend([q, q, q])
    sql += " ORDER BY birth_year DESC NULLS LAST, person_name"
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_persons_for_city(conn: Any, city_id: int) -> list[dict[str, Any]]:
    """Get persons linked to a specific city."""
    rows = conn.execute(
        """SELECT p.person_id, p.person_name, p.person_slug,
                  p.birth_year, p.death_year,
                  p.person_level, p.person_category,
                  pl.role
           FROM dim_person p
           JOIN dim_person_location pl ON pl.person_id = p.person_id
           WHERE pl.city_id = ?
           ORDER BY p.birth_year""",
        (city_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_person(conn: Any, person_id: int) -> None:
    """Delete a person and all related data."""
    row = conn.execute("SELECT person_slug FROM dim_person WHERE person_id = ?", (person_id,)).fetchone()
    if row:
        photo_dir = PERSON_PHOTO_DIR / row[0]
        if photo_dir.exists():
            import shutil
            shutil.rmtree(photo_dir, ignore_errors=True)

    conn.execute("DELETE FROM dim_person_photo WHERE person_id = ?", (person_id,))
    conn.execute("DELETE FROM dim_person_location WHERE person_id = ?", (person_id,))
    conn.execute("DELETE FROM dim_person WHERE person_id = ?", (person_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# Person photos
# ---------------------------------------------------------------------------

def _person_default_date(conn: Any, person_id: int) -> str:
    """Return the person's birth_date or birth_year, or empty."""
    row = conn.execute(
        "SELECT birth_date, birth_year FROM dim_person WHERE person_id = ?", (person_id,)
    ).fetchone()
    if row:
        if row["birth_date"]:
            return row["birth_date"]
        if row["birth_year"]:
            return str(row["birth_year"])
    return ""


def _ensure_person_photo_dir(person_slug: str) -> Path:
    d = PERSON_PHOTO_DIR / person_slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_person_photo(
    conn: Any,
    person_id: int,
    person_slug: str,
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

    photo_dir = _ensure_person_photo_dir(person_slug)
    unique_name = f"{uuid.uuid4().hex[:12]}{suffix}"
    dest = photo_dir / unique_name
    dest.write_bytes(file_bytes)
    from app.services.city_photos import generate_thumbnail
    generate_thumbnail(dest)

    if set_primary:
        conn.execute("UPDATE dim_person_photo SET is_primary = FALSE WHERE person_id = ?", (person_id,))

    max_order = conn.execute(
        "SELECT COALESCE(MAX(photo_order), -1) FROM dim_person_photo WHERE person_id = ?",
        (person_id,),
    ).fetchone()[0]

    conn.execute(
        """INSERT INTO dim_person_photo
           (person_id, filename, caption, source_url, attribution, is_primary, photo_order, image_url, photo_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (person_id, unique_name, caption, source_url, attribution,
         bool(set_primary), max_order + 1, image_url,
         _person_default_date(conn, person_id)),
    )
    conn.commit()
    return {"success": True, "filename": unique_name}


def delete_person_photo(conn: Any, person_photo_id: int, person_slug: str) -> None:
    row = conn.execute(
        "SELECT filename, is_primary, person_id FROM dim_person_photo WHERE person_photo_id = ?",
        (person_photo_id,),
    ).fetchone()
    if not row:
        return
    filepath = PERSON_PHOTO_DIR / person_slug / row["filename"]
    if filepath.exists():
        filepath.unlink()
    was_primary = row["is_primary"]
    person_id = row["person_id"]
    conn.execute("DELETE FROM dim_person_photo WHERE person_photo_id = ?", (person_photo_id,))
    if was_primary:
        conn.execute(
            """UPDATE dim_person_photo SET is_primary = TRUE
               WHERE person_photo_id = (
                   SELECT person_photo_id FROM dim_person_photo
                   WHERE person_id = ? ORDER BY photo_order LIMIT 1
               )""",
            (person_id,),
        )
    conn.commit()


def set_person_photo_primary(conn: Any, person_photo_id: int, person_id: int) -> None:
    conn.execute("UPDATE dim_person_photo SET is_primary = FALSE WHERE person_id = ?", (person_id,))
    conn.execute("UPDATE dim_person_photo SET is_primary = TRUE WHERE person_photo_id = ?", (person_photo_id,))
    conn.commit()


def get_person_primary_photo(conn: Any, person_slug: str) -> str | None:
    """Return the photo_path of the primary photo, or None."""
    row = conn.execute(
        """SELECT pp.filename FROM dim_person_photo pp
           JOIN dim_person p ON p.person_id = pp.person_id
           WHERE p.person_slug = ? AND pp.is_primary = TRUE LIMIT 1""",
        (person_slug,),
    ).fetchone()
    if row:
        return f"images/persons/{person_slug}/{row[0]}"
    row = conn.execute(
        """SELECT pp.filename FROM dim_person_photo pp
           JOIN dim_person p ON p.person_id = pp.person_id
           WHERE p.person_slug = ? ORDER BY pp.photo_order LIMIT 1""",
        (person_slug,),
    ).fetchone()
    if row:
        return f"images/persons/{person_slug}/{row[0]}"
    return None
