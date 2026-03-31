"""Extract all country data from the database and generate paysstats_RAW.py.

This script reads every country from dim_country + fact_country_population + annotations
and produces the canonical Python source file that mirrors the DB contents.

Run:  python scripts/export_paysstats_raw.py
"""
from __future__ import annotations

import sqlite3
import textwrap
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "city_analysis.db"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "paysstats_RAW.py"


def format_list(values: list[int]) -> str:
    """Format a list of ints, wrapping at ~90 chars."""
    inner = ", ".join(str(v) for v in values)
    if len(inner) + 2 <= 90:
        return f"[{inner}]"
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


def export_all() -> str:
    """Return the full Python source text for paysstats_RAW.py."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    countries = conn.execute(
        "SELECT country_id, country_name, country_slug, country_color "
        "FROM dim_country ORDER BY country_name COLLATE NOCASE"
    ).fetchall()

    blocks: list[str] = []

    for country in countries:
        country_id = country["country_id"]
        country_name = country["country_name"]
        country_color = country["country_color"] or "#333333"

        rows = conn.execute(
            """SELECT fp.year, fp.population, a.annotation_label, a.annotation_color
               FROM fact_country_population fp
               LEFT JOIN dim_annotation a ON fp.annotation_id = a.annotation_id
               WHERE fp.country_id = ?
               ORDER BY fp.year""",
            (country_id,),
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

        years_str = format_list(years)
        pop_str = format_list(pops)

        block_lines = [
            f'# {"=" * 60}',
            f"# {country_name}",
            f'# {"=" * 60}',
            f'COUNTRY_NAME = "{country_name}"',
            f"COUNTRY_COLOR = '{country_color}'",
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
        # paysstats_RAW.py — Export automatique depuis la BD Central City Scrutinizer
        # Ce fichier est régénéré à chaque import de pays.
        # NE PAS MODIFIER MANUELLEMENT — les changements seront écrasés.
        # ================================================================
        #
        # Nombre de pays : {count}
        #

    """).format(count=len(blocks))

    return header + "\n\n".join(blocks) + "\n"


if __name__ == "__main__":
    content = export_all()
    OUTPUT_PATH.write_text(content, encoding="utf-8")
    print(f"Exported to {OUTPUT_PATH}")
