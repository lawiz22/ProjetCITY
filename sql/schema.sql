PRAGMA foreign_keys = ON;

DROP VIEW IF EXISTS vw_fiche_section_content_stats;
DROP VIEW IF EXISTS vw_fiche_city_richness;
DROP VIEW IF EXISTS vw_fiche_section_catalog;
DROP VIEW IF EXISTS vw_fiche_coverage;
DROP VIEW IF EXISTS vw_annotated_events_by_period;
DROP VIEW IF EXISTS vw_city_rebound_periods;
DROP VIEW IF EXISTS vw_city_decline_periods;
DROP VIEW IF EXISTS vw_city_peak_population;
DROP VIEW IF EXISTS vw_city_growth_by_decade;
DROP VIEW IF EXISTS vw_city_period_detail_with_annotations;
DROP VIEW IF EXISTS vw_city_period_detail_with_population;
DROP VIEW IF EXISTS vw_city_period_detail_analysis;
DROP VIEW IF EXISTS vw_city_population_analysis;

DROP TABLE IF EXISTS dim_city_photo;
DROP TABLE IF EXISTS fact_city_population;
DROP TABLE IF EXISTS ref_population;
DROP TABLE IF EXISTS dim_city_fiche_section;
DROP TABLE IF EXISTS dim_city_fiche;
DROP TABLE IF EXISTS dim_city_period_detail_item;
DROP TABLE IF EXISTS dim_city_period_detail;
DROP TABLE IF EXISTS dim_time;
DROP TABLE IF EXISTS dim_city;
DROP TABLE IF EXISTS dim_annotation;

CREATE TABLE dim_annotation (
    annotation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    annotation_label TEXT NOT NULL,
    annotation_color TEXT NOT NULL,
    annotation_type TEXT NOT NULL DEFAULT 'event',
    photo_filename TEXT,
    photo_source_url TEXT,
    UNIQUE(annotation_label, annotation_color)
);

CREATE TABLE ref_population (
    ref_pop_id INTEGER PRIMARY KEY AUTOINCREMENT,
    country TEXT NOT NULL,
    region TEXT,
    year INTEGER NOT NULL,
    population INTEGER NOT NULL,
    UNIQUE(country, region, year)
);

CREATE TABLE dim_city (
    city_id INTEGER PRIMARY KEY AUTOINCREMENT,
    city_name TEXT NOT NULL,
    city_slug TEXT NOT NULL UNIQUE,
    region TEXT,
    country TEXT NOT NULL,
    city_color TEXT,
    latitude REAL,
    longitude REAL,
    area_km2 REAL,
    density REAL,
    foundation_year INTEGER,
    source_file TEXT NOT NULL
);

CREATE TABLE dim_time (
    time_id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL UNIQUE,
    decade INTEGER NOT NULL,
    quarter_century_label TEXT NOT NULL,
    half_century_label TEXT NOT NULL,
    century INTEGER NOT NULL,
    period_label TEXT NOT NULL
);

CREATE TABLE dim_city_period_detail (
    period_detail_id INTEGER PRIMARY KEY AUTOINCREMENT,
    city_id INTEGER NOT NULL,
    period_order INTEGER NOT NULL,
    period_range_label TEXT NOT NULL,
    period_title TEXT NOT NULL,
    start_year INTEGER,
    end_year INTEGER,
    start_time_id INTEGER,
    end_time_id INTEGER,
    summary_text TEXT NOT NULL,
    source_file TEXT NOT NULL,
    UNIQUE(city_id, period_order, source_file),
    FOREIGN KEY (city_id) REFERENCES dim_city(city_id),
    FOREIGN KEY (start_time_id) REFERENCES dim_time(time_id),
    FOREIGN KEY (end_time_id) REFERENCES dim_time(time_id)
);

CREATE TABLE dim_city_period_detail_item (
    period_detail_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    period_detail_id INTEGER NOT NULL,
    item_order INTEGER NOT NULL,
    item_text TEXT NOT NULL,
    UNIQUE(period_detail_id, item_order),
    FOREIGN KEY (period_detail_id) REFERENCES dim_city_period_detail(period_detail_id)
);

CREATE TABLE fact_city_population (
    population_id INTEGER PRIMARY KEY AUTOINCREMENT,
    city_id INTEGER NOT NULL,
    time_id INTEGER NOT NULL,
    year INTEGER NOT NULL,
    population INTEGER NOT NULL,
    is_key_year INTEGER NOT NULL DEFAULT 0 CHECK (is_key_year IN (0, 1)),
    annotation_id INTEGER,
    source_file TEXT NOT NULL,
    UNIQUE(city_id, year),
    FOREIGN KEY (city_id) REFERENCES dim_city(city_id),
    FOREIGN KEY (time_id) REFERENCES dim_time(time_id),
    FOREIGN KEY (annotation_id) REFERENCES dim_annotation(annotation_id)
);

CREATE TABLE dim_city_fiche (
    fiche_id INTEGER PRIMARY KEY AUTOINCREMENT,
    city_id INTEGER NOT NULL UNIQUE,
    raw_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (city_id) REFERENCES dim_city(city_id)
);

CREATE TABLE dim_city_fiche_section (
    section_id INTEGER PRIMARY KEY AUTOINCREMENT,
    fiche_id INTEGER NOT NULL,
    section_order INTEGER NOT NULL,
    section_emoji TEXT,
    section_title TEXT NOT NULL,
    content_json TEXT NOT NULL,
    UNIQUE(fiche_id, section_order),
    FOREIGN KEY (fiche_id) REFERENCES dim_city_fiche(fiche_id)
);

CREATE TABLE dim_city_photo (
    photo_id INTEGER PRIMARY KEY AUTOINCREMENT,
    city_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    caption TEXT,
    source_url TEXT,
    attribution TEXT,
    is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    exif_lat REAL,
    exif_lon REAL,
    exif_date TEXT,
    exif_camera TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (city_id) REFERENCES dim_city(city_id)
);

CREATE INDEX idx_city_slug ON dim_city (city_slug);
CREATE INDEX idx_city_country ON dim_city (country, region);
CREATE INDEX idx_period_detail_city ON dim_city_period_detail (city_id, period_order);
CREATE INDEX idx_period_detail_start_time ON dim_city_period_detail (start_time_id, end_time_id);
CREATE INDEX idx_period_item_detail ON dim_city_period_detail_item (period_detail_id, item_order);
CREATE INDEX idx_fact_city_year ON fact_city_population (city_id, year);
CREATE INDEX idx_fact_time ON fact_city_population (time_id);
CREATE INDEX idx_fact_annotation ON fact_city_population (annotation_id);
CREATE INDEX idx_fiche_city ON dim_city_fiche (city_id);
CREATE INDEX idx_fiche_section ON dim_city_fiche_section (fiche_id, section_order);
CREATE INDEX idx_photo_city ON dim_city_photo (city_id);

CREATE VIEW vw_city_population_analysis AS
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

CREATE VIEW vw_city_period_detail_analysis AS
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

CREATE VIEW vw_city_period_detail_with_population AS
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

CREATE VIEW vw_city_period_detail_with_annotations AS
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
        GROUP_CONCAT(DISTINCT CAST(f.year AS TEXT)) AS annotation_years,
        GROUP_CONCAT(DISTINCT da.annotation_label) AS annotation_labels,
        GROUP_CONCAT(DISTINCT da.annotation_color) AS annotation_colors,
        GROUP_CONCAT(DISTINCT da.annotation_type) AS annotation_types
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

CREATE VIEW vw_city_growth_by_decade AS
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

CREATE VIEW vw_city_peak_population AS
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

CREATE VIEW vw_city_decline_periods AS
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

CREATE VIEW vw_city_rebound_periods AS
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

CREATE VIEW vw_annotated_events_by_period AS
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

-- ── Fiche views ─────────────────────────────────────────────

CREATE VIEW vw_fiche_coverage AS
SELECT
    dc.city_id,
    dc.city_name,
    dc.city_slug,
    dc.country,
    dc.region,
    f.created_at AS fiche_created,
    COUNT(s.section_id) AS section_count,
    GROUP_CONCAT(s.section_title, ' | ') AS section_list,
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
GROUP BY dc.city_id;

CREATE VIEW vw_fiche_section_catalog AS
SELECT
    s.section_title,
    s.section_emoji,
    COUNT(DISTINCT f.city_id) AS city_count,
    ROUND(COUNT(DISTINCT f.city_id) * 100.0 / (SELECT COUNT(*) FROM dim_city_fiche), 1) AS coverage_pct,
    ROUND(AVG(LENGTH(s.content_json)), 0) AS avg_content_length,
    MIN(dc.city_name) AS example_city
FROM dim_city_fiche_section s
INNER JOIN dim_city_fiche f ON f.fiche_id = s.fiche_id
INNER JOIN dim_city dc ON dc.city_id = f.city_id
GROUP BY s.section_title
ORDER BY city_count DESC;

CREATE VIEW vw_fiche_city_richness AS
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
GROUP BY dc.city_id
ORDER BY total_content_length DESC;

CREATE VIEW vw_fiche_section_content_stats AS
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
