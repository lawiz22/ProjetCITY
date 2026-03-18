from __future__ import annotations

import sqlite3
from pathlib import Path

from build_city_database import DATABASE_FILE, build_time_row, city_base_name, slugify, split_location


def table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def ensure_dim_city(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS dim_city (
            city_id INTEGER PRIMARY KEY AUTOINCREMENT,
            city_name TEXT NOT NULL,
            city_slug TEXT NOT NULL UNIQUE,
            region TEXT,
            country TEXT NOT NULL,
            city_color TEXT,
            source_file TEXT NOT NULL
        )
        """
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_city_slug ON dim_city (city_slug)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_city_country ON dim_city (country, region)")


def ensure_dim_time(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS dim_time (
            time_id INTEGER PRIMARY KEY AUTOINCREMENT,
            year INTEGER NOT NULL UNIQUE,
            decade INTEGER NOT NULL,
            quarter_century_label TEXT NOT NULL,
            half_century_label TEXT NOT NULL,
            century INTEGER NOT NULL,
            period_label TEXT NOT NULL
        )
        """
    )


def populate_dim_time_from_fact(connection: sqlite3.Connection) -> None:
    years = [row[0] for row in connection.execute("SELECT DISTINCT year FROM fact_city_population ORDER BY year")]
    for year in years:
        time_row = build_time_row(year)
        connection.execute(
            """
            INSERT INTO dim_time (
                year,
                decade,
                quarter_century_label,
                half_century_label,
                century,
                period_label
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(year)
            DO UPDATE SET
                decade = excluded.decade,
                quarter_century_label = excluded.quarter_century_label,
                half_century_label = excluded.half_century_label,
                century = excluded.century,
                period_label = excluded.period_label
            """,
            (
                time_row["year"],
                time_row["decade"],
                time_row["quarter_century_label"],
                time_row["half_century_label"],
                time_row["century"],
                time_row["period_label"],
            ),
        )


def populate_dim_city_from_legacy_fact(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        """
        SELECT DISTINCT
            city_name,
            city_slug,
            region,
            country,
            city_color,
            source_file
        FROM fact_city_population
        ORDER BY city_name, city_slug
        """
    ).fetchall()

    for row in rows:
        raw_city_name = row[0]
        city_slug = row[1] or slugify(raw_city_name)
        normalized_region = row[2]
        normalized_country = row[3]

        if raw_city_name:
            parsed_region, parsed_country = split_location(raw_city_name)
            normalized_region = normalized_region or parsed_region
            normalized_country = normalized_country if normalized_country != "Unknown" else parsed_country

        normalized_row = (
            city_base_name(raw_city_name),
            city_slug,
            normalized_region,
            normalized_country,
            row[4],
            row[5],
        )

        connection.execute(
            """
            INSERT INTO dim_city (
                city_name,
                city_slug,
                region,
                country,
                city_color,
                source_file
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(city_slug)
            DO UPDATE SET
                city_name = excluded.city_name,
                region = excluded.region,
                country = excluded.country,
                city_color = excluded.city_color,
                source_file = excluded.source_file
            """,
            normalized_row,
        )


def repair_legacy_fact_table(connection: sqlite3.Connection) -> None:
    legacy_columns = table_columns(connection, "fact_city_population")
    if "city_id" in legacy_columns and "city_name" not in legacy_columns:
        return

    connection.execute(
        """
        CREATE TABLE fact_city_population_new (
            population_id INTEGER PRIMARY KEY AUTOINCREMENT,
            city_id INTEGER NOT NULL,
            time_id INTEGER NOT NULL,
            year INTEGER NOT NULL,
            population INTEGER NOT NULL,
            is_key_year INTEGER NOT NULL DEFAULT 0 CHECK (is_key_year IN (0, 1)),
            annotation_id INTEGER,
            source_file TEXT NOT NULL,
            UNIQUE(city_id, year),
            FOREIGN KEY (city_id) REFERENCES dim_city(city_id),
            FOREIGN KEY (time_id) REFERENCES dim_time(time_id),
            FOREIGN KEY (annotation_id) REFERENCES dim_annotation(annotation_id)
        )
        """
    )

    connection.execute(
        """
        INSERT INTO fact_city_population_new (
            city_id,
            time_id,
            year,
            population,
            is_key_year,
            annotation_id,
            source_file
        )
        SELECT
            dc.city_id,
            dt.time_id,
            f.year,
            f.population,
            f.is_key_year,
            f.annotation_id,
            f.source_file
        FROM fact_city_population f
        INNER JOIN dim_city dc
            ON dc.city_slug = f.city_slug
        INNER JOIN dim_time dt
            ON dt.year = f.year
        """
    )

    connection.execute("DROP TABLE fact_city_population")
    connection.execute("ALTER TABLE fact_city_population_new RENAME TO fact_city_population")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_fact_city_year ON fact_city_population (city_id, year)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_fact_time ON fact_city_population (time_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_fact_annotation ON fact_city_population (annotation_id)")


def main() -> None:
    database_path = Path(DATABASE_FILE)
    if not database_path.exists():
        raise FileNotFoundError(f"Base introuvable: {database_path}")

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = OFF;")
        ensure_dim_city(connection)
        ensure_dim_time(connection)
        populate_dim_time_from_fact(connection)

        columns = table_columns(connection, "fact_city_population")
        if "city_name" in columns and "city_slug" in columns:
            populate_dim_city_from_legacy_fact(connection)

        repair_legacy_fact_table(connection)
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.commit()

        city_count = connection.execute("SELECT COUNT(*) FROM dim_city").fetchone()[0]
        time_count = connection.execute("SELECT COUNT(*) FROM dim_time").fetchone()[0]
        fact_count = connection.execute("SELECT COUNT(*) FROM fact_city_population").fetchone()[0]

    print(f"Base corrigée: {database_path}")
    print(f"dim_city: {city_count} lignes")
    print(f"dim_time: {time_count} lignes")
    print(f"fact_city_population: {fact_count} lignes")


if __name__ == "__main__":
    main()
