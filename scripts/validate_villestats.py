from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys

from build_city_database import SOURCE_FILE, extract_city_segments


def main() -> int:
    source_path = Path(SOURCE_FILE)
    segments = extract_city_segments(source_path)

    errors: list[str] = []
    warnings: list[str] = []
    city_year_counter: Counter[tuple[str, int]] = Counter()
    city_slug_counter: Counter[str] = Counter()

    if not segments:
        errors.append("Aucune ville valide détectée dans villestats.py")

    for city in segments:
        city_name = city["city_name"]
        display_name = city.get("raw_city_name", city_name)
        city_slug = city["city_slug"]
        years = city["years"]
        populations = city["population"]
        annotations = city["annotations"]
        key_years = city["key_years"]

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

        missing_key_years = sorted(set(key_years) - set(years))
        if missing_key_years:
            warnings.append(f"{display_name}: années clés absentes de la série {missing_key_years}")

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

    duplicate_pairs = [(city_slug, year, count) for (city_slug, year), count in city_year_counter.items() if count > 1]
    for city_slug, year, count in duplicate_pairs:
        warnings.append(f"Doublon global: {city_slug} / {year} apparaît {count} fois")

    duplicate_slugs = [(slug, count) for slug, count in city_slug_counter.items() if count > 1]
    for slug, count in duplicate_slugs:
        warnings.append(f"Slug dupliqué: {slug} apparaît {count} fois")

    print(f"Validation de {source_path.name}")
    print(f"Villes détectées: {len(segments)}")
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
