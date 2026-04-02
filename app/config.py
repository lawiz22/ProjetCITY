from __future__ import annotations

import os
from pathlib import Path

from .db import build_sqlite_url, is_postgres_url

# Default SQLite database path (same value as scripts/build_city_database.py)
_DEFAULT_DB_FILE = Path(__file__).resolve().parents[1] / "data" / "city_analysis.db"


def _resolve_sqlite_path(raw_value: str | None, default_path: Path) -> Path:
    if not raw_value:
        return default_path.resolve()

    if raw_value.startswith("sqlite:///"):
        raw_path = raw_value[len("sqlite:///") :]
        if raw_path.startswith("/") and len(raw_path) > 2 and raw_path[2] == ":":
            raw_path = raw_path[1:]
        return Path(raw_path).resolve()

    return Path(raw_value).resolve()


class Config:
    ROOT_DIR = Path(__file__).resolve().parents[1]
    SECRET_KEY = os.environ.get("PROJETCITY_SECRET_KEY", "projetcity-dev")

    _DATABASE_URL_ENV = (os.environ.get("DATABASE_URL") or os.environ.get("PROJETCITY_DATABASE_URL", "")).strip()
    _DATABASE_PATH_ENV = os.environ.get("PROJETCITY_DATABASE_PATH", "").strip()

    if _DATABASE_URL_ENV:
        DATABASE_URL = _DATABASE_URL_ENV
        DATABASE_BACKEND = "postgresql" if is_postgres_url(_DATABASE_URL_ENV) else "sqlite"
        DATABASE_PATH = (
            None if DATABASE_BACKEND == "postgresql"
            else _resolve_sqlite_path(_DATABASE_URL_ENV, _DEFAULT_DB_FILE)
        )
    else:
        DATABASE_PATH = _resolve_sqlite_path(_DATABASE_PATH_ENV or None, _DEFAULT_DB_FILE)
        DATABASE_URL = build_sqlite_url(DATABASE_PATH)
        DATABASE_BACKEND = "sqlite"

    SQL_QUERY_LIMIT = int(os.environ.get("PROJETCITY_SQL_QUERY_LIMIT", "500"))
    SQL_EXPORT_LIMIT = int(os.environ.get("PROJETCITY_SQL_EXPORT_LIMIT", "5000"))
    SQL_HISTORY_PATH = Path(
        os.environ.get(
            "PROJETCITY_SQL_HISTORY_PATH",
            str(ROOT_DIR / "data" / "sql_lab_history.json"),
        )
    ).resolve()
    SQL_HISTORY_LIMIT = int(os.environ.get("PROJETCITY_SQL_HISTORY_LIMIT", "60"))
    SAVED_VIEWS_PATH = Path(
        os.environ.get(
            "PROJETCITY_SAVED_VIEWS_PATH",
            str(ROOT_DIR / "data" / "saved_views.json"),
        )
    ).resolve()
    SAVED_VIEWS_LIMIT = int(os.environ.get("PROJETCITY_SAVED_VIEWS_LIMIT", "80"))
    SQL_ENABLE_WRITE = os.environ.get("PROJETCITY_SQL_ENABLE_WRITE", "0") == "1"
    SQL_STATEMENT_LIMIT = int(os.environ.get("PROJETCITY_SQL_STATEMENT_LIMIT", "5"))

    # When True, each user must provide their own Mammouth AI API key
    # (stored in browser session instead of server DB).
    # Auto-enabled on Railway unless explicitly set.
    REQUIRE_USER_API_KEY = os.environ.get(
        "PROJETCITY_REQUIRE_USER_KEY",
        "1" if os.environ.get("RAILWAY_ENVIRONMENT") else "0",
    ) == "1"

    ADMIN_PASSWORD = os.environ.get("PROJETCITY_ADMIN_PASSWORD", "")
    ADMIN_EMAIL = os.environ.get("PROJETCITY_ADMIN_EMAIL", "lawiz2222@gmail.com")
    ADMIN_USERNAME = os.environ.get("PROJETCITY_ADMIN_USERNAME", "admin")
