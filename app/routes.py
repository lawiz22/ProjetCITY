from __future__ import annotations

from datetime import datetime

from flask import Blueprint, Response, current_app, flash, redirect, render_template, request, url_for

from .services.analytics import AnalyticsService, SqlExecutionError
from .services.pdf_reports import build_city_pdf, build_dashboard_pdf

web = Blueprint("web", __name__)


@web.app_context_processor
def inject_navigation() -> dict[str, object]:
    service = AnalyticsService()
    return {
        "nav_filters": service.get_filter_options(),
    }


@web.route("/")
def dashboard() -> str:
    service = AnalyticsService()
    filters = service.normalize_filters(request.args)
    return render_template(
        "web/dashboard.html",
        page_title="Analyst Hub",
        filters=filters,
        metrics=service.get_dashboard_metrics(filters),
        growth_leaders=service.get_growth_leaders(filters),
        peak_cities=service.get_peak_cities(filters),
        decline_cities=service.get_decline_cities(filters),
        chart_payload=service.get_dashboard_chart_payload(filters),
    )


@web.route("/export/dashboard.pdf")
def dashboard_pdf() -> Response:
    service = AnalyticsService()
    filters = service.normalize_filters(request.args)
    pdf_bytes = build_dashboard_pdf(
        filters,
        service.get_dashboard_metrics(filters),
        service.get_growth_leaders(filters),
        service.get_peak_cities(filters),
        service.get_decline_cities(filters),
    )
    response = Response(pdf_bytes, mimetype="application/pdf")
    response.headers["Content-Disposition"] = "attachment; filename=projetcity-dashboard.pdf"
    return response


@web.route("/cities")
def city_directory() -> str:
    service = AnalyticsService()
    filters = service.normalize_filters(request.args)
    view_mode = request.args.get("view", "grid").strip().lower()
    if view_mode not in {"grid", "list"}:
        view_mode = "grid"
    return render_template(
        "web/cities.html",
        page_title="City Directory",
        filters=filters,
        view_mode=view_mode,
        cities=service.get_city_directory(filters),
    )


@web.route("/cities/<city_slug>")
def city_detail(city_slug: str) -> str:
    service = AnalyticsService()
    filters = service.normalize_filters(request.args)
    city = service.get_city_detail(city_slug, filters)
    if city is None:
        flash("Ville introuvable dans la base analytique.", "error")
        return redirect(url_for("web.city_directory"))

    return render_template(
        "web/city_detail.html",
        page_title=city["city_name"],
        filters=filters,
        city=city,
        periods=service.get_city_periods(city_slug, filters),
        annotations=service.get_city_annotations(city_slug, filters),
        chart_payload=service.get_city_chart_payload(city_slug, filters),
    )


@web.route("/cities/<city_slug>/export/pdf")
def city_detail_pdf(city_slug: str) -> Response:
    service = AnalyticsService()
    filters = service.normalize_filters(request.args)
    city = service.get_city_detail(city_slug, filters)
    if city is None:
        flash("Ville introuvable dans la base analytique.", "error")
        return redirect(url_for("web.city_directory"))
    pdf_bytes = build_city_pdf(
        city,
        filters,
        service.get_city_periods(city_slug, filters),
        service.get_city_annotations(city_slug, filters),
    )
    response = Response(pdf_bytes, mimetype="application/pdf")
    response.headers["Content-Disposition"] = f"attachment; filename={city_slug}.pdf"
    return response


@web.route("/compare")
def compare() -> str:
    service = AnalyticsService()
    filters = service.normalize_filters(request.args)
    selected_slugs = service.normalize_slug_list(request.args.getlist("city"))
    return render_template(
        "web/compare.html",
        page_title="Compare Cities",
        filters=filters,
        city_options=service.get_city_options(),
        selected_slugs=selected_slugs,
        compare_rows=service.get_compare_overview(selected_slugs, filters),
        chart_payload=service.get_compare_chart_payload(selected_slugs, filters),
    )


@web.route("/map")
def city_map() -> str:
    service = AnalyticsService()
    filters = service.normalize_filters(request.args)
    return render_template(
        "web/map.html",
        page_title="City Map",
        filters=filters,
        map_payload=service.get_map_payload(filters),
    )


@web.route("/sql-lab", methods=["GET", "POST"])
def sql_lab() -> str:
    service = AnalyticsService()
    sql = request.form.get("sql", "").strip()
    confirm_write = request.form.get("confirm_write") == "on"
    result: dict[str, object] | None = None

    if request.method == "POST" and sql:
        try:
            result = service.execute_sql(sql, confirm_write=confirm_write)
            if result["kind"] == "write":
                flash("Requête exécutée avec succès.", "success")
        except SqlExecutionError as exc:
            flash(str(exc), "error")

    return render_template(
        "web/sql_lab.html",
        page_title="SQL Lab",
        sql=sql,
        result=result,
        examples=service.get_sql_examples(),
        history_entries=service.get_sql_history(),
        saved_views=service.get_saved_views(),
        sql_write_enabled=current_app.config["SQL_ENABLE_WRITE"],
    )


@web.route("/sql-lab/export", methods=["POST"])
def sql_lab_export() -> Response:
    service = AnalyticsService()
    sql = request.form.get("sql", "").strip()
    try:
        csv_content, _statement = service.export_sql_csv(sql)
    except SqlExecutionError as exc:
        flash(str(exc), "error")
        return redirect(url_for("web.sql_lab"))

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    response = Response(csv_content, mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = f"attachment; filename=sql-lab-{timestamp}.csv"
    return response


@web.route("/sql-lab/history/clear", methods=["POST"])
def sql_lab_history_clear() -> Response:
    service = AnalyticsService()
    service.clear_sql_history()
    flash("Historique SQL effacé.", "success")
    return redirect(url_for("web.sql_lab"))


@web.route("/sql-lab/views/save", methods=["POST"])
def sql_lab_view_save() -> Response:
    service = AnalyticsService()
    try:
        service.save_sql_view(
            request.form.get("view_name", ""),
            request.form.get("view_description", ""),
            request.form.get("sql", ""),
        )
    except SqlExecutionError as exc:
        flash(str(exc), "error")
        return redirect(url_for("web.sql_lab"))
    flash("Vue analytique sauvegardée.", "success")
    return redirect(url_for("web.sql_lab"))


@web.route("/sql-lab/views/<view_id>/delete", methods=["POST"])
def sql_lab_view_delete(view_id: str) -> Response:
    service = AnalyticsService()
    service.delete_sql_view(view_id)
    flash("Vue analytique supprimée.", "success")
    return redirect(url_for("web.sql_lab"))