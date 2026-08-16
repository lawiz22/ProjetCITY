"""Route-level tests — verify that main pages respond correctly."""
from __future__ import annotations


class TestDashboard:
    def test_dashboard_loads(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Dashboard" in resp.data or b"dashboard" in resp.data.lower()

    def test_dashboard_with_country_filter(self, client):
        resp = client.get("/?country=Canada")
        assert resp.status_code == 200

    def test_dashboard_preserves_explicit_empty_region_selection(self, client):
        response = client.get("/?regions_applied=1")

        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "Régions (0)" in html
        assert 'class="dash-reset"' in html
        assert "data-chart-lazy='{\"datasets\": [], \"labels\": []}'" in html

    def test_saved_country_selection_filters_dashboard(self, client, db_conn):
        from werkzeug.security import generate_password_hash

        try:
            user_id = db_conn.execute(
                """
                INSERT INTO app_user (username, email, password_hash, role, is_approved)
                VALUES (%s, %s, %s, 'collaborateur', TRUE)
                RETURNING user_id
                """,
                ("dashboard-options", "dashboard-options@example.com", generate_password_hash("test")),
            ).fetchone()["user_id"]
            db_conn.execute(
                """
                INSERT INTO dim_country (country_name, country_slug)
                VALUES ('Canada', 'canada'), ('United States', 'united-states')
                ON CONFLICT (country_slug) DO NOTHING
                """
            )
            db_conn.commit()

            with client.session_transaction() as session:
                session["user_id"] = user_id

            response = client.post("/options/save", data={
                "api_key": "",
                "model": "gpt-4.1-mini",
                "dashboard_country": "Canada",
            })
            assert response.status_code == 302

            response = client.get("/")
            assert response.status_code == 200
            assert b"Montr" in response.data
            assert b"Boston" not in response.data
            assert b"Canada" in response.data
            assert b"United States" not in response.data
        finally:
            db_conn.execute("DELETE FROM app_setting WHERE setting_key IN ('dashboard_settings', 'mammouth_settings')")
            db_conn.execute("DELETE FROM dim_country WHERE country_slug IN ('canada', 'united-states')")
            db_conn.execute("DELETE FROM app_user WHERE username = 'dashboard-options'")
            db_conn.commit()

    def test_country_count_includes_selected_country_without_cities(self, client, db_conn):
        try:
            france_id = db_conn.execute(
                """
                INSERT INTO dim_country (country_name, country_slug)
                VALUES ('France', 'france')
                ON CONFLICT (country_slug) DO UPDATE SET country_name = EXCLUDED.country_name
                RETURNING country_id
                """
            ).fetchone()["country_id"]
            db_conn.execute(
                """
                INSERT INTO fact_country_population (country_id, time_id, year, population)
                VALUES (%s, 8, 2020, 68000000)
                ON CONFLICT (country_id, year) DO UPDATE SET population = EXCLUDED.population
                """,
                (france_id,),
            )
            db_conn.execute(
                """
                INSERT INTO dim_region (region_name, region_slug, country_name)
                VALUES ('Bretagne', 'bretagne', 'France')
                ON CONFLICT (region_slug) DO UPDATE SET country_name = EXCLUDED.country_name
                """
            )
            db_conn.execute(
                """
                INSERT INTO app_setting (setting_key, setting_value)
                VALUES ('dashboard_settings', '{"countries":["Canada","United States","France"]}'::jsonb)
                ON CONFLICT (setting_key) DO UPDATE SET setting_value = EXCLUDED.setting_value
                """
            )
            db_conn.commit()

            response = client.get("/")
            assert response.status_code == 200
            html = response.get_data(as_text=True)
            country_card = html.split('class="metric-card"', 2)[1]
            assert "France" in country_card
            assert ">3<" in country_card or "\n            3\n" in country_card
            assert '"label": "France"' in html
            assert '<option value="France"' in html
            assert '>France</option>' in html
            assert 'value="Bretagne"' in html
            assert "Régions du dashboard" in html
        finally:
            db_conn.execute("DELETE FROM app_setting WHERE setting_key = 'dashboard_settings'")
            db_conn.execute("DELETE FROM dim_region WHERE region_slug = 'bretagne'")
            db_conn.execute("DELETE FROM dim_country WHERE country_slug = 'france'")
            db_conn.commit()


class TestCityDirectory:
    def test_directory_loads(self, client):
        resp = client.get("/cities")
        assert resp.status_code == 200

    def test_directory_view_modes(self, client):
        for mode in ("large", "medium", "small", "compact"):
            resp = client.get(f"/cities?view={mode}")
            assert resp.status_code == 200

    def test_directory_invalid_view_falls_back(self, client):
        resp = client.get("/cities?view=INVALID")
        assert resp.status_code == 200


class TestCityDetail:
    def test_existing_city(self, client):
        resp = client.get("/cities/montreal")
        assert resp.status_code == 200
        assert "Montréal".encode() in resp.data or b"montreal" in resp.data.lower()

    def test_unknown_city_redirects(self, client):
        resp = client.get("/cities/nonexistent-city-xyz")
        assert resp.status_code in (302, 303)

    def test_city_detail_has_chart_data(self, client):
        resp = client.get("/cities/montreal")
        assert resp.status_code == 200
        # Chart payload is rendered as JSON in the template
        assert b"population" in resp.data.lower()


class TestCompare:
    def test_compare_no_selection(self, client):
        resp = client.get("/compare")
        assert resp.status_code == 200

    def test_compare_with_cities(self, client):
        resp = client.get("/compare?city=montreal&city=calgary")
        assert resp.status_code == 200


class TestMap:
    def test_map_page(self, client):
        resp = client.get("/map")
        assert resp.status_code == 200

    def test_map_data_json(self, client):
        resp = client.get("/map/data")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1  # at least one city with coordinates

    def test_map_time_travel(self, client):
        resp = client.get("/map/time-travel")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "years" in data
        assert "cities" in data


class TestSqlLab:
    def test_sql_lab_loads(self, client):
        resp = client.get("/sql-lab")
        assert resp.status_code == 200

    def test_sql_select_query(self, client):
        resp = client.post("/sql-lab", data={
            "query": "SELECT city_name FROM dim_city LIMIT 3",
        })
        # POST may redirect (303) or render inline (200)
        assert resp.status_code in (200, 302, 303)

    def test_sql_write_blocked_by_default(self, client):
        resp = client.post("/sql-lab", data={
            "query": "DELETE FROM dim_city WHERE city_slug = 'test'",
        })
        assert resp.status_code == 200
        # Should show an error / not execute the delete
        assert b"error" in resp.data.lower() or b"interdit" in resp.data.lower() or b"read" in resp.data.lower()


class TestDashboardPdf:
    def test_pdf_export(self, client, db_conn):
        from werkzeug.security import generate_password_hash

        try:
            user_id = db_conn.execute(
                """
                INSERT INTO app_user (username, email, password_hash, role, is_approved)
                VALUES ('dashboard-pdf', 'dashboard-pdf@example.com', %s, 'collaborateur', TRUE)
                RETURNING user_id
                """,
                (generate_password_hash("test"),),
            ).fetchone()["user_id"]
            db_conn.commit()
            with client.session_transaction() as session:
                session["user_id"] = user_id

            resp = client.get("/export/dashboard.pdf")
            assert resp.status_code == 200
            assert resp.content_type == "application/pdf"
            assert resp.data[:4] == b"%PDF"
        finally:
            db_conn.execute("DELETE FROM app_user WHERE username = 'dashboard-pdf'")
            db_conn.commit()


class TestCityPdf:
    def test_city_pdf_export(self, client):
        resp = client.get("/cities/montreal/export/pdf")
        assert resp.status_code == 200
        assert resp.content_type == "application/pdf"

    def test_city_pdf_unknown_redirects(self, client):
        resp = client.get("/cities/nonexistent/export/pdf")
        assert resp.status_code in (302, 303)
