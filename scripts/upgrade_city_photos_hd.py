"""
Upgrade all city photos to high resolution (original from Wikipedia).

For each city:
1. Finds the Wikipedia summary page
2. Downloads the ORIGINAL (full-res) image instead of thumbnail
3. Replaces the existing photo on disk
4. Updates the DB record if the city uses the photo library (dim_city_photo)
5. Updates the manifest for legacy flat-file cities

Usage:
    python scripts/upgrade_city_photos_hd.py          # all cities
    python scripts/upgrade_city_photos_hd.py montreal  # single city by slug
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import quote, urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.services.analytics import AnalyticsService
from app.services.city_photos import (
    CITY_PHOTO_DIR,
    CITY_PHOTO_MANIFEST,
    clear_city_photo_manifest_cache,
)

USER_AGENT = "CentralCityScrutinizer/1.0 (https://github.com/projetcity; contact: projetcity@localhost)"
SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
SEARCH_URL = (
    "https://en.wikipedia.org/w/api.php?action=query&list=search"
    "&utf8=1&format=json&srlimit=5&srsearch={query}"
)

TITLE_OVERRIDES = {
    "boucherville-quebec": ["Boucherville"],
    "charlottetown-prince-edward-island": ["Charlottetown"],
    "des-moines-iowa": ["Des Moines, Iowa"],
    "gatineau-quebec": ["Gatineau"],
    "laval-quebec": ["Laval, Quebec"],
    "london-ontario": ["London, Ontario"],
    "long-beach-california": ["Long Beach, California"],
    "longueuil-quebec": ["Longueuil"],
    "miami-florida": ["Miami"],
    "montreal-quebec": ["Montreal"],
    "new-orleans-louisiana": ["New Orleans"],
    "new-york-city": ["New York City"],
    "north-bay-ontario": ["North Bay, Ontario"],
    "ottawa-ontario": ["Ottawa"],
    "quebec-city-quebec": ["Quebec City"],
    "saint-jean-sur-richelieu-quebec": ["Saint-Jean-sur-Richelieu"],
    "salt-lake-city-utah": ["Salt Lake City"],
    "san-francisco-california": ["San Francisco"],
    "sorel-tracy-quebec": ["Sorel-Tracy"],
    "st-johns-newfoundland-and-labrador": ["St. John's, Newfoundland and Labrador"],
    "st-louis-missouri": ["St. Louis"],
    "trois-rivieres-quebec": ["Trois-Rivieres"],
    "washington-district-of-columbia": ["Washington, D.C."],
}


def http_get_json(url: str) -> dict:
    last_error: Exception | None = None
    for attempt in range(4):
        request = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(request, timeout=15) as response:
                return json.load(response)
        except HTTPError as exc:
            last_error = exc
            if exc.code == 429:
                wait = 10 * (attempt + 1)
                print(f"(api 429, wait {wait}s)", end=" ", flush=True)
                time.sleep(wait)
                continue
            if exc.code not in {403, 500, 502, 503, 504}:
                raise
        except URLError as exc:
            last_error = exc
        time.sleep(1.5 * (attempt + 1))
    if last_error:
        raise last_error
    raise RuntimeError("HTTP request failed.")


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")


def build_region_variants(region: str) -> list[str]:
    if not region:
        return []
    normalized = unicodedata.normalize("NFKD", region).encode("ascii", "ignore").decode("ascii")
    variants = [region]
    if normalized != region:
        variants.append(normalized)
    return variants


def candidate_titles(city: dict) -> list[str]:
    slug = city["city_slug"]
    overrides = TITLE_OVERRIDES.get(slug)
    if overrides:
        return overrides
    city_name = city["city_name"]
    candidates = [city_name]
    for region in build_region_variants(city.get("region") or ""):
        candidates.append(f"{city_name}, {region}")
    if city.get("country"):
        candidates.append(f"{city_name}, {city['country']}")
    return list(dict.fromkeys(candidates))


def fetch_summary(title: str) -> dict | None:
    url = SUMMARY_URL.format(title=quote(title.replace(" ", "_"), safe="_(),.-"))
    try:
        data = http_get_json(url)
    except Exception:
        return None
    if data.get("type") == "https://mediawiki.org/wiki/HyperSwitch/errors/not_found":
        return None
    return data


def search_titles(query: str) -> list[str]:
    try:
        data = http_get_json(SEARCH_URL.format(query=quote(query)))
    except Exception:
        return []
    results = data.get("query", {}).get("search", [])
    return list(dict.fromkeys(r["title"] for r in results if isinstance(r.get("title"), str)))


HD_THUMB_WIDTH = 1280  # Wikimedia-approved thumbnail size


def _make_hd_thumb_url(thumb_url: str, width: int = HD_THUMB_WIDTH) -> str:
    """Convert a Wikimedia thumbnail URL to a higher-resolution thumbnail.

    Wikimedia thumb URLs look like:
        .../thumb/a/ab/File.jpg/320px-File.jpg
    We replace the last segment's width prefix to get e.g.:
        .../thumb/a/ab/File.jpg/1280px-File.jpg
    """
    if "/thumb/" not in thumb_url:
        return thumb_url
    # Replace the NNNpx- prefix in the last path segment
    parts = thumb_url.rsplit("/", 1)
    if len(parts) == 2:
        import re as _re
        new_segment = _re.sub(r'^\d+px-', f'{width}px-', parts[1])
        return parts[0] + "/" + new_segment
    return thumb_url


def select_hd_image(summary: dict) -> str | None:
    """Select a high-resolution (1280px) thumbnail from a Wikipedia summary.

    Uses Wikimedia's official thumbnail resizing rather than downloading
    the original file (which triggers 429 rate limits).
    """
    # Try thumbnail first — we'll resize it to 1280px
    thumbnail = summary.get("thumbnail", {})
    if isinstance(thumbnail, dict) and isinstance(thumbnail.get("source"), str):
        return _make_hd_thumb_url(thumbnail["source"], HD_THUMB_WIDTH)
    # Fallback: build thumb URL from original
    original = summary.get("originalimage", {})
    if isinstance(original, dict) and isinstance(original.get("source"), str):
        orig_url = original["source"]
        # Convert original URL to thumb URL format
        # Original: .../a/ab/File.jpg  ->  .../thumb/a/ab/File.jpg/1280px-File.jpg
        if "/thumb/" not in orig_url:
            filename = orig_url.rsplit("/", 1)[-1]
            thumb_url = orig_url.replace(
                "/commons/", "/commons/thumb/"
            ).replace(
                "/en/", "/en/thumb/"
            ) + f"/{HD_THUMB_WIDTH}px-{filename}"
            return thumb_url
        return _make_hd_thumb_url(orig_url, HD_THUMB_WIDTH)
    return None


def download_image(url: str, destination: Path) -> int:
    """Download image, return file size in bytes."""
    last_error: Exception | None = None
    for attempt in range(5):
        request = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(request, timeout=30) as response:
                data = response.read()
                destination.write_bytes(data)
                return len(data)
        except HTTPError as exc:
            last_error = exc
            if exc.code == 429:
                wait = 15 * (attempt + 1)
                print(f"(dl 429, wait {wait}s)", end=" ", flush=True)
                time.sleep(wait)
                continue
            if exc.code not in {403, 500, 502, 503, 504}:
                raise
        except URLError as exc:
            last_error = exc
        time.sleep(2.0 * (attempt + 1))
    if last_error:
        raise last_error
    raise RuntimeError("Image download failed.")


def choose_extension(image_url: str) -> str:
    suffix = Path(urlsplit(image_url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return suffix
    return ".jpg"


def find_hd_photo(city: dict) -> tuple[str, dict] | tuple[None, None]:
    """Find a high-resolution (1280px) photo for a city via Wikipedia."""
    attempts = candidate_titles(city)
    searched: list[str] = []

    for title in attempts:
        summary = fetch_summary(title)
        if summary:
            image_url = select_hd_image(summary)
            if image_url:
                return image_url, summary
        searched.extend(search_titles(title))

    for title in searched:
        summary = fetch_summary(title)
        if summary:
            image_url = select_hd_image(summary)
            if image_url:
                return image_url, summary

    return None, None


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def main() -> None:
    filter_slug = None
    start_from = 0
    for arg in sys.argv[1:]:
        if arg.isdigit():
            start_from = int(arg) - 1  # 1-based to 0-based
        else:
            filter_slug = arg

    CITY_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    app = create_app()

    # Load existing manifest
    manifest: dict[str, dict] = {}
    if CITY_PHOTO_MANIFEST.exists():
        try:
            manifest = json.loads(CITY_PHOTO_MANIFEST.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}

    success_count = 0
    skipped_count = 0
    failed: list[str] = []
    upgraded: list[tuple[str, int, int]] = []

    with app.app_context():
        from app.db import get_db
        cities = AnalyticsService().get_city_directory(
            {"country": None, "region": None, "search": None, "period": None}
        )

        if filter_slug:
            cities = [c for c in cities if c["city_slug"] == filter_slug]
            if not cities:
                print(f"Ville '{filter_slug}' non trouvée.")
                return

        db = get_db()
        total = len(cities)

        for i, city in enumerate(cities, 1):
            if i - 1 < start_from:
                continue
            slug = city["city_slug"]
            print(f"[{i}/{total}] {slug}...", end=" ", flush=True)

            image_url, summary = find_hd_photo(city)
            if not image_url or not summary:
                print("SKIP (pas de photo Wikipedia)")
                failed.append(slug)
                time.sleep(1.0)
                continue

            extension = choose_extension(image_url)

            # --- Check for per-city directory (DB photos) ---
            city_dir = CITY_PHOTO_DIR / slug
            db_row = db.execute(
                """SELECT p.photo_id, p.filename, c.city_id
                   FROM dim_city_photo p
                   JOIN dim_city c ON c.city_id = p.city_id
                   WHERE c.city_slug = ? AND p.is_primary = 1
                   LIMIT 1""",
                (slug,),
            ).fetchone()

            if db_row:
                # DB-based photo — replace in per-city directory
                old_path = city_dir / db_row["filename"]
                old_size = old_path.stat().st_size if old_path.exists() else 0

                new_filename = f"{db_row['filename'].rsplit('.', 1)[0]}{extension}"
                new_path = city_dir / new_filename

                try:
                    new_size = download_image(image_url, new_path)
                except Exception as exc:
                    print(f"ERREUR download: {exc}")
                    failed.append(slug)
                    continue

                # If extension changed, remove old file and update DB
                if new_filename != db_row["filename"]:
                    if old_path.exists() and old_path != new_path:
                        old_path.unlink()
                    db.execute(
                        "UPDATE dim_city_photo SET filename = ?, source_url = ? WHERE photo_id = ?",
                        (new_filename,
                         summary.get("content_urls", {}).get("desktop", {}).get("page", ""),
                         db_row["photo_id"]),
                    )
                    db.commit()
                else:
                    db.execute(
                        "UPDATE dim_city_photo SET source_url = ? WHERE photo_id = ?",
                        (summary.get("content_urls", {}).get("desktop", {}).get("page", ""),
                         db_row["photo_id"]),
                    )
                    db.commit()

                upgraded.append((slug, old_size, new_size))
                print(f"HD {format_size(old_size)} -> {format_size(new_size)}")

            else:
                # Legacy manifest-based — flat file in CITY_PHOTO_DIR
                filename = f"{slug}{extension}"
                destination = CITY_PHOTO_DIR / filename
                old_size = destination.stat().st_size if destination.exists() else 0

                try:
                    new_size = download_image(image_url, destination)
                except Exception as exc:
                    print(f"ERREUR download: {exc}")
                    failed.append(slug)
                    continue

                manifest[slug] = {
                    "filename": filename,
                    "source_page": summary.get("content_urls", {}).get("desktop", {}).get("page", ""),
                    "source_image": image_url,
                    "attribution": "Image Wikipedia/Wikimedia — haute résolution.",
                }
                upgraded.append((slug, old_size, new_size))
                print(f"HD {format_size(old_size)} -> {format_size(new_size)}")

            success_count += 1
            time.sleep(2.0)  # Respectful rate limiting for Wikimedia

    # Save manifest
    CITY_PHOTO_MANIFEST.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    clear_city_photo_manifest_cache()

    # Summary
    print(f"\n{'='*60}")
    print(f"Photos HD téléchargées : {success_count}/{total}")
    if failed:
        print(f"Échecs ({len(failed)}) : {', '.join(failed)}")
    if upgraded:
        total_old = sum(o for _, o, _ in upgraded)
        total_new = sum(n for _, _, n in upgraded)
        print(f"Taille totale : {format_size(total_old)} -> {format_size(total_new)}")
        # Show biggest upgrades
        biggest = sorted(upgraded, key=lambda x: x[2] - x[1], reverse=True)[:10]
        if biggest:
            print("\nPlus gros gains :")
            for slug, old, new in biggest:
                print(f"  {slug}: {format_size(old)} -> {format_size(new)}")


if __name__ == "__main__":
    main()
