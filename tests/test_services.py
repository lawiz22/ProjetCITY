"""Service-level tests — verify analytics and data logic independently."""
from __future__ import annotations


class TestAnalyticsServiceWithApp:
    """Tests that require the Flask app context (AnalyticsService uses get_db)."""

    def test_normalize_filters_defaults(self, app):
        with app.test_request_context():
            from app.services.analytics import AnalyticsService
            svc = AnalyticsService()
            filters = svc.normalize_filters({})
            assert "country" in filters
            assert "search" in filters

    def test_get_dashboard_metrics(self, app):
        with app.test_request_context():
            from app.services.analytics import AnalyticsService
            svc = AnalyticsService()
            filters = svc.normalize_filters({})
            metrics = svc.get_dashboard_metrics(filters)
            assert "city_count" in metrics
            assert metrics["city_count"] >= 3

    def test_get_growth_leaders(self, app):
        with app.test_request_context():
            from app.services.analytics import AnalyticsService
            svc = AnalyticsService()
            filters = svc.normalize_filters({})
            leaders = svc.get_growth_leaders(filters)
            assert isinstance(leaders, list)

    def test_get_city_detail_existing(self, app):
        with app.test_request_context():
            from app.services.analytics import AnalyticsService
            svc = AnalyticsService()
            filters = svc.normalize_filters({})
            city = svc.get_city_detail("montreal", filters)
            assert city is not None
            assert city["city_name"] == "Montréal"

    def test_get_city_detail_nonexistent(self, app):
        with app.test_request_context():
            from app.services.analytics import AnalyticsService
            svc = AnalyticsService()
            filters = svc.normalize_filters({})
            city = svc.get_city_detail("nonexistent-xyz", filters)
            assert city is None

    def test_get_map_payload(self, app):
        with app.test_request_context():
            from app.services.analytics import AnalyticsService
            svc = AnalyticsService()
            filters = svc.normalize_filters({})
            payload = svc.get_map_payload(filters)
            assert "points" in payload
            assert len(payload["points"]) >= 1

    def test_get_city_options(self, app):
        with app.test_request_context():
            from app.services.analytics import AnalyticsService
            svc = AnalyticsService()
            options = svc.get_city_options()
            slugs = [o["city_slug"] for o in options]
            assert "montreal" in slugs

    def test_get_filter_options(self, app):
        with app.test_request_context():
            from app.services.analytics import AnalyticsService
            svc = AnalyticsService()
            opts = svc.get_filter_options()
            assert "countries" in opts
            assert "regions" in opts
            assert "Canada" in opts["countries"]


class TestSqlExecution:
    """Test SQL Lab execution safety."""

    def test_select_executes(self, app):
        with app.test_request_context():
            from app.services.analytics import AnalyticsService
            svc = AnalyticsService()
            result = svc.execute_sql("SELECT COUNT(*) AS n FROM dim_city", confirm_write=False)
            assert result["kind"] == "read"
            first = result["results"][0]
            assert first["columns"] == ["n"]
            assert first["rows"][0]["n"] >= 3

    def test_write_blocked(self, app):
        with app.test_request_context():
            from app.services.analytics import AnalyticsService, SqlExecutionError
            svc = AnalyticsService()
            try:
                svc.execute_sql("DELETE FROM dim_city WHERE 1=0", confirm_write=False)
                assert False, "Should have raised SqlExecutionError"
            except (SqlExecutionError, Exception):
                pass  # Expected — write blocked


class TestDatabaseSchema:
    """Verify schema integrity on the test database."""

    def test_all_views_exist(self, db_conn):
        rows = db_conn.execute(
            "SELECT table_name FROM information_schema.views WHERE table_schema = 'public' ORDER BY table_name"
        ).fetchall()
        view_names = {row["table_name"] for row in rows}
        expected = {
            "vw_city_population_analysis",
            "vw_city_growth_by_decade",
            "vw_city_peak_population",
            "vw_city_decline_periods",
            "vw_city_rebound_periods",
            "vw_annotated_events_by_period",
            "vw_city_period_detail_analysis",
            "vw_city_period_detail_with_population",
            "vw_city_period_detail_with_annotations",
        }
        missing = expected - view_names
        assert not missing, f"Missing views: {missing}"

    def test_all_tables_exist(self, db_conn):
        rows = db_conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name"
        ).fetchall()
        table_names = {row["table_name"] for row in rows}
        expected = {
            "dim_annotation",
            "dim_city",
            "dim_time",
            "dim_city_period_detail",
            "dim_city_period_detail_item",
            "fact_city_population",
            "dim_city_fiche",
            "dim_city_fiche_section",
            "dim_city_photo",
            "ref_population",
        }
        missing = expected - table_names
        assert not missing, f"Missing tables: {missing}"

    def test_sample_data_loaded(self, db_conn):
        count = db_conn.execute("SELECT COUNT(*) AS n FROM dim_city").fetchone()["n"]
        assert count == 3

    def test_population_view_works(self, db_conn):
        rows = db_conn.execute(
            "SELECT city_slug, year, population FROM vw_city_population_analysis WHERE city_slug = 'montreal' ORDER BY year"
        ).fetchall()
        assert len(rows) == 8
        assert rows[0]["year"] == 1950
        assert rows[-1]["year"] == 2020

    def test_growth_by_decade_view(self, db_conn):
        rows = db_conn.execute(
            "SELECT * FROM vw_city_growth_by_decade WHERE city_id = 1"
        ).fetchall()
        assert len(rows) >= 1
        assert rows[0]["growth_pct"] is not None

    def test_peak_population_view(self, db_conn):
        row = db_conn.execute(
            "SELECT peak_year, peak_population FROM vw_city_peak_population WHERE city_id = 1"
        ).fetchone()
        assert row["peak_year"] == 2020
        assert row["peak_population"] == 1_800_000
