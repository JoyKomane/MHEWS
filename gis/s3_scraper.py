# gis/s3_scraper.py
import httpx
import xml.etree.ElementTree as ET
from backend.main import database

S3_BUCKET_URL = "https://cap-sources.s3.amazonaws.com/"
# The exact default namespace used by AWS S3 XML responses
S3_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"

async def scrape_s3_sources():
    print(" Fetching WMO S3 bucket directory...")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(S3_BUCKET_URL)
            resp.raise_for_status()
            
        root = ET.fromstring(resp.content)
        
        # Find all <Contents> blocks using the explicit default namespace
        contents = root.findall(f".//{S3_NS}Contents")
        
        sources_to_insert = []
        for content in contents:
            key_elem = content.find(f"{S3_NS}Key")
            if key_elem is not None and key_elem.text and key_elem.text.endswith('/'):
                folder = key_elem.text
                feed_url = f"{S3_BUCKET_URL}{folder}rss.xml"
                org_code = folder.replace('/', '').upper()
                
                sources_to_insert.append({
                    "country": "Unknown",
                    "organisation": org_code,
                    "language": "en",
                    "feed_url": feed_url,
                    "region": "Global"
                })
                
        if sources_to_insert:
            await database.execute_many(
                "INSERT INTO cap_sources (country, organisation, language, feed_url, region) VALUES (:country, :organisation, :language, :feed_url, :region) ON CONFLICT (feed_url) DO NOTHING",
                sources_to_insert
            )
            print(f"✅ Successfully inserted {len(sources_to_insert)} live feed URLs into cap_sources.")
        else:
            print("⚠️ No folders found in S3 bucket.")
            
    except Exception as e:
        print(f"❌ Failed to scrape S3 bucket: {e}")

if __name__ == '__main__':
    import asyncio, sys, os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from backend.main import database, startup
    
    async def main():
        await startup()
        try: 
            await scrape_s3_sources()
        except Exception as e:
            print(f"❌ Fatal error: {e}")
        finally: 
            await database.disconnect() 
            
    asyncio.run(main())