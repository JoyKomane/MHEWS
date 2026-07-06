import asyncio
import sys
sys.path.insert(0, '/usr/src/app')
from db.spatial_fallback import check_location_with_fallback

async def test():
    # Inside Witzenberg / Ceres SAWS polygon (lat -32.5, lon 20.3)
    result = await check_location_with_fallback(-32.5, 20.3)
    print(f'Engine: {result["engine"]}')
    print(f'Alerts found: {result["count"]}')
    for a in result['alerts']:
        print(f'  → {a["event"]} — {a["area_desc"]}')

asyncio.run(test())
