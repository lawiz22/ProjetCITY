from __future__ import annotations

import json
import os
import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CITY_PHOTO_DIR = PROJECT_ROOT / "static" / "images" / "cities"
CITY_PHOTO_MANIFEST = CITY_PHOTO_DIR / "manifest.json"
DEFAULT_CITY_PHOTO = "images/cities/default-city.svg"

USER_AGENT = "ProjetCITY/1.0 (city photo library)"
SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
SEARCH_URL = "https://en.wikipedia.org/w/api.php?action=query&list=search&utf8=1&format=json&srlimit=5&srsearch={query}"
WIKI_IMAGES_URL = "https://en.wikipedia.org/w/api.php?action=query&titles={title}&prop=images&imlimit=50&format=json"
WIKI_IMAGEINFO_URL = "https://en.wikipedia.org/w/api.php?action=query&titles={titles}&prop=imageinfo&iiprop=url|size|mime|thumbmime&iiurlwidth=400&format=json"
COMMONS_SEARCH_URL = "https://commons.wikimedia.org/w/api.php?action=query&list=search&srnamespace=6&srsearch={query}&srlimit=40&format=json"
COMMONS_IMAGEINFO_URL = "https://commons.wikimedia.org/w/api.php?action=query&titles={titles}&prop=imageinfo&iiprop=url|size|mime&iiurlwidth=400&format=json"

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


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


# ---------------------------------------------------------------------------
# Primary photo helper (DB-first, fallback to manifest)
# ---------------------------------------------------------------------------

def get_city_photo(slug: str, conn: Any = None) -> dict[str, Any]:
    """Return the primary photo for a city. Checks DB first, then manifest."""
    if conn is not None:
        row = conn.execute(
            """SELECT p.photo_id, p.filename, p.source_url, p.attribution
               FROM dim_city_photo p
               JOIN dim_city c ON c.city_id = p.city_id
               WHERE c.city_slug = ? AND p.is_primary = 1
               LIMIT 1""",
            (slug,),
        ).fetchone()
        if row:
            return {
                "photo_path": f"images/cities/{slug}/{row['filename']}",
                "photo_source": row["source_url"],
                "photo_attribution": row["attribution"],
                "has_photo": True,
            }
        # Check if any photo exists (pick first)
        row = conn.execute(
            """SELECT p.photo_id, p.filename, p.source_url, p.attribution
               FROM dim_city_photo p
               JOIN dim_city c ON c.city_id = p.city_id
               WHERE c.city_slug = ?
               ORDER BY p.photo_id
               LIMIT 1""",
            (slug,),
        ).fetchone()
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
) -> dict[str, Any]:
    """Save a photo file into the per-city directory and register in DB."""
    suffix = Path(original_filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return {"success": False, "error": "Format non supporté. Utilisez JPG, PNG ou WebP."}

    photo_dir = _ensure_city_photo_dir(city_slug)
    unique_name = f"{uuid.uuid4().hex[:12]}{suffix}"
    dest = photo_dir / unique_name
    dest.write_bytes(file_bytes)

    # Extract EXIF
    exif = extract_exif(str(dest))

    # If set_primary, unset other primaries
    if set_primary:
        conn.execute(
            "UPDATE dim_city_photo SET is_primary = 0 WHERE city_id = ?", (city_id,)
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
            exif_lat, exif_lon, exif_date, exif_camera)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           RETURNING photo_id""",
        (city_id, unique_name, caption, source_url, attribution,
         1 if set_primary else 0,
         exif["lat"], exif["lon"], exif["date"], exif["camera"]),
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
                "UPDATE dim_city_photo SET is_primary = 1 WHERE photo_id = ?",
                (next_row["photo_id"],),
            )

    conn.commit()
    return True


def set_photo_primary(conn: Any, photo_id: int, city_id: int) -> bool:
    """Set a photo as the primary for its city."""
    conn.execute(
        "UPDATE dim_city_photo SET is_primary = 0 WHERE city_id = ?", (city_id,)
    )
    conn.execute(
        "UPDATE dim_city_photo SET is_primary = 1 WHERE photo_id = ?", (photo_id,)
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
    "&utf8=1&format=json&srlimit=1&srsearch={query}"
)


def _translate_label_to_english(label: str) -> str | None:
    """Try to find an English equivalent of a French annotation label via Wikipedia search."""
    import re
    # Strip emoji and parenthesized year
    cleaned = re.sub(r'[\U00010000-\U0010ffff]', '', label)  # remove emoji
    cleaned = re.sub(r'\(\d{4}\)', '', cleaned).strip()  # remove (year)
    cleaned = re.sub(r'\s*—\s*', ' ', cleaned)  # replace em-dash with space
    if not cleaned:
        return None
    try:
        url = WIKTIONARY_TRANSLATE_URL.format(query=quote(cleaned))
        data = _http_get_json(url)
        results = data.get("query", {}).get("search", [])
        if results:
            return results[0].get("title")
    except Exception:
        pass
    return None


def _build_annotation_search_queries(label: str, city_name: str) -> list[str]:
    """Build multiple search queries from an annotation label for better image results."""
    import re
    # Clean label: remove emoji
    cleaned = re.sub(r'[\U00010000-\U0010ffff]', '', label).strip()
    # Extract text before and after em-dash
    parts = [p.strip() for p in cleaned.split('—') if p.strip()]
    # Remove year in parentheses
    parts = [re.sub(r'\(\d{4}\)', '', p).strip() for p in parts]

    queries = []
    # Full cleaned label + city
    full = ' '.join(parts)
    if full:
        queries.append(f"{full} {city_name}")
        queries.append(full)
    # First part alone (usually the key event)
    if len(parts) > 1 and parts[0]:
        queries.append(f"{parts[0]} {city_name}")

    return queries


def search_annotation_images(
    label: str, city_name: str, region: str | None, country: str | None
) -> list[dict[str, Any]]:
    """Search Wikipedia + Wikimedia Commons for annotation-related images.

    Uses the annotation label as query, tries English translation too.
    """
    queries = _build_annotation_search_queries(label, city_name)

    # Try English translation for more results
    en_title = _translate_label_to_english(label)
    if en_title and en_title not in queries:
        queries.append(f"{en_title} {city_name}")
        queries.append(en_title)

    images: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for query in queries[:4]:
        # Search Wikimedia Commons
        try:
            url = COMMONS_SEARCH_URL.format(query=quote(query))
            data = _http_get_json(url)
        except Exception:
            continue

        results = data.get("query", {}).get("search", [])
        file_titles = [
            r["title"] for r in results
            if r.get("title") and any(r["title"].lower().endswith(ext)
                                      for ext in (".jpg", ".jpeg", ".png", ".webp"))
        ]

        for batch_start in range(0, min(len(file_titles), 20), 10):
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

                images.append({
                    "url": img_url,
                    "thumb_url": thumb_url,
                    "title": ipage.get("title", ""),
                    "width": width,
                    "height": height,
                    "source_page": f"https://commons.wikimedia.org/wiki/File:{quote(page_title, safe='_(),.-')}",
                })

        if len(images) >= 20:
            break

    return images[:20]


def save_annotation_photo(
    conn: Any,
    annotation_id: int,
    image_url: str,
    source_page: str = "",
) -> dict[str, Any]:
    """Download and save a photo for an annotation."""
    result = download_web_image(image_url)
    if not result:
        return {"success": False, "error": "Impossible de télécharger l'image."}

    file_bytes, ext = result
    ANNOTATION_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"ann_{annotation_id}_{uuid.uuid4().hex[:8]}{ext}"
    dest = ANNOTATION_PHOTO_DIR / filename
    dest.write_bytes(file_bytes)

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
        "UPDATE dim_annotation SET photo_filename = ?, photo_source_url = ? WHERE annotation_id = ?",
        (filename, source_page, annotation_id),
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