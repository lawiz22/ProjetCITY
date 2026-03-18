from __future__ import annotations

import sqlite3
from pathlib import Path

from build_city_database import DATABASE_FILE, import_city_period_details


def main() -> None:
    database_path = Path(DATABASE_FILE)
    if not database_path.exists():
        raise FileNotFoundError(f"Base introuvable: {database_path}")

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON;")

        city_rows = connection.execute(
            "SELECT city_id, city_name, city_slug FROM dim_city ORDER BY city_name"
        ).fetchall()
        city_cache = {city_slug: city_id for city_id, _city_name, city_slug in city_rows}
        city_segments = [
            {"city_name": city_name, "city_slug": city_slug}
            for _city_id, city_name, city_slug in city_rows
        ]
        time_cache = {
            year: time_id
            for time_id, year in connection.execute("SELECT time_id, year FROM dim_time")
        }

        connection.execute("DELETE FROM dim_city_period_detail_item")
        connection.execute("DELETE FROM dim_city_period_detail")

        period_count, item_count = import_city_period_details(
            connection,
            city_segments,
            city_cache,
            time_cache,
        )
        connection.commit()

    print(f"Import des périodes détaillées terminé: {database_path}")
    print(f"Périodes détaillées importées : {period_count}")
    print(f"Éléments détaillés importés : {item_count}")


if __name__ == "__main__":
    main()
