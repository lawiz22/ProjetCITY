from __future__ import annotations

import json
import urllib.request
import urllib.parse
import logging

logger = logging.getLogger(__name__)

CITY_COORDINATES: dict[str, dict[str, float]] = {
    "atlanta-georgia": {"lat": 33.7490, "lng": -84.3880},
    "austin-texas": {"lat": 30.2672, "lng": -97.7431},
    "baltimore-maryland": {"lat": 39.2904, "lng": -76.6122},
    "boston": {"lat": 42.3601, "lng": -71.0589},
    "boucherville-quebec": {"lat": 45.5910, "lng": -73.4360},
    "brampton-ontario": {"lat": 43.7315, "lng": -79.7624},
    "buffalo-new-york": {"lat": 42.8864, "lng": -78.8784},
    "burnaby-british-columbia": {"lat": 49.2488, "lng": -122.9805},
    "calgary-alberta": {"lat": 51.0447, "lng": -114.0719},
    "charlottetown-prince-edward-island": {"lat": 46.2382, "lng": -63.1311},
    "chicago-illinois": {"lat": 41.8781, "lng": -87.6298},
    "cincinnati-ohio": {"lat": 39.1031, "lng": -84.5120},
    "cleveland-ohio": {"lat": 41.4993, "lng": -81.6944},
    "contrecur-quebec": {"lat": 45.8500, "lng": -73.2333},
    "dallas-texas": {"lat": 32.7767, "lng": -96.7970},
    "denver-colorado": {"lat": 39.7392, "lng": -104.9903},
    "des-moines-iowa": {"lat": 41.5868, "lng": -93.6250},
    "detroit-michigan": {"lat": 42.3314, "lng": -83.0458},
    "donnacona-quebec": {"lat": 46.6833, "lng": -71.7333},
    "edmonton-alberta": {"lat": 53.5461, "lng": -113.4938},
    "field-british-columbia": {"lat": 51.3981, "lng": -116.4592},
    "flint-michigan": {"lat": 43.0125, "lng": -83.6875},
    "gary-indiana": {"lat": 41.5934, "lng": -87.3464},
    "gatineau-quebec": {"lat": 45.4765, "lng": -75.7013},
    "guelph-ontario": {"lat": 43.5448, "lng": -80.2482},
    "halifax-nova-scotia": {"lat": 44.6488, "lng": -63.5752},
    "hamilton-ontario": {"lat": 43.2557, "lng": -79.8711},
    "hobbs-new-mexico": {"lat": 32.7126, "lng": -103.1361},
    "houston-texas": {"lat": 29.7604, "lng": -95.3698},
    "la-tuque-quebec": {"lat": 47.4333, "lng": -72.7833},
    "las-vegas-nevada": {"lat": 36.1699, "lng": -115.1398},
    "laval-quebec": {"lat": 45.6066, "lng": -73.7124},
    "london-ontario": {"lat": 42.9849, "lng": -81.2453},
    "long-beach-california": {"lat": 33.7701, "lng": -118.1937},
    "longueuil-quebec": {"lat": 45.5312, "lng": -73.5181},
    "los-angeles-californie": {"lat": 34.0522, "lng": -118.2437},
    "miami-floride": {"lat": 25.7617, "lng": -80.1918},
    "minneapolis-minnesota": {"lat": 44.9778, "lng": -93.2650},
    "mississauga-ontario": {"lat": 43.5890, "lng": -79.6441},
    "moncton-new-brunswick": {"lat": 46.0878, "lng": -64.7782},
    "montreal": {"lat": 45.5017, "lng": -73.5673},
    "myrtle-beach-south-carolina": {"lat": 33.6891, "lng": -78.8867},
    "nashville-tennessee": {"lat": 36.1627, "lng": -86.7816},
    "new-orleans-louisiana": {"lat": 29.9511, "lng": -90.0715},
    "new-westminster-british-columbia": {"lat": 49.2057, "lng": -122.9110},
    "new-york-city-new-york": {"lat": 40.7128, "lng": -74.0060},
    "newark-new-jersey": {"lat": 40.7357, "lng": -74.1724},
    "north-bay-ontario": {"lat": 46.3091, "lng": -79.4608},
    "oakland-california": {"lat": 37.8044, "lng": -122.2712},
    "old-orchard-beach-maine": {"lat": 43.5176, "lng": -70.3774},
    "ottawa-ontario": {"lat": 45.4215, "lng": -75.6972},
    "philadelphia-pennsylvania": {"lat": 39.9526, "lng": -75.1652},
    "phoenix-arizona": {"lat": 33.4484, "lng": -112.0740},
    "pittsburgh-pennsylvania": {"lat": 40.4406, "lng": -79.9959},
    "portland-oregon": {"lat": 45.5152, "lng": -122.6784},
    "quebec-quebec": {"lat": 46.8139, "lng": -71.2080},
    "richmond-british-columbia": {"lat": 49.1666, "lng": -123.1336},
    "sacramento-california": {"lat": 38.5816, "lng": -121.4944},
    "saguenay-quebec": {"lat": 48.4280, "lng": -71.0680},
    "saint-jean-sur-richelieu-quebec": {"lat": 45.3071, "lng": -73.2626},
    "salt-lake-city-utah": {"lat": 40.7608, "lng": -111.8910},
    "san-francisco-californie": {"lat": 37.7749, "lng": -122.4194},
    "san-jose-california": {"lat": 37.3382, "lng": -121.8863},
    "saskatoon-saskatchewan": {"lat": 52.1579, "lng": -106.6702},
    "seattle-washington": {"lat": 47.6062, "lng": -122.3321},
    "sherbrooke-quebec": {"lat": 45.4042, "lng": -71.8929},
    "sorel-tracy": {"lat": 46.0418, "lng": -73.1139},
    "st-john-s-newfoundland-and-labrador": {"lat": 47.5615, "lng": -52.7126},
    "st-louis-missouri": {"lat": 38.6270, "lng": -90.1994},
    "sturgeon-falls-ontario": {"lat": 46.3642, "lng": -79.9329},
    "surrey-british-columbia": {"lat": 49.1913, "lng": -122.8490},
    "trois-rivieres-quebec": {"lat": 46.3430, "lng": -72.5430},
    "tucson-arizona": {"lat": 32.2226, "lng": -110.9747},
    "tumbler-ridge-british-columbia": {"lat": 55.1300, "lng": -120.9950},
    "vancouver-british-columbia": {"lat": 49.2827, "lng": -123.1207},
    "varennes-quebec": {"lat": 45.6833, "lng": -73.4333},
    "vercheres-quebec": {"lat": 45.7833, "lng": -73.3500},
    "victoria-british-columbia": {"lat": 48.4284, "lng": -123.3656},
    "virginia-beach-virginia": {"lat": 36.8529, "lng": -75.9780},
    "washington-district-of-columbia": {"lat": 38.9072, "lng": -77.0369},
    "winnipeg-manitoba": {"lat": 49.8951, "lng": -97.1384},
    "yellowknife-northwest-territories": {"lat": 62.4540, "lng": -114.3718},
}


def geocode_city(city_name: str, region: str | None, country: str) -> dict[str, float] | None:
    """Geocode a city using the Nominatim (OpenStreetMap) API.

    Returns {"lat": float, "lng": float} or None on failure.
    """
    query_parts = [city_name]
    if region:
        query_parts.append(region)
    query_parts.append(country)
    query = ", ".join(query_parts)

    params = urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "limit": "1",
    })
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "CentralCityScrutinizer/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data:
            return {"lat": round(float(data[0]["lat"]), 4), "lng": round(float(data[0]["lon"]), 4)}
    except Exception as exc:
        logger.warning("Geocoding failed for %r: %s", query, exc)
    return None


def _nominatim_search(query: str) -> dict[str, float] | None:
    """Single Nominatim search. Returns {lat, lng} or None."""
    params = urllib.parse.urlencode({"q": query, "format": "json", "limit": "1"})
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "CentralCityScrutinizer/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data:
            return {"lat": round(float(data[0]["lat"]), 4), "lng": round(float(data[0]["lon"]), 4)}
    except Exception as exc:
        logger.warning("Nominatim search failed for %r: %s", query, exc)
    return None


# Common French→English translations for monument names in Nominatim
_FR_EN_REPLACEMENTS = {
    "Statue de la Liberté": "Statue of Liberty",
    "Tour Eiffel": "Eiffel Tower",
    "Notre-Dame de Paris": "Notre-Dame de Paris",
    "Palais de Buckingham": "Buckingham Palace",
    "Tour de Londres": "Tower of London",
    "Pont du Golden Gate": "Golden Gate Bridge",
    "Maison-Blanche": "White House",
    "Empire State": "Empire State Building",
    "Colisée": "Colosseum",
    "Grande Muraille": "Great Wall of China",
}


def _english_variant(name: str) -> str | None:
    """Return an English variant of the monument name if known."""
    for fr, en in _FR_EN_REPLACEMENTS.items():
        if fr.lower() in name.lower():
            return en
    return None


def geocode_monument(monument_name: str, city_name: str | None = None,
                     region: str | None = None, country: str | None = None) -> dict[str, float] | None:
    """Geocode a monument using Nominatim with multiple fallback strategies.

    Tries in order:
    1. Full query: "monument, city, region, country"
    2. Without region: "monument, city, country"
    3. Monument name alone
    4. English variant of the name (if available)
    Returns {"lat": float, "lng": float} or None.
    """
    import time

    queries: list[str] = []

    # Strategy 1: full query
    parts = [monument_name]
    if city_name:
        parts.append(city_name)
    if region:
        parts.append(region)
    if country:
        parts.append(country)
    queries.append(", ".join(parts))

    # Strategy 2: without region
    if region and city_name and country:
        queries.append(", ".join([monument_name, city_name, country]))

    # Strategy 3: monument name alone
    if monument_name not in queries:
        queries.append(monument_name)

    # Strategy 4: English variant
    en = _english_variant(monument_name)
    if en:
        queries.append(en)
        if city_name and country:
            queries.insert(-1, f"{en}, {city_name}, {country}")

    seen: set[str] = set()
    for q in queries:
        q_lower = q.lower()
        if q_lower in seen:
            continue
        seen.add(q_lower)
        result = _nominatim_search(q)
        if result:
            return result
        time.sleep(1)  # respect Nominatim rate limit

    logger.warning("Geocoding monument exhausted all strategies for %r", monument_name)
    return None