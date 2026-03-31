"""Build country_detail.html from region_detail.html with substitutions."""
import re
import os

root = os.path.join(os.path.dirname(__file__), "..")
src_path = os.path.join(root, "templates", "web", "region_detail.html")
dst_path = os.path.join(root, "templates", "web", "country_detail.html")

with open(src_path, encoding="utf-8") as f:
    result = f.read()

# ---------- Jinja variables ----------
result = result.replace("region.region_slug", "country.country_slug")
result = result.replace("region.region_name", "country.country_name")
result = result.replace("region.region_color", "country.country_color")
result = result.replace("region.flag_path", "country.flag_path")
result = result.replace("region.latest_population", "country.latest_population")
result = result.replace("region.latest_year", "country.latest_year")
result = result.replace("region.peak_population", "country.peak_population")
result = result.replace("region.peak_year", "country.peak_year")
result = result.replace("region.first_population", "country.first_population")
result = result.replace("region.first_year", "country.first_year")
result = result.replace("region.trend_label", "country.trend_label")
result = result.replace("region.photo_path", "country.photo_path")
# region.country_name (Jinja: region's parent country) -> country.country_name
result = result.replace("region.country_name", "country.country_name")
# catch any remaining {{ region. 
result = result.replace("{{ region.", "{{ country.")

# ---------- Template variable: region_photos → country_photos ----------
result = result.replace("region_photos", "country_photos")

# ---------- HTML ids / href anchors ----------
for suffix in ("chart", "photos", "annotations", "timeline", "fiche"):
    result = result.replace(f'id="region-{suffix}"', f'id="country-{suffix}"')
    result = result.replace(f'href="#region-{suffix}"', f'href="#country-{suffix}"')

for suffix in ("delete-modal", "delete-btn", "delete-btn-footer",
               "delete-modal-close", "delete-cancel"):
    result = result.replace(f'id="region-{suffix}"', f'id="country-{suffix}"')

# ---------- data-* attributes ----------
result = result.replace("data-region-slug", "data-country-slug")

# ---------- url_for() route names ----------
for route in ("photo_upload", "photo_set_primary", "photo_delete", "directory", "delete"):
    result = result.replace(f"web.region_{route}", f"web.country_{route}")

# url_for kwarg: region_slug= -> country_slug=
result = result.replace("region_slug=", "country_slug=")

# ---------- URLs in JS ----------
result = result.replace("'/regions/'", "'/countries/'")
result = result.replace('"/regions/"', '"/countries/"')
result = result.replace("/regions/", "/countries/")

# ---------- JS variable / data attribute access ----------
result = result.replace(".dataset.regionSlug", ".dataset.countrySlug")
result = result.replace("searchBtn.dataset.regionSlug", "searchBtn.dataset.countrySlug")

# JS slug from Jinja
result = result.replace(
    "var slug = '{{ region.region_slug }}'",
    "var slug = '{{ country.country_slug }}'",
)
# regionName pill in annotation search
result = result.replace(
    "var regionName = '{{ region.region_name }}';",
    "var regionName = '{{ country.country_name }}';",
)

# ---------- JS getElementById for delete modal ----------
for suffix in ("delete-modal", "delete-btn", "delete-btn-footer",
               "delete-modal-close", "delete-cancel"):
    result = result.replace(
        f"document.getElementById('region-{suffix}')",
        f"document.getElementById('country-{suffix}')",
    )

# ---------- Header aria-label ----------
result = result.replace(
    'aria-label="Navigation rapide région"',
    'aria-label="Navigation rapide pays"',
)

# ---------- Subtitle: "Région — country_name" → "Pays" ----------
result = result.replace(
    "<p class=\"eyebrow\">Région &mdash; {{ country.country_name }}</p>",
    "<p class=\"eyebrow\">Pays</p>",
)

# ---------- French text ----------
result = result.replace("Aucune annotation pour cette région.", "Aucune annotation pour ce pays.")
result = result.replace("cette région", "ce pays")
result = result.replace("de cette région", "de ce pays")
result = result.replace("Supprimer la région", "Supprimer le pays")
result = result.replace("Supprimer cette région", "Supprimer ce pays")
result = result.replace("← Retour aux régions", "← Retour aux pays")
result = result.replace("pour cette région", "pour ce pays")
result = result.replace("de la région", "du pays")

# ---------- Delete modal body text ----------
result = result.replace(
    "<p>Supprimer <strong>{{ country.country_name }}</strong> de la base de données ?</p>",
    "<p>Supprimer <strong>{{ country.country_name }}</strong> de la base de données ?</p>",
)

# ---------- Write output ----------
with open(dst_path, "w", encoding="utf-8", newline="\n") as f:
    f.write(result)

# ---------- Verify ----------
with open(dst_path, "rb") as f:
    data = f.read()

try:
    decoded = data.decode("utf-8")
    print(f"Valid UTF-8 — {len(data)} bytes")

    remaining = list(re.finditer(r"region(?!_color)", decoded, re.IGNORECASE))
    # filter out false positives (e.g., "region" might appear in comments or dummy text)
    suspicious = [m for m in remaining if "country" not in decoded[max(0, m.start()-5):m.end()+20]]
    if not suspicious:
        print("No stray 'region' refs: OK")
    else:
        print(f"WARNING: {len(suspicious)} potential region refs remaining")
        for m in suspicious[:10]:
            print(f"  L{decoded[:m.start()].count(chr(10))+1}: {repr(decoded[max(0,m.start()-30):m.end()+30])}")

    if b"country_slug" in data and b"/countries/" in data:
        print("country_slug and /countries/ present: OK")

except UnicodeDecodeError as e:
    print(f"INVALID UTF-8: {e}")
