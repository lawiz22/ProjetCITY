from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys

from build_city_database import (
    DETAILS_DIR,
    SOURCE_FILES,
    build_city_detail_lookup,
    collect_all_city_segments,
    is_separator_line,
    parse_city_period_detail_file,
    resolve_city_slug_from_detail_file,
)


def collect_detail_files(argv: list[str]) -> list[Path]:
    if len(argv) > 1:
        return [Path(value).resolve() for value in argv[1:]]
    return sorted(DETAILS_DIR.glob("*.txt"))


def find_orphan_lines(file_path: Path) -> list[str]:
    lines = file_path.read_text(encoding="utf-8").splitlines()
    orphan_lines: list[str] = []
    index = 0

    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            index += 1
            continue

        if "—" in stripped and index + 1 < len(lines) and is_separator_line(lines[index + 1]):
            index += 2
            while index < len(lines):
                current = lines[index].strip()
                if not current:
                    index += 1
                    break
                if "—" in current and index + 1 < len(lines) and is_separator_line(lines[index + 1]):
                    break
                index += 1
            continue

        orphan_lines.append(stripped)
        index += 1

    return orphan_lines


def main() -> int:
    detail_files = collect_detail_files(sys.argv)
    city_segments = collect_all_city_segments(SOURCE_FILES)
    city_lookup = build_city_detail_lookup(city_segments)

    errors: list[str] = []
    warnings: list[str] = []
    slug_counter: Counter[str] = Counter()

    if not detail_files:
        warnings.append(f"Aucun fichier .txt détecté dans le répertoire {DETAILS_DIR}")

    if not city_segments:
        errors.append("Aucune ville détectée dans villestats.py / villestats_v2.py")

    for detail_file in detail_files:
        if not detail_file.exists():
            errors.append(f"Fichier introuvable: {detail_file.name}")
            continue

        city_slug = resolve_city_slug_from_detail_file(detail_file, city_lookup)
        if city_slug is None:
            warnings.append(f"{detail_file.name}: aucune ville correspondante trouvée")
        else:
            slug_counter[city_slug] += 1

        sections = parse_city_period_detail_file(detail_file)
        orphan_lines = find_orphan_lines(detail_file)

        if not sections:
            warnings.append(f"{detail_file.name}: aucune période valide détectée")

        if orphan_lines:
            preview = "; ".join(orphan_lines[:3])
            warnings.append(f"{detail_file.name}: lignes hors section détectées ({preview})")

        for section in sections:
            range_label = section["period_range_label"]
            period_title = section["period_title"]
            start_year = section["start_year"]
            end_year = section["end_year"]

            if start_year is not None and end_year is not None and start_year > end_year:
                warnings.append(f"{detail_file.name}: plage inversée '{range_label}' pour '{period_title}'")

            if not period_title:
                warnings.append(f"{detail_file.name}: titre de période vide pour '{range_label}'")

            if not section["items"]:
                warnings.append(f"{detail_file.name}: aucune ligne de détail pour '{range_label} — {period_title}'")

        duplicate_ranges = [
            label for label, count in Counter(section["period_range_label"] for section in sections).items() if count > 1
        ]
        if duplicate_ranges:
            warnings.append(f"{detail_file.name}: plages de périodes dupliquées {duplicate_ranges}")

    duplicate_city_files = [slug for slug, count in slug_counter.items() if count > 1]
    for slug in duplicate_city_files:
        warnings.append(f"Plusieurs fichiers .txt associés à la même ville: {slug}")

    print("Validation des fichiers TXT de périodes")
    print(f"Fichiers détectés: {len(detail_files)}")
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
