BEGIN;

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS citext;

-- Migration-oriented PostgreSQL/PostGIS schema for ProjetCITY.
-- This file keeps close parity with the current SQLite model while adding:
-- - spatial columns for future PostGIS usage
-- - helper tables for filesystem-backed state

CREATE TABLE IF NOT EXISTS app_setting (
    setting_key TEXT PRIMARY KEY,
    setting_value JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS raw_document (
    document_id BIGSERIAL PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_slug TEXT NOT NULL,
    document_kind TEXT NOT NULL,
    content TEXT NOT NULL,
    source_origin TEXT NOT NULL DEFAULT 'filesystem',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (entity_type, entity_slug, document_kind)
);

CREATE TABLE IF NOT EXISTS sql_saved_view (
    view_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    sql_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sql_query_history (
    history_id BIGSERIAL PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    sql_text TEXT NOT NULL,
    preview TEXT,
    raw_payload JSONB
);

CREATE TABLE IF NOT EXISTS app_user (
    user_id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    role TEXT NOT NULL DEFAULT 'lecteur' CHECK (role IN ('admin', 'editeur', 'collaborateur', 'lecteur')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_approved BOOLEAN NOT NULL DEFAULT FALSE,
    oauth_provider TEXT,
    oauth_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_log (
    log_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES app_user(user_id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT,
    entity_label TEXT,
    details JSONB,
    ip_address TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dim_annotation (
    annotation_id BIGSERIAL PRIMARY KEY,
    annotation_label TEXT NOT NULL,
    annotation_color TEXT NOT NULL,
    annotation_type TEXT NOT NULL DEFAULT 'event',
    photo_filename TEXT,
    photo_source_url TEXT,
    UNIQUE (annotation_label, annotation_color)
);

CREATE TABLE IF NOT EXISTS ref_population (
    ref_pop_id BIGSERIAL PRIMARY KEY,
    country TEXT NOT NULL,
    region TEXT,
    year INTEGER NOT NULL,
    population BIGINT NOT NULL,
    UNIQUE (country, region, year)
);

CREATE TABLE IF NOT EXISTS ref_city (
    ref_city_id BIGSERIAL PRIMARY KEY,
    city_name TEXT NOT NULL,
    region TEXT NOT NULL,
    country TEXT NOT NULL,
    population BIGINT,
    rank INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (city_name, region, country)
);

CREATE TABLE IF NOT EXISTS dim_city (
    city_id BIGSERIAL PRIMARY KEY,
    city_name TEXT NOT NULL,
    city_slug TEXT NOT NULL UNIQUE,
    region TEXT,
    country TEXT NOT NULL,
    city_color TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    geom GEOGRAPHY(POINT, 4326),
    area_km2 DOUBLE PRECISION,
    density DOUBLE PRECISION,
    foundation_year INTEGER,
    source_file TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by_user_id BIGINT REFERENCES app_user(user_id) ON DELETE SET NULL,
    updated_by_user_id BIGINT REFERENCES app_user(user_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS dim_time (
    time_id BIGSERIAL PRIMARY KEY,
    year INTEGER NOT NULL UNIQUE,
    decade INTEGER NOT NULL,
    quarter_century_label TEXT NOT NULL,
    half_century_label TEXT NOT NULL,
    century INTEGER NOT NULL,
    period_label TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_city_period_detail (
    period_detail_id BIGSERIAL PRIMARY KEY,
    city_id BIGINT NOT NULL REFERENCES dim_city(city_id) ON DELETE CASCADE,
    period_order INTEGER NOT NULL,
    period_range_label TEXT NOT NULL,
    period_title TEXT NOT NULL,
    start_year INTEGER,
    end_year INTEGER,
    start_time_id BIGINT REFERENCES dim_time(time_id),
    end_time_id BIGINT REFERENCES dim_time(time_id),
    summary_text TEXT NOT NULL,
    source_file TEXT NOT NULL,
    UNIQUE (city_id, period_order, source_file)
);

CREATE TABLE IF NOT EXISTS dim_city_period_detail_item (
    period_detail_item_id BIGSERIAL PRIMARY KEY,
    period_detail_id BIGINT NOT NULL REFERENCES dim_city_period_detail(period_detail_id) ON DELETE CASCADE,
    item_order INTEGER NOT NULL,
    item_text TEXT NOT NULL,
    UNIQUE (period_detail_id, item_order)
);

CREATE TABLE IF NOT EXISTS fact_city_population (
    population_id BIGSERIAL PRIMARY KEY,
    city_id BIGINT NOT NULL REFERENCES dim_city(city_id) ON DELETE CASCADE,
    time_id BIGINT NOT NULL REFERENCES dim_time(time_id),
    year INTEGER NOT NULL,
    population BIGINT NOT NULL,
    is_key_year BOOLEAN NOT NULL DEFAULT FALSE,
    annotation_id BIGINT REFERENCES dim_annotation(annotation_id),
    source_file TEXT NOT NULL,
    UNIQUE (city_id, year)
);

CREATE TABLE IF NOT EXISTS dim_city_fiche (
    fiche_id BIGSERIAL PRIMARY KEY,
    city_id BIGINT NOT NULL UNIQUE REFERENCES dim_city(city_id) ON DELETE CASCADE,
    raw_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dim_city_fiche_section (
    section_id BIGSERIAL PRIMARY KEY,
    fiche_id BIGINT NOT NULL REFERENCES dim_city_fiche(fiche_id) ON DELETE CASCADE,
    section_order INTEGER NOT NULL,
    section_emoji TEXT,
    section_title TEXT NOT NULL,
    content_json TEXT NOT NULL,
    UNIQUE (fiche_id, section_order)
);

CREATE TABLE IF NOT EXISTS dim_city_photo (
    photo_id BIGSERIAL PRIMARY KEY,
    city_id BIGINT NOT NULL REFERENCES dim_city(city_id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    object_key TEXT,
    storage_provider TEXT,
    mime_type TEXT,
    file_size BIGINT,
    checksum_sha256 TEXT,
    caption TEXT,
    source_url TEXT,
    attribution TEXT,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    exif_lat DOUBLE PRECISION,
    exif_lon DOUBLE PRECISION,
    exif_date TEXT,
    exif_camera TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dim_event (
    event_id BIGSERIAL PRIMARY KEY,
    event_name TEXT NOT NULL,
    event_slug TEXT NOT NULL UNIQUE,
    event_date_start TEXT,
    event_date_end TEXT,
    event_year INTEGER,
    event_level INTEGER NOT NULL DEFAULT 1 CHECK (event_level IN (1, 2)),
    event_category TEXT NOT NULL DEFAULT 'autre',
    description TEXT,
    impact_population TEXT,
    impact_migration TEXT,
    source_text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by_user_id BIGINT REFERENCES app_user(user_id) ON DELETE SET NULL,
    updated_by_user_id BIGINT REFERENCES app_user(user_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS dim_event_location (
    event_location_id BIGSERIAL PRIMARY KEY,
    event_id BIGINT NOT NULL REFERENCES dim_event(event_id) ON DELETE CASCADE,
    city_id BIGINT REFERENCES dim_city(city_id) ON DELETE SET NULL,
    region TEXT,
    country TEXT,
    role TEXT NOT NULL DEFAULT 'primary'
);

CREATE TABLE IF NOT EXISTS dim_event_photo (
    event_photo_id BIGSERIAL PRIMARY KEY,
    event_id BIGINT NOT NULL REFERENCES dim_event(event_id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    object_key TEXT,
    storage_provider TEXT,
    mime_type TEXT,
    file_size BIGINT,
    checksum_sha256 TEXT,
    caption TEXT,
    source_url TEXT,
    attribution TEXT,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    photo_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dim_person (
    person_id BIGSERIAL PRIMARY KEY,
    person_name TEXT NOT NULL,
    person_slug TEXT NOT NULL UNIQUE,
    birth_date TEXT,
    death_date TEXT,
    birth_year INTEGER,
    death_year INTEGER,
    birth_city TEXT,
    birth_country TEXT,
    death_city TEXT,
    death_country TEXT,
    person_category TEXT NOT NULL DEFAULT 'autre',
    person_level INTEGER NOT NULL DEFAULT 2 CHECK (person_level IN (1, 2)),
    summary TEXT,
    biography TEXT,
    achievements TEXT,
    impact_population TEXT,
    source_text TEXT,
    annotation_id BIGINT REFERENCES dim_annotation(annotation_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by_user_id BIGINT REFERENCES app_user(user_id) ON DELETE SET NULL,
    updated_by_user_id BIGINT REFERENCES app_user(user_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS dim_person_location (
    person_location_id BIGSERIAL PRIMARY KEY,
    person_id BIGINT NOT NULL REFERENCES dim_person(person_id) ON DELETE CASCADE,
    city_id BIGINT REFERENCES dim_city(city_id) ON DELETE SET NULL,
    region TEXT,
    country TEXT,
    role TEXT NOT NULL DEFAULT 'residence'
);

CREATE TABLE IF NOT EXISTS dim_person_photo (
    person_photo_id BIGSERIAL PRIMARY KEY,
    person_id BIGINT NOT NULL REFERENCES dim_person(person_id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    object_key TEXT,
    storage_provider TEXT,
    mime_type TEXT,
    file_size BIGINT,
    checksum_sha256 TEXT,
    caption TEXT,
    source_url TEXT,
    attribution TEXT,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    photo_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dim_country (
    country_id BIGSERIAL PRIMARY KEY,
    country_name TEXT NOT NULL,
    country_slug TEXT NOT NULL UNIQUE,
    country_color TEXT,
    boundary_geom GEOMETRY(MULTIPOLYGON, 4326),
    source_file TEXT NOT NULL DEFAULT 'manual',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by_user_id BIGINT REFERENCES app_user(user_id) ON DELETE SET NULL,
    updated_by_user_id BIGINT REFERENCES app_user(user_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS fact_country_population (
    country_pop_id BIGSERIAL PRIMARY KEY,
    country_id BIGINT NOT NULL REFERENCES dim_country(country_id) ON DELETE CASCADE,
    time_id BIGINT NOT NULL REFERENCES dim_time(time_id),
    year INTEGER NOT NULL,
    population BIGINT NOT NULL,
    is_key_year BOOLEAN NOT NULL DEFAULT FALSE,
    annotation_id BIGINT REFERENCES dim_annotation(annotation_id),
    source_file TEXT NOT NULL DEFAULT 'manual',
    UNIQUE (country_id, year)
);

CREATE TABLE IF NOT EXISTS dim_country_photo (
    photo_id BIGSERIAL PRIMARY KEY,
    country_id BIGINT NOT NULL REFERENCES dim_country(country_id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    object_key TEXT,
    storage_provider TEXT,
    mime_type TEXT,
    file_size BIGINT,
    checksum_sha256 TEXT,
    caption TEXT,
    source_url TEXT,
    attribution TEXT,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dim_region (
    region_id BIGSERIAL PRIMARY KEY,
    region_name TEXT NOT NULL,
    region_slug TEXT NOT NULL UNIQUE,
    country_name TEXT NOT NULL,
    region_color TEXT,
    boundary_geom GEOMETRY(MULTIPOLYGON, 4326),
    source_file TEXT NOT NULL DEFAULT 'manual',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by_user_id BIGINT REFERENCES app_user(user_id) ON DELETE SET NULL,
    updated_by_user_id BIGINT REFERENCES app_user(user_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS fact_region_population (
    region_pop_id BIGSERIAL PRIMARY KEY,
    region_id BIGINT NOT NULL REFERENCES dim_region(region_id) ON DELETE CASCADE,
    time_id BIGINT NOT NULL REFERENCES dim_time(time_id),
    year INTEGER NOT NULL,
    population BIGINT NOT NULL,
    is_key_year BOOLEAN NOT NULL DEFAULT FALSE,
    annotation_id BIGINT REFERENCES dim_annotation(annotation_id),
    source_file TEXT NOT NULL DEFAULT 'manual',
    UNIQUE (region_id, year)
);

CREATE TABLE IF NOT EXISTS dim_region_period_detail (
    region_period_id BIGSERIAL PRIMARY KEY,
    region_id BIGINT NOT NULL REFERENCES dim_region(region_id) ON DELETE CASCADE,
    period_order INTEGER NOT NULL,
    period_range_label TEXT NOT NULL,
    period_title TEXT NOT NULL,
    start_year INTEGER,
    end_year INTEGER,
    start_time_id BIGINT REFERENCES dim_time(time_id),
    end_time_id BIGINT REFERENCES dim_time(time_id),
    summary_text TEXT NOT NULL,
    source_file TEXT NOT NULL,
    UNIQUE (region_id, period_order)
);

CREATE TABLE IF NOT EXISTS dim_region_period_detail_item (
    item_id BIGSERIAL PRIMARY KEY,
    region_period_id BIGINT NOT NULL REFERENCES dim_region_period_detail(region_period_id) ON DELETE CASCADE,
    item_order INTEGER NOT NULL,
    item_text TEXT NOT NULL,
    UNIQUE (region_period_id, item_order)
);

CREATE TABLE IF NOT EXISTS dim_region_photo (
    photo_id BIGSERIAL PRIMARY KEY,
    region_id BIGINT NOT NULL REFERENCES dim_region(region_id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    object_key TEXT,
    storage_provider TEXT,
    mime_type TEXT,
    file_size BIGINT,
    checksum_sha256 TEXT,
    caption TEXT,
    source_url TEXT,
    attribution TEXT,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_raw_document_lookup
    ON raw_document (entity_type, entity_slug, document_kind);
CREATE INDEX IF NOT EXISTS idx_sql_query_history_occurred_at
    ON sql_query_history (occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_city_slug ON dim_city (city_slug);
CREATE INDEX IF NOT EXISTS idx_city_country ON dim_city (country, region);
CREATE INDEX IF NOT EXISTS idx_city_name_trgm ON dim_city USING GIN (city_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_city_geom ON dim_city USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_period_detail_city ON dim_city_period_detail (city_id, period_order);
CREATE INDEX IF NOT EXISTS idx_period_detail_start_time ON dim_city_period_detail (start_time_id, end_time_id);
CREATE INDEX IF NOT EXISTS idx_period_item_detail ON dim_city_period_detail_item (period_detail_id, item_order);
CREATE INDEX IF NOT EXISTS idx_fact_city_year ON fact_city_population (city_id, year);
CREATE INDEX IF NOT EXISTS idx_fact_time ON fact_city_population (time_id);
CREATE INDEX IF NOT EXISTS idx_fact_annotation ON fact_city_population (annotation_id);
CREATE INDEX IF NOT EXISTS idx_fiche_city ON dim_city_fiche (city_id);
CREATE INDEX IF NOT EXISTS idx_fiche_section ON dim_city_fiche_section (fiche_id, section_order);
CREATE INDEX IF NOT EXISTS idx_photo_city ON dim_city_photo (city_id);
CREATE INDEX IF NOT EXISTS idx_event_slug ON dim_event (event_slug);
CREATE INDEX IF NOT EXISTS idx_event_year ON dim_event (event_year);
CREATE INDEX IF NOT EXISTS idx_event_category ON dim_event (event_category);
CREATE INDEX IF NOT EXISTS idx_event_level ON dim_event (event_level);
CREATE INDEX IF NOT EXISTS idx_event_location_event ON dim_event_location (event_id);
CREATE INDEX IF NOT EXISTS idx_event_location_city ON dim_event_location (city_id);
CREATE INDEX IF NOT EXISTS idx_event_photo_event ON dim_event_photo (event_id);
CREATE INDEX IF NOT EXISTS idx_country_slug ON dim_country (country_slug);
CREATE INDEX IF NOT EXISTS idx_country_pop_country ON fact_country_population (country_id);
CREATE INDEX IF NOT EXISTS idx_country_pop_year ON fact_country_population (year);
CREATE INDEX IF NOT EXISTS idx_country_boundary_geom ON dim_country USING GIST (boundary_geom);
CREATE INDEX IF NOT EXISTS idx_country_photo_country ON dim_country_photo (country_id);
CREATE INDEX IF NOT EXISTS idx_region_slug ON dim_region (region_slug);
CREATE INDEX IF NOT EXISTS idx_region_country ON dim_region (country_name);
CREATE INDEX IF NOT EXISTS idx_region_pop_region ON fact_region_population (region_id);
CREATE INDEX IF NOT EXISTS idx_region_pop_year ON fact_region_population (year);
CREATE INDEX IF NOT EXISTS idx_region_period ON dim_region_period_detail (region_id, period_order);
CREATE INDEX IF NOT EXISTS idx_region_period_item ON dim_region_period_detail_item (region_period_id, item_order);
CREATE INDEX IF NOT EXISTS idx_region_boundary_geom ON dim_region USING GIST (boundary_geom);
CREATE INDEX IF NOT EXISTS idx_region_photo_region ON dim_region_photo (region_id);
CREATE INDEX IF NOT EXISTS idx_ref_city_region_country ON ref_city (region, country, rank);
CREATE INDEX IF NOT EXISTS idx_user_email ON app_user (email);
CREATE INDEX IF NOT EXISTS idx_user_role ON app_user (role);
CREATE INDEX IF NOT EXISTS idx_audit_log_user ON audit_log (user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_entity ON audit_log (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON audit_log (created_at DESC);

-- Analytical views translated from SQLite to PostgreSQL.
-- GROUP_CONCAT becomes string_agg.

CREATE OR REPLACE VIEW vw_city_population_analysis AS
SELECT
    f.population_id,
    dc.city_id,
    dc.city_name,
    dc.city_slug,
    dc.region,
    dc.country,
    dc.city_color,
    dc.latitude,
    dc.longitude,
    dc.area_km2,
    dc.density,
    dt.time_id,
    dt.year,
    dt.decade,
    dt.quarter_century_label,
    dt.half_century_label,
    dt.century,
    dt.period_label,
    f.population,
    f.is_key_year,
    da.annotation_id,
    da.annotation_label,
    da.annotation_color,
    da.annotation_type,
    da.photo_filename AS annotation_photo_filename,
    da.photo_source_url AS annotation_photo_source_url,
    f.source_file
FROM fact_city_population f
INNER JOIN dim_city dc
    ON dc.city_id = f.city_id
INNER JOIN dim_time dt
    ON dt.time_id = f.time_id
LEFT JOIN dim_annotation da
    ON da.annotation_id = f.annotation_id;

CREATE OR REPLACE VIEW vw_city_period_detail_analysis AS
SELECT
    pd.period_detail_id,
    dc.city_id,
    dc.city_name,
    dc.city_slug,
    dc.region,
    dc.country,
    pd.period_order,
    pd.period_range_label,
    pd.period_title,
    pd.start_year,
    pd.end_year,
    ts.period_label AS start_period_label,
    te.period_label AS end_period_label,
    pd.summary_text,
    pd.source_file
FROM dim_city_period_detail pd
INNER JOIN dim_city dc
    ON dc.city_id = pd.city_id
LEFT JOIN dim_time ts
    ON ts.time_id = pd.start_time_id
LEFT JOIN dim_time te
    ON te.time_id = pd.end_time_id;

CREATE OR REPLACE VIEW vw_city_period_detail_with_population AS
WITH start_match AS (
    SELECT
        pd.period_detail_id,
        f.year,
        f.population,
        ROW_NUMBER() OVER (
            PARTITION BY pd.period_detail_id
            ORDER BY ABS(f.year - pd.start_year), f.year
        ) AS rn
    FROM dim_city_period_detail pd
    INNER JOIN fact_city_population f
        ON f.city_id = pd.city_id
    WHERE pd.start_year IS NOT NULL
),
end_match AS (
    SELECT
        pd.period_detail_id,
        f.year,
        f.population,
        ROW_NUMBER() OVER (
            PARTITION BY pd.period_detail_id
            ORDER BY ABS(f.year - pd.end_year), f.year DESC
        ) AS rn
    FROM dim_city_period_detail pd
    INNER JOIN fact_city_population f
        ON f.city_id = pd.city_id
    WHERE pd.end_year IS NOT NULL
)
SELECT
    pd.period_detail_id,
    dc.city_id,
    dc.city_name,
    dc.city_slug,
    dc.region,
    dc.country,
    pd.period_order,
    pd.period_range_label,
    pd.period_title,
    pd.start_year,
    pd.end_year,
    ts.period_label AS start_period_label,
    te.period_label AS end_period_label,
    sm.year AS start_population_year,
    em.year AS end_population_year,
    sm.population AS start_population,
    em.population AS end_population,
    CASE
        WHEN sm.population IS NOT NULL AND em.population IS NOT NULL
        THEN em.population - sm.population
        ELSE NULL
    END AS population_change,
    ROUND(
        CASE
            WHEN sm.population IS NULL OR em.population IS NULL OR sm.population = 0 THEN NULL
            ELSE ((em.population - sm.population) * 100.0) / sm.population
        END,
        2
    ) AS population_change_pct,
    pd.summary_text,
    pd.source_file
FROM dim_city_period_detail pd
INNER JOIN dim_city dc
    ON dc.city_id = pd.city_id
LEFT JOIN start_match sm
    ON sm.period_detail_id = pd.period_detail_id
   AND sm.rn = 1
LEFT JOIN end_match em
    ON em.period_detail_id = pd.period_detail_id
   AND em.rn = 1
LEFT JOIN dim_time ts
    ON ts.year = sm.year
LEFT JOIN dim_time te
    ON te.year = em.year;

CREATE OR REPLACE VIEW vw_city_period_detail_with_annotations AS
WITH base AS (
    SELECT
        v.*,
        CASE
            WHEN v.start_population_year IS NULL THEN v.end_population_year
            WHEN v.end_population_year IS NULL THEN v.start_population_year
            WHEN v.start_population_year <= v.end_population_year THEN v.start_population_year
            ELSE v.end_population_year
        END AS annotation_window_start,
        CASE
            WHEN v.start_population_year IS NULL THEN v.end_population_year
            WHEN v.end_population_year IS NULL THEN v.start_population_year
            WHEN v.start_population_year >= v.end_population_year THEN v.start_population_year
            ELSE v.end_population_year
        END AS annotation_window_end
    FROM vw_city_period_detail_with_population v
),
annotation_rollup AS (
    SELECT
        b.period_detail_id,
        COUNT(da.annotation_id) AS annotation_count,
        STRING_AGG(DISTINCT CAST(f.year AS TEXT), ',') AS annotation_years,
        STRING_AGG(DISTINCT da.annotation_label, ',') AS annotation_labels,
        STRING_AGG(DISTINCT da.annotation_color, ',') AS annotation_colors,
        STRING_AGG(DISTINCT da.annotation_type, ',') AS annotation_types
    FROM base b
    LEFT JOIN fact_city_population f
        ON f.city_id = b.city_id
       AND f.annotation_id IS NOT NULL
       AND b.annotation_window_start IS NOT NULL
       AND b.annotation_window_end IS NOT NULL
       AND f.year BETWEEN b.annotation_window_start AND b.annotation_window_end
    LEFT JOIN dim_annotation da
        ON da.annotation_id = f.annotation_id
    GROUP BY b.period_detail_id
)
SELECT
    b.period_detail_id,
    b.city_id,
    b.city_name,
    b.city_slug,
    b.region,
    b.country,
    b.period_order,
    b.period_range_label,
    b.period_title,
    b.start_year,
    b.end_year,
    b.start_period_label,
    b.end_period_label,
    b.start_population_year,
    b.end_population_year,
    b.start_population,
    b.end_population,
    b.population_change,
    b.population_change_pct,
    b.annotation_window_start,
    b.annotation_window_end,
    COALESCE(ar.annotation_count, 0) AS annotation_count,
    ar.annotation_years,
    ar.annotation_labels,
    ar.annotation_colors,
    ar.annotation_types,
    b.summary_text,
    b.source_file
FROM base b
LEFT JOIN annotation_rollup ar
    ON ar.period_detail_id = b.period_detail_id;

CREATE OR REPLACE VIEW vw_city_growth_by_decade AS
WITH ordered_pop AS (
    SELECT
        dc.city_id,
        dc.city_name,
        dc.country,
        dt.year,
        dt.decade,
        f.population,
        LAG(dt.year) OVER (PARTITION BY dc.city_id ORDER BY dt.year) AS prev_year,
        LAG(f.population) OVER (PARTITION BY dc.city_id ORDER BY dt.year) AS prev_population,
        LAG(dt.decade) OVER (PARTITION BY dc.city_id ORDER BY dt.year) AS prev_decade
    FROM fact_city_population f
    INNER JOIN dim_city dc
        ON dc.city_id = f.city_id
    INNER JOIN dim_time dt
        ON dt.time_id = f.time_id
)
SELECT
    city_id,
    city_name,
    country,
    decade,
    prev_year AS start_year,
    year AS end_year,
    prev_population AS start_population,
    population AS end_population,
    population - prev_population AS absolute_growth,
    ROUND(
        CASE
            WHEN prev_population IS NULL OR prev_population = 0 THEN NULL
            ELSE ((population - prev_population) * 100.0) / prev_population
        END,
        2
    ) AS growth_pct
FROM ordered_pop
WHERE prev_year IS NOT NULL;

CREATE OR REPLACE VIEW vw_city_peak_population AS
SELECT
    dc.city_id,
    dc.city_name,
    dc.region,
    dc.country,
    f.year AS peak_year,
    f.population AS peak_population,
    dt.period_label,
    da.annotation_label AS peak_annotation
FROM fact_city_population f
INNER JOIN dim_city dc
    ON dc.city_id = f.city_id
INNER JOIN dim_time dt
    ON dt.time_id = f.time_id
LEFT JOIN dim_annotation da
    ON da.annotation_id = f.annotation_id
WHERE f.population_id = (
    SELECT f2.population_id
    FROM fact_city_population f2
    WHERE f2.city_id = f.city_id
    ORDER BY f2.population DESC, f2.year DESC
    LIMIT 1
);

CREATE OR REPLACE VIEW vw_city_decline_periods AS
WITH yearly_changes AS (
    SELECT
        dc.city_id,
        dc.city_name,
        dc.country,
        dt.year,
        f.population,
        LAG(dt.year) OVER (PARTITION BY dc.city_id ORDER BY dt.year) AS previous_year,
        LAG(f.population) OVER (PARTITION BY dc.city_id ORDER BY dt.year) AS previous_population
    FROM fact_city_population f
    INNER JOIN dim_city dc
        ON dc.city_id = f.city_id
    INNER JOIN dim_time dt
        ON dt.time_id = f.time_id
)
SELECT
    city_id,
    city_name,
    country,
    previous_year,
    year AS current_year,
    previous_population,
    population AS current_population,
    population - previous_population AS absolute_change,
    ROUND(
        CASE
            WHEN previous_population = 0 THEN NULL
            ELSE ((population - previous_population) * 100.0) / previous_population
        END,
        2
    ) AS change_pct
FROM yearly_changes
WHERE previous_population IS NOT NULL
  AND population < previous_population;

CREATE OR REPLACE VIEW vw_city_rebound_periods AS
WITH yearly_changes AS (
    SELECT
        dc.city_id,
        dc.city_name,
        dc.country,
        dt.year,
        f.population,
        LAG(dt.year) OVER (PARTITION BY dc.city_id ORDER BY dt.year) AS previous_year,
        LAG(f.population) OVER (PARTITION BY dc.city_id ORDER BY dt.year) AS previous_population,
        LAG(f.population, 2) OVER (PARTITION BY dc.city_id ORDER BY dt.year) AS two_periods_back_population
    FROM fact_city_population f
    INNER JOIN dim_city dc
        ON dc.city_id = f.city_id
    INNER JOIN dim_time dt
        ON dt.time_id = f.time_id
)
SELECT
    city_id,
    city_name,
    country,
    previous_year,
    year AS current_year,
    previous_population,
    population AS current_population,
    population - previous_population AS absolute_change,
    ROUND(
        CASE
            WHEN previous_population = 0 THEN NULL
            ELSE ((population - previous_population) * 100.0) / previous_population
        END,
        2
    ) AS change_pct
FROM yearly_changes
WHERE previous_population IS NOT NULL
  AND population > previous_population
  AND (
      two_periods_back_population IS NULL
      OR previous_population <= two_periods_back_population
  );

CREATE OR REPLACE VIEW vw_annotated_events_by_period AS
SELECT
    dc.city_id,
    dc.city_name,
    dc.region,
    dc.country,
    dt.year,
    dt.decade,
    dt.period_label,
    f.population,
    da.annotation_id,
    da.annotation_label,
    da.annotation_color,
    da.annotation_type
FROM fact_city_population f
INNER JOIN dim_city dc
    ON dc.city_id = f.city_id
INNER JOIN dim_time dt
    ON dt.time_id = f.time_id
INNER JOIN dim_annotation da
    ON da.annotation_id = f.annotation_id;

CREATE OR REPLACE VIEW vw_fiche_coverage AS
SELECT
    dc.city_id,
    dc.city_name,
    dc.city_slug,
    dc.country,
    dc.region,
    f.created_at AS fiche_created,
    COUNT(s.section_id) AS section_count,
    STRING_AGG(s.section_title, ' | ' ORDER BY s.section_order) AS section_list,
    SUM(CASE WHEN s.section_title = 'Population' THEN 1 ELSE 0 END) AS has_population,
    SUM(CASE WHEN s.section_title = 'Économie' THEN 1 ELSE 0 END) AS has_economie,
    SUM(CASE WHEN s.section_title = 'Éducation' THEN 1 ELSE 0 END) AS has_education,
    SUM(CASE WHEN s.section_title = 'Transport' THEN 1 ELSE 0 END) AS has_transport,
    SUM(CASE WHEN s.section_title = 'Climat' THEN 1 ELSE 0 END) AS has_climat,
    SUM(CASE WHEN s.section_title = 'Santé' THEN 1 ELSE 0 END) AS has_sante,
    SUM(CASE WHEN s.section_title LIKE '%Sport%' THEN 1 ELSE 0 END) AS has_sports,
    SUM(CASE WHEN s.section_title LIKE '%Quartier%' THEN 1 ELSE 0 END) AS has_quartiers
FROM dim_city dc
INNER JOIN dim_city_fiche f ON f.city_id = dc.city_id
LEFT JOIN dim_city_fiche_section s ON s.fiche_id = f.fiche_id
GROUP BY dc.city_id, dc.city_name, dc.city_slug, dc.country, dc.region, f.created_at;

CREATE OR REPLACE VIEW vw_fiche_section_catalog AS
SELECT
    s.section_title,
    s.section_emoji,
    COUNT(DISTINCT f.city_id) AS city_count,
    ROUND(COUNT(DISTINCT f.city_id) * 100.0 / NULLIF((SELECT COUNT(*) FROM dim_city_fiche), 0), 1) AS coverage_pct,
    ROUND(AVG(LENGTH(s.content_json)), 0) AS avg_content_length,
    MIN(dc.city_name) AS example_city
FROM dim_city_fiche_section s
INNER JOIN dim_city_fiche f ON f.fiche_id = s.fiche_id
INNER JOIN dim_city dc ON dc.city_id = f.city_id
GROUP BY s.section_title, s.section_emoji
ORDER BY city_count DESC;

CREATE OR REPLACE VIEW vw_fiche_city_richness AS
SELECT
    dc.city_id,
    dc.city_name,
    dc.city_slug,
    dc.country,
    dc.region,
    COUNT(s.section_id) AS section_count,
    SUM(LENGTH(s.content_json)) AS total_content_length,
    ROUND(AVG(LENGTH(s.content_json)), 0) AS avg_section_length,
    MAX(LENGTH(s.content_json)) AS longest_section_length,
    f.created_at AS fiche_created
FROM dim_city dc
INNER JOIN dim_city_fiche f ON f.city_id = dc.city_id
LEFT JOIN dim_city_fiche_section s ON s.fiche_id = f.fiche_id
GROUP BY dc.city_id, dc.city_name, dc.city_slug, dc.country, dc.region, f.created_at
ORDER BY total_content_length DESC;

CREATE OR REPLACE VIEW vw_fiche_section_content_stats AS
SELECT
    s.section_title,
    COUNT(*) AS total_sections,
    ROUND(AVG(LENGTH(s.content_json)), 0) AS avg_length,
    MIN(LENGTH(s.content_json)) AS min_length,
    MAX(LENGTH(s.content_json)) AS max_length,
    SUM(CASE WHEN s.content_json LIKE '%"type": "table"%' THEN 1 ELSE 0 END) AS with_table,
    SUM(CASE WHEN s.content_json LIKE '%"type": "bullets"%' THEN 1 ELSE 0 END) AS with_bullets,
    SUM(CASE WHEN s.content_json LIKE '%"type": "text"%' THEN 1 ELSE 0 END) AS with_text,
    ROUND(SUM(CASE WHEN s.content_json LIKE '%"type": "table"%' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS table_pct,
    ROUND(SUM(CASE WHEN s.content_json LIKE '%"type": "bullets"%' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS bullets_pct
FROM dim_city_fiche_section s
GROUP BY s.section_title
ORDER BY total_sections DESC;

CREATE OR REPLACE VIEW vw_event_summary AS
SELECT
    e.event_id,
    e.event_name,
    e.event_slug,
    e.event_date_start,
    e.event_date_end,
    e.event_year,
    e.event_level,
    e.event_category,
    e.description,
    e.impact_population,
    e.impact_migration,
    e.created_at,
    COUNT(DISTINCT el.event_location_id) AS location_count,
    COUNT(DISTINCT ep.event_photo_id) AS photo_count,
    STRING_AGG(DISTINCT COALESCE(dc.city_name, el.region), ',') AS location_names
FROM dim_event e
LEFT JOIN dim_event_location el ON el.event_id = e.event_id
LEFT JOIN dim_city dc ON dc.city_id = el.city_id
LEFT JOIN dim_event_photo ep ON ep.event_id = e.event_id
GROUP BY
    e.event_id,
    e.event_name,
    e.event_slug,
    e.event_date_start,
    e.event_date_end,
    e.event_year,
    e.event_level,
    e.event_category,
    e.description,
    e.impact_population,
    e.impact_migration,
    e.created_at;

CREATE OR REPLACE VIEW vw_person_summary AS
SELECT
    p.person_id,
    p.person_name,
    p.person_slug,
    p.birth_date,
    p.death_date,
    p.birth_year,
    p.death_year,
    p.birth_city,
    p.birth_country,
    p.death_city,
    p.death_country,
    p.person_level,
    p.person_category,
    p.summary,
    p.created_at,
    COUNT(DISTINCT pl.person_location_id) AS location_count,
    COUNT(DISTINCT pp.person_photo_id) AS photo_count,
    STRING_AGG(DISTINCT COALESCE(dc.city_name, pl.region), ',') AS location_names
FROM dim_person p
LEFT JOIN dim_person_location pl ON pl.person_id = p.person_id
LEFT JOIN dim_city dc ON dc.city_id = pl.city_id
LEFT JOIN dim_person_photo pp ON pp.person_id = p.person_id
GROUP BY
    p.person_id,
    p.person_name,
    p.person_slug,
    p.birth_date,
    p.death_date,
    p.birth_year,
    p.death_year,
    p.birth_city,
    p.birth_country,
    p.death_city,
    p.death_country,
    p.person_level,
    p.person_category,
    p.summary,
    p.created_at;

-- ===== MONUMENTS =====

CREATE TABLE IF NOT EXISTS dim_monument (
    monument_id BIGSERIAL PRIMARY KEY,
    monument_name TEXT NOT NULL,
    monument_slug TEXT NOT NULL UNIQUE,
    construction_date TEXT,
    inauguration_date TEXT,
    construction_year INTEGER,
    demolition_year INTEGER,
    architect TEXT,
    architectural_style TEXT,
    height_meters NUMERIC,
    floors INTEGER,
    latitude NUMERIC,
    longitude NUMERIC,
    monument_category TEXT NOT NULL DEFAULT 'autre',
    monument_level INTEGER NOT NULL DEFAULT 2 CHECK (monument_level IN (1, 2)),
    summary TEXT,
    description TEXT,
    history TEXT,
    significance TEXT,
    source_text TEXT,
    annotation_id BIGINT REFERENCES dim_annotation(annotation_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by_user_id BIGINT REFERENCES app_user(user_id) ON DELETE SET NULL,
    updated_by_user_id BIGINT REFERENCES app_user(user_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS dim_monument_location (
    monument_location_id BIGSERIAL PRIMARY KEY,
    monument_id BIGINT NOT NULL REFERENCES dim_monument(monument_id) ON DELETE CASCADE,
    city_id BIGINT REFERENCES dim_city(city_id) ON DELETE SET NULL,
    region TEXT,
    country TEXT,
    role TEXT NOT NULL DEFAULT 'primary'
);

CREATE TABLE IF NOT EXISTS dim_monument_photo (
    monument_photo_id BIGSERIAL PRIMARY KEY,
    monument_id BIGINT NOT NULL REFERENCES dim_monument(monument_id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    object_key TEXT,
    storage_provider TEXT,
    mime_type TEXT,
    file_size BIGINT,
    checksum_sha256 TEXT,
    caption TEXT,
    source_url TEXT,
    attribution TEXT,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    photo_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE VIEW vw_monument_summary AS
SELECT
    m.monument_id,
    m.monument_name,
    m.monument_slug,
    m.construction_date,
    m.inauguration_date,
    m.construction_year,
    m.demolition_year,
    m.architect,
    m.architectural_style,
    m.height_meters,
    m.floors,
    m.monument_level,
    m.monument_category,
    m.summary,
    m.created_at,
    COUNT(DISTINCT ml.monument_location_id) AS location_count,
    COUNT(DISTINCT mp.monument_photo_id) AS photo_count,
    STRING_AGG(DISTINCT COALESCE(dc.city_name, ml.region), ',') AS location_names
FROM dim_monument m
LEFT JOIN dim_monument_location ml ON ml.monument_id = m.monument_id
LEFT JOIN dim_city dc ON dc.city_id = ml.city_id
LEFT JOIN dim_monument_photo mp ON mp.monument_id = m.monument_id
GROUP BY
    m.monument_id,
    m.monument_name,
    m.monument_slug,
    m.construction_date,
    m.inauguration_date,
    m.construction_year,
    m.demolition_year,
    m.architect,
    m.architectural_style,
    m.height_meters,
    m.floors,
    m.monument_level,
    m.monument_category,
    m.summary,
    m.created_at;

-- ===== LEGENDS =====

CREATE TABLE IF NOT EXISTS dim_legend (
    legend_id BIGSERIAL PRIMARY KEY,
    legend_name TEXT NOT NULL,
    legend_slug TEXT NOT NULL UNIQUE,
    legend_type TEXT NOT NULL DEFAULT 'legende' CHECK (legend_type IN ('legende', 'inexplique')),
    legend_category TEXT NOT NULL DEFAULT 'origine_inconnue',
    legend_level INTEGER NOT NULL DEFAULT 2 CHECK (legend_level IN (1, 2)),
    date_reported TEXT,
    year_reported INTEGER,
    country TEXT,
    region TEXT,
    city_name TEXT,
    latitude NUMERIC,
    longitude NUMERIC,
    summary TEXT,
    description TEXT,
    history TEXT,
    evidence TEXT,
    source_text TEXT,
    annotation_id BIGINT REFERENCES dim_annotation(annotation_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by_user_id BIGINT REFERENCES app_user(user_id) ON DELETE SET NULL,
    updated_by_user_id BIGINT REFERENCES app_user(user_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS dim_legend_location (
    legend_location_id BIGSERIAL PRIMARY KEY,
    legend_id BIGINT NOT NULL REFERENCES dim_legend(legend_id) ON DELETE CASCADE,
    city_id BIGINT REFERENCES dim_city(city_id) ON DELETE SET NULL,
    region TEXT,
    country TEXT,
    role TEXT NOT NULL DEFAULT 'primary'
);

CREATE TABLE IF NOT EXISTS dim_legend_photo (
    legend_photo_id BIGSERIAL PRIMARY KEY,
    legend_id BIGINT NOT NULL REFERENCES dim_legend(legend_id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    object_key TEXT,
    storage_provider TEXT,
    mime_type TEXT,
    file_size BIGINT,
    checksum_sha256 TEXT,
    caption TEXT,
    source_url TEXT,
    attribution TEXT,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    photo_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_legend_slug ON dim_legend (legend_slug);
CREATE INDEX IF NOT EXISTS idx_legend_type ON dim_legend (legend_type);
CREATE INDEX IF NOT EXISTS idx_legend_category ON dim_legend (legend_category);
CREATE INDEX IF NOT EXISTS idx_legend_level ON dim_legend (legend_level);
CREATE INDEX IF NOT EXISTS idx_legend_location_legend ON dim_legend_location (legend_id);
CREATE INDEX IF NOT EXISTS idx_legend_location_city ON dim_legend_location (city_id);
CREATE INDEX IF NOT EXISTS idx_legend_photo_legend ON dim_legend_photo (legend_id);

CREATE OR REPLACE VIEW vw_legend_summary AS
SELECT
    l.legend_id,
    l.legend_name,
    l.legend_slug,
    l.legend_type,
    l.legend_category,
    l.legend_level,
    l.date_reported,
    l.year_reported,
    l.country,
    l.region,
    l.city_name,
    l.summary,
    l.created_at,
    COUNT(DISTINCT ll.legend_location_id) AS location_count,
    COUNT(DISTINCT lp.legend_photo_id) AS photo_count,
    STRING_AGG(DISTINCT COALESCE(dc.city_name, ll.region), ',') AS location_names
FROM dim_legend l
LEFT JOIN dim_legend_location ll ON ll.legend_id = l.legend_id
LEFT JOIN dim_city dc ON dc.city_id = ll.city_id
LEFT JOIN dim_legend_photo lp ON lp.legend_id = l.legend_id
GROUP BY
    l.legend_id,
    l.legend_name,
    l.legend_slug,
    l.legend_type,
    l.legend_category,
    l.legend_level,
    l.date_reported,
    l.year_reported,
    l.country,
    l.region,
    l.city_name,
    l.summary,
    l.created_at;

COMMIT;
