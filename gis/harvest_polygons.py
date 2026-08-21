# gis/harvest_polygons.py
import httpx
import asyncio
import sys
import os
from bs4 import BeautifulSoup

# Add parent directory to path to import backend modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.main import database, startup

WMO_ATOM_URL = "https://alertingauthority.wmo.int/atom.xml"

def parse_polygon_to_wkt(poly_str):
    """Converts WMO 'lat,lon lat,lon' string to PostGIS WKT 'POLYGON((lon lat...))'"""
    if not poly_str or "Syria" in poly_str: # Skip known malformed data
        return None
    try:
        points = []
        for pair in poly_str.strip().split():
            if ',' in pair:
                lat, lon = pair.split(',')
                # SWAP to [lon, lat] for GeoJSON/PostGIS
                points.append(f"{float(lon)} {float(lat)}")
        
        if len(points) < 3:
            return None
            
        # Ensure the polygon is closed (first point == last point)
        if points[0] != points[-1]:
            points.append(points[0])
            
        return f"POLYGON(({', '.join(points)}))"
    except Exception:
        return None

async def harvest():
    print("🌍 Harvesting official WMO country polygons...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(WMO_ATOM_URL)
    
    # BeautifulSoup with html.parser is incredibly forgiving with messy XML/namespaces
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    inserted = 0
    for entry in soup.find_all('entry'):
        title_elem = entry.find('title')
        country_code_elem = entry.find('iso:countrycode')
        
        if not title_elem or not country_code_elem:
            continue
            
        country_name = title_elem.get_text(strip=True).split(':')[0].strip()
        iso_code = country_code_elem.get_text(strip=True)
        
        # Find the polygon tag (bs4 handles namespaces loosely, so we check both)
        poly_elem = entry.find('cap:polygon') or entry.find('polygon')
        
        if poly_elem:
            poly_str = poly_elem.get_text(strip=True)
            wkt = parse_polygon_to_wkt(poly_str)
            if wkt:
                await database.execute(
                    """INSERT INTO country_polygons (iso_code, country_name, polygon_wkt) 
                       VALUES (:iso, :name, :wkt) 
                       ON CONFLICT (iso_code) DO UPDATE SET polygon_wkt = EXCLUDED.polygon_wkt""",
                    {"iso": iso_code, "name": country_name, "wkt": wkt}
                )
                inserted += 1
                print(f"  ✅ {country_name} ({iso_code})")
                
    print(f"\n🏆 Successfully stored {inserted} country boundaries in the database.")

async def main():
    await startup()
    try:
        await harvest()
    finally:
        await database.disconnect()

if __name__ == '__main__':
    asyncio.run(main())