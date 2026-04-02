"""Shared fixtures for ProjetCITY test suite (PostgreSQL via Docker)."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import psycopg
import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT_DIR / "sql" / "schema_postgres.sql"

# Connection to the *admin* database for creating/dropping the test DB.
_ADMIN_DSN = os.environ.get(
    "PROJETCITY_TEST_ADMIN_DSN",
    "postgresql://projetcity:projetcity_dev@localhost:5432/projetcity",
)
_TEST_DB = "projetcity_test"
_TEST_DSN = _ADMIN_DSN.rsplit("/", 1)[0] + f"/{_TEST_DB}"


def _create_test_database() -> None:
    conn = psycopg.connect(_ADMIN_DSN, autocommit=True)
    try:
        conn.execute(f"DROP DATABASE IF EXISTS {_TEST_DB}")
        conn.execute(f"CREATE DATABASE {_TEST_DB}")
    finally:
        conn.close()


def _drop_test_database() -> None:
    conn = psycopg.connect(_ADMIN_DSN, autocommit=True)
    try:
        conn.execute(f"DROP DATABASE IF EXISTS {_TEST_DB}")
    finally:
        conn.close()


def _init_schema() -> None:
    """Apply the full PG schema via psql inside Docker (handles multi-statement SQL)."""
    schema_bytes = SCHEMA_PATH.read_bytes()
    result = subprocess.run(
        [
            "docker", "exec", "-i", "projetcity-postgres",
            "psql", "-U", "projetcity", "-d", _TEST_DB,
        ],
        input=schema_bytes,
        capture_output=True,
    )
    stderr = result.stderr.decode("utf-8", errors="replace")
    if "ERROR:" in stderr:
        raise RuntimeError(f"Schema loading failed:\n{stderr}")


def _seed_sample_data(conn: psycopg.Connection) -> None:
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
    cur = conn.cursor()
    cur.executemany(
        "INSERT INTO dim_time (time_id, year, decade, quarter_century_label, half_century_label, century, period_label) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
        time_rows,
    )

    # --- dim_city ---
    city_rows = [
        (1, "Montréal", "montreal", "Québec", "Canada", "#1e90ff", 45.5017, -73.5673, "test"),
        (2, "Calgary", "calgary", "Alberta", "Canada", "#ff6347", 51.0447, -114.0719, "test"),
        (3, "Boston", "boston", "Massachusetts", "United States", "#32cd32", 42.3601, -71.0589, "test"),
    ]
    cur.executemany(
        "INSERT INTO dim_city (city_id, city_name, city_slug, region, country, city_color, latitude, longitude, source_file) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
        city_rows,
    )

    # --- fact_city_population ---
    pop_rows = [
        # Montréal
        (1, 1, 1950, 1_000_000, True, None, "test"),
        (1, 2, 1960, 1_200_000, False, None, "test"),
        (1, 3, 1970, 1_400_000, False, None, "test"),
        (1, 4, 1980, 1_350_000, False, None, "test"),
        (1, 5, 1990, 1_500_000, False, None, "test"),
        (1, 6, 2000, 1_600_000, False, None, "test"),
        (1, 7, 2010, 1_700_000, False, None, "test"),
        (1, 8, 2020, 1_800_000, False, None, "test"),
        # Calgary
        (2, 1, 1950, 100_000, True, None, "test"),
        (2, 2, 1960, 200_000, False, None, "test"),
        (2, 6, 2000, 900_000, False, None, "test"),
        (2, 8, 2020, 1_300_000, False, None, "test"),
        # Boston
        (3, 1, 1950, 800_000, True, None, "test"),
        (3, 4, 1980, 560_000, False, None, "test"),
        (3, 8, 2020, 680_000, False, None, "test"),
    ]
    cur.executemany(
        "INSERT INTO fact_city_population (city_id, time_id, year, population, is_key_year, annotation_id, source_file) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
        pop_rows,
    )
    conn.commit()


@pytest.fixture(scope="session", autouse=True)
def _pg_test_database():
    """Create a temporary PostgreSQL test database for the session."""
    _create_test_database()
    _init_schema()
    conn = psycopg.connect(_TEST_DSN)
    try:
        _seed_sample_data(conn)
    finally:
        conn.close()
    yield
    _drop_test_database()


@pytest.fixture()
def app(_pg_test_database):
    """Create a Flask app configured for testing with the test PG database."""
    os.environ["PROJETCITY_DATABASE_URL"] = _TEST_DSN

    from app import create_app
    application = create_app()
    application.config.update({
        "TESTING": True,
        "DATABASE_URL": _TEST_DSN,
    })
    yield application


@pytest.fixture()
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture()
def db_conn(_pg_test_database):
    """Direct PostgreSQL connection for service-level tests."""
    conn = psycopg.connect(_TEST_DSN, row_factory=psycopg.rows.dict_row)
    yield conn
    conn.close()
