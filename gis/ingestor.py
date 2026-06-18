# ============================================================
#  MHEWS — gis/ingestor.py
#  B10: CAP Feed Ingestor with fallback chain
#
#  Feed priority order:
#  1. SAWS (official SA feed — restricted, tries anyway)
#  2. GDACS (UN global hazards — always works)
#  3. NASA EONET (NASA natural events — always works)
#  4. ReliefWeb (UN humanitarian alerts)
#
#  If feed 1 fails → silently tries feed 2
#  If feed 2 fails → silently tries feed 3
#  Frontend never sees errors — always gets data
# ============================================================

import asyncio
import asyncpg
import os
import sys
import urllib.request
import urllib.error
import json
from datetime import datetime, timezone
from lxml import etree

sys.path.insert(0, '/usr/src/app')
from gis.cap_parser import (
    find_text, parse_polygon_string, coords_to_wkt,
    get_hazard_category, CAP_NAMESPACES, circle_to_bbox_polygon,
)

DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'postgres://postgres:postgres@db:5432/mhews'
)

# ============================================================
#  Feed chain — tried in order, first success wins
# ============================================================
FEED_CHAIN = [
    {
        'name':  'SAWS',
        'url':   'http://caps.weathersa.co.za/Home/RssFeed',
        'type':  'cap_rss',
        'desc':  'South African Weather Service (official)',
    },
    {
        'name':  'GDACS',
        'url':   'https://www.gdacs.org/xml/rss.xml',
        'type':  'gdacs_rss',
        'desc':  'Global Disaster Alert and Coordination System (UN)',
    },
    {
        'name':  'NASA EONET',
        'url':   'https://eonet.gsfc.nasa.gov/api/v3/events?status=open&bbox=10,-40,55,-20',
        'type':  'nasa_eonet',
        'desc':  'NASA Earth Observatory Natural Event Tracker (Africa bbox)',
    },
    {
        'name':  'ReliefWeb',
        'url':   'https://api.reliefweb.int/v1/disasters?appname=mhews&profile=list&preset=latest&fields[include][]=name&fields[include][]=country&fields[include][]=date&fields[include][]=status&filter[field]=country.iso3&filter[value]=ZAF',
        'type':  'reliefweb',
        'desc':  'ReliefWeb UN humanitarian alerts (South Africa)',
    },
]


# ============================================================
#  Fetch URL safely — returns None on any failure, no crash
# ============================================================
def fetch_url(url: str, timeout: int = 15) -> bytes | None:
    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'MHEWS/1.0 (MSc Thesis NWU South Africa)'}
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception:
        return None


# ============================================================
#  Parse datetime string to datetime object
# ============================================================
def parse_dt(dt_str: str):
    if not dt_str:
        return None
    try:
        import re
        dt_str = re.sub(r'([+-]\d{2}):(\d{2})$', r'\1\2', dt_str)
        return datetime.strptime(dt_str, '%Y-%m-%dT%H:%M:%S%z')
    except Exception:
        try:
            return datetime.fromisoformat(dt_str)
        except Exception:
            return None


# ============================================================
#  Extract CAP URLs from RSS feed
# ============================================================
def extract_cap_urls_from_rss(rss_bytes: bytes) -> list[str]:
    try:
        root = etree.fromstring(rss_bytes)
        urls = []
        for item in root.iter('item'):
            link = item.find('link')
            if link is not None and link.text:
                urls.append(link.text.strip())
            enc = item.find('enclosure')
            if enc is not None and enc.get('url'):
                urls.append(enc.get('url'))
        return urls
    except Exception:
        return []


# ============================================================
#  Parse multi-area CAP XML
# ============================================================
def parse_cap_all_areas(xml_bytes: bytes) -> list[dict]:
    results = []
    try:
        if isinstance(xml_bytes, str):
            xml_bytes = xml_bytes.encode('utf-8')
        root = etree.fromstring(xml_bytes)

        ns = {}
        for prefix, uri in root.nsmap.items():
            if uri and 'emergency:cap' in uri:
                ns = {'cap': uri}
                break
        full_ns = {**CAP_NAMESPACES, **ns}

        identifier = find_text(root, 'identifier', full_ns)
        sender     = find_text(root, 'sender',     full_ns)
        sent       = find_text(root, 'sent',       full_ns)

        info = None
        for prefix, uri in full_ns.items():
            infos = root.findall(f'{{{uri}}}info')
            if infos:
                info = infos[0]
                break
        if info is None:
            info = root.find('info')
        if info is None:
            return []

        event       = find_text(info, 'event',       full_ns)
        severity    = find_text(info, 'severity',    full_ns)
        urgency     = find_text(info, 'urgency',     full_ns)
        description = find_text(info, 'description', full_ns)
        instruction = find_text(info, 'instruction', full_ns)
        onset       = find_text(info, 'onset',       full_ns)
        expires     = find_text(info, 'expires',     full_ns)
        sender_name = find_text(info, 'senderName',  full_ns)
        source      = sender_name or sender or 'Unknown'

        areas = []
        for prefix, uri in full_ns.items():
            found = info.findall(f'{{{uri}}}area')
            if found:
                areas = found
                break
        if not areas:
            areas = info.findall('area')
        if not areas:
            return []

        for i, area in enumerate(areas):
            area_desc   = find_text(area, 'areaDesc', full_ns)
            polygon_str = find_text(area, 'polygon',  full_ns)
            circle_str  = find_text(area, 'circle',   full_ns)

            polygon_wkt = ''
            if polygon_str:
                coords = parse_polygon_string(polygon_str)
                if coords:
                    polygon_wkt = coords_to_wkt(coords)
            elif circle_str:
                polygon_wkt = circle_to_bbox_polygon(circle_str)

            if not polygon_wkt:
                continue

            area_id = f"{identifier}_area_{i}" if i > 0 else identifier

            results.append({
                'id':               area_id,
                'event':            event       or 'Unknown',
                'severity':         severity    or 'Unknown',
                'urgency':          urgency     or 'Unknown',
                'description':      description or '',
                'instruction':      instruction or '',
                'onset':            onset       or sent or '',
                'expires':          expires     or '',
                'source':           source,
                'area_desc':        area_desc   or '',
                'hazard_category':  get_hazard_category(event or ''),
                'polygon_wkt':      polygon_wkt,
                'plain_text':       None,
                'plain_text_language': 'en',
                'accuracy_percent': None,
            })

    except Exception as e:
        print(f"  ⚠️  CAP parse error: {e}")

    return results


# ============================================================
#  Parse NASA EONET JSON into alert records
# ============================================================
def parse_nasa_eonet(data: bytes) -> list[dict]:
    results = []
    try:
        obj    = json.loads(data)
        events = obj.get('events', [])

        for event in events:
            title      = event.get('title', 'Natural Event')
            categories = event.get('categories', [{}])
            cat_name   = categories[0].get('title', 'other') if categories else 'other'
            geometries = event.get('geometry', [])

            if not geometries:
                continue

            # Use the most recent geometry
            geom = geometries[-1]
            coords = geom.get('coordinates', [])
            geom_type = geom.get('type', '')
            date = geom.get('date', '')

            polygon_wkt = ''

            if geom_type == 'Point' and len(coords) >= 2:
                # Convert point to small bounding box (0.5 degree radius)
                lon, lat = coords[0], coords[1]
                polygon_wkt = (
                    f"POLYGON(({lon-0.5} {lat-0.5}, {lon+0.5} {lat-0.5}, "
                    f"{lon+0.5} {lat+0.5}, {lon-0.5} {lat+0.5}, "
                    f"{lon-0.5} {lat-0.5}))"
                )
            elif geom_type == 'Polygon':
                ring = coords[0] if coords else []
                if ring:
                    pts = ', '.join(f"{p[0]} {p[1]}" for p in ring)
                    polygon_wkt = f"POLYGON(({pts}))"

            if not polygon_wkt:
                continue

            event_id = f"NASA-EONET-{event.get('id', 'unknown')}"

            results.append({
                'id':               event_id,
                'event':            title,
                'severity':         'Unknown',
                'urgency':          'Unknown',
                'description':      f"NASA EONET: {title}. Category: {cat_name}.",
                'instruction':      'Monitor official sources for updates.',
                'onset':            date,
                'expires':          '',
                'source':           'NASA EONET',
                'area_desc':        title,
                'hazard_category':  get_hazard_category(cat_name),
                'polygon_wkt':      polygon_wkt,
                'plain_text':       f"{title} detected by NASA Earth Observatory.",
                'plain_text_language': 'en',
                'accuracy_percent': None,
            })

    except Exception as e:
        print(f"  ⚠️  NASA EONET parse error: {e}")

    return results


# ============================================================
#  Upsert alerts into PostGIS
# ============================================================
async def upsert_alerts(conn, alerts: list[dict]) -> int:
    inserted = 0
    for alert in alerts:
        try:
            result = await conn.execute("""
                INSERT INTO alerts (
                    id, event, severity, urgency,
                    description, instruction,
                    onset, expires, source,
                    area_desc, plain_text, plain_text_language,
                    accuracy_percent, hazard_category, polygon
                ) VALUES (
                    $1,$2,$3,$4,$5,$6,
                    $7::timestamptz,$8::timestamptz,$9,
                    $10,$11,$12,$13,$14,
                    ST_GeomFromText($15,4326)
                )
                ON CONFLICT (id) DO NOTHING
            """,
                alert['id'], alert['event'], alert['severity'],
                alert['urgency'], alert['description'], alert['instruction'],
                parse_dt(alert['onset']), parse_dt(alert['expires']),
                alert['source'], alert['area_desc'],
                alert['plain_text'], alert['plain_text_language'],
                alert['accuracy_percent'], alert['hazard_category'],
                alert['polygon_wkt'],
            )
            if result == 'INSERT 0 1':
                print(f"  ✅ {alert['area_desc']} ({alert['event']})")
                inserted += 1
            else:
                print(f"  ⏭  Already exists: {alert['id'][:50]}")
        except Exception as e:
            print(f"  ❌ DB error: {e}")
    return inserted


# ============================================================
#  Main poll — tries each feed in order, stops at first success
# ============================================================
async def poll_all_feeds():
    print(f"\n{'='*55}")
    print(f"MHEWS Feed Poll — {datetime.now().strftime('%Y-%m-%d %H:%M:%S SAST')}")
    print(f"{'='*55}")

    conn = await asyncpg.connect(DATABASE_URL)
    total = 0

    try:
        for feed in FEED_CHAIN:
            print(f"\n📡 Trying {feed['name']}: {feed['desc']}")

            data = fetch_url(feed['url'])
            if data is None:
                print(f"  ⏭  Unavailable — trying next source")
                continue

            print(f"  ✅ Connected — parsing alerts")
            alerts = []

            if feed['type'] in ('cap_rss', 'gdacs_rss'):
                cap_urls = extract_cap_urls_from_rss(data)
                print(f"  Found {len(cap_urls)} alert(s) in feed")
                for url in cap_urls[:20]:
                    cap_data = fetch_url(url)
                    if cap_data:
                        alerts.extend(parse_cap_all_areas(cap_data))

            elif feed['type'] == 'nasa_eonet':
                alerts = parse_nasa_eonet(data)
                print(f"  Found {len(alerts)} event(s)")

            elif feed['type'] == 'cap_xml':
                alerts = parse_cap_all_areas(data)

            if alerts:
                n = await upsert_alerts(conn, alerts)
                total += n
                print(f"  ✅ {feed['name']} delivered {len(alerts)} alert(s) — {n} new")
                # Got data — continue to next feed for more coverage
                # (don't break — collect from all available sources)
            else:
                print(f"  ⚠️  No alerts parsed from {feed['name']}")

    finally:
        await conn.close()

    print(f"\n{'='*55}")
    print(f"Poll complete — {total} new alert(s) inserted")
    print(f"{'='*55}\n")
    return total


# ============================================================
#  Ingest from a local CAP XML file
# ============================================================
async def ingest_from_file(filepath: str):
    print(f"📂 Loading CAP file: {filepath}")
    with open(filepath, 'rb') as f:
        xml_bytes = f.read()
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        alerts = parse_cap_all_areas(xml_bytes)
        inserted = await upsert_alerts(conn, alerts)
        print(f"✅ Inserted {inserted} new alert(s) from file")
    finally:
        await conn.close()


# ============================================================
#  Remove mock alerts
# ============================================================
async def remove_mock_alerts():
    mock_ids = [
        'SAWS-20240525-THU-001',
        'SAWS-20240525-FLD-002',
        'SAWS-20240525-WIND-003',
    ]
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        for mock_id in mock_ids:
            result = await conn.execute(
                "DELETE FROM alerts WHERE id = $1", mock_id
            )
            print(f"  Removed: {mock_id} ({result})")
        print("✅ Mock alerts removed")
    finally:
        await conn.close()


# ============================================================
#  CLI
# ============================================================
if __name__ == '__main__':
    if '--remove-mocks' in sys.argv:
        asyncio.run(remove_mock_alerts())
    elif '--file' in sys.argv:
        idx = sys.argv.index('--file')
        if idx + 1 < len(sys.argv):
            asyncio.run(ingest_from_file(sys.argv[idx + 1]))
        else:
            print("Usage: python -m gis.ingestor --file path/to/alert.xml")
    else:
        asyncio.run(poll_all_feeds())
