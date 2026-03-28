"""Download flag images for all countries and regions in the database.

Sources:
  - Country flags: flagcdn.com (public domain, no rate limit)
  - US state flags: flagcdn.com (us-XX codes)
  - CA province flags: Wikimedia API (proper thumbnail URLs)

Saves to static/images/flags/{countries,regions/<country-slug>}/<slug>.png
Width: 160px for all flags.

Usage:
    python scripts/download_flags.py
"""

import os
import time
import urllib.request
import urllib.error
import json
import unicodedata

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "images", "flags")


def slugify(name: str) -> str:
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    return name.lower().replace(" ", "-").replace(".", "")


def download(url: str, dest: str) -> bool:
    if os.path.exists(dest):
        print(f"  OK already exists: {os.path.basename(dest)}")
        return True
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        if len(data) < 100:
            print(f"  FAIL too small ({len(data)} bytes): {os.path.basename(dest)}")
            return False
        with open(dest, "wb") as f:
            f.write(data)
        print(f"  OK {os.path.basename(dest)}  ({len(data)} bytes)")
        return True
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        print(f"  FAIL {os.path.basename(dest)}: {exc}")
        return False


COUNTRY_FLAGS = {
    "Canada": "https://flagcdn.com/w160/ca.png",
    "United States": "https://flagcdn.com/w160/us.png",
}

US_STATE_CODES = {
    "Alabama": "al", "Alaska": "ak", "Arizona": "az", "Arkansas": "ar",
    "California": "ca", "Colorado": "co", "Connecticut": "ct", "Delaware": "de",
    "District of Columbia": "dc", "Florida": "fl", "Georgia": "ga", "Hawaii": "hi",
    "Idaho": "id", "Illinois": "il", "Indiana": "in", "Iowa": "ia",
    "Kansas": "ks", "Kentucky": "ky", "Louisiana": "la", "Maine": "me",
    "Maryland": "md", "Massachusetts": "ma", "Michigan": "mi", "Minnesota": "mn",
    "Mississippi": "ms", "Missouri": "mo", "Montana": "mt", "Nebraska": "ne",
    "Nevada": "nv", "New Hampshire": "nh", "New Jersey": "nj", "New Mexico": "nm",
    "New York": "ny", "North Carolina": "nc", "North Dakota": "nd", "Ohio": "oh",
    "Oklahoma": "ok", "Oregon": "or", "Pennsylvania": "pa", "Rhode Island": "ri",
    "South Carolina": "sc", "South Dakota": "sd", "Tennessee": "tn", "Texas": "tx",
    "Utah": "ut", "Vermont": "vt", "Virginia": "va", "Washington": "wa",
    "West Virginia": "wv", "Wisconsin": "wi", "Wyoming": "wy",
}

CA_PROVINCE_WIKI = {
    "Alberta": "Flag_of_Alberta.svg",
    "British Columbia": "Flag_of_British_Columbia.svg",
    "Manitoba": "Flag_of_Manitoba.svg",
    "New Brunswick": "Flag_of_New_Brunswick.svg",
    "Newfoundland and Labrador": "Flag_of_Newfoundland_and_Labrador.svg",
    "Northwest Territories": "Flag_of_the_Northwest_Territories.svg",
    "Nova Scotia": "Flag_of_Nova_Scotia.svg",
    "Nunavut": "Flag_of_Nunavut.svg",
    "Ontario": "Flag_of_Ontario.svg",
    "Prince Edward Island": "Flag_of_Prince_Edward_Island.svg",
    "Québec": "Flag_of_Quebec.svg",
    "Saskatchewan": "Flag_of_Saskatchewan.svg",
    "Yukon": "Flag_of_Yukon.svg",
}


def get_wikimedia_thumb_url(filename: str, width: int = 160) -> str | None:
    api_url = (
        "https://en.wikipedia.org/w/api.php?"
        "action=query&titles=File:" + urllib.request.quote(filename) +
        "&prop=imageinfo&iiprop=url&iiurlwidth=" + str(width) +
        "&format=json"
    )
    try:
        req = urllib.request.Request(api_url, headers={
            "User-Agent": "ProjetCITY-FlagBot/1.0 (educational project)"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            ii = page.get("imageinfo", [{}])[0]
            return ii.get("thumburl")
    except Exception as exc:
        print(f"  Wiki API error for {filename}: {exc}")
    return None


def main() -> None:
    os.makedirs(BASE_DIR, exist_ok=True)
    ok, fail = 0, 0

    print("=== Country flags ===")
    country_dir = os.path.join(BASE_DIR, "countries")
    os.makedirs(country_dir, exist_ok=True)
    for country, url in COUNTRY_FLAGS.items():
        dest = os.path.join(country_dir, slugify(country) + ".png")
        if download(url, dest):
            ok += 1
        else:
            fail += 1
        time.sleep(0.5)

    print("\n=== US state flags ===")
    us_dir = os.path.join(BASE_DIR, "regions", "united-states")
    os.makedirs(us_dir, exist_ok=True)
    for state, code in US_STATE_CODES.items():
        url = f"https://flagcdn.com/w160/us-{code}.png"
        dest = os.path.join(us_dir, slugify(state) + ".png")
        if download(url, dest):
            ok += 1
        else:
            fail += 1
        time.sleep(0.3)

    print("\n=== Canadian province flags ===")
    ca_dir = os.path.join(BASE_DIR, "regions", "canada")
    os.makedirs(ca_dir, exist_ok=True)
    for province, wiki_file in CA_PROVINCE_WIKI.items():
        dest = os.path.join(ca_dir, slugify(province) + ".png")
        if os.path.exists(dest):
            print(f"  OK already exists: {os.path.basename(dest)}")
            ok += 1
            continue
        thumb_url = get_wikimedia_thumb_url(wiki_file, width=160)
        if thumb_url:
            if download(thumb_url, dest):
                ok += 1
            else:
                fail += 1
        else:
            print(f"  FAIL Could not resolve Wiki URL for {province}")
            fail += 1
        time.sleep(1.5)

    print(f"\n{'='*50}")
    print(f"Done!  {ok} downloaded  /  {fail} failed")
    print(f"Flags saved to: {os.path.abspath(BASE_DIR)}")


if __name__ == "__main__":
    main()
