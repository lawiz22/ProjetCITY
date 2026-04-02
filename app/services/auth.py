from __future__ import annotations

import functools
from typing import Any

from flask import abort, flash, g, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import get_db


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    return generate_password_hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return check_password_hash(hashed, plain)


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

def create_user(
    username: str,
    email: str,
    password: str,
    role: str = "lecteur",
    display_name: str | None = None,
    is_approved: bool = False,
) -> int:
    db = get_db()
    cur = db.execute(
        """
        INSERT INTO app_user (username, email, password_hash, display_name, role, is_approved)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (username, email.lower().strip(), hash_password(password), display_name or username, role, is_approved),
    )
    db.commit()
    return cur.lastrowid


def authenticate(login: str, password: str) -> dict[str, Any] | None:
    db = get_db()
    cur = db.execute(
        "SELECT * FROM app_user WHERE (email = ? OR username = ?) AND is_active = ?",
        (login.lower().strip(), login.strip(), True),
    )
    row = cur.fetchone()
    if row is None:
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return _row_to_dict(row)


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    db = get_db()
    cur = db.execute("SELECT * FROM app_user WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    return _row_to_dict(row) if row else None


def get_all_users() -> list[dict[str, Any]]:
    db = get_db()
    cur = db.execute("SELECT * FROM app_user ORDER BY created_at DESC")
    return [_row_to_dict(r) for r in cur.fetchall()]


def update_user(user_id: int, *, role: str | None = None, is_active: bool | None = None, is_approved: bool | None = None, display_name: str | None = None) -> None:
    sets: list[str] = []
    params: list[Any] = []
    if role is not None:
        sets.append("role = ?")
        params.append(role)
    if is_active is not None:
        sets.append("is_active = ?")
        params.append(is_active)
    if is_approved is not None:
        sets.append("is_approved = ?")
        params.append(is_approved)
    if display_name is not None:
        sets.append("display_name = ?")
        params.append(display_name)
    if not sets:
        return
    sets.append("updated_at = CURRENT_TIMESTAMP")
    params.append(user_id)
    db = get_db()
    db.execute(f"UPDATE app_user SET {', '.join(sets)} WHERE user_id = ?", params)
    db.commit()


def delete_user(user_id: int) -> None:
    db = get_db()
    db.execute("DELETE FROM app_user WHERE user_id = ?", (user_id,))
    db.commit()


def admin_exists() -> bool:
    db = get_db()
    cur = db.execute("SELECT 1 FROM app_user WHERE role = ? LIMIT 1", ("admin",))
    return cur.fetchone() is not None


def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row.items()) if hasattr(row, "items") else dict(zip(row.keys(), row))


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def load_user() -> None:
    """Call from before_request to populate g.user from session."""
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
    else:
        g.user = get_user_by_id(user_id)
        if g.user and not g.user.get("is_active"):
            session.clear()
            g.user = None


def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if g.get("user") is None:
            flash("Connexion requise.", "warning")
            return redirect(url_for("web.login", next=request.path))
        return f(*args, **kwargs)
    return decorated


def role_required(*roles: str):
    def decorator(f):
        @functools.wraps(f)
        def decorated(*args, **kwargs):
            if g.get("user") is None:
                flash("Connexion requise.", "warning")
                return redirect(url_for("web.login", next=request.path))
            if g.user["role"] not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator


editor_required = role_required("admin", "editeur")
admin_required = role_required("admin")
