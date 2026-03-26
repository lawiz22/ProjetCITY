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

    from .services.city_photos import get_city_photos
    conn = get_db()
    city_photos = get_city_photos(conn, city_slug)

    return render_template(
        "web/city_detail.html",
        page_title=city["city_name"],
        filters=filters,
        city=city,
        fiche=fiche,
        city_photos=city_photos,
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
    return render_template("web/add_city.html", page_title="Ajout / mise à jour de ville")


@web.route("/add-city/check-slug")
def add_city_check_slug() -> Response:
    """AJAX: return existing city info for a given slug."""
    from .db import get_db
    slug = request.args.get("slug", "").strip()
    if not slug:
        return jsonify({"exists": False})
    conn = get_db()
    row = conn.execute(
        "SELECT city_id, city_name, city_slug, country, region FROM dim_city WHERE city_slug = ?",
        (slug,),
    ).fetchone()
    if not row:
        return jsonify({"exists": False})
    city_id = row["city_id"]
    pop_count = conn.execute(
        "SELECT COUNT(*) FROM fact_city_population WHERE city_id = ?", (city_id,)
    ).fetchone()[0]
    pop_range = conn.execute(
        "SELECT MIN(year), MAX(year) FROM fact_city_population WHERE city_id = ?", (city_id,)
    ).fetchone()
    period_count = conn.execute(
        "SELECT COUNT(*) FROM dim_city_period_detail WHERE city_id = ?", (city_id,)
    ).fetchone()[0]
    fiche = conn.execute(
        "SELECT fiche_id FROM dim_city_fiche WHERE city_id = ?", (city_id,)
    ).fetchone()
    fiche_sections = 0
    if fiche:
        fiche_sections = conn.execute(
            "SELECT COUNT(*) FROM dim_city_fiche_section WHERE fiche_id = ?", (fiche[0],)
        ).fetchone()[0]
    from app.services.city_photos import get_city_photo
    has_photo = get_city_photo(row["city_slug"], conn).get("has_photo", False)
    return jsonify({
        "exists": True,
        "city_name": row["city_name"],
        "city_slug": row["city_slug"],
        "country": row["country"],
        "region": row["region"],
        "pop_count": pop_count,
        "min_year": pop_range[0],
        "max_year": pop_range[1],
        "period_count": period_count,
        "fiche_sections": fiche_sections,
        "has_photo": has_photo,
    })


@web.route("/add-city/import", methods=["POST"])
def add_city_import() -> Response:
    """Single button: import stats + periods + auto-fetch photo."""
    stats_text = request.form.get("stats_text", "").strip()
    periods_text = request.form.get("periods_text", "").strip()
    skip_pop = request.form.get("skip_population") == "on"
    skip_periods = request.form.get("skip_periods") == "on"
    skip_fiche = request.form.get("skip_fiche") == "on"
    skip_photo = request.form.get("skip_photo") == "on"

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

    messages = []

    if skip_pop:
        # Still need city_id — upsert dim_city only, skip population
        cursor = conn.execute(
            """INSERT INTO dim_city (city_name, city_slug, region, country, city_color, source_file)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(city_slug) DO UPDATE SET
                   city_name = excluded.city_name, region = excluded.region,
                   country = excluded.country, city_color = excluded.city_color,
                   source_file = excluded.source_file
               RETURNING city_id""",
            (stats["city_name"], stats["city_slug"], stats["region"],
             stats["country"], stats["city_color"], "web-import"),
        )
        city_id = cursor.fetchone()[0]
        conn.commit()
        messages.append("Population conservée (non remplacée).")
    else:
        try:
            city_id = import_city_stats(conn, stats)
            conn.commit()
        except Exception as exc:
            conn.rollback()
            flash(f"Erreur DB (population): {exc}", "error")
            return redirect(url_for("web.add_city"))
        messages.append(
            f"Population importée — {len(stats['years'])} années, "
            f"{len(stats['annotations'])} annotations."
        )

    # --- 1b. Auto-geocode if no coordinates yet ---
    existing_coords = conn.execute(
        "SELECT latitude, longitude FROM dim_city WHERE city_id = ?", (city_id,)
    ).fetchone()
    if existing_coords and (existing_coords[0] is None or existing_coords[1] is None):
        from .services.city_coordinates import geocode_city
        coords = geocode_city(stats["city_name"], stats["region"], stats["country"])
        if coords:
            conn.execute(
                "UPDATE dim_city SET latitude = ?, longitude = ? WHERE city_id = ?",
                (coords["lat"], coords["lng"], city_id),
            )
            conn.commit()
            messages.append(f"Coordonnées géocodées ({coords['lat']}, {coords['lng']}).")
        else:
            messages.append("⚠️ Géocodage échoué — coordonnées manquantes.")

    # --- 2. Parse & import periods (if provided) ---
    if periods_text and not skip_periods:
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
    elif skip_periods:
        messages.append("Périodes conservées (non remplacées).")

    # --- 3. Auto-fetch photo ---
    if not skip_photo:
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
    else:
        messages.append("Photo conservée (non remplacée).")

    # --- 4. Parse & import fiche complète (if provided) ---
    fiche_text = request.form.get("fiche_text", "").strip()
    if fiche_text and not skip_fiche:
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
    elif skip_fiche:
        messages.append("Fiche complète conservée (non remplacée).")

    # --- 5. Régénérer villestats_RAW.py ---
    try:
        from scripts.export_villestats_raw import export_all
        from pathlib import Path
        raw_path = Path(__file__).resolve().parent.parent / "villestats_RAW.py"
        raw_path.write_text(export_all(), encoding="utf-8")
        messages.append("villestats_RAW.py synchronisé.")
    except Exception as exc:
        messages.append(f"⚠️ villestats_RAW.py: {exc}")

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


# ------------------------------------------------------------------
#  Photo Library
# ------------------------------------------------------------------

@web.route("/cities/<city_slug>/photos/upload", methods=["POST"])
def city_photo_upload(city_slug: str) -> Response:
    """Upload one or more photos to the city library."""
    from .db import get_db
    from .services.city_photos import save_photo_to_library

    conn = get_db()
    row = conn.execute(
        "SELECT city_id FROM dim_city WHERE city_slug = ?", (city_slug,)
    ).fetchone()
    if not row:
        flash("Ville introuvable.", "error")
        return redirect(url_for("web.city_directory"))

    files = request.files.getlist("photo_files")
    if not files or all(not f.filename for f in files):
        flash("Aucun fichier sélectionné.", "error")
        return redirect(url_for("web.city_detail", city_slug=city_slug))

    imported = 0
    for f in files:
        if not f.filename:
            continue
        result = save_photo_to_library(
            conn, row["city_id"], city_slug,
            f.read(), f.filename,
            attribution="Photo uploadée manuellement.",
        )
        if result["success"]:
            imported += 1

    flash(f"{imported} photo(s) ajoutée(s) à la bibliothèque.", "success")
    return redirect(url_for("web.city_detail", city_slug=city_slug))


@web.route("/cities/<city_slug>/photos/search")
def city_photo_search(city_slug: str) -> Response:
    """AJAX: search Wikipedia for city images and return candidates."""
    from .db import get_db
    from .services.city_photos import search_wikipedia_images

    conn = get_db()
    row = conn.execute(
        "SELECT city_name, region, country FROM dim_city WHERE city_slug = ?", (city_slug,)
    ).fetchone()
    if not row:
        return jsonify({"error": "Ville introuvable.", "images": []})

    images = search_wikipedia_images(row["city_name"], row["region"], row["country"])
    return jsonify({"images": images})


@web.route("/cities/<city_slug>/photos/search-commons")
def city_photo_search_commons(city_slug: str) -> Response:
    """AJAX: search Wikimedia Commons for city images and return candidates."""
    from .db import get_db
    from .services.city_photos import search_commons_images

    conn = get_db()
    row = conn.execute(
        "SELECT city_name, region, country FROM dim_city WHERE city_slug = ?", (city_slug,)
    ).fetchone()
    if not row:
        return jsonify({"error": "Ville introuvable.", "images": []})

    images = search_commons_images(row["city_name"], row["region"], row["country"])
    return jsonify({"images": images})


@web.route("/cities/<city_slug>/photos/import-web", methods=["POST"])
def city_photo_import_web(city_slug: str) -> Response:
    """Import selected web images into the city library."""
    from .db import get_db
    from .services.city_photos import download_web_image, save_photo_to_library

    conn = get_db()
    row = conn.execute(
        "SELECT city_id FROM dim_city WHERE city_slug = ?", (city_slug,)
    ).fetchone()
    if not row:
        return jsonify({"error": "Ville introuvable.", "imported": 0})

    data = request.get_json(silent=True)
    if not data or not isinstance(data.get("images"), list):
        return jsonify({"error": "Aucune image sélectionnée.", "imported": 0})

    imported = 0
    for img in data["images"]:
        url = img.get("url", "")
        if not url:
            continue
        result = download_web_image(url)
        if not result:
            continue
        file_bytes, ext = result
        save_result = save_photo_to_library(
            conn, row["city_id"], city_slug,
            file_bytes, f"web-import{ext}",
            source_url=img.get("source_page", ""),
            attribution="Wikipedia/Wikimedia — vérifier les licences.",
        )
        if save_result["success"]:
            imported += 1

    return jsonify({"imported": imported})


@web.route("/cities/<city_slug>/photos/<int:photo_id>/delete", methods=["POST"])
def city_photo_delete(city_slug: str, photo_id: int) -> Response:
    """Delete a photo from the library."""
    from .db import get_db
    from .services.city_photos import delete_photo_from_library

    conn = get_db()
    deleted = delete_photo_from_library(conn, photo_id, city_slug)
    if deleted:
        flash("Photo supprimée.", "success")
    else:
        flash("Photo introuvable.", "error")
    return redirect(url_for("web.city_detail", city_slug=city_slug))


@web.route("/cities/<city_slug>/photos/<int:photo_id>/primary", methods=["POST"])
def city_photo_set_primary(city_slug: str, photo_id: int) -> Response:
    """Set a photo as the primary for the city."""
    from .db import get_db
    from .services.city_photos import set_photo_primary

    conn = get_db()
    row = conn.execute(
        "SELECT city_id FROM dim_city WHERE city_slug = ?", (city_slug,)
    ).fetchone()
    if not row:
        flash("Ville introuvable.", "error")
        return redirect(url_for("web.city_directory"))

    set_photo_primary(conn, photo_id, row["city_id"])
    flash("Photo principale mise à jour.", "success")
    return redirect(url_for("web.city_detail", city_slug=city_slug))


# ---- Annotation photo routes ----

@web.route("/cities/<city_slug>/annotations/manual-search")
def annotation_manual_search(city_slug: str) -> Response:
    """AJAX: search Commons with a user-provided query string."""
    from .services.city_photos import _search_commons_batch

    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"images": []})

    seen_urls: set[str] = set()
    images = _search_commons_batch(query, seen_urls, limit=40)
    return jsonify({"images": images})


@web.route("/cities/<city_slug>/annotations/<int:annotation_id>/photo/search")
def annotation_photo_search(city_slug: str, annotation_id: int) -> Response:
    """AJAX: search web images for an annotation."""
    from .db import get_db
    from .services.city_photos import search_annotation_images

    conn = get_db()
    city_row = conn.execute(
        "SELECT city_name, region, country FROM dim_city WHERE city_slug = ?", (city_slug,)
    ).fetchone()
    ann_row = conn.execute(
        "SELECT annotation_label FROM dim_annotation WHERE annotation_id = ?", (annotation_id,)
    ).fetchone()
    if not city_row or not ann_row:
        return jsonify({"error": "Introuvable.", "images": []})

    images = search_annotation_images(
        ann_row["annotation_label"], city_row["city_name"],
        city_row["region"], city_row["country"],
    )
    return jsonify({"images": images})


@web.route("/cities/<city_slug>/annotations/<int:annotation_id>/photo/save", methods=["POST"])
def annotation_photo_save(city_slug: str, annotation_id: int) -> Response:
    """Save a web image as the annotation photo."""
    from .db import get_db
    from .services.city_photos import save_annotation_photo

    conn = get_db()
    data = request.get_json(silent=True)
    if not data or not data.get("url"):
        return jsonify({"success": False, "error": "URL manquante."})

    result = save_annotation_photo(
        conn, annotation_id, data["url"], data.get("source_page", ""),
        city_slug=city_slug,
    )
    return jsonify(result)


@web.route("/cities/<city_slug>/annotations/<int:annotation_id>/photo/link", methods=["POST"])
def annotation_photo_link(city_slug: str, annotation_id: int) -> Response:
    """Link an existing city photo to an annotation."""
    from .db import get_db
    from .services.city_photos import link_existing_photo_to_annotation

    conn = get_db()
    data = request.get_json(silent=True)
    if not data or not data.get("photo_id"):
        return jsonify({"success": False, "error": "photo_id manquant."})

    result = link_existing_photo_to_annotation(
        conn, annotation_id, city_slug, int(data["photo_id"]),
    )
    return jsonify(result)


# ---- Annotation CRUD routes ----

@web.route("/cities/<city_slug>/annotations/years")
def annotation_available_years(city_slug: str) -> Response:
    """AJAX: return years available for annotation linking."""
    from .db import get_db
    conn = get_db()
    rows = conn.execute(
        """
        SELECT fcp.year, fcp.population_id, fcp.annotation_id
        FROM fact_city_population fcp
        JOIN dim_city dc ON dc.city_id = fcp.city_id
        WHERE dc.city_slug = ?
        ORDER BY fcp.year
        """,
        (city_slug,),
    ).fetchall()
    years = [{"year": r["year"], "has_annotation": r["annotation_id"] is not None} for r in rows]
    return jsonify({"years": years})


@web.route("/cities/<city_slug>/annotations", methods=["POST"])
def annotation_create(city_slug: str) -> Response:
    """AJAX: create a new annotation and link it to a year."""
    from .db import get_db
    conn = get_db()
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Données manquantes."})

    label = (data.get("label") or "").strip()
    color = (data.get("color") or "red").strip()
    ann_type = (data.get("type") or "event").strip()
    year = data.get("year")

    if not label or not year:
        return jsonify({"success": False, "error": "Label et année requis."})

    try:
        year = int(year)
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "Année invalide."})

    # Verify the year exists for this city
    pop_row = conn.execute(
        """
        SELECT fcp.population_id, fcp.annotation_id
        FROM fact_city_population fcp
        JOIN dim_city dc ON dc.city_id = fcp.city_id
        WHERE dc.city_slug = ? AND fcp.year = ?
        """,
        (city_slug, year),
    ).fetchone()
    if not pop_row:
        return jsonify({"success": False, "error": f"Année {year} introuvable pour cette ville."})
    if pop_row["annotation_id"]:
        return jsonify({"success": False, "error": f"L'année {year} a déjà une annotation."})

    # Insert annotation
    cur = conn.execute(
        "INSERT INTO dim_annotation (annotation_label, annotation_color, annotation_type) VALUES (?, ?, ?)",
        (label, color, ann_type),
    )
    annotation_id = cur.lastrowid

    # Link to year
    conn.execute(
        "UPDATE fact_city_population SET annotation_id = ? WHERE population_id = ?",
        (annotation_id, pop_row["population_id"]),
    )
    conn.commit()
    return jsonify({"success": True, "annotation_id": annotation_id})


@web.route("/cities/<city_slug>/annotations/<int:annotation_id>", methods=["PUT"])
def annotation_update(city_slug: str, annotation_id: int) -> Response:
    """AJAX: update an existing annotation."""
    from .db import get_db
    conn = get_db()
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Données manquantes."})

    label = (data.get("label") or "").strip()
    color = (data.get("color") or "").strip()
    ann_type = (data.get("type") or "").strip()
    new_year = data.get("year")

    if not label:
        return jsonify({"success": False, "error": "Label requis."})

    # Update annotation fields
    updates = ["annotation_label = ?"]
    params: list = [label]
    if color:
        updates.append("annotation_color = ?")
        params.append(color)
    if ann_type:
        updates.append("annotation_type = ?")
        params.append(ann_type)
    params.append(annotation_id)

    conn.execute(
        f"UPDATE dim_annotation SET {', '.join(updates)} WHERE annotation_id = ?",
        params,
    )

    # If year changed, move the annotation link
    if new_year is not None:
        try:
            new_year = int(new_year)
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "Année invalide."})

        # Find current year link
        old_pop = conn.execute(
            """
            SELECT fcp.population_id, fcp.year
            FROM fact_city_population fcp
            JOIN dim_city dc ON dc.city_id = fcp.city_id
            WHERE dc.city_slug = ? AND fcp.annotation_id = ?
            """,
            (city_slug, annotation_id),
        ).fetchone()

        if not old_pop or old_pop["year"] != new_year:
            # Verify new year exists and is free
            new_pop = conn.execute(
                """
                SELECT fcp.population_id, fcp.annotation_id
                FROM fact_city_population fcp
                JOIN dim_city dc ON dc.city_id = fcp.city_id
                WHERE dc.city_slug = ? AND fcp.year = ?
                """,
                (city_slug, new_year),
            ).fetchone()
            if not new_pop:
                return jsonify({"success": False, "error": f"Année {new_year} introuvable."})
            if new_pop["annotation_id"] and new_pop["annotation_id"] != annotation_id:
                return jsonify({"success": False, "error": f"L'année {new_year} a déjà une annotation."})

            # Unlink old year
            if old_pop:
                conn.execute(
                    "UPDATE fact_city_population SET annotation_id = NULL WHERE population_id = ?",
                    (old_pop["population_id"],),
                )
            # Link new year
            conn.execute(
                "UPDATE fact_city_population SET annotation_id = ? WHERE population_id = ?",
                (annotation_id, new_pop["population_id"]),
            )

    conn.commit()
    return jsonify({"success": True})


@web.route("/cities/<city_slug>/annotations/<int:annotation_id>", methods=["DELETE"])
def annotation_delete(city_slug: str, annotation_id: int) -> Response:
    """AJAX: delete an annotation and unlink it from its year."""
    from .db import get_db
    from .services.city_photos import ANNOTATION_PHOTO_DIR
    conn = get_db()

    # Get annotation info (for photo cleanup)
    ann = conn.execute(
        "SELECT photo_filename FROM dim_annotation WHERE annotation_id = ?",
        (annotation_id,),
    ).fetchone()
    if not ann:
        return jsonify({"success": False, "error": "Annotation introuvable."})

    # Unlink from fact_city_population
    conn.execute(
        "UPDATE fact_city_population SET annotation_id = NULL WHERE annotation_id = ?",
        (annotation_id,),
    )

    # Delete photo file if exists
    if ann["photo_filename"]:
        photo_path = ANNOTATION_PHOTO_DIR / ann["photo_filename"]
        if photo_path.exists():
            photo_path.unlink()

    # Delete annotation
    conn.execute("DELETE FROM dim_annotation WHERE annotation_id = ?", (annotation_id,))
    conn.commit()
    return jsonify({"success": True})


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


# ------------------------------------------------------------------
#  Coverage / completeness
# ------------------------------------------------------------------

@web.route("/coverage")
def city_coverage() -> str:
    service = AnalyticsService()
    filters = service.normalize_filters(request.args)
    coverage = service.get_city_coverage(filters)
    missing_decades = service.get_missing_decades()

    total = len(coverage)
    without_fiche = sum(1 for c in coverage if not c["has_fiche"])
    without_photo = sum(1 for c in coverage if not c["has_photo"])
    without_periods = sum(1 for c in coverage if not c["has_periods"])
    without_data = sum(1 for c in coverage if c["data_points"] == 0)

    return render_template(
        "web/coverage.html",
        page_title="Couverture des données",
        filters=filters,
        coverage=coverage,
        missing_decades=missing_decades,
        total=total,
        without_fiche=without_fiche,
        without_photo=without_photo,
        without_periods=without_periods,
        without_data=without_data,
    )


@web.route("/coverage/export/coverage.csv")
def coverage_export_csv() -> Response:
    service = AnalyticsService()
    csv_content = service.export_coverage_csv()
    response = Response(csv_content, mimetype="text/csv; charset=utf-8")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    response.headers["Content-Disposition"] = f"attachment; filename=couverture-{timestamp}.csv"
    return response


@web.route("/coverage/export/missing-decades.csv")
def coverage_export_missing_csv() -> Response:
    service = AnalyticsService()
    csv_content = service.export_missing_decades_csv()
    response = Response(csv_content, mimetype="text/csv; charset=utf-8")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    response.headers["Content-Disposition"] = f"attachment; filename=annees-manquantes-{timestamp}.csv"
    return response


# ------------------------------------------------------------------
#  Reference population
# ------------------------------------------------------------------

@web.route("/reference-population")
def reference_population() -> str:
    service = AnalyticsService()
    data = service.get_reference_population_overview()
    return render_template(
        "web/reference_population.html",
        page_title="Population de référence",
        **data,
    )