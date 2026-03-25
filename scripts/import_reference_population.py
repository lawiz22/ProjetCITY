"""Import population_reference.py data into ref_population table."""
from __future__ import annotations
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.population_reference import (
    CANADA_TOTAL, CANADA_PROVINCES,
    USA_TOTAL, USA_STATES,
)

DB_PATH = ROOT / "data" / "city_analysis.db"


def import_reference_data() -> None:
    conn = sqlite3.connect(str(DB_PATH))

    # Create table if not exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ref_population (
            ref_pop_id INTEGER PRIMARY KEY AUTOINCREMENT,
            country TEXT NOT NULL,
            region TEXT,
            year INTEGER NOT NULL,
            population INTEGER NOT NULL,
            UNIQUE(country, region, year)
        )
    """)

    # Clear existing data
    conn.execute("DELETE FROM ref_population")

    rows: list[tuple[str, str | None, int, int]] = []

    # Canada total
    for year, pop in CANADA_TOTAL.items():
        rows.append(("Canada", None, year, pop))

    # Canada provinces
    for province, data in CANADA_PROVINCES.items():
        for year, pop in data.items():
            rows.append(("Canada", province, year, pop))

    # USA total
    for year, pop in USA_TOTAL.items():
        rows.append(("United States", None, year, pop))

    # USA states
    for state, data in USA_STATES.items():
        for year, pop in data.items():
            rows.append(("United States", state, year, pop))

    conn.executemany(
        "INSERT INTO ref_population (country, region, year, population) VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM ref_population").fetchone()[0]
    countries = conn.execute("SELECT COUNT(DISTINCT country) FROM ref_population").fetchone()[0]
    regions = conn.execute("SELECT COUNT(DISTINCT region) FROM ref_population WHERE region IS NOT NULL").fetchone()[0]
    print(f"Importé {total} entrées — {countries} pays, {regions} régions/états")

    conn.close()


if __name__ == "__main__":
    import_reference_data()
