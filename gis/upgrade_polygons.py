# gis/upgrade_polygons.py
import httpx
import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.main import database, startup

# High-resolution world borders (Public Domain)
NATURAL_EARTH_URL = "https://raw.githubusercontent.com/holtzy/D3-World-Map-Data/master/ne_50m_admin_0_countries.geojson"

def coords_to_wkt(coords):
    """Converts a list of [lon, lat] coordinates to PostGIS WKT format."""
    points = [f"{c[0]} {c[1]}" for c in coords]
    if len(points) < 3: return None
    # Ensure polygon is closed
    if points[0] != points[-1]: points.append(points[0])
    return f"POLYGON(({', '.join(points)}))"

async def upgrade():
    print("🌍 Downloading high-resolution Natural Earth borders...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(NATURAL_EARTH_URL)
    
    data = resp.json()
    features = data.get('features', [])
    print(f" Found {len(features)} country shapes in dataset.")
    
    updated = 0
    for feature in features:
        # Get the 3-letter ISO code (e.g., 'FRA', 'KAZ')
        iso_a3 = feature['properties'].get('ISO_A3')
        if not iso_a3 or iso_a3 == '-99': 
            continue

        geom = feature['geometry']
        wkt = None

        # Handle different geometry types from Natural Earth
        if geom['type'] == 'Polygon':
            wkt = coords_to_wkt(geom['coordinates'][0])
        elif geom['type'] == 'MultiPolygon':
            # For countries with islands (like Indonesia), take the largest landmass
            largest_poly = max(geom['coordinates'], key=lambda p: len(p[0]))
            wkt = coords_to_wkt(largest_poly[0])

        if wkt:
            # Update the existing row in our database that matches this ISO code
            await database.execute("""
                UPDATE country_polygons 
                SET polygon_wkt = :wkt 
                WHERE iso_code = :iso
            """, {"wkt": wkt, "iso": iso_a3})
            updated += 1

    print(f"\n SUCCESS! Upgraded {updated} country shapes to high-resolution borders.")
    print("💡 Next: Run the ingestor to apply these new shapes to your alerts!")

async def main():
    await startup()
    try: 
        await upgrade()
    finally: 
        await database.disconnect()

if __name__ == '__main__': 
    asyncio.run(main())