"""Build the ref_city reference table using Mammouth AI.

Asks the AI for the top cities per Canadian province/territory and US state,
then stores them in data/ref_cities.json and imports into SQLite.

Usage:
    python scripts/build_ref_cities.py               # full run (all regions)
    python scripts/build_ref_cities.py --import-only  # skip AI, import existing JSON
    python scripts/build_ref_cities.py --region "Québec"  # single region
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

# ── paths ────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.mammouth_ai import load_settings, generate_city

DB_PATH = ROOT / "data" / "city_analysis.db"
JSON_PATH = ROOT / "data" / "ref_cities.json"

# ── region lists ─────────────────────────────────────────────────
CA_REGIONS = [
    "Alberta", "British Columbia", "Manitoba", "New Brunswick",
    "Newfoundland and Labrador", "Northwest Territories", "Nova Scotia",
    "Nunavut", "Ontario", "Prince Edward Island", "Québec",
    "Saskatchewan", "Yukon",
]

US_STATES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
    "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York",
    "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
    "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West Virginia", "Wisconsin", "Wyoming",
]

# How many cities to ask per region
CITIES_PER_CA = 10
CITIES_PER_US = 10


def build_prompt(region: str, country: str, count: int) -> str:
    """Build a prompt asking for the top N cities of a region."""
    return (
        f"Liste les {count} villes les plus peuplées de: {region} ({country}).\n"
        f"Réponds en JSON array, chaque élément: "
        f'{{ "city_name": "NomVille", "population": 123456, "rank": 1 }}\n'
        f"Trie par population décroissante. rank = 1 pour la plus grande.\n"
        f"Réponds UNIQUEMENT avec le JSON array, aucun autre texte, aucun markdown.\n"
        f"Utilise les noms de ville courants (ex: Montréal et non Montreal)."
    )


def parse_ai_response(reply: str, region: str, country: str) -> list[dict]:
    """Parse AI JSON response into city dicts."""
    # Strip markdown fences if present
    text = reply.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    text = text.strip()

    try:
        cities = json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON array in the text
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1:
            try:
                cities = json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                print(f"  ❌ Failed to parse JSON for {region} ({country})")
                print(f"     Raw: {text[:200]}")
                return []
        else:
            print(f"  ❌ No JSON array found for {region} ({country})")
            return []

    result = []
    for i, c in enumerate(cities):
        if isinstance(c, dict) and "city_name" in c:
            result.append({
                "city_name": c["city_name"],
                "region": region,
                "country": country,
                "population": c.get("population", 0),
                "rank": c.get("rank", i + 1),
            })
    return result


def fetch_region(api_key: str, model: str, region: str, country: str, count: int) -> list[dict]:
    """Fetch top cities for a single region via AI."""
    prompt = build_prompt(region, country, count)
    result = generate_city(api_key, model, "", prompt, max_tokens=800, temperature=0.2)

    if not result.get("success"):
        print(f"  ❌ API error for {region}: {result.get('error')}")
        return []

    cities = parse_ai_response(result.get("reply", ""), region, country)
    print(f"  ✅ {region} ({country}): {len(cities)} villes")
    return cities


def load_existing_json() -> dict:
    """Load existing ref_cities.json if present."""
    if JSON_PATH.exists():
        try:
            return json.loads(JSON_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_json(data: dict) -> None:
    """Save ref cities data to JSON."""
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\n💾 Saved {JSON_PATH}")


def import_to_db(data: dict) -> None:
    """Import ref cities from JSON dict into SQLite."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ref_city (
            ref_city_id INTEGER PRIMARY KEY AUTOINCREMENT,
            city_name TEXT NOT NULL,
            region TEXT NOT NULL,
            country TEXT NOT NULL,
            population INTEGER,
            rank INTEGER,
            UNIQUE(city_name, region, country)
        )
    """)

    inserted = 0
    skipped = 0
    for key, cities in data.items():
        for c in cities:
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO ref_city
                       (city_name, region, country, population, rank)
                       VALUES (?, ?, ?, ?, ?)""",
                    (c["city_name"], c["region"], c["country"],
                     c.get("population", 0), c.get("rank", 0)),
                )
                inserted += 1
            except Exception as e:
                print(f"  ⚠ Skip {c.get('city_name')}: {e}")
                skipped += 1

    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM ref_city").fetchone()[0]
    conn.close()
    print(f"\n📦 DB import: {inserted} inserted, {skipped} skipped. Total ref_city rows: {total}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ref_city table via Mammouth AI")
    parser.add_argument("--import-only", action="store_true",
                        help="Skip AI calls, just import existing JSON to DB")
    parser.add_argument("--region", type=str, default="",
                        help="Fetch a single region only")
    parser.add_argument("--country", type=str, default="",
                        help="Fetch a single country only (Canada or 'United States')")
    args = parser.parse_args()

    if args.import_only:
        data = load_existing_json()
        if not data:
            print("❌ No ref_cities.json found. Run without --import-only first.")
            return
        import_to_db(data)
        return

    settings = load_settings()
    api_key = settings.get("api_key", "")
    if not api_key:
        print("❌ No API key configured. Set it in Options first.")
        return

    model = settings.get("model", "gpt-4.1-mini")
    print(f"🤖 Using model: {model}")
    print(f"📍 CA: {CITIES_PER_CA} cities × {len(CA_REGIONS)} regions")
    print(f"📍 US: {CITIES_PER_US} cities × {len(US_STATES)} states")
    print()

    data = load_existing_json()

    # Build task list
    tasks: list[tuple[str, str, int]] = []

    if args.region:
        # Single region
        country = args.country or ("Canada" if args.region in CA_REGIONS else "United States")
        count = CITIES_PER_CA if country == "Canada" else CITIES_PER_US
        tasks.append((args.region, country, count))
    elif args.country:
        if args.country == "Canada":
            tasks = [(r, "Canada", CITIES_PER_CA) for r in CA_REGIONS]
        else:
            tasks = [(s, "United States", CITIES_PER_US) for s in US_STATES]
    else:
        # All regions
        for r in CA_REGIONS:
            key = f"Canada|{r}"
            if key not in data:
                tasks.append((r, "Canada", CITIES_PER_CA))
        for s in US_STATES:
            key = f"United States|{s}"
            if key not in data:
                tasks.append((s, "United States", CITIES_PER_US))

    if not tasks:
        print("✅ All regions already in ref_cities.json. Use --import-only to reimport.")
        import_to_db(data)
        return

    print(f"📋 {len(tasks)} regions to fetch...\n")

    for i, (region, country, count) in enumerate(tasks):
        print(f"[{i+1}/{len(tasks)}] {region} ({country})...")
        cities = fetch_region(api_key, model, region, country, count)
        if cities:
            key = f"{country}|{region}"
            data[key] = cities
            # Save after each region (resume-safe)
            save_json(data)

        # Rate limit: 2s between calls
        if i < len(tasks) - 1:
            time.sleep(2)

    print(f"\n✅ Done fetching. Total regions: {len(data)}")
    import_to_db(data)


if __name__ == "__main__":
    main()
