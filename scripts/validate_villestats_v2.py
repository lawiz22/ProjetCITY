from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path
import sys
from typing import Any

from build_city_database import city_base_name, slugify, split_location

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_FILE = ROOT_DIR / "villestats_v2.py"


def literal_value(node: ast.AST) -> Any | None:
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def finalize_segment(segment: dict[str, Any]) -> dict[str, Any] | None:
    city_name = segment.get("city_name")
    years = segment.get("years")
    population = segment.get("population")

    if not city_name or not isinstance(years, list) or not isinstance(population, list):
        return None

    region, country = split_location(city_name)
    return {
        "city_name": city_base_name(city_name),
        "raw_city_name": city_name,
        "city_slug": slugify(city_name),
        "city_color": segment.get("city_color"),
        "years": years,
        "population": population,
        "annotations": segment.get("annotations", []),
        "region": region,
        "country": country,
    }


def extract_city_segments(source_file: Path) -> list[dict[str, Any]]:
    tree = ast.parse(source_file.read_text(encoding="utf-8"))
    segments: list[dict[str, Any]] = []
    current: dict[str, Any] = {}

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue

        value = literal_value(node.value)
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue

            if target.id == "CITY_NAME" and current.get("city_name"):
                finalized = finalize_segment(current)
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

    finalized = finalize_segment(current)
    if finalized:
        segments.append(finalized)

    return segments


def validate_source(source_path: Path) -> tuple[list[str], list[str], int]:
    segments = extract_city_segments(source_path)

    errors: list[str] = []
    warnings: list[str] = []
    city_year_counter: Counter[tuple[str, int]] = Counter()
    city_slug_counter: Counter[str] = Counter()

    if not segments:
        errors.append(f"Aucune ville valide détectée dans {source_path.name}")
        return errors, warnings, 0

    for city in segments:
        city_name = city["city_name"]
        display_name = city.get("raw_city_name", city_name)
        city_slug = city["city_slug"]
        years = city["years"]
        populations = city["population"]
        annotations = city["annotations"]

        city_slug_counter[city_slug] += 1

        if not city["city_color"]:
            warnings.append(f"{display_name}: couleur de ville absente")

        if city["country"] == "Unknown":
            warnings.append(f"{display_name}: pays non reconnu, vérifier le nom de région/état/province")

        if years != sorted(years):
            warnings.append(f"{display_name}: les années ne sont pas triées en ordre croissant")

        duplicated_years = [year for year, count in Counter(years).items() if count > 1]
        if duplicated_years:
            warnings.append(f"{display_name}: années dupliquées détectées {duplicated_years}")

        if len(years) != len(populations):
            errors.append(f"{display_name}: le nombre d'années et de populations ne correspond pas")
            continue

        for year in years:
            city_year_counter[(city_slug, year)] += 1

        population_by_year = dict(zip(years, populations))
        for annotation in annotations:
            if len(annotation) < 4:
                warnings.append(f"{display_name}: annotation incomplète détectée {annotation}")
                continue

            year, population, label, color = annotation[:4]
            if year not in population_by_year:
                warnings.append(f"{display_name}: annotation '{label}' pointe vers une année absente ({year})")
                continue

            if population_by_year[year] != population:
                warnings.append(
                    f"{display_name}: annotation '{label}' a une population différente de la série ({population} vs {population_by_year[year]})"
                )

            if not color:
                warnings.append(f"{display_name}: annotation '{label}' sans couleur")

    duplicate_pairs = [(slug, year, count) for (slug, year), count in city_year_counter.items() if count > 1]
    for city_slug, year, count in duplicate_pairs:
        warnings.append(f"Doublon global: {city_slug} / {year} apparaît {count} fois")

    duplicate_slugs = [(slug, count) for slug, count in city_slug_counter.items() if count > 1]
    for slug, count in duplicate_slugs:
        warnings.append(f"Slug dupliqué: {slug} apparaît {count} fois")

    return errors, warnings, len(segments)


def main() -> int:
    source_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_SOURCE_FILE
    errors, warnings, city_count = validate_source(source_path)

    print(f"Validation de {source_path.name}")
    print(f"Villes détectées: {city_count}")
    print(f"Erreurs: {len(errors)}")
    print(f"Avertissements: {len(warnings)}")

    if errors:
        print("\nErreurs:")
        for item in errors:
            print(f"- {item}")

    if warnings:
        print("\nAvertissements:")
        for item in warnings:
            print(f"- {item}")

    if not errors and not warnings:
        print("\nAucun problème détecté.")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
