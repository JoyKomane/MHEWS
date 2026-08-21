# debug.py
import asyncio
import sys
import os
import httpx

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.main import database, startup
from gis.cap_parser import parse_feed

async def main():
    await startup()
    try:
        print("1. Checking cap_sources for Kazakhstan...")
        rows = await database.fetch_all("SELECT country, feed_url FROM cap_sources WHERE feed_url ILIKE '%kazakhstan%' LIMIT 2")
        for r in rows:
            print(f"   -> Country: '{r['country']}', URL: {r['feed_url']}")
        
        print("\n2. Testing parser on Kazakhstan feed...")
        url = "https://meteoalert.meteoinfo.ru/kazakhstan/cap-feed/en/atom.xml"
        resp = httpx.get(url, timeout=10.0)
        alerts = parse_feed(resp.content, url, "Kazakhstan")
        
        print(f"   -> Parsed {len(alerts)} alerts")
        if alerts:
            a = alerts[0]
            print("   -> Keys in parsed alert:", list(a.keys()))
            print("   -> Has 'identifier'?:", 'identifier' in a)
            print("   -> Has 'effective'?:", 'effective' in a)
            print("   -> Has 'polygon'?:", 'polygon' in a)
            print("   -> Polygon length:", len(a.get('polygon', '')))
        else:
            print("   -> WARNING: Parser returned 0 alerts!")
            
    finally:
        await database.disconnect()

if __name__ == '__main__':
    asyncio.run(main())