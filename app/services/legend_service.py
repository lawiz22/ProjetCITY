"""Service for legends & unexplained events: parse, import, CRUD, photos."""
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
LEGEND_PHOTO_DIR = PROJECT_ROOT / "static" / "images" / "legends"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

LEGEND_TYPES = ["legende", "inexplique"]

LEGEND_CATEGORIES = [
    "origine_inconnue",
    "amerindienne",
    "irlandaise",
    "europeenne",
    "nordique",
    "autre_folklore",
]

INEXPLIQUE_CATEGORIES = [
    "ufo",
    "cryptide",
    "paranormal",
    "disparition",
    "complot",
    "phenomene_naturel",
]

ALL_CATEGORIES = LEGEND_CATEGORIES + INEXPLIQUE_CATEGORIES

CATEGORIES_BY_TYPE = {
    "legende": LEGEND_CATEGORIES,
    "inexplique": INEXPLIQUE_CATEGORIES,
}

CATEGORY_LABELS = {
    "origine_inconnue": "Origine inconnue",
    "amerindienne": "Amérindienne",
    "irlandaise": "Irlandaise",
    "europeenne": "Européenne",
    "nordique": "Nordique / Viking",
    "autre_folklore": "Autre folklore",
    "ufo": "UFO / OVNI",
    "cryptide": "Bigfoot / Cryptides",
    "paranormal": "Paranormal",
    "disparition": "Disparition mystérieuse",
    "complot": "Théorie du complot",
    "phenomene_naturel": "Phénomène naturel inexpliqué",
}

CATEGORY_EMOJIS = {
    "origine_inconnue": "🔮",
    "amerindienne": "🪶",
    "irlandaise": "☘️",
    "europeenne": "🏰",
    "nordique": "⚔️",
    "autre_folklore": "🎭",
    "ufo": "🛸",
    "cryptide": "🦶",
    "paranormal": "👻",
    "disparition": "🔍",
    "complot": "🕵️",
    "phenomene_naturel": "🌀",
}

TYPE_LABELS = {
    "legende": "Légende",
    "inexplique": "Événement inexpliqué",
}

TYPE_EMOJIS = {
    "legende": "📜",
    "inexplique": "❓",
}

LOCATION_ROLES = ["primary", "secondary"]


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", normalized.strip().lower())
    return normalized.strip("-")


# ---------------------------------------------------------------------------
# Parse AI-generated legend text
# ---------------------------------------------------------------------------

def parse_legend_text(text: str) -> dict[str, Any]:
    """Parse structured AI-generated legend text into a dict.

    Expected format::

        LEGEND_NAME = "Le Diable au pont de Québec"
        LEGEND_TYPE = "legende"
        LEGEND_CATEGORY = "origine_inconnue"
        LEGEND_LEVEL = 1
        DATE_REPORTED = "1907"
        YEAR_REPORTED = 1907
        LATITUDE = 46.7488
        LONGITUDE = -71.2878

        === RÉSUMÉ ===
        Court résumé...

        === DESCRIPTION ===
        Description détaillée...

        === HISTOIRE ===
        Historique...

        === PREUVES ===
        Éléments de preuve, témoignages...

        === LIEUX ===
        Québec, Québec, Canada, primary
    """
    result: dict[str, Any] = {
        "legend_name": "",
        "legend_slug": "",
        "legend_type": "legende",
        "legend_category": "origine_inconnue",
        "legend_level": 2,
        "date_reported": None,
        "year_reported": None,
        "country": None,
        "region": None,
        "city_name": None,
        "latitude": None,
        "longitude": None,
        "summary": "",
        "description": "",
        "history": "",
        "evidence": "",
        "locations": [],
    }

    for line in text.splitlines():
        line = line.strip()
        m = re.match(r'^LEGEND_NAME\s*=\s*"(.+)"\s*$', line) or \
            re.match(r"^LEGEND_NAME\s*=\s*'(.+)'\s*$", line)
        if m:
            result["legend_name"] = m.group(1).strip()
            result["legend_slug"] = slugify(result["legend_name"])
            continue
        m = re.match(r'^LEGEND_TYPE\s*=\s*"(.+?)"\s*$', line) or \
            re.match(r"^LEGEND_TYPE\s*=\s*'(.+?)'\s*$", line)
        if m:
            val = m.group(1).strip().lower()
            if val in LEGEND_TYPES:
                result["legend_type"] = val
            continue
        m = re.match(r'^LEGEND_CATEGORY\s*=\s*"(.+?)"\s*$', line) or \
            re.match(r"^LEGEND_CATEGORY\s*=\s*'(.+?)'\s*$", line)
        if m:
            cat = m.group(1).strip().lower()
            if cat in ALL_CATEGORIES:
                result["legend_category"] = cat
            continue
        m = re.match(r'^LEGEND_LEVEL\s*=\s*(\d)', line)
        if m:
            result["legend_level"] = int(m.group(1))
            continue
        m = re.match(r'^DATE_REPORTED\s*=\s*"(.+?)"\s*$', line) or \
            re.match(r"^DATE_REPORTED\s*=\s*'(.+?)'\s*$", line)
        if m:
            result["date_reported"] = m.group(1).strip()
            continue
        m = re.match(r'^YEAR_REPORTED\s*=\s*(-?\d+)', line)
        if m:
            result["year_reported"] = int(m.group(1))
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
        m = re.match(r'^COUNTRY\s*=\s*"(.+?)"\s*$', line) or \
            re.match(r"^COUNTRY\s*=\s*'(.+?)'\s*$", line)
        if m:
            result["country"] = m.group(1).strip()
            continue
        m = re.match(r'^REGION\s*=\s*"(.+?)"\s*$', line) or \
            re.match(r"^REGION\s*=\s*'(.+?)'\s*$", line)
        if m:
            result["region"] = m.group(1).strip()
            continue
        m = re.match(r'^CITY_NAME\s*=\s*"(.+?)"\s*$', line) or \
            re.match(r"^CITY_NAME\s*=\s*'(.+?)'\s*$", line)
        if m:
            result["city_name"] = m.group(1).strip()
            continue

    # Extract sections
    sections = re.split(r'===\s*(.+?)\s*===', text)
    for i in range(1, len(sections) - 1, 2):
        header = sections[i].strip().upper()
        body = sections[i + 1].strip()
        if header in ("RÉSUMÉ", "RESUME"):
            result["summary"] = body
        elif header == "DESCRIPTION":
            result["description"] = body
        elif header in ("HISTOIRE", "HISTORY"):
            result["history"] = body
        elif header in ("PREUVES", "EVIDENCE"):
            result["evidence"] = body
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

    if not result["legend_name"]:
        raise ValueError("LEGEND_NAME introuvable dans le texte généré.")

    # Auto-derive country/region/city_name from the primary location if not explicitly set
    primary_loc = next((l for l in result["locations"] if l.get("role") == "primary"), None)
    if not primary_loc and result["locations"]:
        primary_loc = result["locations"][0]
    if primary_loc:
        if not result["country"] and primary_loc.get("country"):
            result["country"] = primary_loc["country"]
        if not result["region"] and primary_loc.get("region"):
            result["region"] = primary_loc["region"]
        if not result["city_name"] and primary_loc.get("city_name"):
            result["city_name"] = primary_loc["city_name"]

    if len(result["legend_name"]) < 3:
        raise ValueError(
            f"LEGEND_NAME trop court ({result['legend_name']!r}). "
            "Vérifiez les guillemets dans le texte source."
        )

    return result


# ---------------------------------------------------------------------------
# Import / CRUD
# ---------------------------------------------------------------------------

def import_legend(conn: Any, data: dict[str, Any]) -> int:
    """Upsert a legend into dim_legend and its locations. Returns legend_id."""
    uid = _current_user_id()
    cursor = conn.execute(
        """INSERT INTO dim_legend
           (legend_name, legend_slug,
            legend_type, legend_category, legend_level,
            date_reported, year_reported,
            country, region, city_name,
            latitude, longitude,
            summary, description, history, evidence,
            source_text,
            created_by_user_id, updated_by_user_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(legend_slug) DO UPDATE SET
               legend_name = excluded.legend_name,
               legend_type = excluded.legend_type,
               legend_category = excluded.legend_category,
               legend_level = excluded.legend_level,
               date_reported = excluded.date_reported,
               year_reported = excluded.year_reported,
               country = excluded.country,
               region = excluded.region,
               city_name = excluded.city_name,
               latitude = excluded.latitude,
               longitude = excluded.longitude,
               summary = excluded.summary,
               description = excluded.description,
               history = excluded.history,
               evidence = excluded.evidence,
               source_text = excluded.source_text,
               updated_by_user_id = excluded.updated_by_user_id,
               updated_at = CURRENT_TIMESTAMP
           RETURNING legend_id""",
        (
            data["legend_name"], data["legend_slug"],
            data.get("legend_type", "legende"),
            data.get("legend_category", "origine_inconnue"),
            data.get("legend_level", 2),
            data.get("date_reported"), data.get("year_reported"),
            data.get("country"), data.get("region"), data.get("city_name"),
            data.get("latitude"), data.get("longitude"),
            data.get("summary", ""), data.get("description", ""),
            data.get("history", ""), data.get("evidence", ""),
            data.get("source_text", ""),
            uid, uid,
        ),
    )
    legend_id = cursor.fetchone()[0]

    # Replace locations
    conn.execute("DELETE FROM dim_legend_location WHERE legend_id = ?", (legend_id,))
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
            """INSERT INTO dim_legend_location (legend_id, city_id, region, country, role)
               VALUES (?, ?, ?, ?, ?)""",
            (legend_id, city_id, loc.get("region"), loc.get("country"), loc.get("role", "primary")),
        )

    conn.commit()
    return legend_id


def get_legend(conn: Any, legend_slug: str) -> dict[str, Any] | None:
    """Load a full legend with locations and photos."""
    row = conn.execute(
        "SELECT * FROM dim_legend WHERE legend_slug = ?", (legend_slug,)
    ).fetchone()
    if not row:
        return None

    legend = dict(row)
    legend_id = legend["legend_id"]

    locs = conn.execute(
        """SELECT ll.*, dc.city_name AS matched_city_name, dc.city_slug AS matched_city_slug
           FROM dim_legend_location ll
           LEFT JOIN dim_city dc ON dc.city_id = ll.city_id
           WHERE ll.legend_id = ?
           ORDER BY ll.role, ll.legend_location_id""",
        (legend_id,),
    ).fetchall()
    legend["locations"] = [dict(l) for l in locs]

    photos = conn.execute(
        """SELECT * FROM dim_legend_photo
           WHERE legend_id = ? ORDER BY is_primary DESC, photo_order, legend_photo_id""",
        (legend_id,),
    ).fetchall()
    legend["photos"] = [
        {**dict(p), "photo_path": f"images/legends/{legend_slug}/{p['filename']}"}
        for p in photos
    ]

    return legend


def get_legends_list(conn: Any, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """List legends with optional filters (type, category, level, search)."""
    sql = (
        "SELECT vs.*, dl.latitude, dl.longitude,"
        " dl.created_at AS entity_created_at, dl.updated_at AS entity_updated_at,"
        " COALESCE(au_c.display_name, au_c.username) AS created_by_name,"
        " COALESCE(au_u.display_name, au_u.username) AS updated_by_name"
        " FROM vw_legend_summary vs"
        " LEFT JOIN dim_legend dl ON dl.legend_id = vs.legend_id"
        " LEFT JOIN app_user au_c ON au_c.user_id = dl.created_by_user_id"
        " LEFT JOIN app_user au_u ON au_u.user_id = dl.updated_by_user_id"
        " WHERE 1=1"
    )
    params: list[Any] = []
    if filters:
        if filters.get("type"):
            sql += " AND legend_type = ?"
            params.append(filters["type"])
        if filters.get("category"):
            sql += " AND legend_category = ?"
            params.append(filters["category"])
        if filters.get("level"):
            sql += " AND legend_level = ?"
            params.append(int(filters["level"]))
        if filters.get("search"):
            sql += (
                " AND (LOWER(legend_name) LIKE LOWER(?)"
                " OR LOWER(summary) LIKE LOWER(?)"
                " OR LOWER(location_names) LIKE LOWER(?))"
            )
            q = f"%{filters['search']}%"
            params.extend([q, q, q])
        if filters.get("country"):
            sql += " AND dl.country = ?"
            params.append(filters["country"])
        if filters.get("region"):
            sql += " AND dl.region = ?"
            params.append(filters["region"])
    sql += " ORDER BY year_reported DESC NULLS LAST, legend_name"
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_legends_for_city(conn: Any, city_id: int) -> list[dict[str, Any]]:
    """Get legends linked to a specific city."""
    rows = conn.execute(
        """SELECT l.legend_id, l.legend_name, l.legend_slug,
                  l.year_reported, l.legend_level, l.legend_type,
                  l.legend_category, ll.role
           FROM dim_legend l
           JOIN dim_legend_location ll ON ll.legend_id = l.legend_id
           WHERE ll.city_id = ?
           ORDER BY l.year_reported""",
        (city_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_legend(conn: Any, legend_id: int) -> None:
    """Delete a legend and all related data."""
    row = conn.execute("SELECT legend_slug FROM dim_legend WHERE legend_id = ?", (legend_id,)).fetchone()
    if row:
        photo_dir = LEGEND_PHOTO_DIR / row[0]
        if photo_dir.exists():
            import shutil
            shutil.rmtree(photo_dir, ignore_errors=True)

    conn.execute("DELETE FROM dim_legend_photo WHERE legend_id = ?", (legend_id,))
    conn.execute("DELETE FROM dim_legend_location WHERE legend_id = ?", (legend_id,))
    conn.execute("DELETE FROM dim_legend WHERE legend_id = ?", (legend_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# Legend photos
# ---------------------------------------------------------------------------

def _legend_default_date(conn: Any, legend_id: int) -> str:
    """Return the legend's date_reported or year_reported, or empty."""
    row = conn.execute(
        "SELECT date_reported, year_reported FROM dim_legend WHERE legend_id = ?", (legend_id,)
    ).fetchone()
    if row:
        if row["date_reported"]:
            return row["date_reported"]
        if row["year_reported"]:
            return str(row["year_reported"])
    return ""


def _ensure_legend_photo_dir(legend_slug: str) -> Path:
    d = LEGEND_PHOTO_DIR / legend_slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_legend_photo(
    conn: Any,
    legend_id: int,
    legend_slug: str,
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

    photo_dir = _ensure_legend_photo_dir(legend_slug)
    unique_name = f"{uuid.uuid4().hex[:12]}{suffix}"
    dest = photo_dir / unique_name
    dest.write_bytes(file_bytes)

    if set_primary:
        conn.execute("UPDATE dim_legend_photo SET is_primary = FALSE WHERE legend_id = ?", (legend_id,))

    max_order = conn.execute(
        "SELECT COALESCE(MAX(photo_order), -1) FROM dim_legend_photo WHERE legend_id = ?",
        (legend_id,),
    ).fetchone()[0]

    conn.execute(
        """INSERT INTO dim_legend_photo
           (legend_id, filename, caption, source_url, attribution, is_primary, photo_order, image_url, photo_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (legend_id, unique_name, caption, source_url, attribution,
         bool(set_primary), max_order + 1, image_url,
         _legend_default_date(conn, legend_id)),
    )
    conn.commit()
    return {"success": True, "filename": unique_name}


def delete_legend_photo(conn: Any, legend_photo_id: int, legend_slug: str) -> None:
    row = conn.execute(
        "SELECT filename, is_primary, legend_id FROM dim_legend_photo WHERE legend_photo_id = ?",
        (legend_photo_id,),
    ).fetchone()
    if not row:
        return
    filepath = LEGEND_PHOTO_DIR / legend_slug / row["filename"]
    if filepath.exists():
        filepath.unlink()
    was_primary = row["is_primary"]
    legend_id = row["legend_id"]
    conn.execute("DELETE FROM dim_legend_photo WHERE legend_photo_id = ?", (legend_photo_id,))
    if was_primary:
        conn.execute(
            """UPDATE dim_legend_photo SET is_primary = TRUE
               WHERE legend_photo_id = (
                   SELECT legend_photo_id FROM dim_legend_photo
                   WHERE legend_id = ? ORDER BY photo_order LIMIT 1
               )""",
            (legend_id,),
        )
    conn.commit()


def set_legend_photo_primary(conn: Any, legend_photo_id: int, legend_id: int) -> None:
    conn.execute("UPDATE dim_legend_photo SET is_primary = FALSE WHERE legend_id = ?", (legend_id,))
    conn.execute("UPDATE dim_legend_photo SET is_primary = TRUE WHERE legend_photo_id = ?", (legend_photo_id,))
    conn.commit()


def get_legend_primary_photo(conn: Any, legend_slug: str) -> str | None:
    """Return the photo_path of the primary photo, or None."""
    row = conn.execute(
        """SELECT lp.filename FROM dim_legend_photo lp
           JOIN dim_legend l ON l.legend_id = lp.legend_id
           WHERE l.legend_slug = ? AND lp.is_primary = TRUE LIMIT 1""",
        (legend_slug,),
    ).fetchone()
    if row:
        return f"images/legends/{legend_slug}/{row[0]}"
    row = conn.execute(
        """SELECT lp.filename FROM dim_legend_photo lp
           JOIN dim_legend l ON l.legend_id = lp.legend_id
           WHERE l.legend_slug = ? ORDER BY lp.photo_order LIMIT 1""",
        (legend_slug,),
    ).fetchone()
    if row:
        return f"images/legends/{legend_slug}/{row[0]}"
    return None
