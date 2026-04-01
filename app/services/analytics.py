from __future__ import annotations

import csv
import io
import json
import uuid
import re
from collections import defaultdict
from datetime import datetime, UTC
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Sequence

from flask import current_app

from app.db import DatabaseError, get_db
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


def _get_city_origin_metadata(city_slug: str) -> dict[str, int | None]:
    # 0) Check dim_city.foundation_year first (AI-validated overrides)
    try:
        connection = get_db()
        db_row = connection.execute(
            "SELECT foundation_year FROM dim_city WHERE city_slug = ?",
            (city_slug,),
        ).fetchone()
        if db_row and db_row["foundation_year"]:
            return {"foundation_year": db_row["foundation_year"]}
    except Exception:
        pass

    # 1) Try period details text file
    details_path = Path(current_app.root_path).parent / "data" / "city_details" / f"{city_slug}.txt"
    if details_path.exists():
        source_text = details_path.read_text(encoding="utf-8")
        patterns = (
            r"(?:fond(?:ation|e|ée|é)|founded|established|incorporated|cr[eé]ation|na[iî]t).{0,80}?(1[5-9]\d{2}|20\d{2})",
            r"(1[5-9]\d{2}|20\d{2}).{0,80}?(?:fond(?:ation|e|ée|é)|founded|established|incorporated|cr[eé]ation|na[iî]t)",
        )
        for pattern in patterns:
            match = re.search(pattern, source_text, flags=re.IGNORECASE | re.DOTALL)
            if match:
                year = next((group for group in match.groups() if group), None)
                if year:
                    return {"foundation_year": int(year)}

    # 2) Try fiche complète in DB (looks for "Fondation" row in pipe tables or text)
    try:
        connection = get_db()
        row = connection.execute(
            """SELECT f.raw_text FROM dim_city_fiche f
               JOIN dim_city c ON c.city_id = f.city_id
               WHERE c.city_slug = ?""",
            (city_slug,),
        ).fetchone()
        if row:
            fiche_text = row[0]
            # Match pipe table row: | Fondation | 1837 |
            m = re.search(
                r"\|\s*(?:fond(?:ation|e|ée|é)|founded|established|incorporated)\s*\|\s*(1[5-9]\d{2}|20\d{2})\s*\|",
                fiche_text,
                flags=re.IGNORECASE,
            )
            if m:
                return {"foundation_year": int(m.group(1))}
            # Match plain text: Fondation : 1837 or Fondation	1837
            m = re.search(
                r"(?:fond(?:ation|e|ée|é)|founded|established|incorporated)\s*[:\t]\s*(1[5-9]\d{2}|20\d{2})",
                fiche_text,
                flags=re.IGNORECASE,
            )
            if m:
                return {"foundation_year": int(m.group(1))}
    except Exception:
        pass

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

    def normalize_filters(self, args: Any) -> dict[str, Any]:
        country = self._clean_value(args.get("country"))
        raw_regions = args.getlist("region") if hasattr(args, "getlist") else []
        regions = [r for r in (self._clean_value(v) for v in raw_regions) if r]
        search = self._clean_value(args.get("search"))
        period = self._clean_value(args.get("period"))
        return {"country": country, "region": regions, "search": search, "period": period}

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

        # Event count
        event_count_row = connection.execute(
            "SELECT COUNT(*) AS cnt FROM dim_event"
        ).fetchone()

        return {
            "city_count": counts["city_count"] or 0,
            "country_count": counts["country_count"] or 0,
            "latest_city_count": summary["latest_city_count"] or 0,
            "total_population": summary["total_population"] or 0,
            "avg_population": round(summary["avg_population"] or 0),
            "latest_year": summary["latest_year"] or "n/a",
            "event_count": event_count_row["cnt"] if event_count_row else 0,
        }

    def get_growth_leaders(self, filters: dict[str, str | None]) -> list[dict[str, Any]]:
        """Cities with the longest current consecutive growth streaks."""
        connection = get_db()
        filtered_analysis_sql = self._filtered_analysis_cte(filters)
        rows = connection.execute(
            f"""
            WITH {filtered_analysis_sql},
            pop_data AS (
                SELECT city_id, city_name, city_slug, country, year, population
                FROM filtered_analysis
            ),
            with_prev AS (
                SELECT *,
                    LAG(population) OVER (PARTITION BY city_id ORDER BY year) AS prev_pop
                FROM pop_data
            ),
            non_growth AS (
                SELECT city_id, year
                FROM with_prev
                WHERE prev_pop IS NOT NULL AND population <= prev_pop
            ),
            latest AS (
                SELECT city_id, MAX(year) AS latest_year
                FROM pop_data GROUP BY city_id
            ),
            last_stop AS (
                SELECT city_id, MAX(year) AS stop_year
                FROM non_growth GROUP BY city_id
            ),
            streaks AS (
                SELECT l.city_id, l.latest_year,
                    COALESCE(ls.stop_year,
                        (SELECT MIN(year) FROM pop_data pd WHERE pd.city_id = l.city_id)
                    ) AS growth_since
                FROM latest l
                LEFT JOIN last_stop ls ON ls.city_id = l.city_id
                WHERE l.latest_year > COALESCE(ls.stop_year, 0)
            )
            SELECT
                pd_start.city_name,
                pd_start.country,
                city.region,
                s.growth_since,
                pd_start.population AS start_population,
                pd_end.population AS current_population,
                ROUND(CAST(pd_end.population AS REAL) / pd_start.population, 1) AS growth_factor,
                ROUND(((pd_end.population - pd_start.population) * 100.0) / pd_start.population, 1) AS growth_pct
            FROM streaks s
            JOIN pop_data pd_start ON pd_start.city_id = s.city_id AND pd_start.year = s.growth_since
            JOIN pop_data pd_end ON pd_end.city_id = s.city_id AND pd_end.year = s.latest_year
            JOIN dim_city city ON city.city_id = s.city_id
            WHERE pd_start.population >= 1000
              AND pd_end.population > pd_start.population
              AND s.latest_year - s.growth_since >= 20
            ORDER BY growth_pct DESC
            LIMIT 8
            """,
            self._analysis_filter_params(filters),
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
            SELECT v.city_name, v.city_slug, v.city_color, v.population, v.country, v.region
            FROM filtered_analysis v
            INNER JOIN latest_year ly
                ON ly.city_slug = v.city_slug
               AND ly.year = v.year
            ORDER BY v.population DESC
            LIMIT 10
            """,
            self._analysis_filter_params(filters),
        ).fetchall()

        # Color by country, or by region if filtered to a single country
        if filters.get("country"):
            regions_seen: list[str] = []
            for row in rows:
                r = row["region"] or "Autre"
                if r not in regions_seen:
                    regions_seen.append(r)
            region_colors = {r: self._REGION_PALETTE[i % len(self._REGION_PALETTE)] for i, r in enumerate(regions_seen)}
            bar_colors = [region_colors.get(row["region"] or "Autre", "#999") for row in rows]
        else:
            bar_colors = [self._COUNTRY_COLORS.get(row["country"], "#999") for row in rows]

        return {
            "topPopulations": {
                "labels": [row["city_name"] for row in rows],
                "datasets": [
                    {
                        "label": "Population la plus récente",
                        "data": [row["population"] for row in rows],
                        "backgroundColor": bar_colors,
                    }
                ],
            },
            "popEvolution": self._pop_evolution(filters),
            "popEvolutionRegion": self._pop_evolution_by_region(filters),
            "cityCount": self._city_count_evolution(filters),
            "cityCountRegion": self._city_count_by_region(filters),
            "topPopByDecade": self._top_pop_by_decade(filters),
            "eventsByDecade": self._events_by_decade(),
        }

    # ── Dashboard chart helpers ──────────────────────────────────

    _COUNTRY_COLORS = {"Canada": "#d62728", "United States": "#1f77b4"}
    _REGION_PALETTE = [
        "#2f6fed", "#e45932", "#22c55e", "#f59e0b", "#8b5cf6",
        "#ec4899", "#06b6d4", "#84cc16", "#f97316", "#6366f1",
        "#14b8a6", "#ef4444",
    ]

    def _top_pop_by_decade(self, filters: dict) -> dict[str, Any]:
        conn = get_db()
        params = self._analysis_filter_params(filters)
        rows = conn.execute(
            f"""
            WITH {self._filtered_analysis_cte(filters)},
            decade_data AS (
                SELECT city_name, country, region,
                       (year / 10) * 10 AS decade,
                       MAX(population) AS max_pop
                FROM filtered_analysis
                GROUP BY city_name, country, region, (year / 10) * 10
            ),
            ranked AS (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY decade ORDER BY max_pop DESC) AS rn
                FROM decade_data
            )
            SELECT decade, city_name, country, region, max_pop
            FROM ranked
            WHERE rn = 1
            ORDER BY decade
            """,
            params,
        ).fetchall()

        if filters.get("country"):
            regions_seen: list[str] = []
            for r in rows:
                rg = r["region"] or "Autre"
                if rg not in regions_seen:
                    regions_seen.append(rg)
            region_colors = {rg: self._REGION_PALETTE[i % len(self._REGION_PALETTE)] for i, rg in enumerate(regions_seen)}
            bar_colors = [region_colors.get(r["region"] or "Autre", "#999") for r in rows]
        else:
            bar_colors = [self._COUNTRY_COLORS.get(r["country"], "#999") for r in rows]

        return {
            "labels": [f"{r['decade']}s" for r in rows],
            "datasets": [
                {
                    "label": "Ville la plus peuplée par décennie",
                    "data": [r["max_pop"] for r in rows],
                    "backgroundColor": bar_colors,
                    "cityNames": [r["city_name"] for r in rows],
                }
            ],
        }

    def _events_by_decade(self) -> dict[str, Any]:
        """Count events per decade, split by country (Canada vs United States)."""
        conn = get_db()
        rows = conn.execute(
            """
            SELECT (e.event_year / 10) * 10 AS decade,
                   el.country,
                   COUNT(DISTINCT e.event_id) AS cnt
            FROM dim_event e
            JOIN dim_event_location el ON el.event_id = e.event_id
            WHERE e.event_year IS NOT NULL AND el.country IS NOT NULL
            GROUP BY decade, el.country
            ORDER BY decade
            """
        ).fetchall()
        decades = sorted({r["decade"] for r in rows})
        by_country: dict[str, dict[int, int]] = {}
        for r in rows:
            by_country.setdefault(r["country"], {})[r["decade"]] = r["cnt"]
        datasets = []
        for country in ("Canada", "United States"):
            if country not in by_country:
                continue
            datasets.append({
                "label": country,
                "data": [by_country[country].get(d, 0) for d in decades],
                "backgroundColor": self._COUNTRY_COLORS.get(country, "#999"),
            })
        return {
            "labels": [f"{d}s" for d in decades],
            "datasets": datasets,
        }

    def _pop_pie_by_country(self, filters: dict[str, str | None]) -> dict[str, Any]:
        conn = get_db()
        rows = conn.execute(
            f"""
            WITH {self._filtered_analysis_cte(filters)},
            latest AS (
                SELECT city_slug, MAX(year) AS year
                FROM filtered_analysis GROUP BY city_slug
            )
            SELECT v.country, SUM(v.population) AS total
            FROM filtered_analysis v
            INNER JOIN latest l ON l.city_slug = v.city_slug AND l.year = v.year
            GROUP BY v.country
            ORDER BY total DESC
            """,
            self._analysis_filter_params(filters),
        ).fetchall()
        labels = [r["country"] for r in rows]
        data = [r["total"] for r in rows]
        colors = [self._COUNTRY_COLORS.get(c, "#999") for c in labels]
        return {
            "labels": labels,
            "datasets": [{"data": data, "backgroundColor": colors}],
        }

    def _pop_pie_by_region(self, filters: dict[str, str | None]) -> dict[str, Any]:
        conn = get_db()
        rows = conn.execute(
            f"""
            WITH {self._filtered_analysis_cte(filters)},
            latest AS (
                SELECT city_slug, MAX(year) AS year
                FROM filtered_analysis GROUP BY city_slug
            )
            SELECT v.region, SUM(v.population) AS total
            FROM filtered_analysis v
            INNER JOIN latest l ON l.city_slug = v.city_slug AND l.year = v.year
            WHERE v.region IS NOT NULL
            GROUP BY v.region
            ORDER BY total DESC
            """,
            self._analysis_filter_params(filters),
        ).fetchall()
        # Keep top 10, group rest as "Autres"
        top = rows[:10]
        rest_total = sum(r["total"] for r in rows[10:])
        labels = [r["region"] for r in top]
        data = [r["total"] for r in top]
        colors = list(self._REGION_PALETTE[: len(top)])
        if rest_total:
            labels.append("Autres")
            data.append(rest_total)
            colors.append("#9ca3af")
        return {
            "labels": labels,
            "datasets": [{"data": data, "backgroundColor": colors}],
        }

    def _pop_evolution(self, filters: dict[str, str | None]) -> dict[str, Any]:
        """Total aggregated population per decade, split by country."""
        conn = get_db()
        rows = conn.execute(
            f"""
            WITH {self._filtered_analysis_cte(filters)}
            SELECT v.country, dt.decade, SUM(v.population) AS total
            FROM filtered_analysis v
            INNER JOIN dim_time dt ON dt.year = v.year
            GROUP BY v.country, dt.decade
            ORDER BY dt.decade
            """,
            self._analysis_filter_params(filters),
        ).fetchall()
        decades = sorted({r["decade"] for r in rows})
        countries = sorted({r["country"] for r in rows})
        by_country: dict[str, dict[int, int]] = {c: {} for c in countries}
        for r in rows:
            by_country[r["country"]][r["decade"]] = r["total"]
        datasets = []
        for c in countries:
            datasets.append({
                "label": c,
                "data": [by_country[c].get(d, 0) for d in decades],
                "borderColor": self._COUNTRY_COLORS.get(c, "#999"),
                "backgroundColor": self._COUNTRY_COLORS.get(c, "#999") + "33",
                "fill": True,
                "tension": 0.3,
            })
        return {"labels": [str(d) for d in decades], "datasets": datasets}

    def _pop_evolution_by_region(self, filters: dict[str, str | None]) -> dict[str, Any]:
        """Total aggregated population per decade, split by region (top 10)."""
        conn = get_db()
        rows = conn.execute(
            f"""
            WITH {self._filtered_analysis_cte(filters)}
            SELECT v.region, dt.decade, SUM(v.population) AS total
            FROM filtered_analysis v
            INNER JOIN dim_time dt ON dt.year = v.year
            WHERE v.region IS NOT NULL
            GROUP BY v.region, dt.decade
            ORDER BY dt.decade
            """,
            self._analysis_filter_params(filters),
        ).fetchall()
        decades = sorted({r["decade"] for r in rows})
        totals_by_region: dict[str, int] = {}
        by_region: dict[str, dict[int, int]] = {}
        for r in rows:
            by_region.setdefault(r["region"], {})[r["decade"]] = r["total"]
            totals_by_region[r["region"]] = totals_by_region.get(r["region"], 0) + r["total"]
        top_regions = sorted(totals_by_region, key=totals_by_region.get, reverse=True)[:10]
        datasets = []
        for i, region in enumerate(top_regions):
            color = self._REGION_PALETTE[i % len(self._REGION_PALETTE)]
            datasets.append({
                "label": region,
                "data": [by_region[region].get(d, 0) for d in decades],
                "borderColor": color,
                "backgroundColor": color + "33",
                "fill": True,
                "tension": 0.3,
            })
        return {"labels": [str(d) for d in decades], "datasets": datasets}

    def _city_count_evolution(self, filters: dict[str, str | None]) -> dict[str, Any]:
        """Number of cities with data per decade, split by country."""
        conn = get_db()
        rows = conn.execute(
            f"""
            WITH {self._filtered_analysis_cte(filters)}
            SELECT v.country, dt.decade, COUNT(DISTINCT v.city_id) AS cnt
            FROM filtered_analysis v
            INNER JOIN dim_time dt ON dt.year = v.year
            GROUP BY v.country, dt.decade
            ORDER BY dt.decade
            """,
            self._analysis_filter_params(filters),
        ).fetchall()
        decades = sorted({r["decade"] for r in rows})
        countries = sorted({r["country"] for r in rows})
        by_country: dict[str, dict[int, int]] = {c: {} for c in countries}
        for r in rows:
            by_country[r["country"]][r["decade"]] = r["cnt"]
        datasets = []
        for c in countries:
            datasets.append({
                "label": c,
                "data": [by_country[c].get(d, 0) for d in decades],
                "borderColor": self._COUNTRY_COLORS.get(c, "#999"),
                "backgroundColor": self._COUNTRY_COLORS.get(c, "#999") + "33",
                "fill": True,
                "tension": 0.3,
            })
        return {"labels": [str(d) for d in decades], "datasets": datasets}

    def _city_count_by_region(self, filters: dict[str, str | None]) -> dict[str, Any]:
        """Number of cities with data per decade, split by region (top 10)."""
        conn = get_db()
        rows = conn.execute(
            f"""
            WITH {self._filtered_analysis_cte(filters)}
            SELECT v.region, dt.decade, COUNT(DISTINCT v.city_id) AS cnt
            FROM filtered_analysis v
            INNER JOIN dim_time dt ON dt.year = v.year
            WHERE v.region IS NOT NULL
            GROUP BY v.region, dt.decade
            ORDER BY dt.decade
            """,
            self._analysis_filter_params(filters),
        ).fetchall()
        decades = sorted({r["decade"] for r in rows})
        totals_by_region: dict[str, int] = {}
        by_region: dict[str, dict[int, int]] = {}
        for r in rows:
            by_region.setdefault(r["region"], {})[r["decade"]] = r["cnt"]
            totals_by_region[r["region"]] = totals_by_region.get(r["region"], 0) + r["cnt"]
        top_regions = sorted(totals_by_region, key=totals_by_region.get, reverse=True)[:10]
        datasets = []
        for i, region in enumerate(top_regions):
            color = self._REGION_PALETTE[i % len(self._REGION_PALETTE)]
            datasets.append({
                "label": region,
                "data": [by_region[region].get(d, 0) for d in decades],
                "borderColor": color,
                "backgroundColor": color + "33",
                "fill": True,
                "tension": 0.3,
            })
        return {"labels": [str(d) for d in decades], "datasets": datasets}

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
                latest.city_id,
                latest.city_name,
                latest.city_slug,
                latest.country,
                latest.region,
                latest.city_color,
                latest.latitude,
                latest.longitude,
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

        climate_index = self._build_climate_index(connection)
        geography_index = self._build_geography_index(connection)

        for row in rows:
            lat = row["latitude"]
            lng = row["longitude"]
            if lat is None or lng is None:
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
                    "lat": lat,
                    "lng": lng,
                    "radius": radius,
                    "climate": climate_index.get(row["city_id"]),
                    "geography": geography_index.get(row["city_id"]),
                }
            )

        return {
            "points": points,
            "mapped_count": len(points),
            "missing_count": len(missing),
            "top_points": points[:12],
        }

    # ── Climate extraction for map markers ─────────────────────

    @staticmethod
    def _build_climate_index(connection) -> dict[int, dict[str, Any]]:
        """Return {city_id: {winter, summer, climate_type, bullets}} from fiche Climat sections."""
        import json as _json
        import re as _re

        rows = connection.execute(
            """
            SELECT f.city_id, s.content_json
            FROM dim_city_fiche_section s
            JOIN dim_city_fiche f ON f.fiche_id = s.fiche_id
            WHERE LOWER(s.section_title) LIKE '%climat%'
            """
        ).fetchall()

        index: dict[int, dict[str, Any]] = {}
        temp_re = _re.compile(r"([-+]?\d+)\s*°?\s*C")

        for r in rows:
            city_id = r["city_id"]
            blocks = _json.loads(r["content_json"])
            winter = None
            summer = None
            climate_type = None
            bullets: list[str] = []

            for block in blocks:
                if block["type"] == "table":
                    for row in block.get("rows", []):
                        if len(row) >= 2:
                            m = temp_re.search(row[1])
                            if m:
                                val = int(m.group(1))
                                label = row[0].lower()
                                if "hiver" in label or "jan" in label:
                                    winter = val
                                elif "été" in label or "juil" in label or "jul" in label:
                                    summer = val
                elif block["type"] == "bullets":
                    for item in block.get("items", []):
                        bullets.append(item)
                        low = item.lower()
                        if "climat " in low or "climat\u00a0" in low:
                            cm = _re.search(r"\*\*(.+?)\*\*", item)
                            if cm:
                                climate_type = cm.group(1).strip()
                elif block["type"] == "text":
                    text = block.get("value", "")
                    wm = _re.search(r"Hiver.*?([-+]?\d+)\s*°?\s*C", text)
                    sm = _re.search(r"[EÉ]t[eé].*?([-+]?\d+)\s*°?\s*C", text)
                    if wm:
                        winter = int(wm.group(1))
                    if sm:
                        summer = int(sm.group(1))
                    cm = _re.search(r"[Cc]limat\s*\*\*(.+?)\*\*", text)
                    if cm:
                        climate_type = cm.group(1).strip()

            index[city_id] = {
                "winter_temp": winter,
                "summer_temp": summer,
                "climate_type": climate_type,
                "climate_bullets": bullets[:6],
            }

        return index

    @staticmethod
    def _build_geography_index(connection) -> dict[int, dict[str, Any]]:
        """Return {city_id: {area_km2, density, river, altitude, bullets}} from fiche Géographie sections."""
        import json as _json
        import re as _re

        rows = connection.execute(
            """
            SELECT f.city_id, s.content_json
            FROM dim_city_fiche_section s
            JOIN dim_city_fiche f ON f.fiche_id = s.fiche_id
            WHERE LOWER(s.section_title) LIKE '%ographie%densit%'
               OR LOWER(s.section_title) LIKE '%densit%'
            """
        ).fetchall()

        num_re = _re.compile(r"~?\s*([\d\s]+)")

        index: dict[int, dict[str, Any]] = {}
        for r in rows:
            city_id = r["city_id"]
            blocks = _json.loads(r["content_json"])
            area = None
            density = None
            river = None
            altitude = None
            bullets: list[str] = []

            for block in blocks:
                if block["type"] == "table":
                    for row in block.get("rows", []):
                        if len(row) < 2:
                            continue
                        key = row[0].lower()
                        val = row[1]
                        if "superficie" in key or "area" in key:
                            m = num_re.search(val)
                            if m:
                                area = int(m.group(1).replace(" ", "").replace("\u00a0", ""))
                        elif "densit" in key:
                            m = num_re.search(val)
                            if m:
                                density = int(m.group(1).replace(" ", "").replace("\u00a0", ""))
                        elif "rivi" in key or "cours" in key or "lac" in key or "river" in key or "fleuve" in key:
                            river = val
                        elif "altitude" in key:
                            m = num_re.search(val)
                            if m:
                                altitude = int(m.group(1).replace(" ", "").replace("\u00a0", ""))
                elif block["type"] == "bullets":
                    bullets.extend(block.get("items", []))
                elif block["type"] == "text":
                    text = block.get("value", "")
                    dm = _re.search(r"[Dd]ensit[eé].*?~?\s*([\d\s]+)\s*hab", text)
                    if dm:
                        density = int(dm.group(1).replace(" ", "").replace("\u00a0", ""))
                    am = _re.search(r"[Ss]uperficie.*?~?\s*([\d\s]+)\s*km", text)
                    if am:
                        area = int(am.group(1).replace(" ", "").replace("\u00a0", ""))
                    hm = _re.search(r"[Aa]ltitude.*?~?\s*([\d\s]+)\s*m", text)
                    if hm:
                        altitude = int(hm.group(1).replace(" ", "").replace("\u00a0", ""))

            index[city_id] = {
                "area_km2": area,
                "density": density,
                "river": river,
                "altitude": altitude,
                "geo_bullets": bullets[:6],
            }

        return index

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
                v.area_km2,
                v.density,
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
            record.update(get_city_photo(record["city_slug"], connection))
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
        record.update(get_city_photo(record["city_slug"], connection))
        coords = connection.execute(
            "SELECT latitude, longitude FROM dim_city WHERE city_id = ?",
            (record["city_id"],),
        ).fetchone()
        if coords:
            record["latitude"] = coords["latitude"]
            record["longitude"] = coords["longitude"]
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
                da.annotation_type,
                da.photo_filename AS annotation_photo_filename
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
            photo_url = ""
            if annotation["annotation_photo_filename"]:
                photo_url = f"/static/images/annotations/{annotation['annotation_photo_filename']}"
            annotation_map[annotation["period_detail_id"]].append(
                {
                    "year": annotation["year"],
                    "label": annotation["annotation_label"],
                    "color": annotation["annotation_color"],
                    "type": annotation["annotation_type"],
                    "photoUrl": photo_url,
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
            SELECT annotation_id, year, annotation_label, annotation_color, annotation_type,
                   annotation_photo_filename, annotation_photo_source_url
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
            photo_url = ""
            if annotation.get("annotation_photo_filename"):
                photo_url = f"/static/images/annotations/{annotation['annotation_photo_filename']}"
            indexed_annotations.append(
                {
                    "id": f"annotation-{index}",
                    "year": year,
                    "label": annotation["annotation_label"],
                    "color": annotation["annotation_color"] or "#ef6c3d",
                    "type": annotation["annotation_type"],
                    "xMin": year - default_band_width,
                    "xMax": year + default_band_width,
                    "photoUrl": photo_url,
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
        catalog_sql = (
            "SELECT table_type AS type, table_name AS name, NULL::text AS sql\n"
            "FROM information_schema.tables\n"
            "WHERE table_schema = 'public'\n"
            "ORDER BY table_type, table_name;"
            if current_app.config.get("DATABASE_BACKEND") == "postgresql"
            else "SELECT type, name, sql\nFROM sqlite_master\nWHERE type IN ('table','view')\nORDER BY type, name;"
        )
        return [
            # ── Population ──
            {
                "category": "Population",
                "label": "Population récente par ville",
                "sql": "SELECT city_name, country, year, population\nFROM vw_city_population_analysis\nORDER BY year DESC, population DESC\nLIMIT 25;",
            },
            {
                "category": "Population",
                "label": "Top 10 villes les plus peuplées",
                "sql": "SELECT city_name, country, MAX(year) AS année, MAX(population) AS population\nFROM vw_city_population_analysis\nGROUP BY city_id\nORDER BY population DESC\nLIMIT 10;",
            },
            {
                "category": "Population",
                "label": "Pic historique par ville",
                "sql": "SELECT city_name, country, peak_year, peak_population, peak_annotation\nFROM vw_city_peak_population\nORDER BY peak_population DESC;",
            },
            # ── Croissance ──
            {
                "category": "Croissance",
                "label": "Croissance par décennie",
                "sql": "SELECT city_name, decade, start_population, end_population, absolute_growth, growth_pct\nFROM vw_city_growth_by_decade\nORDER BY growth_pct DESC\nLIMIT 25;",
            },
            {
                "category": "Croissance",
                "label": "Top décroissances",
                "sql": "SELECT city_name, country, previous_year, current_year, change_pct\nFROM vw_city_decline_periods\nORDER BY change_pct ASC\nLIMIT 20;",
            },
            {
                "category": "Croissance",
                "label": "Rebonds après déclin",
                "sql": "SELECT city_name, country, previous_year, current_year, absolute_change, change_pct\nFROM vw_city_rebound_periods\nORDER BY change_pct DESC\nLIMIT 20;",
            },
            # ── Périodes & Annotations ──
            {
                "category": "Périodes",
                "label": "Périodes détaillées avec population",
                "sql": "SELECT city_name, period_range_label, period_title,\n  start_population, end_population, population_change_pct\nFROM vw_city_period_detail_with_population\nORDER BY city_name, period_order\nLIMIT 25;",
            },
            {
                "category": "Périodes",
                "label": "Événements annotés par période",
                "sql": "SELECT city_name, year, annotation_label, annotation_color, population\nFROM vw_annotated_events_by_period\nORDER BY year DESC\nLIMIT 25;",
            },
            # ── Fiches complètes ──
            {
                "category": "Fiches",
                "label": "Couverture des fiches par ville",
                "sql": "SELECT city_name, country, section_count,\n  has_population, has_economie, has_education, has_transport, has_climat\nFROM vw_fiche_coverage\nORDER BY section_count DESC;",
            },
            {
                "category": "Fiches",
                "label": "Catalogue des sections",
                "sql": "SELECT section_emoji, section_title, city_count,\n  coverage_pct || '%' AS couverture, avg_content_length\nFROM vw_fiche_section_catalog\nORDER BY city_count DESC;",
            },
            {
                "category": "Fiches",
                "label": "Richesse des fiches (classement)",
                "sql": "SELECT city_name, country, section_count,\n  total_content_length, avg_section_length\nFROM vw_fiche_city_richness\nORDER BY total_content_length DESC\nLIMIT 20;",
            },
            {
                "category": "Fiches",
                "label": "Stats de contenu par type de section",
                "sql": "SELECT section_title, total_sections, avg_length,\n  with_table, with_bullets, with_text,\n  table_pct || '%' AS pct_tables, bullets_pct || '%' AS pct_bullets\nFROM vw_fiche_section_content_stats\nORDER BY total_sections DESC;",
            },
            # ── Exploration ──
            {
                "category": "Exploration",
                "label": "Tables et vues disponibles",
                "sql": catalog_sql,
            },
            {
                "category": "Exploration",
                "label": "Villes sans fiche complète",
                "sql": "SELECT dc.city_name, dc.country, dc.region\nFROM dim_city dc\nLEFT JOIN dim_city_fiche f ON f.city_id = dc.city_id\nWHERE f.fiche_id IS NULL\nORDER BY dc.city_name;",
            },
            {
                "category": "Exploration",
                "label": "Nombre de points de données par ville",
                "sql": "SELECT dc.city_name, dc.country,\n  COUNT(f.population_id) AS data_points,\n  MIN(dt.year) AS première_année,\n  MAX(dt.year) AS dernière_année\nFROM dim_city dc\nJOIN fact_city_population f ON f.city_id = dc.city_id\nJOIN dim_time dt ON dt.time_id = f.time_id\nGROUP BY dc.city_id\nORDER BY data_points DESC;",
            },
        ]

    @staticmethod
    def _region_in_clause(regions: list[str], col: str = "region") -> str:
        return f"AND {col} IN ({','.join('?' for _ in regions)})"

    def _build_city_filter_clause(self, filters: dict) -> tuple[str, list[Any]]:
        clause_parts: list[str] = []
        params: list[Any] = []
        if filters.get("country"):
            clause_parts.append("AND country = ?")
            params.append(filters["country"])
        if filters.get("region"):
            clause_parts.append(self._region_in_clause(filters["region"]))
            params.extend(filters["region"])
        if filters.get("search"):
            clause_parts.append("AND LOWER(city_name) LIKE LOWER(?)")
            params.append(f"%{filters['search']}%")
        return " ".join(clause_parts), params

    def _analysis_filter_sql(
        self,
        filters: dict,
        *,
        alias: str | None = None,
        include_city: bool = True,
    ) -> str:
        parts: list[str] = []
        prefix = f"{alias}." if alias else ""
        if filters.get("country"):
            parts.append(f"AND {prefix}country = ?")
        if filters.get("region"):
            parts.append(self._region_in_clause(filters["region"], f"{prefix}region"))
        if include_city and filters.get("search"):
            parts.append(f"AND LOWER({prefix}city_name) LIKE LOWER(?)")
        if filters.get("period"):
            parts.append(f"AND {prefix}period_label = ?")
        return " ".join(parts)

    def _analysis_filter_params(self, filters: dict, *, include_city: bool = True) -> list[Any]:
        params: list[Any] = []
        if filters.get("country"):
            params.append(filters["country"])
        if filters.get("region"):
            params.extend(filters["region"])
        if include_city and filters.get("search"):
            params.append(f"%{filters['search']}%")
        if filters.get("period"):
            params.append(filters["period"])
        return params

    def _peak_filter_sql(self, filters: dict[str, str | None], *, alias: str | None = None) -> str:
        return self._analysis_filter_sql(filters, alias=alias)

    def _peak_filter_params(self, filters: dict[str, str | None]) -> list[Any]:
        return self._analysis_filter_params(filters)

    def _growth_filter_sql(self, filters: dict) -> str:
        parts: list[str] = []
        if filters.get("country"):
            parts.append("AND growth.country = ?")
        if filters.get("region"):
            parts.append(self._region_in_clause(filters["region"], "city.region"))
        if filters.get("search"):
            parts.append("AND LOWER(growth.city_name) LIKE LOWER(?)")
        if filters.get("period"):
            parts.append("AND " + self._period_year_condition("growth.end_year"))
        return " ".join(parts)

    def _growth_filter_params(self, filters: dict) -> list[Any]:
        params: list[Any] = []
        if filters.get("country"):
            params.append(filters["country"])
        if filters.get("region"):
            params.extend(filters["region"])
        if filters.get("search"):
            params.append(f"%{filters['search']}%")
        if filters.get("period"):
            params.extend(self._period_year_params(filters["period"]))
        return params

    def _decline_filter_sql(self, filters: dict) -> str:
        parts: list[str] = []
        if filters.get("country"):
            parts.append("AND decline.country = ?")
        if filters.get("region"):
            parts.append(self._region_in_clause(filters["region"], "city.region"))
        if filters.get("search"):
            parts.append("AND LOWER(decline.city_name) LIKE LOWER(?)")
        if filters.get("period"):
            parts.append("AND " + self._period_year_condition("decline.current_year"))
        return " ".join(parts)

    def _decline_filter_params(self, filters: dict) -> list[Any]:
        params: list[Any] = []
        if filters.get("country"):
            params.append(filters["country"])
        if filters.get("region"):
            params.extend(filters["region"])
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

    # ------------------------------------------------------------------
    # Coverage / completeness
    # ------------------------------------------------------------------

    def get_city_coverage(self, filters: dict[str, object] | None = None) -> list[dict[str, object]]:
        """Return one row per city with completeness indicators."""
        filters = filters or {}
        conn = get_db()
        rows = conn.execute(
            """
            SELECT
                c.city_id,
                c.city_name,
                c.city_slug,
                c.country,
                c.region,
                COALESCE(pop.data_points, 0) AS data_points,
                pop.min_year,
                pop.max_year,
                CASE WHEN f.fiche_id IS NOT NULL THEN 1 ELSE 0 END AS has_fiche,
                COALESCE(fs.section_count, 0) AS fiche_sections,
                CASE WHEN pd.cnt > 0 THEN 1 ELSE 0 END AS has_periods,
                COALESCE(ann.annotation_count, 0) AS annotation_count
            FROM dim_city c
            LEFT JOIN (
                SELECT city_id,
                       COUNT(*) AS data_points,
                       MIN(year) AS min_year,
                       MAX(year) AS max_year
                FROM fact_city_population
                GROUP BY city_id
            ) pop ON pop.city_id = c.city_id
            LEFT JOIN dim_city_fiche f ON f.city_id = c.city_id
            LEFT JOIN (
                SELECT fiche_id, COUNT(*) AS section_count
                FROM dim_city_fiche_section
                GROUP BY fiche_id
            ) fs ON fs.fiche_id = f.fiche_id
            LEFT JOIN (
                SELECT city_id, COUNT(*) AS cnt
                FROM dim_city_period_detail
                GROUP BY city_id
            ) pd ON pd.city_id = c.city_id
            LEFT JOIN (
                SELECT city_id, COUNT(*) AS annotation_count
                FROM fact_city_population
                WHERE annotation_id IS NOT NULL
                GROUP BY city_id
            ) ann ON ann.city_id = c.city_id
            ORDER BY c.city_name
            """
        ).fetchall()
        from app.services.city_photos import get_city_photo

        results = []
        for r in rows:
            d = dict(r)
            d["has_photo"] = get_city_photo(d["city_slug"], get_db()).get("has_photo", False)
            results.append(d)
        return results

    def get_missing_decades(self) -> list[dict[str, object]]:
        """Return one row per city with the list of missing decade-years (1800–2020).

        Uses the city's foundation year (from fiche/details) to skip decades
        before the city existed.
        """
        conn = get_db()
        # Fixed decade grid: 1800, 1810, ... 2020
        all_decades = list(range(1800, 2030, 10))

        cities = conn.execute(
            "SELECT city_id, city_name, city_slug, region, country FROM dim_city ORDER BY city_name"
        ).fetchall()

        existing = {}
        for row in conn.execute(
            "SELECT city_id, year FROM fact_city_population WHERE year >= 1800"
        ).fetchall():
            existing.setdefault(row["city_id"], set()).add(row["year"])

        results = []
        for city in cities:
            city_years = existing.get(city["city_id"], set())
            if not city_years:
                continue

            # Get founding year from fiche/details
            origin = _get_city_origin_metadata(city["city_slug"])
            foundation_year = origin.get("foundation_year")

            # Determine start decade: use foundation year if available,
            # otherwise fall back to first data point
            if foundation_year:
                # Round foundation year up to next decade if not on a decade boundary
                start_decade = (foundation_year // 10) * 10
                if foundation_year - start_decade > 1:
                    start_decade += 10
            else:
                min_year = min(city_years)
                start_decade = (min_year // 10) * 10
                if min_year - start_decade > 1:
                    start_decade += 10

            expected = [d for d in all_decades if d >= start_decade]

            # Check coverage with ±1 year tolerance (Canadian census years
            # are offset: 1851, 1871, 1901, 1921, 1941, … vs decades)
            def _covered(exp_year: int) -> bool:
                return any(y in city_years for y in (exp_year, exp_year - 1, exp_year + 1))

            missing = [y for y in expected if not _covered(y)]
            if missing:
                results.append({
                    "city_id": city["city_id"],
                    "city_name": city["city_name"],
                    "city_slug": city["city_slug"],
                    "region": city["region"],
                    "country": city["country"],
                    "foundation_year": foundation_year,
                    "start_decade": start_decade,
                    "missing_years": missing,
                    "missing_count": len(missing),
                    "expected_count": len(expected),
                    "completeness_pct": round(100 * (1 - len(missing) / len(expected)), 1) if expected else 100,
                })
        results.sort(key=lambda r: r["missing_count"], reverse=True)
        return results

    def export_coverage_csv(self) -> str:
        """Export city coverage table as CSV."""
        import csv
        import io
        rows = self.get_city_coverage()
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Ville", "Pays", "Région", "Points de données", "Année min", "Année max", "Fiche complète", "Sections fiche", "Périodes historiques", "Photo"])
        for r in rows:
            writer.writerow([
                r["city_name"], r["country"], r["region"],
                r["data_points"], r["min_year"] or "", r["max_year"] or "",
                "Oui" if r["has_fiche"] else "Non",
                r["fiche_sections"],
                "Oui" if r["has_periods"] else "Non",
                "Oui" if r["has_photo"] else "Non",
            ])
        return buf.getvalue()

    def export_missing_decades_csv(self) -> str:
        """Export missing decades table as CSV."""
        import csv
        import io
        rows = self.get_missing_decades()
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Ville", "Pays", "Début", "Années manquantes", "Nb manquantes", "Nb attendues", "Complétude %"])
        for r in rows:
            writer.writerow([
                r["city_name"], r["country"], r["start_decade"],
                " | ".join(str(y) for y in r["missing_years"]),
                r["missing_count"], r["expected_count"], r["completeness_pct"],
            ])
        return buf.getvalue()

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
            except DatabaseError as exc:
                connection.rollback()
                backend = current_app.config.get("DATABASE_BACKEND", "database")
                raise SqlExecutionError(f"Erreur {backend}: {exc}") from exc

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

    # ------------------------------------------------------------------
    # Reference population — couverture vs population réelle
    # ------------------------------------------------------------------

    def get_reference_population_overview(self) -> dict[str, Any]:
        """Return reference population data with coverage ratios.

        Uses ±1-year tolerance when matching city data to reference years
        so that Canadian census years (1861, 1871 …) align with DB decade
        years (1860, 1870 …).  Per-city deduplication picks the closest
        year to avoid double-counting.
        """
        conn = get_db()

        # --- All city-level rows (city, country, region, year, pop) ---
        all_city = conn.execute(
            "SELECT city_id, city_name, country, region, year, population "
            "FROM vw_city_population_analysis"
        ).fetchall()

        # Build index: {(country, year): [(city_id, city_name, pop), ...]}
        from collections import defaultdict
        country_idx: dict[tuple[str, int], list[tuple[int, str, int]]] = defaultdict(list)
        region_idx: dict[tuple[str, str, int], list[tuple[int, str, int]]] = defaultdict(list)
        for r in all_city:
            country_idx[(r["country"], r["year"])].append(
                (r["city_id"], r["city_name"], r["population"])
            )
            if r["region"]:
                region_idx[(r["country"], r["region"], r["year"])].append(
                    (r["city_id"], r["city_name"], r["population"])
                )

        def _best_pop_for_year(idx, key_fn, ref_year: int) -> dict:
            """Sum populations, picking the closest year per city (±1).

            Returns dict with keys: total, cities (list of names),
            year_label (str like '1861' or '1860-1861').
            """
            # Gather candidates: {city_id: (abs_delta, actual_year, name, pop)}
            best: dict[int, tuple[int, int, str, int]] = {}
            for delta in (0, -1, 1):
                yr = ref_year + delta
                for city_id, name, pop in idx.get(key_fn(yr), []):
                    prev = best.get(city_id)
                    if prev is None or abs(delta) < prev[0]:
                        best[city_id] = (abs(delta), yr, name, pop)

            total = sum(v[3] for v in best.values())
            cities = sorted({v[2] for v in best.values()})
            actual_years = {v[1] for v in best.values()}
            if actual_years:
                mn, mx = min(actual_years), max(actual_years)
                year_label = str(ref_year) if mn == mx == ref_year else f"{min(mn, ref_year)}-{max(mx, ref_year)}"
            else:
                year_label = str(ref_year)
            return {"total": total, "cities": cities, "year_label": year_label}

        # --- Summary by country/year ---
        country_ref = conn.execute(
            "SELECT country, year, population FROM ref_population "
            "WHERE region IS NULL ORDER BY country, year"
        ).fetchall()

        def _is_canada_decade(yr: int) -> bool:
            """Keep only decade-aligned census years for Canada."""
            return yr == 1800 or yr % 10 == 1

        country_rows: list[dict[str, Any]] = []
        for r in country_ref:
            yr = r["year"]
            cty = r["country"]
            if yr > 2021:
                continue
            # Canada: keep only decade census years (1800, 1811, 1821 … 2021)
            if cty == "Canada" and not _is_canada_decade(yr):
                continue
            ref_pop = r["population"]
            info = _best_pop_for_year(
                country_idx, lambda y: (cty, y), yr
            )
            db_pop = info["total"]
            pct = round(db_pop / ref_pop * 100, 1) if ref_pop else 0
            country_rows.append({
                "country": cty,
                "year": yr,
                "year_label": info["year_label"],
                "ref_population": ref_pop,
                "db_population": db_pop,
                "cities": info["cities"],
                "coverage_pct": pct,
            })

        # --- By region/year ---
        region_ref = conn.execute(
            "SELECT country, region, year, population FROM ref_population "
            "WHERE region IS NOT NULL ORDER BY country, region, year"
        ).fetchall()

        region_rows: list[dict[str, Any]] = []
        for r in region_ref:
            yr = r["year"]
            cty = r["country"]
            if yr > 2021:
                continue
            # Canada: keep only decade census years
            if cty == "Canada" and not _is_canada_decade(yr):
                continue
            reg = r["region"]
            ref_pop = r["population"]
            info = _best_pop_for_year(
                region_idx, lambda y, c=cty, g=reg: (c, g, y), yr
            )
            db_pop = info["total"]
            pct = round(db_pop / ref_pop * 100, 1) if ref_pop else 0
            region_rows.append({
                "country": cty,
                "region": reg,
                "year": yr,
                "year_label": info["year_label"],
                "ref_population": ref_pop,
                "db_population": db_pop,
                "cities": info["cities"],
                "coverage_pct": pct,
            })

        # --- Distinct regions present in our DB ---
        db_regions = conn.execute(
            "SELECT DISTINCT country, region FROM dim_city "
            "WHERE region IS NOT NULL ORDER BY country, region"
        ).fetchall()
        active_regions = [(r["country"], r["region"]) for r in db_regions]

        # --- Summary cards ---
        ca_latest = [r for r in country_rows if r["country"] == "Canada"]
        us_latest = [r for r in country_rows if r["country"] == "United States"]
        ca_best = max(ca_latest, key=lambda x: x["coverage_pct"]) if ca_latest else None
        us_best = max(us_latest, key=lambda x: x["coverage_pct"]) if us_latest else None

        return {
            "country_rows": country_rows,
            "region_rows": region_rows,
            "active_regions": active_regions,
            "canada_best": ca_best,
            "usa_best": us_best,
            "total_ref_entries": len(country_ref) + len(region_ref),
        }
