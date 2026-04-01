from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - optional until PostgreSQL is enabled
    psycopg = None
    dict_row = None

try:
    from flask import current_app, has_app_context
except ImportError:  # pragma: no cover - scripts can run outside Flask
    current_app = None

    def has_app_context() -> bool:
        return False


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "data" / "city_analysis.db"
_POSTGRES_PREFIXES = ("postgres://", "postgresql://")


def _is_postgres_url(value: str | None) -> bool:
    if not value:
        return False
    return value.startswith(_POSTGRES_PREFIXES)


def resolve_database_target() -> tuple[str, str | Path]:
    if has_app_context():
        backend = current_app.config.get("DATABASE_BACKEND", "sqlite")
        if backend == "postgresql":
            return "postgresql", current_app.config["DATABASE_URL"]
        database_path = current_app.config.get("DATABASE_PATH")
        if database_path:
            return "sqlite", Path(database_path)

    database_url = os.getenv("PROJETCITY_DATABASE_URL") or os.getenv("DATABASE_URL")
    if _is_postgres_url(database_url):
        return "postgresql", database_url

    database_path = os.getenv("PROJETCITY_DATABASE_PATH") or os.getenv("DATABASE_PATH")
    return "sqlite", Path(database_path) if database_path else DEFAULT_SQLITE_PATH


def connect_for_export() -> Any:
    backend, target = resolve_database_target()
    if backend == "postgresql":
        if psycopg is None or dict_row is None:
            raise RuntimeError(
                "PostgreSQL export requires psycopg. Install `psycopg[binary]` first."
            )
        return psycopg.connect(str(target), row_factory=dict_row)

    connection = sqlite3.connect(str(target))
    connection.row_factory = sqlite3.Row
    return connection


def case_insensitive_order(*columns: str) -> str:
    return ", ".join(f"LOWER({column}), {column}" for column in columns)
