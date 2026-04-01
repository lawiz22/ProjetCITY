from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import psycopg
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency: psycopg. Install it with `pip install psycopg[binary]` "
        "before running this migration script."
    ) from exc


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE_PATH = PROJECT_ROOT / "data" / "city_analysis.db"
DEFAULT_SCHEMA_PATH = PROJECT_ROOT / "sql" / "schema_postgres.sql"


@dataclass(frozen=True)
class TableCopySpec:
    name: str
    columns: tuple[str, ...]
    pk_column: str | None = None


@dataclass(frozen=True)
class DocumentImportSpec:
    entity_type: str
    document_kind: str
    directory: Path


TABLE_COPY_ORDER: tuple[TableCopySpec, ...] = (
    TableCopySpec(
        "dim_annotation",
        (
            "annotation_id",
            "annotation_label",
            "annotation_color",
            "annotation_type",
            "photo_filename",
            "photo_source_url",
        ),
        "annotation_id",
    ),
    TableCopySpec(
        "ref_population",
        ("ref_pop_id", "country", "region", "year", "population"),
        "ref_pop_id",
    ),
    TableCopySpec(
        "ref_city",
        ("ref_city_id", "city_name", "region", "country", "population", "rank"),
        "ref_city_id",
    ),
    TableCopySpec(
        "dim_city",
        (
            "city_id",
            "city_name",
            "city_slug",
            "region",
            "country",
            "city_color",
            "latitude",
            "longitude",
            "area_km2",
            "density",
            "foundation_year",
            "source_file",
        ),
        "city_id",
    ),
    TableCopySpec(
        "dim_time",
        (
            "time_id",
            "year",
            "decade",
            "quarter_century_label",
            "half_century_label",
            "century",
            "period_label",
        ),
        "time_id",
    ),
    TableCopySpec(
        "dim_country",
        ("country_id", "country_name", "country_slug", "country_color", "source_file"),
        "country_id",
    ),
    TableCopySpec(
        "dim_region",
        ("region_id", "region_name", "region_slug", "country_name", "region_color", "source_file"),
        "region_id",
    ),
    TableCopySpec(
        "dim_city_period_detail",
        (
            "period_detail_id",
            "city_id",
            "period_order",
            "period_range_label",
            "period_title",
            "start_year",
            "end_year",
            "start_time_id",
            "end_time_id",
            "summary_text",
            "source_file",
        ),
        "period_detail_id",
    ),
    TableCopySpec(
        "dim_city_period_detail_item",
        ("period_detail_item_id", "period_detail_id", "item_order", "item_text"),
        "period_detail_item_id",
    ),
    TableCopySpec(
        "dim_region_period_detail",
        (
            "region_period_id",
            "region_id",
            "period_order",
            "period_range_label",
            "period_title",
            "start_year",
            "end_year",
            "start_time_id",
            "end_time_id",
            "summary_text",
            "source_file",
        ),
        "region_period_id",
    ),
    TableCopySpec(
        "dim_region_period_detail_item",
        ("item_id", "region_period_id", "item_order", "item_text"),
        "item_id",
    ),
    TableCopySpec(
        "fact_city_population",
        (
            "population_id",
            "city_id",
            "time_id",
            "year",
            "population",
            "is_key_year",
            "annotation_id",
            "source_file",
        ),
        "population_id",
    ),
    TableCopySpec(
        "fact_country_population",
        (
            "country_pop_id",
            "country_id",
            "time_id",
            "year",
            "population",
            "is_key_year",
            "annotation_id",
            "source_file",
        ),
        "country_pop_id",
    ),
    TableCopySpec(
        "fact_region_population",
        (
            "region_pop_id",
            "region_id",
            "time_id",
            "year",
            "population",
            "is_key_year",
            "annotation_id",
            "source_file",
        ),
        "region_pop_id",
    ),
    TableCopySpec(
        "dim_city_fiche",
        ("fiche_id", "city_id", "raw_text", "created_at"),
        "fiche_id",
    ),
    TableCopySpec(
        "dim_city_fiche_section",
        ("section_id", "fiche_id", "section_order", "section_emoji", "section_title", "content_json"),
        "section_id",
    ),
    TableCopySpec(
        "dim_city_photo",
        (
            "photo_id",
            "city_id",
            "filename",
            "caption",
            "source_url",
            "attribution",
            "is_primary",
            "exif_lat",
            "exif_lon",
            "exif_date",
            "exif_camera",
            "created_at",
        ),
        "photo_id",
    ),
    TableCopySpec(
        "dim_country_photo",
        ("photo_id", "country_id", "filename", "caption", "source_url", "attribution", "is_primary", "created_at"),
        "photo_id",
    ),
    TableCopySpec(
        "dim_region_photo",
        ("photo_id", "region_id", "filename", "caption", "source_url", "attribution", "is_primary", "created_at"),
        "photo_id",
    ),
    TableCopySpec(
        "dim_event",
        (
            "event_id",
            "event_name",
            "event_slug",
            "event_date_start",
            "event_date_end",
            "event_year",
            "event_level",
            "event_category",
            "description",
            "impact_population",
            "impact_migration",
            "source_text",
            "created_at",
        ),
        "event_id",
    ),
    TableCopySpec(
        "dim_event_location",
        ("event_location_id", "event_id", "city_id", "region", "country", "role"),
        "event_location_id",
    ),
    TableCopySpec(
        "dim_event_photo",
        (
            "event_photo_id",
            "event_id",
            "filename",
            "caption",
            "source_url",
            "attribution",
            "is_primary",
            "photo_order",
            "created_at",
        ),
        "event_photo_id",
    ),
)


DOCUMENT_IMPORTS: tuple[DocumentImportSpec, ...] = (
    DocumentImportSpec("city", "period_detail", PROJECT_ROOT / "data" / "city_details"),
    DocumentImportSpec("city", "fiche", PROJECT_ROOT / "data" / "city_fiches"),
    DocumentImportSpec("country", "period_detail", PROJECT_ROOT / "data" / "country_details"),
    DocumentImportSpec("country", "fiche", PROJECT_ROOT / "data" / "country_fiches"),
    DocumentImportSpec("region", "period_detail", PROJECT_ROOT / "data" / "region_details"),
    DocumentImportSpec("region", "fiche", PROJECT_ROOT / "data" / "region_fiches"),
)


BOOLEAN_COLUMNS: dict[str, set[str]] = {
    "fact_city_population": {"is_key_year"},
    "fact_country_population": {"is_key_year"},
    "fact_region_population": {"is_key_year"},
    "dim_city_photo": {"is_primary"},
    "dim_country_photo": {"is_primary"},
    "dim_region_photo": {"is_primary"},
    "dim_event_photo": {"is_primary"},
}


def clean_text_value(value: Any) -> tuple[Any, bool]:
    if isinstance(value, str) and "\x00" in value:
        return value.replace("\x00", ""), True
    return value, False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate ProjetCITY data from SQLite to PostgreSQL/PostGIS."
    )
    parser.add_argument("--sqlite-path", type=Path, default=DEFAULT_SQLITE_PATH)
    parser.add_argument("--schema-path", type=Path, default=DEFAULT_SCHEMA_PATH)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--pg-dsn", required=True)
    parser.add_argument("--skip-schema", action="store_true")
    parser.add_argument("--truncate-target", action="store_true")
    parser.add_argument("--skip-documents", action="store_true")
    return parser.parse_args()


def connect_sqlite(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


def connect_postgres(dsn: str):
    return psycopg.connect(dsn)


def apply_schema(pg_conn, schema_path: Path) -> None:
    schema_sql = schema_path.read_text(encoding="utf-8")
    previous_autocommit = pg_conn.autocommit
    pg_conn.autocommit = True
    try:
        with pg_conn.cursor() as cur:
            cur.execute(schema_sql)
    finally:
        pg_conn.autocommit = previous_autocommit


def sqlite_table_exists(sqlite_conn: sqlite3.Connection, table_name: str) -> bool:
    row = sqlite_conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def collect_invalid_source_rows(sqlite_conn: sqlite3.Connection) -> dict[str, set[int]]:
    invalid_rows: dict[str, set[int]] = {}
    for table_name, rowid, _parent_table, _fkid in sqlite_conn.execute("PRAGMA foreign_key_check"):
        invalid_rows.setdefault(table_name, set()).add(int(rowid))
    return invalid_rows


def fetch_sqlite_rows(
    sqlite_conn: sqlite3.Connection,
    spec: TableCopySpec,
    invalid_source_rows: dict[str, set[int]] | None = None,
) -> tuple[list[tuple[Any, ...]], int]:
    if not sqlite_table_exists(sqlite_conn, spec.name):
        return [], 0

    invalid_rowids = invalid_source_rows.get(spec.name, set()) if invalid_source_rows else set()
    sql = f"SELECT rowid AS __rowid__, {', '.join(spec.columns)} FROM {spec.name}"
    rows = sqlite_conn.execute(sql).fetchall()
    transformed: list[tuple[Any, ...]] = []
    bool_columns = BOOLEAN_COLUMNS.get(spec.name, set())
    sanitized_values = 0

    for row in rows:
        if invalid_rowids and row["__rowid__"] in invalid_rowids:
            continue
        values: list[Any] = []
        for column in spec.columns:
            value = row[column]
            if column in bool_columns and value is not None:
                values.append(bool(value))
            else:
                cleaned_value, was_sanitized = clean_text_value(value)
                if was_sanitized:
                    sanitized_values += 1
                values.append(cleaned_value)
        transformed.append(tuple(values))

    return transformed, sanitized_values


def truncate_target_tables(pg_conn) -> None:
    table_names = [spec.name for spec in TABLE_COPY_ORDER]
    table_names.extend(["raw_document", "app_setting", "sql_saved_view", "sql_query_history"])
    sql = "TRUNCATE TABLE " + ", ".join(table_names) + " RESTART IDENTITY CASCADE"
    with pg_conn.cursor() as cur:
        cur.execute(sql)
    pg_conn.commit()


def copy_table(
    sqlite_conn: sqlite3.Connection,
    pg_conn,
    spec: TableCopySpec,
    invalid_source_rows: dict[str, set[int]] | None = None,
) -> tuple[int, int]:
    rows, sanitized_values = fetch_sqlite_rows(sqlite_conn, spec, invalid_source_rows)
    if not rows:
        return 0, sanitized_values

    placeholders = ", ".join(["%s"] * len(spec.columns))
    insert_sql = (
        f"INSERT INTO {spec.name} ({', '.join(spec.columns)}) "
        f"VALUES ({placeholders})"
    )

    with pg_conn.cursor() as cur:
        cur.executemany(insert_sql, rows)

    pg_conn.commit()
    if spec.pk_column:
        reset_sequence(pg_conn, spec.name, spec.pk_column)
    return len(rows), sanitized_values


def reset_sequence(pg_conn, table_name: str, pk_column: str) -> None:
    sql = f"""
        SELECT setval(
            pg_get_serial_sequence(%s, %s),
            COALESCE((SELECT MAX({pk_column}) FROM {table_name}), 1),
            true
        )
    """
    with pg_conn.cursor() as cur:
        cur.execute(sql, (table_name, pk_column))
    pg_conn.commit()


def import_raw_documents(pg_conn, project_root: Path) -> int:
    inserted = 0
    with pg_conn.cursor() as cur:
        for spec in DOCUMENT_IMPORTS:
            directory = project_root / spec.directory.relative_to(PROJECT_ROOT)
            if not directory.exists():
                continue

            for path in sorted(directory.glob("*.txt")):
                content = path.read_text(encoding="utf-8")
                cur.execute(
                    """
                    INSERT INTO raw_document (entity_type, entity_slug, document_kind, content, source_origin)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (entity_type, entity_slug, document_kind) DO UPDATE
                    SET content = EXCLUDED.content,
                        source_origin = EXCLUDED.source_origin,
                        updated_at = NOW()
                    """,
                    (spec.entity_type, path.stem, spec.document_kind, content, "filesystem"),
                )
                inserted += 1
    pg_conn.commit()
    return inserted


def import_mammouth_settings(pg_conn, project_root: Path) -> int:
    settings_path = project_root / "data" / "mammouth_settings.json"
    if not settings_path.exists():
        return 0

    payload = json.loads(settings_path.read_text(encoding="utf-8"))
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO app_setting (setting_key, setting_value)
            VALUES (%s, %s::jsonb)
            ON CONFLICT (setting_key) DO UPDATE
            SET setting_value = EXCLUDED.setting_value,
                updated_at = NOW()
            """,
            ("mammouth_settings", json.dumps(payload, ensure_ascii=False)),
        )
    pg_conn.commit()
    return 1


def import_saved_views(pg_conn, project_root: Path) -> int:
    path = project_root / "data" / "saved_views.json"
    if not path.exists():
        return 0

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return 0

    inserted = 0
    with pg_conn.cursor() as cur:
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            cur.execute(
                """
                INSERT INTO sql_saved_view (view_id, name, description, sql_text, created_at, updated_at)
                VALUES (%s, %s, %s, %s, COALESCE(%s::timestamptz, NOW()), NOW())
                ON CONFLICT (view_id) DO UPDATE
                SET name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    sql_text = EXCLUDED.sql_text,
                    updated_at = NOW()
                """,
                (
                    entry.get("id"),
                    entry.get("name", ""),
                    entry.get("description", ""),
                    entry.get("sql", ""),
                    entry.get("created_at"),
                ),
            )
            inserted += 1
    pg_conn.commit()
    return inserted


def import_sql_history(pg_conn, project_root: Path) -> int:
    path = project_root / "data" / "sql_lab_history.json"
    if not path.exists():
        return 0

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return 0

    inserted = 0
    with pg_conn.cursor() as cur:
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            cur.execute(
                """
                INSERT INTO sql_query_history (occurred_at, action, status, sql_text, preview, raw_payload)
                VALUES (COALESCE(%s::timestamptz, NOW()), %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    entry.get("timestamp"),
                    entry.get("action", "execute"),
                    entry.get("status", "unknown"),
                    entry.get("sql", ""),
                    entry.get("preview"),
                    json.dumps(entry, ensure_ascii=False),
                ),
            )
            inserted += 1
    pg_conn.commit()
    return inserted


def backfill_city_geometry(pg_conn) -> int:
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            UPDATE dim_city
            SET geom = ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography
            WHERE latitude IS NOT NULL
              AND longitude IS NOT NULL
              AND geom IS NULL
            """
        )
        rowcount = cur.rowcount
    pg_conn.commit()
    return rowcount


def validate_counts(
    sqlite_conn: sqlite3.Connection,
    pg_conn,
    invalid_source_rows: dict[str, set[int]] | None = None,
) -> list[str]:
    mismatches: list[str] = []
    with pg_conn.cursor() as cur:
        for spec in TABLE_COPY_ORDER:
            if not sqlite_table_exists(sqlite_conn, spec.name):
                continue
            sqlite_count = sqlite_conn.execute(f"SELECT COUNT(*) FROM {spec.name}").fetchone()[0]
            skipped_count = len(invalid_source_rows.get(spec.name, set())) if invalid_source_rows else 0
            expected_postgres_count = sqlite_count - skipped_count
            cur.execute(f"SELECT COUNT(*) FROM {spec.name}")
            postgres_count = cur.fetchone()[0]
            if expected_postgres_count != postgres_count:
                mismatches.append(
                    f"{spec.name}: sqlite={sqlite_count} skipped={skipped_count} expected_postgres={expected_postgres_count} postgres={postgres_count}"
                )
    return mismatches


def run(args: argparse.Namespace) -> None:
    sqlite_conn = connect_sqlite(args.sqlite_path)
    pg_conn = connect_postgres(args.pg_dsn)
    invalid_source_rows = collect_invalid_source_rows(sqlite_conn)

    try:
        if not args.skip_schema:
            print(f"[1/5] Applying schema: {args.schema_path}")
            apply_schema(pg_conn, args.schema_path)

        if args.truncate_target:
            print("[2/5] Truncating target tables")
            truncate_target_tables(pg_conn)

        print("[3/5] Copying SQLite tables")
        total_skipped = sum(len(rowids) for rowids in invalid_source_rows.values())
        if total_skipped:
            print(f"  - skipped invalid SQLite child rows detected by foreign_key_check: {total_skipped}")
            for table_name in sorted(invalid_source_rows):
                print(f"    * {table_name}: {len(invalid_source_rows[table_name])}")
        for spec in TABLE_COPY_ORDER:
            copied, sanitized = copy_table(sqlite_conn, pg_conn, spec, invalid_source_rows)
            skipped = len(invalid_source_rows.get(spec.name, set()))
            suffix = f" ({skipped} skipped)" if skipped else ""
            if sanitized:
                suffix += f" ({sanitized} text values cleaned)" if suffix else f" ({sanitized} text values cleaned)"
            print(f"  - {spec.name}: {copied} rows{suffix}")

        print("[4/5] Importing filesystem-backed state")
        if not args.skip_documents:
            documents = import_raw_documents(pg_conn, args.project_root)
            settings = import_mammouth_settings(pg_conn, args.project_root)
            saved_views = import_saved_views(pg_conn, args.project_root)
            history = import_sql_history(pg_conn, args.project_root)
            print(f"  - raw_document: {documents}")
            print(f"  - app_setting: {settings}")
            print(f"  - sql_saved_view: {saved_views}")
            print(f"  - sql_query_history: {history}")

        geom_updates = backfill_city_geometry(pg_conn)
        print(f"  - dim_city geom backfill: {geom_updates}")

        print("[5/5] Validating row counts")
        mismatches = validate_counts(sqlite_conn, pg_conn, invalid_source_rows)
        if mismatches:
            print("Count mismatches detected:")
            for mismatch in mismatches:
                print(f"  - {mismatch}")
        else:
            if total_skipped:
                print("All copied table counts match after skipping invalid SQLite rows.")
            else:
                print("All copied table counts match.")

        print("")
        print("Migration skeleton completed.")
        print("Next recommended steps:")
        print("  1. Import region/country boundary GeoJSON into boundary_geom.")
        print("  2. Switch app/db.py to a PostgreSQL connection layer.")
        print("  3. Move image binaries from local disk to object storage.")
        print("  4. Migrate SQL Lab and Mammouth settings away from local files entirely.")
    finally:
        sqlite_conn.close()
        pg_conn.close()


def main() -> None:
    args = parse_args()
    run(args)


if __name__ == "__main__":
    main()
