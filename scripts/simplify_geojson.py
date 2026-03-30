"""Simplify the regions.geojson by reducing coordinate precision to 2 decimal places."""
import json
import os

PATH = os.path.join(os.path.dirname(__file__), "..", "static", "data", "regions.geojson")

with open(PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

def simplify_coords(coords):
    """Reduce precision of coordinates to 2 decimal places."""
    if isinstance(coords[0], (int, float)):
        return [round(coords[0], 2), round(coords[1], 2)]
    return [simplify_coords(c) for c in coords]

for feat in data["features"]:
    geom = feat["geometry"]
    geom["coordinates"] = simplify_coords(geom["coordinates"])

with open(PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

print(f"Simplified. New size: {os.path.getsize(PATH)} bytes")
