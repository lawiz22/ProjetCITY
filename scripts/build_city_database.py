from __future__ import annotations

import ast
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
SOURCE_FILE = ROOT_DIR / "villestats.py"
SOURCE_FILES = [
    ROOT_DIR / "villestats.py",
    ROOT_DIR / "villestats_v2.py",
]
DETAILS_DIR = ROOT_DIR / "data" / "city_details"
SCHEMA_FILE = ROOT_DIR / "sql" / "schema.sql"
DATABASE_FILE = ROOT_DIR / "data" / "city_analysis.db"

CANADIAN_PROVINCES = {
    "Québec", "Quebec", "Ontario", "British Columbia", "Alberta", "Manitoba",
    "Saskatchewan", "Nova Scotia", "New Brunswick", "Prince Edward Island",
    "Newfoundland and Labrador", "Northwest Territories", "Nunavut", "Yukon"
}

US_STATES = {
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine",
    "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi", "Missouri",
    "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey", "New Mexico",
    "New York", "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
    "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota", "Tennessee",
    "Texas", "Utah", "Vermont", "Virginia", "Washington", "West Virginia",
    "Wisconsin", "Wyoming", "District of Columbia"
}

CITY_OVERRIDES = {
    "Montréal": ("Québec", "Canada"),
    "Montreal": ("Québec", "Canada"),
    "Boston": ("Massachusetts", "United States"),
}

REGION_ALIASES = {
    "Californie": "California",
    "Floride": "Florida",
    "Pennsylvanie": "Pennsylvania",
    "Caroline du Nord": "North Carolina",
    "Caroline du Sud": "South Carolina",
    "Virginie": "Virginia",
    "Géorgie": "Georgia",
    "Louisiane": "Louisiana",
}


def build_period_label(year: int) -> str:
    if year < 1850:
        return "Pré-industriel"
    if year < 1945:
        return "Industrialisation"
    if year < 1975:
        return "Après-guerre"
    if year < 2000:
        return "Suburbanisation"
    return "Ère contemporaine"


def build_time_row(year: int) -> dict[str, Any]:
    quarter_start = (year // 25) * 25
    half_start = (year // 50) * 50
    century = ((year - 1) // 100) + 1
    return {
        "year": year,
        "decade": (year // 10) * 10,
        "quarter_century_label": f"{quarter_start}-{quarter_start + 24}",
        "half_century_label": f"{half_start}-{half_start + 49}",
        "century": century,
        "period_label": build_period_label(year),
    }


def normalize_lookup_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", slugify(value))


def city_base_name(raw_city_name: str) -> str:
    return raw_city_name.split(",", 1)[0].strip()


def parse_period_range(period_range_label: str) -> tuple[int | None, int | None]:
    label = period_range_label.strip()

    match = re.fullmatch(r"(?P<year>\d{4})", label)
    if match:
        year = int(match.group("year"))
        return year, year

    match = re.fullmatch(r"(?P<start>\d{4})-(?P<end>\d{4})", label)
    if match:
        return int(match.group("start")), int(match.group("end"))

    match = re.fullmatch(r"(?P<start>\d{4})s", label)
    if match:
        start_year = int(match.group("start"))
        return start_year, start_year + 9

    match = re.fullmatch(r"(?P<start>\d{4})s-(?P<end>\d{4})", label)
    if match:
        return int(match.group("start")), int(match.group("end"))

    years = [int(year) for year in re.findall(r"\b\d{4}\b", label)]
    if len(years) == 1:
        return years[0], years[0]
    if len(years) >= 2:
        return years[0], years[-1]

    return None, None


def infer_years_from_text(*values: str) -> tuple[int | None, int | None]:
    years: list[int] = []
    for value in values:
        years.extend(int(year) for year in re.findall(r"\b\d{4}\b", value))

    if not years:
        return None, None

    return min(years), max(years)


def is_separator_line(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and all(character in {"━", "─", "-"} for character in stripped)


def build_city_detail_lookup(city_segments: list[dict[str, Any]]) -> dict[str, str]:
    lookup: dict[str, str] = {}

    for city in city_segments:
        city_name = city["city_name"]
        city_slug = city["city_slug"]
        base_name = city_name.split(",")[0].strip()
        first_token = base_name.split()[0]

        candidate_keys = {
            normalize_lookup_key(city_slug),
            normalize_lookup_key(city_name),
            normalize_lookup_key(base_name),
            normalize_lookup_key(first_token),
            normalize_lookup_key(f"{first_token}s"),
        }

        for key in candidate_keys:
            if key and key not in lookup:
                lookup[key] = city_slug

    return lookup


def resolve_city_slug_from_detail_file(file_path: Path, city_lookup: dict[str, str]) -> str | None:
    candidates = [normalize_lookup_key(file_path.stem)]
    if candidates[0].endswith("s"):
        candidates.append(candidates[0][:-1])

    for candidate in candidates:
        if candidate in city_lookup:
            return city_lookup[candidate]

    return None


def parse_city_period_detail_file(file_path: Path) -> list[dict[str, Any]]:
    lines = file_path.read_text(encoding="utf-8").splitlines()
    sections: list[dict[str, Any]] = []
    index = 0

    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue

        if "—" not in line or index + 1 >= len(lines) or not is_separator_line(lines[index + 1]):
            index += 1
            continue

        period_range_label, period_title = [part.strip() for part in line.split("—", 1)]
        start_year, end_year = parse_period_range(period_range_label)
        index += 2

        items: list[str] = []
        while index < len(lines):
            raw_line = lines[index].rstrip()
            stripped = raw_line.strip()
            if not stripped:
                index += 1
                break
            if "—" in stripped and index + 1 < len(lines) and is_separator_line(lines[index + 1]):
                break
            items.append(stripped)
            index += 1

        if start_year is None or end_year is None:
            inferred_start_year, inferred_end_year = infer_years_from_text(
                period_range_label,
                period_title,
                *items,
            )
            start_year = inferred_start_year
            end_year = inferred_end_year

        sections.append(
            {
                "period_range_label": period_range_label,
                "period_title": period_title,
                "start_year": start_year,
                "end_year": end_year,
                "items": items,
                "summary_text": "\n".join(items),
                "source_file": file_path.name,
            }
        )

    return sections


def upsert_time_dimension(connection: sqlite3.Connection, time_cache: dict[int, int], year: int | None) -> int | None:
    if year is None:
        return None

    time_id = time_cache.get(year)
    if time_id is not None:
        return time_id

    time_row = build_time_row(year)
    cursor = connection.execute(
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
        RETURNING time_id
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
    time_id = cursor.fetchone()[0]
    time_cache[year] = time_id
    return time_id


def build_city_row(city: dict[str, Any]) -> dict[str, Any]:
    return {
        "city_name": city["city_name"],
        "city_slug": city["city_slug"],
        "region": city["region"],
        "country": city["country"],
        "city_color": city["city_color"],
        "source_file": city["source_file"],
    }


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", normalized.strip().lower())
    return normalized.strip("-")


def literal_value(node: ast.AST) -> Any | None:
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def extract_city_from_title(title: str) -> str | None:
    match = re.search(r"Évolution démographique de (.+?)(?:\s*\(|\\n|\n)", title)
    if match:
        return match.group(1).strip()
    return None


def extract_plot_color(call: ast.Call) -> str | None:
    for keyword in call.keywords:
        if keyword.arg == "color":
            value = literal_value(keyword.value)
            if isinstance(value, str):
                return value
    return None


def is_show_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        return False
    func = node.value.func
    return isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "plt" and func.attr == "show"


def extract_key_years_from_for(node: ast.For) -> list[int] | None:
    for child in node.body:
        if isinstance(child, ast.If) and isinstance(child.test, ast.Compare):
            test = child.test
            if (
                isinstance(test.left, ast.Name)
                and test.left.id == "year"
                and len(test.ops) == 1
                and isinstance(test.ops[0], ast.In)
                and len(test.comparators) == 1
            ):
                years = literal_value(test.comparators[0])
                if isinstance(years, (list, tuple)) and all(isinstance(item, int) for item in years):
                    return list(years)
    return None


def split_location(raw_city_name: str) -> tuple[str | None, str]:
    if raw_city_name in CITY_OVERRIDES:
        return CITY_OVERRIDES[raw_city_name]

    if "," in raw_city_name:
        parts = [part.strip() for part in raw_city_name.split(",")]
        region = REGION_ALIASES.get(parts[-1], parts[-1])
        if region in CANADIAN_PROVINCES:
            return region, "Canada"
        if region in US_STATES:
            return region, "United States"
        return region, "Unknown"

    return None, "Unknown"


def finalize_segment(segment: dict[str, Any], source_file: Path) -> dict[str, Any] | None:
    years = segment.get("years")
    populations = segment.get("population")
    raw_city_name = segment.get("city_name")

    if not years or not populations or len(years) != len(populations):
        return None

    if not raw_city_name and segment.get("title"):
        raw_city_name = extract_city_from_title(segment["title"])

    if not raw_city_name:
        return None

    city_name = city_base_name(raw_city_name)
    region, country = split_location(raw_city_name)

    return {
        "city_name": city_name,
        "raw_city_name": raw_city_name,
        "city_slug": slugify(raw_city_name),
        "region": region,
        "country": country,
        "city_color": segment.get("city_color"),
        "years": years,
        "population": populations,
        "annotations": segment.get("annotations", []),
        "key_years": set(segment.get("key_years", [])),
        "source_file": source_file.name,
    }


def extract_city_segments(source_file: Path) -> list[dict[str, Any]]:
    tree = ast.parse(source_file.read_text(encoding="utf-8"))
    segments: list[dict[str, Any]] = []
    current: dict[str, Any] = {}

    for node in tree.body:
        if isinstance(node, ast.Assign):
            value = literal_value(node.value)
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id == "CITY_NAME" and current.get("city_name") and isinstance(value, str):
                    finalized = finalize_segment(current, source_file)
                    if finalized:
                        segments.append(finalized)
                    current = {}
                if target.id == "CITY_NAME" and isinstance(value, str):
                    current["city_name"] = value
                elif target.id == "CITY_COLOR" and isinstance(value, str):
                    current["city_color"] = value
                elif target.id == "years" and isinstance(value, list):
                    current["years"] = value
                elif target.id == "population" and isinstance(value, list):
                    current["population"] = value
                elif target.id == "annotations" and isinstance(value, list):
                    current["annotations"] = value
                elif target.id == "key_years" and isinstance(value, list):
                    current["key_years"] = value
        elif isinstance(node, ast.For):
            if "key_years" not in current:
                extracted_years = extract_key_years_from_for(node)
                if extracted_years:
                    current["key_years"] = extracted_years
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            func = call.func
            if isinstance(func, ast.Attribute):
                if func.attr in {"title", "set_title"} and call.args:
                    title_value = literal_value(call.args[0])
                    if isinstance(title_value, str):
                        current["title"] = title_value
                elif func.attr == "semilogy":
                    plot_color = extract_plot_color(call)
                    if plot_color and "city_color" not in current:
                        current["city_color"] = plot_color

        if is_show_call(node):
            finalized = finalize_segment(current, source_file)
            if finalized:
                segments.append(finalized)
            current = {}

    finalized = finalize_segment(current, source_file)
    if finalized:
        segments.append(finalized)

    return segments


def collect_all_city_segments(source_files: list[Path]) -> list[dict[str, Any]]:
    all_segments: list[dict[str, Any]] = []
    for source_file in source_files:
        if source_file.exists():
            all_segments.extend(extract_city_segments(source_file))
    return all_segments


def import_city_period_details(
    connection: sqlite3.Connection,
    city_segments: list[dict[str, Any]],
    city_cache: dict[str, int],
    time_cache: dict[int, int],
) -> tuple[int, int]:
    city_lookup = build_city_detail_lookup(city_segments)
    detail_row_count = 0
    detail_item_count = 0

    for detail_file in sorted(DETAILS_DIR.glob("*.txt")):
        city_slug = resolve_city_slug_from_detail_file(detail_file, city_lookup)
        if city_slug is None or city_slug not in city_cache:
            continue

        city_id = city_cache[city_slug]
        sections = parse_city_period_detail_file(detail_file)

        for period_order, section in enumerate(sections, start=1):
            start_time_id = upsert_time_dimension(connection, time_cache, section["start_year"])
            end_time_id = upsert_time_dimension(connection, time_cache, section["end_year"])

            cursor = connection.execute(
                """
                INSERT INTO dim_city_period_detail (
                    city_id,
                    period_order,
                    period_range_label,
                    period_title,
                    start_year,
                    end_year,
                    start_time_id,
                    end_time_id,
                    summary_text,
                    source_file
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING period_detail_id
                """,
                (
                    city_id,
                    period_order,
                    section["period_range_label"],
                    section["period_title"],
                    section["start_year"],
                    section["end_year"],
                    start_time_id,
                    end_time_id,
                    section["summary_text"],
                    section["source_file"],
                ),
            )
            period_detail_id = cursor.fetchone()[0]
            detail_row_count += 1

            for item_order, item_text in enumerate(section["items"], start=1):
                connection.execute(
                    """
                    INSERT INTO dim_city_period_detail_item (
                        period_detail_id,
                        item_order,
                        item_text
                    )
                    VALUES (?, ?, ?)
                    """,
                    (period_detail_id, item_order, item_text),
                )
                detail_item_count += 1

    return detail_row_count, detail_item_count


def build_database() -> tuple[int, int]:
    city_segments = collect_all_city_segments(SOURCE_FILES)
    if not city_segments:
        raise RuntimeError("Aucune ville détectée dans les fichiers source")

    DATABASE_FILE.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DATABASE_FILE) as connection:
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.executescript(SCHEMA_FILE.read_text(encoding="utf-8"))

        annotation_cache: dict[tuple[str, str], int] = {}
        city_cache: dict[str, int] = {}
        fact_rows: dict[tuple[str, int], dict[str, Any]] = {}
        time_cache: dict[int, int] = {}

        for city in city_segments:
            annotation_by_year: dict[int, int] = {}
            for annotation in city["annotations"]:
                if len(annotation) < 4:
                    continue
                year, _population, label, color = annotation[:4]
                if not isinstance(year, int) or not isinstance(label, str) or not isinstance(color, str):
                    continue

                annotation_key = (label, color)
                annotation_id = annotation_cache.get(annotation_key)
                if annotation_id is None:
                    cursor = connection.execute(
                        """
                        INSERT INTO dim_annotation (annotation_label, annotation_color)
                        VALUES (?, ?)
                        ON CONFLICT(annotation_label, annotation_color)
                        DO UPDATE SET annotation_color = excluded.annotation_color
                        RETURNING annotation_id
                        """,
                        annotation_key,
                    )
                    annotation_id = cursor.fetchone()[0]
                    annotation_cache[annotation_key] = annotation_id

                annotation_by_year[year] = annotation_id

            for year, population in zip(city["years"], city["population"]):
                key = (city["city_slug"], year)
                new_row = {
                    "city_name": city["city_name"],
                    "raw_city_name": city.get("raw_city_name", city["city_name"]),
                    "city_slug": city["city_slug"],
                    "region": city["region"],
                    "country": city["country"],
                    "city_color": city["city_color"],
                    "year": year,
                    "population": population,
                    "is_key_year": 1 if year in city["key_years"] else 0,
                    "annotation_id": annotation_by_year.get(year),
                    "source_file": city["source_file"],
                }

                existing_row = fact_rows.get(key)
                if existing_row is None:
                    fact_rows[key] = new_row
                else:
                    existing_row["region"] = existing_row["region"] or new_row["region"]
                    existing_row["country"] = (
                        existing_row["country"]
                        if existing_row["country"] != "Unknown"
                        else new_row["country"]
                    )
                    existing_row["city_color"] = existing_row["city_color"] or new_row["city_color"]
                    existing_row["population"] = new_row["population"]
                    existing_row["is_key_year"] = max(existing_row["is_key_year"], new_row["is_key_year"])
                    existing_row["annotation_id"] = existing_row["annotation_id"] or new_row["annotation_id"]

        for row in fact_rows.values():
            city_id = city_cache.get(row["city_slug"])
            if city_id is None:
                city_row = build_city_row(row)
                cursor = connection.execute(
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
                    RETURNING city_id
                    """,
                    (
                        city_row["city_name"],
                        city_row["city_slug"],
                        city_row["region"],
                        city_row["country"],
                        city_row["city_color"],
                        city_row["source_file"],
                    ),
                )
                city_id = cursor.fetchone()[0]
                city_cache[row["city_slug"]] = city_id

            time_id = upsert_time_dimension(connection, time_cache, row["year"])

            connection.execute(
                """
                INSERT INTO fact_city_population (
                    city_id,
                    time_id,
                    year,
                    population,
                    is_key_year,
                    annotation_id,
                    source_file
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    city_id,
                    time_id,
                    row["year"],
                    row["population"],
                    row["is_key_year"],
                    row["annotation_id"],
                    row["source_file"],
                ),
            )

        period_detail_count, period_detail_item_count = import_city_period_details(
            connection,
            city_segments,
            city_cache,
            time_cache,
        )

        connection.commit()

        total_rows = connection.execute("SELECT COUNT(*) FROM fact_city_population").fetchone()[0]
        annotation_count = connection.execute("SELECT COUNT(*) FROM dim_annotation").fetchone()[0]
        city_count = connection.execute("SELECT COUNT(*) FROM dim_city").fetchone()[0]
        time_count = connection.execute("SELECT COUNT(*) FROM dim_time").fetchone()[0]
        period_detail_count = connection.execute("SELECT COUNT(*) FROM dim_city_period_detail").fetchone()[0]
        period_detail_item_count = connection.execute("SELECT COUNT(*) FROM dim_city_period_detail_item").fetchone()[0]

    return (
        city_count,
        total_rows + annotation_count + city_count + time_count + period_detail_count + period_detail_item_count,
    )


def main() -> None:
    city_count, total_records = build_database()
    print(f"Base SQLite créée: {DATABASE_FILE}")
    print(f"Villes uniques importées : {city_count}")
    print(f"Enregistrements créés (faits + dimensions) : {total_records}")


if __name__ == "__main__":
    main()
