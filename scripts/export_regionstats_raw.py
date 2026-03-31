"""Extract all region data from the database and generate regionstats_RAW.py.

This script reads every region from dim_region + fact_region_population + annotations
and produces the canonical Python source file that mirrors the DB contents.

Run:  python scripts/export_regionstats_raw.py
"""
from __future__ import annotations

import sqlite3
import textwrap
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "city_analysis.db"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "regionstats_RAW.py"


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
    """Return the full Python source text for regionstats_RAW.py."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    regions = conn.execute(
        "SELECT region_id, region_name, region_slug, country_name, region_color "
        "FROM dim_region ORDER BY country_name COLLATE NOCASE, region_name COLLATE NOCASE"
    ).fetchall()

    blocks: list[str] = []

    for region in regions:
        region_id = region["region_id"]
        region_name = region["region_name"]
        country_name = region["country_name"]
        region_color = region["region_color"] or "#333333"

        rows = conn.execute(
            """SELECT rp.year, rp.population, a.annotation_label, a.annotation_color
               FROM fact_region_population rp
               LEFT JOIN dim_annotation a ON rp.annotation_id = a.annotation_id
               WHERE rp.region_id = ?
               ORDER BY rp.year""",
            (region_id,),
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
            f"# {region_name} ({country_name})",
            f'# {"=" * 60}',
            f'REGION_NAME = "{region_name}"',
            f'REGION_COUNTRY = "{country_name}"',
            f"REGION_COLOR = '{region_color}'",
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
        # regionstats_RAW.py — Export automatique depuis la BD Central City Scrutinizer
        # Ce fichier est régénéré à chaque import de région.
        # NE PAS MODIFIER MANUELLEMENT — les changements seront écrasés.
        # ================================================================
        #
        # Nombre de régions : {count}
        #

    """).format(count=len(blocks))

    return header + "\n\n".join(blocks) + "\n"


if __name__ == "__main__":
    content = export_all()
    OUTPUT_PATH.write_text(content, encoding="utf-8")
    print(f"Exported to {OUTPUT_PATH}")
