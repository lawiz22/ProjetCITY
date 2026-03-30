#!/usr/bin/env python3
"""Download world countries GeoJSON (Natural Earth 110m) and merge with existing regions.geojson."""

import json
import urllib.request
import os

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXISTING = os.path.join(PROJ, 'static', 'data', 'regions.geojson')
OUTPUT = EXISTING  # overwrite

# Natural Earth 110m countries – small, widely used
URL = 'https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson'
# Fallback: johan/world.geo.json (older but smaller)
URL_FALLBACK = 'https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json'

# Countries to SKIP (we already have detailed provinces/states)
SKIP_COUNTRIES = {'Canada', 'United States of America', 'United States'}


def simplify_coords(obj, precision=2):
    """Recursively round coordinates to given precision."""
    if isinstance(obj, list):
        if obj and isinstance(obj[0], (int, float)):
            return [round(c, precision) for c in obj]
        return [simplify_coords(item, precision) for item in obj]
    return obj


def download_geojson(url):
    """Download GeoJSON from URL."""
    print(f"Downloading from {url}...")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    print(f"  Got {len(data.get('features', []))} features")
    return data


def main():
    # Load existing regions.geojson
    with open(EXISTING, 'r', encoding='utf-8') as f:
        existing = json.load(f)
    
    existing_names = set()
    for feat in existing['features']:
        existing_names.add(feat['properties'].get('name', ''))
    print(f"Existing features: {len(existing['features'])} ({', '.join(sorted(existing_names)[:10])}...)")

    # Download world countries
    try:
        world = download_geojson(URL)
    except Exception as e:
        print(f"Primary URL failed: {e}")
        print("Trying fallback...")
        world = download_geojson(URL_FALLBACK)

    # Process world features - normalize names
    # The datasets/geo-countries uses ADMIN field, johan/world uses 'name'
    new_features = []
    for feat in world['features']:
        props = feat['properties']
        # Try multiple name fields
        name = props.get('ADMIN') or props.get('name') or props.get('NAME') or ''
        
        if name in SKIP_COUNTRIES:
            continue
        
        # Simplify coordinates
        feat['geometry']['coordinates'] = simplify_coords(feat['geometry']['coordinates'])
        
        # Normalize properties to our format
        feat['properties'] = {
            'name': name,
            'country': name  # country-level feature
        }
        new_features.append(feat)
    
    print(f"World features to add (excluding CA/US): {len(new_features)}")
    
    # Merge
    all_features = existing['features'] + new_features
    merged = {
        'type': 'FeatureCollection',
        'features': all_features
    }
    
    # Write output
    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False)
    
    size_kb = os.path.getsize(OUTPUT) / 1024
    print(f"Written {len(all_features)} features to {OUTPUT} ({size_kb:.0f} KB)")
    
    # List all country names for reference
    country_names = sorted(set(f['properties']['name'] for f in new_features))
    print(f"\nCountries added ({len(country_names)}):")
    for n in country_names:
        print(f"  - {n}")


if __name__ == '__main__':
    main()
