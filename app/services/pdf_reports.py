from __future__ import annotations

import html
import io
import os
import re
from pathlib import Path
from typing import Any, Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _register_font(name: str, relative_path: str) -> bool:
    font_path = Path(relative_path)
    if not font_path.exists():
        return False
    try:
        pdfmetrics.registerFont(TTFont(name, str(font_path)))
        return True
    except Exception:
        return False


def _font_names() -> tuple[str, str]:
    regular = "Helvetica"
    bold = "Helvetica-Bold"
    candidates = [
        ("SegoeUI", r"C:\Windows\Fonts\segoeui.ttf", "SegoeUIBold", r"C:\Windows\Fonts\segoeuib.ttf"),
        ("ArialUnicode", r"C:\Windows\Fonts\arial.ttf", "ArialUnicodeBold", r"C:\Windows\Fonts\arialbd.ttf"),
    ]
    for regular_name, regular_path, bold_name, bold_path in candidates:
        if _register_font(regular_name, regular_path) and _register_font(bold_name, bold_path):
            return regular_name, bold_name
    return regular, bold


def _styles() -> dict[str, ParagraphStyle]:
    styles = getSampleStyleSheet()
    font_regular, font_bold = _font_names()
    styles.add(ParagraphStyle(name="TitleCity", parent=styles["Title"], fontName=font_bold, textColor=colors.HexColor("#264653"), fontSize=22, leading=28))
    styles.add(ParagraphStyle(name="SectionHeading", parent=styles["Heading2"], fontName=font_bold, textColor=colors.HexColor("#0f8b8d"), fontSize=15, leading=20, spaceAfter=8))
    styles.add(ParagraphStyle(name="Overline", parent=styles["BodyText"], fontName=font_bold, fontSize=8.5, leading=11, textColor=colors.HexColor("#DDEBEA"), alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="BodySmall", parent=styles["BodyText"], fontName=font_regular, fontSize=9.5, leading=13, textColor=colors.HexColor("#1b2430")))
    styles.add(ParagraphStyle(name="Muted", parent=styles["BodyText"], fontName=font_regular, fontSize=9, leading=12, textColor=colors.HexColor("#5b6574")))
    styles.add(ParagraphStyle(name="HeroLead", parent=styles["BodyText"], fontName=font_regular, fontSize=11, leading=16, textColor=colors.white))
    styles.add(ParagraphStyle(name="BadgeText", parent=styles["BodyText"], fontName=font_bold, fontSize=9, leading=11, textColor=colors.HexColor("#264653"), alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="CardTitle", parent=styles["Heading4"], fontName=font_bold, fontSize=11.5, leading=15, textColor=colors.HexColor("#264653"), spaceAfter=4))
    return styles


def _escape(value: Any) -> str:
    return html.escape(str(value or ""))


def _pdf_safe_text(value: Any) -> str:
    text = str(value or "")
    text = text.replace("—", " - ").replace("–", " - ")
    text = re.sub(r"[\U00010000-\U0010ffff]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _safe_symbol(value: str | None) -> str:
    icon = (value or "").strip()
    symbol_map = {
        "🏞️": "◆",
        "🚢": "◆",
        "👥": "●",
        "🏗️": "◆",
        "📈": "▲",
        "🔥": "✦",
        "🏙️": "◆",
        "🏭": "■",
        "⚔️": "✦",
        "🚗": "◆",
        "🏢": "■",
        "⚠️": "!",
        "💻": "■",
        "🌍": "●",
        "📍": "◆",
        "•": "•",
    }
    return symbol_map.get(icon, "•")


def _trend_symbol(trend_label: str | None) -> str:
    if trend_label == "En croissance":
        return "▲"
    if trend_label == "En décroissance":
        return "▼"
    return "•"


def _hero_panel(city: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table:
    overline = Paragraph("DOSSIER URBAIN · EXPORT ANALYST", styles["Overline"])
    title = Paragraph(f"<font color='#FDF8F0'>{_escape(_pdf_safe_text(city['city_name']))}</font>", styles["TitleCity"])
    trend_symbol = _trend_symbol(city.get("trend_label"))
    subtitle = Paragraph(
        f"<font color='#DDEBEA'>{_escape(_pdf_safe_text(city['region']))} · {_escape(_pdf_safe_text(city['country']))}</font><br/><font color='#FFF8F1'>{trend_symbol} {_escape(_pdf_safe_text(city.get('trend_label', 'Stable')))} · fondation {_escape(_pdf_safe_text(city.get('foundation_year') or 'n.d.'))} · première population {_escape(_pdf_safe_text((f"{city.get('first_population'):,}".replace(',', ' ') + f" en {city.get('first_population_year')}") if city.get('first_population') else 'n.d.'))}</font>",
        styles["HeroLead"],
    )
    table = Table([[overline], [title], [subtitle]], colWidths=[174 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#264653")),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.HexColor("#173746"), colors.HexColor("#264653"), colors.HexColor("#0f8b8d")]),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#173746")),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
                ("TOPPADDING", (0, 1), (-1, 1), 8),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 6),
                ("TOPPADDING", (0, 2), (-1, 2), 0),
                ("BOTTOMPADDING", (0, 2), (-1, 2), 12),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    return table


def _narrative_card(text: str, styles: dict[str, ParagraphStyle]) -> Table:
    table = Table([[Paragraph(_escape(_pdf_safe_text(text)), styles["BodySmall"])]], colWidths=[174 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff7ef")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#efc9b5")),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return table


def _period_card(period: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table:
    header = Paragraph(
        f"<b>{_escape(_pdf_safe_text(period['period_range_label']))}</b> · {_escape(_pdf_safe_text(period['period_title']))}",
        styles["CardTitle"],
    )
    body_parts: list[str] = []
    if period.get("summary_text"):
        body_parts.append(_escape(_pdf_safe_text(period["summary_text"])))
    for bullet in period.get("display_bullets", [])[:4]:
        icon = _escape(_safe_symbol(bullet.get("icon")))
        text = _escape(_pdf_safe_text(bullet.get("text") or ""))
        body_parts.append(f"{icon} {text}")
    body = Paragraph("<br/>".join(body_parts), styles["BodySmall"])
    table = Table([[header], [body]], colWidths=[174 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2eee4")),
                ("BACKGROUND", (0, 1), (-1, 1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d8d3c8")),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#d8d3c8")),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def _annotation_table(annotations: list[dict[str, Any]]) -> Table:
    rows = [["Repère", "Lecture"]]
    for item in annotations[:18]:
        rows.append([f"● {_pdf_safe_text(item['year'])}", _pdf_safe_text(item["annotation_label"])])
    if len(rows) == 1:
        rows.append(["n/a", "Aucune annotation disponible"])
    return _metric_table(rows)


def _metric_table(rows: list[list[str]]) -> Table:
    _font_regular, font_bold = _font_names()
    table = Table(rows, colWidths=[55 * mm, 110 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#264653")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#fffdfa"), colors.HexColor("#f5efe4")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d8d3c8")),
                ("FONTNAME", (0, 0), (-1, 0), font_bold),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def _badge_table(items: list[str]) -> Table:
    _font_regular, font_bold = _font_names()
    rows: list[list[str]] = []
    current: list[str] = []
    for item in items:
        current.append(item)
        if len(current) == 2:
            rows.append(current)
            current = []
    if current:
        current.append("")
        rows.append(current)

    table = Table(rows, colWidths=[82 * mm, 82 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f5efe4")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#264653")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#d8d3c8")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d8d3c8")),
                ("FONTNAME", (0, 0), (-1, -1), font_bold),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def _summary_callout(city: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table:
    trend_symbol = _trend_symbol(city.get("trend_label"))
    text = (
        f"<b>{_escape(_pdf_safe_text(city['city_name']))}</b> se lit ici comme une évolution urbaine complète: "
        f"{trend_symbol} {_escape(_pdf_safe_text(city.get('trend_label', 'Stable')))} · "
        f"fondation {_escape(_pdf_safe_text(city.get('foundation_year') or 'n.d.'))} · "
        f"première population {_escape(_pdf_safe_text((f"{city.get('first_population'):,}".replace(',', ' ') + f" en {city.get('first_population_year')}") if city.get('first_population') else 'n.d.'))}."
    )
    table = Table([[Paragraph(text, styles["BodySmall"])]], colWidths=[174 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef7f6")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#b9d8d4")),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 11),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
            ]
        )
    )
    return table


def build_dashboard_pdf(filters: dict[str, Any], metrics: dict[str, Any], growth_leaders: list[dict[str, Any]], peak_cities: list[dict[str, Any]], decline_cities: list[dict[str, Any]]) -> bytes:
    styles = _styles()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
    story: list[Any] = []

    story.append(Paragraph("Central City Scrutinizer - Dashboard", styles["TitleCity"]))
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
    story.append(_metric_table([["Ville", "Croissance"]] + [[row["city_name"], f"En croissance depuis {row['growth_since']} — \u00d7{row['growth_factor']}"] for row in growth_leaders[:10]]))
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

    story.append(_hero_panel(city, styles))
    story.append(Spacer(1, 8))
    filter_text = ", ".join(f"{key}: {value}" for key, value in filters.items() if value) or "aucun filtre"
    story.append(Paragraph(f"Filtres actifs: {_pdf_safe_text(filter_text)}", styles["Muted"]))
    story.append(Spacer(1, 8))

    photo_path = city.get("photo_path")
    if isinstance(photo_path, str) and photo_path and not photo_path.lower().endswith(".svg"):
        absolute_photo_path = PROJECT_ROOT / "static" / photo_path.replace("/", os.sep)
        if absolute_photo_path.exists():
            story.append(Image(str(absolute_photo_path), width=174 * mm, height=78 * mm))
            story.append(Spacer(1, 10))

    story.append(
        _badge_table(
            [
                f"Tendance { _pdf_safe_text(city.get('trend_label', 'Stable')) }",
                f"{len(periods)} période(s)",
                f"Fondation {_pdf_safe_text(city.get('foundation_year') or 'n.d.')}",
                f"Première population {_pdf_safe_text((f"{city.get('first_population'):,}".replace(',', ' ') + f" en {city.get('first_population_year')}") if city.get('first_population') else 'n.d.')}",
                f"{len(annotations)} annotation(s)",
                f"Pic en {_pdf_safe_text(city['peak_year'])}",
            ]
        )
    )
    story.append(Spacer(1, 10))

    story.append(Paragraph("Synthèse ville", styles["SectionHeading"]))
    story.append(
        _metric_table(
            [
                ["Indicateur", "Valeur"],
                ["Ville", _pdf_safe_text(city["city_name"])],
                ["Région / pays", _pdf_safe_text(f"{city['region']} / {city['country']}")],
                ["Tendance", _pdf_safe_text(city.get("trend_label", "Stable"))],
                ["Fondation", _pdf_safe_text(city.get("foundation_year") or "n.d.")],
                ["Première population", _pdf_safe_text((f"{city.get('first_population'):,}".replace(',', ' ') + f" en {city.get('first_population_year')}") if city.get('first_population') else "n.d.")],
                ["Population récente", _pdf_safe_text(f"{city['latest_population']:,}".replace(",", " ") + f" en {city['latest_year']}")],
                ["Pic historique", _pdf_safe_text(f"{city['peak_population']:,}".replace(",", " ") + f" en {city['peak_year']}")],
            ]
        )
    )
    story.append(Spacer(1, 12))

    story.append(_summary_callout(city, styles))
    story.append(Spacer(1, 10))
    story.append(_narrative_card(
        f"{city['city_name']} est présenté ici comme une évolution urbaine complète: {len(periods)} période(s) détaillée(s) et {len(annotations)} annotation(s) historique(s) reliée(s) à la lecture démographique.",
        styles,
    ))
    story.append(Spacer(1, 12))

    story.append(PageBreak())

    story.append(Paragraph("◉ Périodes détaillées", styles["SectionHeading"]))
    for period in periods[:10]:
        story.append(_period_card(period, styles))
        story.append(Spacer(1, 8))

    story.append(PageBreak())
    story.append(Paragraph("◎ Annotations", styles["SectionHeading"]))
    story.append(_annotation_table(annotations))

    doc.build(story)
    return buffer.getvalue()