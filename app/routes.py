from __future__ import annotations

from datetime import datetime
from pathlib import Path

from flask import Blueprint, Response, current_app, flash, g, jsonify, redirect, render_template, request, session, url_for

from .services.analytics import AnalyticsService, SqlExecutionError
from .services.app_state import delete_raw_document, load_raw_document
from .services.city_import import (
    _resolve_duplicate_slug,
    delete_city_fiche,
    fetch_and_save_city_photo,
    get_city_fiche,
    import_city_fiche,
    import_city_periods,
    import_city_stats,
    import_country_stats,
    parse_country_stats_text,
    parse_fiche_text,
    save_country_details_file,
    save_country_fiche_file,
    import_region_stats,
    parse_region_stats_text,
    import_region_periods,
    save_region_details_file,
    save_region_fiche_file,
    parse_period_details_text,
    parse_region_period_details_text,
    fetch_and_save_region_photo,
    fetch_and_save_region_flag,
    parse_stats_text,
    save_period_details_file,
    save_uploaded_photo,
    upsert_time_dimension,
)
from .services.pdf_reports import build_city_pdf, build_dashboard_pdf
from .services.auth import admin_required, collaborator_required, editor_required, login_required
from .services.audit import log_action

web = Blueprint("web", __name__)


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@web.route("/login", methods=["GET", "POST"])
def login():
    if g.get("user"):
        return redirect(url_for("web.dashboard"))
    if request.method == "POST":
        from .services.auth import authenticate
        login_val = request.form.get("login", "").strip()
        password = request.form.get("password", "")
        user = authenticate(login_val, password)
        if user is None:
            flash("Identifiants invalides.", "error")
            return render_template("web/login.html", page_title="Connexion", login=login_val)
        if not user.get("is_approved"):
            flash("Votre compte est en attente d'approbation par un administrateur.", "warning")
            return render_template("web/login.html", page_title="Connexion", login=login_val)
        session.clear()
        session["user_id"] = user["user_id"]
        session.permanent = True
        g.user = user
        log_action("login", "user", user["user_id"], user["username"])
        flash(f"Bienvenue, {user['display_name'] or user['username']} !", "success")
        next_url = request.form.get("next") or url_for("web.dashboard")
        return redirect(next_url)
    return render_template("web/login.html", page_title="Connexion", login="")


@web.route("/logout")
def logout():
    log_action("logout", "user", g.user["user_id"] if g.get("user") else None, g.user["username"] if g.get("user") else None)
    session.clear()
    flash("Déconnecté.", "info")
    return redirect(url_for("web.dashboard"))


@web.route("/register", methods=["GET", "POST"])
def register():
    if g.get("user"):
        return redirect(url_for("web.dashboard"))
    if request.method == "POST":
        from .services.auth import create_user, get_db
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        display_name = request.form.get("display_name", "").strip() or username
        errors = []
        if not username or len(username) < 3:
            errors.append("Le nom d'utilisateur doit contenir au moins 3 caractères.")
        if not email or "@" not in email:
            errors.append("Adresse email invalide.")
        if len(password) < 6:
            errors.append("Le mot de passe doit contenir au moins 6 caractères.")
        if password != password2:
            errors.append("Les mots de passe ne correspondent pas.")
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("web/register.html", page_title="Inscription",
                                   username=username, email=email, display_name=display_name)
        try:
            create_user(username=username, email=email, password=password,
                        role="lecteur", display_name=display_name, is_approved=False)
        except Exception:
            flash("Ce nom d'utilisateur ou email est déjà utilisé.", "error")
            return render_template("web/register.html", page_title="Inscription",
                                   username=username, email=email, display_name=display_name)
        log_action("register", "user", None, f"Nouvel utilisateur inscrit: {username}")
        flash("Compte créé ! Un administrateur doit approuver votre compte avant la connexion.", "success")
        return redirect(url_for("web.login"))
    return render_template("web/register.html", page_title="Inscription",
                           username="", email="", display_name="")


# ---------------------------------------------------------------------------
# Generic write-operation audit hook — REMOVED
# Explicit log_action() calls are placed directly in each write route
# for precise entity tracking.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Country period parsing helper
# ---------------------------------------------------------------------------

def _parse_country_periods(details_text: str, pop_data: list[dict]) -> list[dict]:
    """Parse a country details file into period dicts matching the city timeline format."""
    import re as _re

    pop_by_year: dict[int, int] = {r["year"]: r["population"] for r in pop_data}
    annotations_by_year: dict[int, dict] = {}
    for r in pop_data:
        if r.get("annotation_id"):
            annotations_by_year[r["year"]] = r

    # Period header: "YYYY[–-–]YYYY — TITLE" (em-dash separates range from title)
    HEADER_RE = _re.compile(
        r"^(\d{4}[\u2013\u2014\-]\d{4})\s*[\u2014\u2013]\s*(.+)$"
    )

    def _extract_emoji(value: str):
        """Return (icon, text) for a line."""
        stripped = value.strip()
        m = _re.match(r"^([^\w\s]+)\s*(.*)", stripped, flags=_re.UNICODE)
        if m:
            return m.group(1).strip(), m.group(2).strip()
        return "•", stripped

    def _flush(period, raw_items, summary_lines):
        if period is None:
            return
        summary = " ".join(summary_lines).strip()
        bullets = []
        seen: set[str] = set()
        for item in raw_items:
            item = item.strip().lstrip("- ").strip()
            if not item or item.lower().startswith("résumé"):
                continue
            icon, text = _extract_emoji(item)
            if not text or text in seen:
                continue
            seen.add(text)
            bullets.append({"icon": icon, "text": text})
        period["display_bullets"] = bullets
        period["summary_text"] = summary
        # Population range
        sy, ey = period["start_year"], period["end_year"]
        start_pop = None
        end_pop = None
        if sy is not None and ey is not None:
            # Closest year >= start_year in range
            candidates = [y for y in pop_by_year if sy <= y <= ey]
            if candidates:
                start_pop = pop_by_year[min(candidates)]
                end_pop = pop_by_year[max(candidates)]
        period["start_population"] = f"{start_pop:,}".replace(",", "\u202f") if start_pop else "n/a"
        period["end_population"] = f"{end_pop:,}".replace(",", "\u202f") if end_pop else "n/a"
        if start_pop and end_pop and start_pop > 0:
            pct = round((end_pop - start_pop) / start_pop * 100, 1)
            period["population_change_pct"] = pct
        else:
            period["population_change_pct"] = None
        # Linked annotations in range
        linked = []
        if sy is not None and ey is not None:
            for y, ann in sorted(annotations_by_year.items()):
                if sy <= y <= ey:
                    linked.append({"year": y, "label": ann.get("label", ""), "color": ann.get("color", "#ef6c3d"), "photoUrl": ""})
        period["linked_annotations"] = linked

    periods: list[dict] = []
    current: dict | None = None
    raw_items: list[str] = []
    summary_lines: list[str] = []
    in_summary = False

    for line in details_text.splitlines():
        stripped = line.strip()
        m = HEADER_RE.match(stripped)
        if m:
            _flush(current, raw_items, summary_lines)
            if current is not None:
                periods.append(current)
            range_label = m.group(1).replace("\u2013", "-").replace("\u2014", "-")
            year_parts = [int(y) for y in _re.findall(r"\d{4}", range_label)]
            current = {
                "period_range_label": range_label,
                "period_title": m.group(2).strip(),
                "start_year": year_parts[0] if year_parts else None,
                "end_year": year_parts[-1] if len(year_parts) >= 2 else (year_parts[0] if year_parts else None),
                "period_detail_id": len(periods),
            }
            raw_items = []
            summary_lines = []
            in_summary = False
            continue

        if current is None:
            continue  # Skip header stats block before first period

        if stripped.startswith("= "):
            in_summary = True
            rest = stripped[2:].strip()
            # Skip the "Résumé :" label itself
            if rest and not rest.lower().startswith("r\u00e9sum\u00e9"):
                summary_lines.append(rest)
            continue
        if stripped == "=":
            in_summary = True
            continue

        if in_summary:
            if stripped:
                summary_lines.append(stripped)
        else:
            if stripped:
                raw_items.append(stripped)

    _flush(current, raw_items, summary_lines)
    if current is not None:
        periods.append(current)

    # Add step index
    for i, p in enumerate(periods):
        p["step_index"] = i + 1
        p["step_total"] = len(periods)

    return periods


@web.route("/")
def dashboard() -> str:
    service = AnalyticsService()
    filters = service.normalize_filters(request.args)
    filter_options = service.get_filter_options()
    return render_template(
        "web/dashboard.html",
        page_title="Dashboard",
        filters=filters,
        filter_options=filter_options,
        metrics=service.get_dashboard_metrics(filters),
        growth_leaders=service.get_growth_leaders(filters),
        decline_leaders=service.get_decline_leader_cities(filters),
        peak_cities=service.get_peak_cities(filters),
        decline_cities=service.get_decline_cities(filters),
        chart_payload=service.get_dashboard_chart_payload(filters),
    )


@web.route("/export/dashboard.pdf")
@editor_required
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

    from .services.city_photos import get_city_photos, count_missing_photos
    conn = get_db()
    city_photos = get_city_photos(conn, city_slug)
    missing_photos_count = count_missing_photos(conn, "city", city_slug)

    from .services.event_service import get_events_for_city, CATEGORY_LABELS, CATEGORY_EMOJIS
    city_events = get_events_for_city(conn, city["city_id"])

    from .services.person_service import get_persons_for_city
    from .services.person_service import CATEGORY_LABELS as PERSON_CATEGORY_LABELS
    from .services.person_service import CATEGORY_EMOJIS as PERSON_CATEGORY_EMOJIS
    city_persons = get_persons_for_city(conn, city["city_id"])

    from .services.monument_service import get_monuments_for_city
    from .services.monument_service import CATEGORY_LABELS as MONUMENT_CATEGORY_LABELS
    from .services.monument_service import CATEGORY_EMOJIS as MONUMENT_CATEGORY_EMOJIS
    city_monuments = get_monuments_for_city(conn, city["city_id"])

    return render_template(
        "web/city_detail.html",
        page_title=city["city_name"],
        filters=filters,
        city=city,
        fiche=fiche,
        city_photos=city_photos,
        missing_photos_count=missing_photos_count,
        city_events=city_events,
        event_category_labels=CATEGORY_LABELS,
        event_category_emojis=CATEGORY_EMOJIS,
        city_persons=city_persons,
        person_category_labels=PERSON_CATEGORY_LABELS,
        person_category_emojis=PERSON_CATEGORY_EMOJIS,
        city_monuments=city_monuments,
        monument_category_labels=MONUMENT_CATEGORY_LABELS,
        monument_category_emojis=MONUMENT_CATEGORY_EMOJIS,
        periods=service.get_city_periods(city_slug, filters),
        annotations=service.get_city_annotations(city_slug, filters),
        chart_payload=service.get_city_chart_payload(city_slug, filters),
    )


@web.route("/cities/<city_slug>/export/pdf")
@editor_required
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


@web.route("/countries")
def country_directory() -> str:
    import os
    from .db import get_db
    conn = get_db()
    view_mode = request.args.get("view", "small").strip().lower()
    if view_mode not in {"large", "medium", "small", "compact"}:
        view_mode = "small"
    rows = conn.execute(
        """
        WITH latest AS (
            SELECT country_id, MAX(year) AS year
            FROM fact_country_population
            GROUP BY country_id
        ),
        first_row AS (
            SELECT country_id, MIN(year) AS first_year
            FROM fact_country_population
            GROUP BY country_id
        ),
        peak AS (
            SELECT country_id,
                   population AS peak_population,
                   year AS peak_year
            FROM (
                SELECT country_id, year, population,
                       ROW_NUMBER() OVER (
                           PARTITION BY country_id
                           ORDER BY population DESC, year ASC
                       ) AS rn
                FROM fact_country_population
            ) ranked_peak
            WHERE rn = 1
        )
        SELECT
            dc.country_id,
            dc.country_name,
            dc.country_slug,
            dc.country_color,
            fcp.population AS latest_population,
            latest.year AS latest_year,
            peak.peak_population,
            peak.peak_year,
            first_row.first_year,
            dc.created_at AS entity_created_at,
            dc.updated_at AS entity_updated_at,
            COALESCE(au_c.display_name, au_c.username) AS created_by_name,
            COALESCE(au_u.display_name, au_u.username) AS updated_by_name
        FROM dim_country dc
        LEFT JOIN latest ON latest.country_id = dc.country_id
        LEFT JOIN fact_country_population fcp
            ON fcp.country_id = dc.country_id AND fcp.year = latest.year
        LEFT JOIN peak ON peak.country_id = dc.country_id
        LEFT JOIN first_row ON first_row.country_id = dc.country_id
        LEFT JOIN app_user au_c ON au_c.user_id = dc.created_by_user_id
        LEFT JOIN app_user au_u ON au_u.user_id = dc.updated_by_user_id
        ORDER BY dc.country_name
        """
    ).fetchall()
    countries = []
    for row in rows:
        r = dict(row)
        slug = r.get("country_slug") or ""
        flag_path = f"images/flags/countries/{slug}.png"
        flag_full = os.path.join(current_app.static_folder, flag_path.replace("/", os.sep))
        r["flag_path"] = flag_path if os.path.exists(flag_full) else "images/flags/countries/unknown.png"
        countries.append(r)
    return render_template(
        "web/countries.html",
        page_title="Annuaire des pays",
        view_mode=view_mode,
        countries=countries,
    )


@web.route("/countries/<country_slug>")
def country_detail(country_slug: str) -> str:
    import os, json
    from .db import get_db
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM dim_country WHERE country_slug = ?", (country_slug,)
    ).fetchone()
    if row is None:
        flash("Pays introuvable dans la base analytique.", "error")
        return redirect(url_for("web.country_directory"))
    country = dict(row)
    pop_rows = conn.execute(
        """
        SELECT year, population, is_key_year, annotation_id
        FROM fact_country_population
        WHERE country_id = ?
        ORDER BY year
        """,
        (country["country_id"],),
    ).fetchall()
    pop_data = [dict(r) for r in pop_rows]
    latest = max(pop_data, key=lambda r: r["year"]) if pop_data else {}
    peak = max(pop_data, key=lambda r: r["population"]) if pop_data else {}
    first = min(pop_data, key=lambda r: r["year"]) if pop_data else {}
    country["latest_population"] = latest.get("population")
    country["latest_year"] = latest.get("year")
    country["peak_population"] = peak.get("population")
    country["peak_year"] = peak.get("year")
    country["first_year"] = first.get("year")
    country["first_population"] = first.get("population")
    # Flag
    flag_path = f"images/flags/countries/{country_slug}.png"
    flag_full = os.path.join(current_app.static_folder, flag_path.replace("/", os.sep))
    country["flag_path"] = flag_path if os.path.exists(flag_full) else None
    # Trend
    if len(pop_data) >= 2:
        delta = pop_data[-1]["population"] - pop_data[-2]["population"]
        country["trend_label"] = "En croissance" if delta > 0 else ("En décroissance" if delta < 0 else "Stable")
    else:
        country["trend_label"] = "Stable"
    # Chart payload
    years = [r["year"] for r in pop_data]
    populations = [r["population"] for r in pop_data]
    # Build indexed annotations for chart (same format as city/region)
    ann_chart_rows = conn.execute(
        """SELECT fcp.year, da.annotation_id, da.annotation_label, da.annotation_color,
                  da.annotation_type, da.photo_filename
           FROM fact_country_population fcp
           JOIN dim_annotation da ON da.annotation_id = fcp.annotation_id
           WHERE fcp.country_id = ?
           ORDER BY fcp.year""",
        (country["country_id"],),
    ).fetchall()
    default_band_width = 2
    if len(years) > 1:
        default_band_width = max(1, round((years[1] - years[0]) / 4))
    indexed_annotations = []
    for idx, row in enumerate(ann_chart_rows):
        photo_url = ""
        if row["photo_filename"]:
            photo_url = f"/static/images/annotations/{row['photo_filename']}"
        indexed_annotations.append({
            "id": f"annotation-{idx}",
            "year": row["year"],
            "label": row["annotation_label"],
            "color": row["annotation_color"] or "#ef6c3d",
            "type": row["annotation_type"],
            "xMin": row["year"] - default_band_width,
            "xMax": row["year"] + default_band_width,
            "photoUrl": photo_url,
        })
    chart_payload = {
        "labels": years,
        "datasets": [{
            "label": country["country_name"],
            "data": populations,
            "borderColor": country.get("country_color") or "#2f6fed",
            "backgroundColor": (country.get("country_color") or "#2f6fed") + "22",
            "fill": True,
            "tension": 0.3,
        }],
        "annotations": indexed_annotations,
    }
    # Fiche
    fiche_path = Path(current_app.root_path).parent / "data" / "country_fiches" / f"{country_slug}.txt"
    fiche = None
    raw_fiche = load_raw_document("country", country_slug, "fiche", fallback_path=fiche_path)
    if raw_fiche:
        _header, fiche_sections = parse_fiche_text(raw_fiche)
        if fiche_sections:
            fiche = {"raw_text": raw_fiche, "sections": [
                {"emoji": s.get("emoji", ""), "title": s.get("title", ""), "blocks": s.get("blocks", [])}
                for s in fiche_sections
            ]}
    # Details → periods
    details_path = Path(current_app.root_path).parent / "data" / "country_details" / f"{country_slug}.txt"
    periods: list[dict] = []
    details = None
    details = load_raw_document("country", country_slug, "period_detail", fallback_path=details_path)
    if details:
        # Enrich pop_data with annotation labels for period linking
        ann_rows = conn.execute(
            """
            SELECT fcp.year, da.annotation_label AS label, da.annotation_color AS color
            FROM fact_country_population fcp
            JOIN dim_annotation da ON da.annotation_id = fcp.annotation_id
            WHERE fcp.country_id = ?
            """,
            (country["country_id"],),
        ).fetchall()
        ann_by_year = {r["year"]: {"label": r["label"], "color": r["color"]} for r in ann_rows}
        # Merge annotation info into pop_data for parser
        pop_with_ann = [
            {**r, **(ann_by_year.get(r["year"], {}))}
            for r in pop_data
        ]
        periods = _parse_country_periods(details, pop_with_ann)
    # Annotations for the template
    ann_rows_tpl = conn.execute(
        """SELECT fcp.year, da.annotation_id, da.annotation_label, da.annotation_color,
                  da.annotation_type, da.photo_filename AS annotation_photo_filename
           FROM fact_country_population fcp
           JOIN dim_annotation da ON da.annotation_id = fcp.annotation_id
           WHERE fcp.country_id = ?
           ORDER BY fcp.year""",
        (country["country_id"],),
    ).fetchall()
    annotations = [dict(r) for r in ann_rows_tpl]
    # Country photos
    from .services.city_photos import get_country_photos, count_missing_photos
    country_photos = get_country_photos(conn, country_slug)
    missing_photos_count = count_missing_photos(conn, "country", country_slug)
    return render_template(
        "web/country_detail.html",
        page_title=country["country_name"],
        country=country,
        pop_data=pop_data,
        periods=periods,
        chart_payload=chart_payload,
        fiche=fiche,
        details=details,
        annotations=annotations,
        country_photos=country_photos,
        missing_photos_count=missing_photos_count,
    )


# ------------------------------------------------------------------
#  Country Photo Library routes
# ------------------------------------------------------------------

@web.route("/countries/<country_slug>/photos/upload", methods=["POST"])
@editor_required
def country_photo_upload(country_slug: str) -> Response:
    from .db import get_db
    from .services.city_photos import save_country_photo_to_library
    conn = get_db()
    row = conn.execute("SELECT country_id FROM dim_country WHERE country_slug = ?", (country_slug,)).fetchone()
    if not row:
        flash("Pays introuvable.", "error")
        return redirect(url_for("web.country_directory"))
    files = request.files.getlist("photo_files")
    if not files or all(not f.filename for f in files):
        flash("Aucun fichier sélectionné.", "error")
        return redirect(url_for("web.country_detail", country_slug=country_slug))
    imported = 0
    for f in files:
        if not f.filename:
            continue
        result = save_country_photo_to_library(
            conn, row["country_id"], country_slug, f.read(), f.filename,
            attribution="Photo uploadée manuellement.",
        )
        if result["success"]:
            imported += 1
    flash(f"{imported} photo(s) ajoutée(s) à la bibliothèque.", "success")
    log_action("upload_photo", "country", country_slug, f"{imported} photo(s) uploadée(s) pour le pays {country_slug}")
    return redirect(url_for("web.country_detail", country_slug=country_slug))


@web.route("/countries/<country_slug>/photos/search")
def country_photo_search(country_slug: str) -> Response:
    from .db import get_db
    from .services.city_photos import search_wikipedia_images
    conn = get_db()
    row = conn.execute("SELECT country_name FROM dim_country WHERE country_slug = ?", (country_slug,)).fetchone()
    if not row:
        return jsonify({"error": "Pays introuvable.", "images": []})
    images = search_wikipedia_images(row["country_name"], None, None)
    return jsonify({"images": images})


@web.route("/countries/<country_slug>/photos/search-commons")
def country_photo_search_commons(country_slug: str) -> Response:
    from .db import get_db
    from .services.city_photos import search_commons_images
    conn = get_db()
    row = conn.execute("SELECT country_name FROM dim_country WHERE country_slug = ?", (country_slug,)).fetchone()
    if not row:
        return jsonify({"error": "Pays introuvable.", "images": []})
    images = search_commons_images(row["country_name"], None, None)
    return jsonify({"images": images})


@web.route("/countries/<country_slug>/photos/import-web", methods=["POST"])
@editor_required
def country_photo_import_web(country_slug: str) -> Response:
    from .db import get_db
    from .services.city_photos import download_web_image, save_country_photo_to_library
    conn = get_db()
    row = conn.execute("SELECT country_id FROM dim_country WHERE country_slug = ?", (country_slug,)).fetchone()
    if not row:
        return jsonify({"error": "Pays introuvable.", "imported": 0})
    data = request.get_json(silent=True)
    if not data or not isinstance(data.get("images"), list):
        return jsonify({"error": "Aucune image.", "imported": 0})
    imported = 0
    for img in data["images"]:
        url = img.get("url", "")
        if not url:
            continue
        result = download_web_image(url)
        if not result:
            continue
        file_bytes, ext = result
        save_result = save_country_photo_to_library(
            conn, row["country_id"], country_slug, file_bytes, f"web-import{ext}",
            source_url=img.get("source_page", ""),
            attribution="Wikipedia/Wikimedia — vérifier les licences.",
            image_url=url,
        )
        if save_result["success"]:
            imported += 1
    if imported:
        log_action("upload_photo", "country", country_slug, f"{imported} photo(s) importée(s) depuis le web pour le pays {country_slug}")
    return jsonify({"imported": imported})


@web.route("/countries/<country_slug>/photos/<int:photo_id>/delete", methods=["POST"])
@editor_required
def country_photo_delete(country_slug: str, photo_id: int) -> Response:
    from .db import get_db
    from .services.city_photos import delete_country_photo_from_library
    conn = get_db()
    deleted = delete_country_photo_from_library(conn, photo_id, country_slug)
    if deleted:
        flash("Photo supprimée.", "success")
        log_action("delete_photo", "country", country_slug, f"Photo #{photo_id} supprimée du pays {country_slug}")
    else:
        flash("Photo introuvable.", "error")
    return redirect(url_for("web.country_detail", country_slug=country_slug))


@web.route("/countries/<country_slug>/photos/<int:photo_id>/primary", methods=["POST"])
@editor_required
def country_photo_set_primary(country_slug: str, photo_id: int) -> Response:
    from .db import get_db
    from .services.city_photos import set_country_photo_primary
    conn = get_db()
    row = conn.execute("SELECT country_id FROM dim_country WHERE country_slug = ?", (country_slug,)).fetchone()
    if not row:
        flash("Pays introuvable.", "error")
        return redirect(url_for("web.country_directory"))
    set_country_photo_primary(conn, photo_id, row["country_id"])
    flash("Photo principale mise à jour.", "success")
    log_action("update_photo", "country", country_slug, f"Photo #{photo_id} définie comme principale pour le pays {country_slug}")
    return redirect(url_for("web.country_detail", country_slug=country_slug))


# ------------------------------------------------------------------
#  Country Annotation routes
# ------------------------------------------------------------------

@web.route("/countries/<country_slug>/annotations/manual-search")
def country_annotation_manual_search(country_slug: str) -> Response:
    from .services.city_photos import _search_commons_batch
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"images": []})
    seen_urls: set[str] = set()
    images = _search_commons_batch(query, seen_urls, limit=40)
    return jsonify({"images": images})


@web.route("/countries/<country_slug>/annotations/<int:annotation_id>/photo/search")
def country_annotation_photo_search(country_slug: str, annotation_id: int) -> Response:
    from .db import get_db
    from .services.city_photos import search_annotation_images
    conn = get_db()
    country_row = conn.execute("SELECT country_name FROM dim_country WHERE country_slug = ?", (country_slug,)).fetchone()
    ann_row = conn.execute("SELECT annotation_label FROM dim_annotation WHERE annotation_id = ?", (annotation_id,)).fetchone()
    if not country_row or not ann_row:
        return jsonify({"error": "Introuvable.", "images": []})
    images = search_annotation_images(ann_row["annotation_label"], country_row["country_name"], None, None)
    return jsonify({"images": images})


@web.route("/countries/<country_slug>/annotations/<int:annotation_id>/photo/save", methods=["POST"])
@editor_required
def country_annotation_photo_save(country_slug: str, annotation_id: int) -> Response:
    from .db import get_db
    from .services.city_photos import save_annotation_photo_for_country
    conn = get_db()
    data = request.get_json(silent=True)
    if not data or not data.get("url"):
        return jsonify({"success": False, "error": "URL manquante."})
    result = save_annotation_photo_for_country(
        conn, annotation_id, data["url"], data.get("source_page", ""), country_slug=country_slug
    )
    if result.get("success"):
        log_action("upload_photo", "annotation", str(annotation_id),
                   f"Photo d'annotation sauvegardée pour le pays {country_slug}, annotation #{annotation_id}")
    return jsonify(result)


@web.route("/countries/<country_slug>/annotations/<int:annotation_id>/photo/link", methods=["POST"])
@editor_required
def country_annotation_photo_link(country_slug: str, annotation_id: int) -> Response:
    from .db import get_db
    from .services.city_photos import link_existing_country_photo_to_annotation
    conn = get_db()
    data = request.get_json(silent=True)
    if not data or not data.get("photo_id"):
        return jsonify({"success": False, "error": "photo_id manquant."})
    result = link_existing_country_photo_to_annotation(conn, annotation_id, country_slug, int(data["photo_id"]))
    if result.get("success"):
        log_action("link_photo", "annotation", str(annotation_id),
                   f"Photo #{data['photo_id']} liée à l'annotation #{annotation_id} du pays {country_slug}")
    return jsonify(result)


@web.route("/countries/<country_slug>/annotations/years")
def country_annotation_years(country_slug: str) -> Response:
    from .db import get_db
    conn = get_db()
    rows = conn.execute(
        """SELECT fcp.year, fcp.annotation_id
           FROM fact_country_population fcp
           JOIN dim_country c ON c.country_id = fcp.country_id
           WHERE c.country_slug = ?
           ORDER BY fcp.year""",
        (country_slug,),
    ).fetchall()
    years = [{"year": r["year"], "has_annotation": r["annotation_id"] is not None} for r in rows]
    return jsonify({"years": years})


@web.route("/countries/<country_slug>/annotations", methods=["POST"])
@editor_required
def country_annotation_create(country_slug: str) -> Response:
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
    pop_row = conn.execute(
        """SELECT fcp.country_pop_id, fcp.annotation_id
           FROM fact_country_population fcp
           JOIN dim_country c ON c.country_id = fcp.country_id
           WHERE c.country_slug = ? AND fcp.year = ?""",
        (country_slug, year),
    ).fetchone()
    if not pop_row:
        return jsonify({"success": False, "error": f"Année {year} introuvable pour ce pays."})
    if pop_row["annotation_id"]:
        return jsonify({"success": False, "error": f"L'année {year} a déjà une annotation."})
    cur = conn.execute(
        "INSERT INTO dim_annotation (annotation_label, annotation_color, annotation_type) VALUES (?, ?, ?)",
        (label, color, ann_type),
    )
    annotation_id = cur.lastrowid
    conn.execute(
        "UPDATE fact_country_population SET annotation_id = ? WHERE country_pop_id = ?",
        (annotation_id, pop_row["country_pop_id"]),
    )
    conn.commit()
    log_action("create", "annotation", str(annotation_id),
               f"Annotation créée pour le pays {country_slug}, année {year}: {label}")
    return jsonify({"success": True, "annotation_id": annotation_id})


@web.route("/countries/<country_slug>/annotations/<int:annotation_id>", methods=["PUT"])
@editor_required
def country_annotation_update(country_slug: str, annotation_id: int) -> Response:
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
    updates = ["annotation_label = ?"]
    params: list = [label]
    if color:
        updates.append("annotation_color = ?")
        params.append(color)
    if ann_type:
        updates.append("annotation_type = ?")
        params.append(ann_type)
    params.append(annotation_id)
    conn.execute(f"UPDATE dim_annotation SET {', '.join(updates)} WHERE annotation_id = ?", params)
    if new_year is not None:
        try:
            new_year = int(new_year)
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "Année invalide."})
        old_pop = conn.execute(
            """SELECT fcp.country_pop_id, fcp.year
               FROM fact_country_population fcp
               JOIN dim_country c ON c.country_id = fcp.country_id
               WHERE c.country_slug = ? AND fcp.annotation_id = ?""",
            (country_slug, annotation_id),
        ).fetchone()
        if not old_pop or old_pop["year"] != new_year:
            new_pop = conn.execute(
                """SELECT fcp.country_pop_id, fcp.annotation_id
                   FROM fact_country_population fcp
                   JOIN dim_country c ON c.country_id = fcp.country_id
                   WHERE c.country_slug = ? AND fcp.year = ?""",
                (country_slug, new_year),
            ).fetchone()
            if not new_pop:
                return jsonify({"success": False, "error": f"Année {new_year} introuvable."})
            if new_pop["annotation_id"] and new_pop["annotation_id"] != annotation_id:
                return jsonify({"success": False, "error": f"L'année {new_year} a déjà une annotation."})
            if old_pop:
                conn.execute("UPDATE fact_country_population SET annotation_id = NULL WHERE country_pop_id = ?", (old_pop["country_pop_id"],))
            conn.execute("UPDATE fact_country_population SET annotation_id = ? WHERE country_pop_id = ?", (annotation_id, new_pop["country_pop_id"]))
    conn.commit()
    log_action("update", "annotation", str(annotation_id),
               f"Annotation #{annotation_id} mise à jour pour le pays {country_slug}: {label}")
    return jsonify({"success": True})


@web.route("/countries/<country_slug>/annotations/<int:annotation_id>", methods=["DELETE"])
@editor_required
def country_annotation_delete(country_slug: str, annotation_id: int) -> Response:
    from .db import get_db
    from .services.city_photos import ANNOTATION_PHOTO_DIR
    conn = get_db()
    ann = conn.execute("SELECT photo_filename FROM dim_annotation WHERE annotation_id = ?", (annotation_id,)).fetchone()
    if not ann:
        return jsonify({"success": False, "error": "Annotation introuvable."})
    conn.execute("UPDATE fact_country_population SET annotation_id = NULL WHERE annotation_id = ?", (annotation_id,))
    if ann["photo_filename"]:
        from pathlib import Path as _Path
        photo_path = ANNOTATION_PHOTO_DIR / ann["photo_filename"]
        if photo_path.exists():
            photo_path.unlink()
    conn.execute("DELETE FROM dim_annotation WHERE annotation_id = ?", (annotation_id,))
    conn.commit()
    log_action("delete", "annotation", str(annotation_id),
               f"Annotation #{annotation_id} supprimée du pays {country_slug}")
    return jsonify({"success": True})


@web.route("/countries/<country_slug>/delete", methods=["POST"])
@editor_required
def country_delete(country_slug: str) -> Response:
    """Delete a country and all its related data from the DB and filesystem."""
    import shutil as _shutil
    from .db import get_db
    conn = get_db()
    row = conn.execute(
        "SELECT country_id, country_name FROM dim_country WHERE country_slug = ?",
        (country_slug,),
    ).fetchone()
    if not row:
        if request.is_json:
            return jsonify({"success": False, "error": "Pays introuvable."})
        flash("Pays introuvable.", "error")
        return redirect(url_for("web.country_directory"))
    country_id = row["country_id"]
    conn.execute(
        "UPDATE fact_country_population SET annotation_id = NULL WHERE country_id = ?",
        (country_id,),
    )
    conn.execute("DELETE FROM fact_country_population WHERE country_id = ?", (country_id,))
    conn.execute("DELETE FROM dim_country_photo WHERE country_id = ?", (country_id,))
    conn.execute("DELETE FROM dim_country WHERE country_id = ?", (country_id,))
    conn.commit()
    from pathlib import Path
    static = Path(current_app.static_folder)
    country_photo_dir = static / "images" / "countries" / country_slug
    if country_photo_dir.exists():
        _shutil.rmtree(str(country_photo_dir))
    flag_file = static / "images" / "flags" / "countries" / f"{country_slug}.png"
    if flag_file.exists():
        flag_file.unlink()
    data_root = Path(current_app.root_path).parent / "data"
    delete_raw_document(
        "country",
        country_slug,
        "period_detail",
        fallback_path=data_root / "country_details" / f"{country_slug}.txt",
    )
    delete_raw_document(
        "country",
        country_slug,
        "fiche",
        fallback_path=data_root / "country_fiches" / f"{country_slug}.txt",
    )
    conn.commit()
    log_action("delete", "country", country_slug, f"Pays '{row['country_name']}' supprimé avec toutes ses données")
    if request.is_json:
        return jsonify({"success": True})
    flash(f"Pays '{row['country_name']}' supprimé.", "success")
    return redirect(url_for("web.country_directory"))


@web.route("/countries/flags/download-missing", methods=["POST"])
@editor_required
def download_missing_country_flags() -> Response:
    """Download flags for all countries that don't have one yet."""
    from .db import get_db
    from .services.city_import import download_country_flag

    conn = get_db()
    rows = conn.execute("SELECT country_name, country_slug FROM dim_country").fetchall()

    downloaded = 0
    failed = 0
    for r in rows:
        slug = r["country_slug"]
        flag_file = Path(current_app.static_folder) / "images" / "flags" / "countries" / f"{slug}.png"
        if flag_file.exists():
            continue
        result = download_country_flag(r["country_name"], slug)
        if result:
            downloaded += 1
        else:
            failed += 1

    return jsonify({
        "success": True,
        "downloaded": downloaded,
        "failed": failed,
        "message": f"{downloaded} drapeau(x) téléchargé(s), {failed} échoué(s).",
    })


def _build_region_periods_from_db(conn, region_id: int, pop_data: list[dict]) -> list[dict]:
    """Build timeline period dicts from dim_region_period_detail (same format as _parse_country_periods)."""
    import re as _re

    pop_by_year: dict[int, int] = {r["year"]: r["population"] for r in pop_data}
    annotations_by_year: dict[int, dict] = {}
    for r in pop_data:
        if r.get("annotation_id"):
            annotations_by_year[r["year"]] = r

    def _extract_emoji(value: str):
        stripped = value.strip()
        m = _re.match(r"^([^\w\s]+)\s*(.*)", stripped, flags=_re.UNICODE)
        if m:
            return m.group(1).strip(), m.group(2).strip()
        return "•", stripped

    period_rows = conn.execute(
        """SELECT region_period_id, period_order, period_range_label, period_title,
                  start_year, end_year, summary_text
           FROM dim_region_period_detail
           WHERE region_id = ?
           ORDER BY period_order""",
        (region_id,),
    ).fetchall()

    total = len(period_rows)
    periods: list[dict] = []

    for i, pr in enumerate(period_rows):
        item_rows = conn.execute(
            "SELECT item_text FROM dim_region_period_detail_item "
            "WHERE region_period_id = ? ORDER BY item_order",
            (pr["region_period_id"],),
        ).fetchall()

        bullets: list[dict] = []
        seen: set[str] = set()
        for row in item_rows:
            item = row["item_text"].strip().lstrip("- ").strip()
            if not item or item.lower().startswith("résumé"):
                continue
            icon, text = _extract_emoji(item)
            if not text or text in seen:
                continue
            seen.add(text)
            bullets.append({"icon": icon, "text": text})

        sy, ey = pr["start_year"], pr["end_year"]
        start_pop = end_pop = None
        if sy is not None and ey is not None:
            candidates = [y for y in pop_by_year if sy <= y <= ey]
            if candidates:
                start_pop = pop_by_year[min(candidates)]
                end_pop = pop_by_year[max(candidates)]

        pct = None
        if start_pop and end_pop and start_pop > 0:
            pct = round((end_pop - start_pop) / start_pop * 100, 1)

        linked: list[dict] = []
        if sy is not None and ey is not None:
            for y, ann in sorted(annotations_by_year.items()):
                if sy <= y <= ey:
                    linked.append({
                        "year": y,
                        "label": ann.get("label", ""),
                        "color": ann.get("color", "#ef6c3d"),
                    })

        range_label = (pr["period_range_label"] or "")
        periods.append({
            "period_range_label": range_label,
            "period_title": pr["period_title"],
            "start_year": sy,
            "end_year": ey,
            "start_population": f"{start_pop:,}".replace(",", "\u202f") if start_pop else "n/a",
            "end_population": f"{end_pop:,}".replace(",", "\u202f") if end_pop else "n/a",
            "population_change_pct": pct,
            "display_bullets": bullets,
            "summary_text": pr["summary_text"] or "",
            "linked_annotations": linked,
            "step_index": i + 1,
            "step_total": total,
        })

    return periods


# ---------------------------------------------------------------------------
# Regions directory + detail
# ---------------------------------------------------------------------------

@web.route("/regions")
def region_directory() -> str:
    import os
    from .db import get_db
    conn = get_db()
    view_mode = request.args.get("view", "small").strip().lower()
    if view_mode not in {"large", "medium", "small", "compact"}:
        view_mode = "small"
    rows = conn.execute(
        """
        WITH latest AS (
            SELECT region_id, MAX(year) AS year
            FROM fact_region_population
            GROUP BY region_id
        ),
        first_row AS (
            SELECT region_id, MIN(year) AS first_year
            FROM fact_region_population
            GROUP BY region_id
        ),
        peak AS (
            SELECT region_id,
                   population AS peak_population,
                   year AS peak_year
            FROM (
                SELECT region_id, year, population,
                       ROW_NUMBER() OVER (
                           PARTITION BY region_id
                           ORDER BY population DESC, year ASC
                       ) AS rn
                FROM fact_region_population
            ) ranked_peak
            WHERE rn = 1
        )
        SELECT
            dr.region_id,
            dr.region_name,
            dr.region_slug,
            dr.country_name,
            dr.region_color,
            frp.population AS latest_population,
            latest.year AS latest_year,
            peak.peak_population,
            peak.peak_year,
            first_row.first_year,
            dr.created_at AS entity_created_at,
            dr.updated_at AS entity_updated_at,
            COALESCE(au_c.display_name, au_c.username) AS created_by_name,
            COALESCE(au_u.display_name, au_u.username) AS updated_by_name
        FROM dim_region dr
        LEFT JOIN latest ON latest.region_id = dr.region_id
        LEFT JOIN fact_region_population frp
            ON frp.region_id = dr.region_id AND frp.year = latest.year
        LEFT JOIN peak ON peak.region_id = dr.region_id
        LEFT JOIN first_row ON first_row.region_id = dr.region_id
        LEFT JOIN app_user au_c ON au_c.user_id = dr.created_by_user_id
        LEFT JOIN app_user au_u ON au_u.user_id = dr.updated_by_user_id
        ORDER BY dr.country_name, dr.region_name
        """
    ).fetchall()
    regions = []
    for row in rows:
        r = dict(row)
        slug = r.get("region_slug") or ""
        # Flag first, then primary photo, else None
        flag_path = f"images/flags/regions/{slug}.png"
        flag_full = os.path.join(current_app.static_folder, flag_path.replace("/", os.sep))
        if os.path.exists(flag_full):
            r["card_image"] = flag_path
            r["card_image_type"] = "flag"
        else:
            # Try primary photo
            photo_row = conn.execute(
                "SELECT filename FROM dim_region_photo WHERE region_id = ? AND is_primary = TRUE LIMIT 1",
                (r["region_id"],),
            ).fetchone()
            if photo_row:
                r["card_image"] = f"images/regions/{slug}/{photo_row['filename']}"
                r["card_image_type"] = "photo"
            else:
                r["card_image"] = None
                r["card_image_type"] = None
        regions.append(r)
    return render_template(
        "web/regions.html",
        page_title="Annuaire des régions",
        view_mode=view_mode,
        regions=regions,
    )


@web.route("/regions/<region_slug>")
def region_detail(region_slug: str) -> str:
    import os
    from .db import get_db
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM dim_region WHERE region_slug = ?", (region_slug,)
    ).fetchone()
    if row is None:
        flash("Région introuvable dans la base analytique.", "error")
        return redirect(url_for("web.region_directory"))
    region = dict(row)
    pop_rows = conn.execute(
        """SELECT year, population, is_key_year, annotation_id
           FROM fact_region_population
           WHERE region_id = ?
           ORDER BY year""",
        (region["region_id"],),
    ).fetchall()
    pop_data = [dict(r) for r in pop_rows]
    latest = max(pop_data, key=lambda r: r["year"]) if pop_data else {}
    peak = max(pop_data, key=lambda r: r["population"]) if pop_data else {}
    first = min(pop_data, key=lambda r: r["year"]) if pop_data else {}
    region["latest_population"] = latest.get("population")
    region["latest_year"] = latest.get("year")
    region["peak_population"] = peak.get("population")
    region["peak_year"] = peak.get("year")
    region["first_year"] = first.get("year")
    region["first_population"] = first.get("population")
    # Trend
    if len(pop_data) >= 2:
        delta = pop_data[-1]["population"] - pop_data[-2]["population"]
        region["trend_label"] = "En croissance" if delta > 0 else ("En décroissance" if delta < 0 else "Stable")
    else:
        region["trend_label"] = "Stable"
    # Flag path
    flag_path = f"images/flags/regions/{region_slug}.png"
    flag_full = os.path.join(current_app.static_folder, flag_path.replace("/", os.sep))
    region["flag_path"] = flag_path if os.path.exists(flag_full) else None
    # Primary photo
    photo_row = conn.execute(
        "SELECT filename, source_url, attribution FROM dim_region_photo "
        "WHERE region_id = ? AND is_primary = TRUE LIMIT 1",
        (region["region_id"],),
    ).fetchone()
    region["photo_path"] = (
        f"images/regions/{region_slug}/{photo_row['filename']}" if photo_row else None
    )
    region["photo_attribution"] = photo_row["attribution"] if photo_row else None
    # Chart payload
    years = [r["year"] for r in pop_data]
    populations = [r["population"] for r in pop_data]
    # Build indexed annotations for chart (same format as city)
    ann_chart_rows = conn.execute(
        """SELECT frp.year, da.annotation_id, da.annotation_label, da.annotation_color,
                  da.annotation_type, da.photo_filename
           FROM fact_region_population frp
           JOIN dim_annotation da ON da.annotation_id = frp.annotation_id
           WHERE frp.region_id = ?
           ORDER BY frp.year""",
        (region["region_id"],),
    ).fetchall()
    default_band_width = 2
    if len(years) > 1:
        default_band_width = max(1, round((years[1] - years[0]) / 4))
    indexed_annotations = []
    for idx, row in enumerate(ann_chart_rows):
        photo_url = ""
        if row["photo_filename"]:
            photo_url = f"/static/images/annotations/{row['photo_filename']}"
        indexed_annotations.append({
            "id": f"annotation-{idx}",
            "year": row["year"],
            "label": row["annotation_label"],
            "color": row["annotation_color"] or "#ef6c3d",
            "type": row["annotation_type"],
            "xMin": row["year"] - default_band_width,
            "xMax": row["year"] + default_band_width,
            "photoUrl": photo_url,
        })
    chart_payload = {
        "labels": years,
        "datasets": [{
            "label": region["region_name"],
            "data": populations,
            "borderColor": region.get("region_color") or "#2f6fed",
            "backgroundColor": (region.get("region_color") or "#2f6fed") + "22",
            "fill": True,
            "tension": 0.3,
        }],
        "annotations": indexed_annotations,
    }
    # Periods from DB
    ann_rows = conn.execute(
        """SELECT frp.year, da.annotation_label AS label, da.annotation_color AS color
           FROM fact_region_population frp
           JOIN dim_annotation da ON da.annotation_id = frp.annotation_id
           WHERE frp.region_id = ?""",
        (region["region_id"],),
    ).fetchall()
    ann_by_year = {r["year"]: {"annotation_id": 1, "label": r["label"], "color": r["color"]} for r in ann_rows}
    pop_with_ann = [{**r, **(ann_by_year.get(r["year"], {}))} for r in pop_data]
    periods = _build_region_periods_from_db(conn, region["region_id"], pop_with_ann)
    # Fiche complète
    fiche_path = Path(current_app.root_path).parent / "data" / "region_fiches" / f"{region_slug}.txt"
    fiche = None
    raw_fiche = load_raw_document("region", region_slug, "fiche", fallback_path=fiche_path)
    if raw_fiche:
        _header, fiche_sections = parse_fiche_text(raw_fiche)
        if fiche_sections:
            fiche = {"raw_text": raw_fiche, "sections": [
                {"emoji": s.get("emoji", ""), "title": s.get("title", ""), "blocks": s.get("blocks", [])}
                for s in fiche_sections
            ]}
    # Annotations
    ann_rows = conn.execute(
        """SELECT frp.year, da.annotation_id, da.annotation_label, da.annotation_color,
                  da.annotation_type, da.photo_filename AS annotation_photo_filename
           FROM fact_region_population frp
           JOIN dim_annotation da ON da.annotation_id = frp.annotation_id
           WHERE frp.region_id = ?
           ORDER BY frp.year""",
        (region["region_id"],),
    ).fetchall()
    annotations = [dict(r) for r in ann_rows]
    # Region photos
    from .services.city_photos import get_region_photos, count_missing_photos
    region_photos = get_region_photos(conn, region_slug)
    missing_photos_count = count_missing_photos(conn, "region", region_slug)
    return render_template(
        "web/region_detail.html",
        page_title=region["region_name"],
        region=region,
        pop_data=pop_data,
        periods=periods,
        chart_payload=chart_payload,
        fiche=fiche,
        annotations=annotations,
        region_photos=region_photos,
        missing_photos_count=missing_photos_count,
    )


# ------------------------------------------------------------------
#  Region Photo Library routes
# ------------------------------------------------------------------

@web.route("/regions/<region_slug>/photos/upload", methods=["POST"])
@editor_required
def region_photo_upload(region_slug: str) -> Response:
    from .db import get_db
    from .services.city_photos import save_region_photo_to_library
    conn = get_db()
    row = conn.execute("SELECT region_id FROM dim_region WHERE region_slug = ?", (region_slug,)).fetchone()
    if not row:
        flash("Région introuvable.", "error")
        return redirect(url_for("web.region_directory"))
    files = request.files.getlist("photo_files")
    if not files or all(not f.filename for f in files):
        flash("Aucun fichier sélectionné.", "error")
        return redirect(url_for("web.region_detail", region_slug=region_slug))
    imported = 0
    for f in files:
        if not f.filename:
            continue
        result = save_region_photo_to_library(
            conn, row["region_id"], region_slug, f.read(), f.filename,
            attribution="Photo uploadée manuellement.",
        )
        if result["success"]:
            imported += 1
    log_action("upload_photo", "region", region_slug, f"{imported} photo(s) uploadée(s) pour la région {region_slug}")
    flash(f"{imported} photo(s) ajoutée(s) à la bibliothèque.", "success")
    return redirect(url_for("web.region_detail", region_slug=region_slug))


@web.route("/regions/<region_slug>/photos/search")
def region_photo_search(region_slug: str) -> Response:
    from .db import get_db
    from .services.city_photos import search_wikipedia_images
    conn = get_db()
    row = conn.execute("SELECT region_name, country_name FROM dim_region WHERE region_slug = ?", (region_slug,)).fetchone()
    if not row:
        return jsonify({"error": "Région introuvable.", "images": []})
    images = search_wikipedia_images(row["region_name"], None, row["country_name"])
    return jsonify({"images": images})


@web.route("/regions/<region_slug>/photos/search-commons")
def region_photo_search_commons(region_slug: str) -> Response:
    from .db import get_db
    from .services.city_photos import search_commons_images
    conn = get_db()
    row = conn.execute("SELECT region_name, country_name FROM dim_region WHERE region_slug = ?", (region_slug,)).fetchone()
    if not row:
        return jsonify({"error": "Région introuvable.", "images": []})
    images = search_commons_images(row["region_name"], None, row["country_name"])
    return jsonify({"images": images})


@web.route("/regions/<region_slug>/photos/import-web", methods=["POST"])
@editor_required
def region_photo_import_web(region_slug: str) -> Response:
    from .db import get_db
    from .services.city_photos import download_web_image, save_region_photo_to_library
    conn = get_db()
    row = conn.execute("SELECT region_id FROM dim_region WHERE region_slug = ?", (region_slug,)).fetchone()
    if not row:
        return jsonify({"error": "Région introuvable.", "imported": 0})
    data = request.get_json(silent=True)
    if not data or not isinstance(data.get("images"), list):
        return jsonify({"error": "Aucune image.", "imported": 0})
    imported = 0
    for img in data["images"]:
        url = img.get("url", "")
        if not url:
            continue
        result = download_web_image(url)
        if not result:
            continue
        file_bytes, ext = result
        save_result = save_region_photo_to_library(
            conn, row["region_id"], region_slug, file_bytes, f"web-import{ext}",
            source_url=img.get("source_page", ""),
            attribution="Wikipedia/Wikimedia — vérifier les licences.",
            image_url=url,
        )
        if save_result["success"]:
            imported += 1
    if imported:
        log_action("upload_photo", "region", region_slug, f"{imported} photo(s) importée(s) depuis le web pour la région {region_slug}")
    return jsonify({"imported": imported})


@web.route("/regions/<region_slug>/photos/<int:photo_id>/delete", methods=["POST"])
@editor_required
def region_photo_delete(region_slug: str, photo_id: int) -> Response:
    from .db import get_db
    from .services.city_photos import delete_region_photo_from_library
    conn = get_db()
    deleted = delete_region_photo_from_library(conn, photo_id, region_slug)
    if deleted:
        log_action("delete_photo", "region", region_slug, f"Photo #{photo_id} supprimée de la région {region_slug}")
        flash("Photo supprimée.", "success")
    else:
        flash("Photo introuvable.", "error")
    return redirect(url_for("web.region_detail", region_slug=region_slug))


@web.route("/regions/<region_slug>/photos/<int:photo_id>/primary", methods=["POST"])
@editor_required
def region_photo_set_primary(region_slug: str, photo_id: int) -> Response:
    from .db import get_db
    from .services.city_photos import set_region_photo_primary
    conn = get_db()
    row = conn.execute("SELECT region_id FROM dim_region WHERE region_slug = ?", (region_slug,)).fetchone()
    if not row:
        flash("Région introuvable.", "error")
        return redirect(url_for("web.region_directory"))
    set_region_photo_primary(conn, photo_id, row["region_id"])
    log_action("update_photo", "region", region_slug, f"Photo #{photo_id} définie comme principale pour la région {region_slug}")
    flash("Photo principale mise à jour.", "success")
    return redirect(url_for("web.region_detail", region_slug=region_slug))


# ------------------------------------------------------------------
#  Region Annotation routes
# ------------------------------------------------------------------

@web.route("/regions/<region_slug>/annotations/manual-search")
def region_annotation_manual_search(region_slug: str) -> Response:
    from .services.city_photos import _search_commons_batch
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"images": []})
    seen_urls: set[str] = set()
    images = _search_commons_batch(query, seen_urls, limit=40)
    return jsonify({"images": images})


@web.route("/regions/<region_slug>/annotations/<int:annotation_id>/photo/search")
def region_annotation_photo_search(region_slug: str, annotation_id: int) -> Response:
    from .db import get_db
    from .services.city_photos import search_annotation_images
    conn = get_db()
    region_row = conn.execute("SELECT region_name, country_name FROM dim_region WHERE region_slug = ?", (region_slug,)).fetchone()
    ann_row = conn.execute("SELECT annotation_label FROM dim_annotation WHERE annotation_id = ?", (annotation_id,)).fetchone()
    if not region_row or not ann_row:
        return jsonify({"error": "Introuvable.", "images": []})
    images = search_annotation_images(ann_row["annotation_label"], region_row["region_name"], None, region_row["country_name"])
    return jsonify({"images": images})


@web.route("/regions/<region_slug>/annotations/<int:annotation_id>/photo/save", methods=["POST"])
@editor_required
def region_annotation_photo_save(region_slug: str, annotation_id: int) -> Response:
    from .db import get_db
    from .services.city_photos import save_annotation_photo_for_region
    conn = get_db()
    data = request.get_json(silent=True)
    if not data or not data.get("url"):
        return jsonify({"success": False, "error": "URL manquante."})
    result = save_annotation_photo_for_region(
        conn, annotation_id, data["url"], data.get("source_page", ""), region_slug=region_slug
    )
    if result.get("success"):
        log_action("upload_photo", "annotation", str(annotation_id),
                   f"Photo d'annotation sauvegardée pour la région {region_slug}, annotation #{annotation_id}")
    return jsonify(result)


@web.route("/regions/<region_slug>/annotations/<int:annotation_id>/photo/link", methods=["POST"])
@editor_required
def region_annotation_photo_link(region_slug: str, annotation_id: int) -> Response:
    from .db import get_db
    from .services.city_photos import link_existing_region_photo_to_annotation
    conn = get_db()
    data = request.get_json(silent=True)
    if not data or not data.get("photo_id"):
        return jsonify({"success": False, "error": "photo_id manquant."})
    result = link_existing_region_photo_to_annotation(conn, annotation_id, region_slug, int(data["photo_id"]))
    if result.get("success"):
        log_action("link_photo", "annotation", str(annotation_id),
                   f"Photo #{data['photo_id']} liée à l'annotation #{annotation_id} de la région {region_slug}")
    return jsonify(result)


@web.route("/regions/<region_slug>/annotations/years")
def region_annotation_years(region_slug: str) -> Response:
    from .db import get_db
    conn = get_db()
    rows = conn.execute(
        """SELECT frp.year, frp.annotation_id
           FROM fact_region_population frp
           JOIN dim_region r ON r.region_id = frp.region_id
           WHERE r.region_slug = ?
           ORDER BY frp.year""",
        (region_slug,),
    ).fetchall()
    years = [{"year": r["year"], "has_annotation": r["annotation_id"] is not None} for r in rows]
    return jsonify({"years": years})


@web.route("/regions/<region_slug>/annotations", methods=["POST"])
@editor_required
def region_annotation_create(region_slug: str) -> Response:
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
    pop_row = conn.execute(
        """SELECT frp.region_pop_id, frp.annotation_id
           FROM fact_region_population frp
           JOIN dim_region r ON r.region_id = frp.region_id
           WHERE r.region_slug = ? AND frp.year = ?""",
        (region_slug, year),
    ).fetchone()
    if not pop_row:
        return jsonify({"success": False, "error": f"Année {year} introuvable pour cette région."})
    if pop_row["annotation_id"]:
        return jsonify({"success": False, "error": f"L'année {year} a déjà une annotation."})
    cur = conn.execute(
        "INSERT INTO dim_annotation (annotation_label, annotation_color, annotation_type) VALUES (?, ?, ?)",
        (label, color, ann_type),
    )
    annotation_id = cur.lastrowid
    conn.execute(
        "UPDATE fact_region_population SET annotation_id = ? WHERE region_pop_id = ?",
        (annotation_id, pop_row["region_pop_id"]),
    )
    conn.commit()
    log_action("create", "annotation", str(annotation_id),
               f"Annotation créée pour la région {region_slug}, année {year}: {label}")
    return jsonify({"success": True, "annotation_id": annotation_id})


@web.route("/regions/<region_slug>/annotations/<int:annotation_id>", methods=["PUT"])
@editor_required
def region_annotation_update(region_slug: str, annotation_id: int) -> Response:
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
    updates = ["annotation_label = ?"]
    params: list = [label]
    if color:
        updates.append("annotation_color = ?")
        params.append(color)
    if ann_type:
        updates.append("annotation_type = ?")
        params.append(ann_type)
    params.append(annotation_id)
    conn.execute(f"UPDATE dim_annotation SET {', '.join(updates)} WHERE annotation_id = ?", params)
    if new_year is not None:
        try:
            new_year = int(new_year)
        except (ValueError, TypeError):
            return jsonify({"success": False, "error": "Année invalide."})
        old_pop = conn.execute(
            """SELECT frp.region_pop_id, frp.year
               FROM fact_region_population frp
               JOIN dim_region r ON r.region_id = frp.region_id
               WHERE r.region_slug = ? AND frp.annotation_id = ?""",
            (region_slug, annotation_id),
        ).fetchone()
        if not old_pop or old_pop["year"] != new_year:
            new_pop = conn.execute(
                """SELECT frp.region_pop_id, frp.annotation_id
                   FROM fact_region_population frp
                   JOIN dim_region r ON r.region_id = frp.region_id
                   WHERE r.region_slug = ? AND frp.year = ?""",
                (region_slug, new_year),
            ).fetchone()
            if not new_pop:
                return jsonify({"success": False, "error": f"Année {new_year} introuvable."})
            if new_pop["annotation_id"] and new_pop["annotation_id"] != annotation_id:
                return jsonify({"success": False, "error": f"L'année {new_year} a déjà une annotation."})
            if old_pop:
                conn.execute("UPDATE fact_region_population SET annotation_id = NULL WHERE region_pop_id = ?", (old_pop["region_pop_id"],))
            conn.execute("UPDATE fact_region_population SET annotation_id = ? WHERE region_pop_id = ?", (annotation_id, new_pop["region_pop_id"]))
    conn.commit()
    log_action("update", "annotation", str(annotation_id),
               f"Annotation #{annotation_id} mise à jour pour la région {region_slug}: {label}")
    return jsonify({"success": True})


@web.route("/regions/<region_slug>/annotations/<int:annotation_id>", methods=["DELETE"])
@editor_required
def region_annotation_delete(region_slug: str, annotation_id: int) -> Response:
    from .db import get_db
    from .services.city_photos import ANNOTATION_PHOTO_DIR
    conn = get_db()
    ann = conn.execute("SELECT photo_filename FROM dim_annotation WHERE annotation_id = ?", (annotation_id,)).fetchone()
    if not ann:
        return jsonify({"success": False, "error": "Annotation introuvable."})
    conn.execute("UPDATE fact_region_population SET annotation_id = NULL WHERE annotation_id = ?", (annotation_id,))
    if ann["photo_filename"]:
        photo_path = ANNOTATION_PHOTO_DIR / ann["photo_filename"]
        if photo_path.exists():
            photo_path.unlink()
    conn.execute("DELETE FROM dim_annotation WHERE annotation_id = ?", (annotation_id,))
    conn.commit()
    log_action("delete", "annotation", str(annotation_id),
               f"Annotation #{annotation_id} supprimée de la région {region_slug}")
    return jsonify({"success": True})


@web.route("/regions/<region_slug>/delete", methods=["POST"])
@editor_required
def region_delete(region_slug: str) -> Response:
    """Delete a region and all its related data from the DB and filesystem."""
    import shutil as _shutil
    from .db import get_db
    conn = get_db()
    row = conn.execute("SELECT region_id, region_name FROM dim_region WHERE region_slug = ?", (region_slug,)).fetchone()
    if not row:
        if request.is_json:
            return jsonify({"success": False, "error": "Région introuvable."})
        flash("Région introuvable.", "error")
        return redirect(url_for("web.region_directory"))
    region_id = row["region_id"]
    # Delete DB rows (cascade order)
    period_ids = [r[0] for r in conn.execute("SELECT region_period_id FROM dim_region_period_detail WHERE region_id = ?", (region_id,))]
    if period_ids:
        placeholders = ",".join("?" * len(period_ids))
        conn.execute(f"DELETE FROM dim_region_period_detail_item WHERE region_period_id IN ({placeholders})", period_ids)
    conn.execute("DELETE FROM dim_region_period_detail WHERE region_id = ?", (region_id,))
    conn.execute("UPDATE fact_region_population SET annotation_id = NULL WHERE region_id = ?", (region_id,))
    conn.execute("DELETE FROM fact_region_population WHERE region_id = ?", (region_id,))
    conn.execute("DELETE FROM dim_region_photo WHERE region_id = ?", (region_id,))
    conn.execute("DELETE FROM dim_region WHERE region_id = ?", (region_id,))
    conn.commit()
    # Delete filesystem files
    from pathlib import Path
    static = Path(current_app.static_folder)
    region_photo_dir = static / "images" / "regions" / region_slug
    if region_photo_dir.exists():
        _shutil.rmtree(str(region_photo_dir))
    flag_file = static / "images" / "flags" / "regions" / f"{region_slug}.png"
    if flag_file.exists():
        flag_file.unlink()
    data_root = Path(current_app.root_path).parent / "data"
    delete_raw_document(
        "region",
        region_slug,
        "period_detail",
        fallback_path=data_root / "region_details" / f"{region_slug}.txt",
    )
    delete_raw_document(
        "region",
        region_slug,
        "fiche",
        fallback_path=data_root / "region_fiches" / f"{region_slug}.txt",
    )
    conn.commit()
    log_action("delete", "region", region_slug, f"Région '{row['region_name']}' supprimée avec toutes ses données")
    if request.is_json:
        return jsonify({"success": True})
    flash(f"Région '{row['region_name']}' supprimée.", "success")
    return redirect(url_for("web.region_directory"))


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


@web.route("/map/event-time-travel")
def map_event_time_travel_data():
    """Return events with locations + city annotations for event time-travel mode.

    Response: {
        years: [sorted unique event_years],
        events: {event_slug: {name, slug, year, level, category, description,
                              locations: [{lat, lng, region, country, role, city_name, city_slug}],
                              primary_photo}},
        city_annotations: {city_slug: {name, region, country, color, lat, lng,
                                       annotations: [{year, label, color, type}],
                                       periods: [{range, title, start, end, summary}]}}
    }
    """
    from .db import get_db
    from .services.event_service import CATEGORY_LABELS, CATEGORY_EMOJIS, get_event_primary_photo

    conn = get_db()

    # ── 1. Load all events with their locations ──
    evt_rows = conn.execute(
        """
        SELECT e.event_id, e.event_name, e.event_slug, e.event_year,
               e.event_level, e.event_category, e.description,
               e.impact_population
        FROM dim_event e
        WHERE e.event_year IS NOT NULL
        ORDER BY e.event_year
        """
    ).fetchall()

    events: dict[str, dict] = {}
    year_set: set[int] = set()
    event_ids: list[int] = []
    affected_regions: set[tuple[str, str]] = set()

    for r in evt_rows:
        slug = r["event_slug"]
        yr = int(r["event_year"])
        year_set.add(yr)
        event_ids.append(r["event_id"])
        cat = r["event_category"] or "autre"
        events[slug] = {
            "name": r["event_name"],
            "slug": slug,
            "year": yr,
            "level": r["event_level"],
            "category": cat,
            "category_label": CATEGORY_LABELS.get(cat, cat),
            "category_emoji": CATEGORY_EMOJIS.get(cat, "📌"),
            "description": (r["description"] or "")[:300],
            "impact": (r["impact_population"] or "")[:200],
            "locations": [],
            "primary_photo": None,
        }

    # ── 2. Load locations for all events ──
    if event_ids:
        loc_rows = conn.execute(
            """
            SELECT el.event_id, el.region, el.country, el.role,
                   dc.city_name, dc.city_slug, dc.latitude, dc.longitude, dc.city_color
            FROM dim_event_location el
            LEFT JOIN dim_city dc ON dc.city_id = el.city_id
            LEFT JOIN dim_event de ON de.event_id = el.event_id
            WHERE el.event_id IN ({})
            ORDER BY el.event_id, el.role
            """.format(",".join("?" for _ in event_ids)),
            event_ids,
        ).fetchall()

        # Map event_id → slug
        eid_to_slug: dict[int, str] = {}
        for r in evt_rows:
            eid_to_slug[r["event_id"]] = r["event_slug"]

        for lr in loc_rows:
            slug = eid_to_slug.get(lr["event_id"])
            if not slug or slug not in events:
                continue
            loc = {
                "region": lr["region"],
                "country": lr["country"],
                "role": lr["role"],
                "city_name": lr["city_name"],
                "city_slug": lr["city_slug"],
                "lat": lr["latitude"],
                "lng": lr["longitude"],
                "color": lr["city_color"] or "#e74c3c",
            }
            events[slug]["locations"].append(loc)
            if lr["region"] and lr["country"]:
                affected_regions.add((lr["region"], lr["country"]))

    # ── 3. Get primary photo for each event ──
    for slug in events:
        photo = get_event_primary_photo(conn, slug)
        if photo:
            events[slug]["primary_photo"] = photo

    # ── 4. City annotations for affected regions ──
    city_annotations: dict[str, dict] = {}
    if affected_regions:
        # Get cities in affected regions
        region_clauses = " OR ".join(
            "(c.region = ? AND c.country = ?)" for _ in affected_regions
        )
        region_params: list[str] = []
        for reg, cty in affected_regions:
            region_params.extend([reg, cty])

        city_rows = conn.execute(
            f"""
            SELECT c.city_id, c.city_name, c.city_slug, c.region, c.country,
                   c.city_color, c.latitude, c.longitude
            FROM dim_city c
            WHERE ({region_clauses})
              AND c.latitude IS NOT NULL
              AND c.longitude IS NOT NULL
            ORDER BY c.city_slug
            """,
            region_params,
        ).fetchall()

        city_id_map: dict[int, str] = {}
        for cr in city_rows:
            cslug = cr["city_slug"]
            city_id_map[cr["city_id"]] = cslug
            city_annotations[cslug] = {
                "name": cr["city_name"],
                "region": cr["region"],
                "country": cr["country"],
                "color": cr["city_color"] or "#2f6fed",
                "lat": cr["latitude"],
                "lng": cr["longitude"],
                "annotations": [],
                "periods": [],
            }

        # Fetch annotations for these cities
        if city_id_map:
            cids = list(city_id_map.keys())
            ann_rows = conn.execute(
                """
                SELECT f.city_id, f.year,
                       a.annotation_label, a.annotation_color, a.annotation_type
                FROM fact_city_population f
                JOIN dim_annotation a ON a.annotation_id = f.annotation_id
                WHERE f.city_id IN ({})
                  AND a.annotation_label IS NOT NULL
                ORDER BY f.city_id, f.year
                """.format(",".join("?" for _ in cids)),
                cids,
            ).fetchall()
            for ar in ann_rows:
                cslug = city_id_map.get(ar["city_id"])
                if cslug and cslug in city_annotations:
                    city_annotations[cslug]["annotations"].append({
                        "year": ar["year"],
                        "label": ar["annotation_label"],
                        "color": ar["annotation_color"],
                        "type": ar["annotation_type"],
                    })

            # Fetch periods for these cities
            period_rows = conn.execute(
                """
                SELECT c.city_slug,
                       cpd.period_range_label, cpd.period_title,
                       cpd.start_year, cpd.end_year, cpd.summary_text
                FROM dim_city_period_detail cpd
                JOIN dim_city c ON c.city_id = cpd.city_id
                WHERE c.city_id IN ({})
                ORDER BY c.city_slug, cpd.period_order
                """.format(",".join("?" for _ in cids)),
                cids,
            ).fetchall()
            for pr in period_rows:
                cslug = pr["city_slug"]
                if cslug in city_annotations:
                    city_annotations[cslug]["periods"].append({
                        "range": pr["period_range_label"],
                        "title": pr["period_title"],
                        "start": pr["start_year"],
                        "end": pr["end_year"],
                        "summary": pr["summary_text"],
                    })

    return jsonify({
        "years": sorted(year_set),
        "events": events,
        "city_annotations": city_annotations,
    })


@web.route("/map/monument-time-travel")
def map_monument_time_travel_data():
    """Return monuments with temporal data for monument time-travel mode.

    Response: {
        years: [sorted unique years spanning all construction/demolition],
        monuments: {monument_slug: {name, slug, construction_year, demolition_year,
                                     lat, lng, category, category_label, category_emoji,
                                     level, summary, architect, architectural_style,
                                     height_meters, floors,
                                     locations: [{region, country, role, city_name, city_slug}],
                                     primary_photo}}
    }
    """
    from .db import get_db
    from .services.monument_service import CATEGORY_LABELS, CATEGORY_EMOJIS, get_monument_primary_photo

    conn = get_db()

    # ── 1. Load all monuments with construction_year ──
    mon_rows = conn.execute(
        """
        SELECT m.monument_id, m.monument_name, m.monument_slug,
               m.construction_year, m.demolition_year,
               m.latitude, m.longitude,
               m.monument_category, m.monument_level,
               m.summary, m.architect, m.architectural_style,
               m.height_meters, m.floors
        FROM dim_monument m
        WHERE m.construction_year IS NOT NULL
        ORDER BY m.construction_year
        """
    ).fetchall()

    monuments: dict[str, dict] = {}
    year_set: set[int] = set()
    monument_ids: list[int] = []

    for r in mon_rows:
        slug = r["monument_slug"]
        cy = int(r["construction_year"])
        dy = int(r["demolition_year"]) if r["demolition_year"] else None
        year_set.add(cy)
        if dy:
            year_set.add(dy)
        monument_ids.append(r["monument_id"])
        cat = r["monument_category"] or "autre"
        monuments[slug] = {
            "name": r["monument_name"],
            "slug": slug,
            "construction_year": cy,
            "demolition_year": dy,
            "lat": float(r["latitude"]) if r["latitude"] else None,
            "lng": float(r["longitude"]) if r["longitude"] else None,
            "category": cat,
            "category_label": CATEGORY_LABELS.get(cat, cat),
            "category_emoji": CATEGORY_EMOJIS.get(cat, "📌"),
            "level": r["monument_level"],
            "summary": (r["summary"] or "")[:300],
            "architect": r["architect"] or "",
            "architectural_style": r["architectural_style"] or "",
            "height_meters": float(r["height_meters"]) if r["height_meters"] else None,
            "floors": r["floors"],
            "locations": [],
            "primary_photo": None,
        }

    # ── 2. Load locations for all monuments ──
    if monument_ids:
        loc_rows = conn.execute(
            """
            SELECT ml.monument_id, ml.region, ml.country, ml.role,
                   dc.city_name, dc.city_slug
            FROM dim_monument_location ml
            LEFT JOIN dim_city dc ON dc.city_id = ml.city_id
            WHERE ml.monument_id IN ({})
            ORDER BY ml.monument_id, ml.role
            """.format(",".join("?" for _ in monument_ids)),
            monument_ids,
        ).fetchall()

        mid_to_slug: dict[int, str] = {}
        for r in mon_rows:
            mid_to_slug[r["monument_id"]] = r["monument_slug"]

        for lr in loc_rows:
            slug = mid_to_slug.get(lr["monument_id"])
            if not slug or slug not in monuments:
                continue
            monuments[slug]["locations"].append({
                "region": lr["region"],
                "country": lr["country"],
                "role": lr["role"],
                "city_name": lr["city_name"],
                "city_slug": lr["city_slug"],
            })

    # ── 3. Get primary photo for each monument ──
    for slug in monuments:
        photo = get_monument_primary_photo(conn, slug)
        if photo:
            monuments[slug]["primary_photo"] = photo

    # ── 4. Build continuous year range ──
    if year_set:
        all_years = list(range(min(year_set), max(year_set) + 1))
    else:
        all_years = []

    return jsonify({
        "years": all_years,
        "monuments": monuments,
    })


@web.route("/map/city-spotlight/<city_slug>")
def map_city_spotlight(city_slug: str):
    """Return rich city data for the annotation spotlight panel."""
    from .db import get_db
    from .services.city_photos import get_city_photos

    service = AnalyticsService()
    filters = service.normalize_filters(request.args)
    city = service.get_city_detail(city_slug, filters)
    if city is None:
        return jsonify({"error": "Ville introuvable."}), 404

    conn = get_db()
    annotations = service.get_city_annotations(city_slug, filters)
    periods = service.get_city_periods(city_slug, filters)
    photos = get_city_photos(conn, city_slug)
    fiche = get_city_fiche(conn, city["city_id"])

    # Build simplified fiche sections
    fiche_sections = []
    if fiche:
        for s in fiche.get("sections", []):
            blocks_html = []
            for b in s.get("blocks", []):
                if b["type"] == "paragraph":
                    blocks_html.append(b["text"])
                elif b["type"] == "list":
                    blocks_html.append("<ul>" + "".join("<li>" + li + "</li>" for li in b["items"]) + "</ul>")
                elif b["type"] == "table":
                    rows_html = "".join(
                        "<tr>" + "".join("<td>" + cell + "</td>" for cell in row) + "</tr>"
                        for row in b.get("rows", [])
                    )
                    blocks_html.append("<table class='spotlight-table'>" + rows_html + "</table>")
            fiche_sections.append({
                "emoji": s["emoji"],
                "title": s["title"],
                "html": "".join(blocks_html),
            })

    # Build annotation list with photo URLs
    ann_list = []
    for a in annotations:
        photo_url = ""
        if a.get("annotation_photo_filename"):
            photo_url = f"/static/images/annotations/{a['annotation_photo_filename']}"
        ann_list.append({
            "year": a["year"],
            "label": a["annotation_label"],
            "color": a["annotation_color"] or "#ef6c3d",
            "type": a["annotation_type"],
            "photoUrl": photo_url,
        })

    # Build period summaries
    period_list = []
    for p in periods:
        linked = []
        for la in p.get("linked_annotations", []):
            linked.append({
                "year": la["year"],
                "label": la["label"],
                "color": la["color"],
                "photoUrl": la.get("photoUrl", ""),
            })
        period_list.append({
            "range": p["period_range_label"],
            "title": p["period_title"],
            "summary": p.get("summary_text", ""),
            "start_pop": p.get("start_population"),
            "end_pop": p.get("end_population"),
            "change_pct": p.get("population_change_pct"),
            "annotations": linked,
            "bullets": [b["text"] if isinstance(b, dict) else b for b in p.get("display_bullets", [])],
        })

    # Photo list
    photo_list = []
    for ph in photos[:8]:
        photo_list.append({
            "url": "/static/" + ph["photo_path"],
            "caption": ph.get("caption", ""),
            "isPrimary": bool(ph.get("is_primary")),
        })

    return jsonify({
        "city_name": city["city_name"],
        "city_slug": city["city_slug"],
        "country": city["country"],
        "region": city["region"],
        "city_color": city.get("city_color", "#2f6fed"),
        "population": city["latest_population"],
        "year": city["latest_year"],
        "peak_population": city.get("peak_population"),
        "peak_year": city.get("peak_year"),
        "first_population": city.get("first_population"),
        "first_population_year": city.get("first_population_year"),
        "trend_label": city.get("trend_label", ""),
        "trend_symbol": city.get("trend_symbol", ""),
        "photo_path": city.get("photo_path", ""),
        "has_photo": city.get("has_photo", False),
        "annotations": ann_list,
        "periods": period_list,
        "photos": photo_list,
        "fiche_sections": fiche_sections,
        "detail_url": f"/cities/{city_slug}",
    })


@web.route("/map/geocode-missing", methods=["POST"])
@editor_required
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

    geocoded = sum(1 for r in results if r["ok"])
    if geocoded:
        log_action("geocode", "city", None, f"Géocodage: {geocoded}/{len(rows)} villes géocodées")
    return jsonify({"total": len(rows), "geocoded": geocoded, "results": results})


@web.route("/sql-lab", methods=["GET", "POST"])
@editor_required
def sql_lab() -> str:
    service = AnalyticsService()
    sql = request.form.get("sql", "").strip()
    confirm_write = request.form.get("confirm_write") == "on"
    result: dict[str, object] | None = None

    if request.method == "POST" and sql:
        try:
            result = service.execute_sql(sql, confirm_write=confirm_write)
            if result["kind"] == "write":
                log_action("sql_write", "sql_lab", None, f"Requête SQL écriture exécutée", {"sql": sql[:500]})
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
@editor_required
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
@editor_required
def sql_lab_history_clear() -> Response:
    service = AnalyticsService()
    service.clear_sql_history()
    log_action("clear", "sql_lab", None, "Historique SQL effacé")
    flash("Historique SQL effacé.", "success")
    return redirect(url_for("web.sql_lab"))


@web.route("/sql-lab/views/save", methods=["POST"])
@editor_required
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
    log_action("create", "sql_view", None, f"Vue analytique sauvegardée: {request.form.get('view_name', '')}")
    flash("Vue analytique sauvegardée.", "success")
    return redirect(url_for("web.sql_lab"))


@web.route("/sql-lab/views/<view_id>/delete", methods=["POST"])
@editor_required
def sql_lab_view_delete(view_id: str) -> Response:
    service = AnalyticsService()
    service.delete_sql_view(view_id)
    log_action("delete", "sql_view", view_id, f"Vue analytique supprimée: {view_id}")
    flash("Vue analytique supprimée.", "success")
    return redirect(url_for("web.sql_lab"))


# ---------------------------------------------------------------------------
# Database Backup / Restore
# ---------------------------------------------------------------------------

# Tables in dependency order (parents before children).
_BACKUP_TABLES: list[dict] = [
    {"name": "dim_annotation", "pk": "annotation_id",
     "conflict": "(annotation_id)", "group": "shared"},
    {"name": "ref_population", "pk": "ref_pop_id",
     "conflict": "(country, region, year)", "group": "vrp"},
    {"name": "ref_city", "pk": "ref_city_id",
     "conflict": "(city_name, region, country)", "group": "vrp"},
    {"name": "dim_city", "pk": "city_id",
     "conflict": "(city_slug)", "group": "vrp"},
    {"name": "dim_time", "pk": "time_id",
     "conflict": "(year)", "group": "shared"},
    {"name": "dim_city_period_detail", "pk": "period_detail_id",
     "conflict": "(city_id, period_order, source_file)", "group": "vrp"},
    {"name": "dim_city_period_detail_item", "pk": "period_detail_item_id",
     "conflict": "(period_detail_id, item_order)", "group": "vrp"},
    {"name": "fact_city_population", "pk": "population_id",
     "conflict": "(city_id, year)", "group": "vrp"},
    {"name": "dim_city_fiche", "pk": "fiche_id",
     "conflict": "(city_id)", "group": "vrp"},
    {"name": "dim_city_fiche_section", "pk": "section_id",
     "conflict": "(fiche_id, section_order)", "group": "vrp"},
    {"name": "dim_city_photo", "pk": "photo_id", "conflict": None, "group": "vrp"},
    {"name": "dim_event", "pk": "event_id",
     "conflict": "(event_slug)", "group": "event"},
    {"name": "dim_event_location", "pk": "event_location_id", "conflict": None, "group": "event"},
    {"name": "dim_event_photo", "pk": "event_photo_id", "conflict": None, "group": "event"},
    {"name": "dim_person", "pk": "person_id",
     "conflict": "(person_slug)", "group": "person"},
    {"name": "dim_person_location", "pk": "person_location_id", "conflict": None, "group": "person"},
    {"name": "dim_person_photo", "pk": "person_photo_id", "conflict": None, "group": "person"},
    {"name": "dim_monument", "pk": "monument_id",
     "conflict": "(monument_slug)", "group": "monument"},
    {"name": "dim_monument_location", "pk": "monument_location_id", "conflict": None, "group": "monument"},
    {"name": "dim_monument_photo", "pk": "monument_photo_id", "conflict": None, "group": "monument"},
    {"name": "dim_country", "pk": "country_id",
     "conflict": "(country_slug)", "group": "vrp"},
    {"name": "fact_country_population", "pk": "country_pop_id",
     "conflict": "(country_id, year)", "group": "vrp"},
    {"name": "dim_country_photo", "pk": "photo_id", "conflict": None, "group": "vrp"},
    {"name": "dim_region", "pk": "region_id",
     "conflict": "(region_slug)", "group": "vrp"},
    {"name": "fact_region_population", "pk": "region_pop_id",
     "conflict": "(region_id, year)", "group": "vrp"},
    {"name": "dim_region_period_detail", "pk": "region_period_id",
     "conflict": "(region_id, period_order)", "group": "vrp"},
    {"name": "dim_region_period_detail_item", "pk": "item_id",
     "conflict": "(region_period_id, item_order)", "group": "vrp"},
    {"name": "dim_region_photo", "pk": "photo_id", "conflict": None, "group": "vrp"},
    {"name": "raw_document", "pk": "document_id",
     "conflict": "(entity_type, entity_slug, document_kind)", "group": "shared"},
    {"name": "app_setting", "pk": "setting_key",
     "conflict": "(setting_key)", "group": "shared"},
]

# Export scope definitions
_EXPORT_SCOPES = {
    "all":       {"label": "Tout", "groups": {"shared", "vrp", "event", "person", "monument"}},
    "vrp":       {"label": "Villes / Régions / Pays", "groups": {"shared", "vrp"}},
    "event":     {"label": "Événements", "groups": {"shared", "event"}},
    "person":    {"label": "Personnages", "groups": {"shared", "person"}},
    "monument":  {"label": "Monuments", "groups": {"shared", "monument"}},
    "delta_all": {"label": "Derniers ajouts — Tout", "groups": {"shared", "vrp", "event", "person", "monument"}, "delta": True},
    "delta_vrp": {"label": "Derniers ajouts — V/R/P", "groups": {"shared", "vrp"}, "delta": True},
    "delta_event": {"label": "Derniers ajouts — Événements", "groups": {"shared", "event"}, "delta": True},
    "delta_person": {"label": "Derniers ajouts — Personnages", "groups": {"shared", "person"}, "delta": True},
    "delta_monument": {"label": "Derniers ajouts — Monuments", "groups": {"shared", "monument"}, "delta": True},
}

_EXPORT_STATE_KEY = "backup_export_state"
_EXPORT_STATE_FILE = Path(__file__).resolve().parents[1] / "data" / "export_state.json"


def _reset_all_sequences(conn) -> None:
    """Reset all SERIAL/BIGSERIAL sequences to max(pk)+1 after a backup import."""
    _SEQ_RESETS = [
        ("dim_annotation",              "annotation_id"),
        ("dim_time",                     "time_id"),
        ("ref_population",               "ref_pop_id"),
        ("ref_city",                     "ref_city_id"),
        ("dim_city",                     "city_id"),
        ("dim_city_period_detail",       "period_detail_id"),
        ("dim_city_period_detail_item",  "period_detail_item_id"),
        ("fact_city_population",         "population_id"),
        ("dim_city_fiche",               "fiche_id"),
        ("dim_city_fiche_section",       "section_id"),
        ("dim_city_photo",               "photo_id"),
        ("dim_event",                    "event_id"),
        ("dim_event_location",           "event_location_id"),
        ("dim_event_photo",              "event_photo_id"),
        ("dim_person",                   "person_id"),
        ("dim_person_location",          "person_location_id"),
        ("dim_person_photo",             "person_photo_id"),
        ("dim_monument",                 "monument_id"),
        ("dim_monument_location",        "monument_location_id"),
        ("dim_monument_photo",           "monument_photo_id"),
        ("dim_country",                  "country_id"),
        ("fact_country_population",      "country_pop_id"),
        ("dim_country_photo",            "photo_id"),
        ("dim_region",                   "region_id"),
        ("fact_region_population",       "region_pop_id"),
        ("dim_region_period_detail",     "region_period_id"),
        ("dim_region_period_detail_item","item_id"),
        ("dim_region_photo",             "photo_id"),
        ("raw_document",                 "document_id"),
    ]
    for table, pk in _SEQ_RESETS:
        try:
            conn.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', '{pk}'), "
                f"COALESCE((SELECT MAX({pk}) FROM {table}), 0) + 1, false)"
            )
        except Exception:
            try:
                conn.execute("ROLLBACK TO SAVEPOINT seq_reset")
            except Exception:
                pass
    conn.commit()


def _serialize_value(value: object) -> object:
    """Make a value JSON-serialisable."""
    if value is None or isinstance(value, (int, float, str, bool)):
        return value
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, bytes):
        import base64
        return {"__bytes__": base64.b64encode(value).decode()}
    return str(value)


@web.route("/sql-lab/backup/export")
@editor_required
def sql_lab_backup_export() -> Response:
    """Export the database (or a subset / delta) as a JSON file for backup."""
    import json as _json
    from .db import get_db
    from .services.app_state import load_json_setting, save_json_setting

    scope_key = request.args.get("scope", "all")
    scope = _EXPORT_SCOPES.get(scope_key, _EXPORT_SCOPES["all"])
    allowed_groups = scope["groups"]
    is_delta = scope.get("delta", False)

    conn = get_db()

    # Load previous export state for delta calculation
    export_state: dict = load_json_setting(
        _EXPORT_STATE_KEY, {}, fallback_path=_EXPORT_STATE_FILE,
    )
    # export_state = {"<table_name>": {"max_pk": <int>, "count": <int>}, ...}

    backup: dict = {"_meta": {
        "exported_at": datetime.now().isoformat(),
        "backend": "postgresql",
        "scope": scope_key,
        "scope_label": scope["label"],
        "is_delta": is_delta,
        "version": 2,
    }, "tables": {}}

    new_state: dict = dict(export_state)  # carry forward previous state
    total_rows = 0

    for tdef in _BACKUP_TABLES:
        table = tdef["name"]
        group = tdef.get("group", "shared")
        pk = tdef["pk"]

        if group not in allowed_groups:
            continue

        try:
            prev_max = export_state.get(table, {}).get("max_pk", 0)
            can_delta = is_delta and table in export_state and isinstance(prev_max, (int, float)) and prev_max > 0
            if can_delta:
                rows = conn.execute(
                    f"SELECT * FROM {table} WHERE {pk} > ? ORDER BY {pk}",
                    (prev_max,),
                ).fetchall()
            else:
                rows = conn.execute(f"SELECT * FROM {table} ORDER BY {pk}").fetchall()

            serialized = [
                {k: _serialize_value(v) for k, v in dict(r).items()}
                for r in rows
            ]
            backup["tables"][table] = serialized
            total_rows += len(serialized)

            # Update state with max pk seen
            # Always recompute from DB to get the true max (handles both delta and full)
            try:
                full_row = conn.execute(f"SELECT MAX({pk}) AS mx FROM {table}").fetchone()
                full_max = full_row["mx"] if full_row and full_row["mx"] is not None else 0
                current_max = full_max if isinstance(full_max, (int, float)) else 0
            except Exception:
                current_max = 0

            new_state[table] = {"max_pk": current_max, "count": len(serialized)}

        except Exception:
            backup["tables"][table] = []

    backup["_meta"]["total_rows"] = total_rows

    # Persist the export state so future delta exports know where we left off
    save_json_setting(_EXPORT_STATE_KEY, new_state, fallback_path=_EXPORT_STATE_FILE)

    scope_suffix = scope_key.replace("_", "-")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    payload = _json.dumps(backup, ensure_ascii=False, indent=1, default=str)
    resp = Response(payload, mimetype="application/json; charset=utf-8")
    resp.headers["Content-Disposition"] = (
        f"attachment; filename=projetcity-{scope_suffix}-{timestamp}.json"
    )
    return resp


@web.route("/sql-lab/backup/import", methods=["POST"])
@editor_required
def sql_lab_backup_import() -> Response:
    """Import a JSON backup, inserting only missing rows (ON CONFLICT DO NOTHING).
    Then validate FK relationships and report issues."""
    import json as _json
    from .db import get_db

    uploaded = request.files.get("backup_file")
    if not uploaded or not uploaded.filename:
        flash("Aucun fichier sélectionné.", "error")
        return redirect(url_for("web.sql_lab"))

    try:
        raw = uploaded.read().decode("utf-8")
        backup = _json.loads(raw)
    except Exception as exc:
        flash(f"Fichier JSON invalide: {exc}", "error")
        return redirect(url_for("web.sql_lab"))

    if "tables" not in backup:
        flash("Format de backup invalide — clé 'tables' manquante.", "error")
        return redirect(url_for("web.sql_lab"))

    conn = get_db()
    report: list[str] = []
    total_inserted = 0

    for tdef in _BACKUP_TABLES:
        table = tdef["name"]
        rows = backup["tables"].get(table, [])
        if not rows:
            continue

        conflict_clause = tdef.get("conflict")
        inserted = 0

        for idx, row in enumerate(rows):
            # Restore bytes values
            for k, v in row.items():
                if isinstance(v, dict) and "__bytes__" in v:
                    import base64
                    row[k] = base64.b64decode(v["__bytes__"])

            columns = list(row.keys())
            placeholders = ", ".join("?" for _ in columns)
            col_list = ", ".join(columns)

            if conflict_clause:
                sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) ON CONFLICT {conflict_clause} DO NOTHING"
            else:
                sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

            sp_name = f"sp_{table}_{idx}"
            try:
                conn.execute(f"SAVEPOINT {sp_name}")
                cur = conn.execute(sql, list(row.values()))
                if hasattr(cur, "rowcount") and cur.rowcount > 0:
                    inserted += 1
                conn.execute(f"RELEASE SAVEPOINT {sp_name}")
            except Exception:
                conn.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")

        if inserted:
            report.append(f"{table}: +{inserted}/{len(rows)}")
            total_inserted += inserted
        elif rows:
            report.append(f"{table}: 0/{len(rows)} (déjà présent)")

    conn.commit()

    # --- Reset all SERIAL/BIGSERIAL sequences after import ---
    _reset_all_sequences(conn)

    # --- Validate FK relationships ---
    fk_checks = [
        ("fact_city_population", "city_id", "dim_city", "city_id"),
        ("fact_city_population", "time_id", "dim_time", "time_id"),
        ("fact_city_population", "annotation_id", "dim_annotation", "annotation_id"),
        ("dim_city_period_detail", "city_id", "dim_city", "city_id"),
        ("dim_city_period_detail_item", "period_detail_id", "dim_city_period_detail", "period_detail_id"),
        ("dim_city_fiche", "city_id", "dim_city", "city_id"),
        ("dim_city_fiche_section", "fiche_id", "dim_city_fiche", "fiche_id"),
        ("dim_city_photo", "city_id", "dim_city", "city_id"),
        ("fact_country_population", "country_id", "dim_country", "country_id"),
        ("fact_country_population", "time_id", "dim_time", "time_id"),
        ("dim_country_photo", "country_id", "dim_country", "country_id"),
        ("fact_region_population", "region_id", "dim_region", "region_id"),
        ("fact_region_population", "time_id", "dim_time", "time_id"),
        ("dim_region_period_detail", "region_id", "dim_region", "region_id"),
        ("dim_region_period_detail_item", "region_period_id", "dim_region_period_detail", "region_period_id"),
        ("dim_region_photo", "region_id", "dim_region", "region_id"),
        ("dim_event_location", "event_id", "dim_event", "event_id"),
        ("dim_event_photo", "event_id", "dim_event", "event_id"),
    ]

    fk_issues: list[str] = []
    for child_table, child_col, parent_table, parent_col in fk_checks:
        try:
            orphans = conn.execute(
                f"""SELECT COUNT(*) FROM {child_table} c
                    WHERE c.{child_col} IS NOT NULL
                      AND NOT EXISTS (
                          SELECT 1 FROM {parent_table} p
                          WHERE p.{parent_col} = c.{child_col}
                      )""",
            ).fetchone()[0]
            if orphans > 0:
                fk_issues.append(f"{child_table}.{child_col} → {parent_table}: {orphans} orphelin(s)")
        except Exception:
            pass

    summary_parts = []
    if total_inserted == 0:
        summary_parts.append("Aucune nouvelle donnée — la BD est déjà à jour")
    else:
        summary_parts.append(f"{total_inserted} ligne(s) insérée(s)")
    if report:
        summary_parts.append("Détail: " + " | ".join(report))
    if fk_issues:
        summary_parts.append("⚠️ FK: " + " | ".join(fk_issues))
    else:
        summary_parts.append("✓ Toutes les relations FK sont valides")

    level = "success"
    if fk_issues:
        level = "warning"
    elif total_inserted == 0:
        level = "success"

    flash(" — ".join(summary_parts), level)
    return redirect(url_for("web.sql_lab"))


@web.route("/sql-lab/backup/import-stream", methods=["POST"])
@editor_required
def sql_lab_backup_import_stream() -> Response:
    """Streaming import: sends SSE events so the frontend shows live progress."""
    import json as _json

    uploaded = request.files.get("backup_file")
    if not uploaded or not uploaded.filename:
        def _err():
            yield 'data: ' + _json.dumps({"type": "error", "message": "Aucun fichier sélectionné."}) + '\n\n'
        return Response(_err(), mimetype="text/event-stream")

    try:
        raw = uploaded.read().decode("utf-8")
        backup = _json.loads(raw)
    except Exception as exc:
        def _err2():
            yield 'data: ' + _json.dumps({"type": "error", "message": f"Fichier JSON invalide: {exc}"}) + '\n\n'
        return Response(_err2(), mimetype="text/event-stream")

    if "tables" not in backup:
        def _err3():
            yield 'data: ' + _json.dumps({"type": "error", "message": "Format invalide — clé 'tables' manquante."}) + '\n\n'
        return Response(_err3(), mimetype="text/event-stream")

    # Capture what we need before the request context disappears
    db_url = current_app.config.get("DATABASE_URL", "")

    fk_checks = [
        ("fact_city_population", "city_id", "dim_city", "city_id"),
        ("fact_city_population", "time_id", "dim_time", "time_id"),
        ("fact_city_population", "annotation_id", "dim_annotation", "annotation_id"),
        ("dim_city_period_detail", "city_id", "dim_city", "city_id"),
        ("dim_city_period_detail_item", "period_detail_id", "dim_city_period_detail", "period_detail_id"),
        ("dim_city_fiche", "city_id", "dim_city", "city_id"),
        ("dim_city_fiche_section", "fiche_id", "dim_city_fiche", "fiche_id"),
        ("dim_city_photo", "city_id", "dim_city", "city_id"),
        ("fact_country_population", "country_id", "dim_country", "country_id"),
        ("fact_country_population", "time_id", "dim_time", "time_id"),
        ("dim_country_photo", "country_id", "dim_country", "country_id"),
        ("fact_region_population", "region_id", "dim_region", "region_id"),
        ("fact_region_population", "time_id", "dim_time", "time_id"),
        ("dim_region_period_detail", "region_id", "dim_region", "region_id"),
        ("dim_region_period_detail_item", "region_period_id", "dim_region_period_detail", "region_period_id"),
        ("dim_region_photo", "region_id", "dim_region", "region_id"),
        ("dim_event_location", "event_id", "dim_event", "event_id"),
        ("dim_event_photo", "event_id", "dim_event", "event_id"),
    ]

    def generate():
        import base64 as _b64
        from .db import _connect_postgres

        conn = _connect_postgres(db_url)

        total_inserted = 0

        try:
            for tdef in _BACKUP_TABLES:
                table = tdef["name"]
                rows = backup["tables"].get(table, [])
                if not rows:
                    yield 'data: ' + _json.dumps({"type": "table_skip", "table": table}) + '\n\n'
                    continue

                yield 'data: ' + _json.dumps({"type": "table_start", "table": table, "row_count": len(rows)}) + '\n\n'

                conflict_clause = tdef.get("conflict")
                inserted = 0

                for idx, row in enumerate(rows):
                    for k, v in row.items():
                        if isinstance(v, dict) and "__bytes__" in v:
                            row[k] = _b64.b64decode(v["__bytes__"])

                    columns = list(row.keys())
                    placeholders = ", ".join("?" for _ in columns)
                    col_list = ", ".join(columns)

                    if conflict_clause:
                        sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) ON CONFLICT {conflict_clause} DO NOTHING"
                    else:
                        sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"

                    sp_name = f"sp_{table}_{idx}"
                    try:
                        conn.execute(f"SAVEPOINT {sp_name}")
                        cur = conn.execute(sql, list(row.values()))
                        rc = cur.rowcount if hasattr(cur, "rowcount") else 0
                        if rc > 0:
                            inserted += 1
                        conn.execute(f"RELEASE SAVEPOINT {sp_name}")
                    except Exception:
                        conn.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")

                yield 'data: ' + _json.dumps({"type": "table_done", "table": table, "inserted": inserted, "row_count": len(rows)}) + '\n\n'
                total_inserted += inserted

            conn.commit()

            # Reset sequences after import
            _reset_all_sequences(conn)

            # FK validation
            yield 'data: ' + _json.dumps({"type": "fk_start"}) + '\n\n'
            fk_issues = []
            for child_table, child_col, parent_table, parent_col in fk_checks:
                try:
                    orphans = conn.execute(
                        f"SELECT COUNT(*) FROM {child_table} c"
                        f" WHERE c.{child_col} IS NOT NULL"
                        f" AND NOT EXISTS ("
                        f"   SELECT 1 FROM {parent_table} p"
                        f"   WHERE p.{parent_col} = c.{child_col}"
                        f")",
                    ).fetchone()[0]
                    if orphans > 0:
                        detail = f"{child_table}.{child_col} → {parent_table}: {orphans} orphelin(s)"
                        fk_issues.append(detail)
                        yield 'data: ' + _json.dumps({"type": "fk_issue", "detail": detail}) + '\n\n'
                    else:
                        yield 'data: ' + _json.dumps({"type": "fk_ok", "relation": f"{child_table}.{child_col} → {parent_table}"}) + '\n\n'
                except Exception:
                    pass

            if total_inserted == 0:
                msg = "Aucune nouvelle donnée — la BD est déjà à jour."
            else:
                msg = f"{total_inserted} ligne(s) insérée(s)."
            if fk_issues:
                msg += f" ⚠️ {len(fk_issues)} problème(s) FK."
            else:
                msg += " ✓ Toutes les relations FK sont valides."

            yield 'data: ' + _json.dumps({"type": "summary", "message": msg, "inserted": total_inserted}) + '\n\n'

            try:
                log_action("import", "backup", None,
                           f"Backup streaming importé: {total_inserted} ligne(s) insérée(s)")
            except Exception:
                pass  # logging failure should not break the import

        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            yield 'data: ' + _json.dumps({"type": "error", "message": str(exc)}) + '\n\n'
        finally:
            conn.close()

    return Response(generate(), mimetype="text/event-stream")


# ---------------------------------------------------------------------------
# Full Backup (BD + Photos)
# ---------------------------------------------------------------------------

@web.route("/backup/export-full")
@editor_required
def backup_export_full() -> Response:
    """Download a single ZIP containing the full DB backup + all photos."""
    from .db import _connect_postgres
    from .services.full_backup import export_full_backup_streaming

    db_url = current_app.config.get("DATABASE_URL", "")
    scope_groups = {"shared", "vrp", "event", "person", "monument"}
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"projetcity-full-backup-{timestamp}.zip"

    def generate():
        conn = _connect_postgres(db_url)
        try:
            yield from export_full_backup_streaming(conn, _BACKUP_TABLES, scope_groups)
        finally:
            conn.close()

    return Response(
        generate(),
        mimetype="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@web.route("/backup/export-photos/<entity_type>")
@editor_required
def backup_export_entity_photos(entity_type: str) -> Response:
    """Download a ZIP with all photos for a given entity type."""
    from .db import get_db
    from .services.full_backup import export_entity_photos_zip

    valid_types = ("city", "event", "person", "monument", "country", "region")
    if entity_type not in valid_types:
        return jsonify({"success": False, "error": f"Type inconnu: {entity_type}"}), 400

    conn = get_db()
    buf = export_entity_photos_zip(conn, entity_type)
    if buf is None:
        flash("Aucune photo à exporter.", "info")
        return redirect(url_for("web.sql_lab"))

    labels = {"city": "villes", "event": "evenements", "person": "personnages",
              "monument": "monuments", "country": "pays", "region": "regions"}
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"photos-{labels.get(entity_type, entity_type)}-{timestamp}.zip"

    return Response(
        buf.read(),
        mimetype="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@web.route("/backup/import-full", methods=["POST"])
@editor_required
def backup_import_full() -> Response:
    """Phase 1: Upload the ZIP to a temp file on the volume, return JSON."""
    uploaded = request.files.get("backup_file")
    if not uploaded:
        return jsonify({"success": False, "error": "Aucun fichier envoyé."})

    # Save to a temp path (on the persistent volume if available)
    import tempfile, os
    volume = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
    tmp_dir = volume if volume else tempfile.gettempdir()
    tmp_path = os.path.join(tmp_dir, "_pending_backup.zip")
    uploaded.save(tmp_path)
    size_mb = os.path.getsize(tmp_path) / (1024 * 1024)

    return jsonify({"success": True, "path": tmp_path, "size_mb": round(size_mb, 1)})


@web.route("/backup/process-full", methods=["POST"])
@editor_required
def backup_process_full() -> Response:
    """Phase 2: Read the uploaded ZIP from disk and process with SSE streaming."""
    import json as _json
    from .services.full_backup import import_full_backup

    tmp_path = request.json.get("path", "") if request.is_json else ""
    db_url = current_app.config.get("DATABASE_URL", "")

    def generate():
        from .db import _connect_postgres
        import os

        if not tmp_path or not os.path.isfile(tmp_path):
            yield f'data: {_json.dumps({"type":"error","message":"Fichier temporaire introuvable."})}\n\n'
            return

        with open(tmp_path, "rb") as f:
            zip_bytes = f.read()

        conn = _connect_postgres(db_url)
        try:
            for evt in import_full_backup(conn, zip_bytes, _BACKUP_TABLES, _reset_all_sequences):
                yield f"data: {_json.dumps(evt, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f'data: {_json.dumps({"type":"error","message":str(exc)})}\n\n'
        finally:
            conn.close()
            # Clean up temp file
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    return Response(generate(), mimetype="text/event-stream")


# ---------------------------------------------------------------------------
# Add City
# ---------------------------------------------------------------------------

@web.route("/add-city")
@editor_required
def add_city() -> str:
    return render_template("web/add_city.html", page_title="Ajout / mise à jour de ville")


@web.route("/add-city/check-slug")
@editor_required
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
@editor_required
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
@editor_required
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

    _resolve_duplicate_slug(conn, stats)

    # --- Upsert dim_city to get city_id ---
    uid = g.user["user_id"] if hasattr(g, "user") and g.user else None
    cursor = conn.execute(
        """INSERT INTO dim_city (city_name, city_slug, region, country, city_color, source_file,
                                 created_by_user_id, updated_by_user_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(city_slug) DO UPDATE SET
               city_name = excluded.city_name, region = excluded.region,
               country = excluded.country, city_color = excluded.city_color,
               source_file = excluded.source_file,
               updated_by_user_id = excluded.updated_by_user_id,
               updated_at = CURRENT_TIMESTAMP
           RETURNING city_id""",
        (stats["city_name"], stats["city_slug"], stats["region"],
         stats["country"], stats["city_color"], "web-import",
         uid, uid),
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
                           VALUES (?, ?, ?, ?, FALSE, 'web-import')""",
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
    log_action("import", "city", stats["city_slug"], f"Fusion import: {stats['city_name']} ({stats['country']})",
               {"pop_action": pop_action, "ann_action": ann_action, "period_action": period_action, "fiche_action": fiche_action})
    return redirect(url_for("web.city_detail", city_slug=stats["city_slug"]))


@web.route("/add-city/import", methods=["POST"])
@editor_required
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
        _resolve_duplicate_slug(conn, stats)
        uid = g.user["user_id"] if hasattr(g, "user") and g.user else None
        cursor = conn.execute(
            """INSERT INTO dim_city (city_name, city_slug, region, country, city_color, source_file,
                                     created_by_user_id, updated_by_user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(city_slug) DO UPDATE SET
                   city_name = excluded.city_name, region = excluded.region,
                   country = excluded.country, city_color = excluded.city_color,
                   source_file = excluded.source_file,
                   updated_by_user_id = excluded.updated_by_user_id,
                   updated_at = CURRENT_TIMESTAMP
               RETURNING city_id""",
            (stats["city_name"], stats["city_slug"], stats["region"],
             stats["country"], stats["city_color"], "web-import",
             uid, uid),
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
    log_action("import", "city", stats["city_slug"], f"Import: {stats['city_name']} ({stats['country']})",
               {"skip_pop": skip_pop, "skip_periods": skip_periods, "skip_fiche": skip_fiche, "skip_photo": skip_photo})
    return redirect(url_for("web.city_detail", city_slug=stats["city_slug"]))


@web.route("/cities/<city_slug>/photo", methods=["POST"])
@editor_required
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
        log_action("upload_photo", "city", city_slug, f"Photo importée pour {city_name}: {result['filename']}")
    else:
        flash(result["error"], "error")
    return redirect(url_for("web.city_detail", city_slug=city_slug))


# ------------------------------------------------------------------
#  Photo Library
# ------------------------------------------------------------------

@web.route("/cities/<city_slug>/photos/upload", methods=["POST"])
@editor_required
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
    log_action("upload_photo", "city", city_slug, f"{imported} photo(s) uploadée(s) pour la ville {city_slug}")
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
@editor_required
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
            image_url=url,
        )
        if save_result["success"]:
            imported += 1

    if imported:
        log_action("upload_photo", "city", city_slug, f"{imported} photo(s) importée(s) depuis le web pour la ville {city_slug}")
    return jsonify({"imported": imported})


@web.route("/cities/<city_slug>/photos/<int:photo_id>/delete", methods=["POST"])
@editor_required
def city_photo_delete(city_slug: str, photo_id: int) -> Response:
    """Delete a photo from the library."""
    from .db import get_db
    from .services.city_photos import delete_photo_from_library

    conn = get_db()
    deleted = delete_photo_from_library(conn, photo_id, city_slug)
    if deleted:
        flash("Photo supprimée.", "success")
        log_action("delete_photo", "city", city_slug, f"Photo #{photo_id} supprimée de la ville {city_slug}")
    else:
        flash("Photo introuvable.", "error")
    return redirect(url_for("web.city_detail", city_slug=city_slug))


@web.route("/cities/<city_slug>/photos/<int:photo_id>/primary", methods=["POST"])
@editor_required
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
    log_action("update_photo", "city", city_slug, f"Photo #{photo_id} définie comme principale pour la ville {city_slug}")
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
@editor_required
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
    if result.get("success"):
        log_action("upload_photo", "annotation", str(annotation_id),
                   f"Photo web ajoutée à l'annotation #{annotation_id} de la ville {city_slug}")
    return jsonify(result)


@web.route("/cities/<city_slug>/annotations/<int:annotation_id>/photo/link", methods=["POST"])
@editor_required
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
    if result.get("success"):
        log_action("link_photo", "annotation", str(annotation_id),
                   f"Photo #{data['photo_id']} liée à l'annotation #{annotation_id} de la ville {city_slug}")
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
@editor_required
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
    log_action("create", "annotation", str(annotation_id),
               f"Annotation créée pour la ville {city_slug}, année {year}: {label}")
    return jsonify({"success": True, "annotation_id": annotation_id})


@web.route("/cities/<city_slug>/annotations/<int:annotation_id>", methods=["PUT"])
@editor_required
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
    log_action("update", "annotation", str(annotation_id),
               f"Annotation #{annotation_id} modifiée pour la ville {city_slug}: {label}")
    return jsonify({"success": True})


@web.route("/cities/<city_slug>/annotations/<int:annotation_id>", methods=["DELETE"])
@editor_required
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
    log_action("delete", "annotation", str(annotation_id),
               f"Annotation #{annotation_id} supprimée de la ville {city_slug}")
    return jsonify({"success": True})


@web.route("/cities/<city_slug>/fiche", methods=["POST"])
@editor_required
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
        log_action("import", "fiche", city_slug, f"Fiche importée pour {city_name}: {len(sections)} sections")
    except Exception as exc:
        conn.rollback()
        flash(f"Erreur fiche complète: {exc}", "error")

    return redirect(url_for("web.city_detail", city_slug=city_slug))


@web.route("/cities/<city_slug>/fiche/delete", methods=["POST"])
@editor_required
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
            log_action("delete", "fiche", city_slug, f"Fiche supprimée pour {row['city_name']}")
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
@editor_required
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
    import unicodedata as _ud

    def _ascii(name: str) -> str:
        return _ud.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower().strip()

    existing_by_region: dict[str, set[str]] = {}
    existing_ascii_by_region: dict[str, set[str]] = {}
    for r in rows:
        key = f"{r['country']}|{r['region']}"
        if key not in existing_by_region:
            existing_by_region[key] = set()
            existing_ascii_by_region[key] = set()
        existing_by_region[key].add(r["city_name"].lower().strip())
        existing_ascii_by_region[key].add(_ascii(r["city_name"]))

    def _ref_in_db(ref_name: str, key: str) -> bool:
        """Check if ref city matches a DB city (exact, accent-stripped, or substring)."""
        names = existing_by_region.get(key, set())
        ascii_names = existing_ascii_by_region.get(key, set())
        rn = ref_name.lower().strip()
        if rn in names:
            return True
        ra = _ascii(ref_name)
        if ra in ascii_names:
            return True
        # Substring: "New York" matches "New York City"
        for an in ascii_names:
            if ra in an or an in ra:
                return True
        return False

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
        ref_with_status = []
        for rc in ref_cities:
            ref_with_status.append({
                **rc,
                "in_db": _ref_in_db(rc["city_name"], key),
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
        ref_with_status = []
        for rc in ref_cities:
            ref_with_status.append({
                **rc,
                "in_db": _ref_in_db(rc["city_name"], key),
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
@editor_required
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
                """INSERT INTO ref_city
                   (city_name, region, country, population, rank)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT (city_name, region, country) DO NOTHING""",
                (c["city_name"], c["region"], c["country"],
                 c["population"], c["rank"]),
            )
            inserted += 1
        except Exception:
            pass
    conn.commit()

    if inserted:
        log_action("import", "ref_city", None,
                   f"Expansion référence: {inserted} villes ajoutées pour {region} ({country})")
    return jsonify(success=True, inserted=inserted, cities=[c["city_name"] for c in new_cities[:TARGET]])


# ------------------------------------------------------------------
#  Coverage / completeness
# ------------------------------------------------------------------

@web.route("/coverage")
@editor_required
def city_coverage() -> str:
    from .services.mammouth_ai import load_settings, fetch_models

    service = AnalyticsService()
    filters = service.normalize_filters(request.args)
    coverage = service.get_city_coverage(filters)
    missing_decades = service.get_missing_decades()

    total = len(coverage)
    without_fiche = sum(1 for c in coverage if not c["has_fiche"])
    without_photo = sum(1 for c in coverage if not c["has_photo"])
    without_periods = sum(1 for c in coverage if not c["has_periods"])
    without_data = sum(1 for c in coverage if c["data_points"] == 0)

    settings = load_settings()
    models = fetch_models()

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
        settings=settings,
        models=models,
    )


@web.route("/coverage/save-missing-years", methods=["POST"])
@editor_required
def coverage_save_missing_years() -> Response:
    """Save AI-found missing-year populations for an existing city."""
    from .db import get_db
    from .services.city_import import upsert_time_dimension

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "error": "Données JSON manquantes."})

    city_slug = data.get("city_slug", "").strip()
    year_pops = data.get("year_pops", [])
    foundation_year = data.get("foundation_year")

    if not city_slug:
        return jsonify({"success": False, "error": "city_slug manquant."})
    if not year_pops and not foundation_year:
        return jsonify({"success": False, "error": "Aucune donnée à sauvegarder."})

    conn = get_db()
    city_row = conn.execute(
        "SELECT city_id FROM dim_city WHERE city_slug = ?", (city_slug,)
    ).fetchone()
    if not city_row:
        return jsonify({"success": False, "error": f"Ville '{city_slug}' introuvable."})
    city_id = city_row["city_id"]

    # Save foundation year if provided
    foundation_saved = None
    if foundation_year is not None:
        try:
            fy = int(foundation_year)
            if 1500 <= fy <= 2030:
                conn.execute(
                    "UPDATE dim_city SET foundation_year = ? WHERE city_id = ?",
                    (fy, city_id),
                )
                foundation_saved = fy
        except (ValueError, TypeError):
            pass

    time_cache: dict[int, int] = {
        year: tid for tid, year in conn.execute("SELECT time_id, year FROM dim_time")
    }

    inserted = 0
    for entry in year_pops:
        year = int(entry["year"])
        population = int(entry["population"])
        if population <= 0:
            continue
        # Skip if this year already exists
        exists = conn.execute(
            "SELECT 1 FROM fact_city_population WHERE city_id = ? AND year = ?",
            (city_id, year),
        ).fetchone()
        if exists:
            continue
        time_id = upsert_time_dimension(conn, time_cache, year)
        conn.execute(
            """INSERT INTO fact_city_population
               (city_id, time_id, year, population, is_key_year, annotation_id, source_file)
               VALUES (?, ?, ?, ?, FALSE, NULL, 'coverage-fill')""",
            (city_id, time_id, year, population),
        )
        inserted += 1

    conn.commit()

    log_action("import", "coverage", city_slug, f"Couverture: {inserted} année(s) ajoutée(s) pour {city_slug}",
               {"foundation_saved": foundation_saved})

    # Regenerate villestats_RAW.py to stay in sync
    try:
        from scripts.export_villestats_raw import export_all, OUTPUT_PATH
        content = export_all()
        OUTPUT_PATH.write_text(content, encoding="utf-8")
    except Exception:
        pass  # non-blocking — file can be regenerated manually

    return jsonify({"success": True, "inserted": inserted, "foundation_saved": foundation_saved})


@web.route("/coverage/export/coverage.csv")
@editor_required
def coverage_export_csv() -> Response:
    service = AnalyticsService()
    csv_content = service.export_coverage_csv()
    response = Response(csv_content, mimetype="text/csv; charset=utf-8")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    response.headers["Content-Disposition"] = f"attachment; filename=couverture-{timestamp}.csv"
    return response


@web.route("/coverage/export/missing-decades.csv")
@editor_required
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
@editor_required
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
@collaborator_required
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
@collaborator_required
def ai_lab() -> str:
    from .services.mammouth_ai import load_settings, fetch_models, load_prompt

    settings = load_settings()
    models = fetch_models()
    prompt_city = load_prompt("city_data_step1.txt")
    prompt_details = load_prompt("city_data_step2.txt")
    prompt_fiche = load_prompt("city_data_step3.txt")
    prompt_event = load_prompt("event_data.txt")
    prompt_country = load_prompt("country_data_step1.txt")
    prompt_country_details = load_prompt("country_data_step2.txt")
    prompt_country_fiche = load_prompt("country_data_step3.txt")
    prompt_region = load_prompt("region_data_step1.txt")
    prompt_region_details = load_prompt("region_data_step2.txt")
    prompt_region_fiche = load_prompt("region_data_step3.txt")
    from .db import get_db
    conn = get_db()
    countries_for_region = [r["country_name"] for r in conn.execute(
        "SELECT country_name FROM dim_country ORDER BY LOWER(country_name), country_name"
    ).fetchall()]
    countries_for_event = countries_for_region
    regions_for_event = [r["region_name"] for r in conn.execute(
        "SELECT region_name FROM dim_region ORDER BY LOWER(region_name), region_name"
    ).fetchall()]
    from .services.event_service import CATEGORY_LABELS, CATEGORY_EMOJIS
    prompt_refine_event = load_prompt("event_refine.txt")
    events_for_refine = [dict(r) for r in conn.execute(
        "SELECT event_name, event_slug, event_year, event_category "
        "FROM dim_event ORDER BY event_year DESC, LOWER(event_name), event_name"
    ).fetchall()]
    prompt_person = load_prompt("person_data.txt")
    prompt_refine_person = load_prompt("person_refine.txt")
    from .services.person_service import CATEGORY_LABELS as PERSON_CATEGORY_LABELS
    from .services.person_service import CATEGORY_EMOJIS as PERSON_CATEGORY_EMOJIS
    persons_for_refine = [dict(r) for r in conn.execute(
        "SELECT person_name, person_slug, birth_year, person_category "
        "FROM dim_person ORDER BY birth_year DESC NULLS LAST, LOWER(person_name), person_name"
    ).fetchall()]
    countries_for_person = countries_for_region
    regions_for_person = regions_for_event
    prompt_monument = load_prompt("monument_data.txt")
    prompt_refine_monument = load_prompt("monument_refine.txt")
    from .services.monument_service import CATEGORY_LABELS as MONUMENT_CATEGORY_LABELS
    from .services.monument_service import CATEGORY_EMOJIS as MONUMENT_CATEGORY_EMOJIS
    monuments_for_refine = [dict(r) for r in conn.execute(
        "SELECT monument_name, monument_slug, construction_year, monument_category "
        "FROM dim_monument ORDER BY construction_year DESC NULLS LAST, LOWER(monument_name), monument_name"
    ).fetchall()]
    countries_for_monument = countries_for_region
    regions_for_monument = regions_for_event
    return render_template(
        "web/ai_lab.html",
        page_title="AI Lab",
        settings=settings,
        models=models,
        prompt_city=prompt_city,
        prompt_details=prompt_details,
        prompt_fiche=prompt_fiche,
        prompt_event=prompt_event,
        prompt_country=prompt_country,
        prompt_country_details=prompt_country_details,
        prompt_country_fiche=prompt_country_fiche,
        prompt_region=prompt_region,
        prompt_region_details=prompt_region_details,
        prompt_region_fiche=prompt_region_fiche,
        countries_for_region=countries_for_region,
        countries_for_event=countries_for_event,
        regions_for_event=regions_for_event,
        event_category_labels=CATEGORY_LABELS,
        event_category_emojis=CATEGORY_EMOJIS,
        prompt_refine_event=prompt_refine_event,
        events_for_refine=events_for_refine,
        prompt_person=prompt_person,
        prompt_refine_person=prompt_refine_person,
        person_category_labels=PERSON_CATEGORY_LABELS,
        person_category_emojis=PERSON_CATEGORY_EMOJIS,
        persons_for_refine=persons_for_refine,
        countries_for_person=countries_for_person,
        regions_for_person=regions_for_person,
        prompt_monument=prompt_monument,
        prompt_refine_monument=prompt_refine_monument,
        monument_category_labels=MONUMENT_CATEGORY_LABELS,
        monument_category_emojis=MONUMENT_CATEGORY_EMOJIS,
        monuments_for_refine=monuments_for_refine,
        countries_for_monument=countries_for_monument,
        regions_for_monument=regions_for_monument,
    )


@web.route("/options/save", methods=["POST"])
@collaborator_required
def options_save() -> Response:
    from .services.mammouth_ai import load_settings, save_settings

    settings = load_settings()
    settings["api_key"] = request.form.get("api_key", "").strip()
    settings["model"] = request.form.get("model", "gpt-4.1-mini").strip()
    save_settings(settings)
    log_action("update", "settings", None, "Paramètres AI sauvegardés")
    flash("Paramètres enregistrés.", "success")
    return redirect(url_for("web.options"))


@web.route("/options/test", methods=["POST"])
@collaborator_required
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
@collaborator_required
def options_reset_tokens() -> Response:
    from .services.mammouth_ai import reset_tokens
    reset_tokens()
    log_action("update", "settings", None, "Compteur de tokens réinitialisé")
    return jsonify({"success": True, "tokens_used": 0})


@web.route("/options/generate", methods=["POST"])
@collaborator_required
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
@editor_required
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
@editor_required
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
        uid = g.user["user_id"] if hasattr(g, "user") and g.user else None
        cursor = conn.execute(
            """INSERT INTO dim_city (city_name, city_slug, region, country, city_color, foundation_year, source_file,
                                     created_by_user_id, updated_by_user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(city_slug) DO UPDATE SET
                   city_name = excluded.city_name, region = excluded.region,
                   country = excluded.country, city_color = excluded.city_color,
                   foundation_year = COALESCE(excluded.foundation_year, dim_city.foundation_year),
                   source_file = excluded.source_file,
                   updated_by_user_id = excluded.updated_by_user_id,
                   updated_at = CURRENT_TIMESTAMP
               RETURNING city_id""",
            (stats["city_name"], stats["city_slug"], stats["region"],
             stats["country"], stats["city_color"], stats.get("foundation_year"), "ai-lab-import",
             uid, uid),
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

    log_action("import", "city", stats["city_slug"],
               f"AI Lab import: {stats['city_name']} ({stats['region']}, {stats['country']})",
               {"steps": messages})
    return jsonify({
        "success": True,
        "city_name": stats["city_name"],
        "city_slug": stats["city_slug"],
        "messages": messages,
        "redirect": url_for("web.city_detail", city_slug=stats["city_slug"]),
    })


@web.route("/ai-lab/country-import", methods=["POST"])
@editor_required
def ai_lab_country_import() -> Response:
    """AJAX import for country population + details — returns JSON."""
    stats_text = request.form.get("stats_text", "").strip()
    details_text = request.form.get("details_text", "").strip()
    fiche_text = request.form.get("fiche_text", "").strip()
    if not stats_text:
        return jsonify({"success": False, "error": "Le champ population (Step 1) est vide."})

    try:
        stats = parse_country_stats_text(stats_text)
    except ValueError as exc:
        return jsonify({"success": False, "error": f"Erreur de parsing population: {exc}"})

    from .db import get_db
    conn = get_db()
    messages = []

    try:
        country_id = import_country_stats(conn, stats)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        return jsonify({"success": False, "error": f"Erreur DB: {exc}"})
    messages.append(
        f"Population importée — {len(stats['years'])} années, "
        f"{len(stats['annotations'])} annotations."
    )

    # Save details text file
    if details_text:
        try:
            save_country_details_file(stats["country_slug"], details_text)
            messages.append("Fiche détaillée sauvegardée.")
        except Exception as exc:
            messages.append(f"⚠️ Fiche détaillée: {exc}")

    # Save fiche complète file
    if fiche_text:
        try:
            save_country_fiche_file(stats["country_slug"], fiche_text)
            messages.append("Fiche complète sauvegardée.")
        except Exception as exc:
            messages.append(f"⚠️ Fiche complète: {exc}")

    # Sync paysstats_RAW.py
    try:
        from scripts.export_paysstats_raw import export_all
        from pathlib import Path
        raw_path = Path(__file__).resolve().parent.parent / "paysstats_RAW.py"
        raw_path.write_text(export_all(), encoding="utf-8")
        messages.append("paysstats_RAW.py synchronisé.")
    except Exception as exc:
        messages.append(f"⚠️ paysstats_RAW.py: {exc}")

    # Download flag
    try:
        from .services.city_import import download_country_flag
        flag_path = download_country_flag(stats["country_name"], stats["country_slug"])
        if flag_path:
            messages.append(f"Drapeau téléchargé: {flag_path}")
        else:
            messages.append("⚠️ Drapeau non trouvé (code ISO inconnu).")
    except Exception as exc:
        messages.append(f"⚠️ Drapeau: {exc}")

    log_action("import", "country", stats["country_slug"],
               f"AI Lab import pays: {stats['country_name']}",
               {"steps": messages})
    return jsonify({
        "success": True,
        "country_name": stats["country_name"],
        "country_slug": stats["country_slug"],
        "messages": messages,
    })


@web.route("/ai-lab/suggest-country", methods=["POST"])
@editor_required
def ai_lab_suggest_country() -> Response:
    """Ask Mammouth to suggest a random country not yet in the DB."""
    from .services.mammouth_ai import load_settings, generate_city
    from .db import get_db

    settings = load_settings()
    api_key = settings.get("api_key", "")
    if not api_key:
        return jsonify({"success": False, "error": "Aucune clé API configurée."})

    model = request.form.get("model", settings.get("model", "gpt-4.1-mini")).strip()
    conn = get_db()

    existing_rows = conn.execute(
        "SELECT country_name FROM dim_country ORDER BY country_name"
    ).fetchall()
    existing_names = [r["country_name"] for r in existing_rows]

    if existing_names:
        prompt = (
            f"Ma base contient déjà ces pays: {', '.join(existing_names)}.\n"
            f"Suggère UN pays du monde qui n'est PAS dans cette liste. "
            f"Varie entre grands pays, pays moyens et petits pays connus. "
            f"Choisis un pays différent à chaque fois.\n"
            f"Réponds UNIQUEMENT avec le nom du pays en anglais.\n"
            f"Aucun autre texte."
        )
    else:
        prompt = (
            "Suggère UN pays du monde au hasard. "
            "Varie entre grands pays, pays moyens et petits pays connus.\n"
            "Réponds UNIQUEMENT avec le nom du pays en anglais.\n"
            "Aucun autre texte."
        )

    result = generate_city(api_key, model, "", prompt, max_tokens=50, temperature=0.9)
    if result.get("success"):
        result["tokens_total"] = load_settings().get("tokens_used", 0)
    return jsonify(result)


@web.route("/ai-lab/region-import", methods=["POST"])
@editor_required
def ai_lab_region_import() -> Response:
    """AJAX import for region population + period details + fiche — returns JSON."""
    stats_text = request.form.get("stats_text", "").strip()
    periods_text = request.form.get("periods_text", "").strip()
    fiche_text = request.form.get("fiche_text", "").strip()
    if not stats_text:
        return jsonify({"success": False, "error": "Le champ population (Step 1) est vide."})

    try:
        stats = parse_region_stats_text(stats_text)
    except ValueError as exc:
        return jsonify({"success": False, "error": f"Erreur de parsing population: {exc}"})

    from .db import get_db
    conn = get_db()
    messages: list[str] = []

    try:
        region_id = import_region_stats(conn, stats)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        return jsonify({"success": False, "error": f"Erreur DB: {exc}"})
    messages.append(
        f"Population importée — {len(stats['years'])} années, "
        f"{len(stats['annotations'])} annotations."
    )

    # Import period details into DB
    if periods_text:
        try:
            sections = parse_region_period_details_text(periods_text)
            if sections:
                count = import_region_periods(conn, region_id, stats["region_slug"], sections)
                conn.commit()
                messages.append(f"Périodes importées — {count} périodes.")
                save_region_details_file(stats["region_slug"], periods_text)
            else:
                messages.append("⚠️ Aucune période trouvée dans le Step 2.")
        except Exception as exc:
            conn.rollback()
            messages.append(f"⚠️ Périodes: {exc}")

    # Save fiche complète file
    if fiche_text:
        try:
            save_region_fiche_file(stats["region_slug"], fiche_text)
            messages.append("Fiche complète sauvegardée.")
        except Exception as exc:
            messages.append(f"⚠️ Fiche complète: {exc}")

    # Sync regionstats_RAW.py in background thread (avoids Flask reloader restart)
    try:
        import threading
        from scripts.export_regionstats_raw import export_all
        from pathlib import Path
        def _sync_raw():
            try:
                raw_path = Path(__file__).resolve().parent.parent / "regionstats_RAW.py"
                raw_path.write_text(export_all(), encoding="utf-8")
            except Exception:
                pass
        threading.Thread(target=_sync_raw, daemon=True).start()
        messages.append("regionstats_RAW.py synchronisé.")
    except Exception as exc:
        messages.append(f"⚠️ regionstats_RAW.py: {exc}")

    # Download flag
    try:
        flag_path = fetch_and_save_region_flag(stats["region_name"], stats["region_slug"])
        if flag_path:
            messages.append(f"Drapeau téléchargé: {flag_path}")
        else:
            messages.append("⚠️ Drapeau non trouvé (Wikimedia Commons).")
    except Exception as exc:
        messages.append(f"⚠️ Drapeau: {exc}")

    # Download primary photo
    try:
        conn2 = get_db()
        photo_path = fetch_and_save_region_photo(
            conn2, region_id, stats["region_name"],
            stats["region_slug"], stats.get("region_country", ""),
        )
        conn2.commit()
        if photo_path:
            messages.append(f"Photo téléchargée: {photo_path}")
        else:
            messages.append("⚠️ Photo Wikipedia non trouvée.")
    except Exception as exc:
        messages.append(f"⚠️ Photo: {exc}")
        photo_path = None

    # Also save flag to region photo library (album)
    try:
        import shutil as _shutil
        from pathlib import Path as _Path
        flag_dest = _Path(current_app.static_folder) / "images" / "flags" / "regions" / f"{stats['region_slug']}.png"
        if flag_dest.exists():
            region_lib_dir = _Path(current_app.static_folder) / "images" / "regions" / stats["region_slug"]
            region_lib_dir.mkdir(parents=True, exist_ok=True)
            flag_lib_copy = region_lib_dir / "flag.png"
            if not flag_lib_copy.exists():
                _shutil.copy2(str(flag_dest), str(flag_lib_copy))
            # Register in dim_region_photo if not already there
            conn3 = get_db()
            existing_flag = conn3.execute(
                "SELECT photo_id FROM dim_region_photo WHERE region_id = ? AND filename = 'flag.png'",
                (region_id,),
            ).fetchone()
            if not existing_flag:
                flag_is_primary = not photo_path
                conn3.execute(
                    "INSERT INTO dim_region_photo (region_id, filename, caption, source_url, attribution, is_primary) "
                    "VALUES (?, 'flag.png', ?, ?, 'Wikimedia Commons', ?)",
                    (region_id, f"Drapeau de {stats['region_name']}",
                     "images/flags/regions/" + stats["region_slug"] + ".png", flag_is_primary),
                )
                conn3.commit()
                messages.append("Drapeau ajouté à l'album de la région.")
    except Exception as exc:
        messages.append(f"⚠️ Drapeau album: {exc}")

    log_action("import", "region", stats["region_slug"],
               f"AI Lab import r\u00e9gion: {stats['region_name']}",
               {"steps": messages})
    return jsonify({
        "success": True,
        "region_name": stats["region_name"],
        "region_slug": stats["region_slug"],
        "messages": messages,
    })


@web.route("/ai-lab/suggest-region", methods=["POST"])
@editor_required
def ai_lab_suggest_region() -> Response:
    """Ask Mammouth to suggest a region/province not yet in the DB for a given country."""
    from .services.mammouth_ai import load_settings, generate_city
    from .db import get_db

    settings = load_settings()
    api_key = settings.get("api_key", "")
    if not api_key:
        return jsonify({"success": False, "error": "Aucune clé API configurée."})

    model = request.form.get("model", settings.get("model", "gpt-4.1-mini")).strip()
    country = request.form.get("country", "").strip()
    conn = get_db()

    query = "SELECT region_name FROM dim_region"
    params: tuple = ()
    if country:
        query += " WHERE country_name = ?"
        params = (country,)
    query += " ORDER BY region_name"

    existing_rows = conn.execute(query, params).fetchall()
    existing_names = [r["region_name"] for r in existing_rows]

    country_ctx = f" de {country}" if country else ""
    if existing_names:
        prompt = (
            f"Ma base contient déjà ces régions{country_ctx}: {', '.join(existing_names)}.\n"
            f"Suggère UNE région, province ou état{country_ctx} qui n'est PAS dans cette liste. "
            f"Choisis une région importante ou bien connue.\n"
            f"Réponds UNIQUEMENT avec le nom de la région en anglais.\n"
            f"Aucun autre texte."
        )
    else:
        prompt = (
            f"Suggère UNE région, province ou état{country_ctx} au hasard. "
            f"Choisis une région importante ou bien connue.\n"
            f"Réponds UNIQUEMENT avec le nom de la région en anglais.\n"
            f"Aucun autre texte."
        )

    result = generate_city(api_key, model, "", prompt, max_tokens=50, temperature=0.9)
    if result.get("success"):
        result["tokens_total"] = load_settings().get("tokens_used", 0)
    return jsonify(result)


@web.route("/ai-lab/suggest-event", methods=["POST"])
@editor_required
def ai_lab_suggest_event() -> Response:
    """Ask Mammouth to suggest a historical event not yet in the DB."""
    from .services.mammouth_ai import load_settings, generate_city
    from .services.event_service import CATEGORY_LABELS
    from .db import get_db

    settings = load_settings()
    api_key = settings.get("api_key", "")
    if not api_key:
        return jsonify({"success": False, "error": "Aucune clé API configurée."})

    model = request.form.get("model", settings.get("model", "gpt-4.1-mini")).strip()
    filter_country  = request.form.get("country", "").strip()
    filter_region   = request.form.get("region", "").strip()
    filter_category = request.form.get("category", "").strip()
    filter_decade   = request.form.get("decade", "").strip()

    conn = get_db()

    # Collect existing event names + slugs to exclude
    existing_rows = conn.execute(
        "SELECT event_name, event_slug, event_year FROM dim_event ORDER BY event_name"
    ).fetchall()
    existing_entries = [
        f"{r['event_name']} ({r['event_year']})" if r["event_year"] else r["event_name"]
        for r in existing_rows
    ]

    # Build context filters description
    context_parts: list[str] = []
    if filter_country:
        context_parts.append(f"lié au pays '{filter_country}'")
    if filter_region:
        context_parts.append(f"lié à la région '{filter_region}'")
    if filter_category:
        label = CATEGORY_LABELS.get(filter_category, filter_category)
        context_parts.append(f"dans la catégorie '{label}'")
    if filter_decade:
        context_parts.append(f"datant de la période {filter_decade}")
    context_str = ", ".join(context_parts) if context_parts else "de n'importe quel pays, région ou catégorie"

    if existing_entries:
        exclusion_block = (
            f"Ma base contient déjà ces {len(existing_entries)} événements (nom + année) :\n"
            f"{chr(10).join('- ' + e for e in existing_entries[:100])}\n"
            f"{'[… et plus]' if len(existing_entries) > 100 else ''}\n\n"
            f"RÈGLE ABSOLUE : ne suggère PAS un événement déjà présent dans cette liste, "
            f"ni un synonyme, ni une variante du même événement "
            f"(ex: si 'Ouragan Katrina' est listé, ne suggère pas 'Katrina 2005' ou 'Hurricane Katrina').\n\n"
        )
    else:
        exclusion_block = ""

    prompt = (
        f"{exclusion_block}"
        f"Suggère UN événement historique important {context_str} qui N'EST PAS déjà dans la liste ci-dessus.\n"
        f"L'événement doit être réel, documenté, et significatif (guerre, catastrophe, révolution, découverte, traité, etc.).\n"
        f"Réponds UNIQUEMENT avec le nom court et clair de l'événement (en français ou en anglais selon l'usage courant).\n"
        f"Aucun autre texte, aucune explication."
    )

    result = generate_city(api_key, model, "", prompt, max_tokens=80, temperature=0.9)
    if result.get("success"):
        result["tokens_total"] = load_settings().get("tokens_used", 0)
    return jsonify(result)


# ---------------------------------------------------------------------------
# AI Lab — Raffinement (Event)
# ---------------------------------------------------------------------------

@web.route("/ai-lab/refine/event/<event_slug>")
@editor_required
def ai_lab_refine_event_load(event_slug: str) -> Response:
    """Load an event's current data as JSON for the Raffinement tab."""
    from .db import get_db
    from .services.event_service import get_event

    conn = get_db()
    event = get_event(conn, event_slug)
    if event is None:
        return jsonify({"success": False, "error": "Événement introuvable."})

    # Use stored source_text or reconstruct from fields
    source_text = event.get("source_text") or ""
    if not source_text:
        lines = [
            f'EVENT_NAME = "{event["event_name"]}"',
            f'EVENT_DATE_START = "{event.get("event_date_start") or ""}"',
            f'EVENT_DATE_END = "{event.get("event_date_end") or ""}"',
            f'EVENT_YEAR = {event.get("event_year") or ""}',
            f'EVENT_LEVEL = {event.get("event_level") or 1}',
            f'EVENT_CATEGORY = "{event.get("event_category") or "autre"}"',
            "",
            "=== DESCRIPTION ===",
            event.get("description") or "",
            "",
            "=== IMPACT POPULATION ===",
            event.get("impact_population") or "",
            "",
            "=== IMPACT MIGRATION ===",
            event.get("impact_migration") or "",
            "",
            "=== LOCATIONS ===",
        ]
        for loc in event.get("locations", []):
            if loc.get("city_name"):
                lines.append(f"{loc['city_name']}, {loc.get('region', '')}, {loc.get('country', '')}, {loc.get('role', 'primary')}")
            else:
                lines.append(f"{loc.get('region', '')}, {loc.get('country', '')}, {loc.get('role', 'primary')}")
        source_text = "\n".join(lines)

    return jsonify({
        "success": True,
        "event_name": event["event_name"],
        "event_year": event.get("event_year"),
        "event_category": event.get("event_category"),
        "event_level": event.get("event_level"),
        "description": (event.get("description") or "")[:300],
        "location_count": len(event.get("locations", [])),
        "source_text": source_text,
    })


@web.route("/ai-lab/refine/event/generate", methods=["POST"])
@editor_required
def ai_lab_refine_event_generate() -> Response:
    """Generate a refined version of an event via AI."""
    from .services.mammouth_ai import load_settings, generate_city
    from .db import get_db
    from .services.event_service import get_event

    settings = load_settings()
    api_key = settings.get("api_key", "")
    if not api_key:
        return jsonify({"success": False, "error": "Aucune clé API configurée."})

    model = request.form.get("model", settings.get("model", "gpt-4.1-mini")).strip()
    event_slug = request.form.get("event_slug", "").strip()
    prompt_text = request.form.get("prompt_text", "").strip()

    if not event_slug:
        return jsonify({"success": False, "error": "Événement non spécifié."})
    if not prompt_text:
        return jsonify({"success": False, "error": "Le prompt est vide."})

    # Load current event text from DB
    conn = get_db()
    event = get_event(conn, event_slug)
    if event is None:
        return jsonify({"success": False, "error": "Événement introuvable."})

    source_text = event.get("source_text") or ""
    if not source_text:
        lines = [
            f'EVENT_NAME = "{event["event_name"]}"',
            f'EVENT_DATE_START = "{event.get("event_date_start") or ""}"',
            f'EVENT_DATE_END = "{event.get("event_date_end") or ""}"',
            f'EVENT_YEAR = {event.get("event_year") or ""}',
            f'EVENT_LEVEL = {event.get("event_level") or 1}',
            f'EVENT_CATEGORY = "{event.get("event_category") or "autre"}"',
            "",
            "=== DESCRIPTION ===",
            event.get("description") or "",
            "",
            "=== IMPACT POPULATION ===",
            event.get("impact_population") or "",
            "",
            "=== IMPACT MIGRATION ===",
            event.get("impact_migration") or "",
            "",
            "=== LOCATIONS ===",
        ]
        for loc in event.get("locations", []):
            if loc.get("city_name"):
                lines.append(f"{loc['city_name']}, {loc.get('region', '')}, {loc.get('country', '')}, {loc.get('role', 'primary')}")
            else:
                lines.append(f"{loc.get('region', '')}, {loc.get('country', '')}, {loc.get('role', 'primary')}")
        source_text = "\n".join(lines)

    # city_input = source_text so {CITY_INPUT} in prompt gets replaced with event text
    result = generate_city(api_key, model, source_text, prompt_text, max_tokens=4000, temperature=0.3)
    if result.get("success"):
        result["tokens_total"] = load_settings().get("tokens_used", 0)
    return jsonify(result)


@web.route("/ai-lab/refine/event/synthesize", methods=["POST"])
@editor_required
def ai_lab_refine_event_synthesize() -> Response:
    """Ask AI to reconcile the original and refined event versions."""
    from .services.mammouth_ai import load_settings, generate_city, load_prompt
    from .db import get_db
    from .services.event_service import get_event

    settings = load_settings()
    api_key = settings.get("api_key", "")
    if not api_key:
        return jsonify({"success": False, "error": "Aucune clé API configurée."})

    model = request.form.get("model", settings.get("model", "gpt-4.1-mini")).strip()
    event_slug = request.form.get("event_slug", "").strip()
    new_text = request.form.get("new_text", "").strip()

    if not event_slug or not new_text:
        return jsonify({"success": False, "error": "Données manquantes pour la synthèse."})

    # Load original event text
    conn = get_db()
    event = get_event(conn, event_slug)
    if event is None:
        return jsonify({"success": False, "error": "Événement introuvable."})

    source_text = event.get("source_text") or ""
    if not source_text:
        lines = [
            f'EVENT_NAME = "{event["event_name"]}"',
            f'EVENT_DATE_START = "{event.get("event_date_start") or ""}"',
            f'EVENT_DATE_END = "{event.get("event_date_end") or ""}"',
            f'EVENT_YEAR = {event.get("event_year") or ""}',
            f'EVENT_LEVEL = {event.get("event_level") or 1}',
            f'EVENT_CATEGORY = "{event.get("event_category") or "autre"}"',
            "",
            "=== DESCRIPTION ===",
            event.get("description") or "",
            "",
            "=== IMPACT POPULATION ===",
            event.get("impact_population") or "",
            "",
            "=== IMPACT MIGRATION ===",
            event.get("impact_migration") or "",
            "",
            "=== LOCATIONS ===",
        ]
        for loc in event.get("locations", []):
            if loc.get("city_name"):
                lines.append(f"{loc['city_name']}, {loc.get('region', '')}, {loc.get('country', '')}, {loc.get('role', 'primary')}")
            else:
                lines.append(f"{loc.get('region', '')}, {loc.get('country', '')}, {loc.get('role', 'primary')}")
        source_text = "\n".join(lines)

    prompt_text = load_prompt("event_synthesize.txt").replace("{NEW_TEXT}", new_text)
    # {CITY_INPUT} will be replaced with source_text (original) by generate_city
    result = generate_city(api_key, model, source_text, prompt_text, max_tokens=4000, temperature=0.2)
    if result.get("success"):
        result["tokens_total"] = load_settings().get("tokens_used", 0)
    return jsonify(result)


@web.route("/ai-lab/refine/event/save", methods=["POST"])
@editor_required
def ai_lab_refine_event_save() -> Response:
    """Save the (refined or synthesized) event text to the database."""
    from .db import get_db
    from .services.event_service import parse_event_text, import_event

    text = request.form.get("event_text", "").strip()
    if not text:
        return jsonify({"success": False, "error": "Texte vide."})

    try:
        data = parse_event_text(text)
        data["source_text"] = text
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)})

    conn = get_db()
    event_id = import_event(conn, data)
    log_action("import", "event", data["event_slug"],
               f"Événement raffiné sauvegardé: {data['event_name']}")
    return jsonify({
        "success": True,
        "event_name": data["event_name"],
        "event_slug": data["event_slug"],
        "event_id": event_id,
        "redirect": url_for("web.event_detail", event_slug=data["event_slug"]),
    })


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@web.route("/events")
def events_list() -> str:
    from .db import get_db
    from .services.event_service import get_events_list, get_event_primary_photo, EVENT_CATEGORIES, CATEGORY_LABELS, CATEGORY_EMOJIS

    conn = get_db()
    filters = {
        "category": request.args.get("category", ""),
        "level": request.args.get("level", ""),
        "search": request.args.get("search", ""),
    }
    view_mode = request.args.get("view", "small").strip().lower()
    if view_mode not in {"large", "medium", "small", "compact"}:
        view_mode = "small"
    events = get_events_list(conn, filters)
    for ev in events:
        ev["primary_photo"] = get_event_primary_photo(conn, ev["event_slug"])
    return render_template(
        "web/events.html",
        page_title="Événements historiques",
        events=events,
        filters=filters,
        view_mode=view_mode,
        categories=EVENT_CATEGORIES,
        category_labels=CATEGORY_LABELS,
        category_emojis=CATEGORY_EMOJIS,
    )


@web.route("/events/<event_slug>")
def event_detail(event_slug: str) -> str:
    from .db import get_db
    from .services.event_service import get_event, CATEGORY_LABELS, CATEGORY_EMOJIS
    from .services.city_photos import count_missing_photos

    conn = get_db()
    event = get_event(conn, event_slug)
    if event is None:
        flash("Événement introuvable.", "error")
        return redirect(url_for("web.events_list"))
    return render_template(
        "web/event_detail.html",
        page_title=event["event_name"],
        event=event,
        category_labels=CATEGORY_LABELS,
        category_emojis=CATEGORY_EMOJIS,
        missing_photos_count=count_missing_photos(conn, "event", event_slug),
    )


@web.route("/events/import", methods=["POST"])
@editor_required
def event_import() -> Response:
    from .db import get_db
    from .services.event_service import parse_event_text, import_event

    text = request.form.get("event_text", "").strip()
    if not text:
        return jsonify({"success": False, "error": "Texte vide."})
    try:
        data = parse_event_text(text)
        data["source_text"] = text
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)})

    conn = get_db()
    event_id = import_event(conn, data)
    log_action("import", "event", data["event_slug"], f"Événement importé: {data['event_name']} ({data.get('event_year', '')})")
    return jsonify({
        "success": True,
        "event_name": data["event_name"],
        "event_slug": data["event_slug"],
        "event_id": event_id,
        "redirect": url_for("web.event_detail", event_slug=data["event_slug"]),
    })


@web.route("/events/<event_slug>/delete", methods=["POST"])
@editor_required
def event_delete(event_slug: str) -> Response:
    from .db import get_db
    from .services.event_service import get_event, delete_event

    conn = get_db()
    event = get_event(conn, event_slug)
    if event is None:
        flash("Événement introuvable.", "error")
        return redirect(url_for("web.events_list"))
    delete_event(conn, event["event_id"])
    log_action("delete", "event", event_slug, f"Événement '{event['event_name']}' supprimé")
    flash(f"Événement « {event['event_name']} » supprimé.", "success")
    return redirect(url_for("web.events_list"))


@web.route("/events/<event_slug>/photos/upload", methods=["POST"])
@editor_required
def event_photo_upload(event_slug: str) -> Response:
    from .db import get_db
    from .services.event_service import get_event, save_event_photo

    conn = get_db()
    event = get_event(conn, event_slug)
    if event is None:
        return jsonify({"success": False, "error": "Événement introuvable."})

    file = request.files.get("photo")
    if not file or not file.filename:
        return jsonify({"success": False, "error": "Aucun fichier sélectionné."})

    result = save_event_photo(
        conn,
        event["event_id"],
        event_slug,
        file.read(),
        file.filename,
        source_url=request.form.get("source_url", ""),
        attribution=request.form.get("attribution", ""),
        caption=request.form.get("caption", ""),
        set_primary=request.form.get("set_primary") == "on",
    )
    if result.get("success"):
        log_action("upload_photo", "event", event_slug, f"Photo uploadée pour l'événement {event['event_name']}")
    return jsonify(result)


@web.route("/events/<event_slug>/photos/<int:photo_id>/delete", methods=["POST"])
@editor_required
def event_photo_delete(event_slug: str, photo_id: int) -> Response:
    from .db import get_db
    from .services.event_service import delete_event_photo

    conn = get_db()
    delete_event_photo(conn, photo_id, event_slug)
    log_action("delete_photo", "event", event_slug, f"Photo #{photo_id} supprimée de l'événement {event_slug}")
    return jsonify({"success": True})


@web.route("/events/<event_slug>/photos/<int:photo_id>/primary", methods=["POST"])
@editor_required
def event_photo_primary(event_slug: str, photo_id: int) -> Response:
    from .db import get_db
    from .services.event_service import get_event, set_event_photo_primary

    conn = get_db()
    event = get_event(conn, event_slug)
    if event is None:
        return jsonify({"success": False, "error": "Événement introuvable."})
    set_event_photo_primary(conn, photo_id, event["event_id"])
    log_action("update_photo", "event", event_slug, f"Photo #{photo_id} définie comme principale pour l'événement {event['event_name']}")
    return jsonify({"success": True})


@web.route("/events/<event_slug>/photos/search")
def event_photo_search(event_slug: str) -> Response:
    """AJAX: smart multi-tier search for event photos (Wikipedia + Commons)."""
    import re
    from .db import get_db
    from .services.event_service import get_event
    from .services.city_photos import search_annotation_images

    conn = get_db()
    event = get_event(conn, event_slug)
    if event is None:
        return jsonify({"error": "Événement introuvable.", "images": []})

    # Build a label similar to annotation format for the tiered search
    event_name = event["event_name"]
    year = event.get("event_year")

    # Clean emoji and extract a concise label
    clean_name = re.sub(r'[\U00010000-\U0010ffff]', '', event_name).strip()

    # For long event names, build a shorter search-friendly version
    _stop = {"le", "la", "les", "de", "du", "des", "un", "une", "et", "en",
             "au", "aux", "ce", "ces", "se", "sa", "son", "ses", "sur", "par",
             "pour", "dans", "est", "qui", "que", "avec", "vers", "pas", "plus",
             "très", "tout", "mais", "remporte", "lors", "entre", "sans",
             "leur", "leurs", "sont", "ont", "été", "fait", "elle", "ils",
             "aussi", "même", "être", "nous", "vous", "comme", "après",
             "soirée", "jour", "fois", "cette", "autre", "contre",
             "album", "essor", "dont", "puis", "avant", "selon",
             "sous", "chez", "dès", "hors", "via", "notre", "votre"}
    # Common French event-start words (not useful as search terms)
    _fr_event_words = {
        "sortie", "création", "construction", "inauguration", "ouverture",
        "fermeture", "fondation", "début", "arrivée", "découverte",
        "naissance", "mort", "adoption", "abolition", "introduction",
        "apparition", "disparition", "lancement", "publication",
        "signature", "proclamation", "déclaration", "série",
        "établissement", "installation", "invention", "ratification",
        "première", "explosion", "incendie", "inondation",
        "victoire", "défaite", "assassinat", "attentat", "attentats",
        "diffusion", "présentation", "annonce", "séisme",
        "tremblement", "fusion", "annexion", "démolition",
        "reconstruction", "rénovation", "effondrement",
        "épidémie", "pandémie", "grève", "émeute",
    }
    # Tokenize properly: split on apostrophes and non-letter chars
    stripped = re.sub(r'\(\d{4}\)', '', clean_name)
    tokens = re.findall(r"[a-zA-ZÀ-ÿ]{2,}", stripped)
    meaningful = [w for w in tokens
                  if w.lower() not in _stop and len(w) >= 3]

    orig_words = clean_name.split()
    if len(orig_words) > 8 or len(clean_name) > 60:
        # True proper nouns: capitalized + acronyms + digits, excluding
        # common French event-start words
        proper = [w for w in meaningful
                  if (w[0].isupper() or w.isupper() or w.isdigit())
                  and w.lower() not in _fr_event_words]
        other = [w for w in meaningful
                 if w not in proper and w.lower() not in _fr_event_words]
        if proper:
            condensed = list(proper[:5])
            remaining = max(5 - len(condensed), 1)
            condensed.extend(other[:remaining])
            clean_name = ' '.join(condensed[:5])
        elif len(meaningful) > 5:
            filtered = [w for w in meaningful
                        if w.lower() not in _fr_event_words]
            clean_name = ' '.join(filtered[:5])

    label = f"{clean_name} ({year})" if year else clean_name

    # Use the first location's city/region/country for context, or empty
    locs = event.get("locations", [])
    city_name = ""
    region = None
    country = None
    for loc in locs:
        if loc.get("role") == "primary":
            city_name = loc.get("matched_city_name") or loc.get("region") or ""
            region = loc.get("region")
            country = loc.get("country")
            break
    if not city_name and locs:
        loc = locs[0]
        city_name = loc.get("matched_city_name") or loc.get("region") or ""
        region = loc.get("region")
        country = loc.get("country")

    images = search_annotation_images(label, city_name, region, country)
    return jsonify({"images": images})


@web.route("/events/<event_slug>/photos/manual-search")
def event_photo_manual_search(event_slug: str) -> Response:
    """AJAX: manual keyword search on Wikimedia Commons for event photos."""
    from .services.city_photos import _search_commons_batch

    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"images": []})

    seen_urls: set[str] = set()
    images: list[dict] = []

    # If query has more than 4 words, search with progressively shorter
    # sub-queries to get better results from Commons API
    words = query.split()
    if len(words) <= 4:
        images = _search_commons_batch(query, seen_urls, limit=40)
    else:
        # 1. Try full query first (may return few results)
        images.extend(_search_commons_batch(query, seen_urls, limit=20))
        # 2. Try first 4 words
        sub = " ".join(words[:4])
        images.extend(_search_commons_batch(sub, seen_urls, limit=20))
        # 3. Try first 3 words
        if len(images) < 20:
            sub = " ".join(words[:3])
            images.extend(_search_commons_batch(sub, seen_urls, limit=20))
        # 4. Try last meaningful words (often the subject)
        if len(images) < 15:
            sub = " ".join(words[-3:])
            images.extend(_search_commons_batch(sub, seen_urls, limit=20))

    return jsonify({"images": images[:40]})


@web.route("/events/<event_slug>/photos/import-web", methods=["POST"])
@editor_required
def event_photo_import_web(event_slug: str) -> Response:
    """Import multiple web images into an event's photo library."""
    from .db import get_db
    from .services.event_service import get_event, save_event_photo
    from .services.city_photos import download_web_image

    conn = get_db()
    event = get_event(conn, event_slug)
    if event is None:
        return jsonify({"error": "Événement introuvable.", "imported": 0})

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
        save_result = save_event_photo(
            conn,
            event["event_id"],
            event_slug,
            file_bytes,
            f"web-import{ext}",
            source_url=img.get("source_page", ""),
            attribution=img.get("title", "Wikipedia/Wikimedia"),
            caption=img.get("caption", ""),
            set_primary=(imported == 0 and not event.get("photos")),
            image_url=url,
        )
        if save_result.get("success"):
            imported += 1
    if imported:
        log_action("upload_photo", "event", event_slug, f"{imported} photo(s) importée(s) depuis le web pour l'événement {event['event_name']}")
    return jsonify({"imported": imported})


# ---------------------------------------------------------------------------
# AI Lab — Person (suggest / refine / synthesize / save)
# ---------------------------------------------------------------------------

@web.route("/ai-lab/suggest-person", methods=["POST"])
@editor_required
def ai_lab_suggest_person() -> Response:
    """Ask Mammouth to suggest a historical figure not yet in the DB."""
    from .services.mammouth_ai import load_settings, generate_city
    from .services.person_service import CATEGORY_LABELS
    from .db import get_db

    settings = load_settings()
    api_key = settings.get("api_key", "")
    if not api_key:
        return jsonify({"success": False, "error": "Aucune clé API configurée."})

    model = request.form.get("model", settings.get("model", "gpt-4.1-mini")).strip()
    filter_country  = request.form.get("country", "").strip()
    filter_region   = request.form.get("region", "").strip()
    filter_category = request.form.get("category", "").strip()
    filter_decade   = request.form.get("decade", "").strip()

    conn = get_db()
    existing_rows = conn.execute(
        "SELECT person_name, person_slug, birth_year FROM dim_person ORDER BY person_name"
    ).fetchall()
    existing_entries = [
        f"{r['person_name']} ({r['birth_year']})" if r["birth_year"] else r["person_name"]
        for r in existing_rows
    ]

    context_parts: list[str] = []
    if filter_country:
        context_parts.append(f"lié au pays '{filter_country}'")
    if filter_region:
        context_parts.append(f"lié à la région '{filter_region}'")
    if filter_category:
        label = CATEGORY_LABELS.get(filter_category, filter_category)
        context_parts.append(f"dans la catégorie '{label}'")
    if filter_decade:
        context_parts.append(f"ayant vécu durant la période {filter_decade}")
    context_str = ", ".join(context_parts) if context_parts else "de n'importe quel pays, région ou catégorie"

    if existing_entries:
        exclusion_block = (
            f"Ma base contient déjà ces {len(existing_entries)} personnages (nom + année de naissance) :\n"
            f"{chr(10).join('- ' + e for e in existing_entries[:100])}\n"
            f"{'[… et plus]' if len(existing_entries) > 100 else ''}\n\n"
            f"RÈGLE ABSOLUE : ne suggère PAS un personnage déjà présent dans cette liste, "
            f"ni un synonyme, ni une variante du même nom.\n\n"
        )
    else:
        exclusion_block = ""

    prompt = (
        f"{exclusion_block}"
        f"Suggère UN personnage historique important {context_str} qui N'EST PAS déjà dans la liste ci-dessus.\n"
        f"Le personnage doit être réel, documenté et historiquement significatif.\n"
        f"Réponds UNIQUEMENT avec le nom complet du personnage (prénom + nom).\n"
        f"Aucun autre texte, aucune explication."
    )

    result = generate_city(api_key, model, "", prompt, max_tokens=80, temperature=0.9)
    if result.get("success"):
        result["tokens_total"] = load_settings().get("tokens_used", 0)
    return jsonify(result)


@web.route("/ai-lab/refine/person/<person_slug>")
@editor_required
def ai_lab_refine_person_load(person_slug: str) -> Response:
    """Load a person's current data as JSON for the Raffinement tab."""
    from .db import get_db
    from .services.person_service import get_person

    conn = get_db()
    person = get_person(conn, person_slug)
    if person is None:
        return jsonify({"success": False, "error": "Personnage introuvable."})

    source_text = person.get("source_text") or ""
    if not source_text:
        lines = [
            f'PERSON_NAME = "{person["person_name"]}"',
            f'BIRTH_DATE = "{person.get("birth_date") or ""}"',
            f'DEATH_DATE = "{person.get("death_date") or ""}"',
            f'BIRTH_YEAR = {person.get("birth_year") or ""}',
            f'DEATH_YEAR = {person.get("death_year") or ""}',
            f'BIRTH_CITY = "{person.get("birth_city") or ""}"',
            f'BIRTH_COUNTRY = "{person.get("birth_country") or ""}"',
            f'DEATH_CITY = "{person.get("death_city") or ""}"',
            f'DEATH_COUNTRY = "{person.get("death_country") or ""}"',
            f'PERSON_LEVEL = {person.get("person_level") or 2}',
            f'PERSON_CATEGORY = "{person.get("person_category") or "autre"}"',
            "",
            "=== RÉSUMÉ ===",
            person.get("summary") or "",
            "",
            "=== BIOGRAPHIE ===",
            person.get("biography") or "",
            "",
            "=== RÉALISATIONS ===",
            person.get("achievements") or "",
            "",
            "=== IMPACT ===",
            person.get("impact_population") or "",
            "",
            "=== LIEUX ===",
        ]
        for loc in person.get("locations", []):
            if loc.get("city_name") or loc.get("matched_city_name"):
                city_name = loc.get("matched_city_name") or loc.get("city_name") or ""
                lines.append(f"{city_name}, {loc.get('region', '')}, {loc.get('country', '')}, {loc.get('role', 'primary')}")
            else:
                lines.append(f"{loc.get('region', '')}, {loc.get('country', '')}, {loc.get('role', 'primary')}")
        source_text = "\n".join(lines)

    return jsonify({
        "success": True,
        "person_name": person["person_name"],
        "birth_year": person.get("birth_year"),
        "death_year": person.get("death_year"),
        "person_category": person.get("person_category"),
        "person_level": person.get("person_level"),
        "summary": (person.get("summary") or "")[:300],
        "location_count": len(person.get("locations", [])),
        "source_text": source_text,
    })


@web.route("/ai-lab/refine/person/generate", methods=["POST"])
@editor_required
def ai_lab_refine_person_generate() -> Response:
    """Generate a refined version of a person via AI."""
    from .services.mammouth_ai import load_settings, generate_city
    from .db import get_db
    from .services.person_service import get_person

    settings = load_settings()
    api_key = settings.get("api_key", "")
    if not api_key:
        return jsonify({"success": False, "error": "Aucune clé API configurée."})

    model = request.form.get("model", settings.get("model", "gpt-4.1-mini")).strip()
    person_slug = request.form.get("person_slug", "").strip()
    prompt_text = request.form.get("prompt_text", "").strip()

    if not person_slug:
        return jsonify({"success": False, "error": "Personnage non spécifié."})
    if not prompt_text:
        return jsonify({"success": False, "error": "Le prompt est vide."})

    conn = get_db()
    person = get_person(conn, person_slug)
    if person is None:
        return jsonify({"success": False, "error": "Personnage introuvable."})

    source_text = person.get("source_text") or ""
    if not source_text:
        lines = [
            f'PERSON_NAME = "{person["person_name"]}"',
            f'BIRTH_DATE = "{person.get("birth_date") or ""}"',
            f'DEATH_DATE = "{person.get("death_date") or ""}"',
            f'BIRTH_YEAR = {person.get("birth_year") or ""}',
            f'DEATH_YEAR = {person.get("death_year") or ""}',
            f'BIRTH_CITY = "{person.get("birth_city") or ""}"',
            f'BIRTH_COUNTRY = "{person.get("birth_country") or ""}"',
            f'DEATH_CITY = "{person.get("death_city") or ""}"',
            f'DEATH_COUNTRY = "{person.get("death_country") or ""}"',
            f'PERSON_LEVEL = {person.get("person_level") or 2}',
            f'PERSON_CATEGORY = "{person.get("person_category") or "autre"}"',
            "",
            "=== RÉSUMÉ ===",
            person.get("summary") or "",
            "",
            "=== BIOGRAPHIE ===",
            person.get("biography") or "",
            "",
            "=== RÉALISATIONS ===",
            person.get("achievements") or "",
            "",
            "=== IMPACT ===",
            person.get("impact_population") or "",
            "",
            "=== LIEUX ===",
        ]
        for loc in person.get("locations", []):
            if loc.get("city_name") or loc.get("matched_city_name"):
                city_name = loc.get("matched_city_name") or loc.get("city_name") or ""
                lines.append(f"{city_name}, {loc.get('region', '')}, {loc.get('country', '')}, {loc.get('role', 'primary')}")
            else:
                lines.append(f"{loc.get('region', '')}, {loc.get('country', '')}, {loc.get('role', 'primary')}")
        source_text = "\n".join(lines)

    result = generate_city(api_key, model, source_text, prompt_text, max_tokens=4000, temperature=0.3)
    if result.get("success"):
        result["tokens_total"] = load_settings().get("tokens_used", 0)
    return jsonify(result)


@web.route("/ai-lab/refine/person/synthesize", methods=["POST"])
@editor_required
def ai_lab_refine_person_synthesize() -> Response:
    """Ask AI to reconcile the original and refined person versions."""
    from .services.mammouth_ai import load_settings, generate_city, load_prompt
    from .db import get_db
    from .services.person_service import get_person

    settings = load_settings()
    api_key = settings.get("api_key", "")
    if not api_key:
        return jsonify({"success": False, "error": "Aucune clé API configurée."})

    model = request.form.get("model", settings.get("model", "gpt-4.1-mini")).strip()
    person_slug = request.form.get("person_slug", "").strip()
    new_text = request.form.get("new_text", "").strip()

    if not person_slug or not new_text:
        return jsonify({"success": False, "error": "Données manquantes pour la synthèse."})

    conn = get_db()
    person = get_person(conn, person_slug)
    if person is None:
        return jsonify({"success": False, "error": "Personnage introuvable."})

    source_text = person.get("source_text") or ""
    if not source_text:
        lines = [
            f'PERSON_NAME = "{person["person_name"]}"',
            f'BIRTH_DATE = "{person.get("birth_date") or ""}"',
            f'DEATH_DATE = "{person.get("death_date") or ""}"',
            f'BIRTH_YEAR = {person.get("birth_year") or ""}',
            f'DEATH_YEAR = {person.get("death_year") or ""}',
            f'BIRTH_CITY = "{person.get("birth_city") or ""}"',
            f'BIRTH_COUNTRY = "{person.get("birth_country") or ""}"',
            f'DEATH_CITY = "{person.get("death_city") or ""}"',
            f'DEATH_COUNTRY = "{person.get("death_country") or ""}"',
            f'PERSON_LEVEL = {person.get("person_level") or 2}',
            f'PERSON_CATEGORY = "{person.get("person_category") or "autre"}"',
            "",
            "=== RÉSUMÉ ===",
            person.get("summary") or "",
            "",
            "=== BIOGRAPHIE ===",
            person.get("biography") or "",
            "",
            "=== RÉALISATIONS ===",
            person.get("achievements") or "",
            "",
            "=== IMPACT ===",
            person.get("impact_population") or "",
            "",
            "=== LIEUX ===",
        ]
        for loc in person.get("locations", []):
            if loc.get("city_name") or loc.get("matched_city_name"):
                city_name = loc.get("matched_city_name") or loc.get("city_name") or ""
                lines.append(f"{city_name}, {loc.get('region', '')}, {loc.get('country', '')}, {loc.get('role', 'primary')}")
            else:
                lines.append(f"{loc.get('region', '')}, {loc.get('country', '')}, {loc.get('role', 'primary')}")
        source_text = "\n".join(lines)

    prompt_text = load_prompt("person_synthesize.txt").replace("{NEW_TEXT}", new_text)
    result = generate_city(api_key, model, source_text, prompt_text, max_tokens=4000, temperature=0.2)
    if result.get("success"):
        result["tokens_total"] = load_settings().get("tokens_used", 0)
    return jsonify(result)


@web.route("/ai-lab/refine/person/save", methods=["POST"])
@editor_required
def ai_lab_refine_person_save() -> Response:
    """Save the (refined or synthesized) person text to the database."""
    from .db import get_db
    from .services.person_service import parse_person_text, import_person

    text = request.form.get("person_text", "").strip()
    if not text:
        return jsonify({"success": False, "error": "Texte vide."})

    try:
        data = parse_person_text(text)
        data["source_text"] = text
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)})

    conn = get_db()
    person_id = import_person(conn, data)
    log_action("import", "person", data["person_slug"],
               f"Personnage raffiné sauvegardé: {data['person_name']}")
    return jsonify({
        "success": True,
        "person_name": data["person_name"],
        "person_slug": data["person_slug"],
        "person_id": person_id,
        "redirect": url_for("web.person_detail", person_slug=data["person_slug"]),
    })


# ---------------------------------------------------------------------------
# Persons (Historical Figures)
# ---------------------------------------------------------------------------

@web.route("/persons")
def persons_list() -> str:
    from .db import get_db
    from .services.person_service import get_persons_list, get_person_primary_photo, PERSON_CATEGORIES, CATEGORY_LABELS, CATEGORY_EMOJIS

    conn = get_db()
    filters = {
        "category": request.args.get("category", ""),
        "level": request.args.get("level", ""),
        "search": request.args.get("search", ""),
    }
    view_mode = request.args.get("view", "small").strip().lower()
    if view_mode not in {"large", "medium", "small", "compact"}:
        view_mode = "small"
    persons = get_persons_list(conn, filters)
    for p in persons:
        p["primary_photo"] = get_person_primary_photo(conn, p["person_slug"])
    return render_template(
        "web/persons.html",
        page_title="Personnages historiques",
        persons=persons,
        filters=filters,
        view_mode=view_mode,
        categories=PERSON_CATEGORIES,
        category_labels=CATEGORY_LABELS,
        category_emojis=CATEGORY_EMOJIS,
    )


@web.route("/persons/<person_slug>")
def person_detail(person_slug: str) -> str:
    from .db import get_db
    from .services.person_service import get_person, CATEGORY_LABELS, CATEGORY_EMOJIS
    from .services.city_photos import count_missing_photos

    conn = get_db()
    person = get_person(conn, person_slug)
    if person is None:
        flash("Personnage introuvable.", "error")
        return redirect(url_for("web.persons_list"))
    return render_template(
        "web/person_detail.html",
        page_title=person["person_name"],
        person=person,
        category_labels=CATEGORY_LABELS,
        category_emojis=CATEGORY_EMOJIS,
        missing_photos_count=count_missing_photos(conn, "person", person_slug),
    )


@web.route("/persons/import", methods=["POST"])
@editor_required
def person_import() -> Response:
    from .db import get_db
    from .services.person_service import parse_person_text, import_person

    text = request.form.get("person_text", "").strip()
    if not text:
        return jsonify({"success": False, "error": "Texte vide."})
    try:
        data = parse_person_text(text)
        data["source_text"] = text
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)})

    conn = get_db()
    person_id = import_person(conn, data)
    log_action("import", "person", data["person_slug"], f"Personnage importé: {data['person_name']} ({data.get('birth_year', '')})")

    # Auto-search portrait photo from Wikipedia
    _auto_import_person_photo(conn, person_id, data["person_slug"], data["person_name"])

    return jsonify({
        "success": True,
        "person_name": data["person_name"],
        "person_slug": data["person_slug"],
        "person_id": person_id,
        "redirect": url_for("web.person_detail", person_slug=data["person_slug"]),
    })


def _auto_import_person_photo(conn, person_id: int, person_slug: str, person_name: str) -> None:
    """Try to auto-import a portrait photo from Wikipedia/Commons."""
    try:
        from .services.city_photos import search_annotation_images, download_web_image
        from .services.person_service import save_person_photo

        images = search_annotation_images(person_name, "", None, None)
        if images:
            img = images[0]
            result = download_web_image(img.get("url", ""))
            if result:
                file_bytes, ext = result
                save_person_photo(
                    conn, person_id, person_slug,
                    file_bytes, f"auto-portrait{ext}",
                    source_url=img.get("source_page", ""),
                    attribution=img.get("title", "Wikipedia/Wikimedia"),
                    caption=f"Portrait de {person_name}",
                    set_primary=True,
                    image_url=img.get("url", ""),
                )
    except Exception:
        pass  # Non-critical: don't fail import if photo search fails


@web.route("/persons/<person_slug>/delete", methods=["POST"])
@editor_required
def person_delete(person_slug: str) -> Response:
    from .db import get_db
    from .services.person_service import get_person, delete_person

    conn = get_db()
    person = get_person(conn, person_slug)
    if person is None:
        flash("Personnage introuvable.", "error")
        return redirect(url_for("web.persons_list"))
    delete_person(conn, person["person_id"])
    log_action("delete", "person", person_slug, f"Personnage '{person['person_name']}' supprimé")
    flash(f"Personnage « {person['person_name']} » supprimé.", "success")
    return redirect(url_for("web.persons_list"))


@web.route("/persons/<person_slug>/photos/upload", methods=["POST"])
@editor_required
def person_photo_upload(person_slug: str) -> Response:
    from .db import get_db
    from .services.person_service import get_person, save_person_photo

    conn = get_db()
    person = get_person(conn, person_slug)
    if person is None:
        return jsonify({"success": False, "error": "Personnage introuvable."})

    file = request.files.get("photo")
    if not file or not file.filename:
        return jsonify({"success": False, "error": "Aucun fichier sélectionné."})

    result = save_person_photo(
        conn,
        person["person_id"],
        person_slug,
        file.read(),
        file.filename,
        source_url=request.form.get("source_url", ""),
        attribution=request.form.get("attribution", ""),
        caption=request.form.get("caption", ""),
        set_primary=request.form.get("set_primary") == "on",
    )
    if result.get("success"):
        log_action("upload_photo", "person", person_slug, f"Photo uploadée pour le personnage {person['person_name']}")
    return jsonify(result)


@web.route("/persons/<person_slug>/photos/<int:photo_id>/delete", methods=["POST"])
@editor_required
def person_photo_delete(person_slug: str, photo_id: int) -> Response:
    from .db import get_db
    from .services.person_service import delete_person_photo

    conn = get_db()
    delete_person_photo(conn, photo_id, person_slug)
    log_action("delete_photo", "person", person_slug, f"Photo #{photo_id} supprimée du personnage {person_slug}")
    return jsonify({"success": True})


@web.route("/persons/<person_slug>/photos/<int:photo_id>/primary", methods=["POST"])
@editor_required
def person_photo_primary(person_slug: str, photo_id: int) -> Response:
    from .db import get_db
    from .services.person_service import get_person, set_person_photo_primary

    conn = get_db()
    person = get_person(conn, person_slug)
    if person is None:
        return jsonify({"success": False, "error": "Personnage introuvable."})
    set_person_photo_primary(conn, photo_id, person["person_id"])
    log_action("update_photo", "person", person_slug, f"Photo #{photo_id} définie comme principale pour {person['person_name']}")
    return jsonify({"success": True})


@web.route("/persons/<person_slug>/photos/search")
def person_photo_search(person_slug: str) -> Response:
    """AJAX: smart search for person photos (Wikipedia + Commons)."""
    from .db import get_db
    from .services.person_service import get_person
    from .services.city_photos import search_annotation_images

    conn = get_db()
    person = get_person(conn, person_slug)
    if person is None:
        return jsonify({"error": "Personnage introuvable.", "images": []})

    person_name = person["person_name"]
    birth_year = person.get("birth_year")
    label = f"{person_name} ({birth_year})" if birth_year else person_name

    city_name = person.get("birth_city") or ""
    country = person.get("birth_country")
    images = search_annotation_images(label, city_name, None, country)
    return jsonify({"images": images})


@web.route("/persons/<person_slug>/photos/manual-search")
def person_photo_manual_search(person_slug: str) -> Response:
    """AJAX: manual keyword search on Wikimedia Commons for person photos."""
    from .services.city_photos import _search_commons_batch

    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"images": []})

    seen_urls: set[str] = set()
    images: list[dict] = []

    words = query.split()
    if len(words) <= 4:
        images = _search_commons_batch(query, seen_urls, limit=40)
    else:
        images.extend(_search_commons_batch(query, seen_urls, limit=20))
        sub = " ".join(words[:4])
        images.extend(_search_commons_batch(sub, seen_urls, limit=20))
        if len(images) < 20:
            sub = " ".join(words[:3])
            images.extend(_search_commons_batch(sub, seen_urls, limit=20))
        if len(images) < 15:
            sub = " ".join(words[-3:])
            images.extend(_search_commons_batch(sub, seen_urls, limit=20))

    return jsonify({"images": images[:40]})


@web.route("/persons/<person_slug>/photos/import-web", methods=["POST"])
@editor_required
def person_photo_import_web(person_slug: str) -> Response:
    """Import multiple web images into a person's photo library."""
    from .db import get_db
    from .services.person_service import get_person, save_person_photo
    from .services.city_photos import download_web_image

    conn = get_db()
    person = get_person(conn, person_slug)
    if person is None:
        return jsonify({"error": "Personnage introuvable.", "imported": 0})

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
        save_result = save_person_photo(
            conn,
            person["person_id"],
            person_slug,
            file_bytes,
            f"web-import{ext}",
            source_url=img.get("source_page", ""),
            attribution=img.get("title", "Wikipedia/Wikimedia"),
            caption=img.get("caption", ""),
            set_primary=(imported == 0 and not person.get("photos")),
            image_url=url,
        )
        if save_result.get("success"):
            imported += 1
    if imported:
        log_action("upload_photo", "person", person_slug, f"{imported} photo(s) importée(s) depuis le web pour {person['person_name']}")
    return jsonify({"imported": imported})


# ---------------------------------------------------------------------------
# Monuments – AI Lab routes
# ---------------------------------------------------------------------------

@web.route("/ai-lab/suggest-monument", methods=["POST"])
@editor_required
def ai_lab_suggest_monument() -> Response:
    """Ask Mammouth to suggest a monument not yet in the DB."""
    from .services.mammouth_ai import load_settings, generate_city
    from .services.monument_service import CATEGORY_LABELS
    from .db import get_db

    settings = load_settings()
    api_key = settings.get("api_key", "")
    if not api_key:
        return jsonify({"success": False, "error": "Aucune clé API configurée."})

    model = request.form.get("model", settings.get("model", "gpt-4.1-mini")).strip()
    filter_country  = request.form.get("country", "").strip()
    filter_region   = request.form.get("region", "").strip()
    filter_category = request.form.get("category", "").strip()
    filter_decade   = request.form.get("decade", "").strip()

    conn = get_db()
    existing_rows = conn.execute(
        "SELECT monument_name, monument_slug, construction_year FROM dim_monument ORDER BY monument_name"
    ).fetchall()
    existing_entries = [
        f"{r['monument_name']} ({r['construction_year']})" if r["construction_year"] else r["monument_name"]
        for r in existing_rows
    ]

    context_parts: list[str] = []
    if filter_country:
        context_parts.append(f"situé dans le pays '{filter_country}'")
    if filter_region:
        context_parts.append(f"situé dans la région '{filter_region}'")
    if filter_category:
        label = CATEGORY_LABELS.get(filter_category, filter_category)
        context_parts.append(f"dans la catégorie '{label}'")
    if filter_decade:
        context_parts.append(f"construit durant la période {filter_decade}")
    context_str = ", ".join(context_parts) if context_parts else "de n'importe quel pays, région ou catégorie"

    if existing_entries:
        exclusion_block = (
            f"Ma base contient déjà ces {len(existing_entries)} monuments (nom + année de construction) :\n"
            f"{chr(10).join('- ' + e for e in existing_entries[:100])}\n"
            f"{'[… et plus]' if len(existing_entries) > 100 else ''}\n\n"
            f"RÈGLE ABSOLUE : ne suggère PAS un monument déjà présent dans cette liste, "
            f"ni un synonyme, ni une variante du même nom.\n\n"
        )
    else:
        exclusion_block = ""

    prompt = (
        f"{exclusion_block}"
        f"Suggère UN monument ou bâtiment remarquable {context_str} qui N'EST PAS déjà dans la liste ci-dessus.\n"
        f"Le monument doit être réel, documenté et architecturalement ou historiquement significatif.\n"
        f"Réponds UNIQUEMENT avec le nom complet du monument.\n"
        f"Aucun autre texte, aucune explication."
    )

    result = generate_city(api_key, model, "", prompt, max_tokens=80, temperature=0.9)
    if result.get("success"):
        result["tokens_total"] = load_settings().get("tokens_used", 0)
    return jsonify(result)


@web.route("/ai-lab/refine/monument/<monument_slug>")
@editor_required
def ai_lab_refine_monument_load(monument_slug: str) -> Response:
    """Load a monument's current data as JSON for the Raffinement tab."""
    from .db import get_db
    from .services.monument_service import get_monument

    conn = get_db()
    monument = get_monument(conn, monument_slug)
    if monument is None:
        return jsonify({"success": False, "error": "Monument introuvable."})

    source_text = monument.get("source_text") or ""
    if not source_text:
        lines = [
            f'MONUMENT_NAME = "{monument["monument_name"]}"',
            f'CONSTRUCTION_DATE = "{monument.get("construction_date") or ""}"',
            f'INAUGURATION_DATE = "{monument.get("inauguration_date") or ""}"',
            f'CONSTRUCTION_YEAR = {monument.get("construction_year") or ""}',
            f'DEMOLITION_YEAR = {monument.get("demolition_year") or ""}',
            f'ARCHITECT = "{monument.get("architect") or ""}"',
            f'ARCHITECTURAL_STYLE = "{monument.get("architectural_style") or ""}"',
            f'HEIGHT_METERS = {monument.get("height_meters") or ""}',
            f'FLOORS = {monument.get("floors") or ""}',
            f'MONUMENT_LEVEL = {monument.get("monument_level") or 2}',
            f'MONUMENT_CATEGORY = "{monument.get("monument_category") or "autre"}"',
            "",
            "=== RÉSUMÉ ===",
            monument.get("summary") or "",
            "",
            "=== DESCRIPTION ===",
            monument.get("description") or "",
            "",
            "=== HISTOIRE ===",
            monument.get("history") or "",
            "",
            "=== SIGNIFICATION ===",
            monument.get("significance") or "",
            "",
            "=== LIEUX ===",
        ]
        for loc in monument.get("locations", []):
            if loc.get("city_name") or loc.get("matched_city_name"):
                city_name = loc.get("matched_city_name") or loc.get("city_name") or ""
                lines.append(f"{city_name}, {loc.get('region', '')}, {loc.get('country', '')}, {loc.get('role', 'primary')}")
            else:
                lines.append(f"{loc.get('region', '')}, {loc.get('country', '')}, {loc.get('role', 'primary')}")
        source_text = "\n".join(lines)

    return jsonify({
        "success": True,
        "monument_name": monument["monument_name"],
        "construction_year": monument.get("construction_year"),
        "demolition_year": monument.get("demolition_year"),
        "monument_category": monument.get("monument_category"),
        "monument_level": monument.get("monument_level"),
        "summary": (monument.get("summary") or "")[:300],
        "location_count": len(monument.get("locations", [])),
        "source_text": source_text,
    })


@web.route("/ai-lab/refine/monument/generate", methods=["POST"])
@editor_required
def ai_lab_refine_monument_generate() -> Response:
    """Generate a refined version of a monument via AI."""
    from .services.mammouth_ai import load_settings, generate_city
    from .db import get_db
    from .services.monument_service import get_monument

    settings = load_settings()
    api_key = settings.get("api_key", "")
    if not api_key:
        return jsonify({"success": False, "error": "Aucune clé API configurée."})

    model = request.form.get("model", settings.get("model", "gpt-4.1-mini")).strip()
    monument_slug = request.form.get("monument_slug", "").strip()
    prompt_text = request.form.get("prompt_text", "").strip()

    if not monument_slug:
        return jsonify({"success": False, "error": "Monument non spécifié."})
    if not prompt_text:
        return jsonify({"success": False, "error": "Le prompt est vide."})

    conn = get_db()
    monument = get_monument(conn, monument_slug)
    if monument is None:
        return jsonify({"success": False, "error": "Monument introuvable."})

    source_text = monument.get("source_text") or ""
    if not source_text:
        lines = [
            f'MONUMENT_NAME = "{monument["monument_name"]}"',
            f'CONSTRUCTION_DATE = "{monument.get("construction_date") or ""}"',
            f'INAUGURATION_DATE = "{monument.get("inauguration_date") or ""}"',
            f'CONSTRUCTION_YEAR = {monument.get("construction_year") or ""}',
            f'DEMOLITION_YEAR = {monument.get("demolition_year") or ""}',
            f'ARCHITECT = "{monument.get("architect") or ""}"',
            f'ARCHITECTURAL_STYLE = "{monument.get("architectural_style") or ""}"',
            f'HEIGHT_METERS = {monument.get("height_meters") or ""}',
            f'FLOORS = {monument.get("floors") or ""}',
            f'MONUMENT_LEVEL = {monument.get("monument_level") or 2}',
            f'MONUMENT_CATEGORY = "{monument.get("monument_category") or "autre"}"',
            "",
            "=== RÉSUMÉ ===",
            monument.get("summary") or "",
            "",
            "=== DESCRIPTION ===",
            monument.get("description") or "",
            "",
            "=== HISTOIRE ===",
            monument.get("history") or "",
            "",
            "=== SIGNIFICATION ===",
            monument.get("significance") or "",
            "",
            "=== LIEUX ===",
        ]
        for loc in monument.get("locations", []):
            if loc.get("city_name") or loc.get("matched_city_name"):
                city_name = loc.get("matched_city_name") or loc.get("city_name") or ""
                lines.append(f"{city_name}, {loc.get('region', '')}, {loc.get('country', '')}, {loc.get('role', 'primary')}")
            else:
                lines.append(f"{loc.get('region', '')}, {loc.get('country', '')}, {loc.get('role', 'primary')}")
        source_text = "\n".join(lines)

    result = generate_city(api_key, model, source_text, prompt_text, max_tokens=4000, temperature=0.3)
    if result.get("success"):
        result["tokens_total"] = load_settings().get("tokens_used", 0)
    return jsonify(result)


@web.route("/ai-lab/refine/monument/synthesize", methods=["POST"])
@editor_required
def ai_lab_refine_monument_synthesize() -> Response:
    """Ask AI to reconcile the original and refined monument versions."""
    from .services.mammouth_ai import load_settings, generate_city, load_prompt
    from .db import get_db
    from .services.monument_service import get_monument

    settings = load_settings()
    api_key = settings.get("api_key", "")
    if not api_key:
        return jsonify({"success": False, "error": "Aucune clé API configurée."})

    model = request.form.get("model", settings.get("model", "gpt-4.1-mini")).strip()
    monument_slug = request.form.get("monument_slug", "").strip()
    new_text = request.form.get("new_text", "").strip()

    if not monument_slug or not new_text:
        return jsonify({"success": False, "error": "Données manquantes pour la synthèse."})

    conn = get_db()
    monument = get_monument(conn, monument_slug)
    if monument is None:
        return jsonify({"success": False, "error": "Monument introuvable."})

    source_text = monument.get("source_text") or ""
    if not source_text:
        lines = [
            f'MONUMENT_NAME = "{monument["monument_name"]}"',
            f'CONSTRUCTION_DATE = "{monument.get("construction_date") or ""}"',
            f'INAUGURATION_DATE = "{monument.get("inauguration_date") or ""}"',
            f'CONSTRUCTION_YEAR = {monument.get("construction_year") or ""}',
            f'DEMOLITION_YEAR = {monument.get("demolition_year") or ""}',
            f'ARCHITECT = "{monument.get("architect") or ""}"',
            f'ARCHITECTURAL_STYLE = "{monument.get("architectural_style") or ""}"',
            f'HEIGHT_METERS = {monument.get("height_meters") or ""}',
            f'FLOORS = {monument.get("floors") or ""}',
            f'MONUMENT_LEVEL = {monument.get("monument_level") or 2}',
            f'MONUMENT_CATEGORY = "{monument.get("monument_category") or "autre"}"',
            "",
            "=== RÉSUMÉ ===",
            monument.get("summary") or "",
            "",
            "=== DESCRIPTION ===",
            monument.get("description") or "",
            "",
            "=== HISTOIRE ===",
            monument.get("history") or "",
            "",
            "=== SIGNIFICATION ===",
            monument.get("significance") or "",
            "",
            "=== LIEUX ===",
        ]
        for loc in monument.get("locations", []):
            if loc.get("city_name") or loc.get("matched_city_name"):
                city_name = loc.get("matched_city_name") or loc.get("city_name") or ""
                lines.append(f"{city_name}, {loc.get('region', '')}, {loc.get('country', '')}, {loc.get('role', 'primary')}")
            else:
                lines.append(f"{loc.get('region', '')}, {loc.get('country', '')}, {loc.get('role', 'primary')}")
        source_text = "\n".join(lines)

    prompt_text = load_prompt("monument_synthesize.txt").replace("{NEW_TEXT}", new_text)
    result = generate_city(api_key, model, source_text, prompt_text, max_tokens=4000, temperature=0.2)
    if result.get("success"):
        result["tokens_total"] = load_settings().get("tokens_used", 0)
    return jsonify(result)


@web.route("/ai-lab/refine/monument/save", methods=["POST"])
@editor_required
def ai_lab_refine_monument_save() -> Response:
    """Save the (refined or synthesized) monument text to the database."""
    from .db import get_db
    from .services.monument_service import parse_monument_text, import_monument

    text = request.form.get("monument_text", "").strip()
    if not text:
        return jsonify({"success": False, "error": "Texte vide."})

    try:
        data = parse_monument_text(text)
        data["source_text"] = text
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)})

    conn = get_db()
    monument_id = import_monument(conn, data)
    log_action("import", "monument", data["monument_slug"],
               f"Monument raffiné sauvegardé: {data['monument_name']}")
    return jsonify({
        "success": True,
        "monument_name": data["monument_name"],
        "monument_slug": data["monument_slug"],
        "monument_id": monument_id,
        "redirect": url_for("web.monument_detail", monument_slug=data["monument_slug"]),
    })


# ---------------------------------------------------------------------------
# Monuments (Buildings & Landmarks)
# ---------------------------------------------------------------------------

@web.route("/monuments")
def monuments_list() -> str:
    from .db import get_db
    from .services.monument_service import get_monuments_list, get_monument_primary_photo, MONUMENT_CATEGORIES, CATEGORY_LABELS, CATEGORY_EMOJIS

    conn = get_db()
    filters = {
        "category": request.args.get("category", ""),
        "level": request.args.get("level", ""),
        "search": request.args.get("search", ""),
    }
    view_mode = request.args.get("view", "small").strip().lower()
    if view_mode not in {"large", "medium", "small", "compact"}:
        view_mode = "small"
    monuments = get_monuments_list(conn, filters)
    for m in monuments:
        m["primary_photo"] = get_monument_primary_photo(conn, m["monument_slug"])
    return render_template(
        "web/monuments.html",
        page_title="Monuments et bâtiments",
        monuments=monuments,
        filters=filters,
        view_mode=view_mode,
        categories=MONUMENT_CATEGORIES,
        category_labels=CATEGORY_LABELS,
        category_emojis=CATEGORY_EMOJIS,
    )


@web.route("/monuments/<monument_slug>")
def monument_detail(monument_slug: str) -> str:
    from .db import get_db
    from .services.monument_service import get_monument, CATEGORY_LABELS, CATEGORY_EMOJIS
    from .services.city_photos import count_missing_photos

    conn = get_db()
    monument = get_monument(conn, monument_slug)
    if monument is None:
        flash("Monument introuvable.", "error")
        return redirect(url_for("web.monuments_list"))
    return render_template(
        "web/monument_detail.html",
        page_title=monument["monument_name"],
        monument=monument,
        category_labels=CATEGORY_LABELS,
        category_emojis=CATEGORY_EMOJIS,
        missing_photos_count=count_missing_photos(conn, "monument", monument_slug),
    )


@web.route("/monuments/import", methods=["POST"])
@editor_required
def monument_import() -> Response:
    from .db import get_db
    from .services.monument_service import parse_monument_text, import_monument

    text = request.form.get("monument_text", "").strip()
    if not text:
        return jsonify({"success": False, "error": "Texte vide."})
    try:
        data = parse_monument_text(text)
        data["source_text"] = text
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)})

    conn = get_db()
    try:
        monument_id = import_monument(conn, data)
    except Exception as exc:
        return jsonify({"success": False, "error": f"Erreur BD : {exc}"})
    log_action("import", "monument", data["monument_slug"], f"Monument importé: {data['monument_name']} ({data.get('construction_year', '')})")

    # Auto-geocode if no coordinates provided by the AI
    if data.get("latitude") is None or data.get("longitude") is None:
        from .services.city_coordinates import geocode_monument
        primary_loc = next((l for l in data.get("locations", []) if l.get("role") == "primary"), None)
        coords = geocode_monument(
            data["monument_name"],
            city_name=primary_loc["city_name"] if primary_loc else None,
            region=primary_loc.get("region") if primary_loc else None,
            country=primary_loc.get("country") if primary_loc else None,
        )
        if coords:
            conn.execute(
                "UPDATE dim_monument SET latitude = ?, longitude = ? WHERE monument_id = ?",
                (coords["lat"], coords["lng"], monument_id),
            )
            conn.commit()

    # Auto-search photo from Wikipedia
    _auto_import_monument_photo(conn, monument_id, data["monument_slug"], data["monument_name"])

    return jsonify({
        "success": True,
        "monument_name": data["monument_name"],
        "monument_slug": data["monument_slug"],
        "monument_id": monument_id,
        "redirect": url_for("web.monument_detail", monument_slug=data["monument_slug"]),
    })


def _auto_import_monument_photo(conn, monument_id: int, monument_slug: str, monument_name: str) -> None:
    """Try to auto-import a photo from Wikipedia/Commons."""
    try:
        from .services.city_photos import search_annotation_images, download_web_image
        from .services.monument_service import save_monument_photo

        images = search_annotation_images(monument_name, "", None, None)
        if images:
            img = images[0]
            result = download_web_image(img.get("url", ""))
            if result:
                file_bytes, ext = result
                save_monument_photo(
                    conn, monument_id, monument_slug,
                    file_bytes, f"auto-photo{ext}",
                    source_url=img.get("source_page", ""),
                    attribution=img.get("title", "Wikipedia/Wikimedia"),
                    caption=f"Photo de {monument_name}",
                    set_primary=True,
                    image_url=img.get("url", ""),
                )
    except Exception:
        pass  # Non-critical


@web.route("/monuments/geocode-missing", methods=["POST"])
@editor_required
def monuments_geocode_missing() -> Response:
    """Geocode all monuments that have no latitude/longitude."""
    import time
    from .db import get_db
    from .services.city_coordinates import geocode_monument

    conn = get_db()
    rows = conn.execute(
        """SELECT m.monument_id, m.monument_name,
                  ml.region, ml.country,
                  dc.city_name
           FROM dim_monument m
           LEFT JOIN dim_monument_location ml ON ml.monument_id = m.monument_id AND ml.role = 'primary'
           LEFT JOIN dim_city dc ON dc.city_id = ml.city_id
           WHERE m.latitude IS NULL OR m.longitude IS NULL"""
    ).fetchall()

    results = []
    for row in rows:
        coords = geocode_monument(
            row["monument_name"],
            city_name=row["city_name"],
            region=row["region"],
            country=row["country"],
        )
        if coords:
            conn.execute(
                "UPDATE dim_monument SET latitude = ?, longitude = ? WHERE monument_id = ?",
                (coords["lat"], coords["lng"], row["monument_id"]),
            )
            conn.commit()
            results.append({"monument": row["monument_name"], "lat": coords["lat"], "lng": coords["lng"], "ok": True})
        else:
            results.append({"monument": row["monument_name"], "ok": False})
        time.sleep(1)  # respect Nominatim rate limit

    geocoded = sum(1 for r in results if r["ok"])
    if geocoded:
        log_action("geocode", "monument", None, f"Géocodage: {geocoded}/{len(rows)} monuments géocodés")
    return jsonify({"total": len(rows), "geocoded": geocoded, "results": results})


@web.route("/monuments/<monument_slug>/coordinates", methods=["POST"])
@editor_required
def monument_save_coordinates(monument_slug: str) -> Response:
    """Save manually placed coordinates for a monument."""
    from .db import get_db

    data = request.get_json(silent=True) or {}
    lat = data.get("latitude")
    lng = data.get("longitude")
    if lat is None or lng is None:
        return jsonify({"success": False, "error": "latitude et longitude requis."})
    try:
        lat = round(float(lat), 4)
        lng = round(float(lng), 4)
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "Coordonnées invalides."})

    conn = get_db()
    row = conn.execute(
        "SELECT monument_id FROM dim_monument WHERE monument_slug = ?", (monument_slug,)
    ).fetchone()
    if not row:
        return jsonify({"success": False, "error": "Monument introuvable."})

    conn.execute(
        "UPDATE dim_monument SET latitude = ?, longitude = ? WHERE monument_slug = ?",
        (lat, lng, monument_slug),
    )
    conn.commit()
    log_action("geocode_manual", "monument", monument_slug,
               f"Coordonnées manuelles: {lat}, {lng}")
    return jsonify({"success": True, "latitude": lat, "longitude": lng})


@web.route("/monuments/<monument_slug>/delete", methods=["POST"])
@editor_required
def monument_delete(monument_slug: str) -> Response:
    from .db import get_db
    from .services.monument_service import get_monument, delete_monument

    conn = get_db()
    monument = get_monument(conn, monument_slug)
    if monument is None:
        flash("Monument introuvable.", "error")
        return redirect(url_for("web.monuments_list"))
    delete_monument(conn, monument["monument_id"])
    log_action("delete", "monument", monument_slug, f"Monument '{monument['monument_name']}' supprimé")
    flash(f"Monument « {monument['monument_name']} » supprimé.", "success")
    return redirect(url_for("web.monuments_list"))


@web.route("/monuments/<monument_slug>/photos/upload", methods=["POST"])
@editor_required
def monument_photo_upload(monument_slug: str) -> Response:
    from .db import get_db
    from .services.monument_service import get_monument, save_monument_photo

    conn = get_db()
    monument = get_monument(conn, monument_slug)
    if monument is None:
        return jsonify({"success": False, "error": "Monument introuvable."})

    file = request.files.get("photo")
    if not file or not file.filename:
        return jsonify({"success": False, "error": "Aucun fichier sélectionné."})

    result = save_monument_photo(
        conn,
        monument["monument_id"],
        monument_slug,
        file.read(),
        file.filename,
        source_url=request.form.get("source_url", ""),
        attribution=request.form.get("attribution", ""),
        caption=request.form.get("caption", ""),
        set_primary=request.form.get("set_primary") == "on",
    )
    if result.get("success"):
        log_action("upload_photo", "monument", monument_slug, f"Photo uploadée pour le monument {monument['monument_name']}")
    return jsonify(result)


@web.route("/monuments/<monument_slug>/photos/<int:photo_id>/delete", methods=["POST"])
@editor_required
def monument_photo_delete(monument_slug: str, photo_id: int) -> Response:
    from .db import get_db
    from .services.monument_service import delete_monument_photo

    conn = get_db()
    delete_monument_photo(conn, photo_id, monument_slug)
    log_action("delete_photo", "monument", monument_slug, f"Photo #{photo_id} supprimée du monument {monument_slug}")
    return jsonify({"success": True})


@web.route("/monuments/<monument_slug>/photos/<int:photo_id>/primary", methods=["POST"])
@editor_required
def monument_photo_primary(monument_slug: str, photo_id: int) -> Response:
    from .db import get_db
    from .services.monument_service import get_monument, set_monument_photo_primary

    conn = get_db()
    monument = get_monument(conn, monument_slug)
    if monument is None:
        return jsonify({"success": False, "error": "Monument introuvable."})
    set_monument_photo_primary(conn, photo_id, monument["monument_id"])
    log_action("update_photo", "monument", monument_slug, f"Photo #{photo_id} définie comme principale pour {monument['monument_name']}")
    return jsonify({"success": True})


@web.route("/monuments/<monument_slug>/photos/search")
def monument_photo_search(monument_slug: str) -> Response:
    """AJAX: smart search for monument photos (Wikipedia + Commons)."""
    from .db import get_db
    from .services.monument_service import get_monument
    from .services.city_photos import search_annotation_images

    conn = get_db()
    monument = get_monument(conn, monument_slug)
    if monument is None:
        return jsonify({"error": "Monument introuvable.", "images": []})

    monument_name = monument["monument_name"]
    construction_year = monument.get("construction_year")
    label = f"{monument_name} ({construction_year})" if construction_year else monument_name

    # Use first linked city for context
    city_name = ""
    for loc in monument.get("locations", []):
        if loc.get("matched_city_name"):
            city_name = loc["matched_city_name"]
            break
        if loc.get("city_name"):
            city_name = loc["city_name"]
            break

    country = None
    for loc in monument.get("locations", []):
        if loc.get("country"):
            country = loc["country"]
            break

    images = search_annotation_images(label, city_name, None, country)
    return jsonify({"images": images})


@web.route("/monuments/<monument_slug>/photos/manual-search")
def monument_photo_manual_search(monument_slug: str) -> Response:
    """AJAX: manual keyword search on Wikimedia Commons for monument photos."""
    from .services.city_photos import _search_commons_batch

    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"images": []})

    seen_urls: set[str] = set()
    images: list[dict] = []

    words = query.split()
    if len(words) <= 4:
        images = _search_commons_batch(query, seen_urls, limit=40)
    else:
        images.extend(_search_commons_batch(query, seen_urls, limit=20))
        sub = " ".join(words[:4])
        images.extend(_search_commons_batch(sub, seen_urls, limit=20))
        if len(images) < 20:
            sub = " ".join(words[:3])
            images.extend(_search_commons_batch(sub, seen_urls, limit=20))
        if len(images) < 15:
            sub = " ".join(words[-3:])
            images.extend(_search_commons_batch(sub, seen_urls, limit=20))

    return jsonify({"images": images[:40]})


@web.route("/monuments/<monument_slug>/photos/import-web", methods=["POST"])
@editor_required
def monument_photo_import_web(monument_slug: str) -> Response:
    """Import multiple web images into a monument's photo library."""
    from .db import get_db
    from .services.monument_service import get_monument, save_monument_photo
    from .services.city_photos import download_web_image

    conn = get_db()
    monument = get_monument(conn, monument_slug)
    if monument is None:
        return jsonify({"error": "Monument introuvable.", "imported": 0})

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
        save_result = save_monument_photo(
            conn,
            monument["monument_id"],
            monument_slug,
            file_bytes,
            f"web-import{ext}",
            source_url=img.get("source_page", ""),
            attribution=img.get("title", "Wikipedia/Wikimedia"),
            caption=img.get("caption", ""),
            set_primary=(imported == 0 and not monument.get("photos")),
            image_url=url,
        )
        if save_result.get("success"):
            imported += 1
    if imported:
        log_action("upload_photo", "monument", monument_slug, f"{imported} photo(s) importée(s) depuis le web pour {monument['monument_name']}")
    return jsonify({"imported": imported})


# ---------------------------------------------------------------------------
# Photo ZIP export / import  (generic for all entity types)
# ---------------------------------------------------------------------------

@web.route("/photos/export/<entity_type>/<entity_slug>")
@editor_required
def photo_export_zip(entity_type: str, entity_slug: str) -> Response:
    from .db import get_db
    from .services.photo_zip import export_photos_zip, ENTITY_CONFIG

    if entity_type not in ENTITY_CONFIG:
        flash("Type d'entité inconnu.", "error")
        return redirect(request.referrer or url_for("web.dashboard"))

    conn = get_db()
    buf = export_photos_zip(conn, entity_type, entity_slug)
    if buf is None:
        flash("Aucune photo à exporter.", "warning")
        return redirect(request.referrer or url_for("web.dashboard"))

    zip_filename = f"photos-{entity_type}-{entity_slug}.zip"
    return Response(
        buf.getvalue(),
        mimetype="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'},
    )


@web.route("/photos/import/<entity_type>/<entity_slug>", methods=["POST"])
@editor_required
def photo_import_zip(entity_type: str, entity_slug: str) -> Response:
    from .db import get_db
    from .services.photo_zip import import_photos_zip, ENTITY_CONFIG

    if entity_type not in ENTITY_CONFIG:
        return jsonify({"success": False, "error": "Type d'entité inconnu."})

    file = request.files.get("zip_file")
    if not file or not file.filename:
        return jsonify({"success": False, "error": "Aucun fichier ZIP sélectionné."})

    if not file.filename.lower().endswith(".zip"):
        return jsonify({"success": False, "error": "Le fichier doit être un .zip."})

    conn = get_db()
    result = import_photos_zip(conn, entity_type, entity_slug, file.read())
    if result.get("success"):
        log_action(
            "import_photos_zip",
            entity_type,
            entity_slug,
            f"{result['imported']} photo(s) importée(s) depuis ZIP",
        )
    return jsonify(result)


@web.route("/photos/refetch-missing/<entity_type>/<entity_slug>", methods=["POST"])
@editor_required
def photo_refetch_missing(entity_type: str, entity_slug: str) -> Response:
    """Re-download photos that exist in the DB (with image_url) but are missing from disk."""
    from .db import get_db
    from .services.photo_zip import ENTITY_CONFIG
    from .services.city_photos import download_web_image

    cfg = ENTITY_CONFIG.get(entity_type)
    if cfg is None:
        return jsonify({"success": False, "error": "Type d'entité inconnu."})

    conn = get_db()
    photo_tbl = cfg["photo_table"]
    fk_col = cfg["fk_col"]
    slug_col = cfg["slug_col"]
    entity_tbl = cfg["entity_table"]
    photo_dir = Path(current_app.root_path).parent / cfg["photo_dir"]

    rows = conn.execute(
        f"SELECT p.filename, p.image_url "
        f"FROM {photo_tbl} p "
        f"JOIN {entity_tbl} e ON e.{fk_col} = p.{fk_col} "
        f"WHERE e.{slug_col} = ? AND p.image_url IS NOT NULL AND p.image_url != ''",
        (entity_slug,),
    ).fetchall()

    missing = []
    for r in rows:
        file_path = photo_dir / entity_slug / r["filename"]
        if not file_path.is_file():
            missing.append({"filename": r["filename"], "image_url": r["image_url"]})

    if not missing:
        return jsonify({"success": True, "fetched": 0, "failed": 0, "message": "Aucune photo manquante."})

    fetched = 0
    failed = 0
    for item in missing:
        result = download_web_image(item["image_url"])
        if result is None:
            failed += 1
            continue
        data, _ext = result
        dest_dir = photo_dir / entity_slug
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / item["filename"]
        dest.write_bytes(data)
        fetched += 1

    return jsonify({
        "success": True,
        "fetched": fetched,
        "failed": failed,
        "total_missing": len(missing),
        "message": f"{fetched} photo(s) récupérée(s), {failed} échouée(s).",
    })


@web.route("/photos/refetch-all", methods=["POST"])
@editor_required
def photo_refetch_all() -> Response:
    """Re-download ALL missing photos across every entity type. Streams SSE progress."""
    import json as _json
    from .services.photo_zip import ENTITY_CONFIG
    from .services.city_photos import download_web_image

    db_url = current_app.config.get("DATABASE_URL", "")

    def generate():
        from .db import _connect_postgres
        conn = _connect_postgres(db_url)
        grand_fetched = 0
        grand_failed = 0

        try:
            for etype, cfg in ENTITY_CONFIG.items():
                photo_tbl = cfg["photo_table"]
                fk_col = cfg["fk_col"]
                slug_col = cfg["slug_col"]
                entity_tbl = cfg["entity_table"]
                photo_base = Path(__file__).resolve().parent.parent / cfg["photo_dir"]

                rows = conn.execute(
                    f"SELECT e.{slug_col} AS slug, p.filename, p.image_url "
                    f"FROM {photo_tbl} p "
                    f"JOIN {entity_tbl} e ON e.{fk_col} = p.{fk_col} "
                    f"WHERE p.image_url IS NOT NULL AND p.image_url != ''"
                ).fetchall()

                missing = []
                for r in rows:
                    fp = photo_base / r["slug"] / r["filename"]
                    if not fp.is_file():
                        missing.append({"slug": r["slug"], "filename": r["filename"], "image_url": r["image_url"]})

                if not missing:
                    yield f"data: {_json.dumps({'type': 'entity_skip', 'entity_type': etype, 'total_db': len(rows)})}\n\n"
                    continue

                yield f"data: {_json.dumps({'type': 'entity_start', 'entity_type': etype, 'missing': len(missing), 'total_db': len(rows)})}\n\n"

                for i, item in enumerate(missing, 1):
                    result = download_web_image(item["image_url"])
                    if result is None:
                        grand_failed += 1
                        status = "failed"
                    else:
                        img_data, _ext = result
                        dest_dir = photo_base / item["slug"]
                        dest_dir.mkdir(parents=True, exist_ok=True)
                        (dest_dir / item["filename"]).write_bytes(img_data)
                        grand_fetched += 1
                        status = "ok"

                    yield f"data: {_json.dumps({'type': 'photo_progress', 'entity_type': etype, 'current': i, 'total': len(missing), 'file': item['slug'] + '/' + item['filename'], 'status': status})}\n\n"

                yield f"data: {_json.dumps({'type': 'entity_done', 'entity_type': etype})}\n\n"

        except Exception as exc:
            yield f"data: {_json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        finally:
            conn.close()

        yield f"data: {_json.dumps({'type': 'summary', 'fetched': grand_fetched, 'failed': grand_failed, 'message': str(grand_fetched) + ' photo(s) récupérée(s), ' + str(grand_failed) + ' échouée(s).'})}\n\n"

    return Response(generate(), mimetype="text/event-stream")


# ---------------------------------------------------------------------------
# Admin panel
# ---------------------------------------------------------------------------

@web.route("/admin")
@admin_required
def admin_dashboard() -> str:
    from .services.auth import get_all_users
    from .services.audit import count_audit_logs, get_audit_logs
    users = get_all_users()
    recent_logs = get_audit_logs(limit=20)
    total_logs = count_audit_logs()
    return render_template(
        "web/admin_dashboard.html",
        page_title="Administration",
        users=users,
        recent_logs=recent_logs,
        total_logs=total_logs,
    )


@web.route("/admin/users")
@admin_required
def admin_users() -> str:
    from .services.auth import get_all_users
    users = get_all_users()
    return render_template("web/admin_users.html", page_title="Gestion des utilisateurs", users=users)


@web.route("/admin/users/create", methods=["POST"])
@admin_required
def admin_user_create() -> Response:
    from .services.auth import create_user
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "lecteur")
    display_name = request.form.get("display_name", "").strip() or username
    if not username or not email or not password:
        flash("Tous les champs sont obligatoires.", "error")
        return redirect(url_for("web.admin_users"))
    if role not in ("admin", "editeur", "collaborateur", "lecteur"):
        role = "lecteur"
    try:
        create_user(username=username, email=email, password=password,
                     role=role, display_name=display_name, is_approved=True)
        log_action("create", "user", None, f"Utilisateur {username} créé avec le rôle {role}")
        flash(f"Utilisateur {username} créé avec le rôle {role}.", "success")
    except Exception:
        flash("Erreur : nom d'utilisateur ou email déjà utilisé.", "error")
    return redirect(url_for("web.admin_users"))


@web.route("/admin/users/<int:user_id>/update", methods=["POST"])
@admin_required
def admin_user_update(user_id: int) -> Response:
    from .services.auth import update_user
    role = request.form.get("role")
    is_active = request.form.get("is_active")
    is_approved = request.form.get("is_approved")
    display_name = request.form.get("display_name")
    update_user(
        user_id,
        role=role if role in ("admin", "editeur", "collaborateur", "lecteur") else None,
        is_active=is_active == "1" if is_active is not None else None,
        is_approved=is_approved == "1" if is_approved is not None else None,
        display_name=display_name if display_name else None,
    )
    log_action("update", "user", str(user_id), f"Utilisateur #{user_id} mis à jour")
    flash("Utilisateur mis à jour.", "success")
    return redirect(url_for("web.admin_users"))


@web.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def admin_user_delete(user_id: int) -> Response:
    from .services.auth import delete_user, get_user_by_id
    user = get_user_by_id(user_id)
    if user and user["role"] == "admin":
        flash("Impossible de supprimer un administrateur.", "error")
        return redirect(url_for("web.admin_users"))
    delete_user(user_id)
    log_action("delete", "user", str(user_id), f"Utilisateur #{user_id} supprimé")
    flash("Utilisateur supprimé.", "success")
    return redirect(url_for("web.admin_users"))


@web.route("/admin/logs")
@admin_required
def admin_logs() -> str:
    from .services.audit import count_audit_logs, get_audit_logs
    from .services.auth import get_all_users
    page = max(1, request.args.get("page", 1, type=int))
    per_page = 50
    user_id = request.args.get("user_id", type=int)
    action = request.args.get("action", "").strip() or None
    entity_type = request.args.get("entity_type", "").strip() or None
    total = count_audit_logs(user_id=user_id, action=action, entity_type=entity_type)
    logs = get_audit_logs(limit=per_page, offset=(page - 1) * per_page,
                          user_id=user_id, action=action, entity_type=entity_type)
    users = get_all_users()
    total_pages = max(1, (total + per_page - 1) // per_page)
    return render_template(
        "web/admin_logs.html",
        page_title="Journal d'audit",
        logs=logs,
        users=users,
        total=total,
        page=page,
        total_pages=total_pages,
        filter_user_id=user_id,
        filter_action=action,
        filter_entity_type=entity_type,
    )


@web.route("/admin/logs/export")
@admin_required
def admin_logs_export() -> Response:
    import csv
    import io
    from .services.audit import get_audit_logs
    logs = get_audit_logs(limit=10000)
    si = io.StringIO()
    writer = csv.writer(si)
    writer.writerow(["date", "user", "action", "entity_type", "entity_id", "entity_label", "ip", "details"])
    for log in logs:
        writer.writerow([
            log.get("created_at", ""),
            log.get("username", ""),
            log.get("action", ""),
            log.get("entity_type", ""),
            log.get("entity_id", ""),
            log.get("entity_label", ""),
            log.get("ip_address", ""),
            log.get("details", ""),
        ])
    output = si.getvalue()
    return Response(output, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=audit_logs.csv"})
