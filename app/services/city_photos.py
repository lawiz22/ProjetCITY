from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CITY_PHOTO_DIR = PROJECT_ROOT / "static" / "images" / "cities"
CITY_PHOTO_MANIFEST = CITY_PHOTO_DIR / "manifest.json"
DEFAULT_CITY_PHOTO = "images/cities/default-city.svg"


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


def get_city_photo(slug: str) -> dict[str, Any]:
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


def clear_city_photo_manifest_cache() -> None:
    load_city_photo_manifest.cache_clear()