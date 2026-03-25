from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any, Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _styles() -> dict[str, ParagraphStyle]:
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleCity", parent=styles["Title"], textColor=colors.HexColor("#264653"), fontSize=22, leading=28))
    styles.add(ParagraphStyle(name="SectionHeading", parent=styles["Heading2"], textColor=colors.HexColor("#0f8b8d"), fontSize=15, leading=20, spaceAfter=8))
    styles.add(ParagraphStyle(name="BodySmall", parent=styles["BodyText"], fontSize=9.5, leading=13, textColor=colors.HexColor("#1b2430")))
    styles.add(ParagraphStyle(name="Muted", parent=styles["BodyText"], fontSize=9, leading=12, textColor=colors.HexColor("#5b6574")))
    return styles


def _metric_table(rows: list[list[str]]) -> Table:
    table = Table(rows, colWidths=[55 * mm, 110 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#264653")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#fffdfa"), colors.HexColor("#f5efe4")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d8d3c8")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def build_dashboard_pdf(filters: dict[str, Any], metrics: dict[str, Any], growth_leaders: list[dict[str, Any]], peak_cities: list[dict[str, Any]], decline_cities: list[dict[str, Any]]) -> bytes:
    styles = _styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
    story: list[Any] = []

    story.append(Paragraph("ProjetCITY Analyst - Dashboard", styles["TitleCity"]))
    filter_text = ", ".join(f"{key}: {value}" for key, value in filters.items() if value) or "aucun filtre"
    story.append(Paragraph(f"Filtres actifs: {filter_text}", styles["Muted"]))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Indicateurs clés", styles["SectionHeading"]))
    story.append(
        _metric_table(
            [
                ["Indicateur", "Valeur"],
                ["Villes", str(metrics.get("city_count", 0))],
                ["Pays", str(metrics.get("country_count", 0))],
                ["Population agrégée", f"{metrics.get('total_population', 0):,}".replace(",", " ")],
                ["Année la plus récente", str(metrics.get("latest_year", "n/a"))],
            ]
        )
    )
    story.append(Spacer(1, 12))

    story.append(Paragraph("Top croissances", styles["SectionHeading"]))
    story.append(_metric_table([["Ville", "Décennie / croissance"]] + [[row["city_name"], f"{row['decade']} - {row['growth_pct']}%"] for row in growth_leaders[:10]]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Villes au pic", styles["SectionHeading"]))
    story.append(_metric_table([["Ville", "Pic"]] + [[row["city_name"], f"{row['peak_population']:,}".replace(",", " ") + f" en {row['peak_year']}"] for row in peak_cities[:10]]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Périodes de déclin", styles["SectionHeading"]))
    story.append(_metric_table([["Ville", "Fenêtre"]] + [[row["city_name"], f"{row['start_year']} -> {row['end_year']} ({row['population_change']:,})".replace(",", " ")] for row in decline_cities[:10]]))

    doc.build(story)
    return buffer.getvalue()


def build_city_pdf(city: dict[str, Any], filters: dict[str, Any], periods: list[dict[str, Any]], annotations: list[dict[str, Any]]) -> bytes:
    styles = _styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
    story: list[Any] = []

    story.append(Paragraph(f"ProjetCITY Analyst - {city['city_name']}", styles["TitleCity"]))
    filter_text = ", ".join(f"{key}: {value}" for key, value in filters.items() if value) or "aucun filtre"
    story.append(Paragraph(f"Filtres actifs: {filter_text}", styles["Muted"]))
    story.append(Spacer(1, 8))

    photo_path = city.get("photo_path")
    if isinstance(photo_path, str) and photo_path and not photo_path.lower().endswith(".svg"):
        absolute_photo_path = PROJECT_ROOT / "static" / photo_path.replace("/", os.sep)
        if absolute_photo_path.exists():
            story.append(Image(str(absolute_photo_path), width=174 * mm, height=78 * mm))
            story.append(Spacer(1, 10))

    story.append(Paragraph("Synthèse ville", styles["SectionHeading"]))
    story.append(
        _metric_table(
            [
                ["Indicateur", "Valeur"],
                ["Ville", city["city_name"]],
                ["Région / pays", f"{city['region']} / {city['country']}"],
                ["Population récente", f"{city['latest_population']:,}".replace(",", " ") + f" en {city['latest_year']}"],
                ["Pic historique", f"{city['peak_population']:,}".replace(",", " ") + f" en {city['peak_year']}"],
            ]
        )
    )
    story.append(Spacer(1, 12))

    story.append(
        Paragraph(
            f"{city['city_name']} est présenté ici comme une trajectoire urbaine complète: {len(periods)} période(s) détaillée(s) et {len(annotations)} annotation(s) historique(s) reliée(s) à la lecture démographique.",
            styles["BodySmall"],
        )
    )
    story.append(Spacer(1, 12))

    story.append(Paragraph("Périodes détaillées", styles["SectionHeading"]))
    for period in periods[:8]:
        story.append(Paragraph(f"{period['period_range_label']} - {period['period_title']}", styles["Heading4"]))
        story.append(Paragraph(period["summary_text"], styles["BodySmall"]))
        if period.get("items"):
            items_text = "<br/>".join(f"- {item}" for item in period["items"][:5])
            story.append(Paragraph(items_text, styles["BodySmall"]))
        story.append(Spacer(1, 8))

    story.append(Paragraph("Annotations", styles["SectionHeading"]))
    annotation_rows = [["Année", "Annotation"]] + [[str(item["year"]), item["annotation_label"]] for item in annotations[:20]]
    story.append(_metric_table(annotation_rows if len(annotation_rows) > 1 else [["Année", "Annotation"], ["n/a", "Aucune annotation disponible"]]))

    doc.build(story)
    return buffer.getvalue()