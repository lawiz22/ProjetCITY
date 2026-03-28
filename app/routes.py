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
    upsert_time_dimension,
)
from .services.pdf_reports import build_city_pdf, build_dashboard_pdf

web = Blueprint("web", __name__)


@web.route("/")
def dashboard() -> str:
    service = AnalyticsService()
    filters = service.normalize_filters(request.args)
    return render_template(
        "web/dashboard.html",
        page_title="Dashboard",
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
    response.headers["Content-Disposition"] = "attachment; filename=ccs-dashboard.pdf"
    return response


@web.route("/cities")
def city_directory() -> str:
    service = AnalyticsService()
    filters = service.normalize_filters(request.args)
    view_mode = request.args.get("view", "small").strip().lower()
    if view_mode not in {"large", "medium", "small", "compact"}:
        view_mode = "small"
    filter_options = service.get_filter_options()
    return render_template(
        "web/cities.html",
        page_title="City Directory",
        filters=filters,
        view_mode=view_mode,
        cities=service.get_city_directory(filters),
        countries=filter_options["countries"],
        regions=filter_options["regions"],
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
    filter_options = service.get_filter_options()
    return render_template(
        "web/map.html",
        page_title="Carte",
        filters=filters,
        map_payload=service.get_map_payload(filters),
        countries=filter_options["countries"],
        regions=filter_options["regions"],
    )


@web.route("/map/data")
def city_map_data():
    service = AnalyticsService()
    filters = service.normalize_filters(request.args)
    payload = service.get_map_payload(filters)
    return jsonify(payload["points"])


@web.route("/map/time-travel")
def map_time_travel_data():
    """Return all population data by year for time-travel slider.

    Response: {years: [...], cities: {slug: {name, country, region, color, lat, lng, area, density, data: {year: pop, ...}, periods: [...]}}}
    """
    from .db import get_db

    connection = get_db()
    rows = connection.execute(
        """
        SELECT
            f.year,
            f.population,
            c.city_name,
            c.city_slug,
            c.country,
            c.region,
            c.city_color,
            c.latitude,
            c.longitude,
            c.area_km2,
            c.density
        FROM fact_city_population f
        JOIN dim_city c ON c.city_id = f.city_id
        WHERE c.latitude IS NOT NULL
          AND c.longitude IS NOT NULL
          AND f.population IS NOT NULL
        ORDER BY c.city_slug, f.year
        """
    ).fetchall()

    cities: dict[str, dict] = {}
    year_set: set[int] = set()

    for r in rows:
        slug = r["city_slug"]
        yr = int(r["year"])
        year_set.add(yr)
        if slug not in cities:
            cities[slug] = {
                "name": r["city_name"],
                "country": r["country"],
                "region": r["region"],
                "color": r["city_color"] or "#2f6fed",
                "lat": r["latitude"],
                "lng": r["longitude"],
                "area": r["area_km2"],
                "density": r["density"],
                "data": {},
                "periods": [],
            }
        cities[slug]["data"][str(yr)] = r["population"]

    # Fetch period details for all cities that have them
    period_rows = connection.execute(
        """
        SELECT
            c.city_slug,
            cpd.period_order,
            cpd.period_range_label,
            cpd.period_title,
            cpd.start_year,
            cpd.end_year,
            cpd.summary_text
        FROM dim_city_period_detail cpd
        JOIN dim_city c ON c.city_id = cpd.city_id
        WHERE c.city_slug IN ({})
        ORDER BY c.city_slug, cpd.period_order
        """.format(",".join("?" for _ in cities)),
        list(cities.keys()),
    ).fetchall()

    for pr in period_rows:
        slug = pr["city_slug"]
        if slug in cities:
            cities[slug]["periods"].append({
                "order": pr["period_order"],
                "range": pr["period_range_label"],
                "title": pr["period_title"],
                "start": pr["start_year"],
                "end": pr["end_year"],
                "summary": pr["summary_text"],
            })

    return jsonify({"years": sorted(year_set), "cities": cities})


@web.route("/map/geocode-missing", methods=["POST"])
def map_geocode_missing():
    """Geocode all cities that have no latitude/longitude."""
    import time
    from .db import get_db
    from .services.city_coordinates import geocode_city

    connection = get_db()
    rows = connection.execute(
        "SELECT city_id, city_name, region, country FROM dim_city "
        "WHERE latitude IS NULL OR longitude IS NULL"
    ).fetchall()

    results = []
    for row in rows:
        coords = geocode_city(row["city_name"], row["region"], row["country"])
        if coords:
            connection.execute(
                "UPDATE dim_city SET latitude = ?, longitude = ? WHERE city_id = ?",
                (coords["lat"], coords["lng"], row["city_id"]),
            )
            connection.commit()
            results.append({"city": row["city_name"], "lat": coords["lat"], "lng": coords["lng"], "ok": True})
        else:
            results.append({"city": row["city_name"], "ok": False})
        time.sleep(1)  # respect Nominatim rate limit

    return jsonify({"total": len(rows), "geocoded": sum(1 for r in results if r["ok"]), "results": results})


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


@web.route("/add-city/compare", methods=["POST"])
def add_city_compare() -> str | Response:
    """Show side-by-side comparison when importing a city that already exists."""
    stats_text = request.form.get("stats_text", "").strip()
    periods_text = request.form.get("periods_text", "").strip()
    fiche_text = request.form.get("fiche_text", "").strip()

    if not stats_text:
        flash("Le champ population est vide.", "error")
        return redirect(url_for("web.add_city"))

    try:
        stats = parse_stats_text(stats_text)
    except ValueError as exc:
        flash(f"Erreur de parsing population: {exc}", "error")
        return redirect(url_for("web.add_city"))

    from .db import get_db
    conn = get_db()
    row = conn.execute(
        "SELECT city_id, city_name, city_slug FROM dim_city WHERE city_slug = ?",
        (stats["city_slug"],),
    ).fetchone()

    if not row:
        # City doesn't exist — nothing to compare
        flash(f"La ville « {stats['city_name']} » n'existe pas encore dans la BD. Utilisez le bouton Importer.", "error")
        return redirect(url_for("web.add_city"))

    city_id = row["city_id"]

    # --- Existing population data ---
    existing_pop = {
        r["year"]: r["population"]
        for r in conn.execute(
            "SELECT year, population FROM fact_city_population WHERE city_id = ? ORDER BY year",
            (city_id,),
        )
    }
    # --- Existing annotations ---
    existing_annotations = []
    for r in conn.execute(
        """SELECT f.year, a.annotation_label, a.annotation_color
           FROM fact_city_population f
           JOIN dim_annotation a ON f.annotation_id = a.annotation_id
           WHERE f.city_id = ? AND f.annotation_id IS NOT NULL
           ORDER BY f.year""",
        (city_id,),
    ):
        existing_annotations.append({
            "year": r["year"],
            "label": r["annotation_label"],
            "color": r["annotation_color"],
        })

    # --- Existing periods ---
    existing_periods = []
    for r in conn.execute(
        """SELECT period_detail_id, period_order, period_range_label, period_title,
                  start_year, end_year, summary_text
           FROM dim_city_period_detail WHERE city_id = ? ORDER BY period_order""",
        (city_id,),
    ):
        items = [
            i["item_text"] for i in conn.execute(
                "SELECT item_text FROM dim_city_period_detail_item WHERE period_detail_id = ? ORDER BY item_order",
                (r["period_detail_id"],),
            )
        ]
        existing_periods.append({
            "period_range_label": r["period_range_label"],
            "period_title": r["period_title"],
            "items": items,
        })

    # --- Existing fiche ---
    existing_fiche_sections = []
    fiche_row = conn.execute(
        "SELECT fiche_id FROM dim_city_fiche WHERE city_id = ?", (city_id,)
    ).fetchone()
    if fiche_row:
        import json as _json
        for s in conn.execute(
            "SELECT section_emoji, section_title, content_json FROM dim_city_fiche_section WHERE fiche_id = ? ORDER BY section_order",
            (fiche_row["fiche_id"],),
        ):
            existing_fiche_sections.append({
                "emoji": s["section_emoji"],
                "title": s["section_title"],
                "blocks": _json.loads(s["content_json"]) if s["content_json"] else [],
            })

    # --- New data (parsed) ---
    new_pop = dict(zip(stats["years"], stats["population"]))
    new_annotations = []
    for ann in stats["annotations"]:
        if len(ann) >= 4:
            new_annotations.append({
                "year": ann[0],
                "label": ann[2],
                "color": ann[3],
            })

    new_periods = []
    if periods_text:
        new_periods = parse_period_details_text(periods_text)

    new_fiche_sections = []
    if fiche_text:
        try:
            _header, parsed = parse_fiche_text(fiche_text)
            new_fiche_sections = [{"emoji": s.get("emoji", ""), "title": s["title"], "blocks": s.get("blocks", [])} for s in parsed]
        except Exception:
            pass

    # --- Build comparison data ---
    # Population diff
    all_years = sorted(set(existing_pop.keys()) | set(new_pop.keys()))
    pop_diff = []
    for y in all_years:
        ex = existing_pop.get(y)
        nw = new_pop.get(y)
        status = "same"
        if ex is None:
            status = "new"
        elif nw is None:
            status = "only_existing"
        elif ex != nw:
            status = "changed"
        pop_diff.append({"year": y, "existing": ex, "new": nw, "status": status})

    # Annotation diff (by year)
    existing_ann_by_year = {a["year"]: a for a in existing_annotations}
    new_ann_by_year = {a["year"]: a for a in new_annotations}
    all_ann_years = sorted(set(existing_ann_by_year.keys()) | set(new_ann_by_year.keys()))
    ann_diff = []
    for y in all_ann_years:
        ex = existing_ann_by_year.get(y)
        nw = new_ann_by_year.get(y)
        status = "same"
        if ex is None:
            status = "new"
        elif nw is None:
            status = "only_existing"
        elif ex["label"] != nw["label"]:
            status = "changed"
        ann_diff.append({"year": y, "existing": ex, "new": nw, "status": status})

    # Period diff (by range)
    existing_period_by_range = {p["period_range_label"]: p for p in existing_periods}
    new_period_by_range = {p["period_range_label"]: p for p in new_periods}
    all_ranges = list(dict.fromkeys(
        [p["period_range_label"] for p in existing_periods]
        + [p["period_range_label"] for p in new_periods]
    ))
    period_diff = []
    for rng in all_ranges:
        ex = existing_period_by_range.get(rng)
        nw = new_period_by_range.get(rng)
        status = "same"
        if ex is None:
            status = "new"
        elif nw is None:
            status = "only_existing"
        elif ex.get("summary_text", "") != nw.get("summary_text", ""):
            status = "changed"
        period_diff.append({"range": rng, "existing": ex, "new": nw, "status": status})

    return render_template(
        "web/merge_city.html",
        page_title=f"Fusionner — {stats['city_name']}",
        city_name=stats["city_name"],
        city_slug=stats["city_slug"],
        stats_text=stats_text,
        periods_text=periods_text,
        fiche_text=fiche_text,
        pop_diff=pop_diff,
        ann_diff=ann_diff,
        period_diff=period_diff,
        existing_fiche_sections=existing_fiche_sections,
        new_fiche_sections=new_fiche_sections,
        existing_pop_count=len(existing_pop),
        new_pop_count=len(new_pop),
        existing_ann_count=len(existing_annotations),
        new_ann_count=len(new_annotations),
        existing_period_count=len(existing_periods),
        new_period_count=len(new_periods),
    )


@web.route("/add-city/merge-import", methods=["POST"])
def add_city_merge_import() -> Response:
    """Process the merge form decisions and apply selective import."""
    stats_text = request.form.get("stats_text", "").strip()
    periods_text = request.form.get("periods_text", "").strip()
    fiche_text = request.form.get("fiche_text", "").strip()

    pop_action = request.form.get("pop_action", "keep")      # keep | replace | merge
    ann_action = request.form.get("ann_action", "keep")       # keep | replace | merge
    period_action = request.form.get("period_action", "keep") # keep | replace
    fiche_action = request.form.get("fiche_action", "keep")   # keep | replace

    if not stats_text:
        flash("Le champ population est vide.", "error")
        return redirect(url_for("web.add_city"))

    try:
        stats = parse_stats_text(stats_text)
    except ValueError as exc:
        flash(f"Erreur de parsing population: {exc}", "error")
        return redirect(url_for("web.add_city"))

    from .db import get_db
    conn = get_db()
    messages: list[str] = []

    # --- Upsert dim_city to get city_id ---
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

    # --- Population ---
    if pop_action == "replace":
        try:
            import_city_stats(conn, stats)
            conn.commit()
            messages.append(f"Population remplacée — {len(stats['years'])} années.")
        except Exception as exc:
            conn.rollback()
            messages.append(f"Erreur population: {exc}")
    elif pop_action == "merge":
        # Add only new years, keep existing
        try:
            time_cache: dict[int, int] = {
                year: tid for tid, year in conn.execute("SELECT time_id, year FROM dim_time")
            }
            existing_years = {
                r["year"]
                for r in conn.execute(
                    "SELECT year FROM fact_city_population WHERE city_id = ?", (city_id,)
                )
            }
            new_count = 0
            for yr, pop in zip(stats["years"], stats["population"]):
                if yr not in existing_years:
                    time_id = upsert_time_dimension(conn, time_cache, yr)
                    conn.execute(
                        """INSERT INTO fact_city_population (city_id, time_id, year, population, is_key_year, source_file)
                           VALUES (?, ?, ?, ?, 0, 'web-import')""",
                        (city_id, time_id, yr, pop),
                    )
                    new_count += 1
            conn.commit()
            messages.append(f"Population fusionnée — {new_count} nouvelles années ajoutées.")
        except Exception as exc:
            conn.rollback()
            messages.append(f"Erreur fusion population: {exc}")
    else:
        messages.append("Population conservée.")

    # --- Annotations ---
    if ann_action == "replace":
        # Delete existing annotations links, import new
        try:
            conn.execute(
                "UPDATE fact_city_population SET annotation_id = NULL WHERE city_id = ?",
                (city_id,),
            )
            for ann in stats["annotations"]:
                if len(ann) >= 4:
                    year, _, label, color = ann[0], ann[1], ann[2], ann[3]
                    # Upsert annotation
                    row = conn.execute(
                        "SELECT annotation_id FROM dim_annotation WHERE annotation_label = ?",
                        (label,),
                    ).fetchone()
                    if row:
                        ann_id = row["annotation_id"]
                    else:
                        cur = conn.execute(
                            "INSERT INTO dim_annotation (annotation_label, annotation_color) VALUES (?, ?)",
                            (label, color),
                        )
                        ann_id = cur.lastrowid
                    conn.execute(
                        "UPDATE fact_city_population SET annotation_id = ? WHERE city_id = ? AND year = ?",
                        (ann_id, city_id, year),
                    )
            conn.commit()
            messages.append(f"Annotations remplacées — {len(stats['annotations'])}.")
        except Exception as exc:
            conn.rollback()
            messages.append(f"Erreur annotations: {exc}")
    elif ann_action == "merge":
        # Add only missing annotations (years that don't already have one)
        try:
            existing_ann_years = {
                r["year"]
                for r in conn.execute(
                    "SELECT year FROM fact_city_population WHERE city_id = ? AND annotation_id IS NOT NULL",
                    (city_id,),
                )
            }
            new_count = 0
            for ann in stats["annotations"]:
                if len(ann) >= 4:
                    year, _, label, color = ann[0], ann[1], ann[2], ann[3]
                    if year not in existing_ann_years:
                        row = conn.execute(
                            "SELECT annotation_id FROM dim_annotation WHERE annotation_label = ?",
                            (label,),
                        ).fetchone()
                        if row:
                            ann_id = row["annotation_id"]
                        else:
                            cur = conn.execute(
                                "INSERT INTO dim_annotation (annotation_label, annotation_color) VALUES (?, ?)",
                                (label, color),
                            )
                            ann_id = cur.lastrowid
                        conn.execute(
                            "UPDATE fact_city_population SET annotation_id = ? WHERE city_id = ? AND year = ?",
                            (ann_id, city_id, year),
                        )
                        new_count += 1
            conn.commit()
            messages.append(f"Annotations fusionnées — {new_count} nouvelles ajoutées.")
        except Exception as exc:
            conn.rollback()
            messages.append(f"Erreur fusion annotations: {exc}")
    else:
        messages.append("Annotations conservées.")

    # --- Periods ---
    if period_action == "replace" and periods_text:
        sections = parse_period_details_text(periods_text)
        if sections:
            try:
                count = import_city_periods(conn, city_id, stats["city_slug"], sections)
                save_period_details_file(stats["city_slug"], periods_text)
                conn.commit()
                messages.append(f"Périodes remplacées — {count}.")
            except Exception as exc:
                conn.rollback()
                messages.append(f"Erreur périodes: {exc}")
    elif period_action == "merge" and periods_text:
        sections = parse_period_details_text(periods_text)
        if sections:
            try:
                time_cache_p: dict[int, int] = {
                    yr: tid for tid, yr in conn.execute("SELECT time_id, year FROM dim_time")
                }
                existing_ranges = {
                    r["period_range_label"]
                    for r in conn.execute(
                        "SELECT period_range_label FROM dim_city_period_detail WHERE city_id = ?",
                        (city_id,),
                    )
                }
                max_order = conn.execute(
                    "SELECT COALESCE(MAX(period_order), 0) FROM dim_city_period_detail WHERE city_id = ?",
                    (city_id,),
                ).fetchone()[0]
                new_count = 0
                for section in sections:
                    if section["period_range_label"] not in existing_ranges:
                        max_order += 1
                        start_time_id = upsert_time_dimension(conn, time_cache_p, section["start_year"])
                        end_time_id = upsert_time_dimension(conn, time_cache_p, section["end_year"])
                        cursor = conn.execute(
                            """INSERT INTO dim_city_period_detail
                                (city_id, period_order, period_range_label, period_title,
                                 start_year, end_year, start_time_id, end_time_id, summary_text, source_file)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            RETURNING period_detail_id""",
                            (city_id, max_order, section["period_range_label"], section["period_title"],
                             section["start_year"], section["end_year"], start_time_id, end_time_id,
                             section["summary_text"], f"{stats['city_slug']}.txt"),
                        )
                        period_detail_id = cursor.fetchone()[0]
                        for item_order, item_text in enumerate(section["items"], start=1):
                            conn.execute(
                                "INSERT INTO dim_city_period_detail_item (period_detail_id, item_order, item_text) VALUES (?, ?, ?)",
                                (period_detail_id, item_order, item_text),
                            )
                        new_count += 1
                conn.commit()
                messages.append(f"Périodes fusionnées — {new_count} nouvelles ajoutées.")
            except Exception as exc:
                conn.rollback()
                messages.append(f"Erreur fusion périodes: {exc}")
    else:
        messages.append("Périodes conservées.")

    # --- Fiche ---
    if fiche_action == "replace" and fiche_text:
        try:
            _header, fiche_sections = parse_fiche_text(fiche_text)
            if fiche_sections:
                import_city_fiche(conn, city_id, stats["city_slug"], fiche_text, fiche_sections)
                conn.commit()
                messages.append(f"Fiche remplacée — {len(fiche_sections)} sections.")
        except Exception as exc:
            conn.rollback()
            messages.append(f"Erreur fiche: {exc}")
    else:
        messages.append("Fiche conservée.")

    # --- Regenerate villestats_RAW.py ---
    try:
        from scripts.export_villestats_raw import export_all
        from pathlib import Path
        raw_path = Path(__file__).resolve().parent.parent / "villestats_RAW.py"
        raw_path.write_text(export_all(), encoding="utf-8")
        messages.append("villestats_RAW.py synchronisé.")
    except Exception as exc:
        messages.append(f"⚠️ villestats_RAW.py: {exc}")

    flash(f"🔀 {stats['city_name']} — Fusion appliquée. " + " | ".join(messages), "success")
    return redirect(url_for("web.city_detail", city_slug=stats["city_slug"]))


@web.route("/add-city/import", methods=["POST"])
def add_city_import() -> Response:
    """Single button: import stats + periods + auto-fetch photo."""
    stats_text = request.form.get("stats_text", "").strip()
    periods_text = request.form.get("periods_text", "").strip()
    skip_pop = request.form.get("skip_population") == "on"
    skip_periods = request.form.get("skip_periods") == "on"
    skip_fiche = request.form.get("skip_fiche") == "on"
    skip_photo = request.form.get("skip_photo") == "on"
    force_import = request.form.get("force_import") == "on"

    if not stats_text:
        flash("Le champ population est vide.", "error")
        return redirect(url_for("web.add_city"))

    # --- 1. Parse & import stats ---
    try:
        stats = parse_stats_text(stats_text)
    except ValueError as exc:
        flash(f"Erreur de parsing population: {exc}", "error")
        return redirect(url_for("web.add_city"))

    # --- 0. Garde-fou : valider le nom de la ville via géocodage ---
    if not force_import:
        from .services.city_coordinates import geocode_city, CITY_COORDINATES
        slug = stats["city_slug"]
        if slug not in CITY_COORDINATES:
            coords = geocode_city(stats["city_name"], stats["region"], stats["country"])
            if coords is None:
                flash(
                    f"⚠️ Impossible de géocoder « {stats['city_name']}, {stats['region'] or ''} » "
                    f"— le nom est peut-être mal orthographié. "
                    f"Vérifiez le nom et réessayez, ou cochez « Forcer l'import » pour passer outre.",
                    "error",
                )
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
                # Also register in photo library (dim_city_photo)
                try:
                    from .services.city_photos import save_photo_to_library, CITY_PHOTO_DIR
                    photo_path = CITY_PHOTO_DIR / photo_result["filename"]
                    if photo_path.exists():
                        save_photo_to_library(
                            conn, city_id, stats["city_slug"],
                            photo_path.read_bytes(), photo_result["filename"],
                            source_url=photo_result.get("source_page", ""),
                            attribution="Wikipedia/Wikimedia — vérifier les licences.",
                        )
                except Exception as exc_lib:
                    messages.append(f"⚠️ Bibliothèque photo: {exc_lib}")
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
# ------------------------------------------------------------------
#  Geographic coverage (regions / states)
# ------------------------------------------------------------------

@web.route("/geo-coverage")
def geo_coverage() -> str:
    """Geographic coverage: which regions/states are in the DB vs total."""
    from .db import get_db

    CA_REGIONS = [
        "Alberta", "British Columbia", "Manitoba", "New Brunswick",
        "Newfoundland and Labrador", "Northwest Territories", "Nova Scotia",
        "Nunavut", "Ontario", "Prince Edward Island", "Québec",
        "Saskatchewan", "Yukon",
    ]
    US_STATES = [
        "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
        "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
        "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
        "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
        "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
        "New Hampshire", "New Jersey", "New Mexico", "New York",
        "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
        "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
        "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
        "West Virginia", "Wisconsin", "Wyoming",
    ]

    conn = get_db()
    rows = conn.execute(
        """SELECT c.city_name, c.city_slug, c.region, c.country,
                  MAX(f.population) AS peak_pop,
                  COUNT(DISTINCT f.year) AS data_points
           FROM dim_city c
           LEFT JOIN fact_city_population f ON f.city_id = c.city_id
           GROUP BY c.city_id
           ORDER BY c.country, c.region, c.city_name"""
    ).fetchall()

    # Load reference cities (if table exists)
    ref_rows: list = []
    try:
        ref_rows = conn.execute(
            "SELECT city_name, region, country, population, rank FROM ref_city ORDER BY country, region, rank"
        ).fetchall()
    except Exception:
        pass  # table may not exist yet

    # Index ref cities by region
    ref_by_region: dict[str, list[dict]] = {}
    for rr in ref_rows:
        key = f"{rr['country']}|{rr['region']}"
        if key not in ref_by_region:
            ref_by_region[key] = []
        ref_by_region[key].append({
            "city_name": rr["city_name"],
            "population": rr["population"] or 0,
            "rank": rr["rank"] or 0,
        })

    # Index existing city names by region for matching
    existing_by_region: dict[str, set[str]] = {}
    for r in rows:
        key = f"{r['country']}|{r['region']}"
        if key not in existing_by_region:
            existing_by_region[key] = set()
        existing_by_region[key].add(r["city_name"].lower().strip())

    # Build per-region data
    region_data: dict[str, dict] = {}  # key = "country|region"
    for r in rows:
        key = f"{r['country']}|{r['region']}"
        if key not in region_data:
            region_data[key] = {
                "country": r["country"],
                "region": r["region"],
                "cities": [],
            }
        region_data[key]["cities"].append({
            "city_name": r["city_name"],
            "city_slug": r["city_slug"],
            "peak_pop": r["peak_pop"],
            "data_points": r["data_points"],
        })

    # Build country summaries
    ca_covered = set()
    us_covered = set()
    for key, rd in region_data.items():
        if rd["country"] == "Canada":
            if rd["region"] in CA_REGIONS:
                ca_covered.add(rd["region"])
        else:
            if rd["region"] in US_STATES:
                us_covered.add(rd["region"])

    ca_missing = sorted([r for r in CA_REGIONS if r not in ca_covered])
    us_missing = sorted([s for s in US_STATES if s not in us_covered])

    # Regions list with cities for template
    ca_regions_list = []
    for reg in CA_REGIONS:
        key = f"Canada|{reg}"
        cities = region_data.get(key, {}).get("cities", [])
        ref_cities = ref_by_region.get(key, [])
        existing_names = existing_by_region.get(key, set())
        ref_with_status = []
        for rc in ref_cities:
            ref_with_status.append({
                **rc,
                "in_db": rc["city_name"].lower().strip() in existing_names,
            })
        ref_total = len(ref_with_status)
        ref_covered = sum(1 for r in ref_with_status if r["in_db"])
        ca_regions_list.append({
            "name": reg,
            "covered": reg in ca_covered,
            "city_count": len(cities),
            "cities": cities,
            "ref_cities": ref_with_status,
            "ref_total": ref_total,
            "ref_covered": ref_covered,
        })

    us_regions_list = []
    for st in US_STATES:
        key = f"United States|{st}"
        cities = region_data.get(key, {}).get("cities", [])
        ref_cities = ref_by_region.get(key, [])
        existing_names = existing_by_region.get(key, set())
        ref_with_status = []
        for rc in ref_cities:
            ref_with_status.append({
                **rc,
                "in_db": rc["city_name"].lower().strip() in existing_names,
            })
        ref_total = len(ref_with_status)
        ref_covered = sum(1 for r in ref_with_status if r["in_db"])
        us_regions_list.append({
            "name": st,
            "covered": st in us_covered,
            "city_count": len(cities),
            "cities": cities,
            "ref_cities": ref_with_status,
            "ref_total": ref_total,
            "ref_covered": ref_covered,
        })

    total_cities = len(rows)
    ca_city_count = sum(1 for r in rows if r["country"] == "Canada")
    us_city_count = sum(1 for r in rows if r["country"] != "Canada")
    total_ref = len(ref_rows)
    total_ref_covered = sum(
        r["ref_covered"] for r in ca_regions_list + us_regions_list
    )

    return render_template(
        "web/geo_coverage.html",
        page_title="Couverture géographique",
        total_cities=total_cities,
        total_ref=total_ref,
        total_ref_covered=total_ref_covered,
        ca_total=len(CA_REGIONS),
        ca_covered=len(ca_covered),
        ca_missing=ca_missing,
        ca_city_count=ca_city_count,
        ca_regions=ca_regions_list,
        us_total=len(US_STATES),
        us_covered=len(us_covered),
        us_missing=us_missing,
        us_city_count=us_city_count,
        us_regions=us_regions_list,
    )


@web.route("/geo-coverage/expand-ref", methods=["POST"])
def geo_coverage_expand_ref():
    """Add 20 more reference cities for a region via Mammouth AI."""
    import json as _json
    from .db import get_db
    from .services.mammouth_ai import load_settings, generate_city

    region = request.form.get("region", "").strip()
    country = request.form.get("country", "").strip()
    if not region or not country:
        return jsonify(success=False, error="Région et pays requis"), 400

    conn = get_db()
    existing_ref = conn.execute(
        "SELECT city_name FROM ref_city WHERE region = ? AND country = ?",
        (region, country),
    ).fetchall()
    existing_db = conn.execute(
        "SELECT city_name FROM dim_city WHERE region = ? AND country = ?",
        (region, country),
    ).fetchall()

    known_names = set()
    for r in existing_ref:
        known_names.add(r["city_name"].lower().strip())
    for r in existing_db:
        known_names.add(r["city_name"].lower().strip())

    current_max_rank = len(existing_ref)
    exclusion_list = ", ".join(sorted(known_names))

    settings = load_settings()
    api_key = settings.get("api_key", "")
    model = settings.get("model", "")
    if not api_key:
        return jsonify(success=False, error="Clé API non configurée"), 500

    new_cities: list[dict] = []
    TARGET = 20

    # Try up to 4 rounds with progressively smaller city requests
    prompts = [
        (
            f"Liste 30 villes et municipalités de {region} ({country}) "
            f"qui ne sont PAS dans cette liste: [{exclusion_list}].\n\n"
            f"Inclus des villes moyennes et petites (10 000 à 100 000 habitants), "
            f"pas seulement les grandes métropoles.\n"
            f"Réponds en JSON array: "
            f'[{{"city_name": "Nom", "population": 12345, "rank": {current_max_rank + 1}}}]\n'
            f"Trie par population décroissante. "
            f"Utilise les noms courants français si applicable.\n"
            f"UNIQUEMENT le JSON array, aucun markdown, aucun texte autour."
        ),
        (
            f"Liste 30 petites villes et villages de {region} ({country}) "
            f"de moins de 50 000 habitants.\n\n"
            f"NE PAS inclure ces villes déjà connues: [{exclusion_list}].\n\n"
            f"Inclus des municipalités, villages, petites villes régionales.\n"
            f"Réponds en JSON array: "
            f'[{{"city_name": "Nom", "population": 5000, "rank": 1}}]\n'
            f"Trie par population décroissante.\n"
            f"UNIQUEMENT le JSON array, aucun markdown."
        ),
        (
            f"Donne-moi 30 localités/municipalités/villages de {region} ({country}) "
            f"qui sont moins connues, entre 1 000 et 30 000 habitants.\n\n"
            f"EXCLURE absolument: [{exclusion_list}].\n\n"
            f"Réponds en JSON array: "
            f'[{{"city_name": "Nom", "population": 3000, "rank": 1}}]\n'
            f"UNIQUEMENT le JSON array."
        ),
        (
            f"Nomme 30 autres communautés de {region} ({country}) "
            f"qui ne sont dans aucune de ces listes: [{exclusion_list}].\n"
            f"Même les très petits villages de quelques centaines d'habitants.\n"
            f"JSON array: "
            f'[{{"city_name": "Nom", "population": 500, "rank": 1}}]\n'
            f"UNIQUEMENT le JSON array."
        ),
    ]

    for prompt in prompts:
        if len(new_cities) >= TARGET:
            break

        result = generate_city(
            api_key, model, "", prompt,
            max_tokens=2000, temperature=0.7,
        )
        if not result.get("success"):
            continue

        reply = result.get("reply", "").strip()
        if reply.startswith("```"):
            reply = reply.split("\n", 1)[-1]
        if reply.endswith("```"):
            reply = reply.rsplit("```", 1)[0]
        reply = reply.strip()

        start = reply.find("[")
        end = reply.rfind("]")
        if start == -1 or end == -1:
            continue
        try:
            parsed = _json.loads(reply[start:end + 1])
        except _json.JSONDecodeError:
            continue

        for c in parsed:
            if not isinstance(c, dict) or "city_name" not in c:
                continue
            name = c["city_name"].strip()
            if name.lower() in known_names:
                continue
            rank = current_max_rank + len(new_cities) + 1
            new_cities.append({
                "city_name": name,
                "region": region,
                "country": country,
                "population": c.get("population", 0),
                "rank": rank,
            })
            known_names.add(name.lower())

        # Update exclusion list for next prompt round
        exclusion_list = ", ".join(sorted(known_names))

    if not new_cities:
        return jsonify(success=False, error="Aucune nouvelle ville trouvée après plusieurs tentatives"), 500

    # Insert into DB
    inserted = 0
    for c in new_cities[:TARGET]:
        try:
            conn.execute(
                """INSERT OR IGNORE INTO ref_city
                   (city_name, region, country, population, rank)
                   VALUES (?, ?, ?, ?, ?)""",
                (c["city_name"], c["region"], c["country"],
                 c["population"], c["rank"]),
            )
            inserted += 1
        except Exception:
            pass
    conn.commit()

    return jsonify(success=True, inserted=inserted, cities=[c["city_name"] for c in new_cities[:TARGET]])


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


# ------------------------------------------------------------------
#  Options / Mammouth AI settings
# ------------------------------------------------------------------

@web.route("/options", methods=["GET"])
def options() -> str:
    from .services.mammouth_ai import load_settings, fetch_models

    settings = load_settings()
    models = fetch_models()
    return render_template(
        "web/options.html",
        page_title="Options",
        settings=settings,
        models=models,
    )


@web.route("/ai-lab")
def ai_lab() -> str:
    from .services.mammouth_ai import load_settings, fetch_models, load_prompt

    settings = load_settings()
    models = fetch_models()
    prompt_city = load_prompt("city_data_step1.txt")
    prompt_details = load_prompt("city_data_step2.txt")
    prompt_fiche = load_prompt("city_data_step3.txt")
    return render_template(
        "web/ai_lab.html",
        page_title="AI Lab",
        settings=settings,
        models=models,
        prompt_city=prompt_city,
        prompt_details=prompt_details,
        prompt_fiche=prompt_fiche,
    )


@web.route("/options/save", methods=["POST"])
def options_save() -> Response:
    from .services.mammouth_ai import load_settings, save_settings

    settings = load_settings()
    settings["api_key"] = request.form.get("api_key", "").strip()
    settings["model"] = request.form.get("model", "gpt-4.1-mini").strip()
    save_settings(settings)
    flash("Paramètres enregistrés.", "success")
    return redirect(url_for("web.options"))


@web.route("/options/test", methods=["POST"])
def options_test() -> Response:
    from .services.mammouth_ai import test_connection

    api_key = request.form.get("api_key", "").strip()
    model = request.form.get("model", "gpt-4.1-mini").strip()
    if not api_key:
        return jsonify({"success": False, "error": "Aucune clé API fournie."})
    result = test_connection(api_key, model)
    if result.get("success"):
        from .services.mammouth_ai import load_settings
        result["tokens_total"] = load_settings().get("tokens_used", 0)
    return jsonify(result)


@web.route("/options/reset-tokens", methods=["POST"])
def options_reset_tokens() -> Response:
    from .services.mammouth_ai import reset_tokens
    reset_tokens()
    return jsonify({"success": True, "tokens_used": 0})


@web.route("/options/generate", methods=["POST"])
def options_generate() -> Response:
    from .services.mammouth_ai import load_settings, generate_city

    settings = load_settings()
    api_key = settings.get("api_key", "")
    if not api_key:
        return jsonify({"success": False, "error": "Aucune clé API configurée. Enregistrez d'abord votre clé."})

    model = request.form.get("model", settings.get("model", "gpt-4.1-mini")).strip()
    city_input = request.form.get("city_input", "").strip()
    prompt_text = request.form.get("prompt_text", "").strip()

    if not city_input:
        return jsonify({"success": False, "error": "Veuillez entrer un nom de ville."})
    if not prompt_text:
        return jsonify({"success": False, "error": "Le prompt est vide."})

    max_tokens = int(request.form.get("max_tokens", 2000))
    result = generate_city(api_key, model, city_input, prompt_text, max_tokens=max_tokens)
    if result.get("success"):
        result["tokens_total"] = load_settings().get("tokens_used", 0)
    return jsonify(result)


@web.route("/ai-lab/suggest-city", methods=["POST"])
def ai_lab_suggest_city() -> Response:
    """Ask Mammouth to suggest a city not yet in the DB, prioritizing missing regions."""
    from .services.mammouth_ai import load_settings, generate_city
    from .db import get_db
    import random

    settings = load_settings()
    api_key = settings.get("api_key", "")
    if not api_key:
        return jsonify({"success": False, "error": "Aucune clé API configurée."})

    model = request.form.get("model", settings.get("model", "gpt-4.1-mini")).strip()
    filter_country = request.form.get("country", "").strip()
    filter_region = request.form.get("region", "").strip()

    conn = get_db()

    # All Canadian provinces/territories and US states
    CA_REGIONS = [
        "Alberta", "British Columbia", "Manitoba", "New Brunswick",
        "Newfoundland and Labrador", "Northwest Territories", "Nova Scotia",
        "Nunavut", "Ontario", "Prince Edward Island", "Québec",
        "Saskatchewan", "Yukon",
    ]
    US_STATES = [
        "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
        "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
        "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
        "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
        "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
        "New Hampshire", "New Jersey", "New Mexico", "New York",
        "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
        "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
        "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
        "West Virginia", "Wisconsin", "Wyoming",
    ]

    # Get existing cities
    existing_rows = conn.execute(
        "SELECT city_name, region, country FROM dim_city ORDER BY country, region"
    ).fetchall()

    existing_in = set()
    covered_ca = set()
    covered_us = set()
    for r in existing_rows:
        existing_in.add(f"{r['city_name']}, {r['region']}")
        if r["country"] == "Canada":
            covered_ca.add(r["region"])
        else:
            covered_us.add(r["region"])

    # ---- Specific region requested ----
    if filter_country and filter_region:
        existing_in_region = [r["city_name"] for r in existing_rows
                              if r["region"] == filter_region and r["country"] == filter_country]
        if existing_in_region:
            # Shuffle to vary the prompt and get different AI responses
            shuffled = list(existing_in_region)
            random.shuffle(shuffled)
            prompt = (
                f"La région {filter_region} ({filter_country}) a déjà ces villes dans ma base: "
                f"{', '.join(shuffled)}.\n"
                f"Suggère UNE autre ville de {filter_region} qui n'est PAS dans cette liste. "
                f"Choisis une ville différente à chaque fois, pas toujours la même. "
                f"Varie entre grandes villes, villes moyennes et petites villes connues.\n"
                f"Réponds UNIQUEMENT avec: NomVille, {filter_region}\n"
                f"Aucun autre texte."
            )
        else:
            prompt = (
                f"Suggère la ville la plus grande et la plus connue de: {filter_region} ({filter_country}).\n"
                f"Réponds UNIQUEMENT avec: NomVille, {filter_region}\n"
                f"Aucun autre texte."
            )

    # ---- Country filter only: pick a random missing region in that country ----
    elif filter_country:
        if filter_country == "Canada":
            missing = [r for r in CA_REGIONS if r not in covered_ca]
            all_regions = CA_REGIONS
        else:
            missing = [s for s in US_STATES if s not in covered_us]
            all_regions = US_STATES

        if missing:
            pick = random.choice(missing)
            prompt = (
                f"Suggère la ville la plus grande et la plus connue de: {pick} ({filter_country}).\n"
                f"Réponds UNIQUEMENT avec: NomVille, {pick}\n"
                f"Aucun autre texte."
            )
        else:
            # All regions covered for this country — least represented
            region_counts = conn.execute(
                """SELECT region, COUNT(*) as cnt FROM dim_city
                   WHERE country = ? GROUP BY region ORDER BY cnt ASC LIMIT 5""",
                (filter_country,)
            ).fetchall()
            pick = random.choice(region_counts)
            names = [r["city_name"] for r in existing_rows
                     if r["region"] == pick["region"] and r["country"] == filter_country]
            prompt = (
                f"La région {pick['region']} ({filter_country}) a seulement {pick['cnt']} ville(s) "
                f"dans ma base: {', '.join(names)}.\n"
                f"Suggère UNE ville populaire et connue de cette région qui n'est PAS dans cette liste.\n"
                f"Réponds UNIQUEMENT avec: NomVille, {pick['region']}\n"
                f"Aucun autre texte."
            )

    # ---- No filter: original behaviour ----
    else:
        missing_ca = [r for r in CA_REGIONS if r not in covered_ca]
        missing_us = [s for s in US_STATES if s not in covered_us]

        if missing_ca or missing_us:
            all_missing = [("Canada", r) for r in missing_ca] + [("United States", s) for s in missing_us]
            pick = random.choice(all_missing)
            prompt = (
                f"Suggère la ville la plus grande et la plus connue de: {pick[1]} ({pick[0]}).\n"
                f"Réponds UNIQUEMENT avec: NomVille, {pick[1]}\n"
                f"Aucun autre texte."
            )
        else:
            region_counts = conn.execute(
                """SELECT country, region, COUNT(*) as cnt
                   FROM dim_city GROUP BY country, region
                   ORDER BY cnt ASC LIMIT 10"""
            ).fetchall()
            least = region_counts[:5]
            pick = random.choice(least)
            existing_in_region = [r["city_name"] for r in existing_rows
                                  if r["region"] == pick["region"] and r["country"] == pick["country"]]
            prompt = (
                f"La région {pick['region']} ({pick['country']}) a seulement {pick['cnt']} ville(s) "
                f"dans ma base: {', '.join(existing_in_region)}.\n"
                f"Suggère UNE ville populaire et connue de cette région qui n'est PAS dans cette liste.\n"
                f"Réponds UNIQUEMENT avec: NomVille, {pick['region']}\n"
                f"Aucun autre texte."
            )

    result = generate_city(api_key, model, "", prompt, max_tokens=50, temperature=0.9)
    if result.get("success"):
        result["tokens_total"] = load_settings().get("tokens_used", 0)
    return jsonify(result)


@web.route("/ai-lab/import", methods=["POST"])
def ai_lab_import() -> Response:
    """AJAX import from AI Lab — returns JSON instead of redirect."""
    stats_text = request.form.get("stats_text", "").strip()
    periods_text = request.form.get("periods_text", "").strip()
    fiche_text = request.form.get("fiche_text", "").strip()
    skip_pop = request.form.get("skip_population") == "on"
    skip_periods = request.form.get("skip_periods") == "on"
    skip_fiche = request.form.get("skip_fiche") == "on"
    skip_photo = request.form.get("skip_photo") == "on"

    if not stats_text:
        return jsonify({"success": False, "error": "Le champ population (Step 1) est vide."})

    try:
        stats = parse_stats_text(stats_text)
    except ValueError as exc:
        return jsonify({"success": False, "error": f"Erreur de parsing population: {exc}"})

    from .db import get_db
    conn = get_db()
    messages = []

    if skip_pop:
        cursor = conn.execute(
            """INSERT INTO dim_city (city_name, city_slug, region, country, city_color, source_file)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(city_slug) DO UPDATE SET
                   city_name = excluded.city_name, region = excluded.region,
                   country = excluded.country, city_color = excluded.city_color,
                   source_file = excluded.source_file
               RETURNING city_id""",
            (stats["city_name"], stats["city_slug"], stats["region"],
             stats["country"], stats["city_color"], "ai-lab-import"),
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
            return jsonify({"success": False, "error": f"Erreur DB (population): {exc}"})
        messages.append(
            f"Population importée — {len(stats['years'])} années, "
            f"{len(stats['annotations'])} annotations."
        )

    # Auto-geocode
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

    # Periods
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
    elif skip_periods:
        messages.append("Périodes conservées (non remplacées).")

    # Fiche
    if fiche_text and not skip_fiche:
        try:
            _header, fiche_sections = parse_fiche_text(fiche_text)
            if fiche_sections:
                import_city_fiche(conn, city_id, stats["city_slug"], fiche_text, fiche_sections)
                conn.commit()
                messages.append(f"{len(fiche_sections)} sections fiche complète importées.")
        except Exception as exc:
            conn.rollback()
            messages.append(f"Erreur fiche complète: {exc}")

    # Photo
    if not skip_photo:
        try:
            photo_result = fetch_and_save_city_photo(
                stats["city_slug"], stats["city_name"], stats["region"], stats["country"],
            )
            if photo_result["success"]:
                messages.append(f"Photo importée: {photo_result['filename']}")
                # Also register in photo library (dim_city_photo)
                try:
                    from .services.city_photos import save_photo_to_library, CITY_PHOTO_DIR
                    photo_path = CITY_PHOTO_DIR / photo_result["filename"]
                    if photo_path.exists():
                        save_photo_to_library(
                            conn, city_id, stats["city_slug"],
                            photo_path.read_bytes(), photo_result["filename"],
                            source_url=photo_result.get("source_page", ""),
                            attribution="Wikipedia/Wikimedia — vérifier les licences.",
                        )
                except Exception as exc_lib:
                    messages.append(f"⚠️ Bibliothèque photo: {exc_lib}")
            else:
                messages.append(f"Photo: {photo_result['error']}")
        except Exception as exc:
            messages.append(f"Erreur photo: {exc}")
    else:
        messages.append("Photo conservée (non remplacée).")

    # Sync villestats_RAW.py
    try:
        from scripts.export_villestats_raw import export_all
        from pathlib import Path
        raw_path = Path(__file__).resolve().parent.parent / "villestats_RAW.py"
        raw_path.write_text(export_all(), encoding="utf-8")
        messages.append("villestats_RAW.py synchronisé.")
    except Exception as exc:
        messages.append(f"⚠️ villestats_RAW.py: {exc}")

    return jsonify({
        "success": True,
        "city_name": stats["city_name"],
        "city_slug": stats["city_slug"],
        "messages": messages,
        "redirect": url_for("web.city_detail", city_slug=stats["city_slug"]),
    })