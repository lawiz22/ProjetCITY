"""Shared fixtures for ProjetCITY test suite."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT_DIR / "sql" / "schema.sql"


def _init_schema(conn: sqlite3.Connection) -> None:
    """Apply full schema (tables + views) to an in-memory database."""
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema_sql)


def _seed_sample_data(conn: sqlite3.Connection) -> None:
    """Insert minimal sample data for testing."""
    # --- dim_time ---
    time_rows = [
        (1, 1950, 1950, "1950–1974", "1950–1999", 20, "Après-guerre"),
        (2, 1960, 1960, "1950–1974", "1950–1999", 20, "Après-guerre"),
        (3, 1970, 1970, "1950–1974", "1950–1999", 20, "Après-guerre"),
        (4, 1980, 1980, "1975–1999", "1950–1999", 20, "Suburbanisation"),
        (5, 1990, 1990, "1975–1999", "1950–1999", 20, "Suburbanisation"),
        (6, 2000, 2000, "2000–2024", "2000–2049", 21, "Ère contemporaine"),
        (7, 2010, 2010, "2000–2024", "2000–2049", 21, "Ère contemporaine"),
        (8, 2020, 2020, "2000–2024", "2000–2049", 21, "Ère contemporaine"),
    ]
    conn.executemany(
        "INSERT INTO dim_time (time_id, year, decade, quarter_century_label, half_century_label, century, period_label) VALUES (?,?,?,?,?,?,?)",
        time_rows,
    )

    # --- dim_city ---
    conn.execute(
        "INSERT INTO dim_city (city_id, city_name, city_slug, region, country, city_color, latitude, longitude, source_file) VALUES (?,?,?,?,?,?,?,?,?)",
        (1, "Montréal", "montreal", "Québec", "Canada", "#1e90ff", 45.5017, -73.5673, "test"),
    )
    conn.execute(
        "INSERT INTO dim_city (city_id, city_name, city_slug, region, country, city_color, latitude, longitude, source_file) VALUES (?,?,?,?,?,?,?,?,?)",
        (2, "Calgary", "calgary", "Alberta", "Canada", "#ff6347", 51.0447, -114.0719, "test"),
    )
    conn.execute(
        "INSERT INTO dim_city (city_id, city_name, city_slug, region, country, city_color, latitude, longitude, source_file) VALUES (?,?,?,?,?,?,?,?,?)",
        (3, "Boston", "boston", "Massachusetts", "United States", "#32cd32", 42.3601, -71.0589, "test"),
    )

    # --- fact_city_population ---
    pop_rows = [
        # Montréal
        (1, 1, 1950, 1_000_000, 1, None, "test"),
        (1, 2, 1960, 1_200_000, 0, None, "test"),
        (1, 3, 1970, 1_400_000, 0, None, "test"),
        (1, 4, 1980, 1_350_000, 0, None, "test"),
        (1, 5, 1990, 1_500_000, 0, None, "test"),
        (1, 6, 2000, 1_600_000, 0, None, "test"),
        (1, 7, 2010, 1_700_000, 0, None, "test"),
        (1, 8, 2020, 1_800_000, 0, None, "test"),
        # Calgary
        (2, 1, 1950, 100_000, 1, None, "test"),
        (2, 2, 1960, 200_000, 0, None, "test"),
        (2, 6, 2000, 900_000, 0, None, "test"),
        (2, 8, 2020, 1_300_000, 0, None, "test"),
        # Boston
        (3, 1, 1950, 800_000, 1, None, "test"),
        (3, 4, 1980, 560_000, 0, None, "test"),
        (3, 8, 2020, 680_000, 0, None, "test"),
    ]
    conn.executemany(
        "INSERT INTO fact_city_population (city_id, time_id, year, population, is_key_year, annotation_id, source_file) VALUES (?,?,?,?,?,?,?)",
        pop_rows,
    )
    conn.commit()


@pytest.fixture(scope="session")
def test_db_path(tmp_path_factory):
    """Create a temporary SQLite database with schema + sample data (session-scoped)."""
    db_file = tmp_path_factory.mktemp("data") / "test_city_analysis.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("PRAGMA foreign_keys = ON;")
    _init_schema(conn)
    _seed_sample_data(conn)
    conn.close()
    return db_file


@pytest.fixture()
def app(test_db_path):
    """Create a Flask app configured for testing with the temporary database."""
    import os
    os.environ["PROJETCITY_DATABASE_PATH"] = str(test_db_path)

    from app import create_app
    application = create_app()
    application.config.update({
        "TESTING": True,
        "DATABASE_PATH": str(test_db_path),
    })
    yield application


@pytest.fixture()
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture()
def db_conn(test_db_path):
    """Direct database connection for service-level tests."""
    conn = sqlite3.connect(str(test_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    yield conn
    conn.close()
