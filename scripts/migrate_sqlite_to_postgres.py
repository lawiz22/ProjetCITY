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
)


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
