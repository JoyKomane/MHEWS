"""
wmo_register_checker.py
"""
import argparse
import csv
import time
import sys
from datetime import datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://alertingauthority.wmo.int/"
# FIXED: Replaced em-dash with standard hyphens for ASCII compatibility
HEADERS = {
    "User-Agent": "MHEWS-Research-Bot (Academic-Research-MSc-NWU-South-Africa)"
}
REQUEST_DELAY_SECONDS = 1.5
REQUEST_TIMEOUT = 20
FEED_KEYWORDS = ["cap", "rss", "atom", ".xml", "feed"]

def safe_get(url, timeout=REQUEST_TIMEOUT):
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout, headers=HEADERS) as client:
            return client.get(url)
    except Exception as e: # FIXED: Catch all exceptions safely
        print(f"  ⚠️  Request failed: {e}")
        return None

def find_country_links(html):
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(BASE_URL, a["href"])
        text = a.get_text(strip=True)
        if href.startswith(BASE_URL):
            links.append((text, href))
    return list(dict.fromkeys(links))

def verify_feed_url(url):
    r = safe_get(url, timeout=15)
    if r is None:
        return False, None, None, "no response"
    
    content_type = r.headers.get("Content-Type", "")
    text_snippet = r.text[:500].strip().lower()
    
    looks_like_feed = (
        "xml" in content_type.lower() or 
        "rss" in content_type.lower() or 
        "atom" in content_type.lower() or
        text_snippet.startswith("<?xml") or
        "<rss" in text_snippet or
        "<feed" in text_snippet
    )
    
    if r.status_code == 200 and looks_like_feed:
        return True, r.status_code, content_type, "confirmed feed"
    if r.status_code == 200:
        return False, r.status_code, content_type, "200 but not XML/feed content"
    return False, r.status_code, content_type, f"HTTP {r.status_code}"

def inspect_country_page(name, url, results):
    print("=" * 70)
    print(f"{name}\n{url}")

    r = safe_get(url)
    if r is None or r.status_code != 200:
        print(f"  ❌ Could not load page (status: {r.status_code if r else 'no response'})")
        results.append({
            "country_or_authority": name, "register_page": url,
            "candidate_link_text": "", "candidate_link_url": "",
            "verified_working": False, "note": "register page itself failed to load",
        })
        return

    soup = BeautifulSoup(r.text, "html.parser")
    found_any = False

    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(" ", strip=True)
        haystack = (href + " " + text).lower()

        if any(k in haystack for k in FEED_KEYWORDS):
            found_any = True
            candidate_url = urljoin(url, href)
            print(f"\n  Possible feed link: {text}\n  {candidate_url}")

            time.sleep(REQUEST_DELAY_SECONDS)
            is_working, status, ctype, note = verify_feed_url(candidate_url)
            status_icon = "✅" if is_working else "⚠️"
            print(f"  {status_icon} {note} (HTTP {status}, {ctype})")

            results.append({
                "country_or_authority": name, "register_page": url,
                "candidate_link_text": text, "candidate_link_url": candidate_url,
                "verified_working": is_working, "note": note,
            })

    if not found_any:
        print("  No obvious CAP/RSS/Atom links found on this page.")
        results.append({
            "country_or_authority": name, "register_page": url,
            "candidate_link_text": "", "candidate_link_url": "",
            "verified_working": False, "note": "no feed-like links found",
        })

def save_results(results):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"wmo_register_results_{timestamp}.csv"
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "country_or_authority", "register_page", "candidate_link_text",
            "candidate_link_url", "verified_working", "note",
        ])
        writer.writeheader()
        writer.writerows(results)
    print(f"\n💾 Saved {len(results)} row(s) to {filename}")
    return filename

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    print(f"📡 Downloading WMO register homepage: {BASE_URL}")
    r = safe_get(BASE_URL)
    if r is None or r.status_code != 200:
        print("❌ Could not load the WMO register homepage. Aborting.")
        sys.exit(1)

    countries = find_country_links(r.text)
    print(f"\n✅ Found {len(countries)} link(s) on the register homepage.")

    if args.limit:
        countries = countries[:args.limit]
        print(f"   (Limited to first {args.limit} for this run)")

    results = []
    for i, (name, url) in enumerate(countries, 1):
        print(f"\n[{i}/{len(countries)}]")
        inspect_country_page(name, url, results)
        time.sleep(REQUEST_DELAY_SECONDS)

    filename = save_results(results)

    working = [r for r in results if r["verified_working"]]
    print(f"\n{'='*70}")
    print(f"SUMMARY: {len(working)} confirmed working feed(s) out of {len(results)} candidate(s) checked.")
    print(f"Review the full details in {filename}")
    print(f"{'='*70}")

if __name__ == "__main__":
    main()