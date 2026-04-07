"""
Migration: Add population source validation columns.

Adds to dim_city / dim_region / dim_country:
  - population_validated  BOOLEAN DEFAULT FALSE
  - population_validated_at TIMESTAMPTZ

Adds to fact_city_population / fact_region_population / fact_country_population:
  - source_url   TEXT
  - source_label TEXT
  - validated_at TIMESTAMPTZ

Run:
  python -m scripts.migrate_add_population_sources
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg

# Load .env if present (same as Flask app)
_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("PROJETCITY_DATABASE_URL", "")

STMTS = [
    # --- dim tables: aggregate validation flag ---
    "ALTER TABLE dim_city    ADD COLUMN IF NOT EXISTS population_validated    BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE dim_city    ADD COLUMN IF NOT EXISTS population_validated_at TIMESTAMPTZ",
    "ALTER TABLE dim_region  ADD COLUMN IF NOT EXISTS population_validated    BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE dim_region  ADD COLUMN IF NOT EXISTS population_validated_at TIMESTAMPTZ",
    "ALTER TABLE dim_country ADD COLUMN IF NOT EXISTS population_validated    BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE dim_country ADD COLUMN IF NOT EXISTS population_validated_at TIMESTAMPTZ",
    # --- fact tables: per-year source ---
    "ALTER TABLE fact_city_population    ADD COLUMN IF NOT EXISTS source_url    TEXT",
    "ALTER TABLE fact_city_population    ADD COLUMN IF NOT EXISTS source_label  TEXT",
    "ALTER TABLE fact_city_population    ADD COLUMN IF NOT EXISTS validated_at  TIMESTAMPTZ",
    "ALTER TABLE fact_region_population  ADD COLUMN IF NOT EXISTS source_url    TEXT",
    "ALTER TABLE fact_region_population  ADD COLUMN IF NOT EXISTS source_label  TEXT",
    "ALTER TABLE fact_region_population  ADD COLUMN IF NOT EXISTS validated_at  TIMESTAMPTZ",
    "ALTER TABLE fact_country_population ADD COLUMN IF NOT EXISTS source_url    TEXT",
    "ALTER TABLE fact_country_population ADD COLUMN IF NOT EXISTS source_label  TEXT",
    "ALTER TABLE fact_country_population ADD COLUMN IF NOT EXISTS validated_at  TIMESTAMPTZ",
]


def main() -> None:
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set.", file=sys.stderr)
        sys.exit(1)

    conn = psycopg.connect(DATABASE_URL, autocommit=False)
    cur = conn.cursor()
    try:
        for stmt in STMTS:
            print(f"  → {stmt[:80]}...")
            cur.execute(stmt)
        conn.commit()
        print("✅ Migration completed successfully.")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
