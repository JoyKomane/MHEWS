# gis/clean_and_load_polygons.py
import httpx
import asyncio
import sys
import os
import re
from bs4 import BeautifulSoup

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.main import database, startup

WMO_ATOM_URL = "https://alertingauthority.wmo.int/atom.xml"

def clean_polygon_string(raw_text):
    """Cleans messy WMO polygon strings and swaps Lat/Lon to Lon/Lat for maps."""
    if not raw_text:
        return None
    
    # Remove garbage like "Syria, , , Syria"
    if not re.search(r'\d', raw_text):
        return None

    points = []
    # Split by whitespace to get individual coordinate pairs
    for pair in raw_text.strip().split():
        if ',' in pair:
            try:
                lat_str, lon_str = pair.split(',')
                lat = float(lat_str)
                lon = float(lon_str)
                # SWAP to [Longitude, Latitude] for GeoJSON/PostGIS
                points.append(f"{lon} {lat}")
            except ValueError:
                continue # Skip malformed pairs like "Syria,"

    # A polygon needs at least 3 points
    if len(points) < 3:
        return None

    # Ensure the polygon is closed (first point == last point)
    if points[0] != points[-1]:
        points.append(points[0])

    # Return as PostGIS WKT format
    return f"POLYGON(({', '.join(points)}))"

async def clean_and_load():
    print("🧹 Starting WMO Data Cleanup...")
    
    # 1. Ensure the table exists
    await database.execute("""
        CREATE TABLE IF NOT EXISTS country_polygons (
            iso_code VARCHAR(3) PRIMARY KEY,
            country_name VARCHAR(100),
            polygon_wkt TEXT
        )
    """)
    print("✅ Database table ready.")

    # 2. Fetch the messy data
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(WMO_ATOM_URL)
    
    # 3. Parse with BeautifulSoup (forgiving of bad XML)
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    inserted = 0
    skipped = 0
    
    for entry in soup.find_all('entry'):
        title_elem = entry.find('title')
        iso_elem = entry.find('iso:countrycode')
        
        if not title_elem or not iso_elem:
            continue
            
        # Extract Country Name (e.g., "France: Météo-France" -> "France")
        full_title = title_elem.get_text(strip=True)
        country_name = full_title.split(':')[0].strip()
        iso_code = iso_elem.get_text(strip=True)
        
        # Find the polygon tag (BS4 handles namespaces loosely)
        poly_elem = entry.find('cap:polygon') or entry.find('polygon')
        
        if poly_elem:
            raw_poly = poly_elem.get_text(strip=True)
            clean_wkt = clean_polygon_string(raw_poly)
            
            if clean_wkt:
                # Insert or update the database
                await database.execute(
                    """INSERT INTO country_polygons (iso_code, country_name, polygon_wkt) 
                       VALUES (:iso, :name, :wkt) 
                       ON CONFLICT (iso_code) DO UPDATE SET polygon_wkt = EXCLUDED.polygon_wkt""",
                    {"iso": iso_code, "name": country_name, "wkt": clean_wkt}
                )
                inserted += 1
                print(f"  ✅ Loaded shape for: {country_name}")
            else:
                skipped += 1
        else:
            skipped += 1

    print(f"\n Cleanup Complete!")
    print(f"   ✅ Loaded {inserted} valid country shapes.")
    print(f"   🗑️ Skipped {skipped} messy/empty entries.")

async def main():
    await startup()
    try:
        await clean_and_load()
    finally:
        await database.disconnect()

if __name__ == '__main__':
    asyncio.run(main())