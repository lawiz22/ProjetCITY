#!/usr/bin/env python3
"""Filter regions.geojson to only needed countries and simplify coordinates."""
import json, os

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEOJSON = os.path.join(PROJ, 'static', 'data', 'regions.geojson')

NEEDED_COUNTRIES = {
    'Afghanistan', 'Germany', 'Saudi Arabia', 'Austria', 'Belgium',
    'Brazil', 'China', 'South Korea', 'North Korea', 'Cuba', 'Spain',
    'France', 'India', 'Iraq', 'Iran', 'Italy', 'Japan', 'Jordan',
    'Kuwait', 'Mexico', 'Netherlands', 'Pakistan', 'Philippines',
    'Poland', 'United Kingdom', 'Russia', 'Syria', 'Ukraine', 'Vietnam',
    'Turkey', 'Kazakhstan'
}

def simplify_coords(obj, precision=1):
    if isinstance(obj, list):
        if obj and isinstance(obj[0], (int, float)):
            return [round(c, precision) for c in obj]
        return [simplify_coords(item, precision) for item in obj]
    return obj

def remove_duplicate_points(coords):
    """Remove consecutive duplicate points after rounding."""
    if isinstance(coords, list) and coords and isinstance(coords[0], list):
        if coords[0] and isinstance(coords[0][0], (int, float)):
            # This is a ring of coordinates
            deduped = [coords[0]]
            for pt in coords[1:]:
                if pt != deduped[-1]:
                    deduped.append(pt)
            return deduped
        return [remove_duplicate_points(item) for item in coords]
    return coords

with open(GEOJSON, 'r', encoding='utf-8') as f:
    data = json.load(f)

keep = []
for feat in data['features']:
    name = feat['properties'].get('name', '')
    country = feat['properties'].get('country', '')
    
    # Keep all Canada/US province/state features (already at precision 2)
    if country in ('Canada', 'United States'):
        keep.append(feat)
    elif name in NEEDED_COUNTRIES:
        # Simplify world countries more aggressively (1 decimal = ~11km)
        feat['geometry']['coordinates'] = simplify_coords(feat['geometry']['coordinates'], 1)
        feat['geometry']['coordinates'] = remove_duplicate_points(feat['geometry']['coordinates'])
        keep.append(feat)

merged = {'type': 'FeatureCollection', 'features': keep}
with open(GEOJSON, 'w', encoding='utf-8') as f:
    json.dump(merged, f, ensure_ascii=False)

size_kb = os.path.getsize(GEOJSON) / 1024
print(f"Written {len(keep)} features ({size_kb:.0f} KB)")

ca_us = [f for f in keep if f['properties']['country'] in ('Canada', 'United States')]
world = [f for f in keep if f['properties']['country'] not in ('Canada', 'United States')]
print(f"  CA/US: {len(ca_us)} features")
print(f"  World: {len(world)} features")
for f in sorted(world, key=lambda x: x['properties']['name']):
    print(f"    - {f['properties']['name']}")

matched = {f['properties']['name'] for f in world}
missing = NEEDED_COUNTRIES - matched
if missing:
    print(f"  MISSING: {missing}")
else:
    print("  All needed countries found!")
