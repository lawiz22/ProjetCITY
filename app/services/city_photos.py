from __future__ import annotations

import json
import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from flask import has_app_context

from app.db import get_db

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CITY_PHOTO_DIR = PROJECT_ROOT / "static" / "images" / "cities"
CITY_PHOTO_MANIFEST = CITY_PHOTO_DIR / "manifest.json"
DEFAULT_CITY_PHOTO = "images/cities/default-city.svg"

USER_AGENT = "CentralCityScrutinizer/1.0 (city photo library)"
SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
SEARCH_URL = "https://en.wikipedia.org/w/api.php?action=query&list=search&utf8=1&format=json&srlimit=5&srsearch={query}"
WIKI_IMAGES_URL = "https://en.wikipedia.org/w/api.php?action=query&titles={title}&prop=images&imlimit=50&format=json"
WIKI_IMAGEINFO_URL = "https://en.wikipedia.org/w/api.php?action=query&titles={titles}&prop=imageinfo&iiprop=url|size|mime|thumbmime&iiurlwidth=1200&format=json"
COMMONS_SEARCH_URL = "https://commons.wikimedia.org/w/api.php?action=query&list=search&srnamespace=6&srsearch={query}&srlimit=40&format=json"
COMMONS_IMAGEINFO_URL = "https://commons.wikimedia.org/w/api.php?action=query&titles={titles}&prop=imageinfo&iiprop=url|size|mime|extmetadata&iiurlwidth=1200&format=json"

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

THUMB_MAX_SIZE = (400, 400)
THUMB_QUALITY = 80


def generate_thumbnail(original_path: str | Path) -> Path | None:
    """Generate a 400px-wide JPEG thumbnail next to the original image.

    Returns the thumbnail Path, or None if generation failed.
    The thumb is named ``thumb_{original_filename}`` (always .jpg).
    If the thumbnail already exists and is non-empty, it is returned as-is.
    """
    from PIL import Image

    src = Path(original_path)
    if not src.exists():
        return None
    thumb_name = f"thumb_{src.stem}.jpg"
    thumb_path = src.parent / thumb_name
    if thumb_path.exists() and thumb_path.stat().st_size > 0:
        return thumb_path
    try:
        with Image.open(src) as img:
            img = img.convert("RGB")
            img.thumbnail(THUMB_MAX_SIZE, Image.LANCZOS)
            img.save(thumb_path, "JPEG", quality=THUMB_QUALITY, optimize=True)
        return thumb_path
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Legacy manifest support (backward compat)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_city_photo_manifest() -> dict[str, dict[str, Any]]:
    if not CITY_PHOTO_MANIFEST.exists():
        return {}
    try:
        data = json.loads(CITY_PHOTO_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    manifest: dict[str, dict[str, Any]] = {}
    for slug, payload in data.items():
        if isinstance(slug, str) and isinstance(payload, dict):
            manifest[slug] = payload
    return manifest


def clear_city_photo_manifest_cache() -> None:
    load_city_photo_manifest.cache_clear()


def _get_photo_row(conn: Any, slug: str) -> Any:
    row = conn.execute(
        """SELECT p.photo_id, p.filename, p.source_url, p.attribution
           FROM dim_city_photo p
           JOIN dim_city c ON c.city_id = p.city_id
           WHERE c.city_slug = ? AND p.is_primary = TRUE
           LIMIT 1""",
        (slug,),
    ).fetchone()
    if row:
        return row
    return conn.execute(
        """SELECT p.photo_id, p.filename, p.source_url, p.attribution
           FROM dim_city_photo p
           JOIN dim_city c ON c.city_id = p.city_id
           WHERE c.city_slug = ?
           ORDER BY p.photo_id
           LIMIT 1""",
        (slug,),
    ).fetchone()


# ---------------------------------------------------------------------------
# Primary photo helper (DB-first, fallback to manifest)
# ---------------------------------------------------------------------------

def get_city_photo(slug: str, conn: Any = None) -> dict[str, Any]:
    """Return the primary photo for a city. Checks DB first, then manifest."""
    connection = conn
    if connection is None and has_app_context():
        try:
            connection = get_db()
        except Exception:
            connection = None

    if connection is not None:
        row = _get_photo_row(connection, slug)
        if row:
            return {
                "photo_path": f"images/cities/{slug}/{row['filename']}",
                "photo_source": row["source_url"],
                "photo_attribution": row["attribution"],
                "has_photo": True,
            }

    # Fallback to manifest
    manifest = load_city_photo_manifest()
    payload = manifest.get(slug, {})
    filename = payload.get("filename") if isinstance(payload, dict) else None
    if isinstance(filename, str) and filename:
        return {
            "photo_path": f"images/cities/{filename}",
            "photo_source": payload.get("source_page"),
            "photo_attribution": payload.get("attribution"),
            "has_photo": True,
        }
    return {
        "photo_path": DEFAULT_CITY_PHOTO,
        "photo_source": None,
        "photo_attribution": None,
        "has_photo": False,
    }


# ---------------------------------------------------------------------------
# Photo library: list all photos for a city
# ---------------------------------------------------------------------------

def get_city_photos(conn: Any, city_slug: str) -> list[dict[str, Any]]:
    """Return all photos for a city from DB."""
    rows = conn.execute(
        """SELECT p.photo_id, p.filename, p.caption, p.source_url, p.attribution,
                  p.is_primary, p.exif_lat, p.exif_lon, p.exif_date, p.exif_camera,
                  p.created_at
           FROM dim_city_photo p
           JOIN dim_city c ON c.city_id = p.city_id
           WHERE c.city_slug = ?
           ORDER BY p.is_primary DESC, p.photo_id""",
        (city_slug,),
    ).fetchall()
    return [
        {
            "photo_id": r["photo_id"],
            "filename": r["filename"],
            "photo_path": f"images/cities/{city_slug}/{r['filename']}",
            "caption": r["caption"],
            "source_url": r["source_url"],
            "attribution": r["attribution"],
            "is_primary": bool(r["is_primary"]),
            "exif_lat": r["exif_lat"],
            "exif_lon": r["exif_lon"],
            "exif_date": r["exif_date"],
            "exif_camera": r["exif_camera"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# EXIF extraction
# ---------------------------------------------------------------------------

def extract_exif(file_path: str | Path) -> dict[str, Any]:
    """Extract EXIF geolocation and metadata from an image file."""
    result: dict[str, Any] = {"lat": None, "lon": None, "date": None, "camera": None}
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS, GPSTAGS

        img = Image.open(file_path)
        exif_data = img._getexif()
        if not exif_data:
            return result

        exif: dict[str, Any] = {}
        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)
            exif[tag] = value

        # Date
        for key in ("DateTimeOriginal", "DateTime", "DateTimeDigitized"):
            if key in exif and isinstance(exif[key], str):
                result["date"] = exif[key]
                break

        # Camera
        make = exif.get("Make", "")
        model = exif.get("Model", "")
        camera_parts = [str(make).strip(), str(model).strip()]
        camera = " ".join(p for p in camera_parts if p)
        if camera:
            result["camera"] = camera

        # GPS
        gps_info = exif.get("GPSInfo")
        if isinstance(gps_info, dict):
            gps: dict[str, Any] = {}
            for k, v in gps_info.items():
                gps_tag = GPSTAGS.get(k, k)
                gps[gps_tag] = v

            def _to_degrees(ref: str, values: tuple) -> float | None:
                try:
                    d = float(values[0])
                    m = float(values[1])
                    s = float(values[2])
                    dd = d + m / 60.0 + s / 3600.0
                    if ref in ("S", "W"):
                        dd = -dd
                    return round(dd, 6)
                except (TypeError, ValueError, IndexError):
                    return None

            if "GPSLatitude" in gps and "GPSLatitudeRef" in gps:
                result["lat"] = _to_degrees(gps["GPSLatitudeRef"], gps["GPSLatitude"])
            if "GPSLongitude" in gps and "GPSLongitudeRef" in gps:
                result["lon"] = _to_degrees(gps["GPSLongitudeRef"], gps["GPSLongitude"])

    except Exception:
        pass
    return result


# ---------------------------------------------------------------------------
# Save photo to library
# ---------------------------------------------------------------------------

def _city_default_date(conn: Any, city_id: int) -> str:
    """Return the city's foundation_year as a date string, or empty."""
    row = conn.execute(
        "SELECT foundation_year FROM dim_city WHERE city_id = ?", (city_id,)
    ).fetchone()
    if row and row["foundation_year"]:
        return str(row["foundation_year"])
    return ""


def _ensure_city_photo_dir(city_slug: str) -> Path:
    """Create and return the per-city photo directory."""
    d = CITY_PHOTO_DIR / city_slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_photo_to_library(
    conn: Any,
    city_id: int,
    city_slug: str,
    file_bytes: bytes,
    original_filename: str,
    source_url: str = "",
    attribution: str = "",
    caption: str = "",
    set_primary: bool = False,
    image_url: str = "",
) -> dict[str, Any]:
    """Save a photo file into the per-city directory and register in DB."""
    suffix = Path(original_filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return {"success": False, "error": "Format non supporté. Utilisez JPG, PNG ou WebP."}

    photo_dir = _ensure_city_photo_dir(city_slug)
    unique_name = f"{uuid.uuid4().hex[:12]}{suffix}"
    dest = photo_dir / unique_name
    dest.write_bytes(file_bytes)
    generate_thumbnail(dest)

    # Extract EXIF
    exif = extract_exif(str(dest))

    # If set_primary, unset other primaries
    if set_primary:
        conn.execute(
            "UPDATE dim_city_photo SET is_primary = FALSE WHERE city_id = ?", (city_id,)
        )

    # Check if city has no photos yet — auto-set primary
    existing_count = conn.execute(
        "SELECT COUNT(*) FROM dim_city_photo WHERE city_id = ?", (city_id,)
    ).fetchone()[0]
    if existing_count == 0:
        set_primary = True

    cursor = conn.execute(
        """INSERT INTO dim_city_photo
           (city_id, filename, caption, source_url, attribution, is_primary,
            exif_lat, exif_lon, exif_date, exif_camera, image_url, photo_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           RETURNING photo_id""",
        (city_id, unique_name, caption, source_url, attribution,
         bool(set_primary),
         exif["lat"], exif["lon"], exif["date"], exif["camera"], image_url,
         _city_default_date(conn, city_id)),
    )
    photo_id = cursor.fetchone()[0]
    conn.commit()

    return {
        "success": True,
        "photo_id": photo_id,
        "filename": unique_name,
        "exif": exif,
    }


def delete_photo_from_library(conn: Any, photo_id: int, city_slug: str) -> bool:
    """Delete a photo from DB and disk."""
    row = conn.execute(
        "SELECT filename, is_primary FROM dim_city_photo WHERE photo_id = ?", (photo_id,)
    ).fetchone()
    if not row:
        return False

    # Delete file
    photo_path = CITY_PHOTO_DIR / city_slug / row["filename"]
    if photo_path.exists():
        photo_path.unlink()

    was_primary = bool(row["is_primary"])
    conn.execute("DELETE FROM dim_city_photo WHERE photo_id = ?", (photo_id,))

    # If we deleted the primary, promote the next one
    if was_primary:
        next_row = conn.execute(
            """SELECT photo_id FROM dim_city_photo p
               JOIN dim_city c ON c.city_id = p.city_id
               WHERE c.city_slug = ?
               ORDER BY p.photo_id LIMIT 1""",
            (city_slug,),
        ).fetchone()
        if next_row:
            conn.execute(
                "UPDATE dim_city_photo SET is_primary = TRUE WHERE photo_id = ?",
                (next_row["photo_id"],),
            )

    conn.commit()
    return True


def set_photo_primary(conn: Any, photo_id: int, city_id: int) -> bool:
    """Set a photo as the primary for its city."""
    conn.execute(
        "UPDATE dim_city_photo SET is_primary = FALSE WHERE city_id = ?", (city_id,)
    )
    conn.execute(
        "UPDATE dim_city_photo SET is_primary = TRUE WHERE photo_id = ?", (photo_id,)
    )
    conn.commit()
    return True


# ---------------------------------------------------------------------------
# Wikipedia image search (returns multiple candidates)
# ---------------------------------------------------------------------------

def _http_get_json(url: str) -> dict:
    last_error: Exception | None = None
    for attempt in range(3):
        req = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(req, timeout=10) as response:
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


def search_wikipedia_images(city_name: str, region: str | None, country: str | None) -> list[dict[str, Any]]:
    """Search Wikipedia for city images. Returns list of candidates with thumbnails."""
    import unicodedata

    candidates: list[str] = [city_name]
    if region:
        normalized = unicodedata.normalize("NFKD", region).encode("ascii", "ignore").decode("ascii")
        candidates.append(f"{city_name}, {region}")
        if normalized != region:
            candidates.append(f"{city_name}, {normalized}")
    if country:
        candidates.append(f"{city_name}, {country}")

    # Collect page titles to search
    page_titles: list[str] = []
    for c in candidates:
        s = _fetch_summary(c)
        if s and s.get("title"):
            page_titles.append(s["title"])
            break
        page_titles.extend(_search_titles(c)[:3])

    if not page_titles:
        return []

    # Get images from the best page
    images: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for page_title in page_titles[:3]:
        try:
            url = WIKI_IMAGES_URL.format(title=quote(page_title.replace(" ", "_"), safe="_(),.-"))
            data = _http_get_json(url)
        except Exception:
            continue

        pages = data.get("query", {}).get("pages", {})
        image_titles: list[str] = []
        for page in pages.values():
            for img in page.get("images", []):
                title = img.get("title", "")
                if title and any(title.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp")):
                    image_titles.append(title)

        if not image_titles:
            continue

        # Get URLs for these images (batch of 10 max)
        for batch_start in range(0, min(len(image_titles), 20), 10):
            batch = image_titles[batch_start:batch_start + 10]
            titles_param = "|".join(batch)
            try:
                info_url = WIKI_IMAGEINFO_URL.format(titles=quote(titles_param, safe="|_(),.-"))
                info_data = _http_get_json(info_url)
            except Exception:
                continue

            info_pages = info_data.get("query", {}).get("pages", {})
            for ipage in info_pages.values():
                ii_list = ipage.get("imageinfo", [])
                if not ii_list:
                    continue
                ii = ii_list[0]
                img_url = ii.get("url", "")
                mime = ii.get("mime", "")
                if not img_url or img_url in seen_urls:
                    continue
                if mime not in ("image/jpeg", "image/png", "image/webp"):
                    continue
                # Skip tiny icons/logos
                width = ii.get("width", 0)
                height = ii.get("height", 0)
                if width < 200 or height < 150:
                    continue

                seen_urls.add(img_url)
                # Use API-provided thumbnail URL
                thumb_url = ii.get("thumburl", img_url)

                images.append({
                    "url": img_url,
                    "thumb_url": thumb_url,
                    "title": ipage.get("title", ""),
                    "width": width,
                    "height": height,
                    "source_page": f"https://en.wikipedia.org/wiki/{quote(page_title.replace(' ', '_'), safe='_(),.-')}",
                })

        if len(images) >= 15:
            break

    return images[:20]


def count_missing_photos(conn: Any, entity_type: str, entity_slug: str) -> int:
    """Count photos that have an image_url but are missing from disk (recoverable)."""
    from .photo_zip import ENTITY_CONFIG
    cfg = ENTITY_CONFIG.get(entity_type)
    if cfg is None:
        return 0
    photo_tbl = cfg["photo_table"]
    fk_col = cfg["fk_col"]
    slug_col = cfg["slug_col"]
    entity_tbl = cfg["entity_table"]
    photo_dir = PROJECT_ROOT / cfg["photo_dir"]

    rows = conn.execute(
        f"SELECT p.filename FROM {photo_tbl} p "
        f"JOIN {entity_tbl} e ON e.{fk_col} = p.{fk_col} "
        f"WHERE e.{slug_col} = ? AND p.image_url IS NOT NULL AND p.image_url != ''",
        (entity_slug,),
    ).fetchall()
    count = 0
    for r in rows:
        file_path = photo_dir / entity_slug / r["filename"]
        if not file_path.is_file():
            count += 1
    return count


def download_web_image(url: str) -> tuple[bytes, str] | None:
    """Download an image from a URL. Returns (bytes, extension) or None."""
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=15) as resp:
            data = resp.read()
            content_type = resp.headers.get("Content-Type", "")
    except Exception:
        return None

    ext_map = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    ext = ext_map.get(content_type.split(";")[0].strip(), "")
    if not ext:
        # Try from URL
        path_ext = Path(urlsplit(url).path).suffix.lower()
        if path_ext in ALLOWED_EXTENSIONS:
            ext = path_ext
        else:
            ext = ".jpg"

    return data, ext


# ---------------------------------------------------------------------------
# Wikimedia Commons image search
# ---------------------------------------------------------------------------

def search_commons_images(city_name: str, region: str | None, country: str | None) -> list[dict[str, Any]]:
    """Search Wikimedia Commons for city images. Returns list of candidates with thumbnails."""
    query_parts = [city_name]
    if region:
        query_parts.append(region)
    if country:
        query_parts.append(country)
    search_query = " ".join(query_parts)

    try:
        url = COMMONS_SEARCH_URL.format(query=quote(search_query))
        data = _http_get_json(url)
    except Exception:
        return []

    results = data.get("query", {}).get("search", [])
    if not results:
        return []

    # Collect File: titles from search results
    file_titles = []
    for r in results:
        title = r.get("title", "")
        if title and any(title.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp")):
            file_titles.append(title)

    if not file_titles:
        return []

    images: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    # Batch imageinfo requests (10 at a time)
    for batch_start in range(0, min(len(file_titles), 30), 10):
        batch = file_titles[batch_start:batch_start + 10]
        titles_param = "|".join(batch)
        try:
            info_url = COMMONS_IMAGEINFO_URL.format(titles=quote(titles_param, safe="|_(),.-"))
            info_data = _http_get_json(info_url)
        except Exception:
            continue

        info_pages = info_data.get("query", {}).get("pages", {})
        for ipage in info_pages.values():
            ii_list = ipage.get("imageinfo", [])
            if not ii_list:
                continue
            ii = ii_list[0]
            img_url = ii.get("url", "")
            mime = ii.get("mime", "")
            if not img_url or img_url in seen_urls:
                continue
            if mime not in ("image/jpeg", "image/png", "image/webp"):
                continue
            width = ii.get("width", 0)
            height = ii.get("height", 0)
            if width < 200 or height < 150:
                continue

            seen_urls.add(img_url)
            thumb_url = ii.get("thumburl", img_url)
            page_title = ipage.get("title", "").replace("File:", "").replace(" ", "_")

            images.append({
                "url": img_url,
                "thumb_url": thumb_url,
                "title": ipage.get("title", ""),
                "width": width,
                "height": height,
                "source_page": f"https://commons.wikimedia.org/wiki/File:{quote(page_title, safe='_(),.-')}",
            })

    return images[:20]


# ---------------------------------------------------------------------------
# Annotation photo search (smart query with translation)
# ---------------------------------------------------------------------------

ANNOTATION_PHOTO_DIR = PROJECT_ROOT / "static" / "images" / "annotations"

WIKTIONARY_TRANSLATE_URL = (
    "https://en.wikipedia.org/w/api.php?action=query&list=search"
    "&utf8=1&format=json&srlimit=3&srsearch={query}"
)


import re as _re_module

def _strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    return _re_module.sub(r'<[^>]+>', '', text).strip()


_FR_STOPWORDS = {
    "le", "la", "les", "de", "du", "des", "un", "une", "et", "en", "au", "aux",
    "ce", "ces", "se", "sa", "son", "ses", "sur", "par", "pour", "dans", "est",
    "qui", "que", "avec", "vers", "pas", "plus", "très", "tout", "mais",
}


_FR_EN_ANNOTATION_DICT: dict[str, str] = {
    "fusion": "merger amalgamation",
    "annexion": "annexation",
    "construction": "construction",
    "inauguration": "inauguration opening",
    "fondation": "founding foundation",
    "incorporation": "incorporation",
    "incendie": "fire disaster",
    "inondation": "flood flooding",
    "tremblement": "earthquake",
    "explosion": "explosion disaster",
    "ouverture": "opening",
    "fermeture": "closing closure",
    "création": "creation establishment",
    "abolition": "abolition",
    "démolition": "demolition",
    "reconstruction": "reconstruction rebuilding",
    "rénovation": "renovation",
    "expansion": "expansion growth",
    "effondrement": "collapse",
    "épidémie": "epidemic outbreak",
    "pandémie": "pandemic",
    "grève": "strike labor",
    "émeute": "riot",
    "élection": "election",
    "référendum": "referendum",
    "sommet": "summit conference",
    "expo": "exposition world fair",
    "exposition": "exposition exhibition",
    "olympiques": "olympics olympic games",
    "jeux": "games",
    "stade": "stadium",
    "aéroport": "airport",
    "métro": "metro subway",
    "tramway": "tramway streetcar",
    "pont": "bridge",
    "autoroute": "highway freeway",
    "gare": "station railway",
    "église": "church",
    "cathédrale": "cathedral",
    "université": "university",
    "hôpital": "hospital",
    "musée": "museum",
    "bibliothèque": "library",
    "parc": "park",
    "port": "port harbor",
    "barrage": "dam",
    "centrale": "power plant",
    "usine": "factory plant",
    "mine": "mine mining",
    "chemin de fer": "railway railroad",
    "guerre": "war",
    "bataille": "battle",
    "traité": "treaty",
    "loi": "law act",
    "arrondissement": "borough district",
    "quartier": "neighborhood district",
    "séparation": "separation",
    "regroupement": "regrouping consolidation",
    "défusion": "demerger municipal demerger",
}


def _translate_label_to_english(label: str) -> list[str]:
    """Translate a French annotation label to English using a dictionary + Wikipedia.

    Uses a built-in French-English dictionary for common annotation terms first,
    then falls back to Wikipedia search with relevance validation.
    """
    import re
    cleaned = re.sub(r'[\U00010000-\U0010ffff]', '', label)
    cleaned = re.sub(r'\(\d{4}\)', '', cleaned).strip()
    cleaned = re.sub(r'\s*—\s*', ' ', cleaned)
    cleaned = re.sub(r'[=+]', ' ', cleaned).strip()
    if not cleaned:
        return []

    results_out: list[str] = []
    words_lower = cleaned.lower().split()

    # Phase 1: Dictionary-based translation of key French terms
    en_parts: list[str] = []
    for word in words_lower:
        if word in _FR_EN_ANNOTATION_DICT:
            en_parts.append(_FR_EN_ANNOTATION_DICT[word])
        elif word not in _FR_STOPWORDS and len(word) >= 3:
            en_parts.append(word)  # Keep proper nouns as-is
    if en_parts:
        results_out.append(" ".join(en_parts))

    # Phase 2: Wikipedia search with relevance validation
    # Extract meaningful keywords for the search
    label_keywords = set(w for w in words_lower
                         if w not in _FR_STOPWORDS and len(w) >= 3)
    try:
        url = WIKTIONARY_TRANSLATE_URL.format(query=quote(cleaned))
        data = _http_get_json(url)
        results = data.get("query", {}).get("search", [])
        for r in results[:3]:
            t = r.get("title", "")
            if not t:
                continue
            # Validate: the Wikipedia result must share at least one keyword
            # with the annotation label to be considered relevant
            title_words = set(t.lower().split())
            if title_words & label_keywords:
                results_out.append(t)
    except Exception:
        pass
    return results_out


def _extract_keywords(text: str) -> list[str]:
    """Extract meaningful keywords from a cleaned label, removing French stopwords."""
    import re
    words = re.findall(r'[a-zA-ZÀ-ÿ\'-]{3,}', text)
    return [w for w in words if w.lower() not in _FR_STOPWORDS]


def _extract_proper_nouns(text: str) -> list[str]:
    """Extract proper nouns (capitalized words) and acronyms from text."""
    import re
    # Find capitalized words (not at start of sentence) and acronyms
    words = re.findall(r'\b[A-ZÀ-Ý][a-zà-ÿ]{2,}\b', text)
    acronyms = re.findall(r'\b[A-Z]{2,}\b', text)
    return words + acronyms


# Geo-context terms appended to queries to avoid off-topic results
_GEO_CONTEXT = ["city", "ville", "municipality", "history", "historical"]


def _build_annotation_search_queries(
    label: str, city_name: str, region: str | None, country: str | None
) -> dict[str, list[str]]:
    """Build tiered search queries from an annotation label.

    Returns a dict with three tiers:
      - "specific": keyword + city + year  (best match)
      - "medium":   keyword + city          (good match)
      - "generic":  keyword + year or keyword alone (fallback for topic photos)

    The city name is always included in specific/medium tiers.
    Generic tier intentionally omits the city to find at least *some*
    relevant topical photos (e.g. a fire, a flood, an inauguration).
    """
    import re
    # Clean label: remove emoji and special chars like = +
    cleaned = re.sub(r'[\U00010000-\U0010ffff]', '', label).strip()
    # Extract text before and after em-dash
    parts = [p.strip() for p in cleaned.split('—') if p.strip()]
    # Remove year in parentheses, = signs, + signs
    parts = [re.sub(r'\(\d{4}\)', '', p).strip() for p in parts]
    parts = [re.sub(r'[=+]', ' ', p).strip() for p in parts]
    parts = [re.sub(r'\s{2,}', ' ', p).strip() for p in parts if p.strip()]
    # Extract standalone year
    year_match = re.search(r'\((\d{4})\)', cleaned)
    year = year_match.group(1) if year_match else ""

    # Build geo-context strings
    geo_ctx = [city_name]
    if region:
        geo_ctx.append(f"{city_name} {region}")
    if country:
        geo_ctx.append(f"{city_name} {country}")

    specific: list[str] = []
    medium: list[str] = []
    generic: list[str] = []
    seen_lower: set[str] = set()

    def _add(tier: list[str], q: str) -> None:
        q = q.strip()
        if q and q.lower() not in seen_lower:
            seen_lower.add(q.lower())
            tier.append(q)

    full = ' '.join(parts)
    keywords = _extract_keywords(full)
    kw_str = ' '.join(keywords[:3]) if keywords else full

    # --- SPECIFIC tier: full label + city + year ---
    if full and year:
        for geo in geo_ctx:
            _add(specific, f"{full} {geo} {year}")
        _add(specific, f"{kw_str} {city_name} {year}")

    # --- MEDIUM tier: label/keywords + city (no year constraint) ---
    if full:
        for geo in geo_ctx:
            _add(medium, f"{full} {geo}")
    for p in parts:
        if p:
            _add(medium, f"{p} {city_name}")
            if year:
                _add(medium, f"{p} {city_name} {year}")
    if len(keywords) >= 2:
        for geo in geo_ctx[:2]:
            _add(medium, f"{kw_str} {geo}")
    if year:
        _add(medium, f"{city_name} history {year}")
    _add(medium, f"{city_name} historical")
    # Acronyms / special tokens with city context
    specials = re.findall(r'[A-Z]{2,}[\w-]*', full)
    for sp in specials[:2]:
        _add(medium, f"{sp} {city_name}")

    # --- GENERIC tier: keywords WITHOUT city (topic fallback) ---
    # These find at least a photo of the right topic (fire, flood, etc.)
    # Prioritize keywords that are in the FR-EN dictionary (topic words)
    # over generic adjectives like "grand", "petit", etc.
    dict_keywords = [k for k in keywords if k.lower() in _FR_EN_ANNOTATION_DICT]
    other_keywords = [k for k in keywords if k.lower() not in _FR_EN_ANNOTATION_DICT]
    ranked_keywords = dict_keywords + other_keywords
    if ranked_keywords:
        main_kw = ranked_keywords[0]  # most important topic keyword
        if year:
            _add(generic, f"{main_kw} {year}")
            if len(ranked_keywords) >= 2:
                _add(generic, f"{' '.join(ranked_keywords[:3])} {year}")
        _add(generic, f"{main_kw} historical")
        if len(ranked_keywords) >= 2:
            _add(generic, f"{' '.join(ranked_keywords[:3])}")
        # English translation of main keyword for generic fallback
        en_main = _FR_EN_ANNOTATION_DICT.get(main_kw.lower(), "")
        if en_main:
            first_en = en_main.split()[0]
            if year:
                _add(generic, f"{first_en} {year}")
                _add(generic, f"{first_en} historical {year}")
            _add(generic, f"{first_en} historical")

    return {"specific": specific, "medium": medium, "generic": generic}


def _search_commons_batch(
    query: str, seen_urls: set[str], limit: int = 30
) -> list[dict[str, Any]]:
    """Search Wikimedia Commons for a query and return image dicts."""
    images: list[dict[str, Any]] = []
    try:
        url = COMMONS_SEARCH_URL.format(query=quote(query))
        data = _http_get_json(url)
    except Exception:
        return images

    results = data.get("query", {}).get("search", [])
    file_titles = [
        r["title"] for r in results
        if r.get("title") and any(r["title"].lower().endswith(ext)
                                  for ext in (".jpg", ".jpeg", ".png", ".webp"))
    ]

    for batch_start in range(0, min(len(file_titles), limit), 10):
        batch = file_titles[batch_start:batch_start + 10]
        titles_param = "|".join(batch)
        try:
            info_url = COMMONS_IMAGEINFO_URL.format(
                titles=quote(titles_param, safe="|_(),.-")
            )
            info_data = _http_get_json(info_url)
        except Exception:
            continue

        info_pages = info_data.get("query", {}).get("pages", {})
        for ipage in info_pages.values():
            ii_list = ipage.get("imageinfo", [])
            if not ii_list:
                continue
            ii = ii_list[0]
            img_url = ii.get("url", "")
            mime = ii.get("mime", "")
            if not img_url or img_url in seen_urls:
                continue
            if mime not in ("image/jpeg", "image/png", "image/webp"):
                continue
            width = ii.get("width", 0)
            height = ii.get("height", 0)
            if width < 200 or height < 150:
                continue

            seen_urls.add(img_url)
            thumb_url = ii.get("thumburl", img_url)
            page_title = ipage.get("title", "").replace("File:", "").replace(" ", "_")

            # Extract description and categories from extmetadata
            extmeta = ii.get("extmetadata", {})
            desc = (
                extmeta.get("ImageDescription", {}).get("value", "")
                or extmeta.get("ObjectName", {}).get("value", "")
            )
            desc = _strip_html(desc)
            if len(desc) > 200:
                desc = desc[:197] + "..."
            cats = extmeta.get("Categories", {}).get("value", "")

            images.append({
                "url": img_url,
                "thumb_url": thumb_url,
                "title": ipage.get("title", ""),
                "description": desc,
                "categories": cats,
                "width": width,
                "height": height,
                "source_page": f"https://commons.wikimedia.org/wiki/File:{quote(page_title, safe='_(),.-')}",
            })

    return images


def _search_wiki_article_images(
    query: str, seen_urls: set[str]
) -> list[dict[str, Any]]:
    """Search Wikipedia for an article matching the query, then return its images."""
    images: list[dict[str, Any]] = []
    # Find article via search
    try:
        search_url = WIKTIONARY_TRANSLATE_URL.format(query=quote(query))
        data = _http_get_json(search_url)
    except Exception:
        return images

    results = data.get("query", {}).get("search", [])
    if not results:
        return images

    page_title = results[0].get("title", "")
    if not page_title:
        return images

    # Get images from article
    try:
        url = WIKI_IMAGES_URL.format(title=quote(page_title.replace(" ", "_"), safe="_(),.-"))
        data = _http_get_json(url)
    except Exception:
        return images

    pages = data.get("query", {}).get("pages", {})
    image_titles: list[str] = []
    for page in pages.values():
        for img in page.get("images", []):
            title = img.get("title", "")
            if title and any(title.lower().endswith(ext)
                            for ext in (".jpg", ".jpeg", ".png", ".webp")):
                image_titles.append(title)

    if not image_titles:
        return images

    for batch_start in range(0, min(len(image_titles), 20), 10):
        batch = image_titles[batch_start:batch_start + 10]
        titles_param = "|".join(batch)
        try:
            info_url = WIKI_IMAGEINFO_URL.format(titles=quote(titles_param, safe="|_(),.-"))
            info_data = _http_get_json(info_url)
        except Exception:
            continue

        info_pages = info_data.get("query", {}).get("pages", {})
        for ipage in info_pages.values():
            ii_list = ipage.get("imageinfo", [])
            if not ii_list:
                continue
            ii = ii_list[0]
            img_url = ii.get("url", "")
            mime = ii.get("mime", "")
            if not img_url or img_url in seen_urls:
                continue
            if mime not in ("image/jpeg", "image/png", "image/webp"):
                continue
            width = ii.get("width", 0)
            height = ii.get("height", 0)
            if width < 200 or height < 150:
                continue

            seen_urls.add(img_url)
            thumb_url = ii.get("thumburl", img_url)

            images.append({
                "url": img_url,
                "thumb_url": thumb_url,
                "title": ipage.get("title", ""),
                "description": "",
                "width": width,
                "height": height,
                "source_page": f"https://en.wikipedia.org/wiki/{quote(page_title.replace(' ', '_'), safe='_(),.-')}",
            })

    return images


def search_annotation_images(
    label: str, city_name: str, region: str | None, country: str | None
) -> list[dict[str, Any]]:
    """Search Wikipedia + Wikimedia Commons for annotation-related images.

    Uses a **tiered progressive strategy**:
      1. Specific: keyword + city + year (best match)
      2. Medium: keyword + city (good match)
      3. Generic: keyword + year or keyword alone (topic fallback)
      4. Proper noun / named entity queries (for event-style labels)
      5. Wikipedia article images as final fallback

    City name is always present in tier 1-2. Tier 3 drops the city to
    guarantee at least *some* topical photos (e.g. a fire, flood, etc.).
    """
    import re

    tiers = _build_annotation_search_queries(label, city_name, region, country)

    # Get English translations — these work better on Commons
    en_titles = _translate_label_to_english(label)

    # Extract year from label for English queries
    year_match = re.search(r'\((\d{4})\)', label)
    year = year_match.group(1) if year_match else ""

    # Extract proper nouns from the label (e.g. "Michael Jackson", "Grammy Awards")
    cleaned_label = re.sub(r'[\U00010000-\U0010ffff]', '', label).strip()
    cleaned_label = re.sub(r'\(\d{4}\)', '', cleaned_label).strip()
    proper_nouns = _extract_proper_nouns(cleaned_label)

    # Build English queries in same tiers
    en_specific: list[str] = []
    en_medium: list[str] = []
    en_generic: list[str] = []
    for en_title in en_titles:
        if year:
            en_specific.append(f"{en_title} {city_name} {year}")
        en_medium.append(f"{en_title} {city_name}")
        if year:
            en_generic.append(f"{en_title} {year}")
        en_generic.append(en_title)

    # Also extract acronyms / proper nouns
    specials = re.findall(r'[A-Z]{2,}[\w-]*', cleaned_label)
    for sp in specials:
        en_medium.append(f"{sp} {city_name}")

    # Build proper-noun-based queries (great for events with names)
    # E.g. "Michael Jackson Grammy Awards" -> shorter, more targeted
    pn_queries: list[str] = []
    if proper_nouns:
        pn_str = ' '.join(proper_nouns[:4])
        if year:
            pn_queries.append(f"{pn_str} {year}")
        pn_queries.append(pn_str)
        # Try pairs of proper nouns for very specific results
        if len(proper_nouns) >= 2:
            pn_queries.append(f"{proper_nouns[0]} {proper_nouns[1]}")
            if year:
                pn_queries.append(f"{proper_nouns[0]} {proper_nouns[1]} {year}")

    # Merge English + French queries per tier, English first
    def _dedup(queries: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for q in queries:
            ql = q.strip().lower()
            if ql and ql not in seen:
                seen.add(ql)
                out.append(q.strip())
        return out

    tier_specific = _dedup(en_specific + tiers["specific"])
    tier_medium = _dedup(en_medium + tiers["medium"])
    tier_generic = _dedup(pn_queries + en_generic + tiers["generic"])

    images: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    # Categories/descriptions that indicate irrelevant content
    _IRRELEVANT_CATS = {
        "wrestler", "wrestling", "luchador", "lutte", "catch", "catcheuse",
        "catcheur", "suplex", "lufisto", "shimmer", "wwe", "aew", "roh",
        "boxeur", "boxer", "boxing", "boxe", "mma", "fighter",
        "porn", "adult", "erotic",
        "football player", "soccer player", "basketball player",
        "baseball player", "hockey player", "athlete",
        "singer", "musician", "actor", "actress", "model",
        "professional wrestling", "pro wrestling",
    }

    def _is_relevant(img: dict) -> bool:
        """Check if an image is likely relevant to the annotation subject."""
        text = (img.get("title", "") + " " + img.get("description", "")
                + " " + img.get("categories", "")).lower()
        for bad in _IRRELEVANT_CATS:
            if bad in text:
                return False
        return True

    # --- Tier 1: SPECIFIC (keyword + city + year) ---
    for query in tier_specific[:6]:
        batch = _search_commons_batch(query, seen_urls, limit=30)
        images.extend(b for b in batch if _is_relevant(b))
        if len(images) >= 20:
            break

    # --- Tier 2: MEDIUM (keyword + city) — only if not enough ---
    if len(images) < 20:
        for query in tier_medium[:8]:
            batch = _search_commons_batch(query, seen_urls, limit=30)
            images.extend(b for b in batch if _is_relevant(b))
            if len(images) >= 25:
                break

    # --- Tier 3: GENERIC (keyword + year, keyword alone) — topic fallback ---
    if len(images) < 10:
        for query in tier_generic[:6]:
            batch = _search_commons_batch(query, seen_urls, limit=20)
            images.extend(b for b in batch if _is_relevant(b))
            if len(images) >= 20:
                break

    # --- Tier 4: Wikipedia article images as final fallback ---
    if len(images) < 15:
        wiki_queries = []
        if en_titles:
            wiki_queries.append(f"{en_titles[0]} {city_name}")
            wiki_queries.append(en_titles[0])
        wiki_queries.extend(tier_medium[:2])
        seen_wq: set[str] = set()
        for query in wiki_queries:
            ql = query.lower()
            if ql in seen_wq:
                continue
            seen_wq.add(ql)
            if len(images) >= 30:
                break
            batch = _search_wiki_article_images(query, seen_urls)
            images.extend(batch)

    return images[:40]


# ── Legend-specific photo search ─────────────────────────────
# Legends (Wendigo, Chasse-Galerie, MH370…) are *topics*, not places.
# The search must focus on the legend subject itself, not a city.

_LEGEND_CATEGORY_HINTS: dict[str, list[str]] = {
    "creature":        ["creature", "monster", "cryptid", "mythology", "beast"],
    "fantome":         ["ghost", "haunting", "specter", "paranormal", "apparition"],
    "ovni":            ["UFO", "unidentified flying object", "extraterrestrial", "alien"],
    "disparition":     ["disappearance", "mystery", "missing", "vanished"],
    "malediction":     ["curse", "cursed", "malediction", "hex"],
    "lieu_hante":      ["haunted", "haunted place", "ghost", "abandoned"],
    "phenomene":       ["phenomenon", "unexplained", "paranormal", "strange"],
    "origine_inconnue":["legend", "myth", "folklore", "mystery"],
    "mythe":           ["myth", "mythology", "folklore", "mythical"],
    "legende_urbaine": ["urban legend", "hoax", "folklore", "creepypasta"],
    "conspiration":    ["conspiracy", "cover-up", "secret", "classified"],
    "cryptide":        ["cryptid", "creature", "sighting", "monster"],
    "miracle":         ["miracle", "supernatural", "divine", "sacred"],
}

# French legend keywords → English equivalents for better Commons results
_FR_LEGEND_DICT: dict[str, str] = {
    "monstre":     "monster",
    "fantôme":     "ghost",
    "fantome":     "ghost",
    "spectre":     "specter ghost",
    "créature":    "creature",
    "creature":    "creature",
    "mystère":     "mystery",
    "mystere":     "mystery",
    "légende":     "legend",
    "legende":     "legend",
    "malédiction": "curse",
    "sorcière":    "witch",
    "sorcier":     "sorcerer wizard",
    "loup-garou":  "werewolf",
    "vampire":     "vampire",
    "revenant":    "ghost revenant",
    "apparition":  "apparition ghost",
    "hante":       "haunted",
    "hanté":       "haunted",
    "hantée":      "haunted",
    "phénomène":   "phenomenon",
    "phenomene":   "phenomenon",
    "disparition": "disappearance",
    "enlèvement":  "abduction",
    "cryptide":    "cryptid",
    "bête":        "beast creature",
    "bete":        "beast creature",
    "diable":      "devil demon",
    "démon":       "demon",
    "demon":       "demon",
    "serpent":     "serpent sea serpent",
    "dragon":      "dragon",
    "géant":       "giant",
    "canot":       "canoe",
    "volant":      "flying",
    "chasse":      "hunt",
    "galerie":     "gallery",
    "feu":         "fire",
    "lac":         "lake",
    "forêt":       "forest",
    "mer":         "sea ocean",
    "nuit":        "night",
    "mort":        "death dead",
    "sang":        "blood",
    "ombre":       "shadow",
    "brume":       "fog mist",
    "cri":         "scream cry",
    "vol":         "flight",
    "disparu":     "disappeared missing",
    "inexpliqué":  "unexplained",
    "inexplique":  "unexplained",
    "ovni":        "UFO",
}

_LEGEND_IRRELEVANT_CATS = {
    "wrestler", "wrestling", "luchador", "catch", "wwe", "aew",
    "porn", "adult", "erotic",
    "football player", "soccer player", "basketball player",
    "baseball player", "hockey player",
    "logo", "icon", "screenshot", "stub",
    "map of", "location map", "administrative",
    "coat of arms", "flag of", "seal of",
}


def search_legend_images(
    legend_name: str,
    legend_category: str | None = None,
    summary: str | None = None,
    country: str | None = None,
    year_reported: int | None = None,
) -> list[dict[str, Any]]:
    """Search Wikipedia + Wikimedia Commons for legend-related images.

    Strategy (prioritized):
      1. Proper nouns from the name (e.g. "Wendigo", "Champlain")
      2. Subject keywords translated to English (e.g. "monster lake")
      3. Category hints (e.g. "creature", "cryptid")
      4. Wikipedia article images
      5. Country/geography as last resort only
    """
    import re

    images: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    def _is_relevant(img: dict) -> bool:
        text = (img.get("title", "") + " " + img.get("description", "")
                + " " + img.get("categories", "")).lower()
        for bad in _LEGEND_IRRELEVANT_CATS:
            if bad in text:
                return False
        return True

    # Clean the legend name: remove "La légende de", "Le mystère du", etc.
    clean_name = re.sub(
        r"^(la\s+légende\s+d[eu']\s*|le\s+mystère\s+d[eu']\s*|"
        r"l['']\s*histoire\s+d[eu']\s*|les?\s+|le\s+|la\s+)",
        "", legend_name, flags=re.IGNORECASE,
    ).strip()

    # Get category hints
    cat = (legend_category or "").lower()
    hints = _LEGEND_CATEGORY_HINTS.get(cat, ["legend", "myth", "folklore"])

    # Extract proper nouns (capitalized words = typically the unique identifier)
    proper_nouns = _extract_proper_nouns(clean_name)

    # Extract ALL meaningful keywords from name
    name_keywords = _extract_keywords(clean_name)

    # Translate each French keyword to English
    en_keywords: list[str] = []
    for kw in name_keywords:
        en = _FR_LEGEND_DICT.get(kw.lower(), "")
        if en:
            en_keywords.append(en.split()[0])  # Take first translation
        elif kw[0].isupper():
            en_keywords.append(kw)  # Keep proper nouns as-is

    # Get English translation of the full name via Wikipedia
    en_titles = _translate_label_to_english(clean_name)
    en_name = en_titles[0] if en_titles else ""

    year_str = str(year_reported) if year_reported else ""

    # ---- Build query tiers (subject-first, geography-last) ----

    # Tier 1: Proper nouns + subject keywords (most precise)
    tier1: list[str] = []
    # The proper nouns ARE the legend (e.g. "Wendigo", "Champlain")
    if proper_nouns:
        pn_str = " ".join(proper_nouns[:3])
        tier1.append(pn_str)
        # Proper nouns + first hint (e.g. "Wendigo creature")
        tier1.append(f"{pn_str} {hints[0]}")
        if year_str:
            tier1.append(f"{pn_str} {year_str}")
    # English translation of the full name
    if en_name and en_name.lower() != clean_name.lower():
        tier1.append(en_name)
        tier1.append(f"{en_name} {hints[0]}")
    # Full cleaned name
    tier1.append(clean_name)

    # Tier 2: English keywords + hints (subject-focused)
    tier2: list[str] = []
    if en_keywords:
        en_kw_str = " ".join(en_keywords[:3])
        tier2.append(en_kw_str)
        for hint in hints[:2]:
            tier2.append(f"{en_kw_str} {hint}")
    # Category hints alone (e.g. "monster cryptid", "ghost haunting")
    for hint in hints[:3]:
        if proper_nouns:
            tier2.append(f"{proper_nouns[0]} {hint}")

    # Tier 3: Broader — summary keywords, category hints alone, country
    tier3: list[str] = []
    if summary:
        sum_kw = _extract_keywords(summary)[:4]
        # Translate summary keywords too
        en_sum: list[str] = []
        for kw in sum_kw:
            en = _FR_LEGEND_DICT.get(kw.lower(), "")
            if en:
                en_sum.append(en.split()[0])
            elif kw[0].isupper():
                en_sum.append(kw)
        if en_sum:
            tier3.append(" ".join(en_sum[:3]))
    # Hints alone as absolute fallback for subject
    for h1, h2 in zip(hints[:2], hints[1:3]):
        tier3.append(f"{h1} {h2}")
    # Country only as very last resort
    if country and proper_nouns:
        tier3.append(f"{proper_nouns[0]} {country}")

    # Dedup
    def _dedup(queries: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for q in queries:
            ql = q.strip().lower()
            if ql and ql not in seen:
                seen.add(ql)
                out.append(q.strip())
        return out

    tier1 = _dedup(tier1)
    tier2 = _dedup(tier2)
    tier3 = _dedup(tier3)

    # --- Tier 1: Proper nouns + subject ---
    for query in tier1[:8]:
        batch = _search_commons_batch(query, seen_urls, limit=30)
        images.extend(b for b in batch if _is_relevant(b))
        if len(images) >= 15:
            break

    # --- Tier 2: English keywords + hints ---
    if len(images) < 15:
        for query in tier2[:8]:
            batch = _search_commons_batch(query, seen_urls, limit=25)
            images.extend(b for b in batch if _is_relevant(b))
            if len(images) >= 25:
                break

    # --- Tier 3: Broad fallback (summary, hints alone, country) ---
    if len(images) < 10:
        for query in tier3[:6]:
            batch = _search_commons_batch(query, seen_urls, limit=20)
            images.extend(b for b in batch if _is_relevant(b))
            if len(images) >= 20:
                break

    # --- Wikipedia article images as final fallback ---
    if len(images) < 10:
        wiki_queries: list[str] = []
        if proper_nouns:
            wiki_queries.append(" ".join(proper_nouns[:3]))
        if en_name and en_name.lower() != clean_name.lower():
            wiki_queries.append(en_name)
        wiki_queries.append(clean_name)
        seen_wq: set[str] = set()
        for query in wiki_queries:
            ql = query.lower()
            if ql in seen_wq:
                continue
            seen_wq.add(ql)
            if len(images) >= 30:
                break
            batch = _search_wiki_article_images(query, seen_urls)
            images.extend(batch)

    return images[:40]


# ── Person-specific photo search ─────────────────────────────
# Persons are *people*, not places. The search must focus on the person's
# name, profession/category, and optionally their era — NOT a city.

_PERSON_CATEGORY_HINTS: dict[str, list[str]] = {
    "politique":       ["politician", "political leader", "statesman"],
    "militaire":       ["military", "general", "soldier", "officer"],
    "artiste":         ["artist", "painter", "sculptor"],
    "musicien":        ["musician", "singer", "composer"],
    "ecrivain":        ["writer", "author", "poet"],
    "scientifique":    ["scientist", "researcher", "professor"],
    "explorateur":     ["explorer", "expedition"],
    "religieux":       ["religious leader", "priest", "bishop", "missionary"],
    "sportif":         ["athlete", "sports"],
    "entrepreneur":    ["businessman", "entrepreneur", "industrialist"],
    "activiste":       ["activist", "social reformer"],
    "architecte":      ["architect", "architecture"],
    "ingenieur":       ["engineer", "engineering"],
    "enseignant":      ["teacher", "educator", "professor"],
    "medecin":         ["physician", "doctor", "medicine"],
    "avocat":          ["lawyer", "attorney", "jurist"],
    "journaliste":     ["journalist", "reporter"],
    "autre":           ["historical figure", "notable person"],
}

_PERSON_IRRELEVANT_CATS = {
    "porn", "adult", "erotic",
    "logo", "icon", "screenshot", "stub",
    "map", "chart", "graph", "diagram",
}


def search_person_images(
    person_name: str,
    person_category: str | None = None,
    birth_year: int | None = None,
    death_year: int | None = None,
    birth_country: str | None = None,
) -> list[dict[str, Any]]:
    """Search Wikipedia + Wikimedia Commons for person-related images.

    Focuses on the person's name and profession rather than geography.
    """
    import re

    images: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    def _is_relevant(img: dict) -> bool:
        text = (img.get("title", "") + " " + img.get("description", "")
                + " " + img.get("categories", "")).lower()
        for bad in _PERSON_IRRELEVANT_CATS:
            if bad in text:
                return False
        return True

    # Category hints
    cat = (person_category or "").lower()
    hints = _PERSON_CATEGORY_HINTS.get(cat, ["historical figure"])

    # English translations
    en_titles = _translate_label_to_english(person_name)
    en_name = en_titles[0] if en_titles else person_name

    # Build year context
    year_str = ""
    if birth_year and death_year:
        year_str = f"{birth_year}-{death_year}"
    elif birth_year:
        year_str = str(birth_year)

    # Proper nouns from name (first/last name components)
    proper_nouns = _extract_proper_nouns(person_name)

    # ---- Tier 1: Direct name (portrait-focused) ----
    tier1: list[str] = []
    tier1.append(person_name)
    if en_name.lower() != person_name.lower():
        tier1.append(en_name)
    tier1.append(f"{person_name} portrait")
    if year_str:
        tier1.append(f"{person_name} {year_str}")

    # ---- Tier 2: Name + category/country ----
    tier2: list[str] = []
    for hint in hints[:2]:
        tier2.append(f"{person_name} {hint}")
    if birth_country:
        tier2.append(f"{person_name} {birth_country}")
    if en_name.lower() != person_name.lower():
        tier2.append(f"{en_name} portrait")
        for hint in hints[:1]:
            tier2.append(f"{en_name} {hint}")

    # ---- Tier 3: Proper noun subsets ----
    tier3: list[str] = []
    if len(proper_nouns) >= 2:
        # Try last name only
        tier3.append(proper_nouns[-1])
        tier3.append(f"{proper_nouns[-1]} portrait")
    if proper_nouns:
        pn_str = " ".join(proper_nouns)
        if pn_str.lower() != person_name.lower():
            tier3.append(pn_str)

    # Dedup
    def _dedup(queries: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for q in queries:
            ql = q.strip().lower()
            if ql and ql not in seen:
                seen.add(ql)
                out.append(q.strip())
        return out

    tier1 = _dedup(tier1)
    tier2 = _dedup(tier2)
    tier3 = _dedup(tier3)

    # --- Tier 1: Direct name ---
    for query in tier1[:6]:
        batch = _search_commons_batch(query, seen_urls, limit=30)
        images.extend(b for b in batch if _is_relevant(b))
        if len(images) >= 15:
            break

    # --- Tier 2: Name + context ---
    if len(images) < 15:
        for query in tier2[:8]:
            batch = _search_commons_batch(query, seen_urls, limit=25)
            images.extend(b for b in batch if _is_relevant(b))
            if len(images) >= 25:
                break

    # --- Tier 3: Proper nouns ---
    if len(images) < 10:
        for query in tier3[:4]:
            batch = _search_commons_batch(query, seen_urls, limit=20)
            images.extend(b for b in batch if _is_relevant(b))
            if len(images) >= 20:
                break

    # --- Wikipedia article images ---
    if len(images) < 10:
        wiki_queries = [person_name]
        if en_name.lower() != person_name.lower():
            wiki_queries.append(en_name)
        for query in wiki_queries:
            if len(images) >= 30:
                break
            batch = _search_wiki_article_images(query, seen_urls)
            images.extend(batch)

    return images[:40]


def save_annotation_photo(
    conn: Any,
    annotation_id: int,
    image_url: str,
    source_page: str = "",
    city_slug: str = "",
) -> dict[str, Any]:
    """Download and save a photo for an annotation, and also add it to the city photo library."""
    result = download_web_image(image_url)
    if not result:
        return {"success": False, "error": "Impossible de télécharger l'image."}

    file_bytes, ext = result
    ANNOTATION_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"ann_{annotation_id}_{uuid.uuid4().hex[:8]}{ext}"
    dest = ANNOTATION_PHOTO_DIR / filename
    dest.write_bytes(file_bytes)

    # Remove old annotation photo if exists
    old = conn.execute(
        "SELECT photo_filename FROM dim_annotation WHERE annotation_id = ?",
        (annotation_id,),
    ).fetchone()
    if old and old["photo_filename"]:
        old_path = ANNOTATION_PHOTO_DIR / old["photo_filename"]
        if old_path.exists():
            old_path.unlink()

    conn.execute(
        "UPDATE dim_annotation SET photo_filename = ?, photo_source_url = ? WHERE annotation_id = ?",
        (filename, source_page, annotation_id),
    )

    # Also add to city photo library if city_slug is provided
    if city_slug:
        ann_row = conn.execute(
            "SELECT da.annotation_label, dc.city_id "
            "FROM dim_annotation da "
            "JOIN fact_city_population fcp ON fcp.annotation_id = da.annotation_id "
            "JOIN dim_city dc ON dc.city_id = fcp.city_id "
            "WHERE da.annotation_id = ? AND dc.city_slug = ? "
            "LIMIT 1",
            (annotation_id, city_slug),
        ).fetchone()
        if ann_row:
            import re
            label = re.sub(r'[\U00010000-\U0010ffff]', '', ann_row["annotation_label"]).strip()
            save_photo_to_library(
                conn,
                city_id=ann_row["city_id"],
                city_slug=city_slug,
                file_bytes=file_bytes,
                original_filename=f"annotation{ext}",
                source_url=source_page,
                attribution="Wikimedia Commons",
                caption=label,
            )

    conn.commit()
    return {"success": True, "filename": filename}


def link_existing_photo_to_annotation(
    conn: Any,
    annotation_id: int,
    city_slug: str,
    photo_id: int,
) -> dict[str, Any]:
    """Link an existing city photo to an annotation by copying it."""
    row = conn.execute(
        "SELECT filename FROM dim_city_photo WHERE photo_id = ?", (photo_id,)
    ).fetchone()
    if not row:
        return {"success": False, "error": "Photo introuvable."}

    src_path = CITY_PHOTO_DIR / city_slug / row["filename"]
    if not src_path.exists():
        return {"success": False, "error": "Fichier introuvable."}

    ANNOTATION_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(row["filename"]).suffix
    new_filename = f"ann_{annotation_id}_{uuid.uuid4().hex[:8]}{ext}"
    dest = ANNOTATION_PHOTO_DIR / new_filename
    dest.write_bytes(src_path.read_bytes())

    # Remove old photo if exists
    old = conn.execute(
        "SELECT photo_filename FROM dim_annotation WHERE annotation_id = ?",
        (annotation_id,),
    ).fetchone()
    if old and old["photo_filename"]:
        old_path = ANNOTATION_PHOTO_DIR / old["photo_filename"]
        if old_path.exists():
            old_path.unlink()

    conn.execute(
        "UPDATE dim_annotation SET photo_filename = ?, photo_source_url = '' WHERE annotation_id = ?",
        (new_filename, annotation_id),
    )
    conn.commit()
    return {"success": True, "filename": new_filename}


# ---------------------------------------------------------------------------
# Region photo library (mirrors city photo library — no EXIF columns)
# ---------------------------------------------------------------------------

REGION_PHOTO_LIB_DIR = PROJECT_ROOT / "static" / "images" / "regions"


def get_region_photos(conn: Any, region_slug: str) -> list[dict[str, Any]]:
    """Return all photos for a region from DB."""
    rows = conn.execute(
        """SELECT p.photo_id, p.filename, p.caption, p.source_url, p.attribution,
                  p.is_primary, p.created_at
           FROM dim_region_photo p
           JOIN dim_region r ON r.region_id = p.region_id
           WHERE r.region_slug = ?
           ORDER BY p.is_primary DESC, p.photo_id""",
        (region_slug,),
    ).fetchall()
    return [
        {
            "photo_id": r["photo_id"],
            "filename": r["filename"],
            "photo_path": f"images/regions/{region_slug}/{r['filename']}",
            "caption": r["caption"],
            "source_url": r["source_url"],
            "attribution": r["attribution"],
            "is_primary": bool(r["is_primary"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def save_region_photo_to_library(
    conn: Any,
    region_id: int,
    region_slug: str,
    file_bytes: bytes,
    original_filename: str,
    source_url: str = "",
    attribution: str = "",
    caption: str = "",
    set_primary: bool = False,
    image_url: str = "",
) -> dict[str, Any]:
    """Save a photo into the per-region directory and register in dim_region_photo."""
    suffix = Path(original_filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return {"success": False, "error": "Format non supporté. Utilisez JPG, PNG ou WebP."}

    photo_dir = REGION_PHOTO_LIB_DIR / region_slug
    photo_dir.mkdir(parents=True, exist_ok=True)
    unique_name = f"{uuid.uuid4().hex[:12]}{suffix}"
    dest = photo_dir / unique_name
    dest.write_bytes(file_bytes)
    generate_thumbnail(dest)

    if set_primary:
        conn.execute("UPDATE dim_region_photo SET is_primary = FALSE WHERE region_id = ?", (region_id,))

    existing_count = conn.execute(
        "SELECT COUNT(*) FROM dim_region_photo WHERE region_id = ?", (region_id,)
    ).fetchone()[0]
    if existing_count == 0:
        set_primary = True

    cursor = conn.execute(
        """INSERT INTO dim_region_photo
           (region_id, filename, caption, source_url, attribution, is_primary, image_url)
           VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING photo_id""",
        (region_id, unique_name, caption, source_url, attribution, bool(set_primary), image_url),
    )
    photo_id = cursor.fetchone()[0]
    conn.commit()
    return {"success": True, "photo_id": photo_id, "filename": unique_name}


def delete_region_photo_from_library(conn: Any, photo_id: int, region_slug: str) -> bool:
    """Delete a region photo from DB and disk."""
    row = conn.execute(
        "SELECT r.region_id, p.filename, p.is_primary "
        "FROM dim_region_photo p "
        "JOIN dim_region r ON r.region_id = p.region_id "
        "WHERE p.photo_id = ? AND r.region_slug = ?",
        (photo_id, region_slug),
    ).fetchone()
    if not row:
        return False
    photo_path = REGION_PHOTO_LIB_DIR / region_slug / row["filename"]
    if photo_path.exists():
        photo_path.unlink()
    was_primary = bool(row["is_primary"])
    region_id = row["region_id"]
    conn.execute("DELETE FROM dim_region_photo WHERE photo_id = ?", (photo_id,))
    if was_primary:
        next_row = conn.execute(
            "SELECT photo_id FROM dim_region_photo WHERE region_id = ? ORDER BY photo_id LIMIT 1",
            (region_id,),
        ).fetchone()
        if next_row:
            conn.execute(
                "UPDATE dim_region_photo SET is_primary = TRUE WHERE photo_id = ?",
                (next_row["photo_id"],),
            )
    conn.commit()
    return True


def set_region_photo_primary(conn: Any, photo_id: int, region_id: int) -> None:
    """Set a region photo as the primary."""
    conn.execute("UPDATE dim_region_photo SET is_primary = FALSE WHERE region_id = ?", (region_id,))
    conn.execute("UPDATE dim_region_photo SET is_primary = TRUE WHERE photo_id = ?", (photo_id,))
    conn.commit()


def save_annotation_photo_for_region(
    conn: Any,
    annotation_id: int,
    image_url: str,
    source_page: str = "",
    region_slug: str = "",
) -> dict[str, Any]:
    """Download and save a photo for an annotation, also add it to the region photo library."""
    result = download_web_image(image_url)
    if not result:
        return {"success": False, "error": "Impossible de télécharger l'image."}

    file_bytes, ext = result
    ANNOTATION_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"ann_{annotation_id}_{uuid.uuid4().hex[:8]}{ext}"
    dest = ANNOTATION_PHOTO_DIR / filename
    dest.write_bytes(file_bytes)

    old = conn.execute(
        "SELECT photo_filename FROM dim_annotation WHERE annotation_id = ?", (annotation_id,)
    ).fetchone()
    if old and old["photo_filename"]:
        old_path = ANNOTATION_PHOTO_DIR / old["photo_filename"]
        if old_path.exists():
            old_path.unlink()

    conn.execute(
        "UPDATE dim_annotation SET photo_filename = ?, photo_source_url = ? WHERE annotation_id = ?",
        (filename, source_page, annotation_id),
    )

    if region_slug:
        import re as _re
        ann_row = conn.execute(
            "SELECT da.annotation_label, r.region_id "
            "FROM dim_annotation da "
            "JOIN fact_region_population frp ON frp.annotation_id = da.annotation_id "
            "JOIN dim_region r ON r.region_id = frp.region_id "
            "WHERE da.annotation_id = ? AND r.region_slug = ? LIMIT 1",
            (annotation_id, region_slug),
        ).fetchone()
        if ann_row:
            label = _re.sub(r'[\U00010000-\U0010ffff]', '', ann_row["annotation_label"]).strip()
            save_region_photo_to_library(
                conn,
                region_id=ann_row["region_id"],
                region_slug=region_slug,
                file_bytes=file_bytes,
                original_filename=f"annotation{ext}",
                source_url=source_page,
                attribution="Wikimedia Commons",
                caption=label,
            )

    conn.commit()
    return {"success": True, "filename": filename}


def link_existing_region_photo_to_annotation(
    conn: Any,
    annotation_id: int,
    region_slug: str,
    photo_id: int,
) -> dict[str, Any]:
    """Link an existing region photo to an annotation by copying it."""
    row = conn.execute(
        "SELECT p.filename FROM dim_region_photo p "
        "JOIN dim_region r ON r.region_id = p.region_id "
        "WHERE p.photo_id = ? AND r.region_slug = ?",
        (photo_id, region_slug),
    ).fetchone()
    if not row:
        return {"success": False, "error": "Photo introuvable."}

    src_path = REGION_PHOTO_LIB_DIR / region_slug / row["filename"]
    if not src_path.exists():
        return {"success": False, "error": "Fichier introuvable."}

    ANNOTATION_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(row["filename"]).suffix
    new_filename = f"ann_{annotation_id}_{uuid.uuid4().hex[:8]}{ext}"
    dest = ANNOTATION_PHOTO_DIR / new_filename
    dest.write_bytes(src_path.read_bytes())

    old = conn.execute(
        "SELECT photo_filename FROM dim_annotation WHERE annotation_id = ?", (annotation_id,)
    ).fetchone()
    if old and old["photo_filename"]:
        old_path = ANNOTATION_PHOTO_DIR / old["photo_filename"]
        if old_path.exists():
            old_path.unlink()

    conn.execute(
        "UPDATE dim_annotation SET photo_filename = ?, photo_source_url = '' WHERE annotation_id = ?",
        (new_filename, annotation_id),
    )
    conn.commit()
    return {"success": True, "filename": new_filename}


# ---------------------------------------------------------------------------
# Country photo library helpers
# ---------------------------------------------------------------------------

COUNTRY_PHOTO_LIB_DIR = PROJECT_ROOT / "static" / "images" / "countries"


def get_country_photos(conn: Any, country_slug: str) -> list[dict[str, Any]]:
    """Return all photos for a country from DB."""
    rows = conn.execute(
        """SELECT p.photo_id, p.filename, p.caption, p.source_url, p.attribution,
                  p.is_primary, p.created_at
           FROM dim_country_photo p
           JOIN dim_country c ON c.country_id = p.country_id
           WHERE c.country_slug = ?
           ORDER BY p.is_primary DESC, p.photo_id""",
        (country_slug,),
    ).fetchall()
    return [
        {
            "photo_id": r["photo_id"],
            "filename": r["filename"],
            "photo_path": f"images/countries/{country_slug}/{r['filename']}",
            "caption": r["caption"],
            "source_url": r["source_url"],
            "attribution": r["attribution"],
            "is_primary": bool(r["is_primary"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def save_country_photo_to_library(
    conn: Any,
    country_id: int,
    country_slug: str,
    file_bytes: bytes,
    original_filename: str,
    source_url: str = "",
    attribution: str = "",
    caption: str = "",
    set_primary: bool = False,
    image_url: str = "",
) -> dict[str, Any]:
    """Save a photo into the per-country directory and register in dim_country_photo."""
    suffix = Path(original_filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return {"success": False, "error": "Format non supporté. Utilisez JPG, PNG ou WebP."}

    photo_dir = COUNTRY_PHOTO_LIB_DIR / country_slug
    photo_dir.mkdir(parents=True, exist_ok=True)
    unique_name = f"{uuid.uuid4().hex[:12]}{suffix}"
    dest = photo_dir / unique_name
    dest.write_bytes(file_bytes)
    generate_thumbnail(dest)

    if set_primary:
        conn.execute("UPDATE dim_country_photo SET is_primary = FALSE WHERE country_id = ?", (country_id,))

    existing_count = conn.execute(
        "SELECT COUNT(*) FROM dim_country_photo WHERE country_id = ?", (country_id,)
    ).fetchone()[0]
    if existing_count == 0:
        set_primary = True

    cursor = conn.execute(
        """INSERT INTO dim_country_photo
           (country_id, filename, caption, source_url, attribution, is_primary, image_url)
           VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING photo_id""",
        (country_id, unique_name, caption, source_url, attribution, bool(set_primary), image_url),
    )
    photo_id = cursor.fetchone()[0]
    conn.commit()
    return {"success": True, "photo_id": photo_id, "filename": unique_name}


def delete_country_photo_from_library(conn: Any, photo_id: int, country_slug: str) -> bool:
    """Delete a country photo from DB and disk."""
    row = conn.execute(
        "SELECT c.country_id, p.filename, p.is_primary "
        "FROM dim_country_photo p "
        "JOIN dim_country c ON c.country_id = p.country_id "
        "WHERE p.photo_id = ? AND c.country_slug = ?",
        (photo_id, country_slug),
    ).fetchone()
    if not row:
        return False
    photo_path = COUNTRY_PHOTO_LIB_DIR / country_slug / row["filename"]
    if photo_path.exists():
        photo_path.unlink()
    was_primary = bool(row["is_primary"])
    country_id = row["country_id"]
    conn.execute("DELETE FROM dim_country_photo WHERE photo_id = ?", (photo_id,))
    if was_primary:
        next_row = conn.execute(
            "SELECT photo_id FROM dim_country_photo WHERE country_id = ? ORDER BY photo_id LIMIT 1",
            (country_id,),
        ).fetchone()
        if next_row:
            conn.execute(
                "UPDATE dim_country_photo SET is_primary = TRUE WHERE photo_id = ?",
                (next_row["photo_id"],),
            )
    conn.commit()
    return True


def set_country_photo_primary(conn: Any, photo_id: int, country_id: int) -> None:
    """Set a country photo as the primary."""
    conn.execute("UPDATE dim_country_photo SET is_primary = FALSE WHERE country_id = ?", (country_id,))
    conn.execute("UPDATE dim_country_photo SET is_primary = TRUE WHERE photo_id = ?", (photo_id,))
    conn.commit()


def save_annotation_photo_for_country(
    conn: Any,
    annotation_id: int,
    image_url: str,
    source_page: str = "",
    country_slug: str = "",
) -> dict[str, Any]:
    """Download and save a photo for an annotation, also add it to the country photo library."""
    result = download_web_image(image_url)
    if not result:
        return {"success": False, "error": "Impossible de télécharger l'image."}

    file_bytes, ext = result
    ANNOTATION_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"ann_{annotation_id}_{uuid.uuid4().hex[:8]}{ext}"
    dest = ANNOTATION_PHOTO_DIR / filename
    dest.write_bytes(file_bytes)

    old = conn.execute(
        "SELECT photo_filename FROM dim_annotation WHERE annotation_id = ?", (annotation_id,)
    ).fetchone()
    if old and old["photo_filename"]:
        old_path = ANNOTATION_PHOTO_DIR / old["photo_filename"]
        if old_path.exists():
            old_path.unlink()

    conn.execute(
        "UPDATE dim_annotation SET photo_filename = ?, photo_source_url = ? WHERE annotation_id = ?",
        (filename, source_page, annotation_id),
    )

    if country_slug:
        import re as _re
        ann_row = conn.execute(
            "SELECT da.annotation_label, c.country_id "
            "FROM dim_annotation da "
            "JOIN fact_country_population fcp ON fcp.annotation_id = da.annotation_id "
            "JOIN dim_country c ON c.country_id = fcp.country_id "
            "WHERE da.annotation_id = ? AND c.country_slug = ? LIMIT 1",
            (annotation_id, country_slug),
        ).fetchone()
        if ann_row:
            label = _re.sub(r'[\U00010000-\U0010ffff]', '', ann_row["annotation_label"]).strip()
            save_country_photo_to_library(
                conn,
                country_id=ann_row["country_id"],
                country_slug=country_slug,
                file_bytes=file_bytes,
                original_filename=f"annotation{ext}",
                source_url=source_page,
                attribution="Wikimedia Commons",
                caption=label,
            )

    conn.commit()
    return {"success": True, "filename": filename}


def link_existing_country_photo_to_annotation(
    conn: Any,
    annotation_id: int,
    country_slug: str,
    photo_id: int,
) -> dict[str, Any]:
    """Link an existing country photo to an annotation by copying it."""
    row = conn.execute(
        "SELECT p.filename FROM dim_country_photo p "
        "JOIN dim_country c ON c.country_id = p.country_id "
        "WHERE p.photo_id = ? AND c.country_slug = ?",
        (photo_id, country_slug),
    ).fetchone()
    if not row:
        return {"success": False, "error": "Photo introuvable."}

    src_path = COUNTRY_PHOTO_LIB_DIR / country_slug / row["filename"]
    if not src_path.exists():
        return {"success": False, "error": "Fichier introuvable."}

    ANNOTATION_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(row["filename"]).suffix
    new_filename = f"ann_{annotation_id}_{uuid.uuid4().hex[:8]}{ext}"
    dest = ANNOTATION_PHOTO_DIR / new_filename
    dest.write_bytes(src_path.read_bytes())

    old = conn.execute(
        "SELECT photo_filename FROM dim_annotation WHERE annotation_id = ?", (annotation_id,)
    ).fetchone()
    if old and old["photo_filename"]:
        old_path = ANNOTATION_PHOTO_DIR / old["photo_filename"]
        if old_path.exists():
            old_path.unlink()

    conn.execute(
        "UPDATE dim_annotation SET photo_filename = ?, photo_source_url = '' WHERE annotation_id = ?",
        (new_filename, annotation_id),
    )
    conn.commit()
    return {"success": True, "filename": new_filename}
