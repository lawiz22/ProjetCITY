from __future__ import annotations

import ast
import json
import re
import sqlite3
import time
import unicodedata
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from .city_photos import CITY_PHOTO_DIR, CITY_PHOTO_MANIFEST, clear_city_photo_manifest_cache

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DETAILS_DIR = PROJECT_ROOT / "data" / "city_details"

CANADIAN_PROVINCES = {
    "Québec", "Quebec", "Ontario", "British Columbia", "Alberta", "Manitoba",
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
    "Californie": "California",
    "Floride": "Florida",
    "Pennsylvanie": "Pennsylvania",
    "Caroline du Nord": "North Carolina",
    "Caroline du Sud": "South Carolina",
    "Virginie": "Virginia",
    "Géorgie": "Georgia",
    "Louisiane": "Louisiana",
}

USER_AGENT = "ProjetCITY/1.0 (city photo cache)"
SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
SEARCH_URL = "https://en.wikipedia.org/w/api.php?action=query&list=search&utf8=1&format=json&srlimit=5&srsearch={query}"


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


# ---------------------------------------------------------------------------
# Stats text parser (Python format)
# ---------------------------------------------------------------------------

def parse_stats_text(text: str) -> dict[str, Any]:
    """Parse the Python-style stats block (CITY_NAME, CITY_COLOR, years, population, annotations)."""
    result: dict[str, Any] = {}

    city_match = re.search(r'CITY_NAME\s*=\s*["\'](.+?)["\']', text)
    if not city_match:
        raise ValueError("CITY_NAME introuvable dans le texte.")
    result["raw_city_name"] = city_match.group(1)
    result["city_name"] = result["raw_city_name"].split(",", 1)[0].strip()

    color_match = re.search(r"CITY_COLOR\s*=\s*['\"](.+?)['\"]", text)
    result["city_color"] = color_match.group(1) if color_match else "#333333"

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


# ---------------------------------------------------------------------------
# Database import
# ---------------------------------------------------------------------------

def upsert_time_dimension(conn: sqlite3.Connection, time_cache: dict[int, int], year: int | None) -> int | None:
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


def import_city_stats(conn: sqlite3.Connection, stats: dict[str, Any]) -> int:
    """Insert/update dim_city + fact_city_population rows. Returns city_id."""
    time_cache: dict[int, int] = {
        year: tid for tid, year in conn.execute("SELECT time_id, year FROM dim_time")
    }

    # Upsert dim_city
    cursor = conn.execute(
        """
        INSERT INTO dim_city (city_name, city_slug, region, country, city_color, source_file)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(city_slug) DO UPDATE SET
            city_name = excluded.city_name,
            region = excluded.region,
            country = excluded.country,
            city_color = excluded.city_color,
            source_file = excluded.source_file
        RETURNING city_id
        """,
        (stats["city_name"], stats["city_slug"], stats["region"],
         stats["country"], stats["city_color"], "web-import"),
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
        cur = conn.execute(
            """
            INSERT INTO dim_annotation (annotation_label, annotation_color)
            VALUES (?, ?)
            ON CONFLICT(annotation_label, annotation_color)
            DO UPDATE SET annotation_color = excluded.annotation_color
            RETURNING annotation_id
            """,
            (label, color),
        )
        annotation_by_year[year] = cur.fetchone()[0]

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


def import_city_periods(conn: sqlite3.Connection, city_id: int, city_slug: str, sections: list[dict[str, Any]]) -> int:
    """Insert period detail rows. Returns count of periods inserted."""
    time_cache: dict[int, int] = {
        year: tid for tid, year in conn.execute("SELECT time_id, year FROM dim_time")
    }

    # Remove existing periods for this city
    existing_ids = [
        row[0] for row in conn.execute(
            "SELECT period_detail_id FROM dim_city_period_detail WHERE city_id = ?", (city_id,)
        )
    ]
    if existing_ids:
        placeholders = ",".join("?" * len(existing_ids))
        conn.execute(f"DELETE FROM dim_city_period_detail_item WHERE period_detail_id IN ({placeholders})", existing_ids)
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
    DETAILS_DIR.mkdir(parents=True, exist_ok=True)
    file_path = DETAILS_DIR / f"{city_slug}.txt"
    file_path.write_text(text, encoding="utf-8")
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
    thumbnail = summary.get("thumbnail", {})
    if isinstance(thumbnail, dict) and isinstance(thumbnail.get("source"), str):
        return thumbnail["source"]
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

    # Update manifest
    manifest: dict[str, Any] = {}
    if CITY_PHOTO_MANIFEST.exists():
        try:
            manifest = json.loads(CITY_PHOTO_MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}

    manifest[city_slug] = {
        "filename": filename,
        "source_page": summary.get("content_urls", {}).get("desktop", {}).get("page", ""),
        "source_image": image_url,
        "attribution": "Image cachee depuis Wikipedia/Wikimedia, verifier les licences en cas de redistribution.",
    }
    CITY_PHOTO_MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    clear_city_photo_manifest_cache()

    return {"success": True, "filename": filename, "source_page": manifest[city_slug]["source_page"]}


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
    if CITY_PHOTO_MANIFEST.exists():
        try:
            manifest = json.loads(CITY_PHOTO_MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}

    manifest[city_slug] = {
        "filename": filename,
        "source_page": "",
        "source_image": "upload",
        "attribution": "Photo uploadée manuellement.",
    }
    CITY_PHOTO_MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    clear_city_photo_manifest_cache()

    return {"success": True, "filename": filename}
