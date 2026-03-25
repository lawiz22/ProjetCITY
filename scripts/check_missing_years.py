"""Check missing years for big Canadian cities vs reference population years."""
import sqlite3

conn = sqlite3.connect("data/city_analysis.db")
conn.row_factory = sqlite3.Row

# Reference census years for Canada (national)
ref_years = conn.execute(
    "SELECT year FROM ref_population WHERE country='Canada' AND region IS NULL ORDER BY year"
).fetchall()
ref_set = set(r["year"] for r in ref_years)
print(f"=== Années de recensement Canada (ref_population): {len(ref_set)} ===")
print(sorted(ref_set))

# All Canadian cities sorted by max population
print("\n=== Grosses villes canadiennes ===")
cities = conn.execute("""
    SELECT dc.city_id, dc.city_name, dc.region, MAX(f.population) as max_pop
    FROM fact_city_population f
    JOIN dim_city dc ON dc.city_id = f.city_id
    JOIN dim_time dt ON dt.time_id = f.time_id
    WHERE dc.country = 'Canada'
    GROUP BY dc.city_id
    ORDER BY max_pop DESC
""").fetchall()

for c in cities:
    city_id = c["city_id"]
    name = c["city_name"]
    region = c["region"]
    max_pop = c["max_pop"]

    # Get years for this city
    yrows = conn.execute("""
        SELECT dt.year FROM fact_city_population f
        JOIN dim_time dt ON dt.time_id = f.time_id
        WHERE f.city_id = ?
        ORDER BY dt.year
    """, (city_id,)).fetchall()
    city_years = set(r["year"] for r in yrows)

    # Find which ref years are missing
    missing = sorted(ref_set - city_years)
    present = sorted(ref_set & city_years)

    print(f"\n{name} ({region}) — max pop: {max_pop:,} — {len(city_years)} années dans BD")
    print(f"  Années BD: {sorted(city_years)}")
    print(f"  Années réf. présentes: {present}")
    print(f"  Années réf. MANQUANTES: {missing}")

# Also show years in DB that are NOT in ref_population
print("\n\n=== Années dans la BD (Canada) qui NE SONT PAS dans ref_population ===")
db_years = conn.execute("""
    SELECT DISTINCT dt.year
    FROM fact_city_population f
    JOIN dim_city dc ON dc.city_id = f.city_id
    JOIN dim_time dt ON dt.time_id = f.time_id
    WHERE dc.country = 'Canada'
    ORDER BY dt.year
""").fetchall()
db_year_set = set(r["year"] for r in db_years)
extra = sorted(db_year_set - ref_set)
print(f"Années BD non-référencées: {extra}")
print(f"Années ref non couvertes: {sorted(ref_set - db_year_set)}")

conn.close()
