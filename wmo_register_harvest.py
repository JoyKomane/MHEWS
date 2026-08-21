"""
wmo_register_harvest.py
Final reconnaissance tool: harvest CAP feed URLs from the WMO Register
of Alerting Authorities. Does NOT touch your MHEWS database.
"""
import csv
import time
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

BASE = "https://alertingauthority.wmo.int/"
HEADERS = {"User-Agent": "MHEWS Research Bot (Academic Research - MSc NWU South Africa)"}
DELAY = 1.0
MAX_RECID = 450

def get(client, url):
    try:
        r = client.get(url, headers=HEADERS, timeout=20, follow_redirects=True)
        return r if r.status_code == 200 else None
    except Exception:
        return None

def main():
    results = []
    with httpx.Client() as client:
        # Step 1: try the index page for recId links
        r = get(client, BASE + "authorities.php")
        targets = []
        if r:
            soup = BeautifulSoup(r.text, "html.parser")
            targets = [urljoin(BASE, a["href"]) for a in soup.find_all("a", href=True) if "recId=" in a["href"]]
        print(f"Index page gave {len(targets)} recId links.")

        # Step 2: fall back to walking the ID range
        if not targets:
            targets = [f"{BASE}authorities.php?recId={i}" for i in range(1, MAX_RECID + 1)]

        for i, url in enumerate(targets, 1):
            if i % 25 == 0:
                print(f"... progress: {i}/{len(targets)} pages checked, {len(results)} feeds found so far")
            r = get(client, url)
            if r is None:
                time.sleep(0.3)
                continue

            soup = BeautifulSoup(r.text, "html.parser")
            title = soup.title.get_text(strip=True) if soup.title else ""

            feeds = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.startswith("http") and "alertingauthority.wmo.int" not in href:
                    feeds.append((a.get_text(" ", strip=True), href))

            if feeds:
                print(f"[{i}/{len(targets)}] {url} -> {len(feeds)} feed(s)")
                for text, href in feeds:
                    results.append({
                        "country_or_authority": title,
                        "register_page": url,
                        "link_text": text,
                        "feed_url": href,
                    })
            time.sleep(DELAY)

    ts = time.strftime("%Y%m%d_%H%M%S")
    fn = f"wmo_register_feeds_{ts}.csv"
    with open(fn, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["country_or_authority", "register_page", "link_text", "feed_url"])
        w.writeheader()
        w.writerows(results)
    print(f"\nSaved {len(results)} feed URLs to {fn}")

if __name__ == "__main__":
    main()