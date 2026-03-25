from __future__ import annotations

import csv
import io
import json
import uuid
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, UTC
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Sequence

from flask import current_app

from app.db import get_db
from app.services.city_coordinates import CITY_COORDINATES
from app.services.city_photos import get_city_photo


READ_ONLY_PREFIXES = ("select", "with", "pragma")
PERIOD_ORDER = [
    "Pré-industriel",
    "Industrialisation",
    "Après-guerre",
    "Suburbanisation",
    "Ère contemporaine",
]
WRITE_PREFIXES = (
    "insert",
    "update",
    "delete",
    "create",
    "drop",
    "alter",
    "replace",
    "vacuum",
)


class SqlExecutionError(RuntimeError):
    pass


@lru_cache(maxsize=256)
def _get_city_origin_metadata(city_slug: str) -> dict[str, int | None]:
    details_path = Path(current_app.root_path).parent / "data" / "city_details" / f"{city_slug}.txt"
    if not details_path.exists():
        return {"foundation_year": None}

    source_text = details_path.read_text(encoding="utf-8")
    patterns = (
        r"(?:fond(?:ation|e|ée|é)|founded|established|incorporated|cr[eé]ation|na[iî]t).{0,80}?(1[5-9]\d{2}|20\d{2})",
        r"(1[5-9]\d{2}|20\d{2}).{0,80}?(?:fond(?:ation|e|ée|é)|founded|established|incorporated|cr[eé]ation|na[iî]t)",
    )
    for pattern in patterns:
        match = re.search(pattern, source_text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            year = next((group for group in match.groups() if group), None)
            return {"foundation_year": int(year) if year else None}
    return {"foundation_year": None}


class AnalyticsService:
    def _normalize_narrative_text(self, value: str | None) -> str:
        if not value:
            return ""
        return re.sub(r"[\W_]+", "", value.casefold())

    def _extract_leading_emoji(self, value: str) -> tuple[str, str]:
        stripped = (value or "").strip()
        if not stripped:
            return "", ""
        match = re.match(r"^([^\w\s]+)\s*(.*)$", stripped, flags=re.UNICODE)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        return "", stripped

    def _build_period_bullets(self, items: list[str], summary_text: str) -> list[dict[str, str]]:
        source_items = items or []
        if not source_items and summary_text:
            source_items = [part.strip() for part in re.split(r"\s+[—–-]\s+", summary_text) if part.strip()]

        bullets: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in source_items:
            icon, text = self._extract_leading_emoji(item)
            normalized = self._normalize_narrative_text(text)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            bullets.append({
                "icon": icon or "•",
                "text": text,
            })
        return bullets

    def _dedupe_period_items(self, summary_text: str, items: list[str]) -> list[str]:
        normalized_summary = self._normalize_narrative_text(summary_text)
        unique_items: list[str] = []
        seen: set[str] = set()
        duplicated_count = 0

        for item in items:
            normalized_item = self._normalize_narrative_text(item)
            if not normalized_item or normalized_item in seen:
                continue
            seen.add(normalized_item)
            if normalized_item in normalized_summary:
                duplicated_count += 1
                continue
            unique_items.append(item)

        if items and duplicated_count / max(len(items), 1) >= 0.6:
            return []
        return unique_items

    def normalize_filters(self, args: Any) -> dict[str, str | None]:
        country = self._clean_value(args.get("country"))
        region = self._clean_value(args.get("region"))
        search = self._clean_value(args.get("search"))
        period = self._clean_value(args.get("period"))
        return {"country": country, "region": region, "search": search, "period": period}

    def normalize_slug_list(self, values: Iterable[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for value in values:
            slug = self._clean_value(value)
            if slug and slug not in seen:
                seen.add(slug)
                cleaned.append(slug)
        return cleaned[:6]

    def get_filter_options(self) -> dict[str, list[str]]:
        connection = get_db()
        countries = [row[0] for row in connection.execute(
            "SELECT DISTINCT country FROM dim_city WHERE country IS NOT NULL ORDER BY country"
        )]
        regions = [row[0] for row in connection.execute(
            "SELECT DISTINCT region FROM dim_city WHERE region IS NOT NULL ORDER BY region"
        )]
        periods = [row[0] for row in connection.execute(
            "SELECT DISTINCT period_label FROM dim_time WHERE period_label IS NOT NULL"
        )]
        periods = [label for label in PERIOD_ORDER if label in periods]
        return {"countries": countries, "regions": regions, "periods": periods}

    def get_city_options(self) -> list[dict[str, str]]:
        connection = get_db()
        rows = connection.execute(
            "SELECT city_name, city_slug, country, region FROM dim_city ORDER BY city_name"
        ).fetchall()
        return [dict(row) for row in rows]

    def get_dashboard_metrics(self, filters: dict[str, str | None]) -> dict[str, Any]:
        connection = get_db()
        filtered_analysis_sql = self._filtered_analysis_cte(filters)
        filtered_params = self._analysis_filter_params(filters)
        counts = connection.execute(
            f"""
            WITH {filtered_analysis_sql}
            SELECT COUNT(DISTINCT city_slug) AS city_count, COUNT(DISTINCT country) AS country_count
            FROM filtered_analysis
            """,
            filtered_params,
        ).fetchone()

        summary = connection.execute(
            f"""
            WITH {filtered_analysis_sql},
            latest_year AS (
                SELECT city_slug, MAX(year) AS year
                FROM filtered_analysis
                GROUP BY city_slug
            )
            SELECT
                COUNT(*) AS latest_city_count,
                SUM(v.population) AS total_population,
                AVG(v.population) AS avg_population,
                MAX(v.year) AS latest_year
            FROM filtered_analysis v
            INNER JOIN latest_year ly
                ON ly.city_slug = v.city_slug
               AND ly.year = v.year
            """,
            filtered_params,
        ).fetchone()

        return {
            "city_count": counts["city_count"] or 0,
            "country_count": counts["country_count"] or 0,
            "latest_city_count": summary["latest_city_count"] or 0,
            "total_population": summary["total_population"] or 0,
            "avg_population": round(summary["avg_population"] or 0),
            "latest_year": summary["latest_year"] or "n/a",
        }

    def get_growth_leaders(self, filters: dict[str, str | None]) -> list[dict[str, Any]]:
        connection = get_db()
        rows = connection.execute(
            f"""
            SELECT growth.city_name, growth.decade, growth.absolute_growth, growth.growth_pct, growth.country, city.region
            FROM vw_city_growth_by_decade growth
            INNER JOIN dim_city city
                ON city.city_id = growth.city_id
            WHERE growth_pct IS NOT NULL {self._growth_filter_sql(filters)}
            ORDER BY growth_pct DESC, absolute_growth DESC
            LIMIT 8
            """,
            self._growth_filter_params(filters),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_peak_cities(self, filters: dict[str, str | None]) -> list[dict[str, Any]]:
        connection = get_db()
        rows = connection.execute(
            f"""
            SELECT city.city_slug, peak.city_name, peak.peak_year, peak.peak_population, peak.country, peak.region
            FROM vw_city_peak_population peak
            INNER JOIN dim_city city
                ON city.city_id = peak.city_id
            WHERE 1 = 1 {self._peak_filter_sql(filters, alias='peak')}
            ORDER BY peak_population DESC
            LIMIT 8
            """,
            self._peak_filter_params(filters),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_decline_cities(self, filters: dict[str, str | None]) -> list[dict[str, Any]]:
        connection = get_db()
        rows = connection.execute(
            f"""
            SELECT decline.city_name, city.region, decline.country, decline.previous_year AS start_year,
                   decline.current_year AS end_year, decline.absolute_change AS population_change
            FROM vw_city_decline_periods decline
            INNER JOIN dim_city city
                ON city.city_id = decline.city_id
            WHERE 1 = 1 {self._decline_filter_sql(filters)}
            ORDER BY decline.absolute_change ASC
            LIMIT 8
            """,
            self._decline_filter_params(filters),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_decline_leader_cities(self, filters: dict[str, str | None]) -> list[dict[str, Any]]:
        connection = get_db()
        filtered_analysis_sql = self._filtered_analysis_cte(filters)
        rows = connection.execute(
            f"""
            WITH {filtered_analysis_sql},
            latest_year AS (
                SELECT city_slug, MAX(year) AS year
                FROM filtered_analysis
                GROUP BY city_slug
            )
            SELECT
                v.city_name,
                v.city_slug,
                v.country,
                city.region,
                peak.peak_year,
                peak.peak_population,
                v.population AS current_population,
                v.year AS current_year,
                ROUND(((v.population - peak.peak_population) * 100.0) / peak.peak_population, 1) AS decline_pct
            FROM filtered_analysis v
            INNER JOIN latest_year ly
                ON ly.city_slug = v.city_slug
               AND ly.year = v.year
            INNER JOIN dim_city city
                ON city.city_id = v.city_id
            INNER JOIN vw_city_peak_population peak
                ON peak.city_id = v.city_id
            WHERE v.population < peak.peak_population
            ORDER BY decline_pct ASC
            LIMIT 8
            """,
            self._analysis_filter_params(filters),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_dashboard_chart_payload(self, filters: dict[str, str | None]) -> dict[str, Any]:
        connection = get_db()
        filtered_analysis_sql = self._filtered_analysis_cte(filters)
        rows = connection.execute(
            f"""
            WITH {filtered_analysis_sql},
            latest_year AS (
                SELECT city_slug, MAX(year) AS year
                FROM filtered_analysis
                GROUP BY city_slug
            )
            SELECT v.city_name, v.city_slug, v.city_color, v.population
            FROM filtered_analysis v
            INNER JOIN latest_year ly
                ON ly.city_slug = v.city_slug
               AND ly.year = v.year
            ORDER BY v.population DESC
            LIMIT 10
            """,
            self._analysis_filter_params(filters),
        ).fetchall()

        return {
            "topPopulations": {
                "labels": [row["city_name"] for row in rows],
                "datasets": [
                    {
                        "label": "Population la plus récente",
                        "data": [row["population"] for row in rows],
                        "backgroundColor": [row["city_color"] or "#2f6fed" for row in rows],
                    }
                ],
            }
        }

    def get_map_payload(self, filters: dict[str, str | None]) -> dict[str, Any]:
        connection = get_db()
        rows = connection.execute(
            f"""
            WITH {self._filtered_analysis_cte(filters)},
            latest_year AS (
                SELECT city_slug, MAX(year) AS year
                FROM filtered_analysis
                GROUP BY city_slug
            ),
            latest_growth AS (
                SELECT growth.city_id, growth.decade, growth.growth_pct,
                       ROW_NUMBER() OVER (PARTITION BY growth.city_id ORDER BY growth.decade DESC) AS rn
                FROM vw_city_growth_by_decade growth
            ),
            decline_rollup AS (
                SELECT city_id, COUNT(*) AS decline_count, MIN(change_pct) AS deepest_decline_pct
                FROM vw_city_decline_periods
                GROUP BY city_id
            ),
            annotation_rollup AS (
                SELECT city_id,
                       COUNT(*) AS annotation_count,
                       GROUP_CONCAT(CAST(year AS TEXT) || '|' || annotation_label || '|' || annotation_color, '||') AS annotation_preview
                FROM vw_annotated_events_by_period
                WHERE 1 = 1 {self._analysis_filter_sql(filters, alias=None, include_city=True)}
                GROUP BY city_id
            )
            SELECT
                latest.city_name,
                latest.city_slug,
                latest.country,
                latest.region,
                latest.city_color,
                latest.population,
                latest.year,
                peak.peak_population,
                peak.peak_year,
                growth.decade AS latest_growth_decade,
                growth.growth_pct AS latest_growth_pct,
                decline.decline_count,
                decline.deepest_decline_pct,
                annotation.annotation_count,
                annotation.annotation_preview
            FROM filtered_analysis latest
            INNER JOIN latest_year ly
                ON ly.city_slug = latest.city_slug
               AND ly.year = latest.year
            LEFT JOIN vw_city_peak_population peak
                ON peak.city_id = latest.city_id
            LEFT JOIN latest_growth growth
                ON growth.city_id = latest.city_id
               AND growth.rn = 1
            LEFT JOIN decline_rollup decline
                ON decline.city_id = latest.city_id
            LEFT JOIN annotation_rollup annotation
                ON annotation.city_id = latest.city_id
            ORDER BY latest.population DESC
            """,
            self._analysis_filter_params(filters) + self._analysis_filter_params(filters),
        ).fetchall()

        points: list[dict[str, Any]] = []
        missing: list[str] = []
        max_population = max((row["population"] or 0 for row in rows), default=0)

        for row in rows:
            coordinates = CITY_COORDINATES.get(row["city_slug"])
            if coordinates is None:
                missing.append(row["city_slug"])
                continue
            population = row["population"] or 0
            radius = 8
            if max_population > 0:
                radius = max(8, min(28, round(8 + (population / max_population) * 20)))
            annotation_preview: list[dict[str, Any]] = []
            if row["annotation_preview"]:
                for item in str(row["annotation_preview"]).split("||")[:6]:
                    parts = item.split("|", 2)
                    if len(parts) == 3:
                        annotation_preview.append(
                            {"year": parts[0], "label": parts[1], "color": parts[2]}
                        )
            points.append(
                {
                    "city_name": row["city_name"],
                    "city_slug": row["city_slug"],
                    "country": row["country"],
                    "region": row["region"],
                    "city_color": row["city_color"] or "#2f6fed",
                    "population": population,
                    "year": row["year"],
                    "peak_population": row["peak_population"],
                    "peak_year": row["peak_year"],
                    "latest_growth_decade": row["latest_growth_decade"],
                    "latest_growth_pct": row["latest_growth_pct"],
                    "decline_count": row["decline_count"] or 0,
                    "deepest_decline_pct": row["deepest_decline_pct"],
                    "annotation_count": row["annotation_count"] or 0,
                    "annotations": annotation_preview,
                    "lat": coordinates["lat"],
                    "lng": coordinates["lng"],
                    "radius": radius,
                }
            )

        return {
            "points": points,
            "mapped_count": len(points),
            "missing_count": len(missing),
            "top_points": points[:12],
        }

    def get_city_directory(self, filters: dict[str, str | None]) -> list[dict[str, Any]]:
        connection = get_db()
        filtered_analysis_sql = self._filtered_analysis_cte(filters)
        rows = connection.execute(
            f"""
            WITH {filtered_analysis_sql},
            latest_year AS (
                SELECT city_slug, MAX(year) AS year
                FROM filtered_analysis
                GROUP BY city_slug
            ),
            first_population AS (
                SELECT city_id, year AS first_population_year, population AS first_population
                FROM (
                    SELECT city_id, year, population,
                           ROW_NUMBER() OVER (PARTITION BY city_id ORDER BY year ASC) AS rn
                    FROM fact_city_population
                ) ranked
                WHERE rn = 1
            ),
            decline_rollup AS (
                SELECT city_id, COUNT(*) AS decline_count, MAX(current_year) AS latest_decline_year
                FROM vw_city_decline_periods
                GROUP BY city_id
            ),
            rebound_rollup AS (
                SELECT city_id, COUNT(*) AS rebound_count, MAX(current_year) AS latest_rebound_year
                FROM vw_city_rebound_periods
                GROUP BY city_id
            )
            SELECT
                v.city_id,
                v.city_name,
                v.city_slug,
                v.country,
                v.region,
                v.city_color,
                v.population,
                v.year,
                peak.peak_population,
                peak.peak_year,
                first_population.first_population_year,
                first_population.first_population,
                decline.decline_count,
                decline.latest_decline_year,
                rebound.rebound_count,
                rebound.latest_rebound_year
            FROM filtered_analysis v
            INNER JOIN latest_year ly
                ON ly.city_slug = v.city_slug
               AND ly.year = v.year
            LEFT JOIN vw_city_peak_population peak
                ON peak.city_id = v.city_id
            LEFT JOIN first_population
                ON first_population.city_id = v.city_id
            LEFT JOIN decline_rollup decline
                ON decline.city_id = v.city_id
            LEFT JOIN rebound_rollup rebound
                ON rebound.city_id = v.city_id
            ORDER BY v.city_name
            """,
            self._analysis_filter_params(filters),
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            record = dict(row)
            foundation = _get_city_origin_metadata(record["city_slug"])
            record.update(foundation)
            latest_decline_year = record.get("latest_decline_year")
            latest_rebound_year = record.get("latest_rebound_year")
            decline_count = record.get("decline_count") or 0
            rebound_count = record.get("rebound_count") or 0
            if latest_rebound_year and (not latest_decline_year or latest_rebound_year >= latest_decline_year):
                record["trend_label"] = "En croissance"
            elif decline_count:
                record["trend_label"] = "En décroissance"
            elif rebound_count:
                record["trend_label"] = "En croissance"
            else:
                record["trend_label"] = "Stable"
            record.update(get_city_photo(record["city_slug"]))
            result.append(record)
        return result

    def get_city_detail(self, city_slug: str, filters: dict[str, str | None]) -> dict[str, Any] | None:
        connection = get_db()
        detail_filters = dict(filters)
        row = connection.execute(
            f"""
            WITH {self._filtered_analysis_cte(detail_filters)},
            latest_year AS (
                SELECT city_slug, MAX(year) AS year
                FROM filtered_analysis
                WHERE city_slug = ?
                GROUP BY city_slug
            ),
            first_population AS (
                SELECT city_id, year AS first_population_year, population AS first_population
                FROM (
                    SELECT city_id, year, population,
                           ROW_NUMBER() OVER (PARTITION BY city_id ORDER BY year ASC) AS rn
                    FROM fact_city_population
                ) ranked
                WHERE rn = 1
            ),
            decline_rollup AS (
                SELECT city_id, COUNT(*) AS decline_count, MAX(current_year) AS latest_decline_year
                FROM vw_city_decline_periods
                GROUP BY city_id
            ),
            rebound_rollup AS (
                SELECT city_id, COUNT(*) AS rebound_count, MAX(current_year) AS latest_rebound_year
                FROM vw_city_rebound_periods
                GROUP BY city_id
            )
            SELECT
                v.city_id,
                v.city_name,
                v.city_slug,
                v.country,
                v.region,
                v.city_color,
                v.population AS latest_population,
                v.year AS latest_year,
                peak.peak_population,
                peak.peak_year,
                first_population.first_population_year,
                first_population.first_population,
                decline.decline_count,
                decline.latest_decline_year,
                rebound.rebound_count,
                rebound.latest_rebound_year
            FROM filtered_analysis v
            INNER JOIN latest_year ly
                ON ly.city_slug = v.city_slug
               AND ly.year = v.year
            LEFT JOIN vw_city_peak_population peak
                ON peak.city_id = v.city_id
            LEFT JOIN first_population
                ON first_population.city_id = v.city_id
            LEFT JOIN decline_rollup decline
                ON decline.city_id = v.city_id
            LEFT JOIN rebound_rollup rebound
                ON rebound.city_id = v.city_id
            """,
            self._analysis_filter_params(detail_filters) + [city_slug],
        ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record.update(_get_city_origin_metadata(record["city_slug"]))
        latest_decline_year = record.get("latest_decline_year")
        latest_rebound_year = record.get("latest_rebound_year")
        decline_count = record.get("decline_count") or 0
        rebound_count = record.get("rebound_count") or 0
        if latest_rebound_year and (not latest_decline_year or latest_rebound_year >= latest_decline_year):
            record["trend_label"] = "En croissance"
            record["trend_symbol"] = "▲"
        elif decline_count:
            record["trend_label"] = "En décroissance"
            record["trend_symbol"] = "▼"
        elif rebound_count:
            record["trend_label"] = "En croissance"
            record["trend_symbol"] = "▲"
        else:
            record["trend_label"] = "Stable"
            record["trend_symbol"] = "•"
        record.update(get_city_photo(record["city_slug"]))
        return record

    def get_city_periods(self, city_slug: str, filters: dict[str, str | None]) -> list[dict[str, Any]]:
        connection = get_db()
        params: list[Any] = [city_slug]
        period_sql = ""
        if filters.get("period"):
            period_sql = "AND ? IN (start_period_label, end_period_label)"
            params.append(filters["period"])
        rows = connection.execute(
            f"""
            SELECT *
            FROM vw_city_period_detail_with_annotations
            WHERE city_slug = ?
              {period_sql}
            ORDER BY period_order
            """,
            params,
        ).fetchall()
        items = connection.execute(
            """
            SELECT pd.period_detail_id, item.item_order, item.item_text
            FROM dim_city_period_detail_item item
            INNER JOIN dim_city_period_detail pd
                ON pd.period_detail_id = item.period_detail_id
            INNER JOIN dim_city city
                ON city.city_id = pd.city_id
            WHERE city.city_slug = ?
            ORDER BY pd.period_order, item.item_order
            """,
            (city_slug,),
        ).fetchall()
        item_map: dict[int, list[str]] = defaultdict(list)
        for item in items:
            item_map[item["period_detail_id"]].append(item["item_text"])

        period_annotations = connection.execute(
            """
            SELECT
                pd.period_detail_id,
                f.year,
                da.annotation_label,
                da.annotation_color,
                da.annotation_type
            FROM dim_city_period_detail pd
            INNER JOIN dim_city city
                ON city.city_id = pd.city_id
            INNER JOIN fact_city_population f
                ON f.city_id = pd.city_id
               AND f.annotation_id IS NOT NULL
            INNER JOIN dim_annotation da
                ON da.annotation_id = f.annotation_id
            LEFT JOIN vw_city_period_detail_with_annotations pop
                ON pop.period_detail_id = pd.period_detail_id
            WHERE city.city_slug = ?
              AND pop.annotation_window_start IS NOT NULL
              AND pop.annotation_window_end IS NOT NULL
              AND f.year BETWEEN pop.annotation_window_start AND pop.annotation_window_end
            ORDER BY pd.period_order, f.year
            """,
            (city_slug,),
        ).fetchall()
        annotation_map: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for annotation in period_annotations:
            annotation_map[annotation["period_detail_id"]].append(
                {
                    "year": annotation["year"],
                    "label": annotation["annotation_label"],
                    "color": annotation["annotation_color"],
                    "type": annotation["annotation_type"],
                }
            )

        result: list[dict[str, Any]] = []
        for row in rows:
            record = dict(row)
            record["items"] = item_map.get(record["period_detail_id"], [])
            record["display_items"] = self._dedupe_period_items(record["summary_text"], record["items"])
            record["display_bullets"] = self._build_period_bullets(record["items"], record["summary_text"])
            record["condensed_items_count"] = max(0, len(record["items"]) - len(record["display_items"]))
            record["linked_annotations"] = annotation_map.get(record["period_detail_id"], [])
            result.append(record)
        return result

    def get_city_annotations(self, city_slug: str, filters: dict[str, str | None]) -> list[dict[str, Any]]:
        connection = get_db()
        rows = connection.execute(
            f"""
            SELECT year, annotation_label, annotation_color, annotation_type
            FROM vw_city_population_analysis
            WHERE city_slug = ?
              AND annotation_label IS NOT NULL
              {self._analysis_filter_sql(filters, alias=None, include_city=False)}
            ORDER BY year
            """,
            [city_slug] + self._analysis_filter_params(filters, include_city=False),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_city_chart_payload(self, city_slug: str, filters: dict[str, str | None]) -> dict[str, Any]:
        connection = get_db()
        rows = connection.execute(
            f"""
            SELECT year, population, city_name, city_color
            FROM vw_city_population_analysis
            WHERE city_slug = ?
              {self._analysis_filter_sql(filters, alias=None, include_city=False)}
            ORDER BY year
            """,
            [city_slug] + self._analysis_filter_params(filters, include_city=False),
        ).fetchall()
        if not rows:
            return {"timeline": {"labels": [], "datasets": []}}

        annotations = self.get_city_annotations(city_slug, filters)
        labels = [row["year"] for row in rows]
        indexed_annotations: list[dict[str, Any]] = []
        default_band_width = 2
        if len(labels) > 1:
            default_band_width = max(1, round((labels[1] - labels[0]) / 4))

        for index, annotation in enumerate(annotations):
            year = annotation["year"]
            indexed_annotations.append(
                {
                    "id": f"annotation-{index}",
                    "year": year,
                    "label": annotation["annotation_label"],
                    "color": annotation["annotation_color"] or "#ef6c3d",
                    "type": annotation["annotation_type"],
                    "xMin": year - default_band_width,
                    "xMax": year + default_band_width,
                }
            )

        return {
            "timeline": {
                "labels": labels,
                "datasets": [
                    {
                        "label": rows[0]["city_name"],
                        "data": [row["population"] for row in rows],
                        "borderColor": rows[0]["city_color"] or "#2f6fed",
                        "backgroundColor": "rgba(47, 111, 237, 0.18)",
                        "fill": True,
                    }
                ],
                "annotations": indexed_annotations,
            }
        }

    def get_compare_overview(self, selected_slugs: Sequence[str], filters: dict[str, str | None]) -> list[dict[str, Any]]:
        if not selected_slugs:
            return []
        placeholders = ", ".join("?" for _ in selected_slugs)
        connection = get_db()
        rows = connection.execute(
            f"""
            WITH {self._filtered_analysis_cte(filters)},
            latest_year AS (
                SELECT city_slug, MAX(year) AS year
                FROM filtered_analysis
                WHERE city_slug IN ({placeholders})
                GROUP BY city_slug
            )
            SELECT v.city_name, v.city_slug, v.country, v.region, v.population, v.year, peak.peak_population, peak.peak_year
            FROM filtered_analysis v
            INNER JOIN latest_year ly
                ON ly.city_slug = v.city_slug
               AND ly.year = v.year
            LEFT JOIN vw_city_peak_population peak
                ON peak.city_id = v.city_id
            WHERE v.city_slug IN ({placeholders})
            ORDER BY v.population DESC
            """,
            tuple(self._analysis_filter_params(filters)) + tuple(selected_slugs) + tuple(selected_slugs),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_compare_chart_payload(self, selected_slugs: Sequence[str], filters: dict[str, str | None]) -> dict[str, Any]:
        if not selected_slugs:
            return {"comparison": {"labels": [], "datasets": []}}

        placeholders = ", ".join("?" for _ in selected_slugs)
        connection = get_db()
        rows = connection.execute(
            f"""
            WITH {self._filtered_analysis_cte(filters)}
            SELECT city_slug, city_name, year, population, city_color
            FROM filtered_analysis
            WHERE city_slug IN ({placeholders})
            ORDER BY year, city_name
            """,
            tuple(self._analysis_filter_params(filters)) + tuple(selected_slugs),
        ).fetchall()

        labels = sorted({row["year"] for row in rows})
        series: dict[str, dict[str, Any]] = {}
        for row in rows:
            city = series.setdefault(
                row["city_slug"],
                {
                    "label": row["city_name"],
                    "borderColor": row["city_color"] or "#2f6fed",
                    "backgroundColor": "transparent",
                    "points": {},
                },
            )
            city["points"][row["year"]] = row["population"]

        datasets = []
        for slug in selected_slugs:
            city = series.get(slug)
            if city is None:
                continue
            datasets.append(
                {
                    "label": city["label"],
                    "borderColor": city["borderColor"],
                    "backgroundColor": city["backgroundColor"],
                    "data": [city["points"].get(year) for year in labels],
                    "fill": False,
                }
            )

        return {"comparison": {"labels": labels, "datasets": datasets}}

    def execute_sql(self, sql: str, *, confirm_write: bool) -> dict[str, Any]:
        try:
            result = self._run_sql(sql, confirm_write=confirm_write, row_limit=current_app.config["SQL_QUERY_LIMIT"])
        except SqlExecutionError:
            self._append_sql_history(sql, action="execute", status="error")
            raise
        self._append_sql_history(sql, action="execute", status=result["kind"])
        return result

    def export_sql_csv(self, sql: str) -> tuple[str, str]:
        try:
            result = self._run_sql(sql, confirm_write=False, row_limit=current_app.config["SQL_EXPORT_LIMIT"], export_mode=True)
        except SqlExecutionError:
            self._append_sql_history(sql, action="export", status="error")
            raise
        first_result = result["results"][0]
        columns = first_result["columns"]
        rows = first_result["rows"]
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([row.get(column) for column in columns])
        self._append_sql_history(sql, action="export", status="csv")
        return buffer.getvalue(), first_result["statement"]

    def get_sql_history(self) -> list[dict[str, str]]:
        history_path = self._sql_history_path()
        if not history_path.exists():
            return []
        try:
            data = json.loads(history_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        entries = [entry for entry in data if isinstance(entry, dict)]
        return entries[: current_app.config["SQL_HISTORY_LIMIT"]]

    def get_saved_views(self) -> list[dict[str, str]]:
        views_path = self._saved_views_path()
        if not views_path.exists():
            return []
        try:
            data = json.loads(views_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        entries = [entry for entry in data if isinstance(entry, dict)]
        return entries[: current_app.config["SAVED_VIEWS_LIMIT"]]

    def save_sql_view(self, name: str, description: str, sql: str) -> None:
        cleaned_sql = sql.strip()
        cleaned_name = name.strip()
        if not cleaned_name:
            raise SqlExecutionError("Nom de vue requis pour la sauvegarde.")
        if not cleaned_sql:
            raise SqlExecutionError("Requête SQL vide: rien à sauvegarder.")
        views_path = self._saved_views_path()
        views_path.parent.mkdir(parents=True, exist_ok=True)
        existing = self.get_saved_views()
        entry = {
            "id": uuid.uuid4().hex[:10],
            "name": cleaned_name,
            "description": description.strip(),
            "sql": cleaned_sql,
            "created_at": datetime.now(UTC).isoformat(),
        }
        updated = [entry] + [item for item in existing if item.get("name") != cleaned_name]
        updated = updated[: current_app.config["SAVED_VIEWS_LIMIT"]]
        views_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")

    def delete_sql_view(self, view_id: str) -> None:
        views_path = self._saved_views_path()
        existing = self.get_saved_views()
        filtered = [item for item in existing if item.get("id") != view_id]
        views_path.parent.mkdir(parents=True, exist_ok=True)
        views_path.write_text(json.dumps(filtered, ensure_ascii=False, indent=2), encoding="utf-8")

    def clear_sql_history(self) -> None:
        history_path = self._sql_history_path()
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text("[]", encoding="utf-8")

    def get_sql_examples(self) -> list[dict[str, str]]:
        return [
            {
                "label": "Villes canadiennes par population récente",
                "sql": "SELECT city_name, year, population\nFROM vw_city_population_analysis\nWHERE country = 'Canada'\nORDER BY year DESC, population DESC\nLIMIT 25;",
            },
            {
                "label": "Croissance par décennie",
                "sql": "SELECT city_name, decade, absolute_growth, growth_pct\nFROM vw_city_growth_by_decade\nORDER BY growth_pct DESC\nLIMIT 25;",
            },
            {
                "label": "Périodes détaillées enrichies",
                "sql": "SELECT city_name, period_range_label, period_title, start_population, end_population, population_change_pct\nFROM vw_city_period_detail_with_population\nORDER BY city_name, period_order\nLIMIT 25;",
            },
        ]

    def _build_city_filter_clause(self, filters: dict[str, str | None]) -> tuple[str, list[Any]]:
        clause_parts: list[str] = []
        params: list[Any] = []
        if filters.get("country"):
            clause_parts.append("AND country = ?")
            params.append(filters["country"])
        if filters.get("region"):
            clause_parts.append("AND region = ?")
            params.append(filters["region"])
        if filters.get("search"):
            clause_parts.append("AND city_name LIKE ?")
            params.append(f"%{filters['search']}%")
        return " ".join(clause_parts), params

    def _analysis_filter_sql(
        self,
        filters: dict[str, str | None],
        *,
        alias: str | None = None,
        include_city: bool = True,
    ) -> str:
        parts: list[str] = []
        prefix = f"{alias}." if alias else ""
        if filters.get("country"):
            parts.append(f"AND {prefix}country = ?")
        if filters.get("region"):
            parts.append(f"AND {prefix}region = ?")
        if include_city and filters.get("search"):
            parts.append(f"AND {prefix}city_name LIKE ?")
        if filters.get("period"):
            parts.append(f"AND {prefix}period_label = ?")
        return " ".join(parts)

    def _analysis_filter_params(self, filters: dict[str, str | None], *, include_city: bool = True) -> list[Any]:
        params: list[Any] = []
        if filters.get("country"):
            params.append(filters["country"])
        if filters.get("region"):
            params.append(filters["region"])
        if include_city and filters.get("search"):
            params.append(f"%{filters['search']}%")
        if filters.get("period"):
            params.append(filters["period"])
        return params

    def _peak_filter_sql(self, filters: dict[str, str | None], *, alias: str | None = None) -> str:
        return self._analysis_filter_sql(filters, alias=alias)

    def _peak_filter_params(self, filters: dict[str, str | None]) -> list[Any]:
        return self._analysis_filter_params(filters)

    def _growth_filter_sql(self, filters: dict[str, str | None]) -> str:
        parts: list[str] = []
        if filters.get("country"):
            parts.append("AND growth.country = ?")
        if filters.get("region"):
            parts.append("AND city.region = ?")
        if filters.get("search"):
            parts.append("AND growth.city_name LIKE ?")
        if filters.get("period"):
            parts.append("AND " + self._period_year_condition("growth.end_year"))
        return " ".join(parts)

    def _growth_filter_params(self, filters: dict[str, str | None]) -> list[Any]:
        params: list[Any] = []
        if filters.get("country"):
            params.append(filters["country"])
        if filters.get("region"):
            params.append(filters["region"])
        if filters.get("search"):
            params.append(f"%{filters['search']}%")
        if filters.get("period"):
            params.extend(self._period_year_params(filters["period"]))
        return params

    def _decline_filter_sql(self, filters: dict[str, str | None]) -> str:
        parts: list[str] = []
        if filters.get("country"):
            parts.append("AND decline.country = ?")
        if filters.get("region"):
            parts.append("AND city.region = ?")
        if filters.get("search"):
            parts.append("AND decline.city_name LIKE ?")
        if filters.get("period"):
            parts.append("AND " + self._period_year_condition("decline.current_year"))
        return " ".join(parts)

    def _decline_filter_params(self, filters: dict[str, str | None]) -> list[Any]:
        params: list[Any] = []
        if filters.get("country"):
            params.append(filters["country"])
        if filters.get("region"):
            params.append(filters["region"])
        if filters.get("search"):
            params.append(f"%{filters['search']}%")
        if filters.get("period"):
            params.extend(self._period_year_params(filters["period"]))
        return params

    def _filtered_analysis_cte(self, filters: dict[str, str | None]) -> str:
        return f"filtered_analysis AS (SELECT * FROM vw_city_population_analysis WHERE 1 = 1 {self._analysis_filter_sql(filters)})"

    def _period_year_condition(self, year_expression: str) -> str:
        return (
            f"CASE "
            f"WHEN ? = 'Pré-industriel' THEN {year_expression} < 1850 "
            f"WHEN ? = 'Industrialisation' THEN {year_expression} >= 1850 AND {year_expression} < 1945 "
            f"WHEN ? = 'Après-guerre' THEN {year_expression} >= 1945 AND {year_expression} < 1975 "
            f"WHEN ? = 'Suburbanisation' THEN {year_expression} >= 1975 AND {year_expression} < 2000 "
            f"WHEN ? = 'Ère contemporaine' THEN {year_expression} >= 2000 "
            f"ELSE 1 END"
        )

    def _period_year_params(self, period: str) -> list[str]:
        return [period, period, period, period, period]

    def _append_sql_history(self, sql: str, *, action: str, status: str) -> None:
        cleaned_sql = sql.strip()
        if not cleaned_sql:
            return
        history_path = self._sql_history_path()
        history_path.parent.mkdir(parents=True, exist_ok=True)
        entries = self.get_sql_history()
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "action": action,
            "status": status,
            "sql": cleaned_sql,
            "preview": cleaned_sql.splitlines()[0][:120],
        }
        deduped = [item for item in entries if item.get("sql") != cleaned_sql or item.get("action") != action]
        history = [entry] + deduped
        history = history[: current_app.config["SQL_HISTORY_LIMIT"]]
        history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    def _sql_history_path(self) -> Path:
        return Path(current_app.config["SQL_HISTORY_PATH"])

    def _saved_views_path(self) -> Path:
        return Path(current_app.config["SAVED_VIEWS_PATH"])

    def _run_sql(
        self,
        sql: str,
        *,
        confirm_write: bool,
        row_limit: int,
        export_mode: bool = False,
    ) -> dict[str, Any]:
        statements = [statement.strip() for statement in sql.split(";") if statement.strip()]
        if not statements:
            raise SqlExecutionError("Aucune requête SQL fournie.")

        if len(statements) > current_app.config["SQL_STATEMENT_LIMIT"]:
            raise SqlExecutionError("Trop d'instructions SQL dans une seule exécution.")

        if export_mode and len(statements) != 1:
            raise SqlExecutionError("L'export CSV accepte une seule instruction SELECT ou WITH.")

        connection = get_db()
        results: list[dict[str, Any]] = []
        overall_kind = "read"

        for statement in statements:
            kind = self._classify_statement(statement)
            if export_mode and kind != "read":
                raise SqlExecutionError("L'export CSV est limité aux requêtes en lecture.")
            if kind == "write":
                overall_kind = "write"
                if not current_app.config["SQL_ENABLE_WRITE"]:
                    raise SqlExecutionError("Le mode écriture SQL n'est pas activé. Définit PROJETCITY_SQL_ENABLE_WRITE=1 pour l'autoriser.")
                if not confirm_write:
                    raise SqlExecutionError("Confirme l'exécution en écriture avant de lancer cette requête.")

            try:
                cursor = connection.execute(statement)
            except sqlite3.Error as exc:
                connection.rollback()
                raise SqlExecutionError(f"Erreur SQLite: {exc}") from exc

            if cursor.description:
                rows = cursor.fetchmany(row_limit)
                columns = [column[0] for column in cursor.description]
                results.append(
                    {
                        "statement": statement,
                        "columns": columns,
                        "rows": [dict(zip(columns, row)) for row in rows],
                        "row_count": len(rows),
                    }
                )
            else:
                results.append(
                    {
                        "statement": statement,
                        "columns": [],
                        "rows": [],
                        "row_count": cursor.rowcount,
                    }
                )

        if overall_kind == "write":
            connection.commit()

        return {"kind": overall_kind, "results": results}

    def _classify_statement(self, statement: str) -> str:
        normalized = re.sub(r"^--.*$", "", statement, flags=re.MULTILINE).strip().lower()
        if not normalized:
            raise SqlExecutionError("Instruction SQL vide.")
        if normalized.startswith(READ_ONLY_PREFIXES):
            return "read"
        if normalized.startswith(WRITE_PREFIXES):
            return "write"
        raise SqlExecutionError("Type de requête non pris en charge dans SQL Lab.")

    def _clean_value(self, value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None