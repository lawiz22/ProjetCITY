"""Extract all city data from the database and generate villestats_RAW.py.

This script reads every city from dim_city + fact_city_population + annotations
and produces the canonical Python source file that mirrors the DB contents.

Run:  python scripts/export_villestats_raw.py
"""
from __future__ import annotations

import sqlite3
import textwrap
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "city_analysis.db"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "villestats_RAW.py"


def export_all() -> str:
    """Return the full Python source text for villestats_RAW.py."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    cities = conn.execute(
        "SELECT city_id, city_name, city_slug, region, country, city_color "
        "FROM dim_city ORDER BY city_name COLLATE NOCASE"
    ).fetchall()

    blocks: list[str] = []

    for city in cities:
        city_id = city["city_id"]
        city_name = city["city_name"]
        region = city["region"] or ""
        country = city["country"]
        city_color = city["city_color"] or "#333333"

        # Build CITY_NAME value: "Name, Region" or "Name, Country" if no region
        if region:
            raw_name = f"{city_name}, {region}"
        else:
            raw_name = f"{city_name}, {country}"

        rows = conn.execute(
            "SELECT v.year, v.population, v.annotation_label, v.annotation_color "
            "FROM vw_city_population_analysis v "
            "WHERE v.city_id = ? ORDER BY v.year",
            (city_id,),
        ).fetchall()

        if not rows:
            continue

        years = [r["year"] for r in rows]
        pops = [r["population"] for r in rows]

        annotations: list[str] = []
        for r in rows:
            if r["annotation_label"]:
                label = r["annotation_label"].replace('"', '\\"')
                color = r["annotation_color"] or "black"
                annotations.append(
                    f'    ({r["year"]}, {r["population"]}, "{label}", \'{color}\'),'
                )

        # Format years line(s)
        years_str = format_list(years)
        pop_str = format_list(pops)

        block_lines = [
            f'# {"=" * 60}',
            f'# {city_name} ({country})',
            f'# {"=" * 60}',
            f'CITY_NAME = "{raw_name}"',
            f"CITY_COLOR = '{city_color}'",
            "",
            f"years = {years_str}",
            f"population = {pop_str}",
            "",
        ]

        if annotations:
            block_lines.append("annotations = [")
            block_lines.extend(annotations)
            block_lines.append("]")
        else:
            block_lines.append("annotations = []")

        blocks.append("\n".join(block_lines))

    conn.close()

    header = textwrap.dedent("""\
        # -*- coding: utf-8 -*-
        # ================================================================
        # villestats_RAW.py — Export automatique depuis la BD ProjetCITY
        # Ce fichier est régénéré à chaque import de ville.
        # NE PAS MODIFIER MANUELLEMENT — les changements seront écrasés.
        # ================================================================
        #
        # Nombre de villes : {count}
        #

    """).format(count=len(blocks))

    return header + "\n\n".join(blocks) + "\n"


def format_list(values: list[int]) -> str:
    """Format a list of ints, wrapping at ~90 chars."""
    inner = ", ".join(str(v) for v in values)
    if len(inner) + 2 <= 90:
        return f"[{inner}]"
    # Wrap
    lines: list[str] = ["["]
    line = "    "
    for i, v in enumerate(values):
        token = str(v) + ("," if i < len(values) - 1 else "")
        if len(line) + len(token) + 1 > 90:
            lines.append(line)
            line = "    " + token + " "
        else:
            line += token + " "
    lines.append(line.rstrip())
    lines.append("]")
    return "\n".join(lines)


if __name__ == "__main__":
    content = export_all()
    OUTPUT_PATH.write_text(content, encoding="utf-8")
    city_count = content.count("CITY_NAME =")
    print(f"villestats_RAW.py généré — {city_count} villes")
