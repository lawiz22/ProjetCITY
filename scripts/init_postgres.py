"""Initialise the PostgreSQL schema on Railway (or any PG target).

This script is idempotent — safe to run on every deploy.
It reads sql/schema_postgres.sql and applies it, gracefully handling
missing extensions (e.g. PostGIS on Railway's standard Postgres).

Usage:
    python scripts/init_postgres.py          # uses env vars
    python scripts/init_postgres.py --url postgresql://user:pass@host/db
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

try:
    import psycopg
except ImportError:
    sys.exit("psycopg is required. Install with: pip install 'psycopg[binary]'")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_FILE = PROJECT_ROOT / "sql" / "schema_postgres.sql"

# Extensions that may not be available on managed PostgreSQL (Railway, etc.)
_OPTIONAL_EXTENSIONS = {"postgis", "postgis_topology", "postgis_raster"}

# Column types that need PostGIS — we rewrite them to TEXT when PostGIS is absent.
_POSTGIS_TYPE_MAP = {
    "GEOGRAPHY(POINT, 4326)": "TEXT",
    "GEOMETRY(MULTIPOLYGON, 4326)": "TEXT",
    "GEOMETRY(POLYGON, 4326)": "TEXT",
    "GEOMETRY(POINT, 4326)": "TEXT",
}

# Index types that require PostGIS
_POSTGIS_INDEX_MARKERS = ("USING GIST", "USING GIN (")


def _resolve_database_url() -> str:
    """Get PG connection URL from env vars (Railway's DATABASE_URL wins)."""
    # On Railway, DATABASE_URL is auto-injected and must take priority
    # over any stale PROJETCITY_DATABASE_URL that might point to localhost.
    for key in ("DATABASE_URL", "PROJETCITY_DATABASE_URL"):
        url = os.environ.get(key, "").strip()
        if url and url.startswith(("postgres://", "postgresql://")):
            return url
    sys.exit(
        "No PostgreSQL URL found. Set DATABASE_URL or PROJETCITY_DATABASE_URL."
    )


def _check_postgis(conn: psycopg.Connection) -> bool:
    """Return True if PostGIS is available."""
    try:
        conn.execute("SELECT PostGIS_Version()")
        return True
    except psycopg.errors.UndefinedFunction:
        conn.rollback()
        return False
    except Exception:
        conn.rollback()
        return False


def _adapt_schema(sql: str, has_postgis: bool) -> str:
    """Adapt the schema SQL for environments without PostGIS."""
    if has_postgis:
        return sql

    lines = sql.splitlines()
    adapted: list[str] = []

    for line in lines:
        stripped = line.strip().upper()

        # Skip PostGIS extension creation
        if "CREATE EXTENSION" in stripped:
            for ext in _OPTIONAL_EXTENSIONS:
                if ext.upper() in stripped:
                    adapted.append(f"-- [SKIPPED: PostGIS not available] {line.strip()}")
                    break
            else:
                adapted.append(line)
            continue

        # Skip PostGIS-dependent indexes (GIST on geom columns)
        if stripped.startswith("CREATE INDEX") and any(
            m in stripped for m in _POSTGIS_INDEX_MARKERS
        ):
            adapted.append(f"-- [SKIPPED: PostGIS not available] {line.strip()}")
            continue

        # Rewrite PostGIS column types to TEXT
        modified = line
        for pg_type, replacement in _POSTGIS_TYPE_MAP.items():
            if pg_type in modified.upper():
                # Case-insensitive replace
                pattern = re.compile(re.escape(pg_type), re.IGNORECASE)
                modified = pattern.sub(replacement, modified)
        adapted.append(modified)

    return "\n".join(adapted)


def main() -> None:
    import argparse
    import time
    from urllib.parse import urlparse

    parser = argparse.ArgumentParser(description="Init PostgreSQL schema for ProjetCITY")
    parser.add_argument("--url", help="PostgreSQL connection URL (overrides env vars)")
    args = parser.parse_args()

    db_url = args.url or _resolve_database_url()

    # Log host (without credentials) for debugging
    try:
        parsed = urlparse(db_url)
        print(f"[init_postgres] Target: {parsed.hostname}:{parsed.port or 5432}/{parsed.path.lstrip('/')}")
    except Exception:
        pass

    # Retry connection — Railway PG may not be ready at container start
    max_retries = 10
    retry_delay = 2  # seconds
    conn = None
    for attempt in range(1, max_retries + 1):
        print(f"[init_postgres] Connecting to PostgreSQL… (attempt {attempt}/{max_retries})")
        try:
            conn = psycopg.connect(db_url, autocommit=False)
            break
        except psycopg.OperationalError as exc:
            if attempt == max_retries:
                print(f"[init_postgres] FATAL: could not connect after {max_retries} attempts.")
                raise
            print(f"[init_postgres] Connection failed ({exc}), retrying in {retry_delay}s…")
            time.sleep(retry_delay)

    # Check PostGIS availability
    has_postgis = _check_postgis(conn)
    if has_postgis:
        print("[init_postgres] PostGIS detected — full spatial support enabled.")
    else:
        print("[init_postgres] PostGIS NOT available — spatial columns mapped to TEXT.")

    # Read and adapt schema
    raw_sql = SCHEMA_FILE.read_text(encoding="utf-8")
    adapted_sql = _adapt_schema(raw_sql, has_postgis)

    # Some extensions that ARE available on Railway's Postgres
    safe_extensions = ("unaccent", "pg_trgm", "citext")
    for ext in safe_extensions:
        try:
            conn.execute(f"CREATE EXTENSION IF NOT EXISTS {ext}")
            conn.commit()
        except Exception:
            conn.rollback()
            print(f"[init_postgres] Extension '{ext}' not available — skipped.")

    # Execute the schema (split by semicolons at statement boundaries)
    # We use a simple approach: execute the full script.
    # But we skip the BEGIN/COMMIT if present since we manage the transaction.
    adapted_sql = adapted_sql.replace("BEGIN;", "-- BEGIN managed externally")
    adapted_sql = adapted_sql.replace("COMMIT;", "-- COMMIT managed externally")

    # Split into statements and execute each one
    statements = _split_statements(adapted_sql)
    ok_count = 0
    skip_count = 0

    for stmt in statements:
        clean = stmt.strip()
        if not clean or clean.startswith("--"):
            if clean.startswith("-- [SKIPPED"):
                skip_count += 1
            continue
        try:
            conn.execute(clean)
            conn.commit()
            ok_count += 1
        except psycopg.errors.DuplicateTable:
            conn.rollback()
            ok_count += 1  # table already exists — fine
        except psycopg.errors.DuplicateObject:
            conn.rollback()
            ok_count += 1  # index/constraint already exists — fine
        except Exception as exc:
            conn.rollback()
            # Log but don't crash — some statements are best-effort
            short = clean[:120].replace("\n", " ")
            print(f"[init_postgres] WARN: {exc.__class__.__name__}: {short}…")

    conn.close()
    print(
        f"[init_postgres] Done — {ok_count} statement(s) applied, "
        f"{skip_count} skipped (PostGIS)."
    )


def _split_statements(sql: str) -> list[str]:
    """Split a SQL script into individual statements.

    Handles multi-line strings, dollar-quoted blocks (e.g. $$...$$), and
    regular semicolon splitting.
    """
    statements: list[str] = []
    current: list[str] = []
    in_dollar_quote = False
    dollar_tag = ""

    for line in sql.splitlines():
        stripped = line.strip()

        # Track dollar-quoting ($$ or $tag$)
        if not in_dollar_quote:
            match = re.search(r'\$([a-zA-Z_]*)?\$', stripped)
            if match:
                in_dollar_quote = True
                dollar_tag = match.group(0)
                current.append(line)
                # Check if closing tag is on the same line (after the opening one)
                rest = stripped[stripped.index(dollar_tag) + len(dollar_tag):]
                if dollar_tag in rest:
                    in_dollar_quote = False
                continue
        else:
            current.append(line)
            if dollar_tag in stripped:
                in_dollar_quote = False
            continue

        # Regular processing
        if stripped.endswith(";") and not in_dollar_quote:
            current.append(line)
            statements.append("\n".join(current))
            current = []
        else:
            current.append(line)

    if current:
        joined = "\n".join(current).strip()
        if joined:
            statements.append(joined)

    return statements


if __name__ == "__main__":
    main()
