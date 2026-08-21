# test_parser.py
import httpx
from gis.cap_parser import parse_feed

url = 'https://www.dwd.de/DWD/warnungen/cap-feed/en/atom.xml'
print(f"Testing: {url}")

try:
    resp = httpx.get(url, timeout=10.0)
    print(f"Status: {resp.status_code}, Length: {len(resp.content)} bytes")
    
    alerts = parse_feed(resp.content, url, 'Germany')
    print(f"\nParsed {len(alerts)} alerts")
    
    if alerts:
        alert = alerts[0]
        print("\n--- First Alert Details ---")
        print(f"Event: {alert.get('event')}")
        print(f"Severity: {alert.get('severity')}")
        print(f"Area: {alert.get('area_desc')[:60]}")
        
        poly = alert.get('polygon_wkt', '')
        print(f"Polygon length: {len(poly)} chars")
        print(f"Has polygon: {bool(poly)}")
        
        if poly:
            print(f"Polygon preview: {poly[:100]}...")
    else:
        print("\nNo alerts parsed. Checking raw XML snippet...")
        print(resp.text[:500])
        
except Exception as e:
    print(f"Error: {e}")