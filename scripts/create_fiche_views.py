"""Create the 4 fiche analytical views in the live database."""
import sqlite3

DB = "data/city_analysis.db"

VIEWS_SQL = """
CREATE VIEW IF NOT EXISTS vw_fiche_coverage AS
SELECT
    dc.city_id, dc.city_name, dc.city_slug, dc.country, dc.region,
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

CREATE VIEW IF NOT EXISTS vw_fiche_section_catalog AS
SELECT
    s.section_title, s.section_emoji,
    COUNT(DISTINCT f.city_id) AS city_count,
    ROUND(COUNT(DISTINCT f.city_id) * 100.0 / (SELECT COUNT(*) FROM dim_city_fiche), 1) AS coverage_pct,
    ROUND(AVG(LENGTH(s.content_json)), 0) AS avg_content_length,
    MIN(dc.city_name) AS example_city
FROM dim_city_fiche_section s
INNER JOIN dim_city_fiche f ON f.fiche_id = s.fiche_id
INNER JOIN dim_city dc ON dc.city_id = f.city_id
GROUP BY s.section_title
ORDER BY city_count DESC;

CREATE VIEW IF NOT EXISTS vw_fiche_city_richness AS
SELECT
    dc.city_id, dc.city_name, dc.city_slug, dc.country, dc.region,
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

CREATE VIEW IF NOT EXISTS vw_fiche_section_content_stats AS
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
"""

if __name__ == "__main__":
    conn = sqlite3.connect(DB)
    conn.executescript(VIEWS_SQL)
    conn.close()
    print("4 fiche views created.")
    conn = sqlite3.connect(DB)
    for v in ["vw_fiche_coverage", "vw_fiche_section_catalog", "vw_fiche_city_richness", "vw_fiche_section_content_stats"]:
        r = conn.execute(f"SELECT COUNT(*) FROM {v}").fetchone()
        print(f"  {v}: {r[0]} rows")
    conn.close()
