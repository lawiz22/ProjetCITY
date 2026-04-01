"""Production WSGI entry point for Railway / Gunicorn."""
from __future__ import annotations

import os
import secrets

# Railway injects DATABASE_URL — map it to the env var the app expects.
_railway_db = os.environ.get("DATABASE_URL", "")
if _railway_db and not os.environ.get("PROJETCITY_DATABASE_URL"):
    os.environ["PROJETCITY_DATABASE_URL"] = _railway_db

# Enable SQL write by default in production (admin-only pages)
if not os.environ.get("PROJETCITY_SQL_ENABLE_WRITE"):
    os.environ["PROJETCITY_SQL_ENABLE_WRITE"] = "1"

# Ensure a strong secret key is set for session cookies.
# On Railway set PROJETCITY_SECRET_KEY in the dashboard; this fallback
# generates a random key (sessions won't survive redeploys).
if not os.environ.get("PROJETCITY_SECRET_KEY"):
    os.environ["PROJETCITY_SECRET_KEY"] = secrets.token_hex(32)

from app import create_app  # noqa: E402

app = create_app()
