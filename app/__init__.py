from __future__ import annotations

import unicodedata
from pathlib import Path

from flask import Flask

from .config import Config
from .db import close_db, run_migrations
from .routes import web


def _slugify(name: str) -> str:
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    return name.lower().replace(" ", "-").replace(".", "")


def _flag_url(country: str, region: str | None = None) -> str:
    if region:
        return f"/static/images/flags/regions/{_slugify(country)}/{_slugify(region)}.png"
    return f"/static/images/flags/countries/{_slugify(country)}.png"


def create_app() -> Flask:
    root_dir = Path(__file__).resolve().parents[1]
    app = Flask(
        __name__,
        template_folder=str(root_dir / "templates"),
        static_folder=str(root_dir / "static"),
    )
    app.config.from_object(Config())
    app.register_blueprint(web)
    app.teardown_appcontext(close_db)
    run_migrations(app.config)
    app.jinja_env.globals["flag_url"] = _flag_url
    return app
