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
    def test_pdf_export(self, client):
        resp = client.get("/export/dashboard.pdf")
        assert resp.status_code == 200
        assert resp.content_type == "application/pdf"
        assert resp.data[:4] == b"%PDF"


class TestCityPdf:
    def test_city_pdf_export(self, client):
        resp = client.get("/cities/montreal/export/pdf")
        assert resp.status_code == 200
        assert resp.content_type == "application/pdf"

    def test_city_pdf_unknown_redirects(self, client):
        resp = client.get("/cities/nonexistent/export/pdf")
        assert resp.status_code in (302, 303)
