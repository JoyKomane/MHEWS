import csv
import glob
import os
import asyncio
from backend.main import database, startup

INSERT_SQL = """
    INSERT INTO cap_sources (country, organisation, feed_url, region, language, enabled)
    VALUES (:country, :organisation, :feed_url, 'WMO-Register', 'en', TRUE)
    ON CONFLICT (feed_url) DO NOTHING
"""

async def import_feeds(csv_file):
    print(f"📥 Importing feeds from {csv_file} into cap_sources...")
    
    processed = 0
    with open(csv_file, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            country_name = row.get('country_or_authority', 'Unknown')[:100]
            link_text = row.get('link_text', '')[:255]
            feed_url = row.get('feed_url', '')[:500]
            
            if not feed_url.startswith('http'):
                continue
                
            org = link_text if link_text else country_name
            
            try:
                await database.execute(INSERT_SQL, values={
                    "country": country_name,
                    "organisation": org,
                    "feed_url": feed_url,
                })
                processed += 1
            except Exception:
                pass # Ignore duplicates silently
                
    print(f"✅ Processed {processed} rows from CSV.")
    
    total = await database.fetch_val("SELECT count(*) FROM cap_sources WHERE enabled = TRUE")
    print(f"🌍 Total active feeds now in cap_sources: {total}")

async def main():
    await startup()
    
    csv_files = glob.glob("wmo_register_feeds_*.csv")
    if not csv_files:
        print("❌ No wmo_register_feeds_*.csv files found.")
        return
        
    latest_csv = max(csv_files, key=os.path.getctime)
    
    try:
        await import_feeds(latest_csv)
    finally:
        await database.disconnect()

if __name__ == '__main__':
    asyncio.run(main())