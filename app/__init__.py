from __future__ import annotations

import unicodedata
from datetime import timedelta
from pathlib import Path

from flask import Flask

from .config import Config
from .db import close_db, run_migrations
from .routes import web
from .services.auth import load_user


def _slugify(name: str) -> str:
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    return name.lower().replace(" ", "-").replace(".", "")


def _flag_url(country: str, region: str | None = None) -> str:
    if region:
        return f"/static/images/flags/regions/{_slugify(country)}/{_slugify(region)}.png"
    return f"/static/images/flags/countries/{_slugify(country)}.png"


def _thumb_url(photo_path: str | None) -> str:
    """Convert a photo path to its thumbnail equivalent with fallback.

    ``images/cities/slug/abc123.jpg`` → ``images/cities/slug/thumb_abc123.jpg``
    If the thumbnail file doesn't exist on disk, returns the original path.
    """
    if not photo_path:
        return photo_path or ""
    p = Path(photo_path)
    thumb_name = f"thumb_{p.stem}.jpg"
    thumb_rel = str(p.parent / thumb_name).replace("\\", "/")
    static_root = Path(__file__).resolve().parents[1] / "static"
    if (static_root / thumb_rel).exists():
        return thumb_rel
    return photo_path


def create_app() -> Flask:
    root_dir = Path(__file__).resolve().parents[1]
    app = Flask(
        __name__,
        template_folder=str(root_dir / "templates"),
        static_folder=str(root_dir / "static"),
    )
    app.config.from_object(Config())
    app.permanent_session_lifetime = timedelta(days=31)
    app.register_blueprint(web)
    app.teardown_appcontext(close_db)
    run_migrations(app.config)
    _ensure_admin_user(app)
    app.jinja_env.globals["flag_url"] = _flag_url
    app.jinja_env.globals["require_user_key"] = app.config.get("REQUIRE_USER_API_KEY", False)
    app.jinja_env.filters["thumb_url"] = _thumb_url

    @app.before_request
    def _before_request() -> None:
        load_user()

    @app.context_processor
    def _inject_user() -> dict:
        from flask import g
        return {"current_user": getattr(g, "user", None)}

    return app


def _ensure_admin_user(app: Flask) -> None:
    """Create the initial admin account if no admin exists yet."""
    password = app.config.get("ADMIN_PASSWORD", "")
    if not password:
        return
    with app.app_context():
        from .db import get_db
        from .services.auth import admin_exists, create_user
        try:
            if admin_exists():
                return
            create_user(
                username=app.config.get("ADMIN_USERNAME", "admin"),
                email=app.config.get("ADMIN_EMAIL", "lawiz2222@gmail.com"),
                password=password,
                role="admin",
                display_name="Admin",
                is_approved=True,
            )
        except Exception:
            pass
