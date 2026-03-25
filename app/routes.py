from __future__ import annotations

from datetime import datetime

from flask import Blueprint, Response, current_app, flash, jsonify, redirect, render_template, request, url_for

from .services.analytics import AnalyticsService, SqlExecutionError
from .services.city_import import (
    delete_city_fiche,
    fetch_and_save_city_photo,
    get_city_fiche,
    import_city_fiche,
    import_city_periods,
    import_city_stats,
    parse_fiche_text,
    parse_period_details_text,
    parse_stats_text,
    save_period_details_file,
    save_uploaded_photo,
)
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
        decline_leaders=service.get_decline_leader_cities(filters),
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
    view_mode = request.args.get("view", "small").strip().lower()
    if view_mode not in {"large", "medium", "small", "compact"}:
        view_mode = "small"
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

    from .db import get_db
    fiche = get_city_fiche(get_db(), city["city_id"])

    return render_template(
        "web/city_detail.html",
        page_title=city["city_name"],
        filters=filters,
        city=city,
        fiche=fiche,
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


# ---------------------------------------------------------------------------
# Add City
# ---------------------------------------------------------------------------

@web.route("/add-city")
def add_city() -> str:
    return render_template("web/add_city.html", page_title="Ajout de ville")


@web.route("/add-city/import", methods=["POST"])
def add_city_import() -> Response:
    """Single button: import stats + periods + auto-fetch photo."""
    stats_text = request.form.get("stats_text", "").strip()
    periods_text = request.form.get("periods_text", "").strip()

    if not stats_text:
        flash("Le champ population est vide.", "error")
        return redirect(url_for("web.add_city"))

    # --- 1. Parse & import stats ---
    try:
        stats = parse_stats_text(stats_text)
    except ValueError as exc:
        flash(f"Erreur de parsing population: {exc}", "error")
        return redirect(url_for("web.add_city"))

    from .db import get_db
    conn = get_db()
    try:
        city_id = import_city_stats(conn, stats)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        flash(f"Erreur DB (population): {exc}", "error")
        return redirect(url_for("web.add_city"))

    messages = [
        f"Population importée — {len(stats['years'])} années, "
        f"{len(stats['annotations'])} annotations."
    ]

    # --- 2. Parse & import periods (if provided) ---
    if periods_text:
        sections = parse_period_details_text(periods_text)
        if sections:
            try:
                count = import_city_periods(conn, city_id, stats["city_slug"], sections)
                save_period_details_file(stats["city_slug"], periods_text)
                conn.commit()
                messages.append(f"{count} périodes détaillées importées.")
            except Exception as exc:
                conn.rollback()
                messages.append(f"Erreur périodes: {exc}")
        else:
            messages.append("Aucune période détectée dans le texte.")

    # --- 3. Auto-fetch photo ---
    try:
        photo_result = fetch_and_save_city_photo(
            stats["city_slug"], stats["city_name"], stats["region"], stats["country"],
        )
        if photo_result["success"]:
            messages.append(f"Photo importée: {photo_result['filename']}")
        else:
            messages.append(f"Photo: {photo_result['error']}")
    except Exception as exc:
        messages.append(f"Erreur photo: {exc}")

    # --- 4. Parse & import fiche complète (if provided) ---
    fiche_text = request.form.get("fiche_text", "").strip()
    if fiche_text:
        try:
            _header, fiche_sections = parse_fiche_text(fiche_text)
            if fiche_sections:
                import_city_fiche(conn, city_id, stats["city_slug"], fiche_text, fiche_sections)
                conn.commit()
                messages.append(f"{len(fiche_sections)} sections fiche complète importées.")
            else:
                messages.append("Aucune section détectée dans la fiche complète.")
        except Exception as exc:
            conn.rollback()
            messages.append(f"Erreur fiche complète: {exc}")

    flash(f"{stats['city_name']} ({stats['city_slug']}) — " + " | ".join(messages), "success")
    return redirect(url_for("web.city_detail", city_slug=stats["city_slug"]))


@web.route("/cities/<city_slug>/photo", methods=["POST"])
def city_photo_import(city_slug: str) -> Response:
    """Fetch or upload a photo for an existing city."""
    from .db import get_db
    conn = get_db()
    row = conn.execute(
        "SELECT city_name, region, country FROM dim_city WHERE city_slug = ?", (city_slug,)
    ).fetchone()
    if not row:
        flash("Ville introuvable.", "error")
        return redirect(url_for("web.city_directory"))

    city_name, region, country = row

    # Check for uploaded file first
    uploaded = request.files.get("photo_file")
    if uploaded and uploaded.filename:
        from .services.city_import import save_uploaded_photo
        result = save_uploaded_photo(city_slug, uploaded)
    else:
        result = fetch_and_save_city_photo(city_slug, city_name, region, country)

    if result["success"]:
        flash(f"Photo importée: {result['filename']}", "success")
    else:
        flash(result["error"], "error")
    return redirect(url_for("web.city_detail", city_slug=city_slug))


@web.route("/cities/<city_slug>/fiche", methods=["POST"])
def city_fiche_import(city_slug: str) -> Response:
    """Import a fiche complète for an existing city."""
    from .db import get_db
    conn = get_db()
    row = conn.execute(
        "SELECT city_id, city_name FROM dim_city WHERE city_slug = ?", (city_slug,)
    ).fetchone()
    if not row:
        flash("Ville introuvable.", "error")
        return redirect(url_for("web.city_directory"))

    city_id, city_name = row["city_id"], row["city_name"]
    fiche_text = request.form.get("fiche_text", "").strip()

    if not fiche_text:
        flash("Le champ fiche complète est vide.", "error")
        return redirect(url_for("web.city_detail", city_slug=city_slug))

    try:
        _header, sections = parse_fiche_text(fiche_text)
        if not sections:
            flash("Aucune section détectée dans le texte.", "error")
            return redirect(url_for("web.city_detail", city_slug=city_slug))

        import_city_fiche(conn, city_id, city_slug, fiche_text, sections)
        conn.commit()
        flash(f"Fiche complète importée pour {city_name} — {len(sections)} sections.", "success")
    except Exception as exc:
        conn.rollback()
        flash(f"Erreur fiche complète: {exc}", "error")

    return redirect(url_for("web.city_detail", city_slug=city_slug))


@web.route("/cities/<city_slug>/fiche/delete", methods=["POST"])
def city_fiche_delete(city_slug: str) -> Response:
    """Delete the fiche complète for a city."""
    from .db import get_db
    conn = get_db()
    row = conn.execute(
        "SELECT city_id, city_name FROM dim_city WHERE city_slug = ?", (city_slug,)
    ).fetchone()
    if not row:
        flash("Ville introuvable.", "error")
        return redirect(url_for("web.city_directory"))

    try:
        deleted = delete_city_fiche(conn, row["city_id"], city_slug)
        conn.commit()
        if deleted:
            flash(f"Fiche complète supprimée pour {row['city_name']}.", "success")
        else:
            flash("Aucune fiche à supprimer.", "error")
    except Exception as exc:
        conn.rollback()
        flash(f"Erreur suppression fiche: {exc}", "error")

    return redirect(url_for("web.city_detail", city_slug=city_slug))