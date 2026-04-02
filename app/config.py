from __future__ import annotations

import os
from pathlib import Path


class Config:
    ROOT_DIR = Path(__file__).resolve().parents[1]
    SECRET_KEY = os.environ.get("PROJETCITY_SECRET_KEY", "projetcity-dev")

    DATABASE_URL = (os.environ.get("DATABASE_URL") or os.environ.get("PROJETCITY_DATABASE_URL", "")).strip()
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL ou PROJETCITY_DATABASE_URL doit être défini "
            "(ex: postgresql://user:pass@host:5432/db)"
        )

    SQL_QUERY_LIMIT = int(os.environ.get("PROJETCITY_SQL_QUERY_LIMIT", "500"))
    SQL_EXPORT_LIMIT = int(os.environ.get("PROJETCITY_SQL_EXPORT_LIMIT", "5000"))
    SQL_HISTORY_LIMIT = int(os.environ.get("PROJETCITY_SQL_HISTORY_LIMIT", "60"))
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
