from __future__ import annotations

import os
from pathlib import Path

from scripts.build_city_database import DATABASE_FILE


class Config:
    ROOT_DIR = Path(__file__).resolve().parents[1]
    SECRET_KEY = os.environ.get("PROJETCITY_SECRET_KEY", "projetcity-dev")
    DATABASE_PATH = Path(os.environ.get("PROJETCITY_DATABASE_PATH", str(DATABASE_FILE))).resolve()
    SQL_QUERY_LIMIT = int(os.environ.get("PROJETCITY_SQL_QUERY_LIMIT", "500"))
    SQL_EXPORT_LIMIT = int(os.environ.get("PROJETCITY_SQL_EXPORT_LIMIT", "5000"))
    SQL_HISTORY_PATH = Path(os.environ.get("PROJETCITY_SQL_HISTORY_PATH", str(ROOT_DIR / "data" / "sql_lab_history.json"))).resolve()
    SQL_HISTORY_LIMIT = int(os.environ.get("PROJETCITY_SQL_HISTORY_LIMIT", "60"))
    SAVED_VIEWS_PATH = Path(os.environ.get("PROJETCITY_SAVED_VIEWS_PATH", str(ROOT_DIR / "data" / "saved_views.json"))).resolve()
    SAVED_VIEWS_LIMIT = int(os.environ.get("PROJETCITY_SAVED_VIEWS_LIMIT", "80"))
    SQL_ENABLE_WRITE = os.environ.get("PROJETCITY_SQL_ENABLE_WRITE", "0") == "1"
    SQL_STATEMENT_LIMIT = int(os.environ.get("PROJETCITY_SQL_STATEMENT_LIMIT", "5"))