from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.db import get_db


def load_json_setting(setting_key: str, default: dict[str, Any], *, fallback_path: Path | None = None) -> dict[str, Any]:
    row = get_db().execute(
        "SELECT setting_value FROM app_setting WHERE setting_key = ?",
        (setting_key,),
    ).fetchone()
    if row:
        payload = row["setting_value"]
        if isinstance(payload, dict):
            return {**default, **payload}
        if isinstance(payload, str):
            try:
                data = json.loads(payload)
                if isinstance(data, dict):
                    return {**default, **data}
            except json.JSONDecodeError:
                pass
    return dict(default)


def save_json_setting(setting_key: str, value: dict[str, Any], *, fallback_path: Path | None = None) -> None:
    payload = json.dumps(value, ensure_ascii=False)
    conn = get_db()
    conn.execute(
        """
        INSERT INTO app_setting (setting_key, setting_value)
        VALUES (?, CAST(? AS JSONB))
        ON CONFLICT (setting_key) DO UPDATE
        SET setting_value = EXCLUDED.setting_value,
            updated_at = NOW()
        """,
        (setting_key, payload),
    )
    conn.commit()


def load_raw_document(
    entity_type: str,
    entity_slug: str,
    document_kind: str,
    *,
    fallback_path: Path | None = None,
) -> str | None:
    row = get_db().execute(
        """
        SELECT content
        FROM raw_document
        WHERE entity_type = ? AND entity_slug = ? AND document_kind = ?
        """,
        (entity_type, entity_slug, document_kind),
    ).fetchone()
    if row and row["content"]:
        return row["content"]
    return None


def save_raw_document(
    entity_type: str,
    entity_slug: str,
    document_kind: str,
    content: str,
    *,
    fallback_path: Path | None = None,
) -> None:
    conn = get_db()
    conn.execute(
        """
        INSERT INTO raw_document (entity_type, entity_slug, document_kind, content, source_origin)
        VALUES (?, ?, ?, ?, 'application')
        ON CONFLICT (entity_type, entity_slug, document_kind) DO UPDATE
        SET content = EXCLUDED.content,
            source_origin = EXCLUDED.source_origin,
            updated_at = NOW()
        """,
        (entity_type, entity_slug, document_kind, content),
    )


def delete_raw_document(
    entity_type: str,
    entity_slug: str,
    document_kind: str,
    *,
    fallback_path: Path | None = None,
) -> None:
    conn = get_db()
    conn.execute(
        """
        DELETE FROM raw_document
        WHERE entity_type = ? AND entity_slug = ? AND document_kind = ?
        """,
        (entity_type, entity_slug, document_kind),
    )
