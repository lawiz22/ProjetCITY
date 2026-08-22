"""Manage the cached list of possible regions per country.

Stored under data/country_regions/{country_slug}.json as::

    {"regions": ["Alberta", "British Columbia", ...], "generated_at": "..."}
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
COUNTRY_REGIONS_DIR = _PROJECT_ROOT / "data" / "country_regions"


def _path_for(country_slug: str) -> Path:
    return COUNTRY_REGIONS_DIR / f"{country_slug}.json"


def load_country_regions(country_slug: str) -> list[str] | None:
    """Return the cached list of region names for a country, or None if not generated yet."""
    path = _path_for(country_slug)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    if isinstance(data, list):
        return [str(x).strip() for x in data if str(x).strip()]
    if isinstance(data, dict):
        regions = data.get("regions", [])
        if isinstance(regions, list):
            return [str(x).strip() for x in regions if str(x).strip()]
    return None


def save_country_regions(country_slug: str, regions: list[str]) -> Path:
    """Persist the list of possible region names for a country."""
    COUNTRY_REGIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = _path_for(country_slug)
    cleaned = []
    seen: set[str] = set()
    for name in regions:
        n = str(name).strip()
        key = n.lower()
        if n and key not in seen:
            cleaned.append(n)
            seen.add(key)
    payload: dict[str, Any] = {
        "regions": cleaned,
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def parse_regions_reply(reply: str) -> list[str]:
    """Best-effort parser: accepts JSON array, JSON object with `regions`, or bullet list."""
    text = (reply or "").strip()
    if not text:
        return []
    # Strip markdown code fences
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
        text = text.strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    # Try JSON first
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
        if isinstance(data, dict):
            regions = data.get("regions") or data.get("Regions") or []
            if isinstance(regions, list):
                return [str(x).strip() for x in regions if str(x).strip()]
    except Exception:
        pass
    # Fallback: line by line, strip bullets/numbering
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        s = s.lstrip("-*•").strip()
        # remove leading "1." / "1)" numbering
        while s and s[0].isdigit():
            s = s[1:]
        s = s.lstrip(".)-: ").strip()
        # remove trailing commas / quotes
        s = s.strip('",;')
        if s and not s.lower().startswith(("regions", "voici", "liste", "réponse")):
            out.append(s)
    return out
