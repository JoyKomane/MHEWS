# gis/wmo_scraper.py
import httpx
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from backend.main import database

S3_BUCKET_URL = "https://cap-sources.s3.amazonaws.com/"
S3_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"
SOURCES_URL = "https://severeweather.wmo.int/sources.html"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MHEWS-Thesis/1.0"}

# Fallback ONLY if the directory page can't be parsed (Europe publishes via MeteoAlarm)
METEOALARM = ["austria","belgium","bosnia-herzegovina","bulgaria","croatia","cyprus","czechia",
              "denmark","estonia","finland","france","germany","greece","hungary","iceland",
              "ireland","italy","latvia","liechtenstein","lithuania","luxembourg","malta",
              "moldova","monaco","montenegro","netherlands","north-macedonia","norway","poland",
              "portugal","romania","serbia","slovakia","slovenia","spain","switzerland",
              "ukraine","united-kingdom"]

async def _s3_feeds():
    feeds, marker = [], ""
    async with httpx.AsyncClient(timeout=30.0, headers=HEADERS) as client:
        while True:
            url = f"{S3_BUCKET_URL}?delimiter=/" + (f"&marker={marker}" if marker else "")
            resp = await client.get(url); resp.raise_for_status()
            root = ET.fromstring(resp.content)
            for cp in root.findall(f"{S3_NS}CommonPrefixes"):
                p = cp.find(f"{S3_NS}Prefix")
                if p is not None and p.text and p.text.endswith("/"):
                    folder = p.text[:-1]
                    feeds.append({"country": folder.split("-")[0].upper(),
                                  "organisation": folder.upper(),
                                  "feed_url": f"{S3_BUCKET_URL}{folder}/rss.xml"})
            if root.findtext(f"{S3_NS}IsTruncated") == "true":
                marker = root.findtext(f"{S3_NS}NextMarker") or ""
                if not marker: break
            else:
                break
    return feeds

async def _external_feeds():
    """Harvest every feed link from the WMO directory table (any layout)."""
    feeds = []
    try:
        async with httpx.AsyncClient(timeout=20.0, headers=HEADERS, follow_redirects=True) as client:
            resp = await client.get(SOURCES_URL); resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")
        for tr in soup.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if len(cells) < 2: continue
            org = cells[0].get_text(strip=True)
            if not org: continue
            country = org.split(":")[0].strip()
            for cell in cells[1:]:                     # feed links live after the org cell
                for a in cell.find_all("a", href=True):
                    if a["href"].strip().startswith("http"):
                        feeds.append({"country": country, "organisation": org,
                                      "feed_url": a["href"].strip()})
        print(f"Directory scrape found {len(feeds)} external feeds.")
    except Exception as e:
        print(f"Directory scrape failed: {e}")
    if not feeds:  # fallback: Europe via MeteoAlarm
        feeds = [{"country": s.replace("-", " ").title(),
                  "organisation": f"MeteoAlarm ({s})",
                  "feed_url": f"https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-{s}"}
                 for s in METEOALARM]
    return feeds

async def discover_sources():
    print("Discovering WMO sources (S3 bucket + external directory)...")
    s3, ext = await _s3_feeds(), await _external_feeds()
    seen, unique = set(), []
    for f in s3 + ext:
        if f["feed_url"] not in seen:
            seen.add(f["feed_url"]); unique.append(f)
    await database.execute("DELETE FROM cap_sources")
    await database.execute_many(
        "INSERT INTO cap_sources (country, organisation, language, feed_url, region) "
        "VALUES (:country, :organisation, 'en', :feed_url, 'WMO')", unique)
    print(f"Stored {len(unique)} feeds ({len(s3)} S3 + {len(ext)} external).")

if __name__ == '__main__':
    import asyncio, sys, os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from backend.main import database, startup
    async def main():
        await startup()
        try: await discover_sources()
        finally: await database.disconnect()
    asyncio.run(main())