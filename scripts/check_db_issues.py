"""Temporary script to fix DB issues."""
import sqlite3

conn = sqlite3.connect("data/city_analysis.db")

# Geocode Longlac
conn.execute(
    "UPDATE dim_city SET latitude = 49.7782, longitude = -86.5394 WHERE city_slug LIKE '%longlac%' AND latitude IS NULL"
)

# Geocode Timmins
conn.execute(
    "UPDATE dim_city SET latitude = 48.4775, longitude = -81.3304 WHERE city_slug LIKE '%timmins%' AND latitude IS NULL"
)

conn.commit()

# Verify
print("Longlac:", conn.execute(
    "SELECT city_name, region, country, latitude, longitude FROM dim_city WHERE city_slug LIKE '%longlac%'"
).fetchone())

print("Timmins:", conn.execute(
    "SELECT city_name, region, country, latitude, longitude FROM dim_city WHERE city_slug LIKE '%timmins%'"
).fetchone())

conn.close()
