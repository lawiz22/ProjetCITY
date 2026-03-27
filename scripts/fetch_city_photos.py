from __future__ import annotations

import json
import re
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
from app.services.city_photos import CITY_PHOTO_DIR, CITY_PHOTO_MANIFEST, clear_city_photo_manifest_cache


USER_AGENT = "CentralCityScrutinizer/1.0 (city photo cache)"
SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
SEARCH_URL = "https://en.wikipedia.org/w/api.php?action=query&list=search&utf8=1&format=json&srlimit=5&srsearch={query}"

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
            with urlopen(request) as response:
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
    raise RuntimeError("HTTP request failed without a concrete error.")


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = ascii_text.lower()
    ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text)
    return ascii_text.strip("-")


def build_region_variants(region: str) -> list[str]:
    if not region:
        return []
    normalized = unicodedata.normalize("NFKD", region).encode("ascii", "ignore").decode("ascii")
    variants = [region, normalized]
    return [value for index, value in enumerate(variants) if value and value not in variants[:index]]


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

    deduped: list[str] = []
    for candidate in candidates:
        if candidate not in deduped:
            deduped.append(candidate)
    return deduped


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
    titles: list[str] = []
    for result in results:
        title = result.get("title")
        if isinstance(title, str) and title not in titles:
            titles.append(title)
    return titles


def select_image(summary: dict) -> str | None:
    thumbnail = summary.get("thumbnail", {})
    if isinstance(thumbnail, dict) and isinstance(thumbnail.get("source"), str):
        return thumbnail["source"]
    original = summary.get("originalimage", {})
    if isinstance(original, dict) and isinstance(original.get("source"), str):
        return original["source"]
    return None


def download_image(url: str, destination: Path) -> None:
    last_error: Exception | None = None
    for attempt in range(4):
        request = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(request) as response:
                destination.write_bytes(response.read())
            return
        except HTTPError as exc:
            last_error = exc
            if exc.code not in {403, 429, 500, 502, 503, 504}:
                raise
        except URLError as exc:
            last_error = exc
        time.sleep(0.8 * (attempt + 1))
    if last_error:
        raise last_error
    raise RuntimeError("Image download failed without a concrete error.")


def choose_extension(image_url: str) -> str:
    suffix = Path(urlsplit(image_url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return suffix
    return ".jpg"


def find_photo(city: dict) -> tuple[str, dict] | tuple[None, None]:
    attempts = candidate_titles(city)
    searched: list[str] = []

    for title in attempts:
        summary = fetch_summary(title)
        if summary:
            image_url = select_image(summary)
            if image_url:
                return image_url, summary
        searched.extend(search_titles(title))

    for title in searched:
        summary = fetch_summary(title)
        if summary:
            image_url = select_image(summary)
            if image_url:
                return image_url, summary

    return None, None


def main() -> None:
    CITY_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    app = create_app()
    manifest: dict[str, dict[str, str]] = {}
    success_count = 0
    missing: list[str] = []

    with app.app_context():
        cities = AnalyticsService().get_city_directory({"country": None, "region": None, "search": None, "period": None})

    for city in cities:
        image_url, summary = find_photo(city)
        if not image_url or not summary:
            missing.append(city["city_slug"])
            continue

        extension = choose_extension(image_url)
        filename = f"{city['city_slug']}{extension}"
        destination = CITY_PHOTO_DIR / filename
        try:
            download_image(image_url, destination)
        except Exception:
            missing.append(city["city_slug"])
            continue

        manifest[city["city_slug"]] = {
            "filename": filename,
            "source_page": summary.get("content_urls", {}).get("desktop", {}).get("page", ""),
            "source_image": image_url,
            "attribution": "Image cachee depuis Wikipedia/Wikimedia, verifier les licences en cas de redistribution.",
        }
        success_count += 1
        print(f"OK {city['city_slug']} -> {filename}")
        time.sleep(0.2)

    CITY_PHOTO_MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    clear_city_photo_manifest_cache()
    print(f"\nPhotos telechargees: {success_count}/{len(cities)}")
    if missing:
        print("Sans photo:", ", ".join(missing))


if __name__ == "__main__":
    main()