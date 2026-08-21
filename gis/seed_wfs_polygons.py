# gis/seed_wfs_polygons.py
import httpx
import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.main import database, startup

WFS_URL = "https://severeweather.wmo.int/f/wfs?request=GetFeature&version=1.1.0&typeName=local_postgis:postgis_geojsons&cql_filter=row_type='POLYGON'&outputFormat=json"

def coords_to_wkt(geom_list):
    try:
        if not geom_list or not isinstance(geom_list, list):
            return None
        
        # Take the first geometry object in the list
        geom = geom_list[0]
        coords = geom.get('coordinates')
        geom_type = geom.get('type', '')
        
        if not coords:
            return None
            
        if geom_type == 'Polygon':
            # coords is [ [lon, lat], [lon, lat], ... ]
            ring = coords[0]
        elif geom_type == 'MultiPolygon':
            # coords is [ [ [lon, lat], ... ], [ [lon, lat], ... ] ]
            # Take the first polygon's first ring
            ring = coords[0][0]
        else:
            return None
            
        if not ring or len(ring) < 3:
            return None
            
        points = [f"{c[0]} {c[1]}" for c in ring]
        # Ensure closed ring
        if points[0] != points[-1]:
            points.append(points[0])
            
        return f"POLYGON(({', '.join(points)}))"
    except Exception:
        return None

async def seed():
    print("🌍 Fetching WFS Country Boundaries from WMO...")
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.get(WFS_URL)
    
    if resp.status_code != 200:
        print(f"❌ Failed to fetch WFS: {resp.status_code}")
        return

    data = resp.json()
    count = 0
    
    for country_name, geom_list in data.items():
        wkt = coords_to_wkt(geom_list)
        if wkt:
            # Clean up country name for better ILIKE matching in the fallback
            clean_name = country_name.replace(" (Plurinational State of)", "") \
                                     .replace(" (Federated States of)", "") \
                                     .replace("Democratic People's Republic of", "North Korea") \
                                     .replace("Republic of Korea", "South Korea") \
                                     .strip()
            
            await database.execute("""
                INSERT INTO country_polygons (country_name, polygon_wkt)
                VALUES (:name, :wkt)
                ON CONFLICT (country_name) DO UPDATE SET polygon_wkt = EXCLUDED.polygon_wkt
            """, {"name": clean_name, "wkt": wkt})
            count += 1
            if count % 20 == 0:
                print(f"  ... processed {count} countries")
    
    print(f"\n🎉 SUCCESS! Seeded {count} official WMO country boundary polygons.")

async def main():
    await startup()
    try:
        await seed()
    finally:
        await database.disconnect()

if __name__ == '__main__':
    asyncio.run(main())