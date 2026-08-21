# gis/ingestor.py
import httpx
import asyncio
import sys
import os
from datetime import datetime, timezone, timedelta

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.main import database, startup
from gis.cap_parser import parse_feed

HEADERS = {"User-Agent": "MHEWS-Thesis/1.0"}
CONCURRENCY_LIMIT = 50

async def fetch_feeds():
    rows = await database.fetch_all(
        "SELECT country, organisation, feed_url FROM cap_sources WHERE enabled = TRUE")
    print(f"Polling {len(rows)} feeds from cap_sources...")
    return [dict(r) for r in rows]

def is_fresh(alert):
    now = datetime.now(timezone.utc)
    exp = alert.get("expires")
    onset = alert.get("effective")

    # If it has an expiry, it must be in the future.
    if exp is not None and exp < now:
        return False

    # If it has an onset, it must be within the last 30 days.
    if onset is not None and onset < now - timedelta(days=30):
        return False

    # If dates are missing, assume it is fresh. Don't drop good data!
    return True

INSERT_ALERT_SQL = """
    INSERT INTO alerts (id, event, severity, urgency, description, instruction,
            source, area_desc, hazard_category, onset, expires, polygon, last_seen_at)
    VALUES (:id, :event, :severity, :urgency, :description, :instruction,
            :source, :area_desc, :hazard_category, :onset, :expires,
            ST_GeomFromText(CAST(:polygon AS text), 4326), NOW())
    ON CONFLICT (id) DO UPDATE SET
        event = EXCLUDED.event, severity = EXCLUDED.severity,
        description = EXCLUDED.description, instruction = EXCLUDED.instruction,
        expires = EXCLUDED.expires, polygon = EXCLUDED.polygon,
        last_seen_at = NOW()
"""

async def get_country_polygon(country_name):
    """Fallback: Get the official WMO shape for this country if the alert lacks one."""
    row = await database.fetch_one(
        "SELECT polygon_wkt FROM country_polygons WHERE country_name ILIKE :name LIMIT 1",
        {"name": f"%{country_name}%"}
    )
    return row['polygon_wkt'] if row else None

async def process_feed(feed, semaphore):
    async with semaphore:
        url, org, country = feed['feed_url'], feed['organisation'], feed['country']
        try:
            async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=HEADERS)
                resp.raise_for_status()

            alerts = [a for a in parse_feed(resp.content, url, country) if is_fresh(a)]
            if not alerts:
                return 0

            count = 0
            for alert in alerts:
                # --- NEW: KILL OLD ONSET DATES ---
                onset = alert.get('effective')
                if onset and (datetime.now(timezone.utc) - onset).days > 3:
                    continue  # Skip alerts that started more than 3 days ago
                # -----------------------------------

                # --- FIX: Ensure onset is never None ---
                effective_dt = alert.get('effective')
                if effective_dt is None:
                    effective_dt = datetime.now(timezone.utc)

                expires_dt = alert.get('expires')

                # THE FIX: If the alert has no polygon, fetch the country's master polygon
                polygon = alert.get('polygon')
                if not polygon:
                    polygon = await get_country_polygon(country)
                    
                try:
                    await database.execute(INSERT_ALERT_SQL, values={
                        "id": alert['identifier'],
                        "event": alert['event'],
                        "severity": alert['severity'],
                        "urgency": alert['urgency'],
                        "description": alert['description'],
                        "instruction": alert['instruction'],
                        "source": country if alert.get('sender') == 'Unknown' or not alert.get('sender') else alert['sender'],
                        "area_desc": alert['area'],
                        "hazard_category": alert['hazard_category'],
                        "onset": effective_dt,
                        "expires": expires_dt,
                        "polygon": polygon,
                    })
                    count += 1
                except Exception as e:
                    print(f"   ⚠️ DB Insert Error for {alert.get('event')}: {e}")
            
            if count > 0:
                print(f"  ✅ {org}: inserted {count} live alerts.")
            return count
        except Exception as e:
            print(f"⚠️ Feed processing error for {url}: {e}")
            return 0

async def poll_all_feeds():
    print("🔄 Starting automatic poll with polygon fallback...")
    feeds = await fetch_feeds()
    
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    tasks = [process_feed(feed, semaphore) for feed in feeds]
    
    results = await asyncio.gather(*tasks)
    
    total = sum(results)
    print(f"🏁 Ingestion complete. Total live alerts inserted/updated: {total}")

async def main():
    await startup()
    try:
        await poll_all_feeds()
    finally:
        await database.disconnect()

if __name__ == '__main__':
    asyncio.run(main())