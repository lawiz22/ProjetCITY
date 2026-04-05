from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from typing import Any

import psycopg
from flask import current_app, g

DatabaseError = psycopg.Error

_AUTO_RETURNING_PK = {
    "dim_annotation": "annotation_id",
}


class DbRow:
    """Compatibility row object supporting row['col'], row[0] and dict(row)."""

    def __init__(self, columns: Sequence[str], values: Sequence[Any]) -> None:
        self._columns = tuple(columns)
        self._values = tuple(values)
        self._index = {name: idx for idx, name in enumerate(self._columns)}

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return self._values[key]
        return self._values[self._index[key]]

    def __iter__(self) -> Iterator[Any]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._columns)

    def keys(self):
        return self._columns

    def values(self):
        return self._values

    def items(self):
        return tuple((column, self._values[idx]) for idx, column in enumerate(self._columns))

    def __repr__(self) -> str:
        payload = ", ".join(f"{column}={self._values[idx]!r}" for idx, column in enumerate(self._columns))
        return f"DbRow({payload})"


class PostgresCursorWrapper:
    def __init__(
        self,
        cursor: Any,
        *,
        prefetched_rows: Sequence[Sequence[Any]] | None = None,
        lastrowid: Any = None,
    ) -> None:
        self._cursor = cursor
        self._prefetched_rows = list(prefetched_rows or [])
        self.lastrowid = lastrowid
        self._columns = tuple(column.name for column in (cursor.description or ()))

    @property
    def description(self):
        if not self._columns:
            return None
        return [(column, None, None, None, None, None, None) for column in self._columns]

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    def _wrap_row(self, row: Sequence[Any] | None) -> DbRow | None:
        if row is None:
            self.close()
            return None
        return DbRow(self._columns, row)

    def fetchone(self) -> DbRow | None:
        if self._prefetched_rows:
            return self._wrap_row(self._prefetched_rows.pop(0))
        return self._wrap_row(self._cursor.fetchone())

    def fetchmany(self, size: int | None = None) -> list[DbRow]:
        remaining = size if size is not None else 1
        rows: list[Sequence[Any]] = []

        if remaining > 0 and self._prefetched_rows:
            rows.extend(self._prefetched_rows[:remaining])
            self._prefetched_rows = self._prefetched_rows[remaining:]
            remaining -= len(rows)

        if remaining > 0:
            rows.extend(self._cursor.fetchmany(remaining))

        if not rows:
            self.close()
            return []

        return [DbRow(self._columns, row) for row in rows]

    def fetchall(self) -> list[DbRow]:
        rows = list(self._prefetched_rows)
        self._prefetched_rows = []
        rows.extend(self._cursor.fetchall())
        self.close()
        return [DbRow(self._columns, row) for row in rows]

    def __iter__(self) -> Iterator[DbRow]:
        while True:
            row = self.fetchone()
            if row is None:
                break
            yield row

    def close(self) -> None:
        if self._cursor is not None and not self._cursor.closed:
            self._cursor.close()

    def __del__(self) -> None:  # pragma: no cover - best effort cleanup
        try:
            self.close()
        except Exception:
            pass


class PostgresConnectionWrapper:
    def __init__(self, dsn: str) -> None:
        if psycopg is None:
            raise RuntimeError(
                "PostgreSQL support requires psycopg. Install `psycopg[binary]` first."
            )
        self._connection = psycopg.connect(dsn)

    def _translate_placeholders(self, sql: str) -> str:
        result: list[str] = []
        in_single = False
        in_double = False
        index = 0

        while index < len(sql):
            char = sql[index]

            if char == "'" and not in_double:
                if in_single and index + 1 < len(sql) and sql[index + 1] == "'":
                    result.append("''")
                    index += 2
                    continue
                in_single = not in_single
                result.append(char)
            elif char == '"' and not in_single:
                in_double = not in_double
                result.append(char)
            elif char == "?" and not in_single and not in_double:
                result.append("%s")
            else:
                result.append(char)
            index += 1

        return "".join(result)

    def _inject_returning_for_lastrowid(self, sql: str) -> tuple[str, str | None]:
        normalized = sql.strip().rstrip(";")
        if re.search(r"\breturning\b", normalized, flags=re.IGNORECASE):
            return normalized, None

        match = re.match(r"(?is)^insert\s+into\s+([a-zA-Z_][\w]*)\b", normalized)
        if not match:
            return normalized, None

        table_name = match.group(1)
        pk_column = _AUTO_RETURNING_PK.get(table_name)
        if pk_column is None:
            return normalized, None

        return f"{normalized} RETURNING {pk_column}", pk_column

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> PostgresCursorWrapper:
        translated_sql = self._translate_placeholders(sql)
        final_sql, auto_returning_pk = self._inject_returning_for_lastrowid(translated_sql)
        cursor = self._connection.cursor()
        cursor.execute(final_sql, params)

        prefetched_rows: list[Sequence[Any]] = []
        lastrowid = None
        if auto_returning_pk is not None:
            first_row = cursor.fetchone()
            if first_row is not None:
                prefetched_rows.append(first_row)
                lastrowid = first_row[0]

        return PostgresCursorWrapper(
            cursor,
            prefetched_rows=prefetched_rows,
            lastrowid=lastrowid,
        )

    def executemany(self, sql: str, seq_of_params: Sequence[Sequence[Any]]) -> Any:
        translated_sql = self._translate_placeholders(sql)
        cursor = self._connection.cursor()
        cursor.executemany(translated_sql, seq_of_params)
        return cursor

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()


def _connect_postgres(database_url: str) -> PostgresConnectionWrapper:
    return PostgresConnectionWrapper(database_url)


def get_db() -> PostgresConnectionWrapper:
    if "db" not in g:
        g.db = _connect_postgres(current_app.config["DATABASE_URL"])
    return g.db


def close_db(_error: Exception | None = None) -> None:
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def run_migrations(config: Mapping[str, Any]) -> None:
    """Apply lightweight PostgreSQL migrations (add missing columns/tables)."""
    db_url = config.get("DATABASE_URL")
    if not db_url:
        return
    conn = psycopg.connect(db_url)
    try:
        cur = conn.cursor()

        # --- app_user + audit_log tables ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS app_user (
                user_id BIGSERIAL PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                display_name TEXT,
                role TEXT NOT NULL DEFAULT 'lecteur',
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                is_approved BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                log_id BIGSERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES app_user(user_id) ON DELETE SET NULL,
                action TEXT NOT NULL,
                entity_type TEXT,
                entity_id TEXT,
                entity_label TEXT,
                details TEXT,
                ip_address TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # --- person tables ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dim_person (
                person_id BIGSERIAL PRIMARY KEY,
                person_name TEXT NOT NULL,
                person_slug TEXT NOT NULL UNIQUE,
                birth_date TEXT,
                death_date TEXT,
                birth_year INTEGER,
                death_year INTEGER,
                birth_city TEXT,
                birth_country TEXT,
                death_city TEXT,
                death_country TEXT,
                person_category TEXT NOT NULL DEFAULT 'autre',
                person_level INTEGER NOT NULL DEFAULT 2 CHECK (person_level IN (1, 2)),
                summary TEXT,
                biography TEXT,
                achievements TEXT,
                impact_population TEXT,
                source_text TEXT,
                annotation_id BIGINT REFERENCES dim_annotation(annotation_id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                created_by_user_id BIGINT REFERENCES app_user(user_id) ON DELETE SET NULL,
                updated_by_user_id BIGINT REFERENCES app_user(user_id) ON DELETE SET NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dim_person_location (
                person_location_id BIGSERIAL PRIMARY KEY,
                person_id BIGINT NOT NULL REFERENCES dim_person(person_id) ON DELETE CASCADE,
                city_id BIGINT REFERENCES dim_city(city_id) ON DELETE SET NULL,
                region TEXT,
                country TEXT,
                role TEXT NOT NULL DEFAULT 'residence'
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dim_person_photo (
                person_photo_id BIGSERIAL PRIMARY KEY,
                person_id BIGINT NOT NULL REFERENCES dim_person(person_id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                object_key TEXT,
                storage_provider TEXT,
                mime_type TEXT,
                file_size BIGINT,
                checksum_sha256 TEXT,
                caption TEXT,
                source_url TEXT,
                attribution TEXT,
                is_primary BOOLEAN NOT NULL DEFAULT FALSE,
                photo_order INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # --- vw_person_summary view ---
        cur.execute("""
            CREATE OR REPLACE VIEW vw_person_summary AS
            SELECT
                p.person_id,
                p.person_name,
                p.person_slug,
                p.birth_date,
                p.death_date,
                p.birth_year,
                p.death_year,
                p.birth_city,
                p.birth_country,
                p.death_city,
                p.death_country,
                p.person_level,
                p.person_category,
                p.summary,
                p.created_at,
                COUNT(DISTINCT pl.person_location_id) AS location_count,
                COUNT(DISTINCT pp.person_photo_id) AS photo_count,
                STRING_AGG(DISTINCT COALESCE(dc.city_name, pl.region), ',') AS location_names
            FROM dim_person p
            LEFT JOIN dim_person_location pl ON pl.person_id = p.person_id
            LEFT JOIN dim_city dc ON dc.city_id = pl.city_id
            LEFT JOIN dim_person_photo pp ON pp.person_id = p.person_id
            GROUP BY
                p.person_id,
                p.person_name,
                p.person_slug,
                p.birth_date,
                p.death_date,
                p.birth_year,
                p.death_year,
                p.birth_city,
                p.birth_country,
                p.death_city,
                p.death_country,
                p.person_level,
                p.person_category,
                p.summary,
                p.created_at
        """)

        # --- dim_monument tables ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dim_monument (
                monument_id BIGSERIAL PRIMARY KEY,
                monument_name TEXT NOT NULL,
                monument_slug TEXT NOT NULL UNIQUE,
                construction_date TEXT,
                inauguration_date TEXT,
                construction_year INTEGER,
                demolition_year INTEGER,
                architect TEXT,
                architectural_style TEXT,
                height_meters NUMERIC,
                floors INTEGER,
                latitude NUMERIC,
                longitude NUMERIC,
                monument_category TEXT NOT NULL DEFAULT 'autre',
                monument_level INTEGER NOT NULL DEFAULT 2 CHECK (monument_level IN (1, 2)),
                summary TEXT,
                description TEXT,
                history TEXT,
                significance TEXT,
                source_text TEXT,
                annotation_id BIGINT REFERENCES dim_annotation(annotation_id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                created_by_user_id BIGINT REFERENCES app_user(user_id) ON DELETE SET NULL,
                updated_by_user_id BIGINT REFERENCES app_user(user_id) ON DELETE SET NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dim_monument_location (
                monument_location_id BIGSERIAL PRIMARY KEY,
                monument_id BIGINT NOT NULL REFERENCES dim_monument(monument_id) ON DELETE CASCADE,
                city_id BIGINT REFERENCES dim_city(city_id) ON DELETE SET NULL,
                region TEXT,
                country TEXT,
                role TEXT NOT NULL DEFAULT 'primary'
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dim_monument_photo (
                monument_photo_id BIGSERIAL PRIMARY KEY,
                monument_id BIGINT NOT NULL REFERENCES dim_monument(monument_id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                object_key TEXT,
                storage_provider TEXT,
                mime_type TEXT,
                file_size BIGINT,
                checksum_sha256 TEXT,
                caption TEXT,
                source_url TEXT,
                attribution TEXT,
                is_primary BOOLEAN NOT NULL DEFAULT FALSE,
                photo_order INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # --- dim_monument latitude/longitude columns (must be before view) ---
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'dim_monument'",
        )
        _mon_cols = {row[0] for row in cur.fetchall()}
        if _mon_cols and "latitude" not in _mon_cols:
            cur.execute("ALTER TABLE dim_monument ADD COLUMN latitude NUMERIC")
        if _mon_cols and "longitude" not in _mon_cols:
            cur.execute("ALTER TABLE dim_monument ADD COLUMN longitude NUMERIC")

        # --- vw_monument_summary view ---
        cur.execute("""
            CREATE OR REPLACE VIEW vw_monument_summary AS
            SELECT
                m.monument_id,
                m.monument_name,
                m.monument_slug,
                m.construction_date,
                m.inauguration_date,
                m.construction_year,
                m.demolition_year,
                m.architect,
                m.architectural_style,
                m.height_meters,
                m.floors,
                m.monument_level,
                m.monument_category,
                m.summary,
                m.created_at,
                COUNT(DISTINCT ml.monument_location_id) AS location_count,
                COUNT(DISTINCT mp.monument_photo_id) AS photo_count,
                STRING_AGG(DISTINCT COALESCE(dc.city_name, ml.region), ',') AS location_names
            FROM dim_monument m
            LEFT JOIN dim_monument_location ml ON ml.monument_id = m.monument_id
            LEFT JOIN dim_city dc ON dc.city_id = ml.city_id
            LEFT JOIN dim_monument_photo mp ON mp.monument_id = m.monument_id
            GROUP BY
                m.monument_id,
                m.monument_name,
                m.monument_slug,
                m.construction_date,
                m.inauguration_date,
                m.construction_year,
                m.demolition_year,
                m.architect,
                m.architectural_style,
                m.height_meters,
                m.floors,
                m.latitude,
                m.longitude,
                m.monument_level,
                m.monument_category,
                m.summary,
                m.created_at
        """)


        # --- dim_legend tables ---
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dim_legend (
                legend_id BIGSERIAL PRIMARY KEY,
                legend_name TEXT NOT NULL,
                legend_slug TEXT NOT NULL UNIQUE,
                legend_type TEXT NOT NULL DEFAULT 'legende' CHECK (legend_type IN ('legende', 'inexplique')),
                legend_category TEXT NOT NULL DEFAULT 'origine_inconnue',
                legend_level INTEGER NOT NULL DEFAULT 2 CHECK (legend_level IN (1, 2)),
                date_reported TEXT,
                year_reported INTEGER,
                country TEXT,
                region TEXT,
                city_name TEXT,
                latitude NUMERIC,
                longitude NUMERIC,
                summary TEXT,
                description TEXT,
                history TEXT,
                evidence TEXT,
                source_text TEXT,
                annotation_id BIGINT REFERENCES dim_annotation(annotation_id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                created_by_user_id BIGINT REFERENCES app_user(user_id) ON DELETE SET NULL,
                updated_by_user_id BIGINT REFERENCES app_user(user_id) ON DELETE SET NULL
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dim_legend_location (
                legend_location_id BIGSERIAL PRIMARY KEY,
                legend_id BIGINT NOT NULL REFERENCES dim_legend(legend_id) ON DELETE CASCADE,
                city_id BIGINT REFERENCES dim_city(city_id) ON DELETE SET NULL,
                region TEXT,
                country TEXT,
                role TEXT NOT NULL DEFAULT 'primary'
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dim_legend_photo (
                legend_photo_id BIGSERIAL PRIMARY KEY,
                legend_id BIGINT NOT NULL REFERENCES dim_legend(legend_id) ON DELETE CASCADE,
                filename TEXT NOT NULL,
                object_key TEXT,
                storage_provider TEXT,
                mime_type TEXT,
                file_size BIGINT,
                checksum_sha256 TEXT,
                caption TEXT,
                source_url TEXT,
                attribution TEXT,
                is_primary BOOLEAN NOT NULL DEFAULT FALSE,
                photo_order INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # --- dim_legend country/region/city_name columns ---
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'dim_legend'",
        )
        _leg_cols = {row[0] for row in cur.fetchall()}
        if _leg_cols and "country" not in _leg_cols:
            cur.execute("ALTER TABLE dim_legend ADD COLUMN country TEXT")
        if _leg_cols and "region" not in _leg_cols:
            cur.execute("ALTER TABLE dim_legend ADD COLUMN region TEXT")
        if _leg_cols and "city_name" not in _leg_cols:
            cur.execute("ALTER TABLE dim_legend ADD COLUMN city_name TEXT")

        # --- vw_legend_summary view ---
        cur.execute("DROP VIEW IF EXISTS vw_legend_summary")
        cur.execute("""
            CREATE VIEW vw_legend_summary AS
            SELECT
                l.legend_id,
                l.legend_name,
                l.legend_slug,
                l.legend_type,
                l.legend_category,
                l.legend_level,
                l.date_reported,
                l.year_reported,
                l.country,
                l.region,
                l.city_name,
                l.summary,
                l.created_at,
                COUNT(DISTINCT ll.legend_location_id) AS location_count,
                COUNT(DISTINCT lp.legend_photo_id) AS photo_count,
                STRING_AGG(DISTINCT COALESCE(dc.city_name, ll.region), ',') AS location_names
            FROM dim_legend l
            LEFT JOIN dim_legend_location ll ON ll.legend_id = l.legend_id
            LEFT JOIN dim_city dc ON dc.city_id = ll.city_id
            LEFT JOIN dim_legend_photo lp ON lp.legend_id = l.legend_id
            GROUP BY
                l.legend_id,
                l.legend_name,
                l.legend_slug,
                l.legend_type,
                l.legend_category,
                l.legend_level,
                l.date_reported,
                l.year_reported,
                l.country,
                l.region,
                l.city_name,
                l.summary,
                l.created_at
        """)

        # --- tracking columns on entity tables ---
        _tracking_tables = ["dim_city", "dim_country", "dim_region", "dim_event", "dim_person", "dim_monument", "dim_legend"]
        for tbl in _tracking_tables:
            # Check which columns exist
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
                (tbl,),
            )
            cols = {row[0] for row in cur.fetchall()}
            if not cols:
                continue  # table does not exist yet
            if "created_at" not in cols:
                cur.execute(f"ALTER TABLE {tbl} ADD COLUMN created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP")
            if "updated_at" not in cols:
                cur.execute(f"ALTER TABLE {tbl} ADD COLUMN updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP")
            if "created_by_user_id" not in cols:
                cur.execute(f"ALTER TABLE {tbl} ADD COLUMN created_by_user_id BIGINT REFERENCES app_user(user_id) ON DELETE SET NULL")
            if "updated_by_user_id" not in cols:
                cur.execute(f"ALTER TABLE {tbl} ADD COLUMN updated_by_user_id BIGINT REFERENCES app_user(user_id) ON DELETE SET NULL")

        # Backfill created_by_user_id with the first admin user where NULL
        admin_row = cur.execute(
            "SELECT user_id FROM app_user WHERE role = 'admin' ORDER BY user_id LIMIT 1"
        ).fetchone()

        # --- Add image_url column to all photo tables (direct download URL) ---
        _photo_tables = [
            "dim_city_photo", "dim_event_photo", "dim_person_photo",
            "dim_country_photo", "dim_region_photo", "dim_monument_photo",
            "dim_legend_photo",
        ]
        for ptbl in _photo_tables:
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = %s AND column_name = 'image_url'",
                (ptbl,),
            )
            if not cur.fetchone():
                cur.execute(f"ALTER TABLE {ptbl} ADD COLUMN image_url TEXT DEFAULT ''")

        # --- Add photo_date column to all photo tables ---
        for ptbl in _photo_tables:
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = %s AND column_name = 'photo_date'",
                (ptbl,),
            )
            if not cur.fetchone():
                cur.execute(f"ALTER TABLE {ptbl} ADD COLUMN photo_date TEXT DEFAULT ''")

        if admin_row:
            admin_id = admin_row[0]
            for tbl in _tracking_tables:
                cur.execute(
                    f"UPDATE {tbl} SET created_by_user_id = %s WHERE created_by_user_id IS NULL",
                    (admin_id,),
                )

        # --- Reset all SERIAL/BIGSERIAL sequences to avoid PK conflicts ---
        _seq_resets = [
            ("dim_annotation",              "annotation_id"),
            ("dim_time",                     "time_id"),
            ("dim_city",                     "city_id"),
            ("dim_city_period_detail",       "period_detail_id"),
            ("dim_city_period_detail_item",  "period_detail_item_id"),
            ("fact_city_population",         "population_id"),
            ("dim_city_fiche",               "fiche_id"),
            ("dim_city_fiche_section",       "section_id"),
            ("dim_city_photo",               "photo_id"),
            ("dim_event",                    "event_id"),
            ("dim_event_location",           "event_location_id"),
            ("dim_event_photo",              "event_photo_id"),
            ("dim_person",                   "person_id"),
            ("dim_person_location",          "person_location_id"),
            ("dim_person_photo",             "person_photo_id"),
            ("dim_monument",                 "monument_id"),
            ("dim_monument_location",        "monument_location_id"),
            ("dim_monument_photo",           "monument_photo_id"),
            ("dim_legend",                   "legend_id"),
            ("dim_legend_location",          "legend_location_id"),
            ("dim_legend_photo",             "legend_photo_id"),
            ("dim_country",                  "country_id"),
            ("dim_country_photo",            "photo_id"),
            ("dim_region",                   "region_id"),
            ("dim_region_period_detail",     "region_period_id"),
            ("dim_region_period_detail_item","item_id"),
            ("dim_region_photo",             "photo_id"),
        ]
        for tbl, pk in _seq_resets:
            try:
                cur.execute(
                    f"SELECT setval(pg_get_serial_sequence('{tbl}', '{pk}'), "
                    f"COALESCE((SELECT MAX({pk}) FROM {tbl}), 0) + 1, false)"
                )
            except Exception:
                pass  # table may not exist yet

        conn.commit()
    finally:
        conn.close()
