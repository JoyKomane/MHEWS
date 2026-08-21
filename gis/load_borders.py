import json
import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.main import database, startup

# Simple name mapping
COUNTRIES = {
    "France": "France",
    "Kazakhstan": "Kazakhstan", 
    "Germany": "Germany",
    "Spain": "Spain",
    # ... add all countries you need
}

async def load():
    with open("gis/countries.geojson") as f:
        data = json.load(f)
    
    for feature in data['features']:
        name = feature['properties'].get('name')
        if name in COUNTRIES:
            coords = feature['geometry']['coordinates'][0][0]  # Simplified
            # Convert to WKT and update DB
            print(f"Loaded {COUNTRIES[name]}")

asyncio.run(load())