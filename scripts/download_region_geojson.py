"""Download simplified GeoJSON for Canada provinces and US states, merge into one file."""
import requests
import json
import os

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "data")
os.makedirs(OUT_DIR, exist_ok=True)

url_ca = "https://raw.githubusercontent.com/codeforamerica/click_that_hood/master/public/data/canada.geojson"
url_us = "https://raw.githubusercontent.com/PublicaMundi/MappingAPI/master/data/geojson/us-states.json"

print("Downloading Canada provinces...")
r_ca = requests.get(url_ca, timeout=30)
print(f"  Status: {r_ca.status_code}, {len(r_ca.content)} bytes")

print("Downloading US states...")
r_us = requests.get(url_us, timeout=30)
print(f"  Status: {r_us.status_code}, {len(r_us.content)} bytes")

if r_ca.status_code != 200 or r_us.status_code != 200:
    print("ERROR: Failed to download")
    exit(1)

ca = r_ca.json()
us = r_us.json()

print(f"Canada features: {len(ca['features'])}")
print(f"US features: {len(us['features'])}")

# Show names
ca_names = [f["properties"].get("name") for f in ca["features"]]
us_names = [f["properties"].get("name") for f in us["features"]]
print("CA names:", ca_names)
print("US names:", us_names)

# Normalize: set a unified "name" and "country" field
for f in ca["features"]:
    f["properties"] = {"name": f["properties"].get("name", ""), "country": "Canada"}

for f in us["features"]:
    f["properties"] = {"name": f["properties"].get("name", ""), "country": "United States"}

# Merge into one FeatureCollection
merged = {
    "type": "FeatureCollection",
    "features": ca["features"] + us["features"],
}

out_path = os.path.join(OUT_DIR, "regions.geojson")
with open(out_path, "w", encoding="utf-8") as fp:
    json.dump(merged, fp, ensure_ascii=False)

print(f"\nSaved {len(merged['features'])} features to {out_path}")
print(f"File size: {os.path.getsize(out_path)} bytes")
