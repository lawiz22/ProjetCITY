from __future__ import annotations

from pathlib import Path

from flask import Flask

from .config import Config
from .db import close_db, run_migrations
from .routes import web


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
    run_migrations(app.config["DATABASE_PATH"])
    return app