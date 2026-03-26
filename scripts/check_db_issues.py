"""Populate area_km2 and density from fiche data for all cities."""
import sqlite3, json, re

conn = sqlite3.connect("data/city_analysis.db")

def parse_number(val: str) -> float | None:
    """Extract numeric value from strings like '~1 050 hab./km²' or '**~420 km²**'."""
    val = val.replace("\u202f", " ").replace("\xa0", " ")  # narrow no-break space
    val = val.replace("**", "")  # strip markdown bold
    val = val.replace("~", "").strip()
    # Remove units and anything after
    val = re.sub(r"\s*(hab\.?/km²|km²|hectares?|m\b).*", "", val, flags=re.IGNORECASE)
    # Remove spaces used as thousands separators
    val = val.replace(" ", "")
    # Replace comma as decimal separator (but not thousands)
    if val.count(",") == 1 and val.count(".") == 0:
        val = val.replace(",", ".")
    else:
        val = val.replace(",", "")
    try:
        return float(val)
    except ValueError:
        return None

rows = conn.execute("""
    SELECT c.city_id, c.city_name, s.content_json
    FROM dim_city_fiche_section s
    JOIN dim_city_fiche f ON f.fiche_id = s.fiche_id
    JOIN dim_city c ON c.city_id = f.city_id
    WHERE s.section_title LIKE '%ographie%' OR s.section_title LIKE '%ensit%'
""").fetchall()

updated = 0
for city_id, city_name, cj in rows:
    blocks = json.loads(cj)
    area = None
    density = None
    for b in blocks:
        if b["type"] == "table":
            for row in b.get("rows", []):
                if len(row) >= 2:
                    label = row[0].lower()
                    if area is None and ("superficie" in label or "surface" in label) and "rmr" not in label and "brûlé" not in label:
                        area = parse_number(row[1])
                    elif density is None and "densit" in label and "manhattan" not in label:
                        density = parse_number(row[1])
        elif b["type"] == "text":
            # Some fiches store as text (London-style)
            text = b["value"]
            m = re.search(r"Superficie\s*[~:]?\s*([\d\s,.]+)\s*km", text)
            if m:
                area = parse_number(m.group(1))
            m = re.search(r"Densit[eé]\s*[~:]?\s*([\d\s,.]+)\s*hab", text)
            if m:
                density = parse_number(m.group(1))

    if area is not None or density is not None:
        conn.execute(
            "UPDATE dim_city SET area_km2 = ?, density = ? WHERE city_id = ?",
            (area, density, city_id)
        )
        updated += 1
        print(f"  {city_name}: area={area}, density={density}")

conn.commit()

# Fix remaining manually
conn.execute("UPDATE dim_city SET area_km2=68000, density=1.2 WHERE city_name='Fort McMurray' AND density IS NULL")
conn.execute("UPDATE dim_city SET area_km2=0.57, density=350 WHERE city_name='Oak Island' AND density IS NULL")
conn.commit()

missing_count = conn.execute("SELECT count(*) FROM dim_city WHERE density IS NULL").fetchone()[0]
total = conn.execute("SELECT count(*) FROM dim_city WHERE density IS NOT NULL").fetchone()[0]
print(f"\nStill missing: {missing_count}")
print(f"Total with density: {total}")

conn.close()
