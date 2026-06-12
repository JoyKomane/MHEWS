# ============================================================
#  MHEWS — gis/ingestor.py
#  B10: CAP Feed Ingestor
#
#  This module does three things:
#  1. Fetches CAP XML from a feed URL (SAWS, GDACS, WMO)
#  2. Parses each alert using cap_parser.py (B7)
#  3. Upserts it into PostGIS — no duplicates ever
#
#  It handles multi-area alerts — one CAP alert can cover
#  multiple polygons (e.g. Witzenberg AND Hantam AND Karoo).
#  Each area gets its own row in the database.
#
#  Can be run manually:
#    docker exec -it mhews-app-1 bash -c "cd /usr/src/app && python -m gis.ingestor"
#
#  Or called by the FastAPI startup to poll on a schedule.
# ============================================================

import asyncio
import asyncpg
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from lxml import etree

# ── Import our CAP parser ──────────────────────────────────
import sys
sys.path.insert(0, '/usr/src/app')
from gis.cap_parser import (
    parse_cap_xml,
    find_text,
    parse_polygon_string,
    coords_to_wkt,
    get_hazard_category,
    CAP_NAMESPACES,
    circle_to_bbox_polygon,
)

# ── Feed URLs ──────────────────────────────────────────────
FEEDS = [
    {
        'name': 'SAWS',
        'url':  'http://caps.weathersa.co.za/Home/RssFeed',
        'type': 'cap_rss',   # RSS feed of CAP alerts
    },
    {
        'name': 'GDACS',
        'url':  'https://www.gdacs.org/xml/rss.xml',
        'type': 'gdacs_rss',
    },
]

DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'postgres://postgres:postgres@db:5432/mhews'
)


# ============================================================
#  Fetch a URL safely
# ============================================================
def fetch_url(url: str, timeout: int = 15) -> bytes | None:
    """
    Fetches a URL and returns the raw bytes.
    Returns None on any error — never crashes the ingestor.
    """
    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'MHEWS/1.0 (MSc Thesis; NWU South Africa)'}
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} — {url}")
        return None
    except urllib.error.URLError as e:
        print(f"  URL error — {e.reason}")
        return None
    except Exception as e:
        print(f"  Error fetching {url}: {e}")
        return None


# ============================================================
#  Parse a SAWS CAP RSS feed
# ============================================================
def extract_cap_urls_from_rss(rss_bytes: bytes) -> list[str]:
    """
    SAWS publishes an RSS feed where each <item> links to
    a CAP XML alert. This function extracts those URLs.
    """
    try:
        root = etree.fromstring(rss_bytes)
        urls = []
        # Find all <link> elements in RSS items
        for item in root.iter('item'):
            link = item.find('link')
            if link is not None and link.text:
                urls.append(link.text.strip())
            # Also check enclosure tags
            enc = item.find('enclosure')
            if enc is not None:
                url = enc.get('url', '')
                if url:
                    urls.append(url)
        return urls
    except Exception as e:
        print(f"  Could not parse RSS: {e}")
        return []


# ============================================================
#  Parse multi-area CAP XML
# ============================================================
def parse_cap_all_areas(xml_bytes: bytes) -> list[dict]:
    """
    A single CAP alert can have ONE <info> block but
    MULTIPLE <area> blocks — one per affected region.

    This function returns ONE dict per area, each with
    its own polygon and areaDesc but sharing the same
    event/severity/description.

    This is the key difference from the basic parser —
    it handles the real SAWS format which often covers
    multiple municipalities in one alert.
    """
    results = []

    try:
        if isinstance(xml_bytes, str):
            xml_bytes = xml_bytes.encode('utf-8')

        root = etree.fromstring(xml_bytes)

        # Detect namespace
        ns = {}
        for prefix, uri in root.nsmap.items():
            if uri and 'emergency:cap' in uri:
                ns = {'cap': uri}
                break
        full_ns = {**CAP_NAMESPACES, **ns}

        # Alert-level fields
        identifier = find_text(root, 'identifier', full_ns)
        sender     = find_text(root, 'sender',     full_ns)
        sent       = find_text(root, 'sent',       full_ns)

        # Find the info block
        info = None
        for prefix, uri in full_ns.items():
            infos = root.findall(f'{{{uri}}}info')
            if infos:
                info = infos[0]
                break
        if info is None:
            info = root.find('info')
        if info is None:
            print(f"  No <info> block in alert {identifier}")
            return []

        # Info-level fields (shared across all areas)
        event       = find_text(info, 'event',       full_ns)
        severity    = find_text(info, 'severity',    full_ns)
        urgency     = find_text(info, 'urgency',     full_ns)
        description = find_text(info, 'description', full_ns)
        instruction = find_text(info, 'instruction', full_ns)
        onset       = find_text(info, 'onset',       full_ns)
        expires     = find_text(info, 'expires',     full_ns)
        sender_name = find_text(info, 'senderName',  full_ns)
        headline    = find_text(info, 'headline',    full_ns)

        source = sender_name or sender or 'SAWS'

        # Find ALL area blocks
        areas = []
        for prefix, uri in full_ns.items():
            found = info.findall(f'{{{uri}}}area')
            if found:
                areas = found
                break
        if not areas:
            areas = info.findall('area')

        if not areas:
            print(f"  No <area> blocks in alert {identifier}")
            return []

        print(f"  Found {len(areas)} area(s) in alert '{event}'")

        # Build one record per area
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
                print(f"  Skipping area '{area_desc}' — no valid polygon")
                continue

            # Make a unique ID per area
            # Format: base_identifier + _area_N
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

        return results

    except Exception as e:
        print(f"  Error parsing multi-area CAP: {e}")
        return []


# ============================================================
#  Ingest a single CAP XML string into PostGIS
# ============================================================
def parse_dt(dt_str: str):
    """Converts ISO datetime string to datetime object for asyncpg."""
    if not dt_str:
        return None
    try:
        from datetime import datetime, timezone
        import re
        # Handle timezone offset like +02:00
        dt_str = re.sub(r'([+-]\d{2}):(\d{2})$', r'\1\2', dt_str)
        return datetime.strptime(dt_str, '%Y-%m-%dT%H:%M:%S%z')
    except Exception:
        try:
            return datetime.fromisoformat(dt_str)
        except Exception:
            return None


async def ingest_cap_xml(conn, xml_bytes: bytes) -> int:
    """
    Parses a CAP XML alert and upserts all its areas
    into the PostGIS database.

    Returns the number of new alerts inserted.
    """
    alerts = parse_cap_all_areas(xml_bytes)
    inserted = 0

    for alert in alerts:
        try:
            # Use ON CONFLICT DO NOTHING so re-running
            # the ingestor never creates duplicates
            result = await conn.execute("""
                INSERT INTO alerts (
                    id, event, severity, urgency,
                    description, instruction,
                    onset, expires, source,
                    area_desc, plain_text, plain_text_language,
                    accuracy_percent, hazard_category, polygon
                ) VALUES (
                    $1, $2, $3, $4,
                    $5, $6,
                    $7::timestamptz, $8::timestamptz, $9,
                    $10, $11, $12,
                    $13, $14,
                    ST_GeomFromText($15, 4326)
                )
                ON CONFLICT (id) DO NOTHING
            """,
                alert['id'],
                alert['event'],
                alert['severity'],
                alert['urgency'],
                alert['description'],
                alert['instruction'],
                parse_dt(alert['onset']),
                parse_dt(alert['expires']),
                alert['source'],
                alert['area_desc'],
                alert['plain_text'],
                alert['plain_text_language'],
                alert['accuracy_percent'],
                alert['hazard_category'],
                alert['polygon_wkt'],
            )

            if result == 'INSERT 0 1':
                print(f"  ✅ Inserted: {alert['area_desc']} ({alert['event']})")
                inserted += 1
            else:
                print(f"  ⏭  Already exists: {alert['id'][:40]}")

        except Exception as e:
            print(f"  ❌ DB error for {alert['id'][:40]}: {e}")

    return inserted


# ============================================================
#  Ingest from a CAP XML file (for testing with real files)
# ============================================================
async def ingest_from_file(filepath: str):
    """
    Ingests a CAP XML file directly into PostGIS.
    Use this to load real SAWS CAP files from your supervisor.

    Usage:
      docker exec -it mhews-app-1 bash -c
      "cd /usr/src/app && python -m gis.ingestor --file /usr/src/app/gis/saws_alert.xml"
    """
    print(f"📂 Loading CAP file: {filepath}")
    with open(filepath, 'rb') as f:
        xml_bytes = f.read()

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        inserted = await ingest_cap_xml(conn, xml_bytes)
        print(f"✅ Inserted {inserted} new alert(s) from file")
    finally:
        await conn.close()


# ============================================================
#  Poll all configured feeds
# ============================================================
async def poll_all_feeds():
    """
    Fetches and ingests alerts from all configured feed URLs.
    Skips feeds that are unreachable without crashing.
    """
    print(f"\n{'='*50}")
    print(f"MHEWS Feed Poll — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")

    conn = await asyncpg.connect(DATABASE_URL)
    total_inserted = 0

    try:
        for feed in FEEDS:
            print(f"\n📡 Polling {feed['name']}: {feed['url']}")

            data = fetch_url(feed['url'])
            if data is None:
                print(f"  ⚠️  Skipping — feed unreachable")
                continue

            # For RSS feeds, extract individual CAP URLs
            if feed['type'] in ('cap_rss', 'gdacs_rss'):
                cap_urls = extract_cap_urls_from_rss(data)
                print(f"  Found {len(cap_urls)} CAP alert URL(s) in feed")

                for cap_url in cap_urls[:20]:  # Limit to 20 per poll
                    print(f"  Fetching: {cap_url[:80]}")
                    cap_data = fetch_url(cap_url)
                    if cap_data:
                        n = await ingest_cap_xml(conn, cap_data)
                        total_inserted += n

            # For direct CAP XML feeds
            elif feed['type'] == 'cap_xml':
                n = await ingest_cap_xml(conn, data)
                total_inserted += n

    finally:
        await conn.close()

    print(f"\n{'='*50}")
    print(f"Poll complete — {total_inserted} new alert(s) inserted")
    print(f"{'='*50}\n")
    return total_inserted


# ============================================================
#  Remove mock/expired alerts
# ============================================================
async def remove_mock_alerts():
    """
    Removes the 3 original mock alerts from the database.
    Call this once real alerts are flowing in.
    """
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
            print(f"  Removed mock: {mock_id} ({result})")
        print("✅ Mock alerts removed")
    finally:
        await conn.close()


# ============================================================
#  CLI entry point
# ============================================================
if __name__ == '__main__':
    import sys

    if '--remove-mocks' in sys.argv:
        print("Removing mock alerts...")
        asyncio.run(remove_mock_alerts())

    elif '--file' in sys.argv:
        idx = sys.argv.index('--file')
        if idx + 1 < len(sys.argv):
            asyncio.run(ingest_from_file(sys.argv[idx + 1]))
        else:
            print("Usage: python -m gis.ingestor --file path/to/alert.xml")

    else:
        print("Running feed poll...")
        asyncio.run(poll_all_feeds())
