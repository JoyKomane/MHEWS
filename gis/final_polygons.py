# gis/final_polygons.py
import httpx
import asyncio
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.main import database, startup

# Reliable GeoJSON source
GEOJSON_URL = "https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson"

# Explicit mapping: Dataset Name -> Your Database Name
NAME_MAP = {
    "Madagascar": "Madagascar",
    "France": "France",
    "Kazakhstan": "Kazakhstan",
    "Germany": "Germany",
    "Spain": "Spain",
    "Italy": "Italy",
    "United Kingdom": "United Kingdom of Great Britain and Northern Ireland",
    "Poland": "Poland",
    "Ukraine": "Ukraine",
    "Romania": "Romania",
    "Greece": "Greece",
    "Portugal": "Portugal",
    "Sweden": "Sweden",
    "Norway": "Norway",
    "Finland": "Finland",
    "Austria": "Austria",
    "Switzerland": "Switzerland",
    "Belgium": "Belgium",
    "Netherlands": "Netherlands",
    "Czech Republic": "Czechia",
    "Hungary": "Hungary",
    "Slovakia": "Slovakia",
    "Slovenia": "Slovenia",
    "Croatia": "Croatia",
    "Bosnia and Herzegovina": "Bosnia and Herzegovina",
    "Serbia": "Serbia",
    "Bulgaria": "Bulgaria",
    "Latvia": "Latvia",
    "Lithuania": "Lithuania",
    "Estonia": "Estonia",
    "Moldova": "Republic of Moldova",
    "India": "India",
    "China": "China",
    "South Africa": "South Africa",
    "Australia": "Australia",
    "Canada": "Canada",
    "United States of America": "United States",
    "Brazil": "Brazil",
    "Argentina": "Argentina",
    "Japan": "Japan",
    "South Korea": "Republic of Korea",
    "Indonesia": "Indonesia",
    "Thailand": "Thailand",
    "Philippines": "Philippines",
    "New Zealand": "New Zealand",
    "Mexico": "Mexico",
    "Turkey": "Türkiye",
    "Egypt": "Egypt",
    "Saudi Arabia": "Saudi Arabia",
    "Iran": "Iran (Islamic Republic of)",
    "Algeria": "Algeria",
    "Morocco": "Morocco",
    "Kenya": "Kenya",
    "Nigeria": "Nigeria",
    "Chile": "Chile",
    "Colombia": "Colombia",
    "Peru": "Peru"
}

def coords_to_wkt(coords):
    points = [f"{c[0]} {c[1]}" for c in coords]
    if len(points) < 3: return None
    if points[0] != points[-1]: points.append(points[0])
    return f"POLYGON(({', '.join(points)}))"

async def fix_polygons():
    print("🌍 Downloading world borders...")
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(GEOJSON_URL)
    
    if resp.status_code != 200:
        print(f"❌ Failed to download. Status: {resp.status_code}")
        return

    try:
        data = resp.json()
    except json.JSONDecodeError:
        print("❌ JSON Error. The URL might be down.")
        return
    
    updated = 0
    for feature in data.get('features', []):
        # This dataset uses 'ADMIN' for country names
        ne_name = feature['properties'].get('ADMIN') 
        if ne_name in NAME_MAP:
            target_name = NAME_MAP[ne_name]
            geom = feature['geometry']
            wkt = None
            
            if geom['type'] == 'Polygon':
                wkt = coords_to_wkt(geom['coordinates'][0])
            elif geom['type'] == 'MultiPolygon':
                largest = max(geom['coordinates'], key=lambda p: len(p[0]))
                wkt = coords_to_wkt(largest[0])
                
            if wkt:
                await database.execute("""
                    UPDATE country_polygons 
                    SET polygon_wkt = :wkt 
                    WHERE country_name = :name
                """, {"wkt": wkt, "name": target_name})
                updated += 1
                print(f"  ✅ Upgraded: {target_name}")
                
    print(f"\n🎉 SUCCESS! Upgraded {updated} countries.")

async def main():
    await startup()
    try: 
        await fix_polygons()
    finally: 
        await database.disconnect()

if __name__ == '__main__': 
    asyncio.run(main())