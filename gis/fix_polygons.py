# gis/fix_polygons.py
import httpx
import asyncio
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.main import database, startup

# Reliable, standard GeoJSON source for world countries
GEOJSON_URL = "https://raw.githubusercontent.com/johan/world.geo.json/master/countries.geo.json"

# Direct mapping from this dataset's 'name' to our exact country_name in the DB
NAME_MAP = {
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
    "United States": "United States",
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
    print("🌍 Downloading high-res world borders...")
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(GEOJSON_URL)
    
    # Debugging: if it's not 200 OK, print what we got
    if resp.status_code != 200:
        print(f"❌ Failed to download. Status: {resp.status_code}")
        print(f"Response: {resp.text[:200]}")
        return

    try:
        data = resp.json()
    except json.JSONDecodeError as e:
        print(f"❌ JSON Decode Error. The server returned: {resp.text[:200]}")
        return
    
    updated = 0
    
    for feature in data.get('features', []):
        # Note: this dataset uses lowercase 'name'
        ne_name = feature['properties'].get('name')
        if ne_name in NAME_MAP:
            target_name = NAME_MAP[ne_name]
            geom = feature['geometry']
            wkt = None
            
            if geom['type'] == 'Polygon':
                wkt = coords_to_wkt(geom['coordinates'][0])
            elif geom['type'] == 'MultiPolygon':
                # For countries with islands, take the largest landmass
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
                
    print(f"\n🎉 SUCCESS! Upgraded {updated} countries to high-resolution shapes.")
    print("💡 Now run: docker compose exec app python -m gis.ingestor")

async def main():
    await startup()
    try: 
        await fix_polygons()
    finally: 
        await database.disconnect()

if __name__ == '__main__': 
    asyncio.run(main())