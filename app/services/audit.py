from __future__ import annotations

import json
from typing import Any

from flask import g, request

from ..db import get_db


def log_action(
    action: str,
    entity_type: str,
    entity_id: str | int | None = None,
    entity_label: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Insert an audit log entry for the current request."""
    try:
        db = get_db()
        user = getattr(g, "user", None)
        user_id = user["user_id"] if user else None
        ip = request.remote_addr if request else None
        details_val = json.dumps(details, ensure_ascii=False) if details else None
        db.execute(
            """
            INSERT INTO audit_log (user_id, action, entity_type, entity_id, entity_label, details, ip_address)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, action, entity_type, str(entity_id) if entity_id is not None else None, entity_label, details_val, ip),
        )
        db.commit()
    except Exception:
        pass


def get_audit_logs(
    limit: int = 100,
    offset: int = 0,
    user_id: int | None = None,
    action: str | None = None,
    entity_type: str | None = None,
) -> list[dict[str, Any]]:
    db = get_db()
    clauses: list[str] = []
    params: list[Any] = []
    if user_id is not None:
        clauses.append("l.user_id = ?")
        params.append(user_id)
    if action:
        clauses.append("l.action = ?")
        params.append(action)
    if entity_type:
        clauses.append("l.entity_type = ?")
        params.append(entity_type)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    params.extend([limit, offset])
    cur = db.execute(
        f"""
        SELECT l.*, u.username, u.display_name
        FROM audit_log l
        LEFT JOIN app_user u ON u.user_id = l.user_id
        {where}
        ORDER BY l.created_at DESC
        LIMIT ? OFFSET ?
        """,
        params,
    )
    return [dict(r.items()) if hasattr(r, "items") else dict(zip(r.keys(), r)) for r in cur.fetchall()]


def count_audit_logs(
    user_id: int | None = None,
    action: str | None = None,
    entity_type: str | None = None,
) -> int:
    db = get_db()
    clauses: list[str] = []
    params: list[Any] = []
    if user_id is not None:
        clauses.append("user_id = ?")
        params.append(user_id)
    if action:
        clauses.append("action = ?")
        params.append(action)
    if entity_type:
        clauses.append("entity_type = ?")
        params.append(entity_type)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    cur = db.execute(f"SELECT COUNT(*) FROM audit_log{where}", params)
    row = cur.fetchone()
    return row[0] if row else 0
