from __future__ import annotations

import ast
import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from flask import current_app, has_app_context

from .app_state import delete_raw_document, save_raw_document
from .city_photos import CITY_PHOTO_DIR, CITY_PHOTO_MANIFEST, clear_city_photo_manifest_cache

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DETAILS_DIR = PROJECT_ROOT / "data" / "city_details"
FICHES_DIR = PROJECT_ROOT / "data" / "city_fiches"

CANADIAN_PROVINCES = {
    "Québec", "Ontario", "British Columbia", "Alberta", "Manitoba",
    "Saskatchewan", "Nova Scotia", "New Brunswick", "Prince Edward Island",
    "Newfoundland and Labrador", "Northwest Territories", "Nunavut", "Yukon",
}

US_STATES = {
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine",
    "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi", "Missouri",
    "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey", "New Mexico",
    "New York", "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
    "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota", "Tennessee",
    "Texas", "Utah", "Vermont", "Virginia", "Washington", "West Virginia",
    "Wisconsin", "Wyoming", "District of Columbia",
}

REGION_ALIASES = {
    # French names — US states
    "Californie": "California",
    "Floride": "Florida",
    "Pennsylvanie": "Pennsylvania",
    "Caroline du Nord": "North Carolina",
    "Caroline du Sud": "South Carolina",
    "Virginie": "Virginia",
    "Géorgie": "Georgia",
    "Louisiane": "Louisiana",
    # French names — Canadian provinces
    "Colombie-Britannique": "British Columbia",
    "Nouveau-Brunswick": "New Brunswick",
    "Nouvelle-Écosse": "Nova Scotia",
    "Île-du-Prince-Édouard": "Prince Edward Island",
    "Terre-Neuve-et-Labrador": "Newfoundland and Labrador",
    "Territoires du Nord-Ouest": "Northwest Territories",
    # Quebec accent normalization
    "Quebec": "Québec",
    # Canadian province abbreviations
    "ON": "Ontario",
    "QC": "Québec",
    "BC": "British Columbia",
    "AB": "Alberta",
    "MB": "Manitoba",
    "SK": "Saskatchewan",
    "NS": "Nova Scotia",
    "NB": "New Brunswick",
    "PE": "Prince Edward Island",
    "NL": "Newfoundland and Labrador",
    "NT": "Northwest Territories",
    "NU": "Nunavut",
    "YT": "Yukon",
    # US state abbreviations (common ones)
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
    "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "DC": "District of Columbia",
}


def _should_update_legacy_city_manifest() -> bool:
    if not has_app_context():
        return True
    return current_app.config.get("DATABASE_BACKEND") != "postgresql"

USER_AGENT = "CentralCityScrutinizer/1.0 (city photo cache)"
SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
SEARCH_URL = "https://en.wikipedia.org/w/api.php?action=query&list=search&utf8=1&format=json&srlimit=5&srsearch={query}"

DbConnection = Any


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", normalized.strip().lower())
    return normalized.strip("-")


def split_location(raw_city_name: str) -> tuple[str | None, str]:
    if "," in raw_city_name:
        parts = [part.strip() for part in raw_city_name.split(",")]
        region = REGION_ALIASES.get(parts[-1], parts[-1])
        if region in CANADIAN_PROVINCES:
            return region, "Canada"
        if region in US_STATES:
            return region, "United States"
        # Handle composite regions like "Alberta/Saskatchewan"
        if "/" in region:
            sub = [s.strip() for s in region.split("/")]
            if any(s in CANADIAN_PROVINCES for s in sub):
                return sub[0], "Canada"
            if any(s in US_STATES for s in sub):
                return sub[0], "United States"
        return region, "Unknown"
    return None, "Unknown"


def build_period_label(year: int) -> str:
    if year < 1850:
        return "Pré-industriel"
    if year < 1945:
        return "Industrialisation"
    if year < 1975:
        return "Après-guerre"
    if year < 2000:
        return "Suburbanisation"
    return "Ère contemporaine"


def build_time_row(year: int) -> dict[str, Any]:
    quarter_start = (year // 25) * 25
    half_start = (year // 50) * 50
    century = ((year - 1) // 100) + 1
    return {
        "year": year,
        "decade": (year // 10) * 10,
        "quarter_century_label": f"{quarter_start}-{quarter_start + 24}",
        "half_century_label": f"{half_start}-{half_start + 49}",
        "century": century,
        "period_label": build_period_label(year),
    }


def _build_time_cache(conn: DbConnection) -> dict[int, int]:
    return {year: time_id for time_id, year in conn.execute("SELECT time_id, year FROM dim_time")}


def _upsert_annotation(conn: DbConnection, label: str, color: str) -> int:
    cursor = conn.execute(
        """
        INSERT INTO dim_annotation (annotation_label, annotation_color)
        VALUES (?, ?)
        ON CONFLICT(annotation_label, annotation_color)
        DO UPDATE SET annotation_color = excluded.annotation_color
        RETURNING annotation_id
        """,
        (label, color),
    )
    row = cursor.fetchone()
    if row is None:
        raise RuntimeError("Impossible de créer ou retrouver l'annotation.")
    return row[0]


def _delete_rows_by_ids(
    conn: DbConnection,
    table_name: str,
    id_column: str,
    ids: list[int],
) -> None:
    if not ids:
        return
    placeholders = ",".join("?" for _ in ids)
    conn.execute(
        f"DELETE FROM {table_name} WHERE {id_column} IN ({placeholders})",
        ids,
    )


# ---------------------------------------------------------------------------
# Stats text parser (Python format)
# ---------------------------------------------------------------------------

def parse_stats_text(text: str) -> dict[str, Any]:
    """Parse the Python-style stats block (CITY_NAME, CITY_COLOR, years, population, annotations)."""
    result: dict[str, Any] = {}

    city_match = re.search(r'CITY_NAME\s*=\s*"([^"]+)"', text)
    if not city_match:
        city_match = re.search(r"CITY_NAME\s*=\s*'([^']+)'", text)
    if not city_match:
        raise ValueError("CITY_NAME introuvable dans le texte.")
    result["raw_city_name"] = city_match.group(1)
    result["city_name"] = result["raw_city_name"].split(",", 1)[0].strip()

    color_match = re.search(r"CITY_COLOR\s*=\s*['\"](.+?)['\"]", text)
    result["city_color"] = color_match.group(1) if color_match else "#333333"

    # Foundation year
    fondation_match = re.search(r"fondation\s*=\s*['\"]?(\d{4})['\"]?", text, re.IGNORECASE)
    result["foundation_year"] = int(fondation_match.group(1)) if fondation_match else None

    years_match = re.search(r"years\s*=\s*\[([^\]]+)\]", text, re.DOTALL)
    if not years_match:
        raise ValueError("Liste 'years' introuvable.")
    result["years"] = [int(y.strip()) for y in years_match.group(1).split(",") if y.strip()]

    pop_match = re.search(r"population\s*=\s*\[([^\]]+)\]", text, re.DOTALL)
    if not pop_match:
        raise ValueError("Liste 'population' introuvable.")
    result["population"] = [int(p.strip()) for p in pop_match.group(1).split(",") if p.strip()]

    if len(result["years"]) != len(result["population"]):
        raise ValueError(
            f"years ({len(result['years'])}) et population ({len(result['population'])}) "
            f"n'ont pas la même longueur."
        )

    annotations: list[tuple] = []
    ann_match = re.search(r"annotations\s*=\s*\[(.+?)\]\s*$", text, re.DOTALL | re.MULTILINE)
    if ann_match:
        try:
            raw = ast.literal_eval("[" + ann_match.group(1) + "]")
            annotations = [tuple(a) for a in raw if isinstance(a, (list, tuple)) and len(a) >= 4]
        except Exception:
            pass
    result["annotations"] = annotations

    region, country = split_location(result["raw_city_name"])
    result["region"] = region
    result["country"] = country
    result["city_slug"] = slugify(result["raw_city_name"])

    return result


# ---------------------------------------------------------------------------
# Period details text parser (same format as .txt files)
# ---------------------------------------------------------------------------

def is_separator_line(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and all(c in {"━", "─", "-"} for c in stripped)


def parse_period_range(label: str) -> tuple[int | None, int | None]:
    label = label.strip()
    match = re.fullmatch(r"(?P<year>\d{4})", label)
    if match:
        y = int(match.group("year"))
        return y, y
    match = re.fullmatch(r"(?P<start>\d{4})-(?P<end>\d{4})", label)
    if match:
        return int(match.group("start")), int(match.group("end"))
    match = re.fullmatch(r"(?P<start>\d{4})s", label)
    if match:
        s = int(match.group("start"))
        return s, s + 9
    match = re.fullmatch(r"(?P<start>\d{4})s-(?P<end>\d{4})", label)
    if match:
        return int(match.group("start")), int(match.group("end"))
    years = [int(y) for y in re.findall(r"\b\d{4}\b", label)]
    if len(years) == 1:
        return years[0], years[0]
    if len(years) >= 2:
        return years[0], years[-1]
    return None, None


def parse_period_details_text(text: str) -> list[dict[str, Any]]:
    """Parse period-detail blocks from a raw text string (same format as city .txt files)."""
    lines = text.splitlines()
    sections: list[dict[str, Any]] = []
    index = 0

    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue

        if "—" not in line or index + 1 >= len(lines) or not is_separator_line(lines[index + 1]):
            index += 1
            continue

        period_range_label, period_title = [part.strip() for part in line.split("—", 1)]
        start_year, end_year = parse_period_range(period_range_label)
        index += 2

        items: list[str] = []
        while index < len(lines):
            raw_line = lines[index].rstrip()
            stripped = raw_line.strip()
            if not stripped:
                index += 1
                break
            if "—" in stripped and index + 1 < len(lines) and is_separator_line(lines[index + 1]):
                break
            items.append(stripped)
            index += 1

        if start_year is None or end_year is None:
            all_text = [period_range_label, period_title] + items
            found_years = []
            for t in all_text:
                found_years.extend(int(y) for y in re.findall(r"\b\d{4}\b", t))
            if found_years:
                start_year = start_year or min(found_years)
                end_year = end_year or max(found_years)

        sections.append({
            "period_range_label": period_range_label,
            "period_title": period_title,
            "start_year": start_year,
            "end_year": end_year,
            "items": items,
            "summary_text": "\n".join(items),
        })

    return sections


# Regex to detect period headers in AI-generated region text (no separator lines).
# Matches:  "1608–1763 — TITLE"  or  "1608-1763 — TITLE"
_REGION_PERIOD_HEADER_RE = re.compile(
    r"^(\d{4}\s*[–\-]\s*\d{4})\s*[—]\s*(.+)$"
)


def parse_region_period_details_text(text: str) -> list[dict[str, Any]]:
    """Parse period blocks from AI-generated region Step 2 text.

    Does not require separator lines — headers are detected by the
    ``YYYY–YYYY — TITLE`` pattern.  Lines starting with ``= Résumé``
    are extracted as the section summary_text rather than as bullet items.
    """
    lines = text.splitlines()
    sections: list[dict[str, Any]] = []
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        m = _REGION_PERIOD_HEADER_RE.match(line)
        if not m:
            i += 1
            continue

        period_range_label = m.group(1).strip()
        period_title = m.group(2).strip()
        start_year, end_year = parse_period_range(period_range_label)
        i += 1

        items: list[str] = []
        summary_lines: list[str] = []
        in_summary = False

        while i < len(lines):
            stripped = lines[i].strip()
            # Next period header → stop current section
            if _REGION_PERIOD_HEADER_RE.match(stripped):
                break
            # Start of résumé block
            if re.match(r"^=\s*Résumé", stripped, re.IGNORECASE):
                in_summary = True
                remainder = re.sub(r"^=\s*Résumé\s*:?\s*", "", stripped, flags=re.IGNORECASE).strip()
                if remainder:
                    summary_lines.append(remainder)
                i += 1
                continue
            if in_summary:
                if stripped:
                    summary_lines.append(stripped)
            else:
                if stripped:
                    items.append(stripped)
            i += 1

        sections.append({
            "period_range_label": period_range_label,
            "period_title": period_title,
            "start_year": start_year,
            "end_year": end_year,
            "items": items,
            "summary_text": " ".join(summary_lines) if summary_lines else "\n".join(items),
        })

    return sections


# ---------------------------------------------------------------------------
# Database import
# ---------------------------------------------------------------------------

def upsert_time_dimension(conn: DbConnection, time_cache: dict[int, int], year: int | None) -> int | None:
    if year is None:
        return None
    if year in time_cache:
        return time_cache[year]
    row = build_time_row(year)
    cursor = conn.execute(
        """
        INSERT INTO dim_time (year, decade, quarter_century_label, half_century_label, century, period_label)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(year) DO UPDATE SET
            decade = excluded.decade,
            quarter_century_label = excluded.quarter_century_label,
            half_century_label = excluded.half_century_label,
            century = excluded.century,
            period_label = excluded.period_label
        RETURNING time_id
        """,
        (row["year"], row["decade"], row["quarter_century_label"],
         row["half_century_label"], row["century"], row["period_label"]),
    )
    time_id = cursor.fetchone()[0]
    time_cache[year] = time_id
    return time_id


def _ascii_name(name: str) -> str:
    """Strip accents and lowercase for fuzzy name comparison."""
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()


def _resolve_duplicate_slug(conn: DbConnection, stats: dict[str, Any]) -> None:
    """If a city with the same accent-stripped name already exists in the same
    region, reuse its slug and name so the UPSERT merges instead of creating a
    duplicate (e.g. Philadelphie vs Philadelphia)."""
    if not stats.get("region"):
        return
    ascii_new = _ascii_name(stats["city_name"])
    rows = conn.execute(
        "SELECT city_name, city_slug FROM dim_city WHERE region = ? AND country = ?",
        (stats["region"], stats["country"]),
    ).fetchall()
    for row in rows:
        if _ascii_name(row[0]) == ascii_new and row[1] != stats["city_slug"]:
            stats["city_slug"] = row[1]
            stats["city_name"] = row[0]
            return


def import_city_stats(conn: DbConnection, stats: dict[str, Any]) -> int:
    """Insert/update dim_city + fact_city_population rows. Returns city_id."""
    _resolve_duplicate_slug(conn, stats)
    time_cache = _build_time_cache(conn)

    # Upsert dim_city
    cursor = conn.execute(
        """
        INSERT INTO dim_city (city_name, city_slug, region, country, city_color, foundation_year, source_file)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(city_slug) DO UPDATE SET
            city_name = excluded.city_name,
            region = excluded.region,
            country = excluded.country,
            city_color = excluded.city_color,
            foundation_year = COALESCE(excluded.foundation_year, dim_city.foundation_year),
            source_file = excluded.source_file
        RETURNING city_id
        """,
        (stats["city_name"], stats["city_slug"], stats["region"],
         stats["country"], stats["city_color"], stats.get("foundation_year"), "web-import"),
    )
    city_id = cursor.fetchone()[0]

    # Build annotation cache for this city
    annotation_by_year: dict[int, int] = {}
    for ann in stats["annotations"]:
        if len(ann) < 4:
            continue
        year, _pop, label, color = ann[:4]
        if not isinstance(year, int) or not isinstance(label, str) or not isinstance(color, str):
            continue
        annotation_by_year[year] = _upsert_annotation(conn, label, color)

    # Delete existing population rows for this city (to allow re-import)
    conn.execute("DELETE FROM fact_city_population WHERE city_id = ?", (city_id,))

    # Insert fact rows
    for year, population in zip(stats["years"], stats["population"]):
        time_id = upsert_time_dimension(conn, time_cache, year)
        conn.execute(
            """
            INSERT INTO fact_city_population (city_id, time_id, year, population, is_key_year, annotation_id, source_file)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (city_id, time_id, year, population,
             1 if year in annotation_by_year else 0,
             annotation_by_year.get(year), "web-import"),
        )

    return city_id


def import_city_periods(conn: DbConnection, city_id: int, city_slug: str, sections: list[dict[str, Any]]) -> int:
    """Insert period detail rows. Returns count of periods inserted."""
    time_cache = _build_time_cache(conn)

    # Remove existing periods for this city
    existing_ids = [
        row[0] for row in conn.execute(
            "SELECT period_detail_id FROM dim_city_period_detail WHERE city_id = ?", (city_id,)
        )
    ]
    if existing_ids:
        _delete_rows_by_ids(conn, "dim_city_period_detail_item", "period_detail_id", existing_ids)
        conn.execute("DELETE FROM dim_city_period_detail WHERE city_id = ?", (city_id,))

    count = 0
    for order, section in enumerate(sections, start=1):
        start_time_id = upsert_time_dimension(conn, time_cache, section["start_year"])
        end_time_id = upsert_time_dimension(conn, time_cache, section["end_year"])
        cursor = conn.execute(
            """
            INSERT INTO dim_city_period_detail
                (city_id, period_order, period_range_label, period_title,
                 start_year, end_year, start_time_id, end_time_id, summary_text, source_file)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING period_detail_id
            """,
            (city_id, order, section["period_range_label"], section["period_title"],
             section["start_year"], section["end_year"], start_time_id, end_time_id,
             section["summary_text"], f"{city_slug}.txt"),
        )
        period_detail_id = cursor.fetchone()[0]
        count += 1
        for item_order, item_text in enumerate(section["items"], start=1):
            conn.execute(
                "INSERT INTO dim_city_period_detail_item (period_detail_id, item_order, item_text) VALUES (?, ?, ?)",
                (period_detail_id, item_order, item_text),
            )

    return count


def save_period_details_file(city_slug: str, text: str) -> Path:
    """Save the period details text as a .txt file in data/city_details/."""
    file_path = DETAILS_DIR / f"{city_slug}.txt"
    save_raw_document("city", city_slug, "period_detail", text, fallback_path=file_path)
    return file_path


# ---------------------------------------------------------------------------
# Photo fetch (reuses Wikipedia API logic from fetch_city_photos.py)
# ---------------------------------------------------------------------------

def _http_get_json(url: str) -> dict:
    last_error: Exception | None = None
    for attempt in range(4):
        req = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(req) as response:
                return json.load(response)
        except HTTPError as exc:
            last_error = exc
            if exc.code not in {403, 429, 500, 502, 503, 504}:
                raise
        except URLError as exc:
            last_error = exc
        time.sleep(0.6 * (attempt + 1))
    if last_error:
        raise last_error
    raise RuntimeError("HTTP request failed.")


def _fetch_summary(title: str) -> dict | None:
    url = SUMMARY_URL.format(title=quote(title.replace(" ", "_"), safe="_(),.-"))
    try:
        return _http_get_json(url)
    except Exception:
        return None


def _search_titles(query: str) -> list[str]:
    try:
        data = _http_get_json(SEARCH_URL.format(query=quote(query)))
    except Exception:
        return []
    results = data.get("query", {}).get("search", [])
    return [r["title"] for r in results if isinstance(r.get("title"), str)]


def _select_image(summary: dict) -> str | None:
    """Pick the best image URL from a Wikipedia summary, preferring a 1280px thumbnail."""
    import re as _re

    def _make_hd_thumb(url: str) -> str:
        """Rewrite a Wikimedia thumb URL to request 1280px width."""
        if "/thumb/" in url:
            parts = url.rsplit("/", 1)
            if len(parts) == 2:
                new_last = _re.sub(r"^\d+px-", "1280px-", parts[1])
                return f"{parts[0]}/{new_last}"
        return url

    # Prefer thumbnail rewritten to 1280px (Wikimedia-approved)
    thumbnail = summary.get("thumbnail", {})
    if isinstance(thumbnail, dict) and isinstance(thumbnail.get("source"), str):
        return _make_hd_thumb(thumbnail["source"])
    # Fallback to original
    original = summary.get("originalimage", {})
    if isinstance(original, dict) and isinstance(original.get("source"), str):
        return original["source"]
    return None


def _build_region_variants(region: str) -> list[str]:
    if not region:
        return []
    normalized = unicodedata.normalize("NFKD", region).encode("ascii", "ignore").decode("ascii")
    variants = [region, normalized]
    return list(dict.fromkeys(v for v in variants if v))


def fetch_and_save_city_photo(city_slug: str, city_name: str, region: str | None, country: str | None) -> dict[str, Any]:
    """Fetch a photo from Wikipedia and save it locally. Returns status dict."""
    CITY_PHOTO_DIR.mkdir(parents=True, exist_ok=True)

    # Build candidate titles
    candidates = [city_name]
    if region:
        for rv in _build_region_variants(region):
            candidates.append(f"{city_name}, {rv}")
    if country:
        candidates.append(f"{city_name}, {country}")

    image_url = None
    summary = None
    searched: list[str] = []

    for title in candidates:
        s = _fetch_summary(title)
        if s:
            img = _select_image(s)
            if img:
                image_url, summary = img, s
                break
            searched.extend(_search_titles(title))

    if not image_url:
        for title in searched:
            s = _fetch_summary(title)
            if s:
                img = _select_image(s)
                if img:
                    image_url, summary = img, s
                    break

    if not image_url or not summary:
        return {"success": False, "error": "Aucune photo trouvée sur Wikipedia."}

    suffix = Path(urlsplit(image_url).path).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    filename = f"{city_slug}{suffix}"
    destination = CITY_PHOTO_DIR / filename

    last_error: Exception | None = None
    for attempt in range(4):
        req = Request(image_url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(req) as resp:
                destination.write_bytes(resp.read())
            last_error = None
            break
        except (HTTPError, URLError) as exc:
            last_error = exc
            time.sleep(0.8 * (attempt + 1))

    if last_error:
        return {"success": False, "error": f"Téléchargement échoué: {last_error}"}

    source_page = summary.get("content_urls", {}).get("desktop", {}).get("page", "")
    if _should_update_legacy_city_manifest():
        manifest: dict[str, Any] = {}
        if CITY_PHOTO_MANIFEST.exists():
            try:
                manifest = json.loads(CITY_PHOTO_MANIFEST.read_text(encoding="utf-8"))
            except Exception:
                manifest = {}

        manifest[city_slug] = {
            "filename": filename,
            "source_page": source_page,
            "source_image": image_url,
            "attribution": "Image cachee depuis Wikipedia/Wikimedia, verifier les licences en cas de redistribution.",
        }
        CITY_PHOTO_MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        clear_city_photo_manifest_cache()

    return {"success": True, "filename": filename, "source_page": source_page}


def save_uploaded_photo(city_slug: str, file_storage: Any) -> dict[str, Any]:
    """Save a user-uploaded photo file. file_storage is a werkzeug FileStorage."""
    CITY_PHOTO_DIR.mkdir(parents=True, exist_ok=True)

    original_name = file_storage.filename or ""
    suffix = Path(original_name).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        return {"success": False, "error": "Format non supporté. Utilisez JPG, PNG ou WebP."}

    filename = f"{city_slug}{suffix}"
    destination = CITY_PHOTO_DIR / filename
    file_storage.save(str(destination))

    # Update manifest
    manifest: dict[str, Any] = {}
    if _should_update_legacy_city_manifest() and CITY_PHOTO_MANIFEST.exists():
        try:
            manifest = json.loads(CITY_PHOTO_MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}

    if _should_update_legacy_city_manifest():
        manifest[city_slug] = {
            "filename": filename,
            "source_page": "",
            "source_image": "upload",
            "attribution": "Photo uploadée manuellement.",
        }
        CITY_PHOTO_MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        clear_city_photo_manifest_cache()

    return {"success": True, "filename": filename}


# ---------------------------------------------------------------------------
# Fiche Complète parser
# ---------------------------------------------------------------------------

_NOISE_LINES = {"Copier le tableau", "Copier", "Copy table"}
_NOISE_RE = re.compile(r"^[-|:\s]+$")
_MD_SECTION_RE = re.compile(r"^#{1,3}\s+([^\w\s]{1,4})\s+(.+)$", re.UNICODE)
_EMOJI_SECTION_RE = re.compile(r"^([^\w\s]{1,4})\s+(.+)$", re.UNICODE)
_PIPE_ROW_RE = re.compile(r"^\|(.+)\|$")
_HR_RE = re.compile(r"^-{3,}$")


def _is_noise(line: str) -> bool:
    stripped = line.strip()
    return stripped in _NOISE_LINES or bool(_HR_RE.match(stripped))


def _is_pipe_separator(line: str) -> bool:
    """Detect pipe-table separator lines like |---|---|"""
    return bool(re.fullmatch(r"\|[-:\s|]+\|", line.strip()))


def _parse_pipe_row(line: str) -> list[str] | None:
    """Parse a markdown pipe table row. Returns cells or None."""
    stripped = line.strip()
    m = _PIPE_ROW_RE.match(stripped)
    if not m:
        return None
    cells = [c.strip() for c in m.group(1).split("|")]
    return cells if len(cells) >= 2 else None


def _is_section_header(line: str) -> tuple[str, str] | None:
    """Return (emoji, title) if line is a section header, else None.
    Handles both '## 📍 Title' markdown and '📍 Title' plain formats."""
    stripped = line.strip()
    if not stripped:
        return None

    # Pipe table rows are never headers
    if stripped.startswith("|"):
        return None

    # Try markdown format: ## 📍 Title or ### 📍 Title
    m = _MD_SECTION_RE.match(stripped)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    # Lines starting with # but not matching MD section emoji pattern are not headers
    if stripped.startswith("#"):
        return None

    # Try plain emoji format: 📍 Title (short titles only, ≤ 3 words)
    m = _EMOJI_SECTION_RE.match(stripped)
    if m:
        emoji, title = m.group(1).strip(), m.group(2).strip()
        # Reject if title contains markdown bold (it's content, not a header)
        if "**" in title:
            return None
        if title and len(title) > 2 and len(title.split()) <= 3:
            return emoji, title
    return None


def parse_fiche_text(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Parse a fiche complète text into city header and sections.
    Handles markdown pipe tables, ## headers, bullet lists, and plain text.
    """
    raw_lines = text.splitlines()

    # Extract header (first meaningful line, e.g. "# London, Ontario — Fiche Complète")
    header = ""
    start = 0
    for i, line in enumerate(raw_lines):
        stripped = line.strip().lstrip("#").strip()
        if stripped and not _is_noise(line):
            if "fiche" in stripped.lower() or "—" in stripped:
                header = stripped
                start = i + 1
                break
            header = stripped
            start = i + 1
            break

    # Split into sections by section headers
    sections: list[dict[str, Any]] = []
    current_section: dict[str, Any] | None = None
    current_lines: list[str] = []

    def _flush_section():
        nonlocal current_section, current_lines
        if current_section is not None:
            current_section["_raw_lines"] = [l for l in current_lines]
            sections.append(current_section)
            current_lines = []
            current_section = None

    for i in range(start, len(raw_lines)):
        line = raw_lines[i]
        stripped = line.strip()

        # Skip noise
        if _is_noise(line):
            continue

        if not stripped:
            if current_lines and current_lines[-1] != "":
                current_lines.append("")
            continue

        header_match = _is_section_header(stripped)
        if header_match:
            _flush_section()
            emoji, title = header_match
            current_section = {"emoji": emoji, "title": title, "blocks": []}
            current_lines = []
            continue

        # Skip ### sub-headers (e.g. "### Secteurs Principaux :") — keep as text
        if stripped.startswith("###"):
            stripped = stripped.lstrip("#").strip()

        if current_section is not None:
            current_lines.append(stripped)

    _flush_section()

    # Parse content blocks within each section
    for section in sections:
        raw = section.pop("_raw_lines")
        blocks = _parse_content_blocks(raw)
        section["blocks"] = blocks

    return header, sections


def _parse_content_blocks(lines: list[str]) -> list[dict[str, Any]]:
    """Parse lines into blocks: pipe-tables, tab-tables, bullets, and text."""
    blocks: list[dict[str, Any]] = []
    if not lines:
        return blocks

    i = 0
    pending_bullets: list[str] = []
    pending_text: list[str] = []

    def flush_bullets():
        nonlocal pending_bullets
        if pending_bullets:
            blocks.append({"type": "bullets", "items": list(pending_bullets)})
            pending_bullets = []

    def flush_text():
        nonlocal pending_text
        if pending_text:
            blocks.append({"type": "text", "value": " ".join(pending_text)})
            pending_text = []

    while i < len(lines):
        line = lines[i].strip()

        if not line:
            i += 1
            continue

        if line in _NOISE_LINES or _is_pipe_separator(line):
            i += 1
            continue

        # --- Try pipe table ---
        pipe_cells = _parse_pipe_row(line)
        if pipe_cells:
            flush_bullets()
            flush_text()
            # Collect all consecutive pipe rows (skip blanks + separators)
            headers = pipe_cells
            rows: list[list[str]] = []
            i += 1
            while i < len(lines):
                row_line = lines[i].strip()
                if not row_line or _is_pipe_separator(row_line):
                    i += 1
                    continue
                row_cells = _parse_pipe_row(row_line)
                if row_cells:
                    rows.append(row_cells)
                    i += 1
                else:
                    break
            blocks.append({"type": "table", "headers": headers, "rows": rows})
            continue

        # --- Try tab table ---
        if "\t" in line:
            flush_bullets()
            flush_text()
            headers_tab = [h.strip() for h in line.split("\t") if h.strip()]
            if len(headers_tab) >= 2:
                rows_tab: list[list[str]] = []
                i += 1
                while i < len(lines):
                    row_line = lines[i].strip()
                    if not row_line or row_line in _NOISE_LINES:
                        i += 1
                        continue
                    if _is_section_header(row_line):
                        break
                    if "\t" in row_line:
                        cells = [c.strip() for c in row_line.split("\t")]
                        rows_tab.append(cells)
                        i += 1
                    else:
                        break
                blocks.append({"type": "table", "headers": headers_tab, "rows": rows_tab})
                continue

        # --- Bullet item ---
        is_bullet = bool(re.match(r"^(?:[-*]\s|[^\w\s]{1,3}\s)", line))
        if not is_bullet and " — " in line:
            is_bullet = True
        if is_bullet:
            flush_text()
            # Clean up leading "- " prefix
            cleaned = re.sub(r"^[-*]\s+", "", line)
            pending_bullets.append(cleaned)
            i += 1
            continue

        # --- Plain text ---
        flush_bullets()
        pending_text.append(line)
        i += 1

    flush_bullets()
    flush_text()

    return blocks


# ---------------------------------------------------------------------------
# Fiche Complète database import
# ---------------------------------------------------------------------------

def import_city_fiche(conn: DbConnection, city_id: int, city_slug: str,
                      raw_text: str, sections: list[dict[str, Any]]) -> int:
    """Insert/update fiche complète for a city. Saves to DB + .txt file. Returns fiche_id."""
    # Remove existing fiche
    existing = conn.execute(
        "SELECT fiche_id FROM dim_city_fiche WHERE city_id = ?", (city_id,)
    ).fetchone()
    if existing:
        conn.execute("DELETE FROM dim_city_fiche_section WHERE fiche_id = ?", (existing[0],))
        conn.execute("DELETE FROM dim_city_fiche WHERE fiche_id = ?", (existing[0],))

    cursor = conn.execute(
        "INSERT INTO dim_city_fiche (city_id, raw_text) VALUES (?, ?) RETURNING fiche_id",
        (city_id, raw_text),
    )
    fiche_id = cursor.fetchone()[0]

    for order, section in enumerate(sections, start=1):
        conn.execute(
            """INSERT INTO dim_city_fiche_section
               (fiche_id, section_order, section_emoji, section_title, content_json)
               VALUES (?, ?, ?, ?, ?)""",
            (fiche_id, order, section.get("emoji", ""),
             section["title"], json.dumps(section["blocks"], ensure_ascii=False)),
        )

    # Save raw text to file
    save_fiche_file(city_slug, raw_text)

    # Extract density/area from geography section and update dim_city
    _update_density_from_fiche(conn, city_id, sections)

    return fiche_id


def _parse_fiche_number(val: str) -> float | None:
    """Extract numeric value from fiche strings like '~1 050 hab./km²' or '**~420 km²**'."""
    val = val.replace("\u202f", " ").replace("\xa0", " ")
    val = val.replace("**", "").replace("~", "").strip()
    val = re.sub(r"\s*(hab\.?/km²|km²|hectares?|m\b).*", "", val, flags=re.IGNORECASE)
    val = val.replace(" ", "")
    if val.count(",") == 1 and val.count(".") == 0:
        val = val.replace(",", ".")
    else:
        val = val.replace(",", "")
    try:
        return float(val)
    except ValueError:
        return None


def _update_density_from_fiche(conn: DbConnection, city_id: int,
                               sections: list[dict[str, Any]]) -> None:
    """Extract area_km2 and density from fiche geography section and update dim_city."""
    area: float | None = None
    density: float | None = None

    for section in sections:
        title = section.get("title", "").lower()
        if "ographie" not in title and "ensit" not in title:
            continue
        for block in section.get("blocks", []):
            if block.get("type") == "table":
                for row in block.get("rows", []):
                    if len(row) < 2:
                        continue
                    label = row[0].lower()
                    if area is None and ("superficie" in label or "surface" in label) \
                            and "rmr" not in label and "brûlé" not in label:
                        area = _parse_fiche_number(row[1])
                    elif density is None and "densit" in label and "manhattan" not in label:
                        density = _parse_fiche_number(row[1])
            elif block.get("type") == "text":
                text = block.get("value", "")
                if area is None:
                    m = re.search(r"Superficie\s*[~:]?\s*([\d\s,.]+)\s*km", text)
                    if m:
                        area = _parse_fiche_number(m.group(1))
                if density is None:
                    m = re.search(r"Densit[eé]\s*[~:]?\s*([\d\s,.]+)\s*hab", text)
                    if m:
                        density = _parse_fiche_number(m.group(1))

    if area is not None or density is not None:
        conn.execute(
            "UPDATE dim_city SET area_km2 = COALESCE(?, area_km2), density = COALESCE(?, density) WHERE city_id = ?",
            (area, density, city_id),
        )


def delete_city_fiche(conn: DbConnection, city_id: int, city_slug: str) -> bool:
    """Delete fiche complète from DB and remove .txt file."""
    existing = conn.execute(
        "SELECT fiche_id FROM dim_city_fiche WHERE city_id = ?", (city_id,)
    ).fetchone()
    if not existing:
        return False
    conn.execute("DELETE FROM dim_city_fiche_section WHERE fiche_id = ?", (existing[0],))
    conn.execute("DELETE FROM dim_city_fiche WHERE fiche_id = ?", (existing[0],))
    file_path = FICHES_DIR / f"{city_slug}.txt"
    delete_raw_document("city", city_slug, "fiche", fallback_path=file_path)
    return True


def save_fiche_file(city_slug: str, text: str) -> Path:
    """Save the fiche complète raw text as a .txt file in data/city_fiches/."""
    file_path = FICHES_DIR / f"{city_slug}.txt"
    save_raw_document("city", city_slug, "fiche", text, fallback_path=file_path)
    return file_path


def get_city_fiche(conn: DbConnection, city_id: int) -> dict[str, Any] | None:
    """Load a city's fiche complète with all sections."""
    fiche = conn.execute(
        "SELECT fiche_id, raw_text, created_at FROM dim_city_fiche WHERE city_id = ?",
        (city_id,),
    ).fetchone()
    if not fiche:
        return None

    sections = conn.execute(
        """SELECT section_emoji, section_title, content_json
           FROM dim_city_fiche_section
           WHERE fiche_id = ?
           ORDER BY section_order""",
        (fiche[0],),
    ).fetchall()

    return {
        "fiche_id": fiche[0],
        "raw_text": fiche[1],
        "created_at": fiche[2],
        "sections": [
            {
                "emoji": row[0],
                "title": row[1],
                "blocks": json.loads(row[2]),
            }
            for row in sections
        ],
    }


# ---------------------------------------------------------------------------
# Country stats parser (Python format)
# ---------------------------------------------------------------------------

def parse_country_stats_text(text: str) -> dict[str, Any]:
    """Parse a Python-style country stats block (COUNTRY_NAME, COUNTRY_COLOR, years, population, annotations)."""
    result: dict[str, Any] = {}

    name_match = re.search(r'COUNTRY_NAME\s*=\s*"([^"]+)"', text)
    if not name_match:
        name_match = re.search(r"COUNTRY_NAME\s*=\s*'([^']+)'", text)
    if not name_match:
        raise ValueError("COUNTRY_NAME introuvable dans le texte.")
    result["country_name"] = name_match.group(1).strip()

    color_match = re.search(r"COUNTRY_COLOR\s*=\s*['\"](.+?)['\"]", text)
    result["country_color"] = color_match.group(1) if color_match else "#333333"

    years_match = re.search(r"years\s*=\s*\[([^\]]+)\]", text, re.DOTALL)
    if not years_match:
        raise ValueError("Liste 'years' introuvable.")
    result["years"] = [int(y.strip()) for y in years_match.group(1).split(",") if y.strip()]

    pop_match = re.search(r"population\s*=\s*\[([^\]]+)\]", text, re.DOTALL)
    if not pop_match:
        raise ValueError("Liste 'population' introuvable.")
    result["population"] = [int(p.strip()) for p in pop_match.group(1).split(",") if p.strip()]

    if len(result["years"]) != len(result["population"]):
        raise ValueError(
            f"years ({len(result['years'])}) et population ({len(result['population'])}) "
            f"n'ont pas la même longueur."
        )

    annotations: list[tuple] = []
    ann_match = re.search(r"annotations\s*=\s*\[(.+?)\]\s*$", text, re.DOTALL | re.MULTILINE)
    if ann_match:
        try:
            raw = ast.literal_eval("[" + ann_match.group(1) + "]")
            annotations = [tuple(a) for a in raw if isinstance(a, (list, tuple)) and len(a) >= 4]
        except Exception:
            pass
    result["annotations"] = annotations

    result["country_slug"] = slugify(result["country_name"])

    return result


# ---------------------------------------------------------------------------
# Country database import
# ---------------------------------------------------------------------------

def import_country_stats(conn: DbConnection, stats: dict[str, Any]) -> int:
    """Insert/update dim_country + fact_country_population rows. Returns country_id."""
    time_cache = _build_time_cache(conn)

    # Upsert dim_country
    cursor = conn.execute(
        """
        INSERT INTO dim_country (country_name, country_slug, country_color, source_file)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(country_slug) DO UPDATE SET
            country_name = excluded.country_name,
            country_color = excluded.country_color,
            source_file = excluded.source_file
        RETURNING country_id
        """,
        (stats["country_name"], stats["country_slug"], stats["country_color"], "web-import"),
    )
    country_id = cursor.fetchone()[0]

    # Build annotation cache
    annotation_by_year: dict[int, int] = {}
    for ann in stats["annotations"]:
        if len(ann) < 4:
            continue
        year, _pop, label, color = ann[:4]
        if not isinstance(year, int) or not isinstance(label, str) or not isinstance(color, str):
            continue
        annotation_by_year[year] = _upsert_annotation(conn, label, color)

    # Delete existing population rows for this country (to allow re-import)
    conn.execute("DELETE FROM fact_country_population WHERE country_id = ?", (country_id,))

    # Insert fact rows
    for year, population in zip(stats["years"], stats["population"]):
        time_id = upsert_time_dimension(conn, time_cache, year)
        conn.execute(
            """
            INSERT INTO fact_country_population (country_id, time_id, year, population, is_key_year, annotation_id, source_file)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (country_id, time_id, year, population,
             1 if year in annotation_by_year else 0,
             annotation_by_year.get(year), "web-import"),
        )

    return country_id


COUNTRY_DETAILS_DIR = PROJECT_ROOT / "data" / "country_details"
COUNTRY_FICHES_DIR = PROJECT_ROOT / "data" / "country_fiches"


def save_country_details_file(country_slug: str, text: str) -> Path:
    """Save the country details raw text as a .txt file in data/country_details/."""
    file_path = COUNTRY_DETAILS_DIR / f"{country_slug}.txt"
    save_raw_document("country", country_slug, "period_detail", text, fallback_path=file_path)
    return file_path


def save_country_fiche_file(country_slug: str, text: str) -> Path:
    """Save the country fiche complète as a .txt file in data/country_fiches/."""
    file_path = COUNTRY_FICHES_DIR / f"{country_slug}.txt"
    save_raw_document("country", country_slug, "fiche", text, fallback_path=file_path)
    return file_path


# Mapping of common country names to ISO 3166-1 alpha-2 codes (flagcdn.com format)
_COUNTRY_ISO2: dict[str, str] = {
    "Afghanistan": "af", "Albania": "al", "Algeria": "dz", "Andorra": "ad",
    "Angola": "ao", "Antigua and Barbuda": "ag", "Argentina": "ar", "Armenia": "am",
    "Australia": "au", "Austria": "at", "Azerbaijan": "az", "Bahamas": "bs",
    "Bahrain": "bh", "Bangladesh": "bd", "Barbados": "bb", "Belarus": "by",
    "Belgium": "be", "Belize": "bz", "Benin": "bj", "Bhutan": "bt",
    "Bolivia": "bo", "Bosnia and Herzegovina": "ba", "Botswana": "bw", "Brazil": "br",
    "Brunei": "bn", "Bulgaria": "bg", "Burkina Faso": "bf", "Burundi": "bi",
    "Cabo Verde": "cv", "Cambodia": "kh", "Cameroon": "cm", "Canada": "ca",
    "Central African Republic": "cf", "Chad": "td", "Chile": "cl", "China": "cn",
    "Colombia": "co", "Comoros": "km", "Congo": "cg", "Costa Rica": "cr",
    "Croatia": "hr", "Cuba": "cu", "Cyprus": "cy", "Czech Republic": "cz",
    "Czechia": "cz", "Denmark": "dk", "Djibouti": "dj", "Dominica": "dm",
    "Dominican Republic": "do", "Ecuador": "ec", "Egypt": "eg", "El Salvador": "sv",
    "Equatorial Guinea": "gq", "Eritrea": "er", "Estonia": "ee", "Eswatini": "sz",
    "Ethiopia": "et", "Fiji": "fj", "Finland": "fi", "France": "fr",
    "Gabon": "ga", "Gambia": "gm", "Georgia": "ge", "Germany": "de",
    "Ghana": "gh", "Greece": "gr", "Grenada": "gd", "Guatemala": "gt",
    "Guinea": "gn", "Guinea-Bissau": "gw", "Guyana": "gy", "Haiti": "ht",
    "Honduras": "hn", "Hungary": "hu", "Iceland": "is", "India": "in",
    "Indonesia": "id", "Iran": "ir", "Iraq": "iq", "Ireland": "ie",
    "Israel": "il", "Italy": "it", "Jamaica": "jm", "Japan": "jp",
    "Jordan": "jo", "Kazakhstan": "kz", "Kenya": "ke", "Kiribati": "ki",
    "Kuwait": "kw", "Kyrgyzstan": "kg", "Laos": "la", "Latvia": "lv",
    "Lebanon": "lb", "Lesotho": "ls", "Liberia": "lr", "Libya": "ly",
    "Liechtenstein": "li", "Lithuania": "lt", "Luxembourg": "lu", "Madagascar": "mg",
    "Malawi": "mw", "Malaysia": "my", "Maldives": "mv", "Mali": "ml",
    "Malta": "mt", "Marshall Islands": "mh", "Mauritania": "mr", "Mauritius": "mu",
    "Mexico": "mx", "Micronesia": "fm", "Moldova": "md", "Monaco": "mc",
    "Mongolia": "mn", "Montenegro": "me", "Morocco": "ma", "Mozambique": "mz",
    "Myanmar": "mm", "Namibia": "na", "Nauru": "nr", "Nepal": "np",
    "Netherlands": "nl", "New Zealand": "nz", "Nicaragua": "ni", "Niger": "ne",
    "Nigeria": "ng", "North Korea": "kp", "North Macedonia": "mk", "Norway": "no",
    "Oman": "om", "Pakistan": "pk", "Palau": "pw", "Panama": "pa",
    "Papua New Guinea": "pg", "Paraguay": "py", "Peru": "pe", "Philippines": "ph",
    "Poland": "pl", "Portugal": "pt", "Qatar": "qa", "Romania": "ro",
    "Russia": "ru", "Rwanda": "rw", "Saint Kitts and Nevis": "kn",
    "Saint Lucia": "lc", "Saint Vincent and the Grenadines": "vc", "Samoa": "ws",
    "San Marino": "sm", "Sao Tome and Principe": "st", "Saudi Arabia": "sa",
    "Senegal": "sn", "Serbia": "rs", "Seychelles": "sc", "Sierra Leone": "sl",
    "Singapore": "sg", "Slovakia": "sk", "Slovenia": "si", "Solomon Islands": "sb",
    "Somalia": "so", "South Africa": "za", "South Korea": "kr", "South Sudan": "ss",
    "Spain": "es", "Sri Lanka": "lk", "Sudan": "sd", "Suriname": "sr",
    "Sweden": "se", "Switzerland": "ch", "Syria": "sy", "Taiwan": "tw",
    "Tajikistan": "tj", "Tanzania": "tz", "Thailand": "th", "Timor-Leste": "tl",
    "Togo": "tg", "Tonga": "to", "Trinidad and Tobago": "tt", "Tunisia": "tn",
    "Turkey": "tr", "Turkmenistan": "tm", "Tuvalu": "tv", "Uganda": "ug",
    "Ukraine": "ua", "United Arab Emirates": "ae", "United Kingdom": "gb",
    "United States": "us", "United States of America": "us", "Uruguay": "uy",
    "Uzbekistan": "uz", "Vanuatu": "vu", "Vatican City": "va", "Venezuela": "ve",
    "Vietnam": "vn", "Yemen": "ye", "Zambia": "zm", "Zimbabwe": "zw",
    # Alias variants (English)
    "DR Congo": "cd", "Democratic Republic of the Congo": "cd",
    "Republic of the Congo": "cg", "South Korea": "kr", "North Korea": "kp",
    "Ivory Coast": "ci", "Côte d'Ivoire": "ci", "Cote d'Ivoire": "ci",
    "Cape Verde": "cv", "East Timor": "tl", "Swaziland": "sz",
    "Burma": "mm", "Réunion": "re", "Kosovo": "xk",
    # French country name aliases
    "États-Unis": "us", "Etats-Unis": "us", "USA": "us",
    "Royaume-Uni": "gb", "Grande-Bretagne": "gb",
    "Allemagne": "de", "Espagne": "es", "Italie": "it", "Grèce": "gr",
    "Suède": "se", "Finlande": "fi", "Norvège": "no", "Danemark": "dk",
    "Pologne": "pl", "Hongrie": "hu", "Roumanie": "ro", "Bulgarie": "bg",
    "Tchéquie": "cz", "République tchèque": "cz", "Slovaquie": "sk",
    "Slovénie": "si", "Croatie": "hr", "Serbie": "rs",
    "Suisse": "ch", "Autriche": "at", "Belgique": "be",
    "Pays-Bas": "nl", "Irlande": "ie", "Portugal": "pt",
    "Russie": "ru", "Biélorussie": "by", "Bélarus": "by",
    "Ukraine": "ua", "Géorgie": "ge", "Arménie": "am", "Azerbaïdjan": "az",
    "Kazakhstan": "kz", "Ouzbékistan": "uz", "Kirghizistan": "kg",
    "Tadjikistan": "tj", "Turkménistan": "tm", "Mongolie": "mn",
    "Chine": "cn", "Japon": "jp", "Corée du Sud": "kr", "Corée du Nord": "kp",
    "Inde": "in", "Pakistan": "pk", "Bangladesh": "bd",
    "Thaïlande": "th", "Viêt Nam": "vn", "Viet Nam": "vn",
    "Cambodge": "kh", "Birmanie": "mm", "Indonésie": "id",
    "Philippines": "ph", "Malaisie": "my", "Singapour": "sg",
    "Timor oriental": "tl", "Australie": "au", "Nouvelle-Zélande": "nz",
    "Maroc": "ma", "Algérie": "dz", "Tunisie": "tn", "Libye": "ly",
    "Égypte": "eg", "Soudan": "sd", "Éthiopie": "et", "Érythrée": "er",
    "Somalie": "so", "Kenya": "ke", "Kénya": "ke", "Tanzanie": "tz",
    "Mozambique": "mz", "Afrique du Sud": "za",
    "Nigéria": "ng", "Sénégal": "sn", "Burkina Faso": "bf", "Niger": "ne",
    "Tchad": "td", "Cameroun": "cm", "République centrafricaine": "cf",
    "Congo": "cg", "République démocratique du Congo": "cd",
    "Brésil": "br", "Mexique": "mx", "Argentine": "ar", "Colombie": "co",
    "Chili": "cl", "Pérou": "pe", "Vénézuéla": "ve", "Venezuela": "ve",
    "Équateur": "ec", "Bolivie": "bo",
    "Arabie saoudite": "sa", "Arabie Saoudite": "sa",
    "Émirats arabes unis": "ae", "Émirats Arabes Unis": "ae",
    "Irak": "iq", "Syrie": "sy", "Turquie": "tr", "Türkiye": "tr",
    "Liban": "lb", "Israël": "il", "Jordanie": "jo",
    "Koweït": "kw", "Bahreïn": "bh", "Yémen": "ye",
    "Roumanie": "ro", "Macédoine du Nord": "mk",
}


def download_country_flag(country_name: str, country_slug: str) -> str | None:
    """Download the flag for a country from flagcdn.com and save to static/images/flags/countries/.

    Returns the relative URL path (e.g. 'images/flags/countries/canada.png') or None on failure.
    """
    import urllib.request
    import urllib.error

    iso2 = _COUNTRY_ISO2.get(country_name)
    if not iso2:
        # Try case-insensitive lookup
        name_lower = country_name.lower()
        for k, v in _COUNTRY_ISO2.items():
            if k.lower() == name_lower:
                iso2 = v
                break
    if not iso2:
        return None

    flags_dir = PROJECT_ROOT / "static" / "images" / "flags" / "countries"
    flags_dir.mkdir(parents=True, exist_ok=True)
    dest = flags_dir / f"{country_slug}.png"

    if dest.exists():
        return f"images/flags/countries/{country_slug}.png"

    url = f"https://flagcdn.com/w160/{iso2}.png"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        if len(data) < 100:
            return None
        dest.write_bytes(data)
        return f"images/flags/countries/{country_slug}.png"
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return None


# ---------------------------------------------------------------------------
# Region stats parser (Python format)
# ---------------------------------------------------------------------------

REGION_DETAILS_DIR = PROJECT_ROOT / "data" / "region_details"
REGION_FICHES_DIR = PROJECT_ROOT / "data" / "region_fiches"


def parse_region_stats_text(text: str) -> dict[str, Any]:
    """Parse a Python-style region stats block (REGION_NAME, REGION_COUNTRY, REGION_COLOR, years, population, annotations)."""
    result: dict[str, Any] = {}

    name_match = re.search(r'REGION_NAME\s*=\s*"([^"]+)"', text)
    if not name_match:
        name_match = re.search(r"REGION_NAME\s*=\s*'([^']+)'", text)
    if not name_match:
        raise ValueError("REGION_NAME introuvable dans le texte.")
    result["region_name"] = name_match.group(1).strip()

    country_match = re.search(r'REGION_COUNTRY\s*=\s*"([^"]+)"', text)
    if not country_match:
        country_match = re.search(r"REGION_COUNTRY\s*=\s*'([^']+)'", text)
    result["region_country"] = country_match.group(1).strip() if country_match else ""

    color_match = re.search(r"REGION_COLOR\s*=\s*['\"](.+?)['\"]", text)
    result["region_color"] = color_match.group(1) if color_match else "#333333"

    years_match = re.search(r"years\s*=\s*\[([^\]]+)\]", text, re.DOTALL)
    if not years_match:
        raise ValueError("Liste 'years' introuvable.")
    result["years"] = [int(y.strip()) for y in years_match.group(1).split(",") if y.strip()]

    pop_match = re.search(r"population\s*=\s*\[([^\]]+)\]", text, re.DOTALL)
    if not pop_match:
        raise ValueError("Liste 'population' introuvable.")
    result["population"] = [int(p.strip()) for p in pop_match.group(1).split(",") if p.strip()]

    if len(result["years"]) != len(result["population"]):
        raise ValueError(
            f"years ({len(result['years'])}) et population ({len(result['population'])}) "
            f"n'ont pas la même longueur."
        )

    annotations: list[tuple] = []
    ann_match = re.search(r"annotations\s*=\s*\[(.+?)\]\s*$", text, re.DOTALL | re.MULTILINE)
    if ann_match:
        try:
            raw = ast.literal_eval("[" + ann_match.group(1) + "]")
            annotations = [tuple(a) for a in raw if isinstance(a, (list, tuple)) and len(a) >= 4]
        except Exception:
            pass
    result["annotations"] = annotations

    result["region_slug"] = slugify(result["region_name"])

    return result


# ---------------------------------------------------------------------------
# Region database import
# ---------------------------------------------------------------------------

def import_region_stats(conn: DbConnection, stats: dict[str, Any]) -> int:
    """Insert/update dim_region + fact_region_population rows. Returns region_id."""
    time_cache = _build_time_cache(conn)

    # Upsert dim_region
    cursor = conn.execute(
        """
        INSERT INTO dim_region (region_name, region_slug, country_name, region_color, source_file)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(region_slug) DO UPDATE SET
            region_name = excluded.region_name,
            country_name = excluded.country_name,
            region_color = excluded.region_color,
            source_file = excluded.source_file
        RETURNING region_id
        """,
        (stats["region_name"], stats["region_slug"], stats["region_country"],
         stats["region_color"], "web-import"),
    )
    region_id = cursor.fetchone()[0]

    # Build annotation cache
    annotation_by_year: dict[int, int] = {}
    for ann in stats["annotations"]:
        if len(ann) < 4:
            continue
        year, _pop, label, color = ann[:4]
        if not isinstance(year, int) or not isinstance(label, str) or not isinstance(color, str):
            continue
        annotation_by_year[year] = _upsert_annotation(conn, label, color)

    # Delete existing population rows for this region (to allow re-import)
    conn.execute("DELETE FROM fact_region_population WHERE region_id = ?", (region_id,))

    # Insert fact rows
    for year, population in zip(stats["years"], stats["population"]):
        time_id = upsert_time_dimension(conn, time_cache, year)
        conn.execute(
            """
            INSERT INTO fact_region_population (region_id, time_id, year, population, is_key_year, annotation_id, source_file)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (region_id, time_id, year, population,
             1 if year in annotation_by_year else 0,
             annotation_by_year.get(year), "web-import"),
        )

    return region_id


def import_region_periods(conn: DbConnection, region_id: int, region_slug: str, sections: list[dict[str, Any]]) -> int:
    """Insert period detail rows into dim_region_period_detail. Returns count of periods inserted."""
    time_cache = _build_time_cache(conn)

    # Remove existing periods for this region
    existing_ids = [
        row[0] for row in conn.execute(
            "SELECT region_period_id FROM dim_region_period_detail WHERE region_id = ?", (region_id,)
        )
    ]
    if existing_ids:
        _delete_rows_by_ids(conn, "dim_region_period_detail_item", "region_period_id", existing_ids)
        conn.execute("DELETE FROM dim_region_period_detail WHERE region_id = ?", (region_id,))

    count = 0
    for order, section in enumerate(sections, start=1):
        start_time_id = upsert_time_dimension(conn, time_cache, section["start_year"])
        end_time_id = upsert_time_dimension(conn, time_cache, section["end_year"])
        cursor = conn.execute(
            """
            INSERT INTO dim_region_period_detail
                (region_id, period_order, period_range_label, period_title,
                 start_year, end_year, start_time_id, end_time_id, summary_text, source_file)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING region_period_id
            """,
            (region_id, order, section["period_range_label"], section["period_title"],
             section["start_year"], section["end_year"], start_time_id, end_time_id,
             section["summary_text"], f"{region_slug}.txt"),
        )
        region_period_id = cursor.fetchone()[0]
        count += 1
        for item_order, item_text in enumerate(section["items"], start=1):
            conn.execute(
                "INSERT INTO dim_region_period_detail_item (region_period_id, item_order, item_text) VALUES (?, ?, ?)",
                (region_period_id, item_order, item_text),
            )

    return count


def save_region_details_file(region_slug: str, text: str) -> Path:
    """Save the region period details raw text as a .txt file in data/region_details/."""
    file_path = REGION_DETAILS_DIR / f"{region_slug}.txt"
    save_raw_document("region", region_slug, "period_detail", text, fallback_path=file_path)
    return file_path


def save_region_fiche_file(region_slug: str, text: str) -> Path:
    """Save the region fiche complète as a .txt file in data/region_fiches/."""
    file_path = REGION_FICHES_DIR / f"{region_slug}.txt"
    save_raw_document("region", region_slug, "fiche", text, fallback_path=file_path)
    return file_path


# ---------------------------------------------------------------------------
# Region photo & flag download
# ---------------------------------------------------------------------------

REGION_PHOTO_DIR = PROJECT_ROOT / "static" / "images" / "regions"
REGION_FLAG_DIR = PROJECT_ROOT / "static" / "images" / "flags" / "regions"


def _download_bytes(url: str) -> bytes | None:
    """Download raw bytes from a URL with a browser-like User-Agent. Returns None on failure."""
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        return data if len(data) > 500 else None
    except Exception:
        return None


def fetch_and_save_region_flag(region_name: str, region_slug: str) -> str | None:
    """Search Wikimedia Commons for a region/province flag and save it.

    Returns the relative static path (e.g. 'images/flags/regions/quebec.png') or None.
    """
    import json
    import urllib.parse
    import urllib.request

    REGION_FLAG_DIR.mkdir(parents=True, exist_ok=True)
    dest = REGION_FLAG_DIR / f"{region_slug}.png"
    if dest.exists():
        return f"images/flags/regions/{region_slug}.png"

    query = f"Flag of {region_name}"
    search_url = (
        "https://commons.wikimedia.org/w/api.php?action=query&list=search"
        f"&srnamespace=6&srsearch={urllib.parse.quote(query)}&srlimit=10&format=json"
    )
    try:
        req = urllib.request.Request(search_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
    except Exception:
        return None

    hits = data.get("query", {}).get("search", [])
    for hit in hits:
        title = hit.get("title", "")
        if not any(title.lower().endswith(ext) for ext in (".svg", ".png", ".jpg", ".jpeg")):
            continue
        info_url = (
            "https://commons.wikimedia.org/w/api.php?action=query"
            f"&titles={urllib.parse.quote(title)}&prop=imageinfo&iiprop=url"
            "&iiurlwidth=400&format=json"
        )
        try:
            req2 = urllib.request.Request(info_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req2, timeout=15) as resp2:
                info = json.load(resp2)
        except Exception:
            continue
        pages = info.get("query", {}).get("pages", {})
        for page in pages.values():
            ii_list = page.get("imageinfo", [])
            if not ii_list:
                continue
            img_url = ii_list[0].get("thumburl") or ii_list[0].get("url")
            if not img_url:
                continue
            raw = _download_bytes(img_url)
            if raw:
                dest.write_bytes(raw)
                return f"images/flags/regions/{region_slug}.png"
    return None


def fetch_and_save_region_photo(
    conn: DbConnection,
    region_id: int,
    region_name: str,
    region_slug: str,
    country_name: str,
) -> str | None:
    """Download the Wikipedia thumbnail for a region and register it in dim_region_photo.

    Returns the relative static path (e.g. 'images/regions/quebec/abc123.jpg') or None.
    """
    import json
    import urllib.parse
    import urllib.request
    import uuid as _uuid

    # Skip if a primary photo already exists
    existing = conn.execute(
        "SELECT photo_id FROM dim_region_photo WHERE region_id = ? AND is_primary = TRUE",
        (region_id,),
    ).fetchone()
    if existing:
        row = conn.execute(
            "SELECT filename FROM dim_region_photo WHERE photo_id = ?",
            (existing["photo_id"],),
        ).fetchone()
        if row:
            return f"images/regions/{region_slug}/{row['filename']}"

    region_dir = REGION_PHOTO_DIR / region_slug
    region_dir.mkdir(parents=True, exist_ok=True)

    # Try Wikipedia REST summary for a ready-made thumbnail
    thumb_url = None
    source_url = ""
    attribution = ""
    for search_name in [f"{region_name}", f"{region_name}, {country_name}"]:
        encoded = urllib.parse.quote(search_name.replace(" ", "_"), safe="()")
        wiki_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
        try:
            req = urllib.request.Request(wiki_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                summary = json.load(resp)
            img_info = summary.get("originalimage") or summary.get("thumbnail")
            if img_info and img_info.get("source"):
                thumb_url = img_info["source"]
                source_url = (
                    summary.get("content_urls", {}).get("desktop", {}).get("page", "")
                )
                attribution = summary.get("description") or search_name
                break
        except Exception:
            continue

    if not thumb_url:
        return None

    raw = _download_bytes(thumb_url)
    if not raw or len(raw) < 5000:
        return None

    # Determine extension
    ext = Path(urllib.parse.urlsplit(thumb_url).path).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        ext = ".jpg"
    filename = f"{_uuid.uuid4().hex[:12]}{ext}"
    (region_dir / filename).write_bytes(raw)

    conn.execute(
        """
        INSERT INTO dim_region_photo (region_id, filename, caption, source_url, attribution, is_primary)
        VALUES (?, ?, ?, ?, ?, TRUE)
        """,
        (region_id, filename, region_name, source_url, attribution),
    )
    return f"images/regions/{region_slug}/{filename}"
